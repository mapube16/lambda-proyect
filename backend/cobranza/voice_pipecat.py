"""
voice_pipecat.py — Pipecat-based voice agent for cobranza.

OpenAI Realtime API pipeline (speech-to-speech, no separate STT/TTS):
  Twilio WebSocket -> OpenAI Realtime (STT+LLM+TTS all-in-one) -> Twilio

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
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.services.openai.realtime import events as rt_events
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

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


async def run_bot(websocket, call_sid: str, debtor: dict, estrategia: dict) -> CallResult:
    """
    Spawn a Pipecat pipeline using OpenAI Realtime API.
    Returns CallResult with transcript and duration for post-call processing.
    """
    import json as _json

    call_result = CallResult(call_sid=call_sid, started_at=time.time())

    debtor_name = debtor.get("nombre", "senor o senora")
    monto = debtor.get("monto", 0)
    vencimiento = debtor.get("vencimiento", "desconocida")

    logger.info("[VOICE] run_bot called: call_sid=%s, debtor=%s", call_sid, debtor_name)

    # ── Wait for Twilio start message to get stream_sid ──────────────────
    logger.info("[VOICE] Waiting for Twilio handshake...")
    stream_sid = ""
    msg_count = 0
    while True:
        try:
            raw = await websocket.receive_text()
        except Exception as e:
            logger.error("[VOICE] ERROR: receive_text failed: %s: %s", type(e).__name__, e)
            return call_result
        msg_count += 1
        msg = _json.loads(raw)
        event = msg.get("event")
        logger.info("[VOICE] Twilio msg #%d: event=%s", msg_count, event)
        if event == "start":
            start_data = msg.get("start", {})
            stream_sid = start_data.get("streamSid") or msg.get("streamSid", "")
            logger.info("[VOICE] Got streamSid=%s", stream_sid)
            break
        elif event == "connected":
            continue

    if not stream_sid:
        logger.error("[VOICE] ERROR: No streamSid, aborting")
        return call_result

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

    # ── Transport: Twilio WebSocket ──────────────────────────────────────
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=24000,
            audio_out_sample_rate=24000,
            vad_enabled=False,
            serializer=TwilioFrameSerializer(
                stream_sid=stream_sid,
                call_sid=call_sid,
                account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
                auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            ),
        ),
    )

    # ── Tool: end_call (LLM can hang up the call) ─────────────────────
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

    # ── OpenAI Realtime (STT + LLM + TTS all-in-one) ────────────────────
    llm = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAIRealtimeLLMService.Settings(
            model="gpt-4o-realtime-preview-2024-12-17",
            system_instruction=system_prompt,
            temperature=0.6,
            session_properties=rt_events.SessionProperties(
                audio=rt_events.AudioConfiguration(
                    output=rt_events.AudioOutput(voice="shimmer"),
                    input=rt_events.AudioInput(
                        transcription=rt_events.InputAudioTranscription(
                            model="whisper-1",
                            language="es",
                        ),
                        noise_reduction=rt_events.InputAudioNoiseReduction(type="near_field"),
                        turn_detection=rt_events.TurnDetection(
                            type="server_vad",
                            threshold=0.6,
                            prefix_padding_ms=400,
                            silence_duration_ms=800,
                        ),
                    ),
                ),
                tools=[end_call_tool],
            ),
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

    # ── Function call handler: end_call ────────────────────────────────
    async def _handle_end_call(params):
        reason = params.arguments.get("reason", "conversacion finalizada")
        logger.info("[VOICE] end_call invoked: reason=%s", reason)
        await params.result_callback({"status": "ending", "reason": reason})
        # Wait for the farewell TTS to finish playing before hanging up
        import asyncio
        await asyncio.sleep(4.0)
        # Hang up Twilio call
        try:
            from twilio.rest import Client
            twilio_client = Client(
                os.getenv("TWILIO_ACCOUNT_SID"),
                os.getenv("TWILIO_AUTH_TOKEN"),
            )
            twilio_client.calls(call_sid).update(status="completed")
            logger.info("[VOICE] Twilio call %s hung up", call_sid)
        except Exception as e:
            logger.error("[VOICE] Failed to hang up Twilio call: %s", e)
        await task.queue_frames([EndFrame()])

    # cancel_on_interruption=False → user talking during goodbye won't cancel the hangup
    llm.register_function("end_call", _handle_end_call, cancel_on_interruption=False)

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
