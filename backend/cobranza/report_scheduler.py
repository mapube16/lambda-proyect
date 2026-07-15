"""
report_scheduler.py — cron de los reportes diario/semanal (informe §12).

Diario: 13:00 hora Colombia (18:00 UTC, Bogotá no tiene horario de verano),
L-Sáb (domingo no hay operación bajo Ley 2300, no tiene sentido reportar 0s).
Semanal: lunes 13:05 CO, cubre la semana ANTERIOR completa (lun-dom).

Registrado desde main.py junto a register_cobranza_jobs, mismo patrón: itera
todos los tenants con cobranza_enabled y corre el reporte de cada uno — un
fallo de un tenant no debe afectar a los demás.
"""
import logging
from datetime import date, timedelta

from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("cobranza.report_scheduler")

_JOB_IDS = ("cobr_reporte_diario", "cobr_reporte_semanal")


async def _tenant_ids(db) -> list:
    cur = db.company_voice.find({"cobranza_enabled": True}, {"user_id": 1})
    return [d["user_id"] async for d in cur]


async def reporte_diario_job() -> None:
    from database import get_db
    from cobranza.reports import run_daily_report

    db = get_db()
    for user_id in await _tenant_ids(db):
        try:
            res = await run_daily_report(db, user_id)
            logger.info("[report_scheduler] diario user=%s enviado=%s", user_id, res["envio"].get("sent"))
        except Exception:
            logger.exception("[report_scheduler] diario falló user=%s", user_id)


async def reporte_semanal_job() -> None:
    from database import get_db
    from cobranza.reports import run_weekly_report

    db = get_db()
    semana_fin = date.today() - timedelta(days=1)  # domingo: cierra la semana lun-dom anterior
    for user_id in await _tenant_ids(db):
        try:
            res = await run_weekly_report(db, user_id, semana_fin)
            logger.info("[report_scheduler] semanal user=%s enviado=%s", user_id, res["envio"].get("sent"))
        except Exception:
            logger.exception("[report_scheduler] semanal falló user=%s", user_id)


async def fin_jornada_check_job() -> None:
    """Cada 15 min: si la ÚLTIMA franja del tenant ya cerró hoy, hubo actividad
    (llamadas iniciadas) y el informe de fin de jornada no se ha enviado aún,
    lo envía UNA vez (flag idempotente en cobranza_runtime). Chequeo periódico
    en vez de cron fijo: la hora de cierre es config por tenant y puede cambiar
    en caliente (hoy mismo se extendió 16:00→17:00)."""
    from datetime import datetime
    import pytz
    from database import get_db
    from cobranza.reports import run_fin_jornada_report

    db = get_db()
    co = pytz.timezone("America/Bogota")
    ahora = datetime.now(co)
    hoy = ahora.date().isoformat()
    hhmm = ahora.strftime("%H:%M")

    for user_id in await _tenant_ids(db):
        try:
            flag_id = f"fin_jornada_sent:{user_id}"
            flag = await db.cobranza_runtime.find_one({"_id": flag_id})
            if flag and flag.get("fecha") == hoy:
                continue  # ya enviado hoy

            from cobranza.config_cache import get_tenant_config
            cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
            franjas = (cfg.get("horarios") or {}).get("franjas") or [["09:00", "12:00"], ["14:00", "16:00"]]
            cierre = max(f[1] for f in franjas)
            if hhmm <= cierre:
                continue  # la jornada sigue abierta

            stats = await db.cobranza_daily_stats.find_one({"user_id": user_id, "fecha": hoy})
            if not int((stats or {}).get("llamadas_iniciadas") or 0):
                continue  # hoy no hubo jornada (festivo / no autorizada) — nada que informar

            res = await run_fin_jornada_report(db, user_id)
            await db.cobranza_runtime.update_one(
                {"_id": flag_id},
                {"$set": {"fecha": hoy, "sent_at": datetime.now(pytz.utc),
                          "enviado": res["envio"].get("sent")}},
                upsert=True,
            )
            logger.info("[report_scheduler] fin_jornada user=%s enviado=%s", user_id, res["envio"].get("sent"))
        except Exception:
            logger.exception("[report_scheduler] fin_jornada falló user=%s", user_id)


async def jornada_notificaciones_job() -> None:
    """Cada 5 min, por tenant:
    - INICIO: la jornada quedó autorizada y salió la primera llamada del día →
      correo '🟢 Operación iniciada' (una vez al día, flag idempotente).
    - RECORDATORIO: la franja ya abrió, hay día hábil, y la jornada NO está
      autorizada → correo '⚠️ Jornada sin autorizar' (máx 3, cada ~2h)."""
    from datetime import datetime, timezone as _tzu
    import pytz
    from database import get_db
    from cobranza.call_scheduler import is_business_day
    from cobranza.campaign_scheduler import is_jornada_authorized
    from cobranza.reports import run_inicio_jornada_email, run_recordatorio_autorizacion

    db = get_db()
    co = pytz.timezone("America/Bogota")
    ahora = datetime.now(co)
    if not is_business_day(ahora.date()):
        return
    hoy = ahora.date().isoformat()
    hhmm = ahora.strftime("%H:%M")

    for user_id in await _tenant_ids(db):
        try:
            from cobranza.config_cache import get_tenant_config
            cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
            franjas = (cfg.get("horarios") or {}).get("franjas") or [["09:00", "12:00"], ["14:00", "16:00"]]
            apertura, cierre = min(f[0] for f in franjas), max(f[1] for f in franjas)
            if not (apertura <= hhmm <= cierre):
                continue  # fuera del horario de operación — nada que avisar

            autorizada = await is_jornada_authorized(user_id)
            stats = await db.cobranza_daily_stats.find_one({"user_id": user_id, "fecha": hoy})
            iniciadas = int((stats or {}).get("llamadas_iniciadas") or 0)

            if autorizada and iniciadas > 0:
                # INICIO (una vez)
                flag_id = f"inicio_jornada_sent:{user_id}"
                flag = await db.cobranza_runtime.find_one({"_id": flag_id})
                if not (flag and flag.get("fecha") == hoy):
                    res = await run_inicio_jornada_email(db, user_id)
                    await db.cobranza_runtime.update_one(
                        {"_id": flag_id},
                        {"$set": {"fecha": hoy, "sent_at": datetime.now(_tzu.utc)}},
                        upsert=True,
                    )
                    logger.info("[report_scheduler] inicio_jornada user=%s enviado=%s",
                                user_id, res["envio"].get("sent"))
            elif not autorizada:
                # RECORDATORIO (máx 3/día, cada 2h)
                flag_id = f"jornada_reminder:{user_id}"
                flag = await db.cobranza_runtime.find_one({"_id": flag_id}) or {}
                count = int(flag.get("count") or 0) if flag.get("fecha") == hoy else 0
                last = flag.get("last_at") if flag.get("fecha") == hoy else None
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=_tzu.utc)
                horas_desde = ((datetime.now(_tzu.utc) - last).total_seconds() / 3600) if last else 99
                if count < 3 and horas_desde >= 2:
                    res = await run_recordatorio_autorizacion(db, user_id, count + 1)
                    await db.cobranza_runtime.update_one(
                        {"_id": flag_id},
                        {"$set": {"fecha": hoy, "count": count + 1, "last_at": datetime.now(_tzu.utc)}},
                        upsert=True,
                    )
                    logger.info("[report_scheduler] recordatorio_jornada #%d user=%s enviado=%s",
                                count + 1, user_id, res["envio"].get("sent"))
        except Exception:
            logger.exception("[report_scheduler] jornada_notificaciones falló user=%s", user_id)


def register_report_jobs(scheduler) -> None:
    scheduler.add_job(
        reporte_diario_job, CronTrigger(hour=18, minute=0, day_of_week="mon-sat", timezone="UTC"),
        id="cobr_reporte_diario", replace_existing=True,
    )
    scheduler.add_job(
        reporte_semanal_job, CronTrigger(day_of_week="mon", hour=18, minute=5, timezone="UTC"),
        id="cobr_reporte_semanal", replace_existing=True,
    )
    # next_run_time: primer disparo ~45s tras el boot. El jobstore es EN MEMORIA
    # y cada redeploy reinicia el timer — con deploys frecuentes un intervalo de
    # 15 min podía NO dispararse nunca (observado: el fin-de-jornada del 15-jul
    # se saltó dos veces por redeploys consecutivos). Los jobs son idempotentes
    # (flags por fecha en cobranza_runtime), así que correr al boot es seguro.
    from datetime import datetime as _dt, timedelta as _td
    scheduler.add_job(
        fin_jornada_check_job, "interval", minutes=15,
        next_run_time=_dt.now() + _td(seconds=45),
        id="cobr_fin_jornada_check", replace_existing=True,
    )
    scheduler.add_job(
        jornada_notificaciones_job, "interval", minutes=5,
        next_run_time=_dt.now() + _td(seconds=60),
        id="cobr_jornada_notifs", replace_existing=True,
    )
    logger.info("[report_scheduler] registrados: cobr_reporte_diario (18:00 UTC L-Sáb), "
                "cobr_reporte_semanal (lun 18:05 UTC), cobr_fin_jornada_check (15m), "
                "cobr_jornada_notifs (5m)")
