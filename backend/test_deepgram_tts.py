#!/usr/bin/env python3
"""End-to-end Deepgram TTS smoke test.

Generates:
- A playable WAV (24k PCM) for listening
- A Twilio-friendly 8k mu-law payload

Usage:
  python test_deepgram_tts.py

Env:
  DEEPGRAM_API_KEY (required)
  DEEPGRAM_TTS_MODEL (optional, default aura-2-celeste-es)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("[FAIL] DEEPGRAM_API_KEY not set")
        return 1

    text = "Ajá, listo. Le hablo de De Pe Ge Seguros, es por un saldito pendiente."

    from cobranza.deepgram_tts_client import speak_mulaw_8k, speak_raw
    from cobranza.audio_utils import wav_bytes_from_pcm16

    out_dir = Path(__file__).resolve().parent / "tmp"
    out_dir.mkdir(parents=True, exist_ok=True)

    import asyncio

    async def run():
        pcm, rate = await speak_raw(text)
        wav = wav_bytes_from_pcm16(pcm, rate)
        wav_path = out_dir / "deepgram_celeste_raw.wav"
        wav_path.write_bytes(wav)

        ulaw = await speak_mulaw_8k(text)
        ulaw_path = out_dir / "deepgram_celeste_8k_mulaw.raw"
        ulaw_path.write_bytes(ulaw)

        # El check que importa: Deepgram ignora el header Accept y devuelve MP3
        # si no se le pide el formato por query. Un MP3 tomado por PCM "pesa"
        # ~8x menos, asi que las dos duraciones se separan. Si vuelven a diverger,
        # el audio que sale al deudor es ruido.
        dur_pcm = len(pcm) / (rate * 2)
        dur_ulaw = len(ulaw) / 8000
        assert dur_pcm > 1.0, f"PCM sospechosamente corto ({dur_pcm:.1f}s) — ¿volvio el MP3?"
        # Tolerancia amplia: cada llamada al TTS es una "toma" distinta (el ritmo
        # varia hasta ~40%). El bug del MP3 daba una razon de ~8x — eso si se atrapa.
        razon = max(dur_pcm, dur_ulaw) / max(min(dur_pcm, dur_ulaw), 0.1)
        assert razon < 2.0, (
            f"formatos incoherentes (razon {razon:.1f}x): pcm={dur_pcm:.1f}s vs mulaw={dur_ulaw:.1f}s"
        )

        print(f"[OK] Raw PCM: {len(pcm)} bytes @ {rate} Hz ({dur_pcm:.1f}s)")
        print(f"[OK] Wrote WAV: {wav_path}")
        print(f"[OK] 8k mu-law: {len(ulaw)} bytes ({dur_ulaw:.1f}s)")
        print(f"[OK] Wrote mu-law: {ulaw_path}")

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
