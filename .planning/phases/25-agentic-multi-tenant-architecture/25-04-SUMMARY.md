---
phase: 25-agentic-multi-tenant-architecture
plan: "04"
subsystem: cobranza-rag
tags: [rag, pinecone, embeddings, multi-tenant, namespace-isolation]
dependency_graph:
  requires: ["25-01"]
  provides: ["ingest_document", "search_knowledge"]
  affects: ["backend/cobranza/rag_service.py"]
tech_stack:
  added: ["pinecone (async)", "langchain-text-splitters"]
  patterns: ["namespace=user_id isolation", "RecursiveCharacterTextSplitter(1000/100)", "graceful degradation without creds"]
key_files:
  created:
    - backend/cobranza/rag_service.py
  modified:
    - backend/tests/test_cobranza_phase25.py
decisions:
  - "Docstring must not contain the literal 'namespace=None' string — source assertion test checks entire file"
  - "Graceful degradation: missing PINECONE_API_KEY returns error dict / [] instead of raising, enabling CI without real creds"
  - "Pinecone index auto-created on first call (ServerlessSpec aws/us-east-1, dim=1536, cosine)"
  - "Module-level docstring avoids any forbidden pattern text to keep grep-based assertions clean"
metrics:
  duration: "~5 minutes"
  completed: "2026-06-11"
  tasks: 1
  files: 2
---

# Phase 25 Plan 04: RAG Service (Pinecone Namespace Isolation) Summary

Pinecone-backed RAG service with per-tenant namespace isolation. Ingest and search with `assert user_id` guard in every public function prevents cross-tenant data leakage via `namespace=None` silent fail.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 (RED) | Failing tests for RAG namespace isolation | 757baba7 | `tests/test_cobranza_phase25.py` |
| 1 (GREEN) | Implement rag_service.py with Pinecone namespace isolation | 9c0c3473 | `backend/cobranza/rag_service.py` |

## What Was Built

**`backend/cobranza/rag_service.py`** exports two public functions:

- **`ingest_document(user_id, content, title, doc_type) -> dict`**
  - `assert user_id` at entry (T-25-09 mitigation)
  - `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)`
  - Embeds each chunk via `text-embedding-3-small` (1536 dims)
  - Pinecone upsert with `namespace=user_id` — always
  - Saves metadata to MongoDB `rag_documents` via `save_rag_document_metadata`
  - Returns `{"doc_id": str, "chunk_count": int}` or graceful error dict

- **`search_knowledge(user_id, query, top_k=5) -> list[dict]`**
  - `assert user_id` at entry (T-25-09 mitigation)
  - Pinecone query with `namespace=user_id` — always
  - Returns `[{"text", "score", "title", "doc_type"}]` for tenant only
  - Returns `[]` gracefully if no key configured

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Module docstring contained 'namespace=None' text**
- **Found during:** GREEN phase test run
- **Issue:** The plan's ANTI-PATTERNS section mentioned `namespace=None` as forbidden — when copied as documentation into the module docstring, the source assertion test `assert 'namespace=None' not in src` failed
- **Fix:** Rewrote docstring sentence to say "silent cross-tenant leakage" without including the literal forbidden string
- **Files modified:** `backend/cobranza/rag_service.py`
- **Commit:** 9c0c3473 (included in same commit)

## TDD Gate Compliance

- RED gate (test commit): 757baba7 `test(25-04): add failing tests for RAG service namespace isolation`
- GREEN gate (feat commit): 9c0c3473 `feat(25-04): implement RAG service with Pinecone namespace isolation`

Both gates satisfied in correct order.

## Test Results

```
21 passed, 2 xfailed, 4 warnings
```

- 4 new RAG tests: all passing
- 2 xfailed: Telnyx serializer + Gemini Live stubs (Wave 3 — expected, not part of this plan)
- All Wave 1/2 tests still passing — no regressions

## Threat Coverage

| Threat | Status |
|--------|--------|
| T-25-09 Elevation of Privilege (namespace bypass) | MITIGATED — `assert user_id` in both `ingest_document` and `search_knowledge` |
| T-25-10 Information Disclosure (cross-tenant retrieval) | MITIGATED — `namespace=user_id` hardcoded on every upsert/query, never from HTTP input |

## Known Stubs

None — this plan has no UI-visible stubs.

## Self-Check: PASSED

- `backend/cobranza/rag_service.py` exists and parses: FOUND
- RED commit 757baba7: FOUND
- GREEN commit 9c0c3473: FOUND
- `assert user_id` count >= 2: FOUND (2 occurrences)
- `namespace=user_id` present: FOUND
- `namespace=None` absent from source: CONFIRMED
- All 4 RAG tests pass: CONFIRMED
