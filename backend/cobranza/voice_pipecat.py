"""
voice_pipecat.py — Pipecat-based voice agent for cobranza.

Ultra-low latency streaming pipeline:
  Twilio WebSocket → Deepgram Nova-3 STT → Groq Llama 3.1 70B LLM → Deepgram Aura-2 TTS → Twilio

All components stream in parallel. Target: <500ms TTFB.
"""
import logging
import os

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

logger = logging.getLogger("cobranza.pipecat")


async def run_bot(websocket, call_sid: str, debtor: dict, estrategia: dict):
    """
    Spawn a Pipecat pipeline for a single cobranza call.

    This replaces the entire manual pipeline (Assembly AI + OpenAI + Azure TTS)
    with a single streaming pipeline that handles everything.
    """
    import json as _json

    debtor_name = debtor.get("nombre", "señor o señora")
    monto = debtor.get("monto", 0)
    vencimiento = debtor.get("vencimiento", "desconocida")
    tono = estrategia.get("tono", "profesional")

    # ── Wait for Twilio start message to get stream_sid ──────────────────
    stream_sid = ""
    while True:
        raw = await websocket.receive_text()
        msg = _json.loads(raw)
        if msg.get("event") == "start":
            stream_sid = msg.get("start", {}).get("streamSid") or msg.get("streamSid", "")
            logger.info("[Pipecat] Got streamSid: %s", stream_sid)
            break
        elif msg.get("event") == "connected":
            logger.info("[Pipecat] Connected event received, waiting for start...")
            continue

    if not stream_sid:
        logger.error("[Pipecat] No streamSid found, cannot proceed")
        return

    # ── Camila system prompt (short = faster LLM) ────────────────────────
    system_prompt = (
        f"Eres Camila, cobradora colombiana de De Pe Ge Seguros. "
        f"Cálida, usa 'usted'. Frases MUY cortas (1 oración). Nunca suenes robot. "
        f"Deudor: {debtor_name}, debe ${monto:,.0f}, venció {vencimiento}. "
        f"Flujo: 1) confirma identidad 2) menciona el saldo 3) ofrece pago 4) despídete."
    )

    # ── Transport: Twilio WebSocket (WITHOUT VAD for now) ────────────────
    logger.info("[Pipecat] Creating transport (no VAD)...")
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            vad_enabled=False,
            serializer=TwilioFrameSerializer(
                stream_sid=stream_sid,
                call_sid=call_sid,
                account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
                auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            ),
        ),
    )

    # ── STT: Deepgram Nova-3 (streaming, ~300ms) ────────────────────────
    from pipecat.services.deepgram.stt import LiveOptions
    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        live_options=LiveOptions(
            model="nova-3",
            language="es",
            endpointing=300,
            interim_results=True,
            punctuate=True,
        ),
    )

    # ── LLM: OpenAI gpt-4o-mini (Chat Completions API compatible) ────────
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
        params=OpenAILLMService.InputParams(
            max_completion_tokens=80,
            temperature=0.7,
        ),
    )

    # ── TTS: Deepgram Aura-2 Celeste (Spanish, natural voice) ──────────────
    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        voice="aura-2-celeste-es",
    )

    # ── LLM Context (conversation memory) ────────────────────────────────
    messages = [{"role": "system", "content": system_prompt}]
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # ── Pipeline ─────────────────────────────────────────────────────────
    pipeline = Pipeline(
        [
            transport.input(),              # Twilio audio in
            stt,                            # Speech → text (streaming)
            context_aggregator.user(),      # Accumulate user transcript
            llm,                            # Think (streaming tokens)
            tts,                            # Text → speech (streaming)
            transport.output(),             # Audio → Twilio
            context_aggregator.assistant(), # Accumulate assistant response
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,       # User can interrupt Camila
            enable_metrics=True,
            report_only_initial_ttfb=True,
        ),
    )

    # ── Events ───────────────────────────────────────────────────────────
    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("[Pipecat] Connected — sending greeting")
        greeting = f"Aló, buenas tardes, será que hablo con {debtor_name}?"
        await task.queue_frames([TTSSpeakFrame(text=greeting)])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("[Pipecat] Disconnected")
        await task.queue_frames([EndFrame()])

    # ── Run ───────────────────────────────────────────────────────────────
    runner = PipelineRunner()
    logger.info("[Pipecat] Starting pipeline for call %s (debtor=%s)", call_sid, debtor_name)
    await runner.run(task)
    logger.info("[Pipecat] Pipeline finished for call %s", call_sid)
