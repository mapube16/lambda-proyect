import logging
import os
from typing import Optional, Tuple

import httpx

from cobranza.audio_utils import (
    parse_sample_rate_from_content_type,
    pcm16_from_wav_bytes,
    pcm16_mono_resample,
    pcm16_to_mulaw,
)

logger = logging.getLogger("cobranza.deepgram_tts")


DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"


def _default_model() -> str:
    return os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-celeste-es")


def _default_accept() -> str:
    # Deepgram often returns raw PCM with this accept.
    return os.getenv("DEEPGRAM_TTS_ACCEPT", "audio/l16;rate=24000")


async def speak_raw(
    text: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    accept: Optional[str] = None,
    timeout_s: float = 30.0,
) -> Tuple[bytes, int]:
    """Call Deepgram Speak and return (pcm16_mono_bytes, sample_rate_hz).

    If the API responds with WAV, this extracts PCM frames automatically.
    """
    api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY not set")

    model = model or _default_model()
    accept = accept or _default_accept()

    headers = {
        "Authorization": f"Token {api_key}",
        "Accept": accept,
        "Content-Type": "application/json",
    }

    params = {"model": model}
    payload = {"text": text}

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(DEEPGRAM_SPEAK_URL, params=params, json=payload, headers=headers)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type")
        data = resp.content

    # If we accidentally got a WAV container, extract.
    if data.startswith(b"RIFF"):
        pcm, rate = pcm16_from_wav_bytes(data)
        return pcm, rate

    rate = (
        parse_sample_rate_from_content_type(content_type)
        or parse_sample_rate_from_content_type(accept)
        or 24000
    )
    return data, rate


async def speak_mulaw_8k(
    text: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    accept: Optional[str] = None,
) -> bytes:
    """Deepgram Speak → 8kHz μ-law (Twilio media-stream friendly)."""
    pcm, rate = await speak_raw(text, api_key=api_key, model=model, accept=accept)
    if rate != 8000:
        pcm = pcm16_mono_resample(pcm, rate, 8000)
    return pcm16_to_mulaw(pcm)
