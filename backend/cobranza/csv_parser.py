"""
csv_parser.py — CSV upload parsing and phone validation for cobranza debtors.
"""
import csv
import io
from datetime import datetime
from typing import Optional

import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException


def normalize_phone(raw: str, default_region: str = "CO") -> Optional[str]:
    """
    Normalize a phone number string to E164 format.

    Examples:
        normalize_phone("+57 300 123 4567", "CO") -> "+573001234567"
        normalize_phone("3001234567", "CO")        -> "+573001234567"
        normalize_phone("invalid", "CO")           -> None
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw.strip(), default_region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except NumberParseException:
        return None


def parse_debtor_csv(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """
    Parse a CSV file of debtors. Returns (valid_rows, error_messages).

    Required columns: nombre, telefono, monto, vencimiento (YYYY-MM-DD).
    Valid rows are augmented with debtor defaults (estado, intentos, etc.).
    Invalid rows are skipped; an error string is added for each skipped row.
    """
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    required_columns = {"nombre", "telefono", "monto", "vencimiento"}
    rows: list[dict] = []
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        # Normalize column names (strip whitespace)
        row = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}

        # Check required fields present
        missing = required_columns - set(row.keys())
        if missing:
            errors.append(f"Row {row_num}: missing columns {', '.join(sorted(missing))}")
            continue

        # Validate and normalize telefono
        raw_phone = row.get("telefono", "")
        normalized = normalize_phone(raw_phone)
        if normalized is None:
            errors.append(f"Row {row_num}: telefono inválido '{raw_phone}'")
            continue

        # Validate monto
        raw_monto = row.get("monto", "").replace("$", "").replace(",", "").strip()
        try:
            monto = float(raw_monto)
        except (ValueError, AttributeError):
            errors.append(f"Row {row_num}: monto inválido '{row.get('monto', '')}'")
            continue

        # Validate vencimiento
        raw_fecha = row.get("vencimiento", "")
        try:
            vencimiento = datetime.strptime(raw_fecha.strip(), "%Y-%m-%d")
        except (ValueError, AttributeError):
            errors.append(f"Row {row_num}: vencimiento inválido '{raw_fecha}' (esperado YYYY-MM-DD)")
            continue

        # Build valid debtor dict with defaults
        rows.append({
            "nombre": row.get("nombre", "").strip(),
            "telefono": normalized,
            "monto": monto,
            "vencimiento": vencimiento,
            "estado": "pendiente",
            "intentos": 0,
            "max_intentos": 5,
            "historial_llamadas": [],
            "escalado": False,
            "notas": None,
        })

    return rows, errors
