---
phase: 12
plan: "03"
subsystem: landa
tags: [sector-intelligence, company-voice, gpt-4o, mongodb-cache, brand-voice]
dependency_graph:
  requires: [database.get_db, client_profiles collection]
  provides: [landa.sector_profiles.generate_sector_profile, landa.company_voice.get_or_create_company_voice]
  affects: [landa outreach pipeline, persona generation]
tech_stack:
  added: [openai AsyncOpenAI, sector_profiles MongoDB collection, company_voice MongoDB collection]
  patterns: [30-day MongoDB cache pattern, profile-sync-on-first-access]
key_files:
  created:
    - backend/landa/sector_profiles.py
    - backend/landa/company_voice.py
  modified: []
decisions:
  - "Deferred openai import inside function body to avoid import-time failure when OPENAI_API_KEY is not set"
  - "company_voice collection is separate from client_profiles — avoids mutating onboarding data"
  - "Empty voice scaffold uses list/dict/bool/str type defaults matching COMPANY_VOICE_KEYS schema"
metrics:
  duration: "~5 min"
  completed_date: "2026-03-22"
  tasks_completed: 2
  files_created: 2
---

# Phase 12 Plan 03: Sector Profiles and Company Voice Summary

**One-liner:** GPT-4o sector intelligence with 30-day MongoDB cache plus brand voice synced from client_profiles on first access.

## What Was Built

### sector_profiles.py

- `generate_sector_profile(sector, pais_region, tamano)` — async function returning a 12-key sector intelligence profile
- Cache lookup against `sector_profiles` collection (cutoff = now - 30 days)
- On cache miss: calls GPT-4o with `response_format=json_object`, temperature 0.2
- Saves result to MongoDB with `created_at` timestamp; returns doc with stringified `_id`
- `SECTOR_PROFILE_KEYS` constant enumerates the 12 expected profile fields
- `OPENAI_API_KEY` and `OPENAI_MODEL` read from env (defaults to `gpt-4o`)

### company_voice.py

- `get_or_create_company_voice(user_id)` — async function returning full company_voice document
- Checks `company_voice` collection first (cache hit path)
- On miss: reads `client_profiles` for that user and maps via `_map_from_client_profile()`
- If no client_profile exists: builds empty scaffold with correct types for all 13 COMPANY_VOICE_KEYS
- `synced_from_profile` bool field records whether data came from onboarding
- `_map_from_client_profile()` extracts agents list as `remitentes`, maps all campaign.* fields

## Verification

```
syntax OK
imports OK
```

Both modules parse cleanly and import without errors from `backend/` working directory.

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash | Description |
|------|-------------|
| ee1520e | feat(12-03): add sector_profiles and company_voice modules to landa/ |

## Self-Check: PASSED

- `backend/landa/sector_profiles.py` — FOUND
- `backend/landa/company_voice.py` — FOUND
- commit ee1520e — FOUND
