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
    system_prompt = (
        f"Eres Camila, asesora de cobranza colombiana de De Pe Ge Seguros. "
        f"Tu tono es suave, tranquilo y {tono}. Nunca suenas apurada ni agresiva. "
        f"Habla despacio y con calma, como si tuvieras todo el tiempo del mundo. "
        f"Usa 'usted' siempre. "
        f"ESTILO: "
        f"- Frases cortas, maximo 1 oracion por turno. "
        f"- Muletillas colombianas suaves: 'aja', 'listo', 'que pena', 'mire', 'claro'. "
        f"- Se empatica: 'entiendo', 'yo le ayudo', 'no se preocupe', 'tranquilo'. "
        f"- Di los numeros natural: 'quinientos mil pesitos' no '500,000 pesos'. "
        f"- Si el deudor esta molesto, baja el tono y se comprensiva. "
        f"Datos: {debtor_name}, debe {monto:,.0f} pesos, vencio {vencimiento}. "
        f"Flujo: 1) saluda calmadamente y confirma identidad 2) menciona el saldo "
        f"3) ofrece opciones de pago 4) despidete amablemente. "
        f"Empieza con un saludo tranquilo preguntando si hablas con {debtor_name}."
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

    # ── OpenAI Realtime (STT + LLM + TTS all-in-one) ────────────────────
    llm = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAIRealtimeLLMService.Settings(
            model="gpt-4o-mini-realtime-preview-2024-12-17",
            system_instruction=system_prompt,
            temperature=0.8,
            session_properties=rt_events.SessionProperties(
                audio=rt_events.AudioConfiguration(
                    output=rt_events.AudioOutput(voice="coral"),
                    input=rt_events.AudioInput(
                        transcription=rt_events.InputAudioTranscription(
                            model="whisper-1",
                            language="es",
                        ),
                        noise_reduction=rt_events.InputAudioNoiseReduction(type="near_field"),
                        turn_detection=rt_events.TurnDetection(
                            type="server_vad",
                            threshold=0.5,
                            prefix_padding_ms=300,
                            silence_duration_ms=500,
                        ),
                    ),
                ),
            ),
        ),
    )

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

    # ── Events ───────────────────────────────────────────────────────────
    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("[VOICE] EVENT: on_client_connected")
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
