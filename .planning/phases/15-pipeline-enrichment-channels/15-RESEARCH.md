# Phase 15: Pipeline Enrichment + Real Channel Activation — Research

**Researched:** 2026-03-23
**Domain:** Python async pipeline wiring — MongoDB, asyncio tasks, LLM prompt extension
**Confidence:** HIGH (all findings verified directly against source code)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**SECOP bridge (B)**
- In `hive_tools.py`, `make_prospecting_registry(user_id, campaign, ...)` receives `user_id`. Before calling `discover_companies()`, do `await get_or_create_company_voice(user_id)` to obtain `fuentes_habilitadas`.
- Mapping: `"secop_adjudicados" in fuentes_habilitadas` → `use_secop=True`; `"secop_licitaciones" in fuentes_habilitadas` → `use_secop_radar=True`.
- Flags from `campaign` dict serve as fallback if `fuentes_habilitadas` does not exist.
- If `company_voice` does not exist (new client without config), use defaults: `use_secop=False`, `use_secop_radar=False`.

**NIT enrichment (C+D)**
- Called inside `_analyze_company()` in `hive_tools.py`, after the Analista returns its analysis but before saving the lead in MongoDB.
- NIT extracted from `expediente_json` if detected by the Analista, or from SECOP/RUES data if company name matches.
- If NIT cannot be determined → `enrich_nit()` is skipped silently.
- Result merged into `lead.nit_data` as a separate subfield — does NOT replace `expediente_json`.
- 24h cache in `nit_enricher.py` already exists in memory — do not re-implement.
- Enrichment is **non-blocking**: launched as `asyncio.create_task()`. If it fails, log warning and continue.

**WhatsApp phone extraction (A)**
- In `hive_tools.py` Tool 2 (`_analyze_company()`), the Analista prompt already extracts `decisor: {nombre, cargo, email}`. Add `telefono` to the expected output schema.
- The Analista already has access to scraped data — if a phone is visible on the web, it extracts it; if not, it stays `null`.
- In `outreach.py`, when `canal_elegido == "whatsapp"` and `decisor.get("phone")` is empty:
  - Fallback to email if email is available.
  - Register in `historial_conversacion`: `{tipo: "fallback", razon: "no_phone", canal_usado: "email"}`.
  - Log warning with lead_id.
- **No silent failures**: outreach always attempts to send via some channel and records what happened.

**WhatsApp env vars**
- `WA_TOKEN` and `WA_PHONE_ID` are Meta Graph API vars already supported in `whatsapp_sender.py`.
- Add to `.env.example` and document in a comment in `railway.toml` / `vercel.json`.
- In dev mode without these vars: `whatsapp_sender` already logs error and returns `False` — correct behavior.

**Pipeline execution order**
```
discover_companies()  ← reads fuentes_habilitadas → use_secop / use_secop_radar
  ↓
_analyze_company()    ← extracts NIT and decisor phone in the prompt
  ↓
[asyncio.create_task] enrich_nit(nit)   ← non-blocking
  ↓
save lead in MongoDB (with nit_data when enrichment completes)
  ↓
emit lead_checkpoint via WebSocket
```

### Claude's Discretion
- None specified beyond the locked implementation decisions.

### Deferred Ideas (OUT OF SCOPE)
- `whatsapp_agent.py` — conversational Twilio bot for advisors to control the pipeline via WhatsApp. Separate system, requires Twilio webhook + MongoDB sessions. Deferred to Phase 16.
- NIT batch enrichment at campaign start (enrich all discovered companies in parallel) — deferred. First validate individual enrichment works.
- Show `nit_data` in CheckpointModal (lead card) — may be Phase 15.5 or Phase 16 depending on effort.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ENRICH-01 | Activating `secop_adjudicados` in StaffDashboard causes the Investigator to include SECOP companies in the next run — verifiable in server logs | `fuentes_habilitadas` field confirmed written to `company_voice` collection via `POST /api/staff/clients/{id}/sources` (main.py:1598-1600). `hive_tools.py` currently reads only from `campaign` dict (line 127-134). Change is isolated to `_discover_companies()` closure. |
| ENRICH-02 | After scoring, `enrich_nit()` is called with the company's NIT (if it exists) and enriched data appears in the lead's MongoDB expediente | `enrich_nit(nit_raw: str) -> dict` is fully implemented and returns all required fields. `save_lead()` in `database.py` does not currently save `nit_data` — a post-save update via `$set` or a pre-save field addition is needed. |
| ENRICH-03 | Selecting "whatsapp" in CheckpointModal results in a real message sent if the investigator extracted the decisor's phone; if no phone, system falls back to email and logs it | `outreach.py:120-128` already calls `send_whatsapp_text(phone=phone, message=message_text)` and returns `False` when no phone. Fallback logic + historial entry needs to replace the current `return False`. |
</phase_requirements>

---

## Summary

Phase 15 connects three already-implemented but disconnected modules into the live pipeline. Every module exists and is individually functional. The work is entirely about **wiring** — reading `fuentes_habilitadas` from MongoDB instead of the campaign dict, calling `enrich_nit()` at the right point in the pipeline with a `create_task`, and changing `outreach.py` from returning `False` to performing an email fallback.

The most structurally significant change is in `hive_tools.py`: `make_prospecting_registry` is a synchronous factory function that creates async closures. Adding `get_or_create_company_voice(user_id)` requires that the SECOP flag resolution happens inside `_discover_companies()` itself (the async closure), not in `make_prospecting_registry` (which is sync). This is verified by reading the actual call site in `hive_adapter.py:94` — `make_prospecting_registry` is called with `await` nowhere; it is a sync factory.

The NIT enrichment task fires after `save_lead()` completes (so the lead_id is known), but the task itself runs in the background and must call a database `$set` update once complete. This requires a `update_lead_nit_data(lead_id, nit_data)` helper in `database.py` — confirmed not yet present.

**Primary recommendation:** All three changes are self-contained with no cross-team dependencies. Implement in order: (A) WhatsApp fallback in `outreach.py` — smallest change. (B) SECOP bridge in `hive_tools.py` — medium. (C) NIT enrichment task + DB update helper — largest.

---

## Standard Stack

### Core (all pre-existing — no new packages needed)

| Module | Location | Purpose | Status |
|--------|----------|---------|--------|
| `nit_enricher.enrich_nit` | `backend/nit_enricher.py:496` | NIT lookup across RUES, SECOP II, Supersociedades, web | Complete, tested via `test_poc_polizas.py` |
| `get_or_create_company_voice` | `backend/landa/company_voice.py:73` | Fetch or create company voice doc for user | Complete, imported in `outreach.py` |
| `send_whatsapp_text` | `backend/whatsapp_sender.py:15` | Meta Graph API v18.0 message send | Complete, tested in `test_senders.py` |
| `asyncio.create_task` | stdlib | Non-blocking background tasks | Pattern already in `main.py` for `run_outreach` |
| Motor `db.leads.update_one` | `database.py` | MongoDB $set patch on existing document | Pattern already used for `update_lead_hitl` |

### No New Packages Required

All required libraries (`httpx`, `BeautifulSoup`, `motor`, `asyncio`) are already installed. No `pip install` step is needed for this phase.

**Env vars already documented in `.env.example`:**
```
# Landa WhatsApp Sender (Phase 13)
WA_TOKEN=
WA_PHONE_ID=
```
These are already present. Only `railway.toml` / `vercel.json` comments need updating (per locked decision).

Optional env var for Apitude (NIT enricher source 3c):
```
APITUDE_API_KEY=   # Optional — nit_enricher silently skips Apitude if not set
```

---

## Architecture Patterns

### Recommended Project Structure (no new files except DB helper)

```
backend/
├── hive_tools.py         # CHANGE: _discover_companies reads company_voice.fuentes_habilitadas
│                         #         _analyze_company: add telefono to Analista schema +
│                         #         launch create_task(enrich_nit_and_save(nit, lead_id))
├── landa/agents/
│   └── outreach.py       # CHANGE: whatsapp fallback to email when no phone
├── database.py           # ADD: update_lead_nit_data(lead_id, nit_data) -> None
├── nit_enricher.py       # NO CHANGE — already complete
├── whatsapp_sender.py    # NO CHANGE — already complete
└── landa/company_voice.py # NO CHANGE — already complete
```

### Pattern 1: SECOP Flag Resolution Inside Async Closure

`make_prospecting_registry` is a **synchronous** factory (confirmed: `hive_adapter.py:94` calls it without `await`). The async tool closure `_discover_companies` is where `await` calls are valid.

```python
# hive_tools.py — inside _discover_companies() closure
async def _discover_companies(industria: str, ciudad: str, max_r: int = 0) -> dict:
    # ── SECOP flags from company_voice (Phase 15) ──────────────────────────
    from landa.company_voice import get_or_create_company_voice
    try:
        cv = await get_or_create_company_voice(user_id)
        fuentes = cv.get("fuentes_habilitadas") or []
    except Exception as e:
        logger.warning("[discover_companies] company_voice load failed: %s", e)
        fuentes = []

    # Derive flags — campaign dict serves as fallback if fuentes is empty
    if fuentes:
        use_secop      = "secop_adjudicados"  in fuentes
        use_secop_radar = "secop_licitaciones" in fuentes
    else:
        use_secop       = bool(campaign.get("use_secop", False))
        use_secop_radar = bool(campaign.get("use_secop_radar", False))

    # [rest of existing _discover_companies code...]
```

**Key insight:** `get_or_create_company_voice` is already imported in `outreach.py` and follows the same MongoDB async pattern as all other DB calls. No import issues.

### Pattern 2: Non-Blocking NIT Enrichment with Post-Save Update

The lead must be saved first (to get `lead_id`), then enrichment fires as a background task that patches `nit_data` once complete.

```python
# hive_tools.py — inside _analyze_company() after save_lead()
if save_lead and run_id:
    # ... existing save_lead call produces lead_id ...
    result["lead_id"] = lead_id

    # NIT enrichment — non-blocking (Phase 15)
    nit_raw = (json_payload.get("nit")
               or json_payload.get("decisor", {}).get("nit")
               or company.get("nit", ""))
    if nit_raw:
        async def _enrich_and_save(nit: str, lid: str):
            try:
                from nit_enricher import enrich_nit
                from database import update_lead_nit_data
                enriched = await enrich_nit(nit)
                await update_lead_nit_data(lid, enriched)
                logger.info("[analyze_company] NIT enrichment saved for lead %s", lid)
            except Exception as e:
                logger.warning("[analyze_company] NIT enrichment failed for lead %s: %s", lid, e)
        asyncio.create_task(_enrich_and_save(nit_raw, lead_id))
```

### Pattern 3: WhatsApp Fallback to Email

Current `outreach.py:120-128` returns `False` immediately when no phone is available. Replace with graceful fallback:

```python
elif canal_elegido == "whatsapp":
    phone = decisor.get("phone", decisor.get("telefono", ""))
    if phone:
        sent = await send_whatsapp_text(phone=phone, message=message_text)
    else:
        # Fallback to email (Phase 15)
        logger.warning("[outreach_agent] No phone for lead %s — falling back to email", lead_id)
        to_email = decisor.get("email", "")
        if to_email:
            remitentes = company_voice.get("remitentes", [{}])
            sender = remitentes[0] if remitentes else {}
            subject = f"Para {decisor.get('nombre', 'usted')} de {lead.get('company_name', '')}"
            sent = await send_email(
                to=to_email, subject=subject, body=message_text,
                sender_name=sender.get("nombre", ""),
                sender_email=sender.get("email", ""),
            )
            # Record fallback in historial
            fallback_entry = {
                "tipo": "fallback",
                "razon": "no_phone",
                "canal_usado": "email",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await db.leads.update_one(
                {"_id": ObjectId(lead_id)},
                {"$push": {"historial_conversacion": fallback_entry}},
            )
        else:
            logger.error("[outreach_agent] No phone AND no email for lead %s", lead_id)
            sent = False
```

### Pattern 4: `update_lead_nit_data` in database.py

Follow existing `update_lead_hitl` pattern exactly:

```python
# database.py
async def update_lead_nit_data(lead_id: str, nit_data: dict) -> None:
    """Patch nit_data onto an existing lead document after async enrichment completes."""
    db = get_db()
    await db.leads.update_one(
        {"_id": ObjectId(lead_id)},
        {"$set": {"nit_data": nit_data}},
    )
```

### Anti-Patterns to Avoid

- **`await get_or_create_company_voice` in `make_prospecting_registry` (sync function):** The factory is synchronous. All awaits must happen inside the async closures.
- **Blocking on `enrich_nit()` before `save_lead()`:** Enrichment queries 4 external APIs in parallel and can take 5-15 seconds. Blocking would halt the pipeline for every lead. Always use `create_task`.
- **`enrich_nit` without NIT guard:** `enrich_nit("")` or `enrich_nit(None)` returns `{"error": "NIT inválido", "nit_raw": ...}` — the function handles this gracefully, but the task should guard `if nit_raw:` before creating it.
- **Overwriting `decisor` dict in `save_lead`:** The enriched `nit_data` goes in `lead.nit_data`, not merged into `lead.decisor` or `lead.expediente_json`. The save_lead schema has a `decisor` field that maps from `expediente_json.decisor` — don't break this.
- **Raw `telefono` field vs `phone` field:** `outreach.py` already checks `decisor.get("phone", decisor.get("telefono", ""))` — the Analista should output `"telefono"` key in the `decisor` object to align with this existing fallback chain.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Colombian NIT data lookup | Custom RUES/SECOP scrapers | `nit_enricher.enrich_nit(nit_raw)` | Already implements 5 sources in parallel with 24h cache, error isolation per source, and `asyncio.gather` |
| Phone number formatting | Colombian phone regex | Already in `nit_enricher._lookup_web_contact` | Pattern `(?:\+57[\s-]?)?(?:60[1-9]|3[0-9]{2})[\s.-]?\d{3}[\s.-]?\d{4}` is already implemented |
| Company voice fetch | Direct MongoDB query | `get_or_create_company_voice(user_id)` | Handles upsert from `client_profiles`, empty defaults, and `_id` serialization |
| WhatsApp send | Direct Graph API call | `send_whatsapp_text(phone, message)` | Already handles auth, error logging, and returns `bool` |
| Non-blocking task | Thread pool / queue | `asyncio.create_task()` | Already used in `main.py` for `run_outreach` — same event loop |

---

## Common Pitfalls

### Pitfall 1: `make_prospecting_registry` is Synchronous
**What goes wrong:** Developer puts `await get_or_create_company_voice(user_id)` inside `make_prospecting_registry` body (sync function) — Python raises `SyntaxError` or silently creates a coroutine object that never runs.
**Why it happens:** The factory looks like it should be async because it creates async tools.
**How to avoid:** Place all `await` calls inside the async closure `_discover_companies`, not in the factory. Confirmed by reading `hive_adapter.py:94` — registry = `make_prospecting_registry(...)` is sync.
**Warning signs:** Any `await` at the top level of `make_prospecting_registry` before `async def _discover_companies`.

### Pitfall 2: NIT Extraction Depends on Analista Output Field Name
**What goes wrong:** Code checks `json_payload.get("nit")` but the Analista does not return a top-level `nit` field — it returns `decisor.nombre`, `decisor.cargo`, `decisor.email`. There is currently no `nit` field in the Analista output schema (verified in `_analista_prompt` at `prospector.py:483-521`).
**Why it happens:** The context doc assumes the Analista already extracts NIT, but the current prompt schema has no `nit` field.
**How to avoid:** Either (a) add `"nit": "NIT de la empresa si aparece en el sitio o null"` to the Analista JSON schema, or (b) rely on SECOP company data (`company.get("nit")`) which is populated by `secop.py:fetch_secop_providers` for SECOP-sourced leads. For Google Maps leads, NIT likely won't be available — the guard `if nit_raw:` ensures silent skip.
**Warning signs:** `nit_raw` is always empty string even for SECOP leads (NIT is in the `company` dict, not `json_payload`).

### Pitfall 3: `asyncio.create_task` Losing the Task Reference
**What goes wrong:** `asyncio.create_task(...)` without assigning to a variable — Python may garbage-collect the coroutine before it runs if the event loop is under load.
**Why it happens:** CPython's asyncio implementation only weakly references tasks created without assignment.
**How to avoid:** Assign to a local variable: `_task = asyncio.create_task(_enrich_and_save(nit_raw, lead_id))`. The existing `main.py` pattern assigns to `_` which is sufficient. Alternatively, use a module-level set to hold references (overkill for this use case).

### Pitfall 4: `fuentes_habilitadas` Field May Not Exist on Old `company_voice` Documents
**What goes wrong:** `cv.get("fuentes_habilitadas")` returns `None` on documents created before Phase 14 added this field via `POST /api/staff/clients/{id}/sources`. The `or []` guard handles this, but then the code falls through to the `campaign` dict fallback — which is correct behavior per locked decisions.
**Why it happens:** MongoDB schema is schemaless; old documents don't have the field.
**How to avoid:** The pattern `fuentes = cv.get("fuentes_habilitadas") or []` already handles this. The `if fuentes: ... else: [use campaign fallback]` branching in the locked decision is the correct implementation.

### Pitfall 5: `_analyze_company` `_state` Variable Shadowing
**What goes wrong:** `hive_tools.py:217` already has `_state = {...}` inside `on_stage` callback — this shadows the outer `_state: dict` at the module closure level. Any attempt to read or modify `_state["analyzed"]` inside the new enrichment task must close over the outer `_state`, not the inner one.
**Why it happens:** Python's lexical scoping — inner `_state = {...}` in `on_stage` creates a new binding.
**How to avoid:** The enrichment task `_enrich_and_save` is defined after `on_stage`, and the outer `_state` is only modified via `_state["analyzed"] += 1` etc. The new enrichment code does not touch `_state` at all — it only reads `lead_id` (captured from the outer closure). No conflict.

---

## Code Examples

Verified patterns from source code:

### Current SECOP flag reading (lines to replace)
```python
# hive_tools.py:127-134 — CURRENT (reads from campaign dict only)
use_secop_radar = bool(campaign.get("use_secop_radar", False))
companies = await discover_companies(
    industria, ciudad, n, gmaps_key,
    excluded_domains=excluded_set,
    use_secop=bool(campaign.get("use_secop", False)),
)
```

### `enrich_nit` return schema (verified from nit_enricher.py:587-634)
```python
{
    "nit": "900123456",                    # cleaned digits only
    "nit_raw": "900.123.456-7",            # original input
    "razon_social": "Empresa SAS",         # from RUES
    "representante_legal": "Juan Perez",   # from RUES
    "estado": "Activa",                    # from RUES
    "tipo_sociedad": "SAS",
    "fecha_matricula": "2015-03-12",
    "camara_comercio": "Bogota",
    "direccion": "Cra 7 No 32-16",
    "municipio": "Bogota",
    "objeto_social": None,
    "website": "https://empresa.co",       # from SECOP Proveedor > Web
    "email": "contacto@empresa.co",        # from SECOP Proveedor > Web
    "phone": "3101234567",                 # from SECOP Proveedor > Apitude > Web
    "direccion_oficial": "Cra 7 No 32-16",
    "rep_legal_telefono": "6011234567",    # from SECOP Proveedor
    "rep_legal_email": "rep@empresa.co",
    "es_pyme": "SI",
    "categoria_secop": "Ingenieria y Consultoria",
    "contratos_secop": 12,                 # KEY FIELD for ENRICH-02
    "valor_total_contratado": 850000000.0, # KEY FIELD for ENRICH-02
    "valor_total_fmt": "$850M COP",
    "entidades_contratantes": ["INVIAS", "IDU", "Gobernacion"],
    "ultimo_contrato": "Consultoria en diseño vial...",
    "ingresos_operacionales": None,        # only if in Supersociedades
    "activos_totales": None,
    "anio_reporte_financiero": None,
    "fuentes_consultadas": ["RUES", "SECOP II", "SECOP Proveedores"],
    "advertencia_poliza": "Empresa SAS tiene 12 contratos públicos...",
}
```

### `get_or_create_company_voice` — return schema (verified company_voice.py:73-107)
```python
# Returns dict with all COMPANY_VOICE_KEYS + user_id + fuentes_habilitadas (if set)
# COMPANY_VOICE_KEYS does NOT include fuentes_habilitadas — it's added via $set in main.py
# The field may be absent on old documents — always use .get("fuentes_habilitadas") or []
{
    "user_id": "...",
    "remitentes": [...],
    "tono_empresa": "...",
    "fuentes_habilitadas": ["google_maps", "secop_adjudicados"],  # may be absent!
    # ... other COMPANY_VOICE_KEYS fields
}
```

### `save_lead` — fields available for NIT context (verified database.py:400-431)
```python
# save_lead() does NOT have a nit_data field — must add via update_one after save
# The field "decisor" is saved from lead_data.get("decisor") — this comes from
# json_payload.get("decisor") which is the Motor scoring output (not Analista)
# Motor output schema (prospector.py:569):
# {"decisor": {"nombre": "...", "cargo": "...", "email": "..."}}
# After Phase 15: Analista output will also include "telefono" in decisor block
```

### Existing `update_lead_hitl` pattern to follow (database.py:452-458)
```python
async def update_lead_hitl(lead_id: str, user_id: str, decision: str) -> bool:
    db = get_db()
    result = await db.leads.update_one(
        {"_id": ObjectId(lead_id), "user_id": user_id},
        {"$set": {"hitl_status": decision, "hitl_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count == 1
```

---

## Critical Discovery: The `decisor` Field Flow

This is the most important architectural insight for getting phone extraction right:

**Two-stage LLM pipeline, two different `decisor` schemas:**

1. **Stage 2 — Analista** (`_analista_prompt`, `prospector.py:483`): Returns `decisor: {nombre, cargo, email}`. This is the raw extraction from scraped HTML. Currently **no `telefono` field**.

2. **Stage 3 — Motor Scoring** (`_motor_scoring_prompt`, `prospector.py:523`): For approved leads, returns `decisor: {nombre, cargo, email}`. The Motor receives the Analista's output as context and may re-surface the decisor. Currently **no `telefono` field** here either.

3. **`save_lead` in `hive_tools.py:259-270`**: Saves `expediente_json = json_payload` where `json_payload` is the Motor output. The `decisor` field in the saved lead document comes from `json_payload.get("decisor")`.

4. **`outreach.py:68`**: Reads `decisor = lead.get("decisor") or {}` from MongoDB, then `phone = decisor.get("phone", decisor.get("telefono", ""))`.

**Conclusion:** To get `telefono` into the lead's `decisor` in MongoDB:
- Option A (locked decision): Add `"telefono": "..."` to the Analista prompt schema → Motor receives it → Motor must preserve it in its output schema → Motor output `decisor.telefono` flows into MongoDB via `json_payload`.
- The Motor output schema (line 569) must also be extended: `"decisor": {"nombre", "cargo", "email", "telefono"}`.
- This is a **two-prompt change**: both `_analista_prompt` and the Motor schema in `_motor_scoring_prompt` need `telefono`.

---

## State of the Art

| Old Approach | Current Approach | Implication |
|--------------|------------------|-------------|
| `use_secop` read from `campaign` dict | `use_secop` derived from `company_voice.fuentes_habilitadas` | Enables per-user SECOP toggle without rebuilding campaign |
| NIT enrichment not called | `enrich_nit()` called as `create_task` post-save | Lead appears at checkpoint without NIT data; NIT data added asynchronously |
| WhatsApp fails silently (returns False) | WhatsApp falls back to email with historial entry | No lead is lost due to missing phone |

**The `fuentes_habilitadas` field** is written by `POST /api/staff/clients/{id}/sources` (main.py:1598-1600) directly to `company_voice` collection using `$set` with `upsert=True`. This means the field appears on the document **in addition to** the COMPANY_VOICE_KEYS defined in `company_voice.py`. The `get_or_create_company_voice` function returns the raw MongoDB document, so `fuentes_habilitadas` will be in the returned dict when set.

---

## Open Questions

1. **Should `telefono` pass through the Motor scoring stage?**
   - What we know: The Motor output schema (line 569) is hardcoded in `_motor_scoring_prompt`. If the Motor doesn't include `telefono` in its approved-lead output, the field won't reach MongoDB even if the Analista extracted it.
   - What's unclear: Whether the Motor LLM will reliably forward `telefono` if it's in the Analista context but not in the Motor output schema.
   - Recommendation: Add `"telefono": "telefono del decisor extraído o null"` explicitly to the Motor's approved-lead JSON schema on line 569. This guarantees it flows through.

2. **Is NIT available for Google Maps leads (non-SECOP sources)?**
   - What we know: `secop.py:fetch_secop_providers` populates `nit` in each company dict for SECOP-sourced leads. Google Maps leads (`discover_companies_gmaps`) do NOT include NIT — it's not in the Places API response.
   - What's unclear: Whether the Analista reliably extracts NIT from scraped web pages (some Colombian companies display it in footer/contact pages).
   - Recommendation: Add `"nit": "NIT de la empresa si aparece en el sitio, sin puntos ni guion verificacion, o null"` to the Analista schema. Accept that NIT enrichment will be opportunistic for Google Maps leads and guaranteed for SECOP leads.

3. **Task reference retention for `create_task`**
   - What we know: CPython may GC fire-and-forget tasks. The existing `main.py` pattern stores tasks via assignment.
   - Recommendation: Assign `_task = asyncio.create_task(...)` and optionally log if needed. No need for a global task set.

---

## Validation Architecture

`nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode = auto) |
| Config file | `backend/pytest.ini` |
| Quick run command | `cd backend && python -m pytest tests/test_enrichment.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENRICH-01 | `_discover_companies` reads `fuentes_habilitadas` from company_voice and derives `use_secop=True` when `"secop_adjudicados"` is present | unit | `pytest tests/test_enrichment.py::test_secop_flag_from_company_voice -x` | Wave 0 |
| ENRICH-01 | Fallback to `campaign` dict when `fuentes_habilitadas` is absent | unit | `pytest tests/test_enrichment.py::test_secop_flag_fallback_to_campaign -x` | Wave 0 |
| ENRICH-02 | `enrich_nit` is called and `nit_data` appears in MongoDB after async task | unit + mock | `pytest tests/test_enrichment.py::test_nit_enrichment_saved_to_lead -x` | Wave 0 |
| ENRICH-02 | If NIT is absent, enrichment is skipped silently | unit | `pytest tests/test_enrichment.py::test_nit_enrichment_skipped_when_no_nit -x` | Wave 0 |
| ENRICH-03 | WhatsApp sends when phone is available | unit | `pytest tests/test_enrichment.py::test_outreach_whatsapp_sends_with_phone -x` | Wave 0 |
| ENRICH-03 | Fallback to email when no phone, historial entry recorded | unit | `pytest tests/test_enrichment.py::test_outreach_whatsapp_fallback_to_email -x` | Wave 0 |
| ENRICH-03 | No phone AND no email → `sent=False`, no crash | unit | `pytest tests/test_enrichment.py::test_outreach_no_phone_no_email -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && python -m pytest tests/test_enrichment.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_enrichment.py` — covers ENRICH-01, ENRICH-02, ENRICH-03 (7 stubs)
- [ ] `conftest.py` already exists at `backend/tests/conftest.py` — reuse existing fixtures

Note: `test_senders.py` already covers `send_whatsapp_text` (creds-present and creds-absent paths). The new enrichment tests mock `enrich_nit`, `get_or_create_company_voice`, and `db.leads.update_one` to avoid network calls.

---

## Sources

### Primary (HIGH confidence)

All findings verified by direct source code inspection:

- `backend/hive_tools.py` — `make_prospecting_registry`, `_discover_companies`, `_analyze_company`, `save_lead` call, lines 1-363
- `backend/nit_enricher.py` — `enrich_nit` signature (line 496), full return dict (lines 587-634), `enrich_nits_batch` (line 637), env var `APITUDE_API_KEY` (line 336)
- `backend/landa/agents/outreach.py` — `run_outreach`, WhatsApp branch (lines 120-128), historial pattern (lines 131-145)
- `backend/whatsapp_sender.py` — `send_whatsapp_text`, env var requirements `WA_TOKEN` + `WA_PHONE_ID` (lines 15-45)
- `backend/landa/company_voice.py` — `get_or_create_company_voice`, `COMPANY_VOICE_KEYS` (lines 73-107)
- `backend/database.py` — `save_lead` schema (lines 400-431), `update_lead_hitl` pattern (lines 452-458), absence of `update_lead_nit_data`
- `backend/prospector.py` — `_analista_prompt` JSON schema (lines 483-521), `_motor_scoring_prompt` approved output schema (line 569), `analyze_company` function (lines 689-800+)
- `backend/hive_adapter.py` — `make_prospecting_registry` called synchronously (line 94), `start_run` is async context
- `backend/main.py` — `fuentes_habilitadas` endpoint (lines 1573-1607), `VALID_SOURCES` set
- `backend/.env.example` — `WA_TOKEN` and `WA_PHONE_ID` already documented (lines 19-20)
- `.planning/config.json` — `nyquist_validation: true`

### Secondary (MEDIUM confidence)

- `backend/tests/test_senders.py` — existing WhatsApp test pattern to follow for new enrichment tests
- `backend/tests/conftest.py` — existing test infrastructure (asyncio fixtures, reset_db)
- `.planning/phases/15-pipeline-enrichment-channels/15-CONTEXT.md` — all locked decisions

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all modules verified by source inspection, no ambiguity
- Architecture: HIGH — call sites confirmed (hive_adapter → hive_tools sync factory → async closures)
- Pitfalls: HIGH — NIT field absence and sync factory issue confirmed by reading code, not inferred
- Validation: HIGH — pytest infrastructure confirmed at `backend/pytest.ini` and `backend/tests/`

**Research date:** 2026-03-23
**Valid until:** 2026-04-22 (stable — no external API changes expected; SECOP dataset endpoint is public Colombian gov data)
