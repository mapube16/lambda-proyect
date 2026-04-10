#!/usr/bin/env python3
"""End-to-end Deepgram TTS smoke test.

Generates:
- A playable WAV (24k PCM) for listening
- A Twilio-friendly 8k μ-law payload

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

        print(f"[OK] Raw PCM: {len(pcm)} bytes @ {rate} Hz")
        print(f"[OK] Wrote WAV: {wav_path}")
        print(f"[OK] 8k μ-law: {len(ulaw)} bytes")
        print(f"[OK] Wrote μ-law: {ulaw_path}")

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
