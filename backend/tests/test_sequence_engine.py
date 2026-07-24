"""
test_sequence_engine.py — núcleo puro de la máquina de intentos del informe ARIA.

Fechas de referencia (julio 2026, Colombia):
  vie 10 · sáb 11 · dom 12 · lun 13 · mar 14 … vie 17 · lun 20 (FESTIVO) · mar 21
"""
from datetime import date, datetime

import pytz

from cobranza.sequence_engine import (
    DEFAULT_FRANJAS,
    _franjas_del_dia,
    _stagger_slot,
    compute_proximo_intento,
    is_within_tenant_franjas,
    prioridad_informe,
)

CO = pytz.timezone("America/Bogota")
HOY = date(2026, 7, 14)  # martes hábil


def _co(dt_utc: datetime) -> tuple:
    """(fecha, HH:MM) del intento en hora Colombia."""
    local = dt_utc.astimezone(CO)
    return local.date(), local.strftime("%H:%M")


# ── compute_proximo_intento ────────────────────────────────────────────────────

def test_L1_un_habil_antes_del_ancla():
    d = {"estado": "pendiente", "intentos": 0, "fecha_compromiso": "2026-07-16"}
    verdict, at = compute_proximo_intento(d, {}, {}, today=HOY)
    assert verdict == "cita"
    assert _co(at) == (date(2026, 7, 15), "09:00")  # jueves 16 − 1 hábil = mié 15, 9am


def test_L2_dia_del_ancla_y_L3_mas_dos_habiles():
    d = {"estado": "sin_contacto", "intentos": 1, "fecha_compromiso": "2026-07-16"}
    verdict, at = compute_proximo_intento(d, {}, {}, today=HOY)
    assert (verdict, _co(at)[0]) == ("cita", date(2026, 7, 16))  # L2 = día del ancla
    d["intentos"] = 2
    verdict, at = compute_proximo_intento(d, {}, {}, today=HOY)
    # L3 = jue 16 + 2 hábiles: vie 17, (finde), lun 20 FESTIVO → mar 21
    assert (verdict, _co(at)[0]) == ("cita", date(2026, 7, 21))


def test_regla_del_viernes_en_L1():
    # vence lunes 13 → L1 (−1 hábil) = viernes 10 (pero ya pasó vs HOY=mar 14 → HOY)
    d = {"estado": "pendiente", "intentos": 0, "fecha_compromiso": "2026-07-20"}
    # ancla lunes 20 FESTIVO − 1 hábil = viernes 17
    verdict, at = compute_proximo_intento(d, {}, {}, today=HOY)
    assert (verdict, _co(at)[0]) == ("cita", date(2026, 7, 17))


def test_backlog_vencido_se_cita_hoy():
    """Arranque: cuota vencida hace meses → la cita es HOY, no en el pasado."""
    d = {"estado": "pendiente", "intentos": 0, "fecha_compromiso": "2026-04-13"}
    verdict, at = compute_proximo_intento(d, {}, {}, today=HOY)
    assert (verdict, _co(at)[0]) == ("cita", HOY)


def test_ancla_por_vencimiento_si_config_lo_pide():
    d = {"estado": "pendiente", "intentos": 0,
         "fecha_compromiso": "2026-08-01", "vencimiento": "2026-07-16"}
    _, at = compute_proximo_intento(d, {"agendar_por": "fecha_pago"}, {}, today=HOY)
    assert _co(at)[0] == date(2026, 7, 15)  # ancla = vencimiento, no compromiso


def test_max_intentos_agota():
    d = {"estado": "sin_contacto", "intentos": 3, "fecha_compromiso": "2026-07-16"}
    assert compute_proximo_intento(d, {}, {}, today=HOY) == ("agotado", None)
    # config del tenant puede subirlo
    verdict, _ = compute_proximo_intento(d, {"max_intentos": 5}, {}, today=HOY)
    assert verdict == "cita"


def test_reagendado_usa_la_fecha_del_cliente():
    d = {"estado": "reagendado", "intentos": 2, "fecha_compromiso": "2026-07-16",
         "fecha_reagendada": "2026-07-24"}
    verdict, at = compute_proximo_intento(d, {}, {}, today=HOY)
    assert (verdict, _co(at)[0]) == ("cita", date(2026, 7, 24))
    # y NO cuenta el max (reemplaza el siguiente intento, informe §3)
    d["intentos"] = 3
    verdict, _ = compute_proximo_intento(d, {}, {}, today=HOY)
    assert verdict == "cita"


def test_franja_inicio_configurable():
    d = {"estado": "pendiente", "intentos": 0, "fecha_compromiso": "2026-07-16"}
    horarios = {"franjas": [["10:30", "12:00"]]}
    _, at = compute_proximo_intento(d, {}, horarios, today=HOY)
    assert _co(at) == (date(2026, 7, 15), "10:30")


# ── prioridad del informe ──────────────────────────────────────────────────────

def test_prioridad_mayor_mora_primero():
    # DPG: mayor mora primero; vence_hoy/preventiva (mora 0 o negativa) al final.
    hoy = date(2026, 7, 14)
    vence_hoy = {"vencimiento": "2026-07-14", "dias_mora": 0}
    preventiva = {"vencimiento": "2026-07-15", "dias_mora": 0}
    mora_alta = {"vencimiento": "2026-04-01", "dias_mora": 104}
    mora_baja = {"vencimiento": "2026-07-01", "dias_mora": 13}
    orden = sorted([mora_baja, preventiva, mora_alta, vence_hoy],
                   key=lambda d: prioridad_informe(d, hoy, set()))
    assert orden == [mora_alta, mora_baja, vence_hoy, preventiva]


def test_prioridad_mora_fresca_ignora_dias_mora_stale():
    # dias_mora persistido stale (0) pero vencimiento dice 100 días → gana mora fresca.
    hoy = date(2026, 7, 14)
    stale = {"vencimiento": "2026-04-05", "dias_mora": 0}     # real ≈ 100
    reciente = {"vencimiento": "2026-07-10", "dias_mora": 999}  # real = 4
    orden = sorted([reciente, stale], key=lambda d: prioridad_informe(d, hoy, set()))
    assert orden == [stale, reciente]


# ── escalonado de la jornada en tandas ──────────────────────────────────────────

def test_stagger_arranca_en_hora_inicio_y_reparte_en_tandas():
    # Defaults: 11:00, tanda 5, cada 5 min. Los primeros 5 → 11:00, los 5
    # siguientes → 11:05, etc. Franjas default [09-12 / 14-16].
    assert _co(_stagger_slot(HOY, 0, {}, {})) == (HOY, "11:00")
    assert _co(_stagger_slot(HOY, 4, {}, {})) == (HOY, "11:00")   # misma tanda
    assert _co(_stagger_slot(HOY, 5, {}, {})) == (HOY, "11:05")   # tanda 2
    assert _co(_stagger_slot(HOY, 9, {}, {})) == (HOY, "11:05")
    assert _co(_stagger_slot(HOY, 10, {}, {})) == (HOY, "11:10")  # tanda 3


def test_stagger_salta_el_hueco_de_almuerzo():
    # Desde 11:00 quedan 60 min en la franja de la mañana (11:00–12:00) = 12
    # tandas de 5 min (índices de tanda 0..11, hasta 11:55). La tanda 12 (offset
    # 60 min) debe caer al inicio de la franja de la tarde: 14:00, no 12:00.
    # idx de tanda 12 → idx de deudor = 12 * tanda(5) = 60.
    assert _co(_stagger_slot(HOY, 60, {}, {})) == (HOY, "14:00")
    assert _co(_stagger_slot(HOY, 65, {}, {})) == (HOY, "14:05")


def test_stagger_parametros_configurables_por_tenant():
    vol = {"hora_inicio_jornada": "10:00", "llamadas_por_tanda": 2, "intervalo_tandas_min": 10}
    hor = {"franjas": [["08:00", "18:00"]]}
    assert _co(_stagger_slot(HOY, 0, hor, vol)) == (HOY, "10:00")
    assert _co(_stagger_slot(HOY, 1, hor, vol)) == (HOY, "10:00")  # tanda de 2
    assert _co(_stagger_slot(HOY, 2, hor, vol)) == (HOY, "10:10")  # +10 min


def test_stagger_satura_al_cierre_si_se_pasa_el_volumen():
    # Franja única corta: 11:00–11:10 (10 min) → 2 tandas (11:00, 11:05). Un
    # índice que se pasa se satura al final del cierre (11:09), no desborda al día.
    hor = {"franjas": [["11:00", "11:10"]]}
    assert _co(_stagger_slot(HOY, 1000, hor, {})) == (HOY, "11:09")


def test_franjas_del_dia_respeta_festivo_y_finde():
    assert _franjas_del_dia(HOY, {}) == [(540, 720), (840, 960)]  # 09-12 / 14-16
    assert _franjas_del_dia(date(2026, 7, 20), {}) == []          # lunes festivo
    assert _franjas_del_dia(date(2026, 7, 11), {}) == []          # sábado sin franja


# ── franjas del tenant ─────────────────────────────────────────────────────────

def _utc(y, m, d, h, mi):
    return CO.localize(datetime(y, m, d, h, mi)).astimezone(pytz.utc)


def test_franjas_default_del_informe():
    assert DEFAULT_FRANJAS == [["09:00", "12:00"], ["14:00", "16:00"]]
    assert is_within_tenant_franjas({}, _utc(2026, 7, 14, 10, 0)) is True    # 10am mar
    assert is_within_tenant_franjas({}, _utc(2026, 7, 14, 13, 0)) is False   # almuerzo
    assert is_within_tenant_franjas({}, _utc(2026, 7, 14, 15, 30)) is True   # 3:30pm
    assert is_within_tenant_franjas({}, _utc(2026, 7, 14, 18, 0)) is False   # 6pm
    assert is_within_tenant_franjas({}, _utc(2026, 7, 20, 10, 0)) is False   # festivo
    assert is_within_tenant_franjas({}, _utc(2026, 7, 11, 10, 0)) is False   # sábado sin franja


def test_franjas_custom_y_sabado():
    h = {"franjas": [["08:00", "18:00"]], "franjas_sabado": [["09:00", "12:00"]],
         "dias_habiles": [1, 2, 3, 4, 5]}
    assert is_within_tenant_franjas(h, _utc(2026, 7, 14, 17, 0)) is True
    assert is_within_tenant_franjas(h, _utc(2026, 7, 11, 10, 0)) is True     # sábado 10am
    assert is_within_tenant_franjas(h, _utc(2026, 7, 11, 14, 0)) is False    # sábado 2pm
