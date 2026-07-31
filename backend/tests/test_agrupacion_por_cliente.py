"""
test_agrupacion_por_cliente.py — un solo intento por CLIENTE, no por cuota.

Cada fila de `debtors` es una cuota. El 48% de la cartera de DPG tiene varias
(peor caso real: 24 cuotas de un mismo cliente), así que sin agrupar esa
persona recibía 24 llamadas y 24 plantillas — y se rompía el máximo de 1
contacto por día de la Ley 2300.

Se prueba la selección pura (qué cuota lidera cada cliente) y el bloque de
prompt que anuncia el estado de cartera completo.
"""
from bson import ObjectId

from cobranza.prompt_builder import _cartera_multiple_block


def _cuota(doc: str, *, mora: int, tel: str = "+573001112233") -> dict:
    """Cuota de `doc`. `mora` mayor = más prioritaria para el informe."""
    return {
        "_id": ObjectId(),
        "cliente_documento": doc,
        "telefono": tel,
        "dias_mora": mora,
    }


def _lideres(due: list) -> list:
    """Misma agrupación que dispatch_intentos_job: 1 líder por cliente,
    conservando el orden de prioridad con que llega `due`."""
    por_cliente: dict = {}
    for d in due:
        k = str(d.get("cliente_documento") or d.get("telefono") or d["_id"])
        por_cliente.setdefault(k, []).append(d)
    return [g[0] for g in por_cliente.values()]


# ── Agrupación ────────────────────────────────────────────────────────────────

def test_un_solo_lider_por_cliente():
    """El caso real: 24 cuotas de un cliente → UNA llamada."""
    due = [_cuota("900123", mora=i) for i in range(24)]
    assert len(_lideres(due)) == 1


def test_lidera_la_cuota_de_mayor_prioridad():
    """`due` llega ordenado por prioridad; el líder debe ser el primero."""
    primero, segundo = _cuota("900123", mora=90), _cuota("900123", mora=10)
    assert _lideres([primero, segundo])[0]["_id"] == primero["_id"]


def test_clientes_distintos_no_se_mezclan():
    due = [_cuota("900123", mora=5), _cuota("800999", mora=3, tel="+573009998877")]
    assert len(_lideres(due)) == 2


def test_sin_documento_agrupa_por_telefono():
    """Cargas manuales sin documento: el teléfono identifica a la persona —
    llamar dos veces al mismo número el mismo día es lo que hay que evitar."""
    a, b = _cuota("", mora=5), _cuota("", mora=2)
    a["cliente_documento"] = b["cliente_documento"] = None
    assert len(_lideres([a, b])) == 1


def test_sin_documento_ni_telefono_no_colapsa_clientes():
    """Sin ningún identificador, cada fila es su propio grupo: mejor una
    llamada de más que silenciar a un cliente distinto por error."""
    a, b = _cuota("", mora=5), _cuota("", mora=2)
    for x in (a, b):
        x["cliente_documento"] = None
        x["telefono"] = None
    assert len(_lideres([a, b])) == 2


# ── Diálogo ───────────────────────────────────────────────────────────────────

def test_prompt_sin_bloque_cuando_hay_una_sola_cuota():
    assert _cartera_multiple_block(1) == ""
    assert _cartera_multiple_block(0) == ""


def test_prompt_anuncia_estado_de_cartera_por_correo_o_whatsapp():
    b = _cartera_multiple_block(24)
    assert "24" in b
    assert "ESTADO DE CARTERA" in b
    assert "correo" in b and "WhatsApp" in b
    assert "NO recites una por una" in b  # no enumerar 24 pólizas por teléfono
