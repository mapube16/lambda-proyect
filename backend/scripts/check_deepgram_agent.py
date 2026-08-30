"""Chequeo del Voice Agent SIN llamada telefonica.

Abre la sesion contra agent.deepgram.com con los MISMOS Settings que usa
produccion (voice_agent._settings + prompt real de un deudor de prueba o uno
sintetico), y mide lo que un cliente percibe:

  1. SettingsApplied: la config es valida (modelo de oido, voz, think, tools).
  2. Saludo: ms desde Settings hasta el primer byte de audio.
  3. Un turno de texto (InjectUserMessage "si, con ella habla"): ms hasta el
     primer audio de la respuesta + el LatencyReport oficial (stt/ttt/tts).

Uso:
  python scripts/check_deepgram_agent.py                 # nova-3 es (default prod)
  python scripts/check_deepgram_agent.py flux            # flux-general-multi es
  python scripts/check_deepgram_agent.py flux eager      # + eager end-of-turn
  COBRANZA_AGENT_THINK_MODEL=gemini-3.1-flash-lite python scripts/check_deepgram_agent.py

Sale con codigo != 0 si Deepgram rechaza los Settings o el agente no habla.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import websockets

from cobranza.voice_agent import DG_AGENT_URL, THINK_MODEL, _settings, armar_prompt

DEUDOR = {"nombre": "JUAN CARLOS PRUEBA", "monto": 1250000, "vencimiento": "2026-08-01",
          "ramo_nombre": "Automoviles", "aseguradora_nombre": "Sura", "dias_mora": 28,
          "intentos": 0, "numero_cuota": "3"}

LISTEN = {
    "nova": {},
    "flux": {"model": "flux-general-multi", "language_hints": ["es"]},
    "flux_eager": {"model": "flux-general-multi", "language_hints": ["es"],
                   "eot_threshold": 0.7, "eager_eot_threshold": 0.5},
}


async def probar(listen_cfg: dict) -> dict:
    prompt, greeting, keyterms = armar_prompt(DEUDOR, {}, modo_recepcion=False)
    settings = _settings(prompt, greeting, os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-celeste-es"),
                         keyterms, False, listen_cfg, 0.5)
    key = os.getenv("DEEPGRAM_API_KEY", "")
    assert key, "falta DEEPGRAM_API_KEY en .env"
    out = {"listen": settings["agent"]["listen"]["provider"]["model"], "think": THINK_MODEL,
           "prompt_chars": len(prompt), "reports": []}
    t0 = time.time()
    async with websockets.connect(DG_AGENT_URL, additional_headers={"Authorization": f"Token {key}"}) as dg:
        out["conectar_ms"] = round((time.time() - t0) * 1000)
        await dg.send(json.dumps(settings))
        t_settings = time.time()
        audio, fase, t_turno = 0, "saludo", 0.0
        silencio = b"\xff" * 160

        async def bombear():   # el agente espera audio entrante continuo (como Twilio)
            while True:
                await dg.send(silencio)
                await asyncio.sleep(0.02)

        bomba = asyncio.create_task(bombear())
        try:
            async with asyncio.timeout(40):
                async for msg in dg:
                    if isinstance(msg, bytes):
                        audio += len(msg)
                        if fase == "saludo" and "saludo_primer_audio_ms" not in out:
                            out["saludo_primer_audio_ms"] = round((time.time() - t_settings) * 1000)
                        if fase == "turno" and "turno_primer_audio_ms" not in out:
                            out["turno_primer_audio_ms"] = round((time.time() - t_turno) * 1000)
                        continue
                    ev = json.loads(msg)
                    t = ev.get("type")
                    if t == "SettingsApplied":
                        out["settings_applied_ms"] = round((time.time() - t_settings) * 1000)
                    elif t == "Error":
                        out["error"] = ev
                        break
                    elif t == "Warning":
                        out.setdefault("warnings", []).append(ev)
                    elif t == "ConversationText":
                        out.setdefault("texto", []).append(f'{ev.get("role")}: {ev.get("content")}')
                    elif t == "LatencyReport":
                        out["reports"].append({k: v for k, v in ev.items() if k != "type"})
                    elif t == "AgentAudioDone":
                        if fase == "saludo":
                            fase, t_turno = "turno", time.time()
                            await dg.send(json.dumps({"type": "InjectUserMessage",
                                                      "content": "si, con el habla"}))
                        else:
                            break
        except TimeoutError:
            out["timeout"] = True
        finally:
            bomba.cancel()
        out["audio_s"] = round(audio / 8000, 1)
    return out


async def main() -> int:
    modo = "flux_eager" if "eager" in sys.argv[1:] else ("flux" if "flux" in sys.argv[1:] else "nova")
    r = await probar(LISTEN[modo])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r.get("error") or r.get("audio_s", 0) < 1:
        print("FALLO: Deepgram rechazo los Settings o el agente no hablo")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
