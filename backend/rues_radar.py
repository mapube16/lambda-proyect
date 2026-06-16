"""
rues_radar.py — Pipeline AISLADO del vertical "empresas recién creadas".

Objetivo: encontrar empresas recién matriculadas en Cámara de Comercio (RUES)
para ofrecerles pólizas (empresa nueva = necesita seguros desde el día uno).

A diferencia del pipeline web genérico, este vertical NO scrapea sitios web ni
resuelve URLs por Bing (las empresas nuevas casi nunca tienen web). El contacto
se obtiene enriqueciendo el NIT (RUES + Apitude + SECOP) → teléfono, dirección,
representante legal.

Mismo patrón que secop_radar.build_poliza_leads: discover → enrich(NIT) → leads.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)


def _score_lead(exp: dict, fecha_matricula: str | None) -> tuple[int, bool, str]:
    """
    Score para 'recién creadas':
      - base por recencia (más nueva = más alta)
      - +contacto (tel/email) y +rep legal
    qualified = tiene razón social + algún contacto accionable.
    Devuelve (score, qualified, motivo_si_descartada).
    """
    razon = exp.get("razon_social")
    if not razon:
        return 0, False, "SIN_DATOS_RUES"

    tiene_tel = bool(exp.get("phone") or exp.get("rep_legal_telefono"))
    tiene_email = bool(exp.get("email") or exp.get("rep_legal_email"))
    tiene_rep = bool(exp.get("representante_legal"))
    tiene_dir = bool(exp.get("direccion_oficial") or exp.get("direccion"))

    # Recencia → base
    base = 60
    if fecha_matricula:
        try:
            d = datetime.strptime(fecha_matricula[:10].replace("/", "-"), "%Y-%m-%d").date()
            dias = (date.today() - d).days
            if dias <= 30:    base = 85
            elif dias <= 90:  base = 78
            elif dias <= 180: base = 70
            else:             base = 62
        except (ValueError, TypeError):
            pass

    score = base + (12 if tiene_tel else 0) + (8 if tiene_email else 0) + (5 if tiene_rep else 0)
    score = min(score, 98)

    # Una empresa recién creada con rep legal o dirección YA es accionable.
    # Solo se descarta si no hay forma alguna de ubicarla.
    if not (tiene_tel or tiene_email or tiene_rep or tiene_dir):
        return score, False, "SIN_CONTACTO_NI_REP_LEGAL"
    return score, True, ""


async def build_recien_creadas_leads(
    industria: str | None = None,
    ciudad: str | None = None,
    max_results: int = 20,
    dias_recientes: int = 180,
) -> list[dict]:
    """
    Orquestador del vertical recién-creadas.

    industria/ciudad son OPCIONALES: toda empresa recién matriculada es prospecto
    (necesita seguros desde el día uno), sin importar sector ni ciudad. Sin filtro,
    trae todas las recién creadas ordenadas por fecha.

    1. Descubre empresas recién matriculadas (RUES, por CIIU/ciudad/fecha).
    2. Enriquece cada NIT → contacto (tel/email/rep legal/dirección).
    3. Devuelve leads listos para save_lead (shape del pipeline), sin web/Bing.
    """
    from rues import discover_companies_rues
    from nit_enricher import enrich_nits_batch

    logger.info("[RUES-Radar] industria=%r ciudad=%r dias=%d", industria, ciudad, dias_recientes)

    companies = await discover_companies_rues(
        industria=industria,
        ciudad=ciudad or "",
        max_results=max_results,
        dias_recientes=dias_recientes,
    )
    if not companies:
        logger.info("[RUES-Radar] 0 empresas descubiertas")
        return []

    nits = [c["nit"] for c in companies if c.get("nit")]
    logger.info("[RUES-Radar] enriqueciendo %d NITs...", len(nits))
    expedientes = await enrich_nits_batch(nits, max_concurrent=4)
    exp_map = {e["nit"]: e for e in expedientes if isinstance(e, dict) and e.get("nit")}

    leads: list[dict] = []
    for c in companies:
        nit = c.get("nit", "")
        exp = exp_map.get(nit, {})
        razon = exp.get("razon_social") or c.get("title") or ""
        fecha = exp.get("fecha_matricula") or (c.get("rues_data") or {}).get("fecha_matricula")
        score, qualified, motivo = _score_lead(exp, fecha)

        rep_legal = exp.get("representante_legal") or ""
        email = exp.get("rep_legal_email") or exp.get("email") or ""
        phone = exp.get("rep_legal_telefono") or exp.get("phone") or ""
        direccion = exp.get("direccion_oficial") or exp.get("direccion") or exp.get("camara_comercio") or ""

        resumen = f"Empresa {exp.get('tipo_sociedad') or ''} registrada {fecha or 's/f'} en {exp.get('camara_comercio') or 'Cámara de Comercio'}.".strip()

        leads.append({
            "company_name": razon,
            "url": "",
            "phone": phone,
            "address": direccion,
            "score": score,
            "system_state": "SUCCESS_READY_FOR_REVIEW" if qualified else "REJECTED_BY_AI",
            "expediente_markdown": None,
            "expediente_json": {
                "empresa": razon,
                "score": score,
                "system_state": "SUCCESS_READY_FOR_REVIEW" if qualified else "REJECTED_BY_AI",
                "motivo_descalificacion": motivo,
                "resumen_empresa": resumen,
                "evidencia_encontrada": resumen,
                "fecha_matricula": fecha,
                "nit": nit,
                "decisor": {
                    "nombre": rep_legal,
                    "cargo": "Representante Legal" if rep_legal else "",
                    "email": email,
                    "telefono": phone,
                },
                "fuentes_consultadas": exp.get("fuentes_consultadas", ["RUES"]),
            },
            "nit": nit,
        })

    leads.sort(key=lambda x: x["score"], reverse=True)
    qualified_n = sum(1 for l in leads if l["system_state"] == "SUCCESS_READY_FOR_REVIEW")
    logger.info("[RUES-Radar] %d leads (%d calificados / %d sin contacto)", len(leads), qualified_n, len(leads) - qualified_n)
    return leads
