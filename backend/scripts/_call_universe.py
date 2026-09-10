"""Caracteriza el universo REAL de llamadas segun el informe:
- fecha de pago (vencimiento) >= 2026-06-15 (corte del informe §2)
- excluye no_llamar (estatales + opt-outs) y is_test
Desglosa vencidas vs por-vencer y por antiguedad de mora (para la jornada de
arranque §3: evacuar backlog por antiguedad, ~250/dia)."""
import asyncio, os, certifi
from datetime import date, datetime, timezone
from collections import Counter

# El DNS local (hotspot) rechaza la resolucion SRV de mongodb+srv:// — forzamos
# un DNS publico para el lookup.
try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient

USER_ID = "69bcd9bb6e35d53880364535"
CORTE = date(2026, 6, 15)
HOY = datetime.now(timezone.utc).astimezone().date()  # aprox; suficiente para el conteo


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v:
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            return None
    return None


async def main():
    db = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]
    print(f"HOY(aprox)={HOY}  CORTE={CORTE}\n")

    total = gestionables = sin_venc = antes_corte = 0
    vencidas = por_vencer = vence_hoy = 0
    mora_buckets = Counter()  # rangos de dias de mora
    sin_telefono = 0

    async for d in db.debtors.find({"user_id": USER_ID}):
        total += 1
        if d.get("is_test") or d.get("no_llamar"):
            continue
        gestionables += 1
        if not str(d.get("telefono") or "").strip():
            sin_telefono += 1
        venc = _to_date(d.get("fecha_pago") or d.get("vencimiento"))
        if venc is None:
            sin_venc += 1
            continue
        if venc < CORTE:
            antes_corte += 1
            continue
        dias = (HOY - venc).days
        if dias > 0:
            vencidas += 1
            if dias <= 5: mora_buckets["1-5 dias"] += 1
            elif dias <= 15: mora_buckets["6-15 dias"] += 1
            elif dias <= 30: mora_buckets["16-30 dias"] += 1
            else: mora_buckets[">30 dias"] += 1
        elif dias == 0:
            vence_hoy += 1
        else:
            por_vencer += 1

    print(f"[TOTAL deudores DPG]      {total}")
    print(f"[gestionables]            {gestionables}  (excluye is_test + no_llamar)")
    print(f"  - sin telefono          {sin_telefono}  (no se pueden llamar)")
    print(f"  - sin fecha vencimiento  {sin_venc}")
    print(f"  - vencimiento < corte    {antes_corte}  (fuera de alcance, informe)")
    print(f"\n[EN ALCANCE — venc >= {CORTE}]")
    print(f"  VENCIDAS (mora >=1)     {vencidas}   <- jornada de arranque, por antiguedad")
    for k in ("1-5 dias","6-15 dias","16-30 dias",">30 dias"):
        if mora_buckets.get(k): print(f"      {k:12} {mora_buckets[k]}")
    print(f"  VENCE HOY               {vence_hoy}")
    print(f"  POR VENCER (preventiva) {por_vencer}")
    print(f"\n  TOTAL a gestionar ahora {vencidas + vence_hoy + por_vencer}")
    db.client.close()


asyncio.run(main())
