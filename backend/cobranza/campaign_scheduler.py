"""
campaign_scheduler.py — infraestructura de la campaña de llamadas (APScheduler).

Este módulo es dueño del kill-switch runtime, de safe_initiate_call (la única
puerta de salida hacia Twilio: kill-switch + saldo de minutos + mapping) y del
rescue de llamadas colgadas. La LÓGICA de la secuencia (qué deudor toca cuándo)
vive en cobranza/sequence_engine.py — la máquina de intentos del informe ARIA:

  - seq_plan_intentos:     cada 15 min — asigna proximo_intento_at por deudor
                           (ancla compromiso/vencimiento ± offsets en días hábiles).
  - seq_dispatch_intentos: cada 5 min — marca a los que están en hora, dentro de
                           franjas del tenant + Ley 2300, con cupo diario y la
                           prioridad del informe.
  - cobr_rescue_llamando:  cada 10 min — rescata deudores atascados en 'llamando'.

Usage:
    from cobranza.campaign_scheduler import register_cobranza_jobs
    register_cobranza_jobs(scheduler)   # called in main.py lifespan
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from database import get_db
from cobranza.call_scheduler import is_contact_allowed_now, has_been_contacted_today

logger = logging.getLogger("cobranza.campaign_scheduler")

# IDs of the 3 campaign jobs — used by the runtime kill-switch to pause/resume.
_COBRANZA_JOB_IDS = ("seq_plan_intentos", "seq_dispatch_intentos", "cobr_rescue_llamando")


# ---------------------------------------------------------------------------
# Runtime kill-switch (master ON/OFF, hot — no redeploy)
# ---------------------------------------------------------------------------
#
# The boot-time COBRANZA_AUTOCALL_ENABLED env var only decides whether jobs get
# *registered* at startup. It cannot stop a running worker. This runtime switch
# lives in Mongo (db.cobranza_runtime, _id="killswitch") so it:
#   - survives restarts (the source of truth at boot, env var is only the default)
#   - takes effect on the NEXT job tick without a redeploy
#   - is checked at the top of every job AND inside safe_initiate_call, so calls
#     already in flight when the switch flips OFF are aborted before dialing.
#
# enabled=True  → autocall ON  (jobs dial debtors)
# enabled=False → autocall OFF (jobs run but dial no one; system stays healthy)

_RUNTIME_DOC_ID = "killswitch"


async def is_autocall_enabled() -> bool:
    """
    Return whether automated dialing is currently enabled.
    Source of truth = db.cobranza_runtime/killswitch. If no doc exists yet,
    fall back to the COBRANZA_AUTOCALL_ENABLED env var default.
    """
    db = get_db()
    doc = await db.cobranza_runtime.find_one({"_id": _RUNTIME_DOC_ID})
    if doc is not None and "enabled" in doc:
        return bool(doc["enabled"])
    return os.getenv("COBRANZA_AUTOCALL_ENABLED", "false").lower() in ("1", "true", "yes")


async def set_autocall_enabled(enabled: bool, scheduler=None, actor: str = "system") -> bool:
    """
    Master ON/OFF switch — flips the runtime flag in Mongo AND pauses/resumes the
    live APScheduler jobs so the change is effective immediately (no redeploy).

    Args:
        enabled:   True = resume dialing, False = stop all automated calls.
        scheduler: live AsyncIOScheduler. If omitted, only the Mongo flag changes
                   (jobs still honour it on their next tick via is_autocall_enabled).
        actor:     who flipped it (for the audit trail).

    Returns the new enabled state.
    """
    db = get_db()
    await db.cobranza_runtime.update_one(
        {"_id": _RUNTIME_DOC_ID},
        {"$set": {
            "enabled": enabled,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": actor,
        }},
        upsert=True,
    )

    if scheduler is None:
        from landa.scheduler import scheduler as scheduler  # lazy import, avoid cycle

    if enabled:
        # Resume existing jobs; (re)register if missing (e.g. booted with autocall off).
        register_cobranza_jobs(scheduler, force=True)
        for job_id in _COBRANZA_JOB_IDS:
            try:
                scheduler.resume_job(job_id)
            except Exception:
                pass
        logger.warning("[killswitch] AUTOCALL ENABLED by %s — campaign jobs resumed.", actor)
    else:
        for job_id in _COBRANZA_JOB_IDS:
            try:
                scheduler.pause_job(job_id)
            except Exception:
                pass
        logger.warning("[killswitch] AUTOCALL DISABLED by %s — campaign jobs paused, no debtor will be called.", actor)

    return enabled


# ---------------------------------------------------------------------------
# Gate de autorización de jornada (informe §2.1)
# ---------------------------------------------------------------------------
# El bot NO marca hasta que un colaborador de DPG revisa la lista del día y la
# AUTORIZA explícitamente desde el dashboard. La autorización es por-tenant y
# por-día: vale solo para HOY (Bogotá); al día siguiente hay que re-autorizar,
# así nunca marca en automático sin la revisión humana previa.
_JORNADA_DOC_PREFIX = "jornada_authorized"


def _today_bogota() -> str:
    import pytz
    return datetime.now(pytz.timezone("America/Bogota")).date().isoformat()


async def is_jornada_authorized(user_id: str) -> bool:
    db = get_db()
    doc = await db.cobranza_runtime.find_one({"_id": f"{_JORNADA_DOC_PREFIX}:{user_id}"})
    if not doc:
        return False
    hoy = _today_bogota()
    # authorized_dates (lista) permite pre-autorizar mañana sin pisar hoy;
    # authorized_date (campo viejo) se mantiene por compatibilidad.
    return hoy in (doc.get("authorized_dates") or []) or doc.get("authorized_date") == hoy


def _manana_habil_bogota() -> str:
    """Próximo día hábil (la 'jornada de mañana' que se puede pre-autorizar)."""
    import pytz
    from cobranza.call_scheduler import add_business_days
    hoy = datetime.now(pytz.timezone("America/Bogota")).date()
    return add_business_days(hoy, 1).isoformat()


async def set_jornada_authorized(user_id: str, authorized: bool, actor: str = "", dia: str = "hoy") -> dict:
    """dia='hoy' autoriza la jornada de HOY; dia='manana' PRE-autoriza el próximo
    día hábil (petición DPG: autorizar desde la tarde anterior → al llegar el
    día, el gate se cumple solo y arranca automático). authorized_dates es una
    LISTA: pre-autorizar mañana a media jornada NO apaga la de hoy. Desautorizar
    limpia todo (hoy y mañana)."""
    db = get_db()
    _id = f"{_JORNADA_DOC_PREFIX}:{user_id}"
    now = datetime.now(timezone.utc)
    if authorized:
        fecha = _manana_habil_bogota() if dia == "manana" else _today_bogota()
        await db.cobranza_runtime.update_one(
            {"_id": _id},
            {"$addToSet": {"authorized_dates": fecha},
             "$set": {"by": actor, "at": now}},
            upsert=True,
        )
    else:
        # Desautorizar = pausar SOLO el día indicado (por defecto HOY), NO borrar
        # las pre-autorizaciones futuras. Bug 16-jul: desautorizar borraba TODA
        # la lista → al pausar la tarde de ayer se perdió la pre-auto de hoy y no
        # arrancó a las 9am.
        fecha = _manana_habil_bogota() if dia == "manana" else _today_bogota()
        await db.cobranza_runtime.update_one(
            {"_id": _id},
            {"$pull": {"authorized_dates": fecha},
             "$set": {"authorized_date": None, "by": actor, "at": now}},
            upsert=True,
        )
    logger.warning("[jornada] autorizacion=%s dia=%s user=%s por=%s", authorized, dia, user_id, actor)
    return {"authorized": bool(authorized), "authorized_date": fecha, "by": actor}


async def jornada_estado(user_id: str) -> dict:
    db = get_db()
    doc = await db.cobranza_runtime.find_one({"_id": f"{_JORNADA_DOC_PREFIX}:{user_id}"}) or {}
    hoy = _today_bogota()
    manana = _manana_habil_bogota()
    fechas = set(doc.get("authorized_dates") or [])
    if doc.get("authorized_date"):
        fechas.add(doc["authorized_date"])  # compat con el campo viejo
    return {
        "hoy": hoy,
        "manana": manana,
        "authorized": hoy in fechas,
        "authorized_manana": manana in fechas,
        "authorized_date": doc.get("authorized_date"),
        "by": doc.get("by"),
        "at": doc.get("at").isoformat() if doc.get("at") else None,
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def safe_initiate_call(debtor: dict, user_id: str) -> None:
    """
    Fire-and-forget: create outbound Twilio call → Pipecat pipeline.
    On success: stores call_sid on the debtor document and inserts call mapping.
    On failure: resets estado to 'pendiente' so the next job run can retry.
    """
    db = get_db()
    try:
        # Runtime kill-switch: a task may have been queued before the switch
        # flipped OFF. Re-check right before dialing so in-flight calls abort.
        if not await is_autocall_enabled():
            logger.warning(
                "[scheduler] Autocall OFF — aborting queued call for debtor %s; resetting to pendiente",
                debtor["_id"],
            )
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"estado": "pendiente", "updated_at": datetime.now(timezone.utc)}},
            )
            return

        # Gate por fecha_activacion — mismo re-check "justo antes de marcar"
        # que el kill-switch de arriba (defensa en profundidad: una tarea
        # pudo haber quedado encolada de un tick anterior al gate).
        from cobranza.config_cache import get_tenant_config
        _cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
        _fecha_act = (_cfg.get("volumen") or {}).get("fecha_activacion")
        if _fecha_act:
            import pytz as _pytz_ac
            _hoy = datetime.now(_pytz_ac.timezone("America/Bogota")).date().isoformat()
            if _hoy < _fecha_act:
                logger.warning(
                    "[scheduler] fecha_activacion=%s aún no llega (hoy=%s) — abortando llamada a debtor %s",
                    _fecha_act, _hoy, debtor["_id"],
                )
                await db.debtors.update_one(
                    {"_id": debtor["_id"]},
                    {"$set": {"estado": "pendiente", "updated_at": datetime.now(timezone.utc)}},
                )
                return

        # Gate de autorización de jornada (informe §2.1): el bot NO marca hasta
        # que DPG revisó la lista del día y la autorizó desde el dashboard.
        if not await is_jornada_authorized(user_id):
            logger.info(
                "[scheduler] jornada de hoy NO autorizada (user=%s) — no se marca a debtor %s",
                user_id, debtor["_id"],
            )
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"estado": "pendiente", "updated_at": datetime.now(timezone.utc)}},
            )
            return

        # Paquete de minutos: sin saldo el tenant no marca (el job sigue vivo
        # para otros tenants; el deudor vuelve a pendiente).
        from cobranza.minutes import MinutesExhaustedError, require_saldo
        try:
            await require_saldo(db, user_id)
        except MinutesExhaustedError as e:
            logger.warning("[scheduler] %s — debtor %s vuelve a pendiente", e, debtor["_id"])
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"estado": "pendiente", "updated_at": datetime.now(timezone.utc)}},
            )
            return

        from twilio.rest import Client
        from cobranza.minutes import call_status_kwargs

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

        if not all([account_sid, auth_token, from_number]):
            raise RuntimeError("Twilio not configured")

        client = Client(account_sid, auth_token)
        to_number = debtor.get("telefono")
        # Pre-validación de teléfono. Un número inválido (vacío, '+57', malformado)
        # hace fallar el create de Twilio; el deudor volvía a 'pendiente' y —con
        # mora alta— se re-seleccionaba cada minuto, atascando la cola e inflando
        # el contador (observado 21-jul: ~34 números basura loopeando y
        # bloqueando a los buenos). Se excluye ANTES de llamar a Twilio.
        import re as _re
        if not _re.match(r"^\+57\d{10}$", str(to_number or "")):
            logger.warning("[scheduler] telefono invalido %r debtor %s — excluido de la cola", to_number, debtor["_id"])
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"excluir_llamada": True, "excluir_motivo": "telefono_invalido",
                          "estado": "sin_contacto", "updated_at": datetime.now(timezone.utc)}},
            )
            await db.cobranza_daily_stats.update_one(
                {"user_id": user_id, "fecha": _today_bogota()},
                {"$inc": {"llamadas_iniciadas": -1}},   # deshacer el $inc del despachador
            )
            return
        # El SDK de Twilio es sync (HTTP bloqueante): en el event loop congela
        # TODAS las llamadas activas ~0.5-1s por marcación. Igual que initiate-v2.
        loop = asyncio.get_event_loop()
        # Tope de TIMBRADO (petición DPG 24-jul: evitar buzón A TODA COSTA,
        # aunque se corte a humanos lentos — un no-answer cuesta $0 y se
        # reintenta; un buzón factura 1 min sí o sí). Data real (8 días, 1500
        # llamadas): humano contesta mediana 14s, buzón 15s — se solapan, así
        # que un timbrado corto corta ~mitad de buzones al precio de reintentar
        # a los humanos tardíos. Prioridad: tenant_config
        # (cobranza.volumen.ring_timeout_secs, editable en Mongo SIN deploy) >
        # env > default.
        ring_timeout = int(os.getenv("COBRANZA_RING_TIMEOUT_SECS", "18"))
        try:
            from cobranza.config_cache import get_tenant_config
            _vol = (((await get_tenant_config(user_id)) or {}).get("cobranza") or {}).get("volumen") or {}
            ring_timeout = int(_vol.get("ring_timeout_secs") or ring_timeout)
        except Exception:
            pass  # config inaccesible → env/default; nunca frenar la marcación
        # AMD SÍNCRONO (DPG 21-jul: reducir costo Twilio/Gemini — cero palabras al
        # buzón). Twilio clasifica humano/máquina ANTES de entregar el TwiML, así
        # que el webhook cuelga (AnsweredBy=machine) SIN conectar el stream — ARIA
        # nunca le habla a un contestador (menos minutos de Media Stream + Gemini).
        # Costo: ~2-4s de silencio para el humano mientras Twilio clasifica.
        # (Antes era async: conectaba de una y colgaba en paralelo, pero ARIA
        # alcanzaba a decir el saludo al buzón.) Toggle por COBRANZA_AMD_ENABLED.
        amd_kwargs = {}
        if os.getenv("COBRANZA_AMD_ENABLED", "true").lower() == "true":
            amd_kwargs = {
                "machine_detection": "Enable",
                "machine_detection_timeout": int(os.getenv("COBRANZA_AMD_TIMEOUT_SECS", "12")),
            }
        call = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: client.calls.create(
                to=to_number, from_=from_number,
                url=f"{webhook_url}/api/cobranza/voice/webhook", method="POST",
                timeout=ring_timeout,
                # Grabar SOLO las contestadas (petición DPG, QA/compliance):
                # Twilio graba desde que contestan → las no contestadas no
                # generan grabación ni costo. El callback guarda la URL en el
                # historial del deudor (mismo endpoint que el path manual).
                record=True,
                recording_status_callback=f"{webhook_url}/api/cobranza/voice/recording-callback",
                recording_status_callback_method="POST",
                **amd_kwargs,
                **call_status_kwargs(),
            )),
            timeout=15,  # latencia del API de Twilio; el ring_timeout es async del lado de Twilio
        )
        call_sid = call.sid
        logger.info("[scheduler] Twilio call %s -> %s (debtor %s)", call_sid, to_number, debtor["_id"])

        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_sid, "user_id": user_id,
            "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number, "started_at": datetime.now(timezone.utc),
        })

        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"vapi_call_id": call_sid, "updated_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        msg = str(e)
        logger.error("[scheduler] Call failed for debtor %s: %s", debtor["_id"], e)
        # Número inválido de Twilio (21211/21201/21214/21215/21217…): NO reintentar
        # (re-loop infinito) → excluir de la cola. Cualquier otro error = transitorio
        # → vuelve a pendiente para reintentar.
        _num_invalido = (
            any(code in msg for code in ("21211", "21201", "21214", "21215", "21217"))
            or "is not valid" in msg or "No 'To'" in msg or "not authorized to call" in msg
        )
        if _num_invalido:
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"excluir_llamada": True, "excluir_motivo": "telefono_invalido",
                          "estado": "sin_contacto", "updated_at": datetime.now(timezone.utc)}},
            )
        else:
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"estado": "pendiente", "updated_at": datetime.now(timezone.utc)}},
            )
        # Deshacer el $inc del despachador — contó una marcación que no ocurrió.
        await db.cobranza_daily_stats.update_one(
            {"user_id": user_id, "fecha": _today_bogota()},
            {"$inc": {"llamadas_iniciadas": -1}},
        )


# ---------------------------------------------------------------------------
# Job 3: Rescue stuck 'llamando' debtors (call may not complete cleanly)
# ---------------------------------------------------------------------------

async def reschedule_intento_fallido(db, debtor: dict) -> str:
    """
    Regla del informe: UN intento por deudor por día. Cuando la llamada NO
    conecta (no contestó / ocupado / falló), el intento CUENTA y la próxima
    cita pasa al SIGUIENTE día hábil — nunca al mismo día. Sin esto, el
    dispatcher re-marcaba a los mismos cada 15 min hasta quemar el cupo
    (observado 17-jul: 700 marcaciones para ~140 personas). Si con este
    intento llega a max_intentos → 'agotado' + alerta a cartera.
    Devuelve el estado final asignado.
    """
    import pytz
    from cobranza.config_cache import get_tenant_config
    from cobranza.call_scheduler import add_business_days
    from cobranza.sequence_engine import _at_franja_inicio, _parse_festivos

    user_id = str(debtor.get("user_id"))
    cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
    timings, horarios = cfg.get("timings") or {}, cfg.get("horarios") or {}
    max_intentos = int(timings.get("max_intentos") or 3)
    nuevos = int(debtor.get("intentos") or 0) + 1
    now = datetime.now(timezone.utc)

    if nuevos >= max_intentos:
        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"estado": "agotado", "intentos": nuevos, "updated_at": now},
             "$unset": {"proximo_intento_at": "", "proximo_intento_numero": "", "vapi_call_id": ""}},
        )
        try:
            from cobranza.alerts import crear_alerta
            await crear_alerta(db, user_id, debtor, "sin_contacto_agotado")
        except Exception:
            logger.exception("[reschedule] alerta agotado falló (no fatal)")
        return "agotado"

    hoy = datetime.now(pytz.timezone("America/Bogota")).date()
    manana = add_business_days(hoy, 1, _parse_festivos(horarios))
    cita = _at_franja_inicio(manana, horarios)
    await db.debtors.update_one(
        {"_id": debtor["_id"]},
        {"$set": {"estado": "sin_contacto", "intentos": nuevos,
                  "proximo_intento_at": cita, "proximo_intento_numero": nuevos + 1,
                  "updated_at": now},
         "$unset": {"vapi_call_id": ""}},
    )
    return "sin_contacto"


async def rescue_stuck_llamando_job() -> None:
    """
    Deudores atascados en 'llamando' >15 min (la llamada nunca conectó o el
    pipeline murió): se reprograman para el SIGUIENTE día hábil vía
    reschedule_intento_fallido — nunca re-marcado el mismo día.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

    db = get_db()
    cursor = db.debtors.find(
        {
            "estado": "llamando",
            "updated_at": {"$lte": cutoff},
        }
    )
    stuck = await cursor.to_list(length=None)

    if stuck:
        logger.warning("[rescue_stuck_llamando_job] Rescuing %d debtors stuck in 'llamando'", len(stuck))

    for debtor in stuck:
        try:
            final = await reschedule_intento_fallido(db, debtor)
            logger.warning("[rescue_stuck_llamando_job] Debtor %s -> %s (cita: siguiente dia habil)",
                           debtor["_id"], final)
        except Exception:
            logger.exception("[rescue_stuck_llamando_job] fallo debtor %s", debtor["_id"])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_cobranza_jobs(scheduler, force: bool = False) -> None:
    """
    Register all 3 cobranza campaign jobs on the given APScheduler instance.

    Call this from main.py lifespan *after* scheduler.start() has been called.
    Does NOT import scheduler at module level to avoid circular imports.

    Args:
        scheduler: AsyncIOScheduler instance from landa.scheduler
        force:     when True, register the jobs regardless of the boot-time env
                   var. Used by the runtime kill-switch when it is turned ON, so
                   a worker booted with autocall disabled can be enabled live.

    Jobs are registered in a PAUSED state whenever autocall is currently OFF, so
    even a forced/boot registration never dials until the master switch is ON.
    """
    # ── KILL-SWITCH (default OFF for safety) ─────────────────────────────────
    # These jobs place REAL outbound calls to REAL debtors. They must NEVER fire
    # just because the app booted — a deploy would start dialing people. So the
    # automated calling campaign only registers when COBRANZA_AUTOCALL_ENABLED is
    # explicitly truthy. Default = disabled: the app runs, manual test calls via
    # /call/initiate-v2 still work, but the scheduler dials no one.
    autocall_enabled = os.getenv("COBRANZA_AUTOCALL_ENABLED", "false").lower() in ("1", "true", "yes")
    if not autocall_enabled and not force:
        logger.warning(
            "[register_cobranza_jobs] COBRANZA_AUTOCALL_ENABLED is not set — "
            "automated calling jobs NOT registered (no debtor will be auto-called). "
            "Set COBRANZA_AUTOCALL_ENABLED=true or flip the runtime kill-switch ON."
        )
        return

    from cobranza.sequence_engine import dispatch_intentos_job, plan_intentos_job

    scheduler.add_job(
        plan_intentos_job,
        "interval",
        minutes=15,
        id="seq_plan_intentos",
        replace_existing=True,
    )
    # Cada 2 min (era 5): con MAX_CONCURRENT_CALLS=5 y llamadas de ~1 min, el
    # ciclo de 5 min dejaba las lineas ociosas ~4 min. Configurable sin deploy
    # de codigo via COBRANZA_DISPATCH_INTERVAL_MIN.
    dispatch_min = int(os.getenv("COBRANZA_DISPATCH_INTERVAL_MIN", "2"))
    scheduler.add_job(
        dispatch_intentos_job,
        "interval",
        minutes=dispatch_min,
        id="seq_dispatch_intentos",
        replace_existing=True,
    )
    scheduler.add_job(
        rescue_stuck_llamando_job,
        "interval",
        minutes=10,
        id="cobr_rescue_llamando",
        replace_existing=True,
    )
    logger.warning(
        "[register_cobranza_jobs] AUTOCALL ENABLED — Registered: seq_plan_intentos (15m), "
        "seq_dispatch_intentos (%dm), cobr_rescue_llamando (10m). Real debtors WILL be called.",
        dispatch_min,
    )
