"""Chequeos de la demo web de voz. No necesita servidor, Mongo, Redis ni Deepgram.

    python tests/test_demo_aria.py

Dos cosas que SI se pueden romper en silencio:
  1) El codec mu-law del navegador (demo_aria.html) tiene que producir
     exactamente lo mismo que el backend. Si alguien toca la tabla de
     exponentes, la voz se oye como ruido y nadie sabe por que.
  2) El deudor ficticio tiene que atravesar el prompt_builder real sin dejar
     "None" suelto: el modelo lee el prompt en voz alta tal cual ("expedida
     por Non" fue un bug real en produccion).
"""
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CLIENTE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "cobranza", "demo_aria_cliente.js")
BIAS, CLIP = 0x84, 32635


def _tabla_js() -> list:
    """La tabla de exponentes tal como la tiene el navegador."""
    txt = open(CLIENTE, encoding="utf-8").read()
    return json.loads("[" + re.search(r"var EXPLUT = \[(.*?)\];", txt, re.S).group(1) + "]")


def _enc(s: int, tab: list) -> int:
    """Puerto 1:1 de enc() en demo_aria_cliente.js."""
    sign = (s >> 8) & 0x80
    if sign:
        s = -s
    if s > CLIP:
        s = CLIP
    s += BIAS
    e = tab[(s >> 7) & 0xFF]
    m = (s >> (e + 3)) & 0x0F
    return (~(sign | (e << 4) | m)) & 0xFF


def _dec(u8: int) -> int:
    """Puerto 1:1 de la tabla DEC en demo_aria_cliente.js."""
    u = ~u8 & 0xFF
    t = (((u & 0x0F) << 3) + BIAS) << ((u & 0x70) >> 4)
    return (BIAS - t) if (u & 0x80) else (t - BIAS)


def test_tabla_exponentes():
    assert _tabla_js() == [0, 0, 1, 1] + [2] * 4 + [3] * 8 + [4] * 16 + \
                          [5] * 32 + [6] * 64 + [7] * 128


def test_decode_identico_al_backend():
    """DEC del navegador == audioop.ulaw2lin, byte por byte."""
    import audioop
    ref = audioop.ulaw2lin(bytes(range(256)), 2)
    esperado = [int.from_bytes(ref[i * 2:i * 2 + 2], "little", signed=True) for i in range(256)]
    assert [_dec(i) for i in range(256)] == esperado


def test_encode_es_mulaw_estandar():
    """No exige ser byte-identico a audioop (audioop redondea distinto en los
    bordes de segmento), si que el error de cuantizacion sea el mismo."""
    import audioop
    tab = _tabla_js()
    random.seed(7)
    muestras = [random.randint(-32768, 32767) for _ in range(20000)] + [0, 1, -1, 32767, -32768]
    pcm = b"".join(int(x).to_bytes(2, "little", signed=True) for x in muestras)

    distintos = sum(1 for a, b in zip(audioop.lin2ulaw(pcm, 2),
                                      bytes(_enc(x, tab) for x in muestras)) if a != b)
    assert distintos / len(muestras) < 0.01, f"{distintos} bytes difieren de audioop"

    peor_mio = max(abs(_dec(_enc(x, tab)) - x) for x in muestras)
    import struct
    ref = struct.unpack("<%dh" % len(muestras),
                        audioop.ulaw2lin(audioop.lin2ulaw(pcm, 2), 2))
    peor_ref = max(abs(v - s) for v, s in zip(ref, muestras))
    assert peor_mio == peor_ref, f"error max {peor_mio} vs {peor_ref} de audioop"


def test_deudor_falso_atraviesa_el_prompt_real():
    """50 deudores aleatorios por el prompt_builder de produccion: ninguno puede
    dejar 'None' ni un {placeholder} sin renderizar."""
    os.environ.setdefault("DEEPGRAM_API_KEY", "x")
    from cobranza.demo_router import _deudor_falso
    from cobranza.voice_agent import armar_prompt

    for _ in range(50):
        d = _deudor_falso("Maximiliano")
        prompt, saludo, keyterms = armar_prompt(d, {}, modo_recepcion=False)
        assert prompt and saludo
        assert "None" not in prompt, f"None en el prompt con {d}"
        assert "{" not in saludo, f"placeholder sin renderizar: {saludo}"
        assert "Maximiliano" in prompt
        assert len(keyterms) > 10


def test_deudor_falso_no_toca_datos_reales():
    from cobranza.demo_router import _deudor_falso
    d = _deudor_falso("Ana")
    assert d["demo"] is True
    assert str(d["_id"]).startswith("demo-")   # nunca un ObjectId de Mongo
    assert d["telefono"] == ""                 # send_whatsapp no tiene a donde ir
    assert 180_000 <= d["monto"] <= 2_400_000


def test_origen_allowlist():
    """Los WebSocket NO pasan por CORS: si esta lista falla, cualquier sitio
    puede embeber la demo y gastar la cuota de Deepgram a nombre de DPG."""
    from cobranza import demo_router as dr

    os.environ["DEMO_ARIA_ORIGINS"] = ""
    assert dr._origen_ok("https://cualquiera.com")      # sin configurar: abierto
    assert dr._origen_ok(None)

    os.environ["DEMO_ARIA_ORIGINS"] = "https://dpgseguros.com, https://www.dpgseguros.com/"
    assert dr._origen_ok("https://dpgseguros.com")
    assert dr._origen_ok("https://www.dpgseguros.com")  # la barra final no importa
    assert dr._origen_ok("HTTPS://DPGSEGUROS.COM")      # ni las mayusculas
    assert not dr._origen_ok("https://dpgseguros.com.evil.net")
    assert not dr._origen_ok("http://dpgseguros.com")   # http != https
    assert not dr._origen_ok("https://otra.com")
    assert not dr._origen_ok(None)                      # sin Origin, con lista puesta
    assert not dr._origen_ok("")
    del os.environ["DEMO_ARIA_ORIGINS"]


def test_widget_trae_el_cliente_adentro():
    """La landing carga UN script: widget.js tiene que traer conectar() y montar()."""
    from cobranza import demo_router as dr
    assert "AriaDemo.conectar" in dr._WIDGET and "AriaDemo.montar" in dr._WIDGET
    assert "AriaDemo.conectar" in dr._CLIENTE and "AriaDemo.montar" not in dr._CLIENTE


def test_cupo_diario():
    """El techo de gasto. Se prueba la rama de respaldo (sin Redis), que es la
    que corre si Upstash se cae — justo cuando MAS importa que haya tope."""
    import asyncio

    from cobranza import config_cache
    from cobranza import demo_router as dr

    original = config_cache.get_redis

    async def sin_redis():
        raise RuntimeError("redis caido")

    config_cache.get_redis = sin_redis
    try:
        os.environ["DEMO_ARIA_DIARIAS"] = "3"
        dr._dia_local.update(dia="", n=0)
        corridas = [asyncio.run(dr._cupo_diario_ok()) for _ in range(5)]
        assert corridas == [True, True, True, False, False], corridas

        # El contador se reinicia al cambiar el dia.
        dr._dia_local["dia"] = "1999-01-01"
        assert asyncio.run(dr._cupo_diario_ok()) is True

        # 0 = sin tope.
        os.environ["DEMO_ARIA_DIARIAS"] = "0"
        dr._dia_local.update(dia="", n=0)
        assert all(asyncio.run(dr._cupo_diario_ok()) for _ in range(5))
    finally:
        config_cache.get_redis = original
        os.environ.pop("DEMO_ARIA_DIARIAS", None)
        dr._dia_local.update(dia="", n=0)


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FALLO {nombre}: {e}")
    print("\n" + ("todo ok" if not fallos else f"{fallos} fallo(s)"))
    sys.exit(1 if fallos else 0)
