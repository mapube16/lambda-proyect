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
import re
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── In-memory cache (key: (keyword, ciudad), value: (results, timestamp)) ────
import time as _time
_cache_procesos: dict = {}
_cache_proveedores: dict = {}
_CACHE_TTL = 600  # 10 minutes — SECOP data changes slowly

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
    cache_key = (keyword.lower().strip(), (ciudad or "").lower().strip())
    cached = _cache_procesos.get(cache_key)
    if cached:
        results, ts = cached
        if _time.time() - ts < _CACHE_TTL:
            logger.info("[Radar] Cache hit for %s", cache_key)
            return results[:max_results]

    # Solo filtramos por keyword — ciudad puede tener tilde (BOGOTÁ) y fallar
    today_iso = date.today().isoformat()
    params = {
        "$limit": 100,  # reduced from 500 — date filter does the heavy lifting
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
        _cache_procesos[cache_key] = (processes, _time.time())
    except Exception as e:
        logger.error("[Radar] Error fetcheando procesos: %s", e)

    return processes[:max_results]


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


# Dataset: Proponentes por Proceso SECOP II — una fila por (proceso, oferente).
# ESTA es la fuente correcta de "empresas presentándose a procesos".
_PROPONENTES_URL = "https://www.datos.gov.co/resource/hgi6-6wh3.json"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PAREN_RE = re.compile(r"\s*\(.*?\)\s*")


async def fetch_proponentes(
    keyword: str | None = None,
    ciudad: str | None = None,
    max_results: int = 20,
    dias_recientes: int = 365,
) -> list[dict]:
    """
    Empresas que SE PRESENTARON a procesos públicos (oferentes), desde el dataset
    Proponentes-por-Proceso. Deduplica por NIT y agrega los procesos a los que
    cada empresa se presentó. A veces el email viene en el nombre del proveedor.

    keyword es OPCIONAL: para pólizas de cumplimiento, CUALQUIER empresa que se
    presente a un proceso es prospecto, sin importar sector ni ciudad. Si keyword
    viene vacío, trae todos los proponentes recientes (orden por fecha DESC).
    """
    params = {
        "$order": "fecha_publicaci_n DESC",
        "$limit": max(300, max_results * 12),
    }
    if keyword:
        params["$q"] = keyword
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get(_PROPONENTES_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
            rows = resp.json()
    except Exception as e:
        logger.error("[Proponentes] error: %s", e)
        return []
    if not isinstance(rows, list):
        return []

    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=dias_recientes)).isoformat()

    agg: dict[str, dict] = {}
    for r in rows:
        nit = (r.get("nit_proveedor") or "").strip()
        if not nit:
            continue
        fecha = (r.get("fecha_publicaci_n") or "")[:10]
        if fecha and fecha < cutoff:
            continue
        nombre_raw = (r.get("proveedor") or "").strip()
        m = _EMAIL_RE.search(nombre_raw)
        email = m.group(0).lower() if m else ""
        nombre = _PAREN_RE.sub(" ", nombre_raw).strip().title()
        a = agg.setdefault(nit, {"nit": nit, "nombre": nombre, "email": email, "procesos": [], "ultima_fecha": fecha or ""})
        if email and not a["email"]:
            a["email"] = email
        if nombre and not a["nombre"]:
            a["nombre"] = nombre
        a["procesos"].append({
            "nombre": (r.get("nombre_procedimiento") or "").strip(),
            "entidad": (r.get("entidad_compradora") or "").strip().title(),
            "fecha": fecha,
        })
        if fecha > a["ultima_fecha"]:
            a["ultima_fecha"] = fecha

    out = list(agg.values())
    # Más procesos recientes presentados = más activo = mejor prospecto
    out.sort(key=lambda x: (len(x["procesos"]), x["ultima_fecha"]), reverse=True)
    logger.info("[Proponentes] keyword=%r -> %d filas -> %d empresas únicas", keyword, len(rows), len(out))
    return out[:max_results]


def _score_proponente(p: dict, exp: dict) -> int:
    n = len(p.get("procesos", []))
    base = 70 + min(n * 5, 20)
    if exp.get("phone") or exp.get("rep_legal_telefono") or p.get("email"):
        base += 5
    return min(base, 98)


async def build_secop_leads(
    keyword: str | None = None,
    ciudad: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Vertical SECOP aislado: empresas PRESENTÁNDOSE a procesos públicos
    (dataset Proponentes-por-Proceso) → enriquecidas por NIT. Shape de save_lead.
    keyword opcional: sin él, trae TODAS las empresas presentándose (cualquier
    sector/ciudad), que es lo correcto para pólizas de cumplimiento.
    """
    from nit_enricher import enrich_nits_batch

    proponentes = await fetch_proponentes(keyword, ciudad, max_results=max_results, dias_recientes=365)
    if not proponentes:
        logger.info("[SECOP-leads] 0 proponentes para %r", keyword)
        return []

    nits = [p["nit"] for p in proponentes if p.get("nit")]
    expedientes = await enrich_nits_batch(nits, max_concurrent=4)
    exp_map = {e["nit"]: e for e in expedientes if isinstance(e, dict) and e.get("nit")}

    leads: list[dict] = []
    for p in proponentes:
        exp = exp_map.get(p["nit"], {})
        score = _score_proponente(p, exp)
        razon = exp.get("razon_social") or p.get("nombre") or f"NIT {p['nit']}"
        rep_legal = exp.get("representante_legal") or ""
        email = p.get("email") or exp.get("rep_legal_email") or exp.get("email") or ""
        phone = exp.get("rep_legal_telefono") or exp.get("phone") or ""
        procs = p.get("procesos", [])
        n = len(procs)
        ej = procs[0] if procs else {}
        resumen = (
            f"Empresa presentándose a contratación pública: {n} proceso(s) reciente(s). "
            f"Ej: \"{(ej.get('nombre') or '')[:70]}\"" + (f" — {ej.get('entidad')}" if ej.get('entidad') else "") + "."
        )
        procesos_txt = "; ".join(f"{x.get('nombre','')[:50]} ({x.get('entidad','')})" for x in procs[:3])
        leads.append({
            "company_name": razon,
            "url": exp.get("website") or "",
            "phone": phone,
            "address": exp.get("direccion_oficial") or exp.get("direccion") or "",
            "score": score,
            "system_state": "SUCCESS_READY_FOR_REVIEW",
            "expediente_markdown": None,
            "expediente_json": {
                "empresa": razon,
                "score": score,
                "system_state": "SUCCESS_READY_FOR_REVIEW",
                "motivo_descalificacion": "",
                "resumen_empresa": resumen,
                "evidencia_encontrada": f"Procesos a los que se presentó: {procesos_txt}",
                "nit": p["nit"],
                "decisor": {
                    "nombre": rep_legal,
                    "cargo": "Representante Legal" if rep_legal else "",
                    "email": email,
                    "telefono": phone,
                },
                "contratos_secop": n,  # nº de procesos a los que se presentó (recientes)
                "valor_total": "",
                "procesos": procs[:5],
                "fuentes_consultadas": ["SECOP Proponentes", "RUES/NIT"],
            },
            "nit": p["nit"],
        })

    leads.sort(key=lambda x: x["score"], reverse=True)
    logger.info("[SECOP-leads] %d leads para %r", len(leads), keyword)
    return leads
