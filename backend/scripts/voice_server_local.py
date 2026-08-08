"""Servidor de voz LOCAL para probar el modo hibrido (rama feat/voz-deepgram).

Monta SOLO cobranza.voice_router en :8002 — nada de main.py, schedulers ni jobs:
imposible que marque a un deudor real. La llamada la dispara a mano
test_call_deepgram.py modo call-prod, y el flujo desde el webhook es el MISMO
de produccion (TwiML -> ws -> run_bot con el pipeline completo).

Uso:
  VOICE_WEBHOOK_HOST=https://<tunel-ngrok> python scripts/voice_server_local.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# DNS del hotspot rechaza SRV de mongodb+srv:// (mismo fix de los scripts).
try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
except Exception:
    pass

# Gemini Live lee GOOGLE_API_KEY; localmente solo existe GEMINI_API_KEY (misma
# API de Google AI Studio). El motor hibrido se activa por env para la prueba.
os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
os.environ.setdefault("COBRANZA_TTS_ENGINE", "deepgram")

from fastapi import FastAPI

from cobranza.voice_router import router as voice_router

app = FastAPI(title="voz local (hibrido deepgram)")
app.include_router(voice_router)

if __name__ == "__main__":
    import uvicorn

    print(f"VOICE_WEBHOOK_HOST = {os.getenv('VOICE_WEBHOOK_HOST')}")
    print(f"COBRANZA_TTS_ENGINE = {os.getenv('COBRANZA_TTS_ENGINE')}")
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="info")
