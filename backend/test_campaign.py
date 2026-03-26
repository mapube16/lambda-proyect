"""
test_campaign.py — Suite de calidad del pipeline de prospección B2B.

4 capas (de más rápida a más completa):

  Tier 1 — Filtros estáticos    : sin I/O, <1s
  Tier 2 — Calidad de discovery : HTTP real, sin LLM, ~30s
  Tier 3 — Análisis golden set  : LLM en empresas conocidas, ~2 min
  Tier 4 — Benchmark end-to-end : pipeline completo en sector real, ~5 min

Uso:
    python test_campaign.py              # todos los tiers
    python test_campaign.py --tier 1     # solo filtros
    python test_campaign.py --tier 1 2   # filtros + discovery
    python test_campaign.py --tier 3 4   # análisis + benchmark

Requiere las variables de entorno del .env estándar.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
GMAPS_KEY  = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ── Result tracking ────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    elapsed: float = 0.0

@dataclass
class Suite:
    name: str
    results: list[TestResult] = field(default_factory=list)

    def check(self, name: str, condition: bool, detail: str = "", elapsed: float = 0.0):
        self.results.append(TestResult(name, condition, detail, elapsed))
        symbol = "[OK]" if condition else "[FAIL]"
        time_str = f"  [{elapsed:.1f}s]" if elapsed else ""
        print(f"  {symbol}  {name}{time_str}")
        if detail:
            print(f"       {detail}")

    def summary(self) -> tuple[int, int]:
        passed = sum(1 for r in self.results if r.passed)
        return passed, len(self.results)


def _timer(fn: Callable):
    """Run fn() and return (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


async def _timer_async(coro):
    t0 = time.perf_counter()
    result = await coro
    return result, time.perf_counter() - t0


# ── Tier 1: Static filter tests ────────────────────────────────────────────────

def run_tier1() -> Suite:
    """Test all filter logic without making any network calls."""
    from prospector import (
        BLOCKED_DOMAINS,
        LOW_QUALITY_DISCOVERY_DOMAINS,
        _is_low_quality_candidate,
    )
    from hive_tools import COMPETITOR_GENERIC_WORDS

    suite = Suite("Tier 1 — Filtros estáticos")
    print(f"\n{'-'*60}")
    print(f"  {suite.name}")
    print(f"{'-'*60}")

    # ── 1.1 Dominios bloqueados ────────────────────────────────────────────────
    bad_urls = [
        ("https://jooble.org/empleo/bogota-logistica", "jooble.org"),
        ("https://mifuturoempleo.co/vacante/123", "mifuturoempleo.co"),
        ("https://blogspot.com/post/empresa", "blogspot.com"),
        ("https://computrabajo.com/empleos", "computrabajo.com"),
        ("https://paginasamarillas.com.co/empresas", "paginasamarillas.com.co"),
        ("https://clutch.co/agencies/colombia", "clutch.co"),
        ("https://indeed.com/jobs", "indeed.com"),
    ]
    all_blocked = all(_is_low_quality_candidate(url) for url, _ in bad_urls)
    unblocked = [label for url, label in bad_urls if not _is_low_quality_candidate(url)]
    suite.check(
        "Dominios de baja calidad filtrados",
        all_blocked,
        f"Sin filtrar: {unblocked}" if unblocked else f"{len(bad_urls)} dominios correctamente bloqueados",
    )

    # ── 1.2 Path markers ──────────────────────────────────────────────────────
    bad_paths = [
        "https://somesite.com/oferta-de-empleo/bogota",
        "https://somesite.com/empleos/vacante-123",
        "https://somesite.com/blog/mejores-empresas-logistica",
        "https://somesite.com/top-10-transportadoras",
        "https://somesite.com/directorio-empresas/logistica",
    ]
    all_path_filtered = all(_is_low_quality_candidate(url) for url in bad_paths)
    unfiltered_paths = [u for u in bad_paths if not _is_low_quality_candidate(u)]
    suite.check(
        "Path markers de baja calidad filtrados",
        all_path_filtered,
        f"Sin filtrar: {unfiltered_paths}" if unfiltered_paths else f"{len(bad_paths)} paths correctamente bloqueados",
    )

    # ── 1.3 Empresas reales NO deben ser filtradas ─────────────────────────────
    good_urls = [
        "https://coordinadora.com",
        "https://tcc.com.co",
        "https://suppla.com",
        "https://envia.com.co",
        "https://grupolegis.com.co",
        "https://sofasa.com.co",
    ]
    not_filtered = [url for url in good_urls if not _is_low_quality_candidate(url)]
    false_positives = [url for url in good_urls if _is_low_quality_candidate(url)]
    suite.check(
        "Empresas reales NO filtradas (false positives)",
        len(false_positives) == 0,
        f"Falsos positivos: {false_positives}" if false_positives else f"{len(good_urls)} empresas válidas pasan correctamente",
    )

    # ── 1.4 Sufijos de dominio gov/edu ─────────────────────────────────────────
    gov_urls = [
        "https://mineducacion.gov.co",
        "https://unal.edu.co",
        "https://invima.gov.co",
    ]
    all_gov_filtered = all(_is_low_quality_candidate(url) for url in gov_urls)
    suite.check(
        "Dominios .gov.co / .edu.co filtrados",
        all_gov_filtered,
        f"{len(gov_urls)} dominios institucionales bloqueados",
    )

    # ── 1.5 Pre-filtro de competidores — palabras genéricas NO disparan filtro ──
    # Sector propio = "agencia de software, desarrollo digital"
    # Target = "Agencia de Marketing Digital X" → NO debe filtrarse (cliente potencial)
    sector_propio = "agencia de software, desarrollo digital"
    competitor_keywords = [
        w.strip().lower()
        for token in sector_propio.replace(",", " ").split()
        for w in [token.strip()]
        if len(w) >= 5 and w.strip().lower() not in COMPETITOR_GENERIC_WORDS
    ]
    # "software" and "desarrollo" should be keywords; "agencia" and "digital" should not
    target_title = "Agencia de Marketing Digital XYZ"
    text = f"{target_title} https://agencia-marketing.co".lower()
    would_be_filtered = any(kw in text for kw in competitor_keywords)
    suite.check(
        "Agencias de marketing NO pre-filtradas como competidores",
        not would_be_filtered,
        f"Keywords activos: {competitor_keywords}  |  Match: {would_be_filtered}",
    )

    # ── 1.6 Competidores reales SÍ deben ser capturados ───────────────────────
    sector_sw = "desarrollo de software a medida"
    kw_sw = [
        w.strip().lower()
        for token in sector_sw.replace(",", " ").split()
        for w in [token.strip()]
        if len(w) >= 5 and w.strip().lower() not in COMPETITOR_GENERIC_WORDS
    ]
    competitor_title = "Pragma Software Colombia — fábrica de software"
    competitor_text = f"{competitor_title} https://pragma.com.co".lower()
    is_competitor = any(kw in competitor_text for kw in kw_sw)
    suite.check(
        "Competidor real SÍ es detectado por pre-filtro",
        is_competitor,
        f"Keywords: {kw_sw}  |  Match: {is_competitor}",
    )

    return suite


# ── Tier 2: Discovery quality ──────────────────────────────────────────────────

async def run_tier2(industria: str = "logistica y transporte", ciudad: str = "Bogotá") -> Suite:
    """Real HTTP discovery — no LLM. Validates quantity and quality of found URLs."""
    from prospector import (
        discover_companies,
        _is_low_quality_candidate,
        BLOCKED_DOMAINS,
        LOW_QUALITY_DISCOVERY_DOMAINS,
    )
    from urllib.parse import urlparse

    suite = Suite(f"Tier 2 — Discovery: '{industria}' en '{ciudad}'")
    print(f"\n{'-'*60}")
    print(f"  {suite.name}")
    print(f"{'-'*60}")

    # ── 2.1 Discovery retorna resultados ──────────────────────────────────────
    t0 = time.perf_counter()
    companies = await discover_companies(
        industria, ciudad, max_results=15,
        gmaps_key=GMAPS_KEY,
        excluded_domains=set(),
        use_secop=False,
    )
    elapsed = time.perf_counter() - t0

    suite.check(
        f"Discovery retorna ≥5 empresas",
        len(companies) >= 5,
        f"Encontradas: {len(companies)}",
        elapsed,
    )

    if not companies:
        return suite

    # ── 2.2 Sin dominios bloqueados ───────────────────────────────────────────
    slipped = [
        c["url"] for c in companies
        if _is_low_quality_candidate(c.get("url", ""), c.get("title", ""))
    ]
    suite.check(
        "Sin dominios de baja calidad en resultados",
        len(slipped) == 0,
        f"Filtraron: {slipped}" if slipped else f"{len(companies)} empresas limpias",
    )

    # ── 2.3 Sin duplicados de dominio ─────────────────────────────────────────
    domains = [urlparse(c["url"]).netloc.replace("www.", "") for c in companies]
    unique_domains = set(domains)
    suite.check(
        "Sin dominios duplicados",
        len(domains) == len(unique_domains),
        f"Total={len(domains)}  únicos={len(unique_domains)}",
    )

    # ── 2.4 URLs tienen http/https ────────────────────────────────────────────
    malformed = [c["url"] for c in companies if not c.get("url", "").startswith("http")]
    suite.check(
        "Todas las URLs tienen esquema http(s)",
        len(malformed) == 0,
        f"Malformadas: {malformed}" if malformed else "OK",
    )

    # ── 2.5 Tasa de accesibilidad ≥ 40% ───────────────────────────────────────
    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36"
    async def _head(client, url):
        try:
            r = await client.head(url, headers={"User-Agent": _UA}, follow_redirects=True, timeout=8)
            return r.status_code
        except Exception:
            return 0

    print(f"       Chequeando accesibilidad de {len(companies)} URLs...")
    t0 = time.perf_counter()
    async with httpx.AsyncClient() as client:
        statuses = await asyncio.gather(*[_head(client, c["url"]) for c in companies])
    elapsed_check = time.perf_counter() - t0

    ok_count = sum(1 for s in statuses if 200 <= s < 400)
    rate = ok_count / len(statuses) if statuses else 0
    suite.check(
        f"Tasa de accesibilidad ≥ 40%",
        rate >= 0.40,
        f"{ok_count}/{len(statuses)} responden 2xx/3xx ({rate:.0%})",
        elapsed_check,
    )

    # ── 2.6 Print found companies ─────────────────────────────────────────────
    print(f"\n       Empresas encontradas:")
    for c, s in zip(companies, statuses):
        icon = "[200]" if 200 <= s < 400 else "[ERR]" if s == 0 else "[WARN]"
        print(f"       {icon} [{s or '---'}] {c.get('title','')[:35]:<35}  {c['url']}")

    return suite


# ── Tier 3: Analysis quality on golden set ─────────────────────────────────────

# Known Colombian B2B logistics companies — should all score ≥ 60 and be approved
GOLDEN_SET = [
    {"url": "https://coordinadora.com",     "title": "Coordinadora Mercantil"},
    {"url": "https://tcc.com.co",            "title": "TCC Transporte"},
    {"url": "https://envia.com.co",          "title": "Envía Colombia"},
]

# Companies that should be rejected by the pipeline
REJECT_SET = [
    {"url": "https://computrabajo.com",     "title": "CompuTrabajo",      "expect_code": "WRONG_SECTOR"},
    {"url": "https://jooble.org",           "title": "Jooble empleos",    "expect_code": "WRONG_SECTOR"},
]

TEST_CAMPAIGN = {
    "nombre_remitente":    "Maximiliano Pulido",
    "empresa_remitente":   "Isomorph",
    "sector_propio_cliente": "",
    "industria_objetivo":  "Logística y Transporte",
    "ciudad_objetivo":     "Bogotá",
    "dolor_operativo":     "gestión manual de rutas y despachos",
    "solucion_ofrecida":   "automatización de operaciones logísticas con IA",
    "software_clave":      "SAP, Excel, WhatsApp Business, TMS",
    "jerarquia_decisores": "Gerente General > Director de Operaciones > Jefe de Logística",
    "llm_analista":        "gpt-5.4-2026-03-05",
    "llm_redactor":        "gpt-5.4-2026-03-05",
}


async def run_tier3() -> Suite:
    """Run the full LLM analysis pipeline on a golden set of known companies."""
    if not OPENAI_KEY:
        suite = Suite("Tier 3 — Análisis golden set [SALTADO — sin OPENAI_API_KEY]")
        print(f"\n[WARN] Tier 3 saltado: OPENAI_API_KEY no configurado")
        return suite

    from openai import AsyncOpenAI
    from prospector import analyze_company

    suite = Suite("Tier 3 — Análisis golden set (LLM)")
    print(f"\n{'-'*60}")
    print(f"  {suite.name}")
    print(f"{'-'*60}")
    print(f"  Procesando {len(GOLDEN_SET)} empresas contra campaña de prueba...")

    client = AsyncOpenAI(api_key=OPENAI_KEY)

    async def _noop_stage(stage, status):
        pass

    results = []
    for company in GOLDEN_SET:
        print(f"\n  → Analizando: {company['title']} ({company['url']})")
        t0 = time.perf_counter()
        try:
            result = await analyze_company(company, TEST_CAMPAIGN, client, _noop_stage)
            elapsed = time.perf_counter() - t0
            results.append((company, result, elapsed))

            state = result.get("status", "")
            jp = result.get("json_payload") or {}
            score = jp.get("score", 0) or 0
            motivo = jp.get("motivo_descalificacion", "")

            print(f"       status={state}  score={score}  motivo={motivo}  [{elapsed:.1f}s]")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            results.append((company, {"status": "error", "error": str(e)}, elapsed))
            print(f"       [FAIL] ERROR: {e}")

    # ── 3.1 Golden set: tasa de aprobación ≥ 66% ──────────────────────────────
    approved = [r for _, r, _ in results if r.get("status") == "success"]
    rate = len(approved) / len(results) if results else 0
    suite.check(
        f"Golden set: tasa de aprobación ≥ 66%",
        rate >= 0.66,
        f"{len(approved)}/{len(results)} aprobados ({rate:.0%})",
    )

    # ── 3.2 Score promedio ≥ 65 en aprobados ──────────────────────────────────
    scores = [
        (r.get("json_payload") or {}).get("score", 0) or 0
        for _, r, _ in results
        if r.get("status") == "success"
    ]
    avg_score = sum(scores) / len(scores) if scores else 0
    suite.check(
        "Score promedio de aprobados ≥ 65",
        avg_score >= 65,
        f"Scores: {scores}  |  Promedio: {avg_score:.1f}",
    )

    # ── 3.3 Aprobados tienen borrador de email ────────────────────────────────
    no_email = []
    for company, r, _ in results:
        if r.get("status") == "success":
            jp = r.get("json_payload") or {}
            borradores = jp.get("borradores") or {}
            if not borradores.get("email_cuerpo") or not borradores.get("email_asuntos"):
                no_email.append(company["title"])
    suite.check(
        "Aprobados tienen borrador de email completo",
        len(no_email) == 0,
        f"Sin email: {no_email}" if no_email else f"{len(approved)} con email generado",
    )

    # ── 3.4 JSON payload parseado correctamente ───────────────────────────────
    parse_errors = [c["title"] for c, r, _ in results if r.get("status") == "error"]
    suite.check(
        "Sin errores de parseo en respuestas LLM",
        len(parse_errors) == 0,
        f"Errores: {parse_errors}" if parse_errors else "Todos los JSONs parseados correctamente",
    )

    # ── Detail per company ─────────────────────────────────────────────────────
    print(f"\n  Detalle golden set:")
    for company, result, elapsed in results:
        jp = result.get("json_payload") or {}
        state = result.get("status", "error")
        score = jp.get("score", "—")
        motivo = jp.get("motivo_descalificacion", "")
        decisor = (jp.get("decisor") or {}).get("nombre") or "—"
        icon = "[OK]" if state == "success" else "[FAIL]"
        print(f"  {icon} {company['title']:<30} score={score:<5} decisor={decisor:<25} [{elapsed:.1f}s]")
        if motivo:
            print(f"     motivo: {motivo}")

    return suite


# ── Tier 4: End-to-end benchmark ───────────────────────────────────────────────

BENCHMARK_INDUSTRY = "empresas de logistica y transporte de carga"
BENCHMARK_CITY     = "Bogotá"
BENCHMARK_MAX      = 8  # small set to keep cost/time reasonable

async def run_tier4() -> Suite:
    """Full pipeline benchmark: discover → analyze → validate quality metrics."""
    if not OPENAI_KEY:
        suite = Suite("Tier 4 — Benchmark end-to-end [SALTADO — sin OPENAI_API_KEY]")
        print(f"\n[WARN] Tier 4 saltado: OPENAI_API_KEY no configurado")
        return suite

    from openai import AsyncOpenAI
    from prospector import discover_companies, analyze_company

    suite = Suite("Tier 4 — Benchmark end-to-end")
    print(f"\n{'-'*60}")
    print(f"  {suite.name}")
    print(f"  Campaña: '{BENCHMARK_INDUSTRY}' en '{BENCHMARK_CITY}'  max={BENCHMARK_MAX}")
    print(f"{'-'*60}")

    # ── Discover ───────────────────────────────────────────────────────────────
    print("  [1/3] Discovery...")
    t0 = time.perf_counter()
    companies = await discover_companies(
        BENCHMARK_INDUSTRY, BENCHMARK_CITY, BENCHMARK_MAX,
        gmaps_key=GMAPS_KEY,
        excluded_domains=set(),
        use_secop=False,
    )
    discovery_elapsed = time.perf_counter() - t0

    suite.check(
        f"Discovery retorna ≥ {BENCHMARK_MAX // 2} empresas",
        len(companies) >= BENCHMARK_MAX // 2,
        f"Encontradas: {len(companies)}",
        discovery_elapsed,
    )

    if not companies:
        print("  [WARN] Sin empresas para analizar. Abortando Tier 4.")
        return suite

    # ── Analyze (capped at BENCHMARK_MAX) ─────────────────────────────────────
    print(f"  [2/3] Analizando {len(companies)} empresas con LLM...")
    client = AsyncOpenAI(api_key=OPENAI_KEY)
    pipeline_results = []

    async def _noop_stage(stage, status):
        pass

    t0 = time.perf_counter()
    for i, company in enumerate(companies, 1):
        print(f"       [{i}/{len(companies)}] {company.get('title','?')[:40]}")
        try:
            r = await analyze_company(company, TEST_CAMPAIGN, client, _noop_stage)
            pipeline_results.append((company, r))
        except Exception as e:
            pipeline_results.append((company, {"status": "error", "error": str(e)}))
    analysis_elapsed = time.perf_counter() - t0

    # ── 4.1 Tasa de aprobación ≥ 30% ─────────────────────────────────────────
    print(f"\n  [3/3] Validando métricas de calidad...")
    approved_results = [(c, r) for c, r in pipeline_results if r.get("status") == "success"]
    rejected_results = [(c, r) for c, r in pipeline_results if r.get("status") != "success"]
    total = len(pipeline_results)
    approval_rate = len(approved_results) / total if total else 0

    suite.check(
        "Tasa de aprobación ≥ 30%",
        approval_rate >= 0.30,
        f"{len(approved_results)}/{total} aprobados ({approval_rate:.0%})",
        analysis_elapsed,
    )

    # ── 4.2 Sin job boards ni directorios aprobados ───────────────────────────
    from prospector import _is_low_quality_candidate
    junk_approved = [
        c.get("url") for c, r in approved_results
        if _is_low_quality_candidate(c.get("url", ""), c.get("title", ""))
    ]
    suite.check(
        "Sin directorios/job-boards aprobados",
        len(junk_approved) == 0,
        f"Basura aprobada: {junk_approved}" if junk_approved else "OK — solo empresas reales aprobadas",
    )

    # ── 4.3 Score mínimo en aprobados ─────────────────────────────────────────
    low_score = [
        c.get("title") for c, r in approved_results
        if ((r.get("json_payload") or {}).get("score") or 0) < 60
    ]
    suite.check(
        "Todos los aprobados tienen score ≥ 60",
        len(low_score) == 0,
        f"Score bajo: {low_score}" if low_score else "OK",
    )

    # ── 4.4 Emails completos en aprobados ────────────────────────────────────
    no_email = [
        c.get("title") for c, r in approved_results
        if not ((r.get("json_payload") or {}).get("borradores") or {}).get("email_cuerpo")
    ]
    suite.check(
        "Aprobados con borrador de email",
        len(no_email) == 0,
        f"Sin email: {no_email}" if no_email else f"{len(approved_results)} correos generados",
    )

    # ── 4.5 Sin errores de parseo ─────────────────────────────────────────────
    errors = [(c, r) for c, r in pipeline_results if r.get("status") == "error"]
    suite.check(
        "Sin errores de parseo LLM",
        len(errors) == 0,
        f"{len(errors)} errores" if errors else "OK",
    )

    # ── Full results table ─────────────────────────────────────────────────────
    print(f"\n  Resultados completos:")
    for company, result in pipeline_results:
        jp = result.get("json_payload") or {}
        state = result.get("status", "error")
        score = jp.get("score", "—")
        motivo = jp.get("motivo_descalificacion", "")
        icon = "[OK]" if state == "success" else "[FAIL]"
        print(f"  {icon} {company.get('title','?'):<35} score={str(score):<5} {motivo or 'aprobado'}")

    print(f"\n  Resumen: {len(approved_results)} aprobados / {total} analizados ({approval_rate:.0%})")
    return suite


# ── Tier 5: DB integration ─────────────────────────────────────────────────────

MONGODB_URI = os.getenv("MONGODB_URI", "")

async def run_tier5() -> Suite:
    """DB integration: runs pipeline on 3 companies, validates DB state and agent_logs."""
    suite = Suite("Tier 5 — Integracion con DB")
    print(f"\n{'-'*60}")
    print(f"  {suite.name}")
    print(f"{'-'*60}")

    missing = [k for k, v in [("OPENAI_API_KEY", OPENAI_KEY), ("MONGODB_URI", MONGODB_URI)] if not v]
    if missing:
        print(f"  [WARN] Saltado — faltan variables: {', '.join(missing)}")
        return suite

    from openai import AsyncOpenAI
    from prospector import discover_companies, analyze_company
    from database import init_db, get_db, create_run, save_lead, update_run_status

    # ── Setup DB ──────────────────────────────────────────────────────────────
    print("  [1/4] Conectando a MongoDB...")
    t0 = time.perf_counter()
    try:
        await init_db()
        db = get_db()
        suite.check("Conexion a MongoDB exitosa", True, f"URI configurada", time.perf_counter() - t0)
    except Exception as e:
        suite.check("Conexion a MongoDB exitosa", False, str(e))
        return suite

    # ── Create test run ───────────────────────────────────────────────────────
    test_user_id = "test_qa_user"
    run_id = await create_run(test_user_id, "test_campaign_qa", 3)
    suite.check("Run creado en DB", bool(run_id), f"run_id={run_id[:8]}...")

    # ── Run small pipeline ────────────────────────────────────────────────────
    print("  [2/4] Discovery (3 empresas)...")
    companies = await discover_companies(
        "empresas de logistica y transporte de carga", "Bogota",
        max_results=5, gmaps_key=GMAPS_KEY, excluded_domains=set(), use_secop=False,
    )
    companies = companies[:3]
    suite.check(
        "Discovery retorna empresas para analizar",
        len(companies) >= 1,
        f"{len(companies)} encontradas",
    )

    if not companies:
        await update_run_status(run_id, "error")
        return suite

    # ── Analyze + save to DB ──────────────────────────────────────────────────
    print(f"  [3/4] Analizando {len(companies)} empresas con LLM + guardando en DB...")
    client = AsyncOpenAI(api_key=OPENAI_KEY)
    agent_log_lines: list[str] = []

    async def _stage(stage, status):
        pass

    for company in companies:
        result = await analyze_company(company, TEST_CAMPAIGN, client, _stage)
        jp = result.get("json_payload") or {}
        motivo = jp.get("motivo_descalificacion", "")
        if motivo in ("SCRAPING_BLOCKED", "KILL_DIRECT_COMPETITOR"):
            agent_log_lines.append(f"[descartado] {company['title'][:40]} — {motivo}")
            continue
        await save_lead(run_id, test_user_id, {
            "company_name": company.get("title", ""),
            "url": result.get("url", company["url"]),
            "system_state": jp.get("system_state", "REJECTED_BY_AI"),
            "score": jp.get("score"),
            "expediente_json": jp,
        })
        agent_log_lines.append(f"{result['status'].upper()}: {company['title'][:40]}")

    mock_logs = {"analista": agent_log_lines, "buscador": [f"Descubiertas: {len(companies)}"]}
    await update_run_status(run_id, "complete",
                            total_found=len(companies),
                            total_approved=sum(1 for l in agent_log_lines if l.startswith("SUCCESS")),
                            agent_logs=mock_logs)

    # ── Validate DB state ─────────────────────────────────────────────────────
    print("  [4/4] Validando estado en DB...")
    from bson import ObjectId

    # 5.3 leads saved
    saved_leads = await db.leads.find({"run_id": run_id, "user_id": test_user_id}).to_list(length=50)
    suite.check(
        "Leads guardados en DB",
        len(saved_leads) >= 1,
        f"{len(saved_leads)} leads en DB",
    )

    # 5.4 no SCRAPING_BLOCKED in DB
    blocked_in_db = [
        l for l in saved_leads
        if (l.get("expediente_json") or {}).get("motivo_descalificacion") == "SCRAPING_BLOCKED"
    ]
    suite.check(
        "Sin SCRAPING_BLOCKED guardados en DB",
        len(blocked_in_db) == 0,
        f"{len(blocked_in_db)} encontrados" if blocked_in_db else "OK — solo leads reales guardados",
    )

    # 5.5 run has agent_logs
    run_doc = await db.runs.find_one({"_id": ObjectId(run_id)})
    has_logs = bool((run_doc or {}).get("agent_logs"))
    suite.check(
        "Run tiene agent_logs guardados",
        has_logs,
        f"Keys: {list(run_doc.get('agent_logs', {}).keys())}" if has_logs else "agent_logs ausente",
    )

    # 5.6 run status = complete
    suite.check(
        "Run marcado como 'complete'",
        (run_doc or {}).get("status") == "complete",
        f"status={run_doc.get('status') if run_doc else 'null'}",
    )

    # ── Cleanup test data ─────────────────────────────────────────────────────
    await db.leads.delete_many({"run_id": run_id, "user_id": test_user_id})
    await db.runs.delete_one({"_id": ObjectId(run_id)})
    print(f"  [limpieza] datos de prueba eliminados (run_id={run_id[:8]}...)")

    return suite


# ── Runner ─────────────────────────────────────────────────────────────────────

async def main(tiers: list[int]):
    total_pass = 0
    total_fail = 0
    all_suites: list[Suite] = []
    wall_start = time.perf_counter()

    if 1 in tiers:
        s = run_tier1()
        all_suites.append(s)

    if 2 in tiers:
        s = await run_tier2()
        all_suites.append(s)

    if 3 in tiers:
        s = await run_tier3()
        all_suites.append(s)

    if 4 in tiers:
        s = await run_tier4()
        all_suites.append(s)

    if 5 in tiers:
        s = await run_tier5()
        all_suites.append(s)

    # ── Final summary ──────────────────────────────────────────────────────────
    wall_elapsed = time.perf_counter() - wall_start
    print(f"\n{'='*60}")
    print(f"  RESUMEN FINAL  ({wall_elapsed:.1f}s total)")
    print(f"{'='*60}")
    for suite in all_suites:
        p, t = suite.summary()
        bar = "#" * p + "-" * (t - p)
        status = "[OK]" if p == t else "[WARN]" if p >= t * 0.8 else "[FAIL]"
        print(f"  {status}  {suite.name:<45} {p}/{t}  {bar}")

    grand_pass = sum(s.summary()[0] for s in all_suites)
    grand_total = sum(s.summary()[1] for s in all_suites)
    grand_fail = grand_total - grand_pass

    print(f"\n  {'[OK] TODOS LOS TESTS PASARON' if grand_fail == 0 else f'[FAIL] {grand_fail} TESTS FALLARON'}  ({grand_pass}/{grand_total})")

    return grand_fail == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Suite de calidad del pipeline de prospección B2B")
    parser.add_argument(
        "--tier", type=int, nargs="+",
        default=[1, 2, 3, 4],
        help="Tiers a ejecutar (1=filtros, 2=discovery, 3=análisis, 4=benchmark). Default: todos",
    )
    args = parser.parse_args()

    tiers = sorted(set(args.tier))
    print(f"[TEST]  test_campaign.py — Tiers: {tiers} (5=DB integration)")

    success = asyncio.run(main(tiers))
    sys.exit(0 if success else 1)
