---
plan: 20-01
phase: 20-scraping-improvements
status: complete
completed: 2026-05-27
---

# Plan 20-01: Dockerfile.worker + deps + test scaffold

## What Was Built

Created the Railway Worker Dockerfile using Microsoft's official Playwright base image so Crawl4AI can run without Nixpacks GLIBC issues. Added all new dependencies. Created xfail test stubs.

## Key Files

### Created
- `backend/Dockerfile.worker` — `mcr.microsoft.com/playwright/python:v1.49.0-noble` base image, `CRAWL4AI_MODE=api`, `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`
- `backend/tests/test_scrape.py` — 4 xfail stubs for SCRAPE-01..04

### Modified
- `railway-worker.toml` — added `dockerfilePath = "Dockerfile.worker"`
- `backend/requirements.txt` — added `curl_cffi==0.15.0`, `crawl4ai>=0.4.21`, `tldextract==5.3.1`

## Commits
- `9eeee33` feat(20-01): add Dockerfile.worker + crawl4ai/tldextract deps + test stubs

## Self-Check: PASSED

- [x] `backend/Dockerfile.worker` uses `mcr.microsoft.com/playwright/python:v1.49.0-noble`
- [x] `railway-worker.toml` has `dockerfilePath = "Dockerfile.worker"`
- [x] `backend/requirements.txt` contains `crawl4ai>=0.4.21`, `tldextract==5.3.1`, `curl_cffi==0.15.0`
- [x] No `markdownify` in requirements.txt
