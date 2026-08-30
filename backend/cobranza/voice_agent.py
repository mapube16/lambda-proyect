"""voice_agent.py — motor de voz sobre el Deepgram Voice Agent API (produccion).

Pivote (09-ago): en vez de orquestar STT+LLM+TTS a mano en pipecat (turnos, eco
y barge-in nos rompian llamada tras llamada), se delega ese plumbing al Voice
Agent de Deepgram, que lo hace nativo. Deepgram escucha (nova-2 es + keyterms),
Gemini piensa (el mismo prompt de 3 capas), celeste (rola) pronuncia.

Este modulo es SOLO el puente + el cableado de las 12 tools reales a nuestros
handlers (crear_alerta + CobranzaOrchestrator) y la construccion del CallResult
para el post-call. Toda la capa de Twilio (AMD, ring timeout, ledger de minutos,
scheduling) es independiente y sigue igual.

Se monta detras del flag tenant_config.cobranza.voz_engine == "deepgram_agent"
(o COBRANZA_VOZ_ENGINE); default: el pipeline de pipecat intacto.
"""
import asyncio
import base64
import json
import logging
import os
import time
from datetime import date, datetime, time as dtime, timezone

import websockets

from cobranza.voz_comun import CallResult

logger = logging.getLogger("cobranza.voice_agent")

DG_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"
# flash-lite: 0.66 s de think medidos vs 1.49-1.9 s de 3.5-flash (sonda
# check_deepgram_agent.py, 30-ago) — el turno completo baja de ~1.8 s a ~0.96 s.
# Si en llamada real cede terreno en el guion, se revierte con la env sin deploy.
THINK_MODEL = os.getenv("COBRANZA_AGENT_THINK_MODEL", "gemini-3.1-flash-lite")


# ── Esquemas de las tools (formato Voice Agent) ────────────────────────────────
# Mismas 12 de produccion. El destinatario/ids sensibles NO los elige el modelo:
# se resuelven server-side contra el deudor en curso (igual que en pipecat).

def _tool_schemas(modo_recepcion: bool) -> list:
    end_call = {"name": "end_call",
                "description": "Termina la llamada. Despidete ANTES de llamarla.",
                "parameters": {"type": "object",
                               "properties": {"reason": {"type": "string"}},
                               "required": ["reason"]}}
    if modo_recepcion:
        return [
            {"name": "identificar_cliente",
             "description": "Busca al cliente por el numero de documento que MARCO en el "
                            "teclado (te llega como '[TECLADO] <digitos>') o que dijo. "
                            "Devuelve sus polizas pendientes o 'no_encontrado'.",
             "parameters": {"type": "object",
                            "properties": {"documento": {"type": "string"}},
                            "required": ["documento"]}},
            end_call,
        ]
    return [
        end_call,
        {"name": "solicitar_link_cupon",
         "description": "El deudor pide el LINK o el CUPON de pago. Genera alerta a cartera "
                        "para enviarlo por WhatsApp. Confirma el envio.",
         "parameters": {"type": "object",
                        "properties": {"tipo": {"type": "string", "enum": ["link", "cupon"]}},
                        "required": ["tipo"]}},
        {"name": "informar_fecha_pago",
         "description": "El deudor promete pagar en una fecha futura ('pago el viernes'). "
                        "Registra la promesa (hoy es " + date.today().isoformat() + ").",
         "parameters": {"type": "object",
                        "properties": {"fecha": {"type": "string", "description": "YYYY-MM-DD"}},
                        "required": ["fecha"]}},
        {"name": "reagendar_llamada",
         "description": "El deudor pide que lo llamen en OTRO momento. Pregunta dia y hora "
                        "ANTES de llamarla. Reprograma la llamada.",
         "parameters": {"type": "object",
                        "properties": {"fecha": {"type": "string", "description": "YYYY-MM-DD"},
                                       "hora": {"type": "string", "description": "HH:MM 24h"}},
                        "required": ["fecha"]}},
        {"name": "notify_payment_claim",
         "description": "El deudor dice que YA PAGO. Notifica al equipo para verificar el "
                        "comprobante. Tu NO confirmas el pago, solo registras el reporte.",
         "parameters": {"type": "object",
                        "properties": {"detalle": {"type": "string"}},
                        "required": ["detalle"]}},
        {"name": "escalate",
         "description": "Escala a un asesor humano: el deudor lo pide, o hay disputa del "
                        "monto, reclamo, o pregunta por coberturas de su poliza. Confirma "
                        "que un asesor lo contactara, despidete y llama end_call.",
         "parameters": {"type": "object",
                        "properties": {"reason": {"type": "string"}},
                        "required": ["reason"]}},
        {"name": "registrar_no_desea_llamadas",
         "description": "El deudor pide EXPLICITAMENTE no ser llamado mas ('no me llame'). "
                        "Detiene todas las llamadas futuras. Despidete y llama end_call.",
         "parameters": {"type": "object", "properties": {}}},
        {"name": "verify_identity",
         "description": "USO RARO. Solo si la persona dice EXPLICITAMENTE que NO es el deudor "
                        "('numero equivocado', 'el no vive aqui') o da otro nombre. Nunca por "
                        "un simple 'alo'/'si'.",
         "parameters": {"type": "object",
                        "properties": {"utterance": {"type": "string"}},
                        "required": ["utterance"]}},
        {"name": "registrar_oportunidad_comercial",
         "description": "El deudor muestra interes en OTRO producto/seguro. Alerta al asesor "
                        "comercial. No interrumpe el flujo de cobranza.",
         "parameters": {"type": "object",
                        "properties": {"detalle": {"type": "string"}},
                        "required": ["detalle"]}},
    ]


# ── Dispatch de tools → handlers reales ────────────────────────────────────────

class _Dispatcher:
    """Ejecuta las tools contra la DB real. Reusa crear_alerta + orchestrator +
    la logica de identificar_cliente. `identificado` se comparte con el firewall
    conceptual de recepcion (aqui: si no esta identificado, solo corre
    identificar_cliente)."""

    def __init__(self, db, user_id: str, debtor: dict, orchestrator, call_sid: str,
                 transcript_ref: list, identificado: dict):
        self.db = db
        self.user_id = user_id
        self.debtor = debtor
        self.orch = orchestrator
        self.call_sid = call_sid
        self._transcript = transcript_ref
        self.identificado = identificado
        self._alertas = set()   # dedupe por tipo

    async def _alerta(self, tipo: str, *, detalle: str = "", extra: dict = None) -> dict:
        if not self.user_id or tipo in self._alertas:
            return {"ok": True, "dedupe": True}
        self._alertas.add(tipo)
        try:
            from cobranza.alerts import crear_alerta
            doc = await crear_alerta(self.db, self.user_id, self.debtor, tipo,
                                     detalle=detalle, extra=extra)
            return {"ok": True, "alerta_id": str(doc.get("_id"))}
        except Exception:
            logger.exception("[agent] crear_alerta(%s) fallo", tipo)
            return {"ok": False}

    async def __call__(self, name: str, args: dict) -> dict:
        d = self.debtor
        try:
            if name == "solicitar_link_cupon":
                tipo = args.get("tipo", "link")
                r = await self._alerta("solicitud_link_cupon",
                                       detalle=f"Solicito {tipo} de pago", extra={"tipo": tipo})
                return {**r, "confirmar": f"En breve le enviamos el {tipo} de pago por WhatsApp."}

            if name == "informar_fecha_pago":
                dd = date.fromisoformat(str(args.get("fecha", ""))[:10])
                if self.orch:
                    await self.orch.update_debtor(str(d["_id"]),
                        {"estado": "promesa_de_pago", "fecha_promesa": dd.isoformat()})
                return await self._alerta("fecha_estimada_pago", detalle=f"Pagaria el {dd.isoformat()}")

            if name == "reagendar_llamada":
                dd = date.fromisoformat(str(args.get("fecha", ""))[:10])
                if dd < datetime.now(timezone.utc).date():
                    return {"ok": False, "error": "fecha en el pasado"}
                at = None
                try:
                    hh, mm = str(args.get("hora") or "09:00").split(":")[:2]
                    at = datetime.combine(dd, dtime(int(hh), int(mm)))
                except Exception:
                    at = datetime.combine(dd, dtime(9, 0))
                if self.orch:
                    await self.orch.update_debtor(str(d["_id"]),
                        {"estado": "reagendado", "fecha_reagendada": at.isoformat(),
                         "proximo_intento_at": None})
                return {"ok": True, "confirmar": "Listo, reprogramamos la llamada."}

            if name == "notify_payment_claim":
                # SOLO alerta a cartera para que un HUMANO verifique el comprobante.
                # NO cambia el estado del deudor: un "pague" mal transcrito por el
                # STT (paso 09-ago: se marco pago_reportado sin que el cliente lo
                # dijera) no puede frenar la cobranza. El humano revisa y decide.
                return await self._alerta("pago_reportado",
                                          detalle=args.get("detalle", "el cliente dice que ya pago"))

            if name == "escalate":
                if self.orch:
                    try:
                        await self.orch.escalate(args.get("reason", "escalado"), str(d.get("_id")))
                    except Exception:
                        logger.exception("[agent] escalate orch fallo")
                return await self._alerta("consulta_fuera_alcance", detalle=args.get("reason", ""))

            if name == "registrar_no_desea_llamadas":
                if self.orch:
                    await self.orch.update_debtor(str(d["_id"]),
                        {"no_llamar": True, "no_llamar_motivo": "opt_out", "clasificado_por": "manual"})
                return await self._alerta("opt_out")

            if name == "verify_identity":
                if self.orch:
                    try:
                        r = await self.orch.verify_identity(args.get("utterance", ""),
                                                            d.get("nombre"))
                        if not r.get("confirmed"):
                            await self._alerta("numero_equivocado",
                                               detalle=args.get("utterance", "")[:120])
                        return r
                    except Exception:
                        logger.exception("[agent] verify_identity fallo")
                return {"confirmed": False}

            if name == "registrar_oportunidad_comercial":
                return await self._alerta("oportunidad_comercial", detalle=args.get("detalle", ""))

            if name == "identificar_cliente":
                return await self._identificar(args.get("documento", ""))

        except Exception:
            logger.exception("[agent] tool %s fallo", name)
            return {"ok": False, "error": "fallo interno"}
        return {"ok": True}

    async def _identificar(self, crudo: str) -> dict:
        from cobranza.voz_comun import documento_base
        from cobranza.es_numbers import pesos_en_palabras
        digits = "".join(c for c in str(crudo) if c.isdigit())
        cands = []
        if len(digits) >= 5:
            async for x in self.db.debtors.find(
                {"user_id": self.user_id, "is_active": {"$ne": False},
                 "cliente_documento": {"$nin": [None, ""]}},
                {"cliente_documento": 1, "nombre": 1, "numero_poliza": 1, "ramo_nombre": 1,
                 "aseguradora_nombre": 1, "monto": 1, "vencimiento": 1, "fecha_pago": 1,
                 "numero_cuota": 1, "dias_mora": 1}):
                if documento_base(x.get("cliente_documento")) == digits:
                    cands.append(x)
        if not cands:
            await self._alerta("llamada_entrante_no_identificada",
                               detalle=f"Documento '{digits}' sin match en cartera.")
            return {"resultado": "no_encontrado",
                    "instruccion": "Disculpate, di que un asesor puede ayudarle, NO reveles "
                                   "ningun dato, y despidete."}
        principal = max(cands, key=lambda x: int(x.get("dias_mora") or 0))
        self.debtor = principal
        self.identificado["ok"] = True
        await self.db.cobranza_calls_in_progress.update_one(
            {"call_sid": self.call_sid},
            {"$set": {"debtor_id": str(principal["_id"]), "debtor_name": principal.get("nombre")}})
        pol = [{"tipo": x.get("ramo_nombre"), "aseguradora": x.get("aseguradora_nombre"),
                "valor": pesos_en_palabras(float(x.get("monto") or 0)),
                "vence": str(x.get("fecha_pago") or x.get("vencimiento"))[:10],
                "dias_mora": int(x.get("dias_mora") or 0)} for x in cands]
        return {"resultado": "encontrado", "nombre": principal.get("nombre"),
                "polizas_pendientes": pol,
                "instruccion": "Identidad confirmada. Saludalo por su nombre y gestiona el "
                               "recordatorio con estos datos."}


# ── Settings del Voice Agent ───────────────────────────────────────────────────

def _env_json(name: str) -> dict:
    try:
        return json.loads(os.getenv(name, "") or "{}") or {}
    except json.JSONDecodeError:
        logger.warning("[agent] %s no es JSON valido — ignorado", name)
        return {}


def _listen_provider(keyterms: list, cfg: dict) -> dict:
    """Oido del agente. cfg = tenant_configs.cobranza.deepgram_listen (o env
    COBRANZA_AGENT_LISTEN como JSON). Default: nova-3 es (doc oficial
    Twilio+Deepgram). Con model "flux-general-multi" se usa el end-of-turn
    INTEGRADO de Flux (eot_threshold / eager_eot_threshold / eot_timeout_ms):
    decide que el cliente termino por el modelo, no por un silencio fijo — es
    la palanca grande de latencia STT→LLM. Se valida sin llamada real con
    scripts/check_deepgram_agent.py."""
    model = str(cfg.get("model") or "nova-3")
    p = {"type": "deepgram", "model": model, "keyterms": keyterms}
    if model.startswith("flux"):
        p["version"] = "v2"
        p["language_hints"] = list(cfg.get("language_hints") or ["es"])
        for k in ("eot_threshold", "eager_eot_threshold", "eot_timeout_ms"):
            if cfg.get(k) is not None:
                p[k] = cfg[k]
    else:
        p["language"] = str(cfg.get("language") or "es")
    if cfg.get("smart_format") is not None:
        p["smart_format"] = bool(cfg["smart_format"])
    return p


def _settings(prompt: str, greeting: str, voz: str, keyterms: list,
              modo_recepcion: bool, listen_cfg: dict = None,
              temperature: float = 0.5) -> dict:
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "mulaw", "sample_rate": 8000},
            "output": {"encoding": "mulaw", "sample_rate": 8000, "container": "none"},
        },
        "agent": {
            "listen": {"provider": _listen_provider(keyterms, listen_cfg or {})},
            # temperature 0.5 (misma que el pipeline pipecat): menos deliberacion
            # de muestreo = respuesta un poco antes; cobranza quiere guion, no
            # creatividad.
            "think": {"provider": {"type": "google", "model": THINK_MODEL,
                                   "temperature": temperature},
                      "prompt": prompt, "functions": _tool_schemas(modo_recepcion)},
            "speak": {"provider": {"type": "deepgram", "model": voz}},
            "greeting": greeting,
        },
    }


# ── Prompt de 3 capas + saludo (mismo prompt_builder de produccion) ────────────

def armar_prompt(debtor: dict, tenant_config: dict, *, modo_recepcion: bool) -> tuple:
    """Devuelve (prompt, greeting, keyterms). Reusa prompt_builder para que el
    guion sea IDENTICO al del pipeline pipecat."""
    from cobranza.prompt_builder import (
        assemble_system_prompt, nombre_dos, render_greeting, resolve_persona,
    )
    from cobranza.es_numbers import pesos_en_palabras
    from cobranza.voz_comun import keyterms_llamada
    persona = resolve_persona(tenant_config)
    brand = persona.get("company_brand") or persona.get("company_name", "")
    agente = str(persona.get("agent_name") or "Aria").title()

    if modo_recepcion:
        greeting = f"{brand}, muy buenos dias, le habla {agente}. ¿Con quien tengo el gusto?"
        prompt = (
            f"Eres {agente}, la asistente virtual de {brand} (seguros, Colombia). "
            "Contestaste una llamada ENTRANTE; aun no sabes quien llama.\n"
            "OBJETIVO: identificarlo por su documento (cedula o NIT). Pidele que lo MARQUE "
            "en el teclado y termine con numeral; te llega como '[TECLADO] <digitos>'. Apenas "
            "lo tengas, llama identificar_cliente. Si insiste en decirlo de viva voz, "
            "aceptalo. NUNCA reveles datos de polizas/saldos ni confirmes si un documento "
            "existe hasta que identificar_cliente confirme. Espanol colombiano, de usted, "
            "frases cortas, numeros digito por digito. Al terminar, despidete y llama end_call."
        )
        return prompt, greeting, keyterms_llamada(debtor or {})

    first_name = nombre_dos(debtor.get("nombre") or "")
    monto_natural = pesos_en_palabras(float(debtor.get("monto") or 0))
    runtime_block = (
        "DATOS DE ESTA LLAMADA (reales y exactos de ESTE deudor — usalos directo):\n"
        f"- Nombre: {debtor.get('nombre')}\n"
        f"- Dirigete por su nombre: '{first_name}'. NUNCA 'senor/senora/don/dona'.\n"
        f"- Deuda pendiente: {monto_natural}\n"
        f"- Vencimiento: {str(debtor.get('vencimiento') or debtor.get('fecha_pago'))[:10]}\n"
        f"- Tipo de poliza: {debtor.get('ramo_nombre')}\n"
        f"- Aseguradora: {debtor.get('aseguradora_nombre')}\n\n"
    )
    prompt = assemble_system_prompt(
        persona, runtime_block=runtime_block, first_name=first_name,
        ramo=debtor.get("ramo_nombre") or "seguros", monto_natural=monto_natural,
        aseguradora=debtor.get("aseguradora_nombre") or "",
        riesgo=str(debtor.get("objeto_asegurado") or "").strip(),
        modalidad=str(debtor.get("forma_pago") or "").strip(),
        intento=int(debtor.get("proximo_intento_numero") or (debtor.get("intentos") or 0) + 1),
        dias_mora=int(debtor.get("dias_mora") or 0),
        numero_cuota=str(debtor.get("numero_cuota") or ""),
        is_inbound=False,
    ).replace("ARIA", "Aria")
    greeting = render_greeting(persona, first_name).replace("ARIA", "Aria")
    return prompt, greeting, keyterms_llamada(debtor or {})


# ── Bridge Twilio ↔ Voice Agent ────────────────────────────────────────────────

_MULAW_BPS = 8000.0          # bytes/segundo de mulaw 8k = segundos que suena
_TRAMA = 160                 # 20 ms — la trama que Twilio espera


async def run_voice_agent(*, websocket, call_sid: str, debtor: dict, user_id: str,
                          stream_id: str, tenant_config: dict,
                          is_inbound: bool = False, modo_recepcion: bool = False) -> CallResult:
    """Puentea el media-stream de Twilio (ya aceptado) con el Voice Agent de
    Deepgram y devuelve el CallResult para el post-call. Nunca lanza hacia
    afuera: cualquier fallo cierra limpio con lo que se haya recolectado."""
    result = CallResult(call_sid=call_sid, started_at=time.time(), engine="deepgram_agent")
    from database import get_db
    db = get_db()
    key = os.getenv("DEEPGRAM_API_KEY", "")

    # 1) Conectar a Deepgram YA, en paralelo con armar prompt/orchestrator: el
    #    handshake TLS+WS (~300-600 ms) deja de sumarse al silencio pre-saludo.
    t_conn = time.time()

    async def _abrir():   # websockets.connect es awaitable pero NO corutina
        return await websockets.connect(
            DG_AGENT_URL, additional_headers={"Authorization": f"Token {key}"},
            close_timeout=1)  # si Twilio muere primero, close() esperaba 10s el handshake

    conectar = asyncio.create_task(_abrir())

    cobr = tenant_config.get("cobranza") or {}
    prompt, greeting, keyterms = armar_prompt(debtor or {}, tenant_config,
                                              modo_recepcion=modo_recepcion)
    voz = str(cobr.get("deepgram_voice") or tenant_config.get("deepgram_voice")
              or os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-celeste-es"))
    listen_cfg = cobr.get("deepgram_listen") or _env_json("COBRANZA_AGENT_LISTEN")
    temperature = float(cobr.get("voice_temperature") or tenant_config.get("voice_temperature")
                        or os.getenv("COBRANZA_AGENT_TEMPERATURE", "0.5"))
    logger.info("[agent] call=%s recepcion=%s voz=%s think=%s listen=%s keyterms=%d prompt=%d chars",
                call_sid, modo_recepcion, voz, THINK_MODEL,
                listen_cfg.get("model") or "nova-3", len(keyterms), len(prompt))
    from cobranza.cobranza_orchestrator import CobranzaOrchestrator
    orch = CobranzaOrchestrator(user_id, tenant_config) if user_id else None
    identificado = {"ok": not modo_recepcion}
    dispatch = _Dispatcher(db, user_id, debtor or {}, orch, call_sid,
                           result.transcript, identificado)

    # ── Reloj de reproduccion ─────────────────────────────────────────────────
    # Deepgram entrega el audio del agente en RAFAGA (mucho mas rapido que tiempo
    # real) y Twilio lo reproduce a 8000 B/s. Todo lo que dependa de "ARIA ya
    # termino de hablar" (anti-eco, colgar tras la despedida) se calcula sobre
    # CUANDO TERMINA DE SONAR, no sobre cuando llego el ultimo chunk. (Bug
    # anterior: a los 0.5 s del ultimo chunk se reabria el microfono con ARIA
    # aun a mitad de frase → su propio eco entraba como turno del cliente.)
    play = {"fin": 0.0}                       # epoch en que Twilio termina de sonar
    _COLA_ANTIECO = float(os.getenv("COBRANZA_AGENT_ECHO_TAIL_S", "0.5"))
    _SILENCIO = b"\xff" * _TRAMA
    # Half-duplex apagable por tenant/env: su costo real es que lo que el
    # cliente diga MIENTRAS ARIA habla se pierde (y el se siente ignorado). En
    # telefono al oido casi no hay eco; full-duplex deja que Deepgram maneje
    # eco/barge-in nativo. Default: on (el caso ALTAVOZ inventaba turnos).
    _half_duplex = str(cobr.get("agent_half_duplex",
                                os.getenv("COBRANZA_AGENT_HALF_DUPLEX", "true"))).lower() != "false"

    # El SALUDO manda: hasta que el primer byte de audio de ARIA llegue, TODO lo
    # del cliente se silencia hacia Deepgram. Sin esto habia una carrera fatal:
    # el "alo" al contestar entraba ANTES del saludo, Deepgram disparaba
    # UserStartedSpeaking / barge-in sobre un saludo apenas encolado, y el
    # cliente oia a ARIA arrancando A MITAD de frase (queja 30-ago).
    saludo_pendiente = {"v": True}

    def aria_habla() -> bool:
        # Half-duplex anti-eco (doc Deepgram audio-preprocessing): mientras ARIA
        # suena (+cola), lo que vuelve por la linea es su eco (grave en ALTAVOZ);
        # a Deepgram se le manda silencio. Costo: sin barge-in ese ratito.
        return _half_duplex and (saludo_pendiente["v"]
                                 or time.time() < play["fin"] + _COLA_ANTIECO)

    # ── Latencia por turno (lo que el cliente percibe) ────────────────────────
    lat = {"t_eot": 0.0, "turno": 0}

    # ── Colgado coordinado ───────────────────────────────────────────────────
    colgar = asyncio.Event()
    motivo = {"v": ""}

    def pedir_colgar(m: str):
        if not colgar.is_set():
            motivo["v"] = m
            result.end_reason = result.end_reason or m
            colgar.set()

    marca_eco = asyncio.Event()   # Twilio devolvio el mark: lo encolado ya SONO

    async def _enviar_marca():
        try:
            await websocket.send_json({"event": "mark", "streamSid": stream_id,
                                       "mark": {"name": "fin-despedida"}})
        except Exception:
            pass

    async def colgar_tras_despedida(max_espera: float = 8.0):
        # end_call: colgar cuando la despedida SONO de verdad. El mark de Twilio
        # se encola detras del audio ya enviado y vuelve como eco cuando ese
        # audio se reprodujo — senal exacta, sin estimar red/buffers. Si llega
        # MAS audio despues del mark, se manda otro. Fallback: el reloj de
        # reproduccion +1s si el eco no vuelve; tope duro de max_espera.
        limite = time.time() + max_espera
        await _enviar_marca()
        while time.time() < limite:
            if marca_eco.is_set():
                if time.time() >= play["fin"] - 0.05:
                    break                     # eco recibido y nada mas por sonar
                marca_eco.clear()             # llego mas despedida tras el mark
                await _enviar_marca()
            elif time.time() >= play["fin"] + 1.0:
                break                         # fallback estimado: eco perdido
            await asyncio.sleep(0.15)
        pedir_colgar("end_call")

    tareas_bg: set = set()

    def _bg(coro):
        t = asyncio.create_task(coro)
        tareas_bg.add(t)
        t.add_done_callback(tareas_bg.discard)
        return t

    async def ejecutar_tool(dg, f: dict):
        # Corre como task: mientras la tool pega a Mongo/alertas, el audio que
        # el agente ya mando sigue fluyendo a Twilio (antes el loop se frenaba).
        name = f.get("name", "")
        _a = f.get("arguments")
        if isinstance(_a, str):            # el Voice Agent manda arguments como STRING JSON
            try:
                _a = json.loads(_a) if _a.strip() else {}
            except json.JSONDecodeError:
                _a = {}
        t0 = time.time()
        content = await dispatch(name, _a or {})
        logger.info("[agent][lat] tool %s: %.0f ms", name, (time.time() - t0) * 1000)
        await dg.send(json.dumps({"type": "FunctionCallResponse", "id": f.get("id"),
                                  "name": name,
                                  "content": json.dumps(content, ensure_ascii=False)}))
        if name == "end_call":
            result.end_reason = str((_a or {}).get("reason") or "end_call")
            _bg(colgar_tras_despedida())

    async def watchdogs():
        # Mismos guardas que el pipeline pipecat (el motor nuevo no los tenia):
        # sin voz humana en N s = buzon mudo/aire muerto → colgar; tope duro de
        # duracion pase lo que pase.
        no_speech = int(os.getenv("COBRANZA_NO_SPEECH_HANGUP_SECS", "20"))
        max_s = int(os.getenv("COBRANZA_MAX_CALL_SECS", "240"))
        await asyncio.sleep(no_speech)
        if result.user_turn_count == 0:
            pedir_colgar(f"sin voz humana tras {no_speech}s")
            return
        await asyncio.sleep(max(0, max_s - no_speech))
        pedir_colgar(f"tope de {max_s}s")

    dg_box = {"ws": None}      # la bomba arranca ANTES de tener la sesion
    listo = asyncio.Event()    # Settings ya enviados: se puede reenviar audio
    descartado = {"frames": 0}

    async def twilio_a_dg():
        async for raw in websocket.iter_text():
            m = json.loads(raw)
            ev = m.get("event")
            if ev == "media":
                if not listo.is_set():
                    # Audio ANTERIOR a la sesion con Deepgram (los "alo, alo?"
                    # mientras conectabamos). Antes se acumulaba en el buffer y
                    # al conectar entraba EN RAFAGA: el STT arrancaba esos
                    # segundos atrasado y ARIA respondia a turnos viejos toda la
                    # llamada (visto: stt_latency 6.8s drenando a 0.2s/s). Se
                    # DESCARTA: el saludo lo dice ella primero igual.
                    descartado["frames"] += 1
                    continue
                await dg_box["ws"].send(
                    _SILENCIO if aria_habla() else base64.b64decode(m["media"]["payload"]))
            elif ev == "dtmf":
                dig = "".join(c for c in (m.get("dtmf") or {}).get("digit", "") if c.isdigit())
                if dig and listo.is_set():
                    await dg_box["ws"].send(json.dumps({"type": "InjectUserMessage",
                                                        "content": f"[TECLADO] {dig}"}))
            elif ev == "mark":
                if (m.get("mark") or {}).get("name") == "fin-despedida":
                    marca_eco.set()
            elif ev == "stop":
                pedir_colgar("twilio stop")
                return

    async def dg_a_twilio(dg):
        from cobranza.voz_comun import _VOICEMAIL_LIVE_RE
        async for msg in dg:
            if isinstance(msg, bytes):
                now = time.time()
                saludo_pendiente["v"] = False   # ya esta sonando: manda el reloj
                if lat["t_eot"]:
                    logger.info("[agent][lat] turno %d: fin-de-turno → primer audio %.0f ms",
                                lat["turno"], (now - lat["t_eot"]) * 1000)
                    lat["t_eot"] = 0.0
                if play["fin"] < now:
                    play["fin"] = now          # cola vacia: empieza a sonar ya
                play["fin"] += len(msg) / _MULAW_BPS
                # Re-chunk a tramas de 20 ms: Deepgram manda bloques grandes e
                # irregulares y Twilio glitchea al reproducirlos ("se traba").
                for i in range(0, len(msg), _TRAMA):
                    await websocket.send_json({
                        "event": "media", "streamSid": stream_id,
                        "media": {"payload": base64.b64encode(msg[i:i + _TRAMA]).decode()}})
                continue
            ev = json.loads(msg)
            t = ev.get("type")
            if t == "UserStartedSpeaking":
                # barge-in SOLO en full-duplex: vaciar lo encolado en Twilio.
                # En half-duplex no hay barge-in — y este clear era el que
                # BOTABA el saludo recien encolado cuando el "alo" inicial
                # disparaba UserStartedSpeaking (saludo cortado a la mitad).
                if not _half_duplex:
                    await websocket.send_json({"event": "clear", "streamSid": stream_id})
                    play["fin"] = 0.0
            elif t == "ConversationText":
                texto = ev.get("content", "")
                if ev.get("role") == "user":
                    result.transcript.append((time.time(), "Deudor", texto))
                    lat["turno"] += 1
                    lat["t_eot"] = time.time()
                    if _VOICEMAIL_LIVE_RE.search(texto):
                        pedir_colgar(f"buzon en vivo: {texto[:60]!r}")
                else:
                    result.transcript.append((time.time(), "ARIA", texto))
            elif t == "FunctionCallRequest":
                for f in ev.get("functions", []):
                    if f.get("client_side", True):
                        _bg(ejecutar_tool(dg, f))
            elif t == "LatencyReport":
                # Desglose oficial por turno (segundos): stt / ttt_* (LLM) / tts.
                logger.info("[agent][lat] deepgram %s",
                            {k: v for k, v in ev.items() if k != "type"})
            elif t == "SettingsApplied":
                logger.info("[agent] SettingsApplied a +%.0f ms del arranque del bridge",
                            (time.time() - t_conn) * 1000)
            elif t in ("Error", "Warning", "InjectionRefused"):
                logger.log(logging.ERROR if t == "Error" else logging.WARNING,
                           "[agent] Deepgram %s: %s", t, ev)
                if t == "Error":
                    pedir_colgar("deepgram error")
                    return

    dg = None
    tareas = [asyncio.create_task(twilio_a_dg())]   # leer YA: que nada se encole
    try:
        dg = await conectar
        logger.info("[agent] conectado a Deepgram en %.0f ms", (time.time() - t_conn) * 1000)
        await dg.send(json.dumps(_settings(prompt, greeting, voz, keyterms, modo_recepcion,
                                           listen_cfg, temperature)))
        dg_box["ws"] = dg
        listo.set()
        if descartado["frames"]:
            logger.info("[agent][lat] descartados %d ms de audio pre-sesion (no envenenan el STT)",
                        descartado["frames"] * 20)
        tareas += [asyncio.create_task(dg_a_twilio(dg)),
                   asyncio.create_task(watchdogs()), asyncio.create_task(colgar.wait())]
        await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        if colgar.is_set():
            logger.info("[agent] colgando call=%s motivo=%s", call_sid, motivo["v"])
    except Exception:
        logger.exception("[agent] bridge fallo call=%s", call_sid)
    finally:
        for x in list(tareas) + list(tareas_bg):
            x.cancel()
        if dg is not None:
            try:
                await dg.close()
            except Exception:
                pass
        # Colgado garantizado: cerrar el stream termina la llamada con el TwiML
        # actual, pero el update REST la mata aunque el TwiML cambie o el WS
        # quede zombie — y corta la facturacion ya. Solo cuando decidimos
        # nosotros (si colgo el cliente, la llamada ya esta completed).
        if colgar.is_set() and motivo["v"] != "twilio stop" and call_sid.startswith("CA"):
            def _rest_hangup():
                try:
                    from twilio.rest import Client
                    Client(os.getenv("TWILIO_ACCOUNT_SID", ""),
                           os.getenv("TWILIO_AUTH_TOKEN", "")).calls(call_sid).update(status="completed")
                except Exception:
                    logger.info("[agent] REST hangup no aplico (llamada ya terminada)")
            try:
                await asyncio.get_event_loop().run_in_executor(None, _rest_hangup)
            except Exception:
                pass

    result.ended_at = time.time()
    result.duration_seconds = int(result.ended_at - result.started_at)
    # En recepcion, identificar_cliente ya actualizo el mapping en Mongo con el
    # debtor_id — el ws handler relee el mapping en el post-call.
    return result
