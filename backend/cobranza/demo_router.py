"""
demo_router.py — Demo web de ARIA: una landing cualquiera habla con el MISMO
motor de voz que las llamadas reales.

El bridge (voice_agent.run_voice_agent) ya habla el protocolo media-stream de
Twilio sobre WebSocket: JSON {event:"media", media:{payload:<base64 mulaw 8k>}}.
El navegador puede hablar exactamente eso, asi que la demo no duplica NADA del
motor: misma voz, mismo prompt de 3 capas, misma persona del tenant, mismo
barge-in, mismos watchdogs. Lo unico nuevo es un deudor FICTICIO y el apagado
de las escrituras (user_id="" -> sin orchestrator y sin alertas).

Para la landing (puede vivir en otro dominio):

    <div id="aria"></div>
    <script src="https://TU-BACKEND/demo/aria/widget.js"></script>
    <script>AriaDemo.montar("#aria", { code: "..." });</script>

O, si quiere dibujar su propia interfaz, /demo/aria/cliente.js expone solo
AriaDemo.conectar().

Endpoints:
  GET  /demo/aria             pagina de referencia (sirve tambien de iframe)
  GET  /demo/aria/cliente.js  cliente sin interfaz
  GET  /demo/aria/widget.js   cliente + interfaz lista
  WS   /demo/aria/ws?nombre=  el audio

Config:
  DEMO_ARIA_TENANT   user_id del tenant cuya persona se usa (default: DPG)
  DEMO_ARIA_ORIGINS  dominios autorizados, separados por coma. Los WebSocket NO
                     pasan por CORS, asi que esta lista es el candado real
                     contra que otro sitio embeba la demo. Vacio = cualquiera.
  DEMO_ARIA_CODE     si esta definido, el cliente debe mandar ?code=...
  DEMO_ARIA_MAX      sesiones simultaneas (default 3)
  DEMO_ARIA_DIARIAS  techo de sesiones por dia (default 60; 0 = sin tope)
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

# Import al arrancar, no dentro del handler: la primera visita pagaba ~2 s de
# import (websockets + pipecat) ANTES de abrir el socket con Deepgram.
from cobranza.voice_agent import run_voice_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo/aria", tags=["demo"])

_AQUI = Path(__file__).parent
_PAGINA = _AQUI / "demo_aria.html"
_CLIENTE = (_AQUI / "demo_aria_cliente.js").read_text(encoding="utf-8")
# widget.js = cliente + interfaz, para que la landing cargue UN solo script.
_WIDGET = _CLIENTE + "\n" + (_AQUI / "demo_aria_widget.js").read_text(encoding="utf-8")

_JS = {"Cache-Control": "public, max-age=300"}
_MAX = int(os.getenv("DEMO_ARIA_MAX", "3"))
_vivas = 0   # ponytail: contador en proceso; con varias replicas el tope es por replica
_dia_local = {"dia": "", "n": 0}   # respaldo del cupo diario si Redis no responde


def _hoy() -> str:
    import pytz
    from datetime import datetime
    return datetime.now(pytz.timezone("America/Bogota")).strftime("%Y-%m-%d")


async def _cupo_diario_ok() -> bool:
    """Techo de gasto: N sesiones por dia y se acabo.

    Cuenta en Redis —el mismo que ya usa config_cache— para que el contador
    sobreviva a los redeploys (Railway redespliega seguido) y valga para todas
    las replicas. Si Redis no responde, cae a un contador en proceso: sigue
    habiendo tope, solo que por replica y hasta el proximo redeploy.
    """
    tope = int(os.getenv("DEMO_ARIA_DIARIAS", "60"))
    if tope <= 0:
        return True
    hoy = _hoy()
    try:
        from cobranza.config_cache import get_redis
        r = await get_redis()
        clave = f"demo:aria:sesiones:{hoy}"
        n = await r.incr(clave)
        if n == 1:
            await r.expire(clave, 172800)   # 48 h: la llave se limpia sola
    except Exception:
        logger.warning("[demo] sin Redis para el cupo diario — contando en proceso")
        if _dia_local["dia"] != hoy:
            _dia_local.update(dia=hoy, n=0)
        _dia_local["n"] += 1
        n = _dia_local["n"]
    if n > tope:
        logger.warning("[demo] cupo diario agotado (%d/%d el %s)", n, tope, hoy)
        return False
    logger.info("[demo] sesion %d/%d del %s", n, tope, hoy)
    return True


# ── Deudor ficticio ───────────────────────────────────────────────────────────
# Datos plausibles de la cartera de DPG, pero inventados: ninguna consulta a
# Softseguros ni a Mongo. El telefono va vacio a proposito (send_whatsapp
# ademas queda muerto porque no hay orchestrator).
# Solo Seguros del Estado: la demo se presenta en su curso de innovacion.
_CARTERA = [
    ("Autos", "Seguros del Estado", "Mazda CX-30 placa KJT482"),
    ("Hogar", "Seguros del Estado", "Apartamento en Chapinero"),
    ("Vida", "Seguros del Estado", ""),
    ("Autos", "Seguros del Estado", "Chevrolet Onix placa HSR119"),
]


def _deudor_falso(nombre: str) -> dict:
    ramo, aseguradora, riesgo = random.choice(_CARTERA)
    monto = random.randrange(180, 2400) * 1000          # 180.000 – 2.400.000
    vencio = date.today() - timedelta(days=random.randint(8, 42))
    return {
        "_id": f"demo-{uuid.uuid4().hex[:8]}",
        "nombre": nombre,
        "telefono": "",
        "monto": float(monto),
        "vencimiento": vencio.isoformat(),
        "fecha_limite_pago": (vencio + timedelta(days=30)).isoformat(),
        "ramo_nombre": ramo,
        "aseguradora_nombre": aseguradora,
        "objeto_asegurado": riesgo,
        "numero_poliza": f"{random.randint(100000, 999999)}",
        "numero_cuota": str(random.randint(2, 9)),
        "estado_cartera": "Vencida",
        "estado_poliza_nombre": "Vigente",
        "fecha_fin": (date.today() + timedelta(days=random.randint(60, 300))).isoformat(),
        "forma_pago": "Mensual",
        "vendedores_nombre": "Juan Diego Pulido",
        "intentos": 0,
        "proximo_intento_numero": 1,
        "demo": True,
    }


def _tenant_id() -> str:
    return os.getenv("DEMO_ARIA_TENANT", "69bcd9bb6e35d53880364535")


def _origenes() -> list:
    return [o.strip().rstrip("/").lower()
            for o in os.getenv("DEMO_ARIA_ORIGINS", "").split(",") if o.strip()]


def _origen_ok(origin: str | None) -> bool:
    """Los WebSocket NO pasan por CORS: sin esta lista, cualquier sitio puede
    embeber la demo y gastar la cuota de Deepgram a nombre de DPG."""
    permitidos = _origenes()
    if not permitidos:
        return True                      # sin configurar: modo abierto (dev)
    if not origin:
        return False                     # cliente no-navegador con lista puesta
    return origin.rstrip("/").lower() in permitidos


async def _calentar():
    # Precalienta el config del tenant mientras el visitante escribe su nombre.
    # En frio cuesta ~6 s (Redis vacio + Mongo) y se los comia ENTEROS el
    # silencio previo al saludo, porque run_voice_agent no arranca sin el.
    try:
        from cobranza.config_cache import get_tenant_config
        await get_tenant_config(_tenant_id())
    except Exception:
        logger.debug("[demo] precalentamiento del config fallo", exc_info=True)


@router.get("")
async def pagina():
    asyncio.create_task(_calentar())
    return FileResponse(_PAGINA, media_type="text/html")


@router.get("/cliente.js")
async def cliente_js():
    asyncio.create_task(_calentar())
    return Response(_CLIENTE, media_type="application/javascript", headers=_JS)


@router.get("/widget.js")
async def widget_js():
    asyncio.create_task(_calentar())
    return Response(_WIDGET, media_type="application/javascript", headers=_JS)


@router.websocket("/ws")
async def demo_ws(websocket: WebSocket):
    global _vivas
    # Se acepta PRIMERO y se cierra despues con el codigo real: si se rechaza
    # antes del accept, Starlette responde un 403 HTTP y el navegador solo ve
    # "error de conexion" — ni el visitante sabe que la demo esta ocupada, ni
    # quien integra la landing sabe que le falta su dominio en la allowlist.
    await websocket.accept()
    origin = websocket.headers.get("origin")
    if not _origen_ok(origin):
        logger.warning("[demo] origen rechazado: %r", origin)
        await websocket.close(1008, "origen no autorizado")
        return
    code = os.getenv("DEMO_ARIA_CODE", "")
    if code and websocket.query_params.get("code") != code:
        await websocket.close(1008, "codigo invalido")
        return
    if _vivas >= _MAX:
        await websocket.close(1013, "demo ocupada")
        return
    # El cupo se consume DESPUES del tope de simultaneas: a quien rebota por
    # concurrencia no se le gasta una sesion del dia.
    if not await _cupo_diario_ok():
        await websocket.close(1013, "cupo diario agotado")
        return

    nombre = (websocket.query_params.get("nombre") or "").strip()[:60] or "Invitado"
    _vivas += 1
    call_sid = f"DEMO{uuid.uuid4().hex[:12]}"   # no empieza por "CA": sin hangup REST a Twilio
    try:
        from cobranza.config_cache import get_tenant_config

        tenant = await get_tenant_config(_tenant_id()) or {}
        deudor = _deudor_falso(nombre)
        logger.info("[demo] %s origen=%s nombre=%r %s/%s $%s", call_sid, origin, nombre,
                    deudor["ramo_nombre"], deudor["aseguradora_nombre"], deudor["monto"])
        await run_voice_agent(
            websocket=websocket, call_sid=call_sid, debtor=deudor,
            user_id="",                      # sin orchestrator ni alertas: la demo no escribe
            stream_id="demo", tenant_config=tenant, captions=True,
        )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("[demo] %s fallo", call_sid)
    finally:
        _vivas -= 1
        try:
            await websocket.close()
        except Exception:
            pass
