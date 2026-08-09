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

from cobranza.voice_pipecat import CallResult

logger = logging.getLogger("cobranza.voice_agent")

DG_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"
THINK_MODEL = os.getenv("COBRANZA_AGENT_THINK_MODEL", "gemini-3.5-flash")


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
        from cobranza.voice_pipecat import documento_base
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

def _settings(prompt: str, greeting: str, voz: str, keyterms: list,
              modo_recepcion: bool) -> dict:
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "mulaw", "sample_rate": 8000},
            "output": {"encoding": "mulaw", "sample_rate": 8000, "container": "none"},
        },
        "agent": {
            # nova-3 (no nova-2): es el modelo del ejemplo oficial Twilio+Deepgram,
            # el mejor para acento/ruido. keyterms funciona con nova-3.
            "listen": {"provider": {"type": "deepgram", "model": "nova-3",
                                    "language": "es", "keyterms": keyterms}},
            "think": {"provider": {"type": "google", "model": THINK_MODEL},
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
    from cobranza.deepgram_pipecat_tts import keyterms_llamada
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

async def run_voice_agent(*, websocket, call_sid: str, debtor: dict, user_id: str,
                          stream_id: str, tenant_config: dict,
                          is_inbound: bool = False, modo_recepcion: bool = False) -> CallResult:
    """Puentea el media-stream de Twilio (ya aceptado) con el Voice Agent de
    Deepgram y devuelve el CallResult para el post-call. Nunca lanza hacia
    afuera: cualquier fallo cierra limpio con lo que se haya recolectado."""
    result = CallResult(call_sid=call_sid, started_at=time.time())
    from database import get_db
    db = get_db()

    prompt, greeting, keyterms = armar_prompt(debtor or {}, tenant_config,
                                              modo_recepcion=modo_recepcion)
    voz = str((tenant_config.get("cobranza") or {}).get("deepgram_voice")
              or tenant_config.get("deepgram_voice")
              or os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-celeste-es"))
    logger.info("[agent] call=%s recepcion=%s voz=%s think=%s keyterms=%d",
                call_sid, modo_recepcion, voz, THINK_MODEL, len(keyterms))
    from cobranza.cobranza_orchestrator import CobranzaOrchestrator
    # db=None: el orchestrator hace `db or get_db()` y bool(Database de motor)
    # revienta; get_db() devuelve el mismo singleton igual.
    orch = CobranzaOrchestrator(user_id, tenant_config) if user_id else None
    identificado = {"ok": not modo_recepcion}
    dispatch = _Dispatcher(db, user_id, debtor or {}, orch, call_sid,
                           result.transcript, identificado)

    key = os.getenv("DEEPGRAM_API_KEY", "")
    colgar = {"pedido": False}

    try:
        async with websockets.connect(
            DG_AGENT_URL, additional_headers={"Authorization": f"Token {key}"}
        ) as dg:
            await dg.send(json.dumps(_settings(prompt, greeting, voz, keyterms, modo_recepcion)))

            async def twilio_a_dg():
                async for raw in websocket.iter_text():
                    m = json.loads(raw)
                    ev = m.get("event")
                    if ev == "media":
                        await dg.send(base64.b64decode(m["media"]["payload"]))
                    elif ev == "dtmf":
                        # cedula por teclado en recepcion → turno de texto para el agente
                        dig = "".join(c for c in (m.get("dtmf") or {}).get("digit", "") if c.isdigit())
                        if dig:
                            await dg.send(json.dumps({"type": "InjectUserMessage",
                                                      "content": f"[TECLADO] {dig}"}))
                    elif ev == "stop":
                        return

            async def dg_a_twilio():
                async for msg in dg:
                    if isinstance(msg, bytes):
                        await websocket.send_json({"event": "media", "streamSid": stream_id,
                                                   "media": {"payload": base64.b64encode(msg).decode()}})
                        continue
                    ev = json.loads(msg)
                    t = ev.get("type")
                    if t == "UserStartedSpeaking":
                        # barge-in: limpia el audio del agente ya encolado en Twilio
                        await websocket.send_json({"event": "clear", "streamSid": stream_id})
                    elif t == "ConversationText":
                        who = "Deudor" if ev.get("role") == "user" else "ARIA"
                        result.transcript.append((time.time(), who, ev.get("content", "")))
                    elif t == "FunctionCallRequest":
                        for f in ev.get("functions", []):
                            # el Voice Agent manda arguments como STRING JSON
                            _a = f.get("arguments")
                            if isinstance(_a, str):
                                try:
                                    _a = json.loads(_a) if _a.strip() else {}
                                except json.JSONDecodeError:
                                    _a = {}
                            content = await dispatch(f.get("name", ""), _a or {})
                            dispatch.debtor = dispatch.debtor  # (identificar_cliente puede haberlo cambiado)
                            await dg.send(json.dumps({
                                "type": "FunctionCallResponse", "id": f.get("id"),
                                "name": f.get("name"),
                                "content": json.dumps(content, ensure_ascii=False)}))
                            if f.get("name") == "end_call":
                                colgar["pedido"] = True
                    elif t == "AgentAudioDone" and colgar["pedido"]:
                        await asyncio.sleep(1.5)   # deja salir la despedida
                        return
                    elif t == "Error":
                        logger.error("[agent] Deepgram Error: %s", ev)
                        return

            tareas = [asyncio.create_task(twilio_a_dg()), asyncio.create_task(dg_a_twilio())]
            try:
                await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for x in tareas:
                    x.cancel()
    except Exception:
        logger.exception("[agent] bridge fallo call=%s", call_sid)

    result.ended_at = time.time()
    result.duration_seconds = int(result.ended_at - result.started_at)
    # En recepcion, identificar_cliente ya actualizo el mapping en Mongo con el
    # debtor_id — el ws handler relee el mapping en el post-call (mismo camino
    # que el pipeline pipecat), asi que no hace falta devolver el deudor aqui.
    return result
