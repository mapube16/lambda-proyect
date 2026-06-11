"""
voice_pipecat.py — Pipecat-based voice agent for cobranza.

Telnyx + Gemini Live pipeline (speech-to-speech, no separate STT/TTS):
  Telnyx WebSocket -> Gemini Live (STT+LLM+TTS all-in-one) -> Telnyx

Audio: 8kHz PCMU (telephony standard — NOT 24kHz which is WebRTC standard).
Prompt: hot-reloaded from tenant_configs via Redis cache (5-min TTL).
Tools: end_call, update_debtor, send_whatsapp, verify_identity, escalate.

Target: <500ms TTFB.
"""
import logging
import os
import time
from dataclasses import dataclass, field

from pipecat.frames.frames import (
    EndFrame,
    LLMContextFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from cobranza.config_cache import get_tenant_config
from cobranza.cobranza_orchestrator import CobranzaOrchestrator

logger = logging.getLogger("cobranza.pipecat")


@dataclass
class CallResult:
    """Data collected during the call for post-call processing."""
    call_sid: str = ""
    duration_seconds: int = 0
    transcript: list = field(default_factory=list)  # [(timestamp, speaker, text)]
    started_at: float = 0.0
    ended_at: float = 0.0
    _bot_buffer: str = field(default="", repr=False)
    _bot_buffer_ts: float = field(default=0.0, repr=False)

    def flush_bot_buffer(self):
        """Flush accumulated bot tokens into a single transcript entry."""
        if self._bot_buffer.strip():
            self.transcript.append((self._bot_buffer_ts, "Camila", self._bot_buffer.strip()))
            self._bot_buffer = ""

    @property
    def full_transcript(self) -> str:
        self.flush_bot_buffer()
        lines = []
        for _, speaker, text in sorted(self.transcript, key=lambda x: x[0]):
            lines.append(f"{speaker}: {text}")
        return "\n".join(lines)

    @property
    def user_turn_count(self) -> int:
        return sum(1 for _, speaker, _ in self.transcript if speaker == "Deudor")


class TranscriptCollector(FrameProcessor):
    """Lightweight processor that captures transcription and TTS text frames."""

    def __init__(self, call_result: CallResult, **kwargs):
        super().__init__(**kwargs)
        self._result = call_result

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text:
            # User spoke — flush any pending bot text first
            self._result.flush_bot_buffer()
            self._result.transcript.append((time.time(), "Deudor", frame.text))
        elif isinstance(frame, TTSTextFrame) and frame.text:
            # Bot token — accumulate into buffer
            if not self._result._bot_buffer:
                self._result._bot_buffer_ts = time.time()
            self._result._bot_buffer += frame.text
        await self.push_frame(frame, direction)


async def run_bot(
    websocket,
    call_sid: str,
    debtor: dict,
    estrategia: dict,
    user_id: str = "",
    stream_id: str = "",
    call_control_id: str = "",
) -> CallResult:
    """
    Spawn a Pipecat pipeline using Telnyx transport + Gemini Live LLM.

    Args:
        websocket: Already-accepted FastAPI WebSocket.
        call_sid: Telnyx call_control_id (kept as call_sid for backward compat).
        debtor: Debtor document dict.
        estrategia: Cobranza strategy dict.
        user_id: Tenant user_id for config hot-reload and orchestrator isolation.
        stream_id: Telnyx stream_id from WebSocket handshake.
        call_control_id: Telnyx call_control_id for hang-up via TelnyxFrameSerializer.

    Returns:
        CallResult with transcript and duration for post-call processing.
    """
    call_result = CallResult(call_sid=call_sid, started_at=time.time())

    debtor_name = debtor.get("nombre", "senor o senora")
    monto = debtor.get("monto", 0)
    vencimiento = debtor.get("vencimiento", "desconocida")

    logger.info("[VOICE] run_bot called: call_sid=%s, debtor=%s, user_id=%s", call_sid, debtor_name, user_id)

    # ── Hot-reload: tenant config from Redis cache (5-min TTL) ──────────
    tenant_config: dict = {}
    if user_id:
        try:
            tenant_config = await get_tenant_config(user_id)
        except Exception as _cfg_err:
            logger.warning("[VOICE] Could not load tenant_config for %s: %s", user_id, _cfg_err)

    # Guard: voice module disabled → close socket before pipeline starts
    if not tenant_config.get("modules", {}).get("voice", True):
        logger.info("[VOICE] modules.voice=false for user %s — closing socket (1008)", user_id)
        await websocket.close(1008, "Voice module disabled")
        return CallResult()

    # ── Camila system prompt ─────────────────────────────────────────────
    tono = estrategia.get("tono", "amable")

    # Format monto naturally for speech
    if monto >= 1_000_000:
        monto_natural = f"{monto / 1_000_000:.0f} millones" if monto % 1_000_000 == 0 else f"{monto / 1_000_000:.1f} millones de pesitos".rstrip('0').rstrip('.')
    elif monto >= 1_000:
        monto_natural = f"{monto / 1_000:.0f} mil pesitos" if monto % 1_000 == 0 else f"{monto / 1_000:.1f} mil pesitos".rstrip('0').rstrip('.')
    else:
        monto_natural = f"{monto:.0f} pesitos"

    # Format vencimiento naturally
    if hasattr(vencimiento, 'strftime'):
        vencimiento_str = vencimiento.strftime("%d de %B")
    else:
        vencimiento_str = str(vencimiento)

    system_prompt = (
        f"Eres Camila, asesora de cobranza de De Pe Ge Seguros. Colombiana, de Bogota. "
        f"Tienes 28 anios, llevas 4 anios en la empresa. Eres una persona real, no un robot. "
        f"Tu tono es {tono}, cercano, como si hablaras con un vecino. "
        f"\n\n"
        f"PERSONALIDAD Y VOZ:\n"
        f"- Hablas en espaniol colombiano natural. Usas 'usted' pero de forma cercana, no rigida.\n"
        f"- Frases CORTAS. Maximo 1-2 oraciones por turno. Como en una conversacion real por telefono.\n"
        f"- Muletillas naturales: 'aja', 'listo', 'mire', 'claro', 'si senor', 'que pena con usted', 'no, tranquilo'.\n"
        f"- Pausas naturales: '...', 'mmm', 'a ver'. NO hables como un guion leido.\n"
        f"- Numeros naturales: 'quinientos mil pesitos', 'un millon doscientos', NO '500,000 pesos'.\n"
        f"- Respuestas cortas cuando el otro habla: 'aja', 'si claro', 'entiendo', 'listo'. Escucha mas de lo que hablas.\n"
        f"- NUNCA repitas el mismo argumento dos veces con las mismas palabras.\n"
        f"\n\n"
        f"DATOS DE ESTA LLAMADA:\n"
        f"- Nombre: {debtor_name}\n"
        f"- Deuda: {monto_natural}\n"
        f"- Vencimiento: {vencimiento_str}\n"
        f"\n\n"
        f"FLUJO DE LA CONVERSACION:\n"
        f"1. Tu primer mensaje ya fue enviado (un saludo corto confirmando identidad). Espera la respuesta.\n"
        f"2. Si confirma que es el/ella: presenta el motivo con tacto. NO sueltes el monto de una. "
        f"   Ejemplo: 'Mire, le cuento, lo llamo porque tiene un saldito pendiente con nosotros...'\n"
        f"3. Menciona el monto solo si el deudor pregunta o despues de que acepte escuchar.\n"
        f"4. Ofrece opciones: pago completo, acuerdo de pago, o que lo llamen despues.\n"
        f"5. Si acepta algo: confirma y agradece. 'Listo, perfecto, entonces quedamos asi.'\n"
        f"6. Despidete corto y llama end_call.\n"
        f"\n\n"
        f"MANEJO DE OBJECIONES (muy importante):\n"
        f"- 'No tengo plata' → 'Entiendo, y por eso mismo lo llamo, para mirar como le podemos ayudar. "
        f"Podemos hacer un acuerdo de pago a cuotas, que le queda mas comodo?'\n"
        f"- 'Ya pague' → 'Ah listo, que pena. Dejeme verificar, puede ser que no se haya registrado aun. "
        f"Tiene a mano el comprobante?'\n"
        f"- 'No me interesa' / 'No quiero' → Intenta UNA sola vez con empatia: "
        f"'Entiendo, pero mire que si dejamos pasar mas tiempo puede generar intereses. "
        f"Le conviene que lo miremos ahora.' Si insiste, respeta su decision.\n"
        f"- 'Quien es usted?' / desconfianza → 'Claro, con toda razon. Soy Camila de De Pe Ge Seguros. "
        f"Si quiere puede verificar llamando al numero que aparece en su poliza.'\n"
        f"- Groserías o enojo → NO te alteres. Baja el tono: 'Entiendo que es una situacion incomoda, "
        f"no es mi intencion molestarlo. Si prefiere lo llamamos en otro momento.'\n"
        f"\n\n"
        f"CUANDO COLGAR — usa la funcion end_call (OBLIGATORIO):\n"
        f"Tienes una funcion llamada 'end_call'. DEBES usarla para terminar la llamada.\n"
        f"Despues de decir tu despedida, SIEMPRE llama a end_call. Situaciones:\n"
        f"- El deudor dice 'no me llame mas', 'no me vuelva a llamar', 'dejeme en paz', "
        f"o cualquier variante → di tu despedida y llama end_call.\n"
        f"- El deudor se despide o dice 'chao', 'adios', 'gracias' → despidete y llama end_call.\n"
        f"- Ya lograste el objetivo (promesa de pago o acuerdo) → confirma, despidete y llama end_call.\n"
        f"- El deudor esta grosero y no quiere hablar → despidete corto y llama end_call.\n"
        f"- Maximo 3-4 minutos de llamada. Si no avanzas, ofrece llamar otro dia, despidete y llama end_call.\n"
        f"- NUNCA sigas hablando despues de despedirte. Despedida → end_call, siempre.\n"
        f"\n\n"
        f"PROHIBIDO:\n"
        f"- Amenazar, presionar agresivamente, o mentir.\n"
        f"- Compartir datos con terceros. Si contesta alguien que no es el deudor, NO menciones la deuda.\n"
        f"- Llamar fuera de horario (7am-7pm).\n"
        f"- Sonar como robot o leer un guion. Eres una persona real teniendo una conversacion."
    )

    # ── Hot-reload override: use tenant voice_system_prompt if configured ─
    # string.replace() only — NO template engine (locked decision Phase 25)
    tenant_prompt = tenant_config.get("voice_system_prompt", "")
    if tenant_prompt:
        # Cap to 2000 chars (T-25-06 threat mitigation — written with Pydantic max_length at 25-05)
        brand_name = tenant_config.get("brand_name", "nuestra empresa")
        system_prompt = tenant_prompt[:2000]
        system_prompt = system_prompt.replace("{brand_name}", brand_name)
        system_prompt = system_prompt.replace("{debtor_name}", debtor.get("nombre", ""))
        logger.info("[VOICE] Using tenant voice_system_prompt for user %s", user_id)

    # ── Transport: Telnyx WebSocket (8kHz PCMU — telephony standard) ────
    # CRITICAL: audio_in/out_sample_rate=8000 (NOT 24000 which is WebRTC).
    # TelnyxFrameSerializer with api_key handles hang-up automatically via EndFrame.
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            vad_enabled=False,
            serializer=TelnyxFrameSerializer(
                stream_id=stream_id or call_sid,
                outbound_encoding="PCMU",
                inbound_encoding="PCMU",
                call_control_id=call_control_id or call_sid,
                api_key=os.getenv("TELNYX_API_KEY", ""),
            ),
        ),
    )

    # ── Tool schemas for Gemini function calling ─────────────────────────
    end_call_tool = {
        "type": "function",
        "name": "end_call",
        "description": (
            "Termina la llamada. Usa esta funcion SIEMPRE que la conversacion deba finalizar: "
            "cuando el deudor dice que no quiere hablar mas, cuando ya se llego a un acuerdo, "
            "cuando te despides, o cuando el deudor pide que no lo llamen mas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Motivo breve de por que se termina la llamada",
                },
            },
            "required": ["reason"],
        },
    }

    update_debtor_tool = {
        "type": "function",
        "name": "update_debtor",
        "description": "Actualiza el estado o campos del deudor en la base de datos.",
        "parameters": {
            "type": "object",
            "properties": {
                "debtor_id": {"type": "string", "description": "ID del deudor"},
                "estado": {
                    "type": "string",
                    "description": "Nuevo estado: promesa_de_pago, contactado, sin_contacto, escalado",
                },
            },
            "required": ["debtor_id", "estado"],
        },
    }

    send_whatsapp_tool = {
        "type": "function",
        "name": "send_whatsapp",
        "description": "Envia un mensaje de WhatsApp al deudor con informacion de pago o seguimiento.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Numero de telefono con codigo de pais"},
                "message": {"type": "string", "description": "Contenido del mensaje de WhatsApp"},
            },
            "required": ["phone", "message"],
        },
    }

    verify_identity_tool = {
        "type": "function",
        "name": "verify_identity",
        "description": "Verifica si la persona que contesto el telefono es el deudor esperado.",
        "parameters": {
            "type": "object",
            "properties": {
                "utterance": {
                    "type": "string",
                    "description": "Lo que dijo la persona al contestar",
                },
                "debtor_name": {
                    "type": "string",
                    "description": "Nombre del deudor esperado",
                },
            },
            "required": ["utterance"],
        },
    }

    escalate_tool = {
        "type": "function",
        "name": "escalate",
        "description": "Escala el caso a un asesor humano cuando el deudor tiene una situacion especial.",
        "parameters": {
            "type": "object",
            "properties": {
                "debtor_id": {"type": "string", "description": "ID del deudor"},
                "reason": {"type": "string", "description": "Motivo de la escalacion"},
            },
            "required": ["debtor_id", "reason"],
        },
    }

    # ── Gemini Live (STT + LLM + TTS all-in-one, 8kHz telephony) ────────
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        system_instruction=system_prompt,
        tools=[end_call_tool, update_debtor_tool, send_whatsapp_tool, verify_identity_tool, escalate_tool],
        params=GeminiLiveLLMService.InputParams(
            voice_id="Charon",
            language_code="es-419",
        ),
    )

    # ── First greeting (spoken as TTS, not LLM-generated) ─────────────
    import random
    first_name = debtor_name.split()[0] if debtor_name and debtor_name != "senor o senora" else ""
    if first_name:
        greetings = [
            f"Aló... buenas tardes. ¿Hablo con {first_name}?",
            f"Buenas tardes... ¿{first_name}?",
            f"Aló, buenas tardes. ¿Será que hablo con {first_name}?",
            f"Hola, buenas tardes... ¿estoy hablando con {first_name}?",
        ]
    else:
        greetings = [
            "Aló... buenas tardes. ¿Con quién tengo el gusto?",
            "Buenas tardes... ¿con quién hablo?",
            "Aló, buenas tardes. ¿Quién me contesta?",
        ]
    first_message = random.choice(greetings)

    # ── LLM Context ─────────────────────────────────────────────────────
    messages = [{"role": "system", "content": system_prompt}]
    context = LLMContext(messages)

    # ── Transcript collectors ────────────────────────────────────────────
    # user_collector: before LLM — catches TranscriptionFrames (upstream from LLM)
    # bot_collector: after LLM — catches TTSTextFrames (downstream from LLM)
    user_collector = TranscriptCollector(call_result, name="user_collector")
    bot_collector = TranscriptCollector(call_result, name="bot_collector")

    # ── Pipeline ─────────────────────────────────────────────────────────
    pipeline = Pipeline(
        [
            transport.input(),
            user_collector,
            llm,
            bot_collector,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            report_only_initial_ttfb=True,
        ),
    )

    # ── Function call handlers ─────────────────────────────────────────

    # Instantiate orchestrator once for this call (all handlers share it)
    orchestrator = CobranzaOrchestrator(user_id=user_id, tenant_config=tenant_config) if user_id else None

    async def _handle_end_call(params):
        """end_call: TelnyxFrameSerializer + api_key handles hang-up via EndFrame."""
        reason = params.arguments.get("reason", "conversacion finalizada")
        logger.info("[VOICE] end_call invoked: reason=%s", reason)
        await params.result_callback({"status": "ending", "reason": reason})
        # Allow farewell TTS to play before disconnect
        import asyncio
        await asyncio.sleep(4.0)
        # TelnyxFrameSerializer with api_key automatically signals hang-up on EndFrame
        await task.queue_frames([EndFrame()])

    async def _handle_update_debtor(params):
        """update_debtor: patch debtor estado/fields via CobranzaOrchestrator."""
        debtor_id = params.arguments.get("debtor_id", "")
        estado = params.arguments.get("estado", "")
        logger.info("[VOICE] update_debtor: debtor_id=%s estado=%s", debtor_id, estado)
        result = {"ok": False, "error": "orchestrator unavailable"}
        if orchestrator and debtor_id:
            try:
                result = await orchestrator.update_debtor(debtor_id, {"estado": estado})
            except Exception as exc:
                logger.error("[VOICE] update_debtor error: %s", exc)
                result = {"ok": False, "error": str(exc)[:100]}
        await params.result_callback(result)

    async def _handle_send_whatsapp(params):
        """send_whatsapp: enqueue WhatsApp message via CobranzaOrchestrator."""
        phone = params.arguments.get("phone", "")
        message = params.arguments.get("message", "")
        logger.info("[VOICE] send_whatsapp: phone=%s", phone)
        result = {"ok": False, "error": "orchestrator unavailable"}
        if orchestrator and phone:
            try:
                result = await orchestrator.send_whatsapp(phone, message)
            except Exception as exc:
                logger.error("[VOICE] send_whatsapp error: %s", exc)
                result = {"ok": False, "error": str(exc)[:100]}
        await params.result_callback(result)

    async def _handle_verify_identity(params):
        """verify_identity: regex + LLM fallback identity check."""
        utterance = params.arguments.get("utterance", "")
        debtor_name_arg = params.arguments.get("debtor_name", debtor_name)
        logger.info("[VOICE] verify_identity: utterance=%s", utterance[:50])
        result = {"confirmed": False, "confidence": "low"}
        if orchestrator and utterance:
            try:
                result = await orchestrator.verify_identity(utterance, debtor_name_arg)
            except Exception as exc:
                logger.error("[VOICE] verify_identity error: %s", exc)
                result = {"confirmed": False, "error": str(exc)[:100]}
        await params.result_callback(result)

    async def _handle_escalate(params):
        """escalate: mark debtor escalado and notify dashboard."""
        debtor_id = params.arguments.get("debtor_id", "")
        reason = params.arguments.get("reason", "escalado por agente")
        logger.info("[VOICE] escalate: debtor_id=%s reason=%s", debtor_id, reason)
        result = {"ok": False, "error": "orchestrator unavailable"}
        if orchestrator and debtor_id:
            try:
                result = await orchestrator.escalate(debtor_id, reason)
            except Exception as exc:
                logger.error("[VOICE] escalate error: %s", exc)
                result = {"ok": False, "error": str(exc)[:100]}
        await params.result_callback(result)

    # cancel_on_interruption=False → user talking during goodbye won't cancel the hangup
    llm.register_function("end_call", _handle_end_call, cancel_on_interruption=False)
    llm.register_function("update_debtor", _handle_update_debtor)
    llm.register_function("send_whatsapp", _handle_send_whatsapp)
    llm.register_function("verify_identity", _handle_verify_identity)
    llm.register_function("escalate", _handle_escalate)

    # ── Events ───────────────────────────────────────────────────────────
    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("[VOICE] EVENT: on_client_connected — expected greeting: %s", first_message)
        # Inject a user message that triggers the LLM to speak the greeting
        context.messages.append({
            "role": "user",
            "content": f"[La llamada acaba de conectar. Di EXACTAMENTE esto y nada mas: '{first_message}']",
        })
        await task.queue_frames([LLMContextFrame(context=context)])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("[VOICE] EVENT: on_client_disconnected")
        await task.queue_frames([EndFrame()])

    # ── Run ───────────────────────────────────────────────────────────────
    logger.info("[VOICE] Starting pipeline for call %s...", call_sid)
    try:
        runner = PipelineRunner()
        await runner.run(task)
        logger.info("[VOICE] Pipeline finished OK for call %s", call_sid)
    except Exception as e:
        logger.error("[VOICE] ERROR in pipeline: %s: %s", type(e).__name__, e, exc_info=True)

    call_result.ended_at = time.time()
    call_result.duration_seconds = int(call_result.ended_at - call_result.started_at)
    logger.info("[VOICE] Call %s: duration=%ds, turns=%d", call_sid, call_result.duration_seconds, len(call_result.transcript))

    return call_result
