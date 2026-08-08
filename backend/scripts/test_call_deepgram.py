"""Llamada de PRUEBA con la voz colombiana de Deepgram (rama feat/voz-deepgram).

Puente Twilio Media Streams <-> Deepgram Voice Agent API:
  Twilio manda mulaw 8k base64; se reenvia crudo al agente de Deepgram (que
  escucha con nova-3 es, piensa con Gemini y habla con aura-2 celeste/gloria).
  El audio del agente vuelve ya en mulaw 8k -> directo al stream de Twilio.

Usa el deudor CLON (is_test=true, telefono del staff) y el MISMO prompt de 3
capas de produccion (prompt_builder), para que la unica variable sea la voz.
En llamada: decir "cambia la voz" alterna celeste <-> gloria (UpdateSpeak).

Modos:
  python scripts/test_call_deepgram.py serve            # bridge ws en :8765
  python scripts/test_call_deepgram.py selftest         # simula Twilio contra el bridge
  python scripts/test_call_deepgram.py call <wss-url>   # marca al deudor de prueba
"""
import asyncio
import base64
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
except Exception:
    pass

import websockets
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("test_call_deepgram")

USER_ID = "69bcd9bb6e35d53880364535"
TEL_PRUEBA = "+573123528153"
PUERTO = 8765
DG_URL = "wss://agent.deepgram.com/v1/agent/converse"
VOCES = ["aura-2-celeste-es", "aura-2-gloria-es"]


def _db():
    return AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")]


async def _prompt_y_saludo() -> tuple:
    """El prompt de 3 capas REAL para el deudor clon (mismas piezas que voice_pipecat)."""
    from cobranza.es_numbers import pesos_en_palabras
    from cobranza.prompt_builder import (
        assemble_system_prompt, nombre_dos, render_greeting, resolve_persona,
    )

    db = _db()
    debtor = await db.debtors.find_one({"user_id": USER_ID, "telefono": TEL_PRUEBA, "is_test": True})
    if not debtor:
        raise SystemExit("no existe el deudor clon — correr clonar_deudor.py primero")
    cfg = await db.tenant_configs.find_one({"user_id": USER_ID}) or {}
    db.client.close()

    persona = resolve_persona(cfg)
    first_name = nombre_dos(debtor.get("nombre") or "")
    monto_natural = pesos_en_palabras(float(debtor.get("monto") or 0))
    runtime_block = (
        "DATOS DE ESTA LLAMADA (datos REALES y exactos de ESTE deudor — usalos directo):\n"
        f"- Nombre: {debtor.get('nombre')}\n"
        f"- Dirigete a la persona por su nombre: '{first_name}'. "
        "NUNCA uses 'senor', 'senora', 'don' ni 'dona' — solo el nombre.\n"
        f"- Deuda pendiente: {monto_natural}\n"
        f"- Vencimiento: {str(debtor.get('vencimiento'))[:10]}\n"
        f"- Tipo de poliza: {debtor.get('ramo_nombre')}\n"
        f"- Aseguradora: {debtor.get('aseguradora_nombre')}\n\n"
    )
    prompt = assemble_system_prompt(
        persona,
        runtime_block=runtime_block,
        first_name=first_name,
        ramo=debtor.get("ramo_nombre") or "seguros",
        monto_natural=monto_natural,
        aseguradora=debtor.get("aseguradora_nombre") or "",
        riesgo=str(debtor.get("objeto_asegurado") or "").strip(),
        modalidad=str(debtor.get("forma_pago") or "").strip(),
        intento=1,
        dias_mora=int(debtor.get("dias_mora") or 0),
        numero_cuota=str(debtor.get("numero_cuota") or ""),
    )
    prompt += (
        "\n\nMODO PRUEBA: esta es una llamada de DEMOSTRACION con el equipo tecnico "
        "(no un deudor real). Sigue el guion normal de cobranza. Si te piden 'cambia la voz', "
        "llama la funcion cambiar_voz y sigue la conversacion como si nada."
        "\n\nESTILO DE HABLA (paisa cafetero, calido pero profesional): en una cascada el "
        "TTS pronuncia EXACTAMENTE lo que escribes, asi que el acento se construye con las "
        "palabras. Usa con naturalidad (sin exagerar, maximo una por frase): 'pues', "
        "'¿cierto?', 'hagale pues', 'listo pues', 'con mucho gusto', 'de una', 'qué pena "
        "con usted', 'me le cuenta'. SIEMPRE de usted, nunca tuteo. Frases cortas, con "
        "comas donde va la pausa. Nada de jerga que suene a confianzudo ('parce', 'mijo' "
        "PROHIBIDOS — es una llamada de cobranza de una aseguradora)."
    )
    saludo = render_greeting(persona, first_name)
    # "ARIA" en mayusculas hace que el TTS lo lea como sigla/raro; "Aria" se
    # pronuncia como nombre. Solo para el texto que va a la voz.
    return prompt.replace("ARIA", "Aria"), saludo.replace("ARIA", "Aria")


def _settings(prompt: str, saludo: str, voz: str) -> dict:
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "mulaw", "sample_rate": 8000},
            "output": {"encoding": "mulaw", "sample_rate": 8000, "container": "none"},
        },
        "agent": {
            # sin agent.language: esta deprecado y choca con listen.language=multi
            # Historial de STT en llamadas reales (audio telefonico 8k colombiano):
            #   nova-3 + es    -> basura en espanol ("el reemplacito... el mono")
            #   nova-3 + multi -> alucina idiomas ("Hello Mister <hindi>")
            # nova-2 monolingue es el modelo maduro de espanol de Deepgram.
            "listen": {"provider": {"type": "deepgram", "model": "nova-2", "language": "es"}},
            "think": {
                # flash-lite (del payload de ejemplo) se rendia al primer "no";
                # el guion de cobranza necesita un modelo completo.
                "provider": {"type": "google", "model": "gemini-3.5-flash"},
                "prompt": prompt,
                "functions": [
                    {"name": "end_call",
                     "description": "Cuelga la llamada cuando la gestion termino (despidete ANTES de llamarla).",
                     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}},
                                    "required": ["reason"]}},
                    {"name": "cambiar_voz",
                     "description": "Cambia la voz del agente (celeste <-> gloria) cuando el cliente lo pida.",
                     "parameters": {"type": "object", "properties": {}}},
                    # Stubs: el prompt de produccion las referencia; aqui no tienen efecto.
                    {"name": "verify_identity",
                     "description": "Registra que el cliente confirmo o nego ser el titular.",
                     "parameters": {"type": "object", "properties": {"utterance": {"type": "string"}},
                                    "required": ["utterance"]}},
                    {"name": "send_whatsapp",
                     "description": "Envia la informacion de pago por WhatsApp (simulado en la prueba).",
                     "parameters": {"type": "object", "properties": {"message": {"type": "string"}}}},
                ],
            },
            "speak": {"provider": {"type": "deepgram", "model": voz}},
            "greeting": saludo,
        },
    }


async def _bridge(tw) -> None:
    """Una llamada de Twilio <-> una sesion del Voice Agent."""
    prompt, saludo = await _prompt_y_saludo()
    voz = {"actual": VOCES[0]}
    stream_sid = {"sid": None}
    pre_start = bytearray()   # audio de DG llegado ANTES del start de Twilio
    colgar = {"pendiente": False, "bytes_pend": 0}
    saludo_hecho = {"ok": False}

    async with websockets.connect(
        DG_URL, additional_headers={"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}"}
    ) as dg:
        await dg.send(json.dumps(_settings(prompt, saludo, voz["actual"])))

        async def twilio_a_dg():
            async for raw in tw:
                m = json.loads(raw)
                ev = m.get("event")
                if ev == "start":
                    stream_sid["sid"] = m["start"]["streamSid"]
                    log.info("[tw] start %s", stream_sid["sid"])
                    if pre_start:
                        # el saludo que DG genero durante el handshake de Twilio;
                        # sin esto se perdian los primeros chunks ("se corta el ARIA")
                        await tw.send(json.dumps({
                            "event": "media", "streamSid": stream_sid["sid"],
                            "media": {"payload": base64.b64encode(bytes(pre_start)).decode()},
                        }))
                        log.info("[tw] flush pre-start: %d bytes", len(pre_start))
                        pre_start.clear()
                elif ev == "media":
                    await dg.send(base64.b64decode(m["media"]["payload"]))
                elif ev == "stop":
                    log.info("[tw] stop")
                    return

        async def dg_a_twilio():
            async for msg in dg:
                if isinstance(msg, bytes):
                    if stream_sid["sid"]:
                        await tw.send(json.dumps({
                            "event": "media", "streamSid": stream_sid["sid"],
                            "media": {"payload": base64.b64encode(msg).decode()},
                        }))
                        if colgar["pendiente"]:
                            colgar["bytes_pend"] += len(msg)
                    else:
                        pre_start.extend(msg)
                    continue
                ev = json.loads(msg)
                t = ev.get("type")
                # clear SOLO despues del saludo. Historia: el flush siempre-activo
                # cortaba el saludo cuando el cliente contestaba "alo" encima
                # (llamada 2); quitarlo del todo embotellaba la cola de Twilio y
                # cada turno llegaba mas atrasado y repetido (llamada 4, "se
                # traba"). Punto medio: el saludo se reproduce completo si o si;
                # despues, hablar bota el audio viejo y la respuesta llega fresca.
                if t == "UserStartedSpeaking":
                    if saludo_hecho["ok"] and stream_sid["sid"] and not colgar["pendiente"]:
                        await tw.send(json.dumps({"event": "clear", "streamSid": stream_sid["sid"]}))
                elif t == "ConversationText":
                    log.info("[%s] %s", ev.get("role"), (ev.get("content") or "")[:120])
                elif t == "FunctionCallRequest":
                    for f in ev.get("functions", []):
                        contenido = "ok"
                        if f["name"] == "cambiar_voz":
                            voz["actual"] = VOCES[1] if voz["actual"] == VOCES[0] else VOCES[0]
                            await dg.send(json.dumps({
                                "type": "UpdateSpeak",
                                "speak": {"provider": {"type": "deepgram", "model": voz["actual"]}},
                            }))
                            contenido = "voz cambiada a " + voz["actual"].split("-")[2]
                            log.info("[fn] cambiar_voz -> %s", voz["actual"])
                        elif f["name"] == "send_whatsapp":
                            contenido = "mensaje enviado (simulado, es una prueba)"
                        elif f["name"] == "end_call":
                            # Llamada 3: el modelo puso la despedida DENTRO del
                            # reason y colgo sin decirla. No se cierra aqui: se le
                            # exige despedirse y se cuelga tras ESE audio (ver
                            # AgentAudioDone abajo).
                            log.info("[fn] end_call: %s", f.get("arguments"))
                            colgar["pendiente"] = True
                            await dg.send(json.dumps({
                                "type": "FunctionCallResponse", "id": f.get("id"),
                                "name": f["name"],
                                "content": ("ok. AHORA despidete en voz alta con una "
                                            "frase corta; la llamada se cierra despues "
                                            "de tu despedida."),
                            }))
                            continue
                        await dg.send(json.dumps({
                            "type": "FunctionCallResponse", "id": f.get("id"),
                            "name": f["name"], "content": contenido,
                        }))
                elif t == "AgentAudioDone":
                    saludo_hecho["ok"] = True
                    if colgar["pendiente"]:
                        # despedida generada; esperar lo que Twilio aun tiene en
                        # cola (DG manda el audio mas rapido de lo que se reproduce)
                        await asyncio.sleep(colgar["bytes_pend"] / 8000 + 1.0)
                        log.info("[fn] despedida reproducida — colgando")
                        return
                elif t == "Error":
                    log.error("[dg] %s", ev)
                    return

        tareas = [asyncio.create_task(twilio_a_dg()), asyncio.create_task(dg_a_twilio())]
        try:
            await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t_ in tareas:
                t_.cancel()


async def serve() -> None:
    async def handler(ws):
        try:
            await _bridge(ws)
        except Exception:
            log.exception("bridge fallo")
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    async with websockets.serve(handler, "127.0.0.1", PUERTO):
        log.info("bridge listo en ws://127.0.0.1:%d", PUERTO)
        await asyncio.Future()


async def selftest() -> int:
    """Simula a Twilio: start + 10s de silencio; exige audio del agente de vuelta."""
    audio = 0
    async with websockets.connect("ws://127.0.0.1:%d" % PUERTO) as ws:
        await ws.send(json.dumps({"event": "start", "start": {"streamSid": "MZtest"}}))
        silencio = base64.b64encode(b"\xff" * 160).decode()  # 20ms mulaw

        async def bombear():
            for _ in range(500):  # ~10s
                await ws.send(json.dumps({"event": "media", "media": {"payload": silencio}}))
                await asyncio.sleep(0.02)

        bomba = asyncio.create_task(bombear())
        try:
            async with asyncio.timeout(15):
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("event") == "media":
                        audio += len(base64.b64decode(m["media"]["payload"]))
                        if audio > 8000 * 3:  # 3s de saludo recibidos
                            break
        except TimeoutError:
            pass
        bomba.cancel()
    print("selftest: %d bytes de audio del agente (%.1fs)" % (audio, audio / 8000))
    assert audio > 8000 * 2, "el agente no hablo — revisar logs del bridge"
    print("selftest OK")
    return 0


def call(ws_url: str, destino: str = TEL_PRUEBA) -> None:
    from twilio.rest import Client
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        '<Connect><Stream url="%s" /></Connect></Response>' % ws_url
    )
    c = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    llamada = c.calls.create(to=destino, from_="+576063470078", twiml=twiml, timeout=25)
    print("llamando a %s — call_sid=%s" % (destino, llamada.sid))


async def call_prod(base_https: str, destino: str = TEL_PRUEBA) -> None:
    """Marca por el flujo REAL de produccion: url=webhook (TwiML+firma+ws+run_bot).
    Inserta el mapping call_sid->deudor clon que el ws de run_bot busca.
    Requiere el venv del backend (motor + twilio) y voice_server_local corriendo."""
    from twilio.rest import Client

    db = _db()
    debtor = await db.debtors.find_one({"user_id": USER_ID, "telefono": TEL_PRUEBA, "is_test": True})
    if not debtor:
        raise SystemExit("no existe el deudor clon")

    c = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    llamada = c.calls.create(
        to=destino, from_="+576063470078",
        url=f"{base_https}/api/cobranza/voice/webhook", method="POST",
        timeout=25,
    )
    # El webhook llega cuando CONTESTAN (varios segundos) — el mapping alcanza.
    from datetime import datetime, timezone
    await db.cobranza_calls_in_progress.insert_one({
        "call_sid": llamada.sid, "user_id": USER_ID,
        "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
        "debtor_phone": destino, "started_at": datetime.now(timezone.utc),
    })
    print("llamando (flujo prod) a %s — call_sid=%s" % (destino, llamada.sid))
    db.client.close()


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if modo == "serve":
        asyncio.run(serve())
    elif modo == "selftest":
        sys.exit(asyncio.run(selftest()))
    elif modo == "call":
        call(sys.argv[2], *sys.argv[3:4])
    elif modo == "call-prod":
        asyncio.run(call_prod(sys.argv[2], *sys.argv[3:4]))
    else:
        sys.exit("modo desconocido: " + modo)
