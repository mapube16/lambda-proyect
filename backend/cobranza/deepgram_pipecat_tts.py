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
