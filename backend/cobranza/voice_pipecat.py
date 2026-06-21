"""
voice_pipecat.py — Pipecat-based voice agent for cobranza.

Twilio + Gemini Live pipeline (speech-to-speech, no separate STT/TTS):
  Twilio WebSocket -> Gemini Live (STT+LLM+TTS all-in-one) -> Twilio

Audio: 8kHz PCMU (telephony standard — NOT 24kHz which is WebRTC standard).
Prompt: hot-reloaded from tenant_configs via Redis cache (5-min TTL).
Tools: end_call, update_debtor, send_whatsapp, verify_identity, escalate.

Target: <500ms TTFB.
"""
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from pipecat.frames.frames import (
    EndFrame,
    LLMContextFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.llm_service import FunctionCallResultProperties
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
            self.transcript.append((self._bot_buffer_ts, "ARIA", self._bot_buffer.strip()))
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

    # ── Latency instrumentation: log ms between each startup stage so we can see
    # EXACTLY what's slow between WS-connect and first audio. _t0 = run_bot entry.
    _t0 = time.perf_counter()
    def _lap(stage: str):
        logger.info("[LATENCY] %s: +%.0f ms (call %s)", stage, (time.perf_counter() - _t0) * 1000, call_sid)

    # ── Preload tenant config + RAG precheck IN PARALLEL (latency) ──────
    # These two reads (Redis tenant_config + Mongo rag_documents count) are
    # independent and were the measured ~2s of dead air before the bot could
    # greet (run_bot -> "Starting pipeline"). Running them concurrently collapses
    # that to a single round-trip. The RAG precheck lets search_knowledge skip
    # Pinecone (~5-7s) when the tenant has no documents.
    import asyncio as _asyncio

    async def _load_tenant_config():
        if not user_id:
            return {}
        try:
            return await get_tenant_config(user_id)
        except Exception as _cfg_err:
            logger.warning("[VOICE] Could not load tenant_config for %s: %s", user_id, _cfg_err)
            return {}

    async def _load_rag_flag():
        if not user_id:
            return False
        try:
            from database import get_db
            _db = get_db()
            return (await _db.rag_documents.count_documents({"user_id": user_id}, limit=1)) > 0
        except Exception as _rag_err:
            logger.warning("[VOICE] rag_documents precheck failed for %s: %s", user_id, _rag_err)
            return True  # fail-open: don't block real KB lookups

    tenant_config, tenant_has_rag_docs = await _asyncio.gather(
        _load_tenant_config(), _load_rag_flag()
    )
    _lap("config+rag loaded")

    # Guard: voice module disabled → close socket before pipeline starts
    if not tenant_config.get("modules", {}).get("voice", True):
        logger.info("[VOICE] modules.voice=false for user %s — closing socket (1008)", user_id)
        await websocket.close(1008, "Voice module disabled")
        return CallResult()

    # ── ARIA system prompt ───────────────────────────────────────────────
    tono = estrategia.get("tono", "amable")

    # First name for the in-prompt example molde (the spoken greeting computes
    # its own `first_name` later; this is just for the prompt's example frase).
    first_name_for_prompt = (
        debtor_name.split()[0]
        if debtor_name and debtor_name != "senor o senora"
        else ""
    )

    # Format monto naturally for speech. The old "{monto/1000:.1f} mil" math
    # produced absurd "962.0 mil pesos" for 962036. Spell the whole integer in
    # Spanish words so Gemini reads it correctly ("novecientos sesenta y dos mil
    # pesos") — no diminutives, no decimals.
    from cobranza.es_numbers import pesos_en_palabras
    monto_natural = pesos_en_palabras(monto)

    # Format vencimiento naturally
    if hasattr(vencimiento, 'strftime'):
        vencimiento_str = vencimiento.strftime("%d de %B")
    else:
        vencimiento_str = str(vencimiento)

    # ── Policy data injected straight into the prompt (latency) ──────────
    # The debtor dict is already in memory; inlining its policy fields here means
    # the model can answer "¿cuánto debo?", "¿qué tengo?", "¿cuándo vence?"
    # WITHOUT a get_policy_info round-trip (which added ~0.7s of dead air on the
    # most common question). This scales fine: it's ONE debtor per call (~250
    # tokens, constant size), never accumulates. get_policy_info stays registered
    # as a fallback for edge cases. General company knowledge is NOT inlined — that
    # grows unbounded and stays in RAG/search_knowledge.
    def _p_money(v):
        try:
            return f"{int(float(v)):,}".replace(",", ".") if v is not None else None
        except (TypeError, ValueError):
            return None

    def _p_date(v):
        return str(v)[:10] if v else None

    _tipo_poliza = debtor.get("ramo_nombre") or debtor.get("ramo_global_nombre")
    _ramo = debtor.get("ramo_global_nombre") or debtor.get("ramo_nombre")
    _policy_lines = []
    if _tipo_poliza:
        _policy_lines.append(f"- Tipo de poliza: {_tipo_poliza}" + (f" (ramo: {_ramo})" if _ramo and _ramo != _tipo_poliza else ""))
    if debtor.get("aseguradora_nombre"):
        _policy_lines.append(f"- Compania aseguradora: {debtor.get('aseguradora_nombre')}")
    if debtor.get("objeto_asegurado"):
        _policy_lines.append(f"- Riesgo asegurado (placa/inmueble/objeto): {debtor.get('objeto_asegurado')}")
    if debtor.get("forma_pago_texto"):
        _policy_lines.append(f"- Modalidad de pago: {debtor.get('forma_pago_texto')}")
    if debtor.get("numero_de_cuotas"):
        _policy_lines.append(f"- Numero de cuotas: {debtor.get('numero_de_cuotas')}")
    if debtor.get("numero_poliza"):
        _policy_lines.append(f"- Numero de poliza: {debtor.get('numero_poliza')}")
    if debtor.get("estado_cartera"):
        _policy_lines.append(f"- Estado de cartera: {debtor.get('estado_cartera')}")
    if debtor.get("estado_poliza_nombre"):
        _policy_lines.append(f"- Estado de la poliza: {debtor.get('estado_poliza_nombre')}")
    if _p_money(debtor.get("prima")):
        _policy_lines.append(f"- Prima total: {_p_money(debtor.get('prima'))} pesos")
    if _p_money(debtor.get("total_pagado")):
        _policy_lines.append(f"- Total pagado: {_p_money(debtor.get('total_pagado'))} pesos")
    if _p_date(debtor.get("fecha_limite_pago")):
        _policy_lines.append(f"- Fecha limite de pago: {_p_date(debtor.get('fecha_limite_pago'))}")
    if _p_date(debtor.get("fecha_fin")):
        _policy_lines.append(f"- Vigencia hasta: {_p_date(debtor.get('fecha_fin'))}")
    if debtor.get("periodicidad"):
        _policy_lines.append(f"- Periodicidad: {debtor.get('periodicidad')}")
    if debtor.get("vendedores_nombre"):
        _policy_lines.append(f"- Asesor asignado: {debtor.get('vendedores_nombre')}")
    _policy_block = ("\n".join(_policy_lines) + "\n") if _policy_lines else ""

    # ── 3-layer prompt assembly (multi-tenant) ──────────────────────────────
    # LAYER 1 (engine) lives in prompt_builder; LAYER 2 (persona) comes from the
    # tenant config in Mongo (voice_persona), falling back to a generic default;
    # LAYER 3 (runtime) is THIS debtor's data, built here as runtime_block.
    from cobranza.prompt_builder import (
        resolve_persona, render_greeting, assemble_system_prompt,
    )

    runtime_block = (
        "DATOS DE ESTA LLAMADA (datos REALES y exactos de ESTE deudor — usalos directo, "
        "NO necesitas consultar ninguna herramienta para responder sobre su poliza, "
        "saldo o fechas; ya los tienes aqui):\n"
        f"- Nombre: {debtor_name}\n"
        f"- Deuda pendiente: {monto_natural}\n"
        f"- Vencimiento: {vencimiento_str}\n"
        f"{_policy_block}"
        "\n"
    )

    persona = resolve_persona(tenant_config)
    # tono persisted at the top level of estrategia still wins if the persona
    # didn't set one (back-compat with existing cobranza_config.estrategia.tono).
    if not (tenant_config.get("voice_persona") or {}).get("tono"):
        persona["tono"] = tono

    system_prompt = assemble_system_prompt(
        persona,
        runtime_block=runtime_block,
        first_name=first_name_for_prompt,
        ramo=_tipo_poliza or _ramo or "seguros",
        monto_natural=monto_natural,
        aseguradora=debtor.get("aseguradora_nombre") or "",
    )
    logger.info(
        "[VOICE] Assembled 3-layer prompt for user %s (persona=%s, %d chars)",
        user_id, persona.get("agent_name"), len(system_prompt),
    )
    _lap("prompt assembled")

    # ── Transport: Twilio WebSocket ────────────────────────────────────
    # Silero VAD here handles user-speech interruptions. Gemini's OWN native
    # VAD is DISABLED (see llm params) because on a phone line it self-fires
    # Turn-taking is owned entirely by Gemini's native VAD (see llm params).
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            # Inbound 8kHz µ-law (Twilio wire), outbound 24kHz (Gemini TTS);
            # the serializer bridges both. `sample_rate` override omitted so the
            # pipeline input stays 8kHz. Pipecat resamples 8k->24k into Gemini.
            #
            # NO Silero VAD here. Turn-taking is owned exclusively by Gemini's
            # native VAD (configured below). Running BOTH made them fight: Silero
            # would mark a turn while Gemini disagreed, and disabling Gemini's VAD
            # to compensate left no one telling Gemini the caller had finished —
            # so it greeted once and never responded.
            audio_in_sample_rate=8000,
            audio_out_sample_rate=24000,
            serializer=TwilioFrameSerializer(
                stream_sid=stream_id or call_sid,
                call_sid=call_sid,
                account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
                auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
                params=TwilioFrameSerializer.InputParams(
                    twilio_sample_rate=8000,
                ),
            ),
        ),
    )

    _lap("transport created")

    # ── Tool schemas for Gemini function calling (Pipecat FunctionSchema) ──
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    end_call_tool = FunctionSchema(
        name="end_call",
        description=(
            "Termina la llamada. Usa esta funcion SIEMPRE que la conversacion deba finalizar: "
            "cuando el deudor dice que no quiere hablar mas, cuando ya se llego a un acuerdo, "
            "cuando te despides, o cuando el deudor pide que no lo llamen mas."
            "cuando pide hablar con un humano (despues de llamar escalate), o cuando la conversacion se vuelve improductiva o el deudor se enoja."
        ),
        properties={
            "reason": {"type": "string", "description": "Motivo breve de por que se termina la llamada"},
        },
        required=["reason"],
    )

    update_debtor_tool = FunctionSchema(
        name="update_debtor",
        description="Actualiza el estado o campos del deudor en la base de datos.",
        properties={
            "debtor_id": {"type": "string", "description": "ID del deudor"},
            "estado": {"type": "string", "description": "Nuevo estado: promesa_de_pago, contactado, sin_contacto, escalado"},
        },
        required=["debtor_id", "estado"],
    )

    send_whatsapp_tool = FunctionSchema(
        name="send_whatsapp",
        # SECURITY: the model does NOT choose the recipient. We always send to
        # the debtor's real phone from MongoDB — never a number the model
        # invents (it once hallucinated +573001234567). Only `message` is
        # model-supplied.
        description=(
            "Envia un mensaje de WhatsApp AL DEUDOR (al numero registrado) con "
            "informacion de pago o seguimiento. El destinatario es siempre el "
            "deudor; tu solo escribes el contenido del mensaje."
        ),
        properties={
            "message": {"type": "string", "description": "Contenido del mensaje de WhatsApp para el deudor"},
        },
        required=["message"],
    )

    # NOTE: scoped tightly to avoid latency. If the person answers to their
    # name ("si", "soy yo", "con el habla") or asks about THEIR debt, identity
    # is implicitly confirmed — answer directly, do NOT call this (it costs
    # ~2s via LLM fallback and stalls the conversation).
    verify_identity_tool = FunctionSchema(
        name="verify_identity",
        description=(
            "USO RARISIMO. Llamala UNICAMENTE si la persona dice EXPLICITAMENTE que "
            "NO es el deudor: 'el no esta', 'numero equivocado', 'se equivoco', o da "
            "OTRO nombre distinto. "
            "NUNCA la llames por un simple saludo ('alo', 'si', 'bueno', 'hola', 'a ver', "
            "'diga') — eso es solo contestar el telefono, NO es motivo de verificacion. "
            "NUNCA la llames si la persona responde a su nombre, dice 'soy yo', o pregunta "
            "por su deuda. En TODOS esos casos la identidad ya esta confirmada: saluda y "
            "continua normal. Ante la duda, NO la llames."
        ),
        properties={
            "utterance": {"type": "string", "description": "Lo que dijo la persona al contestar"},
            "debtor_name": {"type": "string", "description": "Nombre del deudor esperado"},
        },
        required=["utterance"],
    )

    escalate_tool = FunctionSchema(
        name="escalate",
        description=(
            "Escala el caso a un asesor humano. Usala SIEMPRE que el deudor pida "
            "hablar con una persona, un humano, un asesor, un agente, o 'alguien "
            "de verdad' — o cuando tenga una situacion especial que tu no puedas "
            "resolver (disputa del monto, reclamo legal, caso de salud). Despues "
            "de llamarla, confirma al deudor que un asesor lo contactara, "
            "despidete, y llama end_call."
        ),
        properties={
            "debtor_id": {"type": "string", "description": "ID del deudor"},
            "reason": {"type": "string", "description": "Motivo de la escalacion"},
        },
        required=["debtor_id", "reason"],
    )

    # Structured per-debtor data from Soft Seguros (synced into MongoDB).
    # This is the SOURCE OF TRUTH for THIS debtor's policy, balance, and dates.
    # NEVER use search_knowledge for these — RAG is fuzzy and could leak another
    # debtor's data. Exact, debtor-specific facts always come from here.
    get_policy_info_tool = FunctionSchema(
        name="get_policy_info",
        description=(
            "FALLBACK SOLAMENTE. Los datos de la poliza de ESTE deudor (tipo, "
            "numero, prima, saldo, fechas, estado de cartera, lo pagado) YA ESTAN "
            "en tu contexto bajo 'DATOS DE ESTA LLAMADA' — responde DIRECTO de ahi, "
            "NO llames esta funcion para 'cuanto debo', 'cuando vence', 'que tengo', "
            "'cual es mi poliza'. Usa esta funcion UNICAMENTE si el deudor pide un "
            "dato puntual que NO aparece en ese bloque. Si la llamas sin necesidad, "
            "agregas un retraso innecesario a la conversacion."
        ),
        properties={},
        required=[],
    )

    # Agentic RAG: lets the agent ground answers in the tenant's own knowledge
    # base (general policies, FAQs, procedures) instead of hallucinating. The
    # agent decides WHEN to call this — for GENERAL questions about how things
    # work, NOT for this debtor's specific numbers (that's get_policy_info).
    search_knowledge_tool = FunctionSchema(
        name="search_knowledge",
        description=(
            "Consulta la base de conocimiento de la empresa (polizas, condiciones, "
            "preguntas frecuentes, procedimientos) para responder con informacion REAL "
            "y no inventada. Usala SIEMPRE que el deudor pregunte algo especifico sobre "
            "su producto, cobertura, deducibles, condiciones de pago, o cualquier dato "
            "que debas verificar en los documentos antes de responder."
        ),
        properties={
            "query": {
                "type": "string",
                "description": "La pregunta o tema a buscar, en lenguaje natural (ej: 'deducible en perdida total', 'cuando se suspende la poliza por mora')",
            },
        },
        required=["query"],
    )

    # Payment claim: when the debtor says they ALREADY PAID, we can't verify it
    # on the call — the comprobante must be reviewed by the DPG team. This tool
    # marks the debtor as pago_reportado AND notifies the team's WhatsApp so a
    # human checks the receipt. It does NOT confirm the payment (that's the
    # team's job); it just routes the claim for review.
    notify_payment_claim_tool = FunctionSchema(
        name="notify_payment_claim",
        description=(
            "Usala SIEMPRE que el deudor diga que YA PAGO o que ya hizo el pago "
            "('ya pague', 'ya lo cancele', 'pague ayer', 'ya hice la consignacion', "
            "'ya transferi'). Notifica al equipo de De Pe Ge para que revise el "
            "comprobante. Tu NO confirmas el pago — solo registras el reporte. "
            "Despues de llamarla, dile al deudor que el equipo revisara el "
            "comprobante y le confirmara."
        ),
        properties={
            "detalle": {
                "type": "string",
                "description": "Lo que dijo el deudor sobre el pago (fecha, medio, monto si lo menciona). Ej: 'dice que pago ayer por transferencia'",
            },
        },
        required=["detalle"],
    )

    tools_schema = ToolsSchema(standard_tools=[
        end_call_tool, update_debtor_tool, send_whatsapp_tool, verify_identity_tool,
        escalate_tool, get_policy_info_tool, search_knowledge_tool,
        notify_payment_claim_tool,
    ])

    # ── Gemini Live (STT + LLM + TTS all-in-one, 8kHz telephony) ────────
    # Gemini's native VAD is tuned LOW-sensitivity: phone lines have constant
    # noise/echo that, at default sensitivity, makes the bot self-interrupt
    # ~0.2s into every utterance (audio cuts out). LOW start-sensitivity +
    # longer silence_duration means only real, sustained speech interrupts.
    from pipecat.services.google.gemini_live.llm import (
        InputParams as GeminiInputParams,
        GeminiVADParams,
        GeminiModalities,
    )
    _lap("tools schema built")
    from pipecat.transcriptions.language import Language
    from google.genai.types import StartSensitivity, EndSensitivity, ThinkingConfig
    _lap("genai.types imported")
    # Per-tenant VAD start-sensitivity. This SDK only exposes HIGH / LOW (no
    # MEDIUM). We default HIGH: LOW reacts to less-confident onsets and was what
    # produced phantom/hallucinated turns. Proactivity instead comes from the
    # shorter silence_duration (turn closes faster → bot answers sooner).
    _vad_start_map = {
        "HIGH": StartSensitivity.START_SENSITIVITY_HIGH,
        "LOW": StartSensitivity.START_SENSITIVITY_LOW,
    }
    _vad_start_sensitivity = _vad_start_map.get(
        str(tenant_config.get("vad_start_sensitivity") or "HIGH").upper(),
        StartSensitivity.START_SENSITIVITY_HIGH,
    )
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        # Model trade-off (see commit notes): native-audio sounds natural but on
        # 8kHz telephony audio it transcribes the CALLER poorly — input
        # transcripts came back as "[.]" (noise), so it never recognized policy
        # questions and never fired get_policy_info; turns were also choppy/laggy
        # (confirmed on call CA8a4d33d9: "habló entrecortado", tool never fired).
        # 3.1-flash-live does proper STT (handles phone audio) and DID execute
        # tools before — its only prior failure was going silent after a tool
        # result, which was the MISSING CONTEXT AGGREGATOR, now fixed via
        # LLMContextAggregatorPair. So it should both transcribe and complete
        # function calls correctly now.
        model="models/gemini-3.1-flash-live-preview",
        # ARIA is a woman → feminine Gemini Live voice. Prebuilt feminine
        # voices: Aoede (warm/natural), Leda (bright/youthful), Kore, Zephyr.
        # Per-tenant override from MongoDB (no hardcoded tenant data); default
        # Aoede when the tenant hasn't set one.
        voice_id=str(tenant_config.get("voice_id") or "Aoede"),
        system_instruction=system_prompt,
        tools=tools_schema,
        params=GeminiInputParams(
            language=Language.ES_US,
            # 0.5 (was 0.7): less sampling deliberation on the post-tool-result
            # generation → the second inference turn (result → spoken answer,
            # measured ~0.7–1.1s) comes back a bit faster. Modest but free, and
            # cobranza wants consistent, on-script answers more than creative ones.
            # Per-tenant override via tenant_config.voice_temperature.
            temperature=float(tenant_config.get("voice_temperature") or 0.5),
            # CRITICAL: force AUDIO output. Without this, Gemini Live returns
            # only text — the pipeline emits "bot speaking" events but ZERO
            # audio frames, so the caller hears nothing.
            modalities=GeminiModalities.AUDIO,
            # Disable "thinking" (thinking_budget=0): the model otherwise spends
            # extra inference deliberating BEFORE emitting the first audio, which
            # adds dead air to the opening greeting (~2.7s measured answer->speak).
            # Cobranza is scripted/reactive, not a reasoning task — no thinking
            # needed. This shaves the first-token latency.
            thinking=ThinkingConfig(thinking_budget=0),
            # Gemini's native VAD MUST stay ON — it's what detects end-of-turn
            # and triggers the response. Disabling it entirely meant Gemini
            # received the caller's audio but never knew the turn ended, so it
            # greeted once and went silent forever. Instead we keep it ON but
            # LOW-sensitivity + longer silence so phone-line noise/echo doesn't
            # trigger false interruptions ~2s into the bot's own speech.
            # start HIGH: require CONFIDENT speech onset before opening a turn.
            # With start LOW, phone-line noise/silence opened phantom turns that
            # Gemini then HALLUCINATED into full sentences (observed: caller said
            # nothing, but STT produced "Quiero hablar con un asesor" and the bot
            # called escalate on words never spoken). HIGH start-sensitivity means
            # only real, confident speech triggers a turn — no phantom input.
            # LATENCY TUNING (configurable per-tenant via tenant_config.vad_*).
            # Measured server-side response latency is already ~0.7–1.1s, but the
            # caller PERCEIVES dead air from the VAD's end-of-turn wait, which the
            # server log can't see (Gemini reports user start+stop at the same ts).
            # That wait = silence_duration_ms, so it's the real lever here.
            # - end_sensitivity HIGH: per Google's API, HIGH = MORE sensitive to
            #   end-of-speech → closes the turn FASTER (this is the fast setting,
            #   keep it).
            # - silence_duration 250ms (was 400): Gemini waits less silence before
            #   deciding the caller finished → bot answers sooner on EVERY turn.
            #   250ms is about the floor before normal mid-sentence pauses start
            #   getting clipped on a phone line; tune up per-tenant if it cuts people off.
            # - prefix_padding 200ms (was 300): less lead-in lag opening a turn.
            # - start stays HIGH to avoid the phantom/hallucinated turns that LOW
            #   produced earlier (there is no MEDIUM in the SDK — only HIGH/LOW).
            vad=GeminiVADParams(
                disabled=False,
                start_sensitivity=_vad_start_sensitivity,
                end_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
                prefix_padding_ms=int(tenant_config.get("vad_prefix_padding_ms") or 200),
                silence_duration_ms=int(tenant_config.get("vad_silence_duration_ms") or 250),
            ),
        ),
    )
    _lap("LLM service created")

    # ── First greeting (spoken as TTS, not LLM-generated) ─────────────
    # Always address the client as "senor" + first name (per client request),
    # never "don"/"dona"/"caballero". No diminutives anywhere.
    # The agent introduces herself as the virtual assistant FROM THE FIRST
    # SECOND, then confirms identity in the same breath (hybrid opener). The
    # greeting text comes from the tenant's persona (Layer 2), so it's
    # per-client and editable without a deploy. The policy detail comes only
    # AFTER the debtor confirms (handled by the prompt flow).
    first_name = debtor_name.split()[0] if debtor_name and debtor_name != "senor o senora" else ""
    first_message = render_greeting(persona, first_name)

    # ── LLM Context ─────────────────────────────────────────────────────
    # Seed the greeting into the INITIAL context so Gemini speaks it the moment
    # the context is set (inference_on_context_initialization=True), with no wait
    # for the caller to talk. TTSSpeakFrame does NOT work here: Gemini Live is
    # audio-native and there's no separate TTS service in the pipeline to render
    # it, so the frame queued silently (observed: "speaking greeting" logged but
    # no audio). Letting Gemini generate the greeting is the only path that
    # actually produces sound on this transport.
    # ── Force the EXACT greeting (no paraphrase) ─────────────────────────────
    # Gemini Live paraphrased the greeting when it was only a trailing
    # instruction buried under a 7000-char prompt full of example "buenas
    # tardes" lines. Fix: put the literal opener FIRST and LAST (a hard frame at
    # the very top of the system message + a final reminder), and make the user
    # turn explicitly order it. The opener must be the model's first words,
    # verbatim, including the ARIA self-introduction.
    greeting_hard = (
        f"=== REGLA #1, POR ENCIMA DE TODO LO DEMAS ===\n"
        f"Tu PRIMERA frase hablada al conectar la llamada DEBE SER, palabra por "
        f"palabra, sin cambiar ni una letra, sin reemplazarla por otro saludo:\n"
        f"\"{first_message}\"\n"
        f"NO digas 'buenas tardes' a secas, NO omitas tu nombre ARIA, NO omitas "
        f"que eres la asistente virtual. Di la frase COMPLETA tal cual. Recien "
        f"despues de decirla, sigue el resto de tus instrucciones.\n"
        f"=== FIN REGLA #1 ===\n\n"
    )
    greeting_instruction = (
        f"\n\nRECORDATORIO FINAL: tu primera linea hablada es EXACTAMENTE "
        f"\"{first_message}\" — palabra por palabra, con tu nombre y que eres asistente virtual."
    )
    messages = [
        {"role": "system", "content": greeting_hard + system_prompt + greeting_instruction},
        {"role": "user", "content": f"[La persona contesto. Di AHORA, exactamente: \"{first_message}\"]"},
    ]
    context = LLMContext(messages)

    # ── Transcript collectors ────────────────────────────────────────────
    # user_collector: before LLM — catches TranscriptionFrames (upstream from LLM)
    # bot_collector: after LLM — catches TTSTextFrames (downstream from LLM)
    user_collector = TranscriptCollector(call_result, name="user_collector")
    bot_collector = TranscriptCollector(call_result, name="bot_collector")

    # ── Context aggregators — REQUIRED for function calling to complete ──
    # ROOT-CAUSE of "tool runs but bot goes silent forever": when a handler
    # finishes, its result is broadcast as a FunctionCallResultFrame. The
    # ASSISTANT aggregator is what writes that result into the LLMContext and
    # re-pushes an LLMContextFrame to the service; only then does
    # GeminiLiveLLMService._process_completed_function_calls() send the
    # tool_response over the socket and Gemini generates the spoken answer.
    # Without this pair, NO tool result ever reaches Gemini on ANY model.
    # NOTE: constructed directly — llm.create_context_aggregator() is broken
    # in pipecat 0.0.108 (deprecated from_openai_context path crashes with
    # AttributeError on user_turn_strategies).
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
    )
    context_aggregator = LLMContextAggregatorPair(context)

    # ── Pipeline ─────────────────────────────────────────────────────────
    # Canonical Pipecat order: assistant aggregator goes AFTER transport.output()
    pipeline = Pipeline(
        [
            transport.input(),
            context_aggregator.user(),
            user_collector,
            llm,
            bot_collector,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    # Interruptions ENABLED but GATED by a min-words strategy. Bare barge-in
    # broke calls: the caller's "Aló" landed ON TOP of ARIA's opening greeting,
    # cut Gemini Live mid-sentence, and Gemini then never recovered (observed:
    # greeting half-said, then only the caller's "Hola... Hola..." with ARIA
    # silent). MinWordsInterruptionStrategy requires the caller to say a real
    # phrase (>= N words) before an interruption is honored — so short backchannel
    # ("Aló", "sí", "hola") does NOT cut the greeting, but a genuine sentence
    # ("espere, una pregunta") still interrupts naturally. Per-tenant override
    # via tenant_config.interruption_min_words (0 disables the gate).
    from pipecat.audio.interruptions.min_words_interruption_strategy import (
        MinWordsInterruptionStrategy,
    )
    _min_words = int(tenant_config.get("interruption_min_words") or 3)
    _strategies = [MinWordsInterruptionStrategy(min_words=_min_words)] if _min_words > 0 else []
    _allow_interruptions = bool(tenant_config.get("allow_interruptions", True))
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=_allow_interruptions,
            interruption_strategies=_strategies,
            enable_metrics=True,
            report_only_initial_ttfb=True,
        ),
    )

    # ── Function call handlers ─────────────────────────────────────────

    # Instantiate orchestrator once for this call (all handlers share it)
    orchestrator = CobranzaOrchestrator(user_id=user_id, tenant_config=tenant_config) if user_id else None

    async def _handle_end_call(params):
        """end_call: play the farewell, then tear the pipeline down hard.

        We deliberately do NOT queue an EndFrame here. Gemini Live defers
        EndFrame handling "until the bot turn is finished" and, after a tool
        call, often never emits turn_complete — so the EndFrame sat for the full
        30s deferral timeout, holding the line open ~50s after the goodbye
        (observed on CA759d6036: end_call at 11:46:42, cleanup at 11:47:32).
        task.cancel() stops the pipeline immediately, which drops the WS and
        hangs up the Twilio call without waiting on a turn that won't complete.
        """
        reason = params.arguments.get("reason", "conversacion finalizada")
        logger.info("[VOICE] end_call invoked: reason=%s", reason)
        await params.result_callback({"status": "ending", "reason": reason})
        # Allow farewell TTS to play before disconnect, then hard-cancel.
        await asyncio.sleep(4.0)
        logger.info("[VOICE] end_call: cancelling pipeline (hard hangup)")
        await task.cancel()

    async def _handle_update_debtor(params):
        """update_debtor: patch debtor estado/fields via CobranzaOrchestrator."""
        # Same as escalate: trust the in-scope debtor's _id, not the model's guess.
        debtor_id = str(debtor.get("_id", "")) or params.arguments.get("debtor_id", "")
        estado = params.arguments.get("estado", "")
        logger.info("[VOICE] update_debtor: debtor_id=%s estado=%s", debtor_id, estado)
        result = {"ok": False, "error": "orchestrator unavailable"}
        if orchestrator and debtor_id:
            try:
                result = await orchestrator.update_debtor(debtor_id, {"estado": estado})
            except Exception as exc:
                logger.error("[VOICE] update_debtor error: %s", exc)
                result = {"ok": False, "error": str(exc)[:100]}
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=True))

    async def _handle_send_whatsapp(params):
        """send_whatsapp: enqueue WhatsApp message to the DEBTOR via orchestrator.

        The recipient is ALWAYS the debtor's registered phone (MongoDB) — never
        a number the model supplies. This prevents the model from hallucinating
        a recipient (it once invented +573001234567).
        """
        message = params.arguments.get("message", "")
        phone = str(debtor.get("telefono", "")).strip()
        logger.info("[VOICE] send_whatsapp -> debtor phone=%s", phone)
        result = {"ok": False, "error": "orchestrator unavailable"}
        if not phone:
            result = {"ok": False, "error": "debtor has no phone on file"}
        elif orchestrator and message:
            try:
                result = await orchestrator.send_whatsapp(phone, message)
            except Exception as exc:
                logger.error("[VOICE] send_whatsapp error: %s", exc)
                result = {"ok": False, "error": str(exc)[:100]}
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=True))

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
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=True))

    async def _handle_escalate(params):
        """escalate: mark debtor escalado and notify dashboard."""
        # Gemini doesn't know the Mongo _id — always fall back to the in-scope
        # debtor. Whatever id the model passes is ignored in favor of the real one.
        debtor_id = str(debtor.get("_id", "")) or params.arguments.get("debtor_id", "")
        reason = params.arguments.get("reason", "escalado por agente")
        logger.info("[VOICE] escalate: debtor_id=%s reason=%s", debtor_id, reason)
        result = {"ok": False, "error": "orchestrator unavailable"}
        if orchestrator and debtor_id:
            try:
                result = await orchestrator.escalate(debtor_id, reason)
            except Exception as exc:
                logger.error("[VOICE] escalate error: %s", exc)
                result = {"ok": False, "error": str(exc)[:100]}
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=True))

    async def _handle_notify_payment_claim(params):
        """notify_payment_claim: debtor says they already paid.

        Two side effects: (1) mark the debtor pago_reportado so the auto-dialer
        stops calling while the team reviews; (2) WhatsApp the DPG team the claim
        so a human verifies the comprobante. We do NOT mark the debt as paid —
        only the team can confirm after seeing the receipt.
        """
        detalle = params.arguments.get("detalle", "el deudor reporta que ya pago")
        debtor_id = str(debtor.get("_id", ""))
        logger.info("[VOICE] notify_payment_claim: debtor_id=%s detalle=%s", debtor_id, detalle[:80])
        result = {"ok": False, "error": "orchestrator unavailable"}
        if orchestrator and debtor_id:
            try:
                # 1) Park the debtor while the team reviews the receipt.
                await orchestrator.update_debtor(debtor_id, {"estado": "pago_reportado"})
                # 2) Notify the team's WhatsApp so a human checks it.
                # Per-tenant value — MUST come from MongoDB tenant_config, never
                # hardcoded/env. Accept a few key aliases for resilience.
                team_phone = str(
                    tenant_config.get("notification_whatsapp")
                    or tenant_config.get("team_whatsapp")
                    or ""
                ).strip()
                if team_phone:
                    msg = (
                        f"📩 Reporte de pago — revisar comprobante\n"
                        f"Deudor: {debtor.get('nombre', 'N/D')}\n"
                        f"Teléfono: {debtor.get('telefono', 'N/D')}\n"
                        f"Póliza: {debtor.get('numero_poliza', 'N/D')}\n"
                        f"Detalle: {detalle}"
                    )
                    await orchestrator.send_whatsapp(team_phone, msg)
                    result = {"ok": True, "notified_team": True}
                else:
                    # No team number configured in tenant_config — still parked, but flag it.
                    logger.warning("[VOICE] notify_payment_claim: tenant_config.notification_whatsapp not set — debtor parked but team NOT notified")
                    result = {"ok": True, "notified_team": False, "warning": "team whatsapp not configured"}
            except Exception as exc:
                logger.error("[VOICE] notify_payment_claim error: %s", exc)
                result = {"ok": False, "error": str(exc)[:100]}
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=True))

    async def _handle_get_policy_info(params):
        """get_policy_info: exact per-debtor policy/balance data from MongoDB.

        Reads the in-scope `debtor` doc (already loaded, synced from Soft Seguros).
        No external call — instant. This is the SOURCE OF TRUTH for THIS debtor;
        only fields belonging to `debtor` are returned (no cross-tenant leak).
        Numbers are formatted in natural Spanish so the agent speaks them well.
        """
        logger.info("[VOICE] get_policy_info for debtor %s", debtor.get("_id"))

        def _money(v):
            try:
                return f"${int(float(v)):,}".replace(",", ".") if v is not None else None
            except (TypeError, ValueError):
                return None

        def _date(v):
            if not v:
                return None
            s = str(v)
            return s[:10]  # YYYY-MM-DD

        # Whitelist of debtor-facing fields. Soft Seguros debtors carry policy
        # detail; manual debtors only have the basics — both handled gracefully.
        info = {
            "nombre": debtor.get("nombre"),
            "numero_poliza": debtor.get("numero_poliza"),
            "ramo": debtor.get("ramo_global_nombre") or debtor.get("ramo_nombre"),
            "tipo_poliza": debtor.get("ramo_nombre"),
            "saldo_pendiente": _money(debtor.get("monto") or debtor.get("total")),
            "prima": _money(debtor.get("prima")),
            "total_pagado": _money(debtor.get("total_pagado")),
            "vencimiento": _date(debtor.get("vencimiento")),
            "fecha_limite_pago": _date(debtor.get("fecha_limite_pago")),
            "vigencia_fin": _date(debtor.get("fecha_fin")),
            "estado_cartera": debtor.get("estado_cartera"),
            "estado_poliza": debtor.get("estado_poliza_nombre"),
            "periodicidad": debtor.get("periodicidad"),
            "asesor": debtor.get("vendedores_nombre"),
        }
        # Drop empty fields so the agent isn't fed nulls
        info = {k: v for k, v in info.items() if v not in (None, "", [])}
        # run_llm=True: the assistant context aggregator re-pushes the context
        # so Gemini receives the tool result and SPEAKS the answer.
        await params.result_callback(
            {"found": bool(info), "poliza": info},
            properties=FunctionCallResultProperties(run_llm=True),
        )

    async def _handle_search_knowledge(params):
        """search_knowledge (Agentic RAG): ground answers in the tenant's KB.

        Queries the tenant's Pinecone namespace (=user_id) and returns the
        top passages so Gemini can answer from real documents, not hallucinate.
        Namespace isolation is enforced inside search_knowledge via user_id.
        """
        query = params.arguments.get("query", "")
        logger.info("[VOICE] search_knowledge: query=%s", query[:80])
        result = {"results": [], "found": False}
        # Short-circuit: tenant has no KB docs → skip the ~5-7s embed+Pinecone
        # round-trip entirely and answer instantly (precomputed at call start).
        if not tenant_has_rag_docs:
            logger.info("[VOICE] search_knowledge: tenant has no RAG docs — short-circuit")
            await params.result_callback(
                {"found": False, "message": "No hay informacion sobre eso en la base de conocimiento."},
                properties=FunctionCallResultProperties(run_llm=True),
            )
            return
        if user_id and query:
            try:
                from cobranza.rag_service import search_knowledge
                # Filler speech: the embed+Pinecone lookup takes a beat. Speak a
                # short natural filler so the caller doesn't sit in dead air while
                # we retrieve (fire-and-forget; doesn't block the lookup).
                import random as _rnd
                _filler = _rnd.choice([
                    "Permítame un momento que reviso eso...",
                    "Déjeme verlo un momento...",
                    "A ver, déjeme consultar eso...",
                ])
                await task.queue_frames([TTSSpeakFrame(_filler)])
                # Hard timeout so a slow Pinecone/OpenAI call can't stall the
                # conversation; on timeout we degrade gracefully to "no info".
                matches = await asyncio.wait_for(
                    search_knowledge(user_id, query, top_k=3), timeout=4.0
                )
                if matches:
                    # Compact payload for the LLM: just the text + title, ranked
                    result = {
                        "found": True,
                        "results": [
                            {"text": m.get("text", "")[:600], "title": m.get("title", "")}
                            for m in matches
                        ],
                    }
                else:
                    result = {
                        "found": False,
                        "message": "No hay informacion sobre eso en la base de conocimiento.",
                    }
            except asyncio.TimeoutError:
                logger.warning("[VOICE] search_knowledge timed out (>4s) — degrading")
                result = {"found": False, "message": "No pude consultar eso a tiempo."}
            except Exception as exc:
                logger.error("[VOICE] search_knowledge error: %s", exc)
                result = {"found": False, "error": str(exc)[:100]}
        # run_llm=True so the agent SPEAKS the retrieved answer (see get_policy_info)
        await params.result_callback(
            result, properties=FunctionCallResultProperties(run_llm=True)
        )

    # cancel_on_interruption=False for any handler with REAL side effects: with
    # barge-in enabled, the caller speaking mid-execution must NOT abort a DB
    # write or an outbound WhatsApp half-way. Read-only tools (get_policy_info,
    # search_knowledge, verify_identity) stay cancellable — re-running them is
    # harmless and aborting them frees the turn faster.
    llm.register_function("end_call", _handle_end_call, cancel_on_interruption=False)
    llm.register_function("update_debtor", _handle_update_debtor, cancel_on_interruption=False)
    llm.register_function("send_whatsapp", _handle_send_whatsapp, cancel_on_interruption=False)
    llm.register_function("escalate", _handle_escalate, cancel_on_interruption=False)
    llm.register_function("verify_identity", _handle_verify_identity)
    llm.register_function("get_policy_info", _handle_get_policy_info)
    llm.register_function("search_knowledge", _handle_search_knowledge)
    # cancel_on_interruption=False: this handler does real side effects (parks
    # the debtor + WhatsApps the team). With barge-in enabled, the caller
    # speaking mid-execution was cancelling it before the WhatsApp went out
    # (observed: notify_payment_claim fired then "has been cancelled" twice).
    # It must run to completion regardless of interruptions.
    llm.register_function(
        "notify_payment_claim", _handle_notify_payment_claim, cancel_on_interruption=False
    )

    # ── Events ───────────────────────────────────────────────────────────
    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        _lap("on_client_connected -> seeding context")
        logger.info("[VOICE] EVENT: on_client_connected — seeding context to greet")
        # The greeting is NOT a TTSSpeakFrame (silent with Gemini Live — there's
        # no separate TTS service to render it). It's seeded into the INITIAL
        # context above as a system instruction + an opening user turn, and
        # inference_on_context_initialization=True makes Gemini generate+speak it
        # the moment the context is set. Pushing the context here kicks that off
        # the instant the call connects, so the bot talks FIRST without waiting
        # for the caller and without the ~15s of dead air the old approach had.
        await task.queue_frames([LLMContextFrame(context=context)])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("[VOICE] EVENT: on_client_disconnected")
        await task.queue_frames([EndFrame()])

    # ── Hard call-duration watchdog ──────────────────────────────────────
    # Voicemail answers never say goodbye, so end_call never fires and the
    # pipeline lives forever (observed: a voicemail call ran 280s ALONGSIDE
    # the next real call, starving it — slow turns, missing replies). Force
    # an EndFrame after MAX_CALL_SECONDS no matter what.
    import asyncio as _asyncio
    MAX_CALL_SECONDS = 240  # prompt already says "maximo 3-4 minutos"

    async def _call_watchdog():
        await _asyncio.sleep(MAX_CALL_SECONDS)
        logger.warning("[VOICE] Watchdog: call %s exceeded %ds — forcing hang-up", call_sid, MAX_CALL_SECONDS)
        await task.queue_frames([EndFrame()])

    watchdog = _asyncio.create_task(_call_watchdog())

    # ── Run ───────────────────────────────────────────────────────────────
    _lap("pipeline built, about to run")
    logger.info("[VOICE] Starting pipeline for call %s...", call_sid)
    try:
        runner = PipelineRunner()
        await runner.run(task)
        logger.info("[VOICE] Pipeline finished OK for call %s", call_sid)
    except Exception as e:
        logger.error("[VOICE] ERROR in pipeline: %s: %s", type(e).__name__, e, exc_info=True)
    finally:
        watchdog.cancel()

    call_result.ended_at = time.time()
    call_result.duration_seconds = int(call_result.ended_at - call_result.started_at)
    logger.info("[VOICE] Call %s: duration=%ds, turns=%d", call_sid, call_result.duration_seconds, len(call_result.transcript))

    return call_result
