"""
es_numbers.py — integer-to-Spanish-words for natural TTS amounts.

The voice agent must SAY amounts, not show them. "962.036 pesos" or
"962.0 mil pesos" both read terribly. pesos_en_palabras(962036) ->
"novecientos sesenta y dos mil pesos".

Covers 0 .. 999_999_999 (enough for any policy balance). No external deps.
"""
from __future__ import annotations

_UNIDADES = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
    "nueve", "diez", "once", "doce", "trece", "catorce", "quince", "dieciseis",
    "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidos",
    "veintitres", "veinticuatro", "veinticinco", "veintiseis", "veintisiete",
    "veintiocho", "veintinueve",
]
_DECENAS = {
    30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta",
    70: "setenta", 80: "ochenta", 90: "noventa",
}
_CENTENAS = {
    100: "cien", 200: "doscientos", 300: "trescientos", 400: "cuatrocientos",
    500: "quinientos", 600: "seiscientos", 700: "setecientos",
    800: "ochocientos", 900: "novecientos",
}


def _dos_cifras(n: int) -> str:
    if n <= 29:
        return _UNIDADES[n]
    d = (n // 10) * 10
    u = n % 10
    if u == 0:
        return _DECENAS[d]
    return f"{_DECENAS[d]} y {_UNIDADES[u]}"


def _tres_cifras(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cien"
    c = (n // 100) * 100
    resto = n % 100
    parte_c = _CENTENAS[c].replace("cien", "ciento") if c == 100 else (_CENTENAS[c] if c else "")
    parte_r = _dos_cifras(resto) if resto else ""
    return " ".join(p for p in (parte_c, parte_r) if p)


def numero_en_palabras(n: int) -> str:
    """Spell a non-negative integer 0..999_999_999 in Spanish."""
    n = int(round(n))
    if n < 0:
        return "menos " + numero_en_palabras(-n)
    if n < 1000:
        return _tres_cifras(n) if n else "cero"

    if n < 1_000_000:
        miles = n // 1000
        resto = n % 1000
        if miles == 1:
            parte_miles = "mil"
        else:
            parte_miles = f"{_tres_cifras(miles)} mil"
        parte_resto = _tres_cifras(resto) if resto else ""
        return " ".join(p for p in (parte_miles, parte_resto) if p)

    millones = n // 1_000_000
    resto = n % 1_000_000
    if millones == 1:
        parte_mill = "un millon"
    else:
        parte_mill = f"{numero_en_palabras(millones)} millones"
    parte_resto = numero_en_palabras(resto) if resto else ""
    return " ".join(p for p in (parte_mill, parte_resto) if p and p != "cero")


def pesos_en_palabras(monto) -> str:
    """Spell an amount of Colombian pesos for speech (drops cents)."""
    try:
        entero = int(float(monto))
    except (TypeError, ValueError):
        return "0 pesos"
    if entero <= 0:
        return "cero pesos"
    return f"{numero_en_palabras(entero)} pesos"
