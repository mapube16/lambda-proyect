"""Modo híbrido de voz (rama feat/voz-deepgram): Gemini Live escucha/piensa,
la voz colombiana de Deepgram (aura-2-celeste-es / gloria) pronuncia.

El TTS es el DeepgramHttpTTSService OFICIAL de pipecat (solo usa aiohttp, no el
SDK de deepgram) — aquí solo vive el pegamento:

  - crear_tts_deepgram(): fábrica con la sesión aiohttp compartida del proceso.
  - DescartarVozGemini: ningún modelo Live vigente acepta response_modalities=
    TEXT (probado 2026-08-08: 3.1-flash-live y los native-audio devuelven 1007;
    los half-cascade viejos ya no existen en la API). Así que Gemini genera su
    voz normal — conservando VAD, turnos y tools EXACTOS de producción — y este
    procesador bota su audio y re-emite su transcripción (TTSTextFrame, la misma
    del transcript de siempre) como TextFrame para que el TTS la pronuncie.

ponytail: se pagan los tokens de audio de Gemini que se botan; si algún día la
API re-admite TEXT en Live, DescartarVozGemini sobra y se quita del pipeline.
"""
import logging
import os
from typing import Optional

import aiohttp

from pipecat.frames.frames import (
    TextFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSTextFrame,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.deepgram.tts import DeepgramHttpTTSService

logger = logging.getLogger("cobranza.deepgram_pipecat_tts")

# Sesión aiohttp compartida del proceso (pooling); se crea en el primer call —
# aiohttp exige un event loop corriendo. Nunca se cierra: vive lo que el server.
_session: Optional[aiohttp.ClientSession] = None


def crear_tts_deepgram(voz: str) -> DeepgramHttpTTSService:
    global _session
    if _session is None:
        _session = aiohttp.ClientSession()
    return DeepgramHttpTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY", ""),
        voice=voz,
        aiohttp_session=_session,
        # 8000, no 24000: la linea telefonica es 8k igual, y a 24k el que
        # remuestrea es Pipecat. Pidiendoselo a 8k lo hace Deepgram, que es
        # justo lo que hacia el Voice Agent (mulaw 8k nativo) y por eso sonaba
        # mejor. Un downsample menos en la cadena.
        sample_rate=8000,
    )


_RE_DATOS_SENSIBLES = None  # compilado perezoso en RecepcionFirewall


class RecepcionFirewall(FrameProcessor):
    """Guardarrail de SERVIDOR para el modo recepcion (inbound sin identificar).

    Llamada real CA2573a3 (09-ago): Gemini Live ignoro el prompt entero y le
    FABRICO al cliente una poliza ("expedida por Equidad, valor pendiente de
    cero pesos") sin haber corrido identificar_cliente. El prompt no basta —
    este filtro va en el pipeline, entre el LLM y el TTS: mientras la llamada
    no este atribuida a un deudor (identificado["ok"]), CUALQUIER frase del bot
    que huela a poliza/plata se BOTA y se reemplaza (una sola vez por racha)
    por la linea fija que redirige a la identificacion. El modelo puede
    alucinar lo que quiera: eso no llega a la boca.
    """

    def __init__(self, identificado: dict, **kwargs):
        super().__init__(**kwargs)
        self._identificado = identificado   # {"ok": bool} — lo escribe identificar_cliente
        self._redirigido = False            # anti-loop: una redireccion por racha
        global _RE_DATOS_SENSIBLES
        if _RE_DATOS_SENSIBLES is None:
            import re
            _RE_DATOS_SENSIBLES = re.compile(
                r"p[oó]liza|pesos|pendiente|cuota|deuda|mora|vencimiento|"
                r"aseguradora|expedida|saldo|pagar|pago", re.IGNORECASE)

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if (not self._identificado.get("ok")
                and isinstance(frame, TextFrame)
                and not isinstance(frame, TTSTextFrame)
                and frame.text and _RE_DATOS_SENSIBLES.search(frame.text)):
            logger.warning("[VOICE][firewall] frase sensible SIN identificar, bloqueada: %r",
                           frame.text[:100])
            if not self._redirigido:
                self._redirigido = True
                await self.push_frame(TextFrame(
                    text="Para poder darle informacion, primero necesito validar su "
                         "identidad. ¿Me marca su numero de cedula o NIT en el teclado "
                         "del telefono, terminando con la tecla numeral, por favor?"))
            return
        if self._identificado.get("ok"):
            self._redirigido = False
        await self.push_frame(frame, direction)


class OidoDeepgram(FrameProcessor):
    """Bridge STT dedicado → cerebro. Modo 'oido Deepgram': DeepgramSTTService
    transcribe (con keyterms por llamada) y este procesador convierte cada
    transcripcion FINAL en un turno de texto para Gemini via el mismo camino
    probado del DTMF (LLMMessagesAppendFrame run_llm=True → send_client_content
    + nudge realtime). Gemini nunca recibe audio (STT con audio_passthrough=
    False), asi que deja de usar su propio oido — el que garblaba el espanol
    telefonico ("con el hilar de cepo", "a los canadienses").

    La TranscriptionFrame se DEJA pasar tambien: user_collector (aguas arriba)
    ya la vio para el transcript/anti-buzon; aguas abajo Gemini la ignora.
    """

    def __init__(self, call_result=None, **kwargs):
        super().__init__(**kwargs)
        self._call_result = call_result

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        from pipecat.frames.frames import TranscriptionFrame, LLMMessagesAppendFrame
        # solo transcripciones FINALES con texto real (las interinas no cuentan)
        if isinstance(frame, TranscriptionFrame) and (frame.text or "").strip():
            texto = frame.text.strip()
            logger.info("[VOICE][oido-dg] turno del cliente: %r", texto[:120])
            await self.push_frame(frame, direction)  # que siga al collector/llm
            await self.push_frame(LLMMessagesAppendFrame(
                messages=[{"role": "user", "content": texto}], run_llm=True))
            return
        await self.push_frame(frame, direction)


def keyterms_llamada(debtor: dict) -> list:
    """Vocabulario a reforzar en el STT para ESTA llamada: nombre del deudor,
    aseguradora, y el vocabulario minado de 372 transcripts reales. Anclar
    estos terminos reduce los inventos del STT en audio telefonico ruidoso."""
    base = [
        "alo", "si", "no", "bueno", "senora", "senor", "gracias", "cupon",
        "link", "poliza", "pago", "cuota", "pesos", "ya pague", "ya lo pague",
        "no tengo plata", "no puedo pagar", "manana", "mas tarde", "asesor",
        "numero equivocado", "de una", "hasta luego", "buenos dias",
    ]
    for campo in ("nombre", "aseguradora_nombre"):
        for w in str(debtor.get(campo) or "").split():
            w = "".join(c for c in w if c.isalpha())
            if len(w) > 2:
                base.append(w)
    # dedup preservando orden
    vistos, out = set(), []
    for t in base:
        k = t.lower()
        if k not in vistos:
            vistos.add(k)
            out.append(t)
    return out


def crear_stt_deepgram(debtor: dict, sample_rate: int = 8000):
    """DeepgramSTTService como oido dedicado: nova-2 es, keyterms por llamada,
    utterance_end para el fin de turno, audio_passthrough=False para que el
    audio NO llegue a Gemini (que si no haria su propio STT en paralelo)."""
    from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
    return DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY", ""),
        audio_passthrough=False,
        sample_rate=sample_rate,
        live_options=LiveOptions(
            model="nova-2", language="es",
            encoding="linear16", channels=1, sample_rate=sample_rate,
            smart_format=True, punctuate=True,
            interim_results=True, utterance_end_ms=1000, vad_events=True,
            endpointing=300,
            keywords=keyterms_llamada(debtor),
        ),
    )


class DescartarVozGemini(FrameProcessor):
    """Entre Gemini Live (AUDIO) y el TTS: bota la voz de Gemini, deja su texto.

    Gemini Live emite CADA frase DOS veces (gemini_live/llm.py:1977-1982): una
    como LLMTextFrame y otra como TTSTextFrame. El TTS aguas abajo agrega
    cualquier TextFrame, asi que dejar pasar las dos hacia celeste producia
    "Le habla Le habla ARIA, ARIA, asistente asistente virtual virtual..."
    (llamada CAc87038). Se deja pasar SOLO el LLMTextFrame; el TTSTextFrame que
    alimenta el transcript lo vuelve a emitir nuestro TTS al hablar
    (push_text_frames=True), asi que bot_collector no pierde nada.
    """

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, (TTSAudioRawFrame, TTSTextFrame,
                              TTSStartedFrame, TTSStoppedFrame)):
            return              # voz y eco de texto de Gemini: a la basura
        await self.push_frame(frame, direction)
