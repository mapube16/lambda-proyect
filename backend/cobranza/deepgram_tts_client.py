"""Cliente de Deepgram Speak (Aura-2).

OJO con el formato: Deepgram IGNORA el header `Accept` en /v1/speak y devuelve
MP3 por defecto. La versión anterior pedía `Accept: audio/l16;rate=24000`,
recibía `audio/mpeg` y trataba esos bytes como PCM16 crudo → lo que llegaba al
deudor era ruido. El formato se pide por QUERY (`encoding`/`sample_rate`/
`container`), y pedirle mu-law 8kHz directamente entrega el payload exacto que
consume el media-stream de Twilio, sin remuestrear nada de nuestro lado.
"""
import logging
import os
from typing import Optional, Tuple

import httpx

from cobranza.audio_utils import pcm16_from_wav_bytes

logger = logging.getLogger("cobranza.deepgram_tts")


DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"

# Voces colombianas de Aura-2: celeste (clara, enérgica) y gloria (natural, suave).
# El resto del catálogo es peninsular/mexicano/argentino.
DEFAULT_MODEL = "aura-2-celeste-es"


def _api_key(api_key: Optional[str]) -> str:
    key = api_key or os.getenv("DEEPGRAM_API_KEY")
    if not key:
        raise RuntimeError("DEEPGRAM_API_KEY not set")
    return key


async def _speak(text: str, key: str, model: str, params: dict, timeout_s: float) -> bytes:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(
            DEEPGRAM_SPEAK_URL,
            params={"model": model, **params},
            json={"text": text},
            headers={"Authorization": f"Token {key}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.content


async def speak_raw(
    text: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    sample_rate: int = 24000,
    timeout_s: float = 30.0,
) -> Tuple[bytes, int]:
    """Deepgram Speak → (pcm16 mono, sample_rate). Para escuchar/guardar en alta."""
    wav = await _speak(
        text, _api_key(api_key), model or os.getenv("DEEPGRAM_TTS_MODEL", DEFAULT_MODEL),
        {"encoding": "linear16", "sample_rate": sample_rate, "container": "wav"}, timeout_s,
    )
    return pcm16_from_wav_bytes(wav)


async def speak_mulaw_8k(
    text: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout_s: float = 30.0,
) -> bytes:
    """Deepgram Speak → μ-law 8kHz sin cabecera: el payload crudo del media-stream
    de Twilio. `container=none` evita tener que quitarle el RIFF a mano."""
    return await _speak(
        text, _api_key(api_key), model or os.getenv("DEEPGRAM_TTS_MODEL", DEFAULT_MODEL),
        {"encoding": "mulaw", "sample_rate": 8000, "container": "none"}, timeout_s,
    )
