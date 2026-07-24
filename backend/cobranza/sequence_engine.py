"""
sequence_engine.py — la máquina de intentos del informe ARIA (§3–§4).

Reemplaza los jobs genéricos pre/post_vencimiento por la secuencia real:
    L1 = ancla − 1 hábil · L2 = día del ancla · L3 = ancla + 2 hábiles
(offsets por tenant en timings.offsets_intentos_dias_habiles; el ancla es la
fecha de COMPROMISO — o el vencimiento, según timings.agendar_por). La "regla
del viernes" sale de la aritmética de días hábiles (call_scheduler).

Dos jobs por tick, SIEMPRE por tenant (multi-tenant, config de tenant_config):

  plan_intentos_job     — asigna proximo_intento_at/proximo_intento_numero a
                          cada deudor elegible que no tenga cita; agota a los
                          que llegaron a max_intentos. Un deudor 'reagendado'
                          usa la fecha_reagendada pedida por el cliente
                          (reemplaza el siguiente intento — informe §3).
  dispatch_intentos_job — marca a los que están en hora, dentro de las franjas
                          del tenant (horarios) Y de la Ley 2300, con cupo
                          diario (volumen.llamadas_por_dia, contado en
                          cobranza_daily_stats) y la prioridad del informe:
                          vencen hoy → vencen el próximo hábil → mayor mora.
                          La jornada de arranque es esta misma prioridad con el
                          cupo diario alto (~250) durante los 2 primeros días.

El estado post-llamada lo sigue poniendo voice_router._process_call_ended
(contactado/sin_contacto/agotado + intentos+=1); al terminar borra la cita para
que el planner recalcule el siguiente intento con el offset correcto.
"""
import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import pytz

from database import get_db
from cobranza.call_scheduler import (
    COLOMBIA_TZ,
    add_business_days,
    has_been_contacted_today,
    is_business_day,
    is_contact_allowed_now,
)

logger = logging.getLogger("cobranza.sequence_engine")

# Estados que la máquina puede volver a llamar. contactado/promesa/reagendado
# post-gestión, pagado, pausado, escalado, disputa y agotado NO se re-marcan
# solos (reagendado sí: es una cita pedida por el cliente).
CALLABLE_ESTADOS = ("pendiente", "sin_contacto", "reagendado")

# Fallback si el tenant no configuró franjas: las del informe (9-12 / 14-16),
# subconjunto seguro de la Ley 2300. El tenant las cambia desde la UI.
DEFAULT_FRANJAS = [["09:00", "12:00"], ["14:00", "16:00"]]
DEFAULT_OFFSETS = [-1, 0, 2]   # L1/L2/L3 del informe, en días hábiles vs el ancla
DEFAULT_MAX_INTENTOS = 3


# ── Helpers puros (testeables sin DB) ──────────────────────────────────────────

def _to_date(v) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_festivos(horarios: dict) -> set:
    out = set()
    for s in (horarios or {}).get("festivos") or []:
        d = _to_date(s)
        if d:
            out.add(d)
    return out


def _tz(horarios: dict):
    try:
        return pytz.timezone((horarios or {}).get("timezone") or "America/Bogota")
    except Exception:
        return COLOMBIA_TZ


def _franja_inicio(horarios: dict) -> time:
    """Hora local a la que se citan los intentos: inicio de la primera franja."""
    franjas = (horarios or {}).get("franjas") or DEFAULT_FRANJAS
    try:
        h, m = str(franjas[0][0]).split(":")
        return time(int(h), int(m))
    except Exception:
        return time(9, 0)


def _at_franja_inicio(d: date, horarios: dict) -> datetime:
    """date → datetime UTC al inicio de la primera franja del tenant."""
    local = _tz(horarios).localize(datetime.combine(d, _franja_inicio(horarios)))
    return local.astimezone(pytz.utc)


# ── Escalonado de la jornada (tandas a lo largo del día) ───────────────────────
# El planner NO apila todas las citas al inicio de la franja (antes: todos a las
# 9:00 → el dispatcher los drenaba de corrido en la mañana y "quemaba" el día
# temprano). En su lugar reparte los intentos de HOY en TANDAS: N llamadas cada
# M minutos desde una hora de arranque, fluyendo por las franjas del tenant y
# saltando los huecos (almuerzo). Así se cubre toda la jornada.
# Parámetros por tenant en cobranza.volumen (editable sin deploy):
#   hora_inicio_jornada  (default "11:00")  — desde cuándo arranca el escalonado
#   llamadas_por_tanda   (default 5)         — cuántas comparten cada slot
#   intervalo_tandas_min (default 5)         — minutos entre tandas
DEFAULT_HORA_INICIO_JORNADA = "11:00"
DEFAULT_LLAMADAS_POR_TANDA = 5
DEFAULT_INTERVALO_TANDAS_MIN = 5


def _hhmm_to_min(s: str, fallback: int) -> int:
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return fallback


def _franjas_del_dia(d: date, horarios: dict) -> list:
    """
    Franjas operativas del tenant para el día `d`, como pares (inicio_min,
    fin_min) locales, ordenadas. Respeta sábado (franjas_sabado), días hábiles
    del tenant y festivos (nacionales + del tenant). [] si el día no es operativo.
    """
    horarios = horarios or {}
    if d in _parse_festivos(horarios):
        return []
    iso_wd = d.weekday() + 1  # 1=lunes … 7=domingo
    dias = horarios.get("dias_habiles") or [1, 2, 3, 4, 5]
    if iso_wd == 6:
        franjas = horarios.get("franjas_sabado") or []
    elif iso_wd in dias:
        franjas = horarios.get("franjas") or DEFAULT_FRANJAS
    else:
        return []
    if not is_business_day(d) and iso_wd != 6:
        return []  # festivo nacional en día hábil
    out = []
    for fr in franjas:
        try:
            a = _hhmm_to_min(fr[0], -1)
            b = _hhmm_to_min(fr[1], -1)
            if 0 <= a < b:
                out.append((a, b))
        except Exception:
            continue
    return sorted(out)


def _stagger_slot(d: date, idx: int, horarios: dict, volumen: dict) -> datetime:
    """
    Slot escalonado (datetime UTC) para el intento de índice `idx` (0-based, en
    orden de prioridad) dentro del día `d`. La tanda `idx // tanda` se cita
    `intervalo` minutos después de la anterior, arrancando en hora_inicio_jornada
    y fluyendo por las franjas del día (salta el hueco de almuerzo). Si el volumen
    se pasa del cierre, se satura al final de la última franja (esos sobrantes los
    retoma el rescate / el día siguiente). Fallback a inicio de franja si el día
    no tiene franjas operativas (no debería ocurrir: el dispatcher ya filtra).
    """
    volumen = volumen or {}
    tanda = max(1, int(volumen.get("llamadas_por_tanda") or DEFAULT_LLAMADAS_POR_TANDA))
    intervalo = max(1, int(volumen.get("intervalo_tandas_min") or DEFAULT_INTERVALO_TANDAS_MIN))
    hora_inicio = _hhmm_to_min(
        volumen.get("hora_inicio_jornada") or DEFAULT_HORA_INICIO_JORNADA, 11 * 60
    )

    franjas = _franjas_del_dia(d, horarios)
    if not franjas:
        return _at_franja_inicio(d, horarios)

    # Ventanas recortadas para no arrancar antes de hora_inicio_jornada.
    ventanas = [(max(a, hora_inicio), b) for a, b in franjas if max(a, hora_inicio) < b]
    if not ventanas:
        ventanas = franjas  # hora_inicio cae tras el cierre → usar franjas tal cual

    offset = (idx // tanda) * intervalo  # minutos dentro de la jornada operativa
    minuto = None
    rem = offset
    for a, b in ventanas:
        dur = b - a
        if rem < dur:
            minuto = a + rem
            break
        rem -= dur
    if minuto is None:
        minuto = ventanas[-1][1] - 1  # excede la capacidad del día → final del cierre

    local = _tz(horarios).localize(datetime.combine(d, time(minuto // 60, minuto % 60)))
    return local.astimezone(pytz.utc)


def is_within_tenant_franjas(horarios: dict, now_utc: Optional[datetime] = None) -> bool:
    """
    ¿Estamos dentro del horario operativo del TENANT? (La Ley 2300 es el techo
    legal y se valida aparte; esto es la franja comercial configurada en la UI.)
    """
    horarios = horarios or {}
    now_local = (now_utc or datetime.now(timezone.utc)).astimezone(_tz(horarios))
    hoy = now_local.date()

    if hoy in _parse_festivos(horarios):
        return False
    iso_wd = now_local.weekday() + 1  # 1=lunes … 7=domingo
    dias = horarios.get("dias_habiles") or [1, 2, 3, 4, 5]
    if iso_wd == 6:
        franjas = horarios.get("franjas_sabado") or []
        if not franjas:
            return False
    elif iso_wd in dias:
        franjas = horarios.get("franjas") or DEFAULT_FRANJAS
    else:
        return False
    if not is_business_day(hoy) and iso_wd != 6:
        return False  # festivo nacional

    hhmm = now_local.hour * 60 + now_local.minute
    for fr in franjas:
        try:
            a_h, a_m = str(fr[0]).split(":")
            b_h, b_m = str(fr[1]).split(":")
            if int(a_h) * 60 + int(a_m) <= hhmm < int(b_h) * 60 + int(b_m):
                return True
        except Exception:
            continue
    return False


def compute_proximo_intento(
    debtor: dict, timings: dict, horarios: dict,
    today: Optional[date] = None,
) -> tuple:
    """
    Núcleo puro del planner. Devuelve:
      ("agotado", None)        — llegó a max_intentos
      ("skip", None)           — sin fecha ancla utilizable
      ("cita", datetime_utc)   — cuándo toca el próximo intento
    """
    timings = timings or {}
    today = today or datetime.now(COLOMBIA_TZ).date()
    extra_fest = _parse_festivos(horarios)

    intentos = int(debtor.get("intentos") or 0)
    max_intentos = int(timings.get("max_intentos") or DEFAULT_MAX_INTENTOS)

    # Cita pedida por el cliente: reemplaza el siguiente intento (informe §3),
    # NO cuenta contra max_intentos hasta que la llamada ocurra.
    if debtor.get("estado") == "reagendado" and debtor.get("fecha_reagendada"):
        raw = debtor["fecha_reagendada"]
        if isinstance(raw, datetime):
            at = raw if raw.tzinfo else pytz.utc.localize(raw)
        else:
            d = _to_date(raw)
            if d is None:
                return ("skip", None)
            # si el cliente dio solo fecha, se cita al inicio de franja
            at = _at_franja_inicio(d, horarios)
        return ("cita", at)

    if intentos >= max_intentos:
        return ("agotado", None)

    # Ancla: compromiso (referente de gestión del informe) o vencimiento.
    anclar_por = timings.get("agendar_por", "fecha_compromiso")
    ancla = None
    if anclar_por == "fecha_compromiso":
        ancla = _to_date(debtor.get("fecha_compromiso"))
    ancla = ancla or _to_date(debtor.get("vencimiento")) or _to_date(debtor.get("fecha_pago"))
    if ancla is None:
        return ("skip", None)

    offsets = timings.get("offsets_intentos_dias_habiles") or DEFAULT_OFFSETS
    idx = min(intentos, len(offsets) - 1)
    target = add_business_days(ancla, int(offsets[idx]), extra_fest)

    # Backlog (arranque): si la fecha ya pasó, toca HOY (o el próximo hábil).
    if target < today:
        target = today if is_business_day(today, extra_fest) \
            else add_business_days(today, 1, extra_fest)

    return ("cita", _at_franja_inicio(target, horarios))


def prioridad_informe(debtor: dict, today: date, extra_fest: set) -> tuple:
    """
    Orden de marcación: MAYOR MORA PRIMERO (prioridad explícita de DPG — los
    días con más mora, mayor riesgo de cancelación, se llaman primero). La mora
    se calcula fresca desde vencimiento; el campo dias_mora persistido puede
    estar stale. El grupo (vence_hoy=0 · preventiva=1 · backlog=2) queda como
    desempate y como etiqueta para el UI.
    """
    venc = _to_date(debtor.get("vencimiento")) or _to_date(debtor.get("fecha_pago"))
    manana_habil = add_business_days(today, 1, extra_fest)
    if venc == today:
        grupo = 0
    elif venc == manana_habil:
        grupo = 1
    else:
        grupo = 2
    if venc is not None:
        mora = (today - venc).days
    else:
        mora = int(debtor.get("dias_mora") or debtor.get("edad_cartera") or 0)
    return (-int(mora), grupo)


# ── Config por tenant ──────────────────────────────────────────────────────────

async def _cobranza_cfg(user_id: str) -> dict:
    from cobranza.config_cache import get_tenant_config
    cfg = await get_tenant_config(user_id)
    return (cfg or {}).get("cobranza") or {}


async def _tenant_ids(db) -> list:
    cur = db.company_voice.find({"cobranza_enabled": True}, {"user_id": 1})
    return [d["user_id"] async for d in cur]


# ── Job 1: planner ─────────────────────────────────────────────────────────────

async def _aplicar_cita(db, debtor: dict, at: datetime) -> None:
    """Persiste proximo_intento_at + numero de intento en el deudor."""
    await db.debtors.update_one(
        {"_id": debtor["_id"]},
        {"$set": {
            "proximo_intento_at": at,
            "proximo_intento_numero": int(debtor.get("intentos") or 0) + 1,
            "updated_at": datetime.now(timezone.utc),
        }},
    )


async def _citas_hoy_count(db, user_id: str, tz, today_local: date) -> int:
    """Cuántos deudores del tenant ya tienen cita para HOY (para no re-escalonar
    encima de las tandas ya asignadas en ticks anteriores)."""
    day_start = tz.localize(datetime.combine(today_local, time(0, 0))).astimezone(pytz.utc)
    day_end = day_start + timedelta(days=1)
    return await db.debtors.count_documents({
        "user_id": user_id,
        "estado": {"$in": list(CALLABLE_ESTADOS)},
        "proximo_intento_at": {"$gte": day_start, "$lt": day_end},
    })


async def plan_intentos_job() -> None:
    """
    Asigna proximo_intento_at a los deudores elegibles sin cita (por tenant).

    Las citas que caen HOY se ESCALONAN en tandas a lo largo de la jornada
    (ver _stagger_slot): en orden de prioridad del informe, N por tanda cada M
    minutos desde hora_inicio_jornada, para cubrir todos los horarios del día en
    vez de apilarse al inicio de la franja. Las citas de días futuros y las
    reagendadas por el cliente conservan su hora exacta (inicio de franja / la
    pedida por el cliente).
    """
    db = get_db()
    for user_id in await _tenant_ids(db):
        try:
            cfg = await _cobranza_cfg(user_id)
            timings = cfg.get("timings") or {}
            horarios = cfg.get("horarios") or {}
            volumen = cfg.get("volumen") or {}
            tz = _tz(horarios)
            today_local = datetime.now(tz).date()
            extra_fest = _parse_festivos(horarios)

            cursor = db.debtors.find({
                "user_id": user_id,
                "is_active": {"$ne": False},
                "no_llamar": {"$ne": True},   # entidades estatales / opt-out (informe SS2)
                "excluir_llamada": {"$ne": True},  # débito automático / póliza inactiva
                # Sin tipo_entidad resuelto (regex+LLM) no sabemos si es estatal — no
                # se planifica hasta que la clasificación termine (ver entidad_estatal.py).
                "tipo_entidad": {"$ne": None},
                "estado": {"$in": list(CALLABLE_ESTADOS)},
                "proximo_intento_at": None,
            })

            agotados = 0
            exactas = []   # (debtor, at) — futuras o reagendadas: hora tal cual
            hoy = []       # debtors cuya cita cae hoy → escalonar en tandas
            async for debtor in cursor:
                verdict, at = compute_proximo_intento(debtor, timings, horarios, today=today_local)
                if verdict == "agotado":
                    await db.debtors.update_one(
                        {"_id": debtor["_id"]},
                        {"$set": {"estado": "agotado", "updated_at": datetime.now(timezone.utc)}},
                    )
                    agotados += 1
                    try:
                        from cobranza.alerts import crear_alerta
                        await crear_alerta(db, user_id, debtor, "sin_contacto_agotado")
                    except Exception:
                        logger.exception("[plan] alerta sin_contacto_agotado falló (no fatal)")
                    continue
                if verdict != "cita":
                    continue
                # Cita pedida por el cliente (reagendado): hora exacta, no se escalona.
                es_reagendado = debtor.get("estado") == "reagendado" and debtor.get("fecha_reagendada")
                if not es_reagendado and at.astimezone(tz).date() <= today_local:
                    hoy.append(debtor)
                else:
                    exactas.append((debtor, at))

            for debtor, at in exactas:
                await _aplicar_cita(db, debtor, at)

            if hoy:
                hoy.sort(key=lambda d: prioridad_informe(d, today_local, extra_fest))
                base_idx = await _citas_hoy_count(db, user_id, tz, today_local)
                for i, debtor in enumerate(hoy):
                    at = _stagger_slot(today_local, base_idx + i, horarios, volumen)
                    await _aplicar_cita(db, debtor, at)

            planned = len(exactas) + len(hoy)
            if planned or agotados:
                logger.info("[plan] tenant=%s citas=%d (escalonadas_hoy=%d) agotados=%d",
                            user_id, planned, len(hoy), agotados)
        except Exception:
            logger.exception("[plan] tenant=%s failed", user_id)


# ── Job 2: dispatcher ──────────────────────────────────────────────────────────

async def dispatch_intentos_job() -> None:
    """Marca a los deudores en hora, respetando franjas, cupo diario y prioridad."""
    from cobranza.campaign_scheduler import (
        is_autocall_enabled, safe_initiate_call, is_jornada_authorized,
    )

    if not await is_autocall_enabled():
        return
    if not is_contact_allowed_now():   # techo legal (Ley 2300 + festivos)
        return

    db = get_db()
    now = datetime.now(timezone.utc)

    for user_id in await _tenant_ids(db):
        try:
            cfg = await _cobranza_cfg(user_id)
            horarios, volumen = cfg.get("horarios") or {}, cfg.get("volumen") or {}

            today_local = now.astimezone(_tz(horarios)).date()
            fecha = today_local.isoformat()

            # Gate DURO por fecha (independiente del kill-switch manual): antes
            # de fecha_activacion, este tenant no marca a NADIE. Defensa en
            # profundidad para "no llamar antes del día acordado con el cliente".
            fecha_act = volumen.get("fecha_activacion")
            if fecha_act and fecha < fecha_act:
                continue

            if not is_within_tenant_franjas(horarios, now):
                continue

            # Gate de jornada AQUÍ (no solo en safe_initiate_call): si no está
            # autorizada, se salta el tenant ANTES de tocar el cupo. Bug 16-jul:
            # safe_initiate_call abortaba per-deudor pero el $inc de
            # llamadas_iniciadas ya había corrido -> 300 abortos quemaron el
            # cupo del día y no marcó ni cuando autorizaron.
            if not await is_jornada_authorized(user_id):
                continue

            # Cupo diario del tenant (jornada de arranque = mismo cupo, alto).
            stats = await db.cobranza_daily_stats.find_one({"user_id": user_id, "fecha": fecha})
            hechas = int((stats or {}).get("llamadas_iniciadas") or 0)
            cupo = int(volumen.get("llamadas_por_dia") or 30) - hechas
            if cupo <= 0:
                continue

            # Concurrencia global (mismo criterio que initiate-v2; F2 lo refina).
            import os
            cutoff = now - timedelta(minutes=10)
            active = await db.cobranza_calls_in_progress.count_documents(
                {"started_at": {"$gte": cutoff}}
            )
            slots = min(cupo, int(os.getenv("MAX_CONCURRENT_CALLS", "5")) - active)
            if slots <= 0:
                continue

            due = await db.debtors.find({
                "user_id": user_id,
                "is_active": {"$ne": False},
                "no_llamar": {"$ne": True},   # entidades estatales / opt-out (informe SS2)
                "excluir_llamada": {"$ne": True},  # débito automático / póliza inactiva
                # Mismo criterio que el planner: sin clasificar todavía, no se marca.
                "tipo_entidad": {"$ne": None},
                "estado": {"$in": list(CALLABLE_ESTADOS)},
                "proximo_intento_at": {"$lte": now},
            }).to_list(length=500)
            due = [d for d in due if not has_been_contacted_today(d)]
            if not due:
                continue

            extra_fest = _parse_festivos(horarios)
            due.sort(key=lambda d: prioridad_informe(d, today_local, extra_fest))

            for debtor in due[:slots]:
                await db.debtors.update_one(
                    {"_id": debtor["_id"]},
                    {"$set": {"estado": "llamando", "updated_at": datetime.now(timezone.utc)}},
                )
                await db.cobranza_daily_stats.update_one(
                    {"user_id": user_id, "fecha": fecha},
                    {"$inc": {"llamadas_iniciadas": 1}},
                    upsert=True,
                )
                asyncio.create_task(safe_initiate_call(debtor, user_id))
            logger.info("[dispatch] tenant=%s marcados=%d (cupo restante=%d, en hora=%d)",
                        user_id, min(slots, len(due)), cupo, len(due))
        except Exception:
            logger.exception("[dispatch] tenant=%s failed", user_id)
