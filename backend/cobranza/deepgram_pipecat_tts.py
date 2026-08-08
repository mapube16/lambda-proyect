"""TTS de Deepgram (Aura-2) como servicio de Pipecat — la "boca" del modo híbrido.

Modo híbrido (rama feat/voz-deepgram): Gemini Live sigue siendo oído + cerebro
(STT telefónico probado, tools, turnos), pero con modalities=TEXT — el texto que
genera lo pronuncia una voz COLOMBIANA de Deepgram (aura-2-celeste-es / gloria).
Veredicto de las 6 llamadas de prueba: la voz de Deepgram gusta, su STT no.

Va montado en el pipeline entre el LLM y transport.output(). La base TTSService
de pipecat agrega tokens en oraciones y llama run_tts() por oración; el audio
sale en PCM 24k y el serializer del transporte lo baja a mulaw 8k (mismo camino
que recorría el audio nativo de Gemini).

ponytail: sintesis por oración completa via HTTP (~200-400ms por frase). Si la
latencia percibida molesta, el paso siguiente es el WS streaming de Deepgram.
"""
import logging

from pipecat.frames.frames import TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame
from pipecat.services.tts_service import TTSService

from cobranza.deepgram_tts_client import DEFAULT_MODEL, speak_raw

logger = logging.getLogger("cobranza.deepgram_pipecat_tts")


class DeepgramHttpTTSService(TTSService):
    """Deepgram Speak /v1/speak (HTTP) → frames de audio PCM para el pipeline."""

    def __init__(self, *, model: str = DEFAULT_MODEL, sample_rate: int = 24000, **kwargs):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._model = model

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str):
        await self.start_ttfb_metrics()
        try:
            pcm, rate = await speak_raw(text, model=self._model, sample_rate=self.sample_rate)
        except Exception:
            # Nunca tumbar la llamada por una frase que no sintetizó: se pierde
            # esa oración y la conversación sigue (Gemini repite si hace falta).
            logger.exception("[deepgram-tts] fallo sintetizando %r", text[:80])
            return
        await self.stop_ttfb_metrics()
        yield TTSStartedFrame()
        yield TTSAudioRawFrame(audio=pcm, sample_rate=rate, num_channels=1)
        yield TTSStoppedFrame()
