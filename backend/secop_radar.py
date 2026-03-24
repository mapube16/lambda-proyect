"""
secop_radar.py — Radar de licitaciones ABIERTAS en SECOP II.

Detecta procesos de contratación en etapa de recepción de ofertas,
identifica los proponentes probables (basado en histórico SECOP),
y genera leads para que la aseguradora ofrezca pólizas de cumplimiento.

Endpoints datos.gov.co usados:
  - Procesos SECOP II:  https://www.datos.gov.co/resource/p6dx-8zbt.json
  - Contratos SECOP II: https://www.datos.gov.co/resource/jbjy-vk9h.json  (ya en secop.py)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}

# Dataset SECOP II — Procesos de Selección
SECOP_PROCESOS_URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"

# Contratos adjudicados (para encontrar proponentes habituales por sector)
SECOP_CONTRATOS_URL = "https://www.datos.gov.co/resource/jbjy-vk9h.json"

# Etapas que indican que el proceso está ABIERTO para ofertas
ETAPAS_ABIERTAS = {
    "publicacion de estudios previos",
    "publicacion de proyecto de pliego",
    "publicacion del pliego definitivo",
    "recepcion de ofertas",
    "evaluacion de ofertas",
    "subasta inversa",
    "apertura proceso",
}


async def fetch_open_processes(
    keyword: str,
    ciudad: Optional[str] = None,
    max_results: int = 50,
) -> list[dict]:
    """
    Busca licitaciones ABIERTAS en SECOP II por keyword de sector.

    Args:
        keyword:     Sector o tipo de contrato (e.g. 'seguridad', 'tecnologia', 'construccion')
        ciudad:      Municipio opcional
        max_results: Máximo de procesos a retornar

    Returns lista de procesos con:
        proceso_id, entidad, objeto, valor_estimado, fecha_cierre, ciudad, estado
    """
    # Solo filtramos por keyword — ciudad puede tener tilde (BOGOTÁ) y fallar
    # Usamos $q para full-text search que es más robusto
    today_iso = date.today().isoformat()
    params = {
        "$limit": max(200, max_results * 10),  # Over-fetch masivo
        "$q": keyword,
        "$order": "fecha_de_publicacion_del DESC",
        "$where": f"fecha_de_recepcion_de > '{today_iso}T00:00:00.000'",
    }

    processes = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(SECOP_PROCESOS_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
            rows = resp.json()

        if not isinstance(rows, list):
            logger.warning("[Radar] Respuesta inesperada: %s", type(rows))
            return []

        # Log primeras filas para debug de campos disponibles
        if rows:
            logger.info("[Radar] Campos disponibles: %s", list(rows[0].keys()))
            logger.info("[Radar] Ejemplo fila: estado_apertura=%s fase=%s ciudad=%s",
                rows[0].get("estado_de_apertura_del_proceso"),
                rows[0].get("fase"),
                rows[0].get("ciudad_entidad"),
            )

        for r in rows:
            estado_apertura = (r.get("estado_de_apertura_del_proceso") or "").strip().lower()
            estado_proc     = (r.get("estado_del_procedimiento") or "").strip().lower()
            fase            = (r.get("fase") or "").strip().lower()
            municipio       = (r.get("ciudad_entidad") or "").strip()

            # Filtro de ciudad flexible (acepta tildes, mayúsculas, etc.)
            if ciudad:
                ciudad_norm = ciudad.lower().replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
                muni_norm   = municipio.lower().replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
                if ciudad_norm not in muni_norm:
                    continue

            # Filtro de fecha de cierre: descartar contratos vencidos
            fecha_cierre_raw = (r.get("fecha_de_recepcion_de") or "")[:10]
            if fecha_cierre_raw:
                try:
                    if date.fromisoformat(fecha_cierre_raw) < date.today():
                        continue  # ya cerrado
                except ValueError:
                    pass  # fecha inválida → no descartar por fecha

            # Incluir si está abierto según cualquier campo de estado
            is_open = (
                "abierto" in estado_apertura
                or any(etapa in fase for etapa in ETAPAS_ABIERTAS)
                or any(etapa in estado_proc for etapa in ETAPAS_ABIERTAS)
                or "cerrado" not in estado_apertura  # incluir si no está explícitamente cerrado
            )
            if not is_open:
                continue

            try:
                valor = float(r.get("precio_base") or 0)
            except (ValueError, TypeError):
                valor = 0.0

            processes.append({
                "proceso_id":     (r.get("id_del_proceso") or "").strip(),
                "entidad":        (r.get("entidad") or "").strip().title(),
                "objeto":         (r.get("descripci_n_del_procedimiento") or "").strip()[:300],
                "valor_estimado": valor,
                "fecha_cierre":   (r.get("fecha_de_recepcion_de") or "")[:10],
                "estado":         estado_apertura or estado_proc or "activo",
                "fase":           fase,
                "municipio":      municipio.title(),
                "departamento":   (r.get("departamento_entidad") or "").strip().title(),
                "modalidad":      (r.get("modalidad_de_contratacion") or "").strip(),
                "tipo_contrato":  (r.get("tipo_de_contrato") or "").strip(),
            })

            if len(processes) >= max_results:
                break

        logger.info("[Radar] keyword='%s' total_rows=%d → %d procesos tras filtros", keyword, len(rows), len(processes))
    except Exception as e:
        logger.error("[Radar] Error fetcheando procesos: %s", e)

    return processes


async def find_likely_proponents(
    keyword: str,
    ciudad: Optional[str] = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Encuentra empresas que PROBABLEMENTE se presenten a una licitación
    basándose en su historial de contratos ganados en el mismo sector.
    Busca sin filtro de ciudad para maximizar resultados.
    """
    from secop import fetch_secop_providers
    # No pasamos ciudad — el campo "ciudad" en jbjy-vk9h es la ciudad de la entidad,
    # no del proveedor, por lo que filtrar por ciudad reduce resultados innecesariamente
    return await fetch_secop_providers(
        keyword=keyword,
        ciudad=None,
        max_results=max_results,
    )


async def build_poliza_leads(
    keyword: str,
    ciudad: Optional[str] = None,
    max_procesos: int = 10,
    max_proponentes: int = 20,
) -> dict:
    """
    Orquestador principal del radar.

    Para un sector dado:
    1. Detecta licitaciones abiertas ahora mismo
    2. Identifica proponentes probables (por historial)
    3. Enriquece cada proponente con NIT → expediente completo
    4. Retorna el paquete de leads listo para la aseguradora

    Args:
        keyword:          Sector (e.g. 'construccion', 'transporte', 'tecnologia')
        ciudad:           Filtro de ciudad (opcional)
        max_procesos:     Máx licitaciones a incluir
        max_proponentes:  Máx empresas a enriquecer

    Returns:
        {
          "licitaciones_abiertas": [...],
          "proponentes_probables":  [...expedientes enriquecidos...],
          "resumen": {...stats}
        }
    """
    from nit_enricher import enrich_nits_batch

    logger.info("[PolizaLeads] Iniciando radar — sector='%s' ciudad='%s'", keyword, ciudad)

    # Paso 1 y 2 en paralelo
    procesos_task    = fetch_open_processes(keyword, ciudad, max_procesos)
    proponentes_task = find_likely_proponents(keyword, ciudad, max_proponentes)

    procesos, proponentes_raw = await asyncio.gather(procesos_task, proponentes_task)

    # Paso 3: enriquecer NITs en paralelo
    nits = [p["nit"] for p in proponentes_raw if p.get("nit")]
    logger.info("[PolizaLeads] Enriqueciendo %d NITs...", len(nits))
    expedientes = await enrich_nits_batch(nits, max_concurrent=4)

    # Mapear nit → expediente para merge
    exp_map = {e["nit"]: e for e in expedientes if isinstance(e, dict)}

    # Merge: combinar datos SECOP de proponentes con expediente enriquecido
    proponentes_final = []
    for p in proponentes_raw:
        nit = p.get("nit", "")
        exp = exp_map.get(nit, {})
        lead = {
            **exp,
            # Sobreescribir con datos directos de SECOP si son más completos
            "contratos_secop":        max(exp.get("contratos_secop", 0), p.get("contratos", 0)),
            "valor_total_contratado": max(
                exp.get("valor_total_contratado", 0), p.get("valor_total", 0)
            ),
            "ultimo_contrato":        exp.get("ultimo_contrato") or p.get("ultimo_objeto"),
            "razon_social":           exp.get("razon_social") or p.get("nombre"),
            "nit":                    nit,
        }
        proponentes_final.append(lead)

    # Ordenar por valor contratado (los más grandes primero = pólizas más grandes)
    proponentes_final.sort(key=lambda x: x.get("valor_total_contratado", 0), reverse=True)

    # Calcular valor total de licitaciones abiertas
    valor_licitaciones = sum(p.get("valor_estimado", 0) for p in procesos)

    from nit_enricher import _fmt_cop
    resumen = {
        "sector":                    keyword,
        "ciudad":                    ciudad or "Colombia",
        "licitaciones_abiertas":     len(procesos),
        "valor_total_licitaciones":  _fmt_cop(valor_licitaciones),
        "proponentes_identificados": len(proponentes_final),
        "con_contacto_web":          sum(1 for p in proponentes_final if p.get("website")),
        "con_email":                 sum(1 for p in proponentes_final if p.get("email")),
        "con_rep_legal":             sum(1 for p in proponentes_final if p.get("representante_legal")),
    }

    logger.info("[PolizaLeads] Completado: %s", resumen)

    return {
        "licitaciones_abiertas":  procesos,
        "proponentes_probables":  proponentes_final,
        "resumen":                resumen,
    }
