"""Genera (UNA VEZ, no en runtime) el saludo de apertura de §9.4 con la misma voz
de ARIA (Gemini TTS, voice_id="Aoede" — la que usa voice_pipecat.py:638), en 2
variantes (mañana/tarde). Los WAV resultantes se commitean al repo como assets
estáticos (Railway persiste lo que está en la imagen del deploy)."""
import base64
import os
import struct
import wave

import httpx

KEY = os.getenv("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash-preview-tts"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "voice")

TEXTOS = {
    "manana": "Buenos días, gracias por comunicarse con DPG Seguros. Le atiende ARIA, su asistente virtual de cobranza. Para verificar su identidad, por favor marque su número de documento seguido de la tecla numeral. Si su documento es un NIT, no incluya el dígito de verificación.",
    "tarde": "Buenas tardes, gracias por comunicarse con DPG Seguros. Le atiende ARIA, su asistente virtual de cobranza. Para verificar su identidad, por favor marque su número de documento seguido de la tecla numeral. Si su documento es un NIT, no incluya el dígito de verificación.",
    # Filler que cubre la latencia de la sintesis dinamica de la enumeracion
    # de polizas (2-8s de Gemini TTS): suena de inmediato mientras el audio
    # real se genera (voice_router._pedir_seleccion_poliza).
    "filler": "Un momento por favor, estoy consultando la información de sus pólizas.",
}


def _synthesize(text: str) -> bytes:
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}",
        json={
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Aoede"}}
                },
            },
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    print("  mimeType:", part.get("mimeType"))
    return base64.b64decode(part["data"])


def _pcm_to_wav(pcm: bytes, path: str, sample_rate: int = 24000) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for variante, texto in TEXTOS.items():
        print("Generando:", variante)
        pcm = _synthesize(texto)
        out_path = os.path.join(OUT_DIR, f"inbound_greeting_{variante}.wav")
        _pcm_to_wav(pcm, out_path)
        size = os.path.getsize(out_path)
        print(f"  guardado: {out_path} ({size} bytes)")
