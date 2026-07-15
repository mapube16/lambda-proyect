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


def register_report_jobs(scheduler) -> None:
    scheduler.add_job(
        reporte_diario_job, CronTrigger(hour=18, minute=0, day_of_week="mon-sat", timezone="UTC"),
        id="cobr_reporte_diario", replace_existing=True,
    )
    scheduler.add_job(
        reporte_semanal_job, CronTrigger(day_of_week="mon", hour=18, minute=5, timezone="UTC"),
        id="cobr_reporte_semanal", replace_existing=True,
    )
    scheduler.add_job(
        fin_jornada_check_job, "interval", minutes=15,
        id="cobr_fin_jornada_check", replace_existing=True,
    )
    logger.info("[report_scheduler] registrados: cobr_reporte_diario (18:00 UTC L-Sáb), "
                "cobr_reporte_semanal (lun 18:05 UTC), cobr_fin_jornada_check (15m)")
