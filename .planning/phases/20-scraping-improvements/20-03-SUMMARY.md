---
phase: 20-scraping-improvements
plan: 03
subsystem: scraping
tags: [curl_cffi, html-markdown, tldextract, scrape_url, discover_via_serper, anti-bot]

# Dependency graph
requires:
  - phase: 20-scraping-improvements
    provides: html_to_compressed_markdown() and extract_homepage() functions (20-02)
provides:
  - scrape_url() using curl_cffi AsyncSession(impersonate="chrome131") instead of httpx
  - scrape_url() producing compressed Markdown via html_to_compressed_markdown(html) instead of raw get_text()
  - discover_via_serper() normalizing each result URL through extract_homepage() before filtering/dedup
affects: [scraping, prospecting-pipeline, anti-bot, token-reduction]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "curl_cffi AsyncSession(impersonate='chrome131') inside scrape_url() — one session per call, not shared module-level"
    - "RequestsError caught at per-candidate level; broad Exception at session level only"
    - "html_to_compressed_markdown(html) receives raw HTML string, not soup — does its own BeautifulSoup parsing internally"
    - "extract_homepage(url) + item['url'] update inserted before BLOCKED_DOMAINS check in discover_via_serper()"

key-files:
  created: []
  modified:
    - backend/prospector.py

key-decisions:
  - "curl_cffi AsyncSession(impersonate='chrome131') replaces httpx.AsyncClient in scrape_url() — TLS fingerprint impersonation defeats Cloudflare WAF detection"
  - "ua_profiles loop removed from scrape_url() — curl_cffi sets all browser headers automatically; manual headers degrade the fingerprint"
  - "RequestsError (not Exception) caught in per-candidate try block — broad Exception kept only at outer session level"
  - "html_to_compressed_markdown(html) wired at end of scrape_url() — soup object retained for contact extraction block above it"
  - "extract_homepage(url) wired before BLOCKED_DOMAINS check in discover_via_serper() — normalizes blog/subpage URLs to company homepages before dedup"

patterns-established:
  - "Pattern: curl_cffi AsyncSession created per scrape_url() call — never shared module-level to avoid max_clients contention"
  - "Pattern: contact extraction (soup, mailto, tel, regex) always runs on raw HTML before any markdown conversion"

requirements-completed: [SCRAPE-01, SCRAPE-02, SCRAPE-04]

# Metrics
duration: 10min
completed: 2026-05-28
---

# Phase 20 Plan 03: Scraping Integration Summary

**curl_cffi chrome131 TLS impersonation active in scrape_url(), Markdown output via html_to_compressed_markdown(), and discover_via_serper() normalizing URLs through extract_homepage() before dedup**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-05-28T14:30:00Z
- **Completed:** 2026-05-28T14:40:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `scrape_url()` now uses `curl_cffi.AsyncSession(impersonate="chrome131")` — TLS/JA3 fingerprint matches Chrome 131, bypassing Cloudflare and similar WAF bot detection
- `ua_profiles` loop (3 User-Agent rotation attempts per candidate) removed — single clean attempt per candidate; curl_cffi auto-generates authentic browser headers
- `scrape_url()` now produces compressed Markdown (via `html_to_compressed_markdown(html)`) instead of raw `soup.get_text()` plain text — significant token reduction for LLM analysis
- `discover_via_serper()` now normalizes each result URL through `extract_homepage(url)` before BLOCKED_DOMAINS check and domain deduplication — blog posts and article paths resolve to company homepages

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace httpx.AsyncClient with curl_cffi AsyncSession in scrape_url()** - `4677c4d` (feat)
2. **Task 2: Wire html_to_compressed_markdown() + extract_homepage() into the pipeline** - `060f370` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/prospector.py` - curl_cffi import added, ua_profiles removed, httpx block replaced with AsyncSession, cleanup block replaced with html_to_compressed_markdown(), extract_homepage() wired in discover_via_serper()

## Decisions Made

- `AsyncSession(impersonate="chrome131", allow_redirects=True, timeout=timeout)` — `allow_redirects` named arg maps to curl_cffi's parameter; `timeout` is a float accepted directly
- The `soup` object created at the start of the contact extraction block (line ~1123) is preserved — it is still used by the contact extraction logic above the new `html_to_compressed_markdown(html)` call
- `item["url"] = url` added alongside `url = extract_homepage(url)` in discover_via_serper — ensures the normalized URL propagates into the result dict, not just the local variable

## Deviations from Plan

**1. [Rule 1 - Bug] Verification check adjusted for multi-line AsyncSession formatting**
- **Found during:** Task 1 verification
- **Issue:** The plan's verify script checks `assert 'AsyncSession(impersonate' in src` as a single string, but the formatted code has a newline between `(` and `impersonate=` — the string spans two lines
- **Fix:** Verification confirmed via two separate checks (`'AsyncSession(' in src` and `'impersonate="chrome131"' in src`) — both present
- **Files modified:** None — code is correct; the verification command in the plan has a formatting mismatch
- **Committed in:** 4677c4d (Task 1 commit)

**2. [Rule 1 - Bug] get_text() pattern check adjusted for fallback presence**
- **Found during:** Task 2 verification
- **Issue:** The plan's verify script checks `assert 'get_text(separator=" ", strip=True)' not in src` for the entire file. But `html_to_compressed_markdown()` (defined in plan 20-02) contains that exact pattern as its bs4 fallback path — so the assertion would always fail
- **Fix:** Confirmed the old `scrape_url()` cleanup block is gone by checking the scrape_url function body specifically; the remaining `get_text` call is in the correct fallback location inside `html_to_compressed_markdown()`
- **Files modified:** None — code is correct; the plan verify check did not account for the 20-02 fallback
- **Committed in:** 060f370 (Task 2 commit)

---

**Total deviations:** 2 (both verification-check mismatches, not code issues — code is correct per spec)
**Impact on plan:** No scope changes. Both deviations were false negatives in the test assertions, not bugs in implementation.

## Issues Encountered

- File required `encoding='utf-8'` in `open()` calls — Windows cp1252 default fails on emoji in the file. Both Python verification commands updated to use `encoding='utf-8'`.

## User Setup Required

None - no external service configuration required. `curl_cffi` was already installed (v0.15.0).

## Known Stubs

None — all three integration points are fully wired and functional.

## Next Phase Readiness

- `scrape_url()` ready: anti-bot scraping active with Chrome 131 TLS fingerprint
- `scrape_url()` ready: compressed Markdown output reduces LLM token consumption
- `discover_via_serper()` ready: homepage normalization prevents blog/article URLs entering the pipeline
- Phase 20 Plan 04 can proceed (remaining scraping improvement: discover query fix / industry pre-population)

---
*Phase: 20-scraping-improvements*
*Completed: 2026-05-28*
