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

    # ── RAG short-circuit precheck (latency) ────────────────────────────
    # search_knowledge costs ~5-7s (OpenAI embed + Pinecone). If the tenant has
    # NO documents ingested, that round-trip is pure dead air for every call.
    # One cheap indexed count here lets the handler skip Pinecone entirely.
    tenant_has_rag_docs = False
    if user_id:
        try:
            from database import get_db
            _db = get_db()
            tenant_has_rag_docs = (
                await _db.rag_documents.count_documents({"user_id": user_id}, limit=1)
            ) > 0
        except Exception as _rag_err:
            logger.warning("[VOICE] rag_documents precheck failed for %s: %s", user_id, _rag_err)
            tenant_has_rag_docs = True  # fail-open: don't block real KB lookups

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
        f"Eres Camila, asesora de cobranza de De Pe Ge Seguros. Colombiana, de Armenia. "
        f"Tienes 28 anios, llevas 4 anios en la empresa. Eres una persona real, no un robot. "
        f"Tu tono es {tono}, cercano, como si hablaras con un vecino. "
        f"\n\n"
        f"PERSONALIDAD Y VOZ:\n"
        f"- Hablas en espaniol colombiano natural. Usas 'usted' pero de forma cercana, no rigida.\n"
        f"- Frases CORTAS. Maximo 1-2 oraciones por turno. Como en una conversacion real por telefono.\n"
        f"- Muletillas naturales: 'aja', 'listo', 'mire', 'claro', 'si senor', 'que pena con usted', 'no, tranquilo'.\n"
        f"- Pausas naturales: '...', 'mmm', 'a ver'. NO hables como un guion leido.\n"
        f"- Numeros naturales: 'quinientos mil pesos', 'un millon doscientos', NO '500,000 pesos'.\n"
        f"- Respuestas cortas cuando el otro habla: 'aja', 'si claro', 'entiendo', 'listo'. Escucha mas de lo que hablas.\n"
        f"- NUNCA repitas el mismo argumento dos veces con las mismas palabras.\n"
        f"- NADA de diminutivos. Di 'pesos' (no 'pesitos'), 'saldo' (no 'saldito'), "
        f"'un momento' (no 'un segundito'), 'espere' (no 'esperecito'). Habla en terminos normales, profesionales pero calidos.\n"
        f"- AL SALUDAR Y AL DIRIGIRTE AL CLIENTE usa siempre 'senor' (ej: 'senor Carlos', 'buenas tardes senor'). "
        f"NUNCA uses 'don', 'dona', 'caballero' ni 'amigo'.\n"
        f"\n\n"
        f"DATOS DE ESTA LLAMADA:\n"
        f"- Nombre: {debtor_name}\n"
        f"- Deuda: {monto_natural}\n"
        f"- Vencimiento: {vencimiento_str}\n"
        f"\n\n"
        f"FLUJO DE LA CONVERSACION:\n"
        f"Siempre te debes presentar como Camila, asesora de cobranza de De Pe Ge Seguros. "
        f"1. Tu primer mensaje ya fue enviado (un saludo corto confirmando identidad). Espera la respuesta.\n"
        f"   Si responde 'si', 'soy yo', 'con el habla', o directamente PREGUNTA por su deuda "
        f"('cuanto debo', 'que paso con mi poliza') → la identidad queda confirmada. Responde de una "
        f"usando get_policy_info, SIN llamar verify_identity.\n"
        f"2. Si confirma que es el/ella: presenta el motivo con tacto. NO sueltes el monto de una. "
        f"   Ejemplo: 'Mire, le cuento, lo llamo porque tiene un saldo pendiente con nosotros...'\n"
        f"3. Menciona el monto solo si el deudor pregunta o despues de que acepte escuchar.\n"
        f"4. Ofrece opciones: pago completo, acuerdo de pago, o que lo llamen despues.\n"
        f"5. Si acepta algo: confirma y agradece. 'Listo, perfecto, entonces quedamos asi.'\n"
        f"6. Despidete corto y llama end_call.\n"
        f"\n\n"
        f"MANEJO DE OBJECIONES (muy importante):\n"
        f"- 'No tengo plata' → 'Entiendo, y por eso mismo lo llamo, para mirar como le podemos ayudar. "
        f"Podemos hacer un acuerdo de pago a cuotas, que le queda mas comodo?'\n"
        f"- 'Ya pague' / 'ya lo cancele' / 'pague ayer' → PRIMERO llama la funcion "
        f"notify_payment_claim (para avisar al equipo de De Pe Ge que revise el "
        f"comprobante), y LUEGO di: 'Ah, listo, que pena. El equipo va a revisar el "
        f"comprobante y le confirmamos. Gracias por avisar.' NUNCA confirmes tu el "
        f"pago — eso lo valida el equipo.\n"
        f"- 'No me interesa' / 'No quiero' → Intenta UNA sola vez con empatia: "
        f"'Entiendo, pero mire que si dejamos pasar mas tiempo su poliza se puede ver "
        f"afectada, y lo que queremos es ayudarlo a mantener su cobertura. "
        f"Le conviene que lo miremos ahora.' Si insiste, respeta su decision.\n"
        f"- 'Quien es usted?' / desconfianza → 'Claro, con toda razon. Soy Camila de De Pe Ge Seguros. "
        f"Si quiere puede verificar llamando al numero que aparece en su poliza.'\n"
        f"- Groserías o enojo → NO te alteres. Baja el tono: 'Entiendo que es una situacion incomoda, "
        f"no es mi intencion molestarlo. Si prefiere lo llamamos en otro momento.'\n"
        f"\n\n"
        f"CONSULTAR INFORMACION — tienes DOS fuentes, no las confundas:\n"
        f"1. get_policy_info → datos EXACTOS de ESTE deudor (su poliza, su saldo, sus fechas). "
        f"Usala cuando pregunte por LO SUYO: 'cuanto debo', 'cuando vence', 'que tengo contratado', "
        f"'cual es mi poliza', 'cuanto he pagado'. NUNCA inventes un monto o fecha — siempre consulta.\n"
        f"2. search_knowledge → informacion GENERAL de como funciona la empresa y los seguros "
        f"(condiciones, coberturas en general, deducibles, procedimientos, preguntas frecuentes). "
        f"Usala cuando pregunte COMO funcionan las cosas: 'que cubre el seguro', 'como es el deducible', "
        f"'que pasa si no pago', 'como hago un reclamo'.\n"
        f"REGLA DE ORO: si la pregunta es sobre SUS numeros → get_policy_info. "
        f"Si es sobre COMO funciona algo → search_knowledge. Si search_knowledge no encuentra nada, "
        f"dilo con honestidad y ofrece que un asesor lo contacte; NO inventes.\n"
        f"\n"
        f"REGLA ANTI-INVENTO (CRITICA): NUNCA actues sobre algo que el deudor NO dijo claramente. "
        f"Si no escuchaste bien, si hubo silencio, o si el audio fue confuso, NO asumas ni completes "
        f"la frase: pregunta '¿Disculpe, no le escuche bien, me puede repetir?'. JAMAS llames a una "
        f"funcion (escalate, end_call, etc.) basandote en algo que crees que dijo pero no estas seguro. "
        f"Solo llama escalate si el deudor PIDIO EXPLICITAMENTE un asesor/humano. Ante la duda, pregunta.\n"
        f"\n\n"
        f"CUANDO COLGAR — usa la funcion end_call (OBLIGATORIO):\n"
        f"Tienes una funcion llamada 'end_call'. DEBES usarla para terminar la llamada.\n"
        f"Despues de decir tu despedida, SIEMPRE llama a end_call. Situaciones:\n"
        f"- El deudor dice 'no me llame mas', 'no me vuelva a llamar', 'dejeme en paz', "
        f"o cualquier variante → di tu despedida y llama end_call.\n"
        f"- El deudor se despide o dice 'chao', 'adios', 'gracias' → despidete y llama end_call.\n"
        f"- El deudor pide hablar con un humano/asesor/persona → llama escalate, confirma que un "
        f"asesor lo contactara pronto, despidete, y llama end_call. NUNCA te quedes en silencio "
        f"despues de prometer el contacto.\n"
        f"- Ya lograste el objetivo (promesa de pago o acuerdo) → confirma, despidete y llama end_call.\n"
        f"- El deudor esta grosero y no quiere hablar → despidete corto y llama end_call.\n"
        f"- Maximo 3-4 minutos de llamada. Si no avanzas, ofrece llamar otro dia, despidete y llama end_call.\n"
        f"- NUNCA sigas hablando despues de despedirte. Despedida → end_call, siempre.\n"
        f"\n\n"
        f"PROHIBIDO:\n"
        f"- Amenazar, presionar agresivamente, o mentir.\n"
        f"- Compartir datos con terceros. Si contesta alguien que no es el deudor, NO menciones la deuda.\n"
        f"- Llamar fuera de horario (8am-5pm).\n"
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
            "Consulta los datos REALES y EXACTOS de la poliza de ESTE deudor "
            "(numero de poliza, ramo, prima, saldo, fechas de vencimiento, estado "
            "de cartera, lo pagado). Usala SIEMPRE que el deudor pregunte algo "
            "sobre SU propia poliza o cuenta: 'cuanto debo', 'cuando vence', 'que "
            "tengo contratado', 'cual es mi poliza'. Es la fuente de verdad — "
            "NUNCA inventes estos datos."
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
    from pipecat.transcriptions.language import Language
    from google.genai.types import StartSensitivity, EndSensitivity
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
        # Camila is a woman → feminine Gemini Live voice. Prebuilt feminine
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

    # ── First greeting (spoken as TTS, not LLM-generated) ─────────────
    # Always address the client as "senor" + first name (per client request),
    # never "don"/"dona"/"caballero". No diminutives anywhere.
    import random
    first_name = debtor_name.split()[0] if debtor_name and debtor_name != "senor o senora" else ""
    if first_name:
        greetings = [
            f"Aló... buenas tardes. ¿Hablo con el señor {first_name}?",
            f"Buenas tardes... ¿señor {first_name}?",
            f"Aló, buenas tardes. ¿Será que hablo con el señor {first_name}?",
            f"Buenas tardes... ¿estoy hablando con el señor {first_name}?",
        ]
    else:
        greetings = [
            "Aló... buenas tardes, señor. ¿Con quién tengo el gusto?",
            "Buenas tardes, señor... ¿con quién hablo?",
            "Aló, buenas tardes, señor. ¿Quién me contesta?",
        ]
    first_message = random.choice(greetings)

    # ── LLM Context ─────────────────────────────────────────────────────
    # Seed the greeting into the INITIAL context so Gemini speaks it the moment
    # the context is set (inference_on_context_initialization=True), with no wait
    # for the caller to talk. TTSSpeakFrame does NOT work here: Gemini Live is
    # audio-native and there's no separate TTS service in the pipeline to render
    # it, so the frame queued silently (observed: "speaking greeting" logged but
    # no audio). Letting Gemini generate the greeting is the only path that
    # actually produces sound on this transport.
    greeting_instruction = (
        f"\n\nIMPORTANTE — APERTURA DE LA LLAMADA: La llamada acaba de conectar. "
        f"Tu PRIMER mensaje debe ser EXACTAMENTE este saludo y nada mas, sin "
        f"esperar a que la otra persona hable: \"{first_message}\""
    )
    messages = [
        {"role": "system", "content": system_prompt + greeting_instruction},
        {"role": "user", "content": "[La llamada acaba de conectar — saluda ahora.]"},
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

    # Interruptions ENABLED: with start_sensitivity HIGH the spurious-interruption
    # problem that forced this off is gone, and barge-in makes the conversation
    # far more natural — the caller can cut the bot off and it responds immediately
    # instead of talking over them. Per-tenant override (set
    # tenant_config.allow_interruptions=false to disable).
    _allow_interruptions = bool(tenant_config.get("allow_interruptions", True))
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=_allow_interruptions,
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
