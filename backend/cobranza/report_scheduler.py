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


def register_report_jobs(scheduler) -> None:
    scheduler.add_job(
        reporte_diario_job, CronTrigger(hour=18, minute=0, day_of_week="mon-sat", timezone="UTC"),
        id="cobr_reporte_diario", replace_existing=True,
    )
    scheduler.add_job(
        reporte_semanal_job, CronTrigger(day_of_week="mon", hour=18, minute=5, timezone="UTC"),
        id="cobr_reporte_semanal", replace_existing=True,
    )
    logger.info("[report_scheduler] registrados: cobr_reporte_diario (18:00 UTC L-Sáb), "
                "cobr_reporte_semanal (lun 18:05 UTC)")
