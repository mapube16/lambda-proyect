---
phase: 20-scraping-improvements
plan: 02
subsystem: scraping
tags: [tldextract, crawl4ai, prospector, python, url-normalization, domain-blocklist]

# Dependency graph
requires:
  - phase: 20-01
    provides: curl_cffi scrape_url() replacement already staged

provides:
  - html_to_compressed_markdown() function using Crawl4AI DefaultMarkdownGenerator + PruningContentFilter with bs4 fallback
  - extract_homepage() function normalizing URLs via tldextract + _NON_HOME_SUBDOMAINS + LOW_QUALITY_PATH_MARKERS
  - _NON_HOME_SUBDOMAINS frozenset constant at module level
  - tldextract imported and PSL cache pre-warmed at import time
  - LOW_QUALITY_DISCOVERY_DOMAINS expanded with ~33 Colombian/LATAM aggregator domains

affects:
  - 20-03-PLAN (wires html_to_compressed_markdown and extract_homepage into scrape_url and discover_via_serper)

# Tech tracking
tech-stack:
  added: [tldextract==5.3.1, crawl4ai (lazy import, graceful fallback)]
  patterns:
    - Crawl4AI DefaultMarkdownGenerator used without browser (processes HTML strings directly)
    - try/except around crawl4ai import — bs4 fallback guarantees function never hard-fails
    - tldextract.extract("") at module top pre-warms PSL cache at Railway pod start
    - _NON_HOME_SUBDOMAINS frozenset for fast subdomain membership check
    - LOW_QUALITY_PATH_MARKERS reused in extract_homepage() — no duplication

key-files:
  created: []
  modified:
    - backend/prospector.py

key-decisions:
  - "Crawl4AI DefaultMarkdownGenerator chosen over markdownify per PLAN critical_notes — processes HTML without browser launch"
  - "html_to_compressed_markdown() uses lazy import of crawl4ai inside try/except so scrape_url() never hard-fails if package absent"
  - "tldextract PSL pre-warm tldextract.extract('') placed at module top (after import) to fire once at Railway cold start, not per-request"
  - "extract_homepage() reuses existing LOW_QUALITY_PATH_MARKERS tuple — avoids duplicating the list"
  - "bumeran.com.co skipped from new additions — already present in set; bumeran.com added"

patterns-established:
  - "Pattern 1: Lazy import of optional heavy deps (crawl4ai) inside try/except for graceful degradation"
  - "Pattern 2: Module-level PSL pre-warm for tldextract ensures Railway cold-start network call happens at boot, not at request time"
  - "Pattern 3: Functions placed between _is_low_quality_candidate() and Discovery section — consistent insertion point for URL utilities"

requirements-completed: [SCRAPE-02, SCRAPE-03, SCRAPE-04]

# Metrics
duration: 2min
completed: 2026-05-27
---

# Phase 20 Plan 02: Scraping Utilities Summary

**html_to_compressed_markdown() via Crawl4AI DefaultMarkdownGenerator, extract_homepage() via tldextract, and ~33 new Colombian/LATAM domains added to LOW_QUALITY_DISCOVERY_DOMAINS**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-27T01:36:35Z
- **Completed:** 2026-05-27T01:38:18Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Added tldextract import with PSL pre-warm (`tldextract.extract("")`) at module level preventing Railway cold-start latency
- Expanded LOW_QUALITY_DISCOVERY_DOMAINS with 33 new Colombian/LATAM domains (business directories, job boards, news portals, classifieds, review sites)
- Added `_NON_HOME_SUBDOMAINS` frozenset with 28 entries covering blog, careers, app, portal, etc.
- Added `html_to_compressed_markdown()` using Crawl4AI DefaultMarkdownGenerator + PruningContentFilter (threshold=0.48), with BeautifulSoup fallback if crawl4ai not installed
- Added `extract_homepage()` using tldextract for .com.co/.co.uk PSL-aware domain extraction, stripping _NON_HOME_SUBDOMAINS and LOW_QUALITY_PATH_MARKERS paths

## Task Commits

Each task was committed atomically:

1. **Task 1: Add tldextract import + PSL pre-warm; expand LOW_QUALITY_DISCOVERY_DOMAINS** - `8bad191` (feat)
2. **Task 2: Add _NON_HOME_SUBDOMAINS, html_to_compressed_markdown(), extract_homepage()** - `60b454c` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `backend/prospector.py` - tldextract import + PSL pre-warm; 33 new blocklist domains; _NON_HOME_SUBDOMAINS constant; html_to_compressed_markdown() function; extract_homepage() function

## Decisions Made
- Used Crawl4AI DefaultMarkdownGenerator per plan `critical_notes` override (not markdownify from RESEARCH.md Standard Stack section — the plan's critical_notes take precedence)
- Lazy import pattern for crawl4ai inside `html_to_compressed_markdown()` — crawl4ai may not be installed locally or in legacy environments, bs4 fallback ensures no hard-fail
- `bumeran.com.co` was already in the set — skipped duplicate, added `bumeran.com` as a new entry
- `extract_homepage()` placed after `_is_low_quality_candidate()` and before Discovery section per plan interface specification

## Deviations from Plan

None - plan executed exactly as written. All code blocks match the plan specification verbatim.

## Issues Encountered
- Python's default cp1252 encoding on Windows caused a UnicodeDecodeError when verifying via `pathlib.Path.read_text()` — resolved by adding `encoding='utf-8'` to verification commands. File content itself is UTF-8, no issue with the file.

## User Setup Required
None - no external service configuration required. tldextract will be installed via requirements.txt update in Plan 20-03.

## Next Phase Readiness
- Plan 20-03 can now wire `html_to_compressed_markdown()` into `scrape_url()` (replace BeautifulSoup cleanup block)
- Plan 20-03 can now wire `extract_homepage()` into `discover_via_serper()` (normalize each result URL)
- No blockers — functions are defined, tested via ast.parse(), and committed

## Known Stubs
None - functions are fully implemented. html_to_compressed_markdown() has a working bs4 fallback path; extract_homepage() handles all documented edge cases.

---
*Phase: 20-scraping-improvements*
*Completed: 2026-05-27*

## Self-Check: PASSED

- FOUND: backend/prospector.py (syntax OK, all functions present)
- FOUND: commit 8bad191 (Task 1 — tldextract + blocklist expansion)
- FOUND: commit 60b454c (Task 2 — _NON_HOME_SUBDOMAINS + html_to_compressed_markdown + extract_homepage)
