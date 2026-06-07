---
phase: 20-scraping-improvements
plan: "04"
subsystem: api
tags: [llm, prompt-engineering, industria, discovery, hive, director]

# Dependency graph
requires:
  - phase: 20-scraping-improvements
    provides: Plans 01-03 (curl_cffi, markdownify, blocklist, extract_homepage)
provides:
  - Strengthened _DIRECTOR_PROMPT with literal industria copy instruction
  - _GENERIC_INDUSTRIA_TERMS runtime guard in _discover_companies() overriding LLM generic terms
affects: [hive_graph, hive_tools, prospecting-pipeline, campaign-discovery]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Defense-in-depth prompt + code guard: prompt instructs LLM, code guard catches failures"
    - "frozenset _GENERIC_INDUSTRIA_TERMS pattern for cheap membership test on generic business words"

key-files:
  created: []
  modified:
    - backend/hive_graph.py
    - backend/hive_tools.py

key-decisions:
  - "Two-layer fix: strengthened _DIRECTOR_PROMPT (prompt-level) + _GENERIC_INDUSTRIA_TERMS guard (runtime-level) — neither alone is sufficient"
  - "_GENERIC_INDUSTRIA_TERMS defined as local frozenset inside _discover_companies() — not module-level to avoid confusion with COMPETITOR_GENERIC_WORDS"
  - "Override fires only when campaign has non-empty industria_objetivo AND LLM term is in generic set — no override if campaign field is blank"
  - "Guard inserted AFTER discovery_calls guard and BEFORE logger.info so corrected industria is what gets logged and passed to prospector"

patterns-established:
  - "Pattern: _GENERIC_INDUSTRIA_TERMS frozenset membership check for LLM generic-term detection"
  - "Pattern: logger.warning with %r repr formatting for before/after override audit trail"

requirements-completed: [SCRAPE-03]

# Metrics
duration: 5min
completed: "2026-05-28"
---

# Phase 20 Plan 04: Discovery Industry Fix Summary

**Defense-in-depth fix for director LLM passing `industria='empresas'` instead of the real campaign industry — strengthened `_DIRECTOR_PROMPT` with literal-copy instruction and `_GENERIC_INDUSTRIA_TERMS` runtime override guard in `_discover_companies()`.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-28T14:27:00Z
- **Completed:** 2026-05-28T14:28:13Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments

- `_DIRECTOR_PROMPT` PASO 1 now explicitly instructs the LLM: `industria` MUST be the LITERAL value of 'Industria objetivo', copied exactly — with a concrete counter-example ('Seguros de vida' → NOT 'seguros' NOR 'empresas')
- `_discover_companies()` now silently overrides generic LLM industria values ('empresas', 'empresa', 'negocios', 'negocio', 'companies', 'company', 'business', 'organizaciones', 'organizacion', '') with `campaign['industria_objetivo']`
- Warning log fires on every override so the bug can be observed in Railway logs without code changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Strengthen _DIRECTOR_PROMPT** - `122df0a` (feat)
2. **Task 2: Add _GENERIC_INDUSTRIA_TERMS guard** - `a72cc71` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/hive_graph.py` - PASO 1 first bullet replaced with explicit literal-copy instruction + concrete example
- `backend/hive_tools.py` - `_GENERIC_INDUSTRIA_TERMS` guard inserted after `discovery_calls` guard and before `logger.info` / `n = int(max_r)...` line

## Decisions Made

- Two-layer fix is intentional defense-in-depth: the LLM occasionally ignores prompts under context pressure; the code guard is a silent safety net that never reaches the search engine with a generic term
- `_GENERIC_INDUSTRIA_TERMS` is a local frozenset, not module-level, to avoid confusion with the existing `COMPETITOR_GENERIC_WORDS` module constant (different semantic category)
- Override conditional requires BOTH a non-empty `campaign['industria_objetivo']` AND the LLM term being generic — prevents overriding if the campaign itself has a blank industry field

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 20 (Scraping Improvements) is now fully complete: all 4 plans executed
- Plans 01-03 delivered curl_cffi, markdownify/Crawl4AI, domain blocklist expansion, extract_homepage()
- Plan 04 closes the discovery query bug with prompt + code guard
- Phase 21 (Pipeline Parametrization) can proceed — VerticalConfig and SignalLead depend on Phase 18/20, both complete

---
*Phase: 20-scraping-improvements*
*Completed: 2026-05-28*
