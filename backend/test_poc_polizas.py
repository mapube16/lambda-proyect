"""
test_poc_polizas.py — Script de prueba rápida del POC de pólizas de cumplimiento.

Uso:
    cd backend
    python test_poc_polizas.py

Prueba 3 cosas:
  1. Enriquecer un NIT específico
  2. Buscar licitaciones abiertas en un sector
  3. Pipeline completo: radar → proponentes → expedientes
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def test_enrich_nit():
    """Prueba 1: Enriquecer un NIT conocido."""
    from nit_enricher import enrich_nit

    # NIT de ejemplo: Constructora Conconcreto S.A. (empresa real con historial SECOP)
    nit = "890.935.625-4"
    print(f"\n{'='*60}")
    print(f"PRUEBA 1 — Enriquecedor de NIT: {nit}")
    print("="*60)

    result = await enrich_nit(nit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


async def test_procesos_abiertos():
    """Prueba 2: Licitaciones abiertas en construcción."""
    from secop_radar import fetch_open_processes

    print(f"\n{'='*60}")
    print("PRUEBA 2 — Licitaciones ABIERTAS: sector='construccion' ciudad='Bogota'")
    print("="*60)

    procesos = await fetch_open_processes("construccion", "Bogota", max_results=5)
    for i, p in enumerate(procesos, 1):
        print(f"\n[{i}] {p['entidad']}")
        print(f"     Objeto: {p['objeto'][:80]}...")
        print(f"     Valor: ${p['valor_estimado']:,.0f} COP" if p['valor_estimado'] else "     Valor: N/D")
        print(f"     Cierre: {p['fecha_cierre'] or 'N/D'}")
        print(f"     Estado: {p['estado']}")
    return procesos


async def test_radar_completo():
    """Prueba 3: Pipeline completo para aseguradora."""
    from secop_radar import build_poliza_leads

    sector = "transporte"
    ciudad = "Bogota"

    print(f"\n{'='*60}")
    print(f"PRUEBA 3 — Radar completo: sector='{sector}' ciudad='{ciudad}'")
    print("="*60)

    result = await build_poliza_leads(
        keyword=sector,
        ciudad=ciudad,
        max_procesos=5,
        max_proponentes=5,  # Pocos para que sea rápido
    )

    print("\n📊 RESUMEN:")
    for k, v in result["resumen"].items():
        print(f"  {k}: {v}")

    print(f"\n🏗️ LICITACIONES ABIERTAS ({len(result['licitaciones_abiertas'])}):")
    for p in result["licitaciones_abiertas"][:3]:
        print(f"  • {p['entidad']}: {p['objeto'][:60]}...")

    print(f"\n🏢 PROPONENTES PROBABLES ({len(result['proponentes_probables'])}):")
    for lead in result["proponentes_probables"]:
        print(f"\n  NIT: {lead.get('nit')}")
        print(f"  Empresa: {lead.get('razon_social') or 'N/D'}")
        print(f"  Rep. Legal: {lead.get('representante_legal') or 'N/D'}")
        print(f"  Email: {lead.get('email') or 'N/D'}")
        print(f"  Web: {lead.get('website') or 'N/D'}")
        print(f"  Contratos SECOP: {lead.get('contratos_secop', 0)}")
        print(f"  Valor total: {lead.get('valor_total_fmt', 'N/D')}")
        print(f"  ⚡ {lead.get('advertencia_poliza', '')[:100]}")

    return result


async def main():
    print("🚀 POC — Agente de Pólizas de Cumplimiento SECOP")
    print("   Fuentes: RUES + SECOP II + Supersociedades + Web")

    # Correr solo la prueba que quieras (comenta las demás)
    # await test_enrich_nit()
    # await test_procesos_abiertos()
    await test_radar_completo()

    print("\n✅ POC completado")


if __name__ == "__main__":
    asyncio.run(main())
