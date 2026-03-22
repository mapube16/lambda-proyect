# Phase 14: Landa API & Checkpoint UI - Research

**Researched:** 2026-03-22
**Domain:** FastAPI REST endpoints, WebSocket event emission, React modal/overlay UI, lead lifecycle state transitions
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Pixel art: agent states for captation module**
- Investigador: thinking/tool_use/waiting ("Tengo [N] candidatos listos")/idle
- Outreach: thinking/tool_use/waiting ("Esperando respuesta de [empresa]")/idle
- Nurturing: thinking/tool_use/waiting ("Monitoreando señales")/idle
- Click on "waiting" (checkpoint) → opens panel/modal overlay with lead card (empresa, decisor, puntaje, criterios, canales + probabilities, buttons Aprobar/Pausar/Rechazar)
- Click on "waiting" (handover) → different panel: hilo + sugerencia de cierre + "Tomar el control"
- NOT a separate screen — overlay over pixel art

**API del ciclo de vida de leads (exact contract):**
- `GET /api/leads/checkpoint` — leads en estado "checkpoint" del usuario autenticado
- `POST /api/leads/{id}/decision` — body: {decision: "aprobar"|"pausar"|"rechazar", canal_elegido?, motivo?}
  - "aprobar" → dispara run_outreach() in background
  - "rechazar" → update_lead_estado(→ "nurturing"), motivo="rechazado_humano"
- `GET /api/leads/{id}/handover` — paquete: {lead, hilo_conversacion, calificacion_original, sugerencia_cierre}
- `POST /api/leads/{id}/handover/tomar` → update_lead_estado(→ "handover") + cancel_lead_actions(lead_id)
- `POST /api/leads/{id}/reporte-llamada` — body: {resultado: "bien"|"mas_o_menos"|"mal"|"no_pude", detalle?, sub_tipo?}

**Reporte-llamada logic:**
- "bien"/"mas_o_menos" → IA interpreta detalle → decide acción
- "mal" → nurturing, motivo=detalle
- "no_pude" ocupado/apagado → schedule_retry(days=1)
- "no_pude" incorrecto → buscar número alternativo (flag en lead)
- "no_pude" corto → cuenta como intento 1, schedule_retry(days=7)
- Si reporte no llega en 48h → scheduler cancela acciones + notifica humano

**WebSocket notifications — exact event types:**
```json
{"type": "lead_checkpoint", "lead_id": "...", "empresa": "...", "puntaje": 84}
{"type": "lead_handover",   "lead_id": "...", "empresa": "...", "canal": "whatsapp"}
{"type": "lead_archived",   "lead_id": "...", "empresa": "..."}
```

**SECOP premium feature — Staff Dashboard:**
- Toggle en staff dashboard, vista de configuración por cliente
- Campo `fuentes_habilitadas` en `company_voice`: default ["google_maps"], add-ons: "secop_adjudicados", "secop_licitaciones"
- `POST /api/staff/clients/{user_id}/sources` — actualiza `company_voice.fuentes_habilitadas`
- El flag se lee en `run_investigador()` de Phase 13

**Pixel art integration — extending existing:**
- AgentPanel.tsx: extender con texto semántico + onClick → modal
- StaffDashboard.tsx: agregar panel "Fuentes de descubrimiento" por cliente

### Claude's Discretion

- Exact shape of the IA interpretation logic for "bien"/"mas_o_menos" call reports
- Whether `sugerencia_cierre` is cached or generated on-demand in GET /handover
- Exact Pydantic schemas for request/response bodies (beyond what's specified)
- Test structure for LANDA-09 through LANDA-12

### Deferred Ideas (OUT OF SCOPE)

- Catálogo de agentes (app store de verticales Landa)
- Self-service de planes y precios
- LinkedIn, Instagram, TikTok como canales de outreach
- Notificaciones por Slack webhook
- WhatsApp como canal de onboarding del usuario final
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LANDA-09 | `GET /api/leads/checkpoint` + `POST /api/leads/{id}/decision` with state transitions and run_outreach() dispatch | MongoDB query by estado + user_id index exists; update_lead_estado() ready; run_outreach() will be ready from Phase 13 |
| LANDA-10 | `GET /api/leads/{id}/handover` package + `POST /api/leads/{id}/handover/tomar` freezing agent | cancel_lead_actions() ready in scheduler.py; historial_conversacion pattern established in Phase 13 |
| LANDA-11 | `POST /api/leads/{id}/reporte-llamada` with 4 result types and internal logic | schedule_retry() and schedule_nurturing() ready in scheduler.py; update_lead_estado() ready |
| LANDA-12 | Frontend checkpoint view with lead cards, action buttons, channel selector, real-time WS updates | WebSocket handleMessage() switch in useWebSocket.ts; AgentPanel.tsx extend pattern; officeStore.ts Zustand patterns established |
</phase_requirements>

---

## Summary

Phase 14 is a pure integration phase: it connects already-built backend infrastructure (state machine, scheduler, agents from Phases 12-13) to the human via REST endpoints and a pixel-art overlay UI. There is no net-new architectural invention required — the patterns are all established. Every building block exists: `update_lead_estado()` enforces transitions, `cancel_lead_actions()` / `schedule_retry()` handle scheduling, `manager.send_to_user()` handles WebSocket delivery, and AgentPanel.tsx + useWebSocket.ts have the hooks for new message types.

The main complexity is in the `POST /api/leads/{id}/reporte-llamada` endpoint, which has branching logic that calls GPT-4o to interpret ambiguous "bien"/"mas_o_menos" results. This call should be fire-and-forget (asyncio.create_task) to keep the endpoint response fast. The 48h no-report scheduler is also new: a one-time job scheduled when handover.tomar is called.

The frontend work (LANDA-12) extends the existing AgentPanel.tsx. The pattern is: new WS message types → new case in handleMessage() → new state in officeStore → conditional render of modal overlay in AgentPanel. This is a surgical extension, not a rewrite.

**Primary recommendation:** Build all 4 API endpoints first (Wave 1), then extend the frontend (Wave 2). Test with xfail stubs in Wave 0. Keep AI interpretation in reporte-llamada as a simple fire-and-forget asyncio.create_task call.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | REST endpoints + Pydantic validation | Already the project framework |
| Motor (asyncio) | 3.7.1 | MongoDB async reads/writes | Already in use for all DB ops |
| APScheduler (AsyncIOScheduler) | existing | 48h no-report job | Already in scheduler.py |
| Pydantic BaseModel | existing | Request body validation | Pattern in main.py via `_BaseModel` alias |
| jose / JWT | existing | Auth guard on all endpoints | `Depends(get_current_user)` pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio.create_task | stdlib | Fire-and-forget background work | run_outreach() after decision, IA interpretation after reporte |
| OpenAI via existing call_agent | existing | "bien"/"mas_o_menos" interpretation | Only for ambiguous call reports |
| React + Zustand | existing | Frontend state management | officeStore.ts extension |

### Installation
No new packages needed. All dependencies are already installed.

---

## Architecture Patterns

### Pattern 1: FastAPI endpoint adding to main.py

**What:** New endpoints follow the `@app.post(...)` + `Depends(get_current_user)` pattern already in main.py. Business logic lives in the landa/ package, main.py just orchestrates.

**When to use:** All 5 new endpoints (checkpoint GET/POST, handover GET/POST, reporte-llamada POST, staff sources POST).

**Example:**
```python
# Source: existing pattern in main.py lines 658-689
@app.post("/api/leads/{lead_id}/decision")
async def lead_decision(
    lead_id: str,
    request: LeadDecisionRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])
    # ... call update_lead_estado(), schedule background task
    await manager.send_to_user(user_id, {"type": "lead_archived", "lead_id": lead_id, ...})
    return {"status": "ok", "lead_id": lead_id}
```

### Pattern 2: WebSocket event emission from endpoint

**What:** After an endpoint mutates lead state, it emits a WebSocket event via `manager.send_to_user(user_id, {...})`. This is the existing pattern for all state notifications.

**When to use:** All POST endpoints that cause a lead state change.

**Example:**
```python
# Source: manager.send_to_user in main.py line 71
await manager.send_to_user(user_id, {
    "type": "lead_checkpoint",
    "lead_id": lead_id,
    "empresa": lead["company_name"],
    "puntaje": lead.get("puntaje", 0),
})
```

### Pattern 3: Fire-and-forget background task

**What:** When an endpoint triggers slow work (run_outreach, IA interpretation), use `asyncio.create_task()` so the HTTP response returns immediately.

**When to use:** POST /decision (approve → run_outreach), POST /reporte-llamada (bien/mas_o_menos → IA decision).

**Example:**
```python
# Source: existing pattern main.py line 488
asyncio.create_task(_run_outreach_background(lead_id, user_id, canal_elegido))
return {"status": "aprobado", "lead_id": lead_id}
```

### Pattern 4: MongoDB query by estado + user_id

**What:** The compound index `[("user_id", 1), ("estado", 1)]` already exists in database.py (line 40). GET /checkpoint just queries this index.

**When to use:** GET /api/leads/checkpoint.

**Example:**
```python
# Source: database.py index line 40
leads = await db.leads.find(
    {"user_id": user_id, "estado": "checkpoint"}
).sort("estado_updated_at", -1).to_list(length=100)
```

### Pattern 5: New WS message type in frontend

**What:** Add a case in the `handleMessage` switch in useWebSocket.ts, add corresponding state to officeStore.ts, then consume in AgentPanel.tsx.

**When to use:** lead_checkpoint and lead_handover message types.

**Example:**
```typescript
// Source: useWebSocket.ts lines 125-193 (handleMessage switch pattern)
case 'lead_checkpoint': {
  const msg = data as LandaCheckpointMessage;
  addCheckpointLead(msg);  // new action in officeStore
  break;
}
```

### Pattern 6: Modal overlay over pixel art

**What:** The CONTEXT.md specifies the checkpoint panel is NOT a separate screen — it's an overlay over the pixel art. Use absolute positioning with a semi-transparent backdrop. The AgentPanel.tsx already uses conditional rendering patterns.

**When to use:** Checkpoint card and handover card.

**Example:**
```tsx
// overlay pattern — absolute over the canvas
{checkpointLead && (
  <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 100 }}>
    <CheckpointCard lead={checkpointLead} onDecision={handleDecision} />
  </div>
)}
```

### Recommended File Structure for New Code

```
backend/
├── landa/
│   ├── api/
│   │   └── checkpoint.py      # POST /decision, GET /checkpoint logic
│   │   └── handover.py        # GET + POST handover logic
│   │   └── reporte.py         # POST reporte-llamada + IA interpretation
│   └── (existing: state_machine, scheduler, company_voice, ...)

frontend/src/
├── components/
│   ├── CheckpointModal.tsx     # new — checkpoint lead card overlay
│   ├── HandoverModal.tsx       # new — handover card overlay
│   └── AgentPanel.tsx          # extend — onClick handler + modal trigger
├── store/
│   └── officeStore.ts          # extend — checkpointLeads state slice
└── hooks/
    └── useWebSocket.ts         # extend — lead_checkpoint / lead_handover cases
```

### Anti-Patterns to Avoid

- **Blocking the HTTP response on run_outreach():** run_outreach() will send an HTTP/SMTP call — it must be fire-and-forget. Never await it inline in POST /decision.
- **Building a separate "Leads" page:** CONTEXT.md is explicit — no separate leads management screen. Everything is the pixel art overlay.
- **Calling IA synchronously in reporte-llamada:** The OpenAI call for "bien"/"mas_o_menos" interpretation must be fire-and-forget. Return 200 immediately.
- **Duplicating the HITL pattern verbatim:** The old `update_lead_hitl()` in database.py sets `hitl_status` (approved/rejected). Phase 14 replaces this surface with `update_lead_estado()` + channel + motivo. Do NOT reuse the old endpoint shape for new Landa leads.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Lead state transition enforcement | Custom if/else state checks | `update_lead_estado()` in landa/state_machine.py | Already validates VALID_TRANSITIONS, raises ValueError, logs timestamps |
| Scheduling retries | Manual asyncio.sleep loops | `schedule_retry(lead_id, canal, days)` in landa/scheduler.py | APScheduler with MongoDB durable state, survives restarts |
| Cancelling lead jobs | Iterating scheduled_actions manually | `cancel_lead_actions(lead_id)` in landa/scheduler.py | Already handles MongoDB update + APScheduler removal |
| WebSocket delivery to user | Direct WS reference lookup | `manager.send_to_user(user_id, msg)` in main.py | Already handles disconnected clients gracefully |
| Auth guard on endpoints | Custom token parsing | `Depends(get_current_user)` from auth.py | Established pattern, returns user dict with user_id |
| Frontend state management | useState for checkpoint leads | officeStore.ts (Zustand) | All app state is already in Zustand — consistency |

---

## Common Pitfalls

### Pitfall 1: "pausar" decision has no matching state transition

**What goes wrong:** VALID_TRANSITIONS["checkpoint"] = {"outreach", "pausado", "nurturing"}. "pausar" maps to "pausado". This is valid. BUT "rechazar" maps to "nurturing" (not "archivado"). The naming mismatch between the API decision value ("rechazar") and the target state ("nurturing") will confuse implementers.

**Why it happens:** Business logic: "rechazado_humano" leads don't get archived — they enter nurturing for a future opportunity.

**How to avoid:** Map explicitly in the endpoint:
```python
DECISION_MAP = {
    "aprobar": "outreach",
    "pausar": "pausado",
    "rechazar": "nurturing",
}
new_estado = DECISION_MAP[request.decision]
```

**Warning signs:** If tests try to assert `estado == "rechazado"` — that state doesn't exist.

### Pitfall 2: 48h no-report job must be scheduled at handover.tomar time

**What goes wrong:** The CONTEXT.md specifies "si reporte no llega en 48h → scheduler cancela acciones + notifica humano". This job must be scheduled when `POST /handover/tomar` is called, not when handover state is set automatically.

**Why it happens:** Phase 13 sets leads to "handover" state automatically. But the 48h clock starts when the human explicitly "takes control".

**How to avoid:** Inside `POST /handover/tomar`, after `update_lead_estado(→ "handover")`, call `schedule_retry(lead_id, "notificacion_48h", days=2)` (or a dedicated notification action type).

**Warning signs:** Missing 48h job in POST /handover/tomar implementation.

### Pitfall 3: Frontend handleMessage switch needs both new types registered

**What goes wrong:** Adding `lead_checkpoint` and `lead_handover` cases to the switch without also updating the `useCallback` dependency array in `handleMessage` causes React to use stale closures.

**Why it happens:** `handleMessage` is a `useCallback` with explicit dep arrays (line 192 in useWebSocket.ts). New store actions added to the switch MUST appear in the dep array.

**How to avoid:** After adding `addCheckpointLead` and `addHandoverLead` store actions, add them to the `useCallback` dep array at the bottom of `handleMessage`.

**Warning signs:** Modal doesn't update when WS message arrives, but console.log shows the message was received.

### Pitfall 4: "no_pude incorrecto" needs a flag on the lead, not a new state

**What goes wrong:** "no_pude incorrecto" (wrong number) doesn't have a corresponding state transition — it flags the lead for a different contact discovery flow. Trying to model this as a state transition will break VALID_TRANSITIONS.

**Why it happens:** It's an enrichment task (find alternative contact), not a lifecycle state.

**How to avoid:** Store as a flag: `await db.leads.update_one({"_id": oid}, {"$set": {"buscar_numero_alternativo": True}})`. The investigador/outreach agents in a future phase will pick this up.

**Warning signs:** Code that tries to call `update_lead_estado(→ "buscar_alternativo")` — that state doesn't exist.

### Pitfall 5: GET /checkpoint must filter by user_id AND estado

**What goes wrong:** Querying only `{"estado": "checkpoint"}` returns ALL users' checkpoint leads — a multi-tenant data leak.

**Why it happens:** The compound index `[("user_id", 1), ("estado", 1)]` is there exactly for this. Using it correctly is non-negotiable.

**How to avoid:** Always: `{"user_id": user_id, "estado": "checkpoint"}`.

---

## Code Examples

Verified patterns from existing codebase:

### MongoDB compound index query (checkpoint leads)
```python
# Source: database.py line 40 — index already exists
db = get_db()
leads = await db.leads.find(
    {"user_id": user_id, "estado": "checkpoint"}
).sort("estado_updated_at", -1).to_list(length=100)
for l in leads:
    l["_id"] = str(l["_id"])
```

### State transition for decision endpoint
```python
# Source: landa/state_machine.py update_lead_estado()
DECISION_MAP = {"aprobar": "outreach", "pausar": "pausado", "rechazar": "nurturing"}

new_estado = DECISION_MAP.get(request.decision)
if not new_estado:
    raise HTTPException(400, f"Unknown decision: {request.decision}")

try:
    updated = await update_lead_estado(lead_id, user_id, new_estado)
except ValueError as e:
    raise HTTPException(400, detail=str(e))
```

### Cancel actions + transition to handover
```python
# Sources: landa/scheduler.py cancel_lead_actions() + landa/state_machine.py
await cancel_lead_actions(lead_id)
updated = await update_lead_estado(lead_id, user_id, "handover")
# Schedule 48h no-report notification
await schedule_retry(lead_id, canal="notificacion_48h", days=2)
await manager.send_to_user(user_id, {"type": "lead_handover", "lead_id": lead_id, ...})
```

### Pydantic request model pattern (existing alias in main.py)
```python
# Source: main.py — _BaseModel is the project alias
from pydantic import BaseModel as _BaseModel

class LeadDecisionRequest(_BaseModel):
    decision: str          # "aprobar" | "pausar" | "rechazar"
    canal_elegido: str | None = None
    motivo: str | None = None

class CallReportRequest(_BaseModel):
    resultado: str         # "bien" | "mas_o_menos" | "mal" | "no_pude"
    detalle: str | None = None
    sub_tipo: str | None = None
```

### WebSocket new message type in frontend
```typescript
// Source: useWebSocket.ts lines 125-193 (handleMessage pattern)
// Step 1: add to officeStore.ts
interface OfficeStore {
  checkpointLeads: LandaCheckpointLead[];
  addCheckpointLead: (lead: LandaCheckpointLead) => void;
  clearCheckpointLead: (leadId: string) => void;
  handoverLead: LandaHandoverLead | null;
  setHandoverLead: (lead: LandaHandoverLead | null) => void;
}

// Step 2: add case in handleMessage
case 'lead_checkpoint': {
  const msg = data as { type: string; lead_id: string; empresa: string; puntaje: number };
  addCheckpointLead({ leadId: msg.lead_id, empresa: msg.empresa, puntaje: msg.puntaje });
  break;
}
```

### Staff Dashboard sources toggle endpoint
```python
# Pattern: follows same structure as existing staff endpoints
class ClientSourcesRequest(_BaseModel):
    fuentes_habilitadas: list[str]  # ["google_maps", "secop_adjudicados"]

@app.post("/api/staff/clients/{target_user_id}/sources")
async def update_client_sources(
    target_user_id: str,
    request: ClientSourcesRequest,
    current_user: dict = Depends(require_staff),  # staff only
):
    db = get_db()
    await db.company_voice.update_one(
        {"user_id": target_user_id},
        {"$set": {"fuentes_habilitadas": request.fuentes_habilitadas}},
        upsert=True,
    )
    return {"status": "ok", "fuentes_habilitadas": request.fuentes_habilitadas}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `PATCH /api/leads/{id}/approve` + `update_lead_hitl()` | `POST /api/leads/{id}/decision` + `update_lead_estado()` | Phase 14 | More expressive: carries canal_elegido, motivo, and maps to 8-state machine |
| No scheduler notification | 48h no-report job via `schedule_retry()` | Phase 14 | Human gets notified if they forget to log call result |
| No frontend checkpoint concept | Pixel art overlay modal triggered by WS lead_checkpoint | Phase 14 | Human workflow stays in pixel art office |

**Deprecated/outdated:**
- `update_lead_hitl()` in database.py: still used for the legacy pipeline HITL (`/approve`, `/reject` endpoints). Phase 14 does NOT replace these — they serve different flows (old pipeline vs. Landa module). Keep both.

---

## Open Questions

1. **Does run_outreach() exist when Phase 14 is implemented?**
   - What we know: Phase 13 Plan 13-04 builds `outreach_agent.py run_outreach()`. Phase 14 depends on Phase 13.
   - What's unclear: Whether Phase 13 will be fully implemented before Phase 14 planning starts (ROADMAP shows Phase 13 "Not started").
   - Recommendation: Phase 14 Wave 0 stubs should import `run_outreach` with `xfail` if not available. The background task wrapper should be isolated so the endpoint works even if run_outreach is a stub.

2. **How is `sugerencia_cierre` generated for GET /handover?**
   - What we know: CONTEXT.md says "sugerencia de cierre generada por IA". The endpoint returns it.
   - What's unclear: Is it generated once when lead enters "handover" and cached, or generated on-demand when GET is called?
   - Recommendation: Generate on-demand (no cache) for Phase 14 simplicity. Use `call_agent()` from `landa/core/context.py` pattern. Cache in Phase 15+ if needed.

3. **What is the `historial_conversacion` schema on a lead?**
   - What we know: Phase 13 agents log to `historial_conversacion`. The GET /handover endpoint returns the full thread.
   - What's unclear: Exact schema of each entry (established in Phase 13 implementation).
   - Recommendation: Treat as a passthrough — return `lead.get("historial_conversacion", [])` as-is without schema enforcement in Phase 14.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode = auto) |
| Config file | `backend/pytest.ini` |
| Quick run command | `cd backend && python -m pytest tests/test_landa_api.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LANDA-09 | GET /checkpoint returns leads with puntaje/criterios/señales/canales | integration | `pytest tests/test_landa_api.py::test_checkpoint_returns_leads_with_canales -x` | Wave 0 |
| LANDA-09 | POST /decision "aprobar" transitions to outreach | integration | `pytest tests/test_landa_api.py::test_decision_aprobar_transitions_to_outreach -x` | Wave 0 |
| LANDA-09 | POST /decision "rechazar" transitions to nurturing | integration | `pytest tests/test_landa_api.py::test_decision_rechazar_transitions_to_nurturing -x` | Wave 0 |
| LANDA-09 | POST /decision "pausar" transitions to pausado | integration | `pytest tests/test_landa_api.py::test_decision_pausar_transitions_to_pausado -x` | Wave 0 |
| LANDA-10 | GET /handover returns full package | integration | `pytest tests/test_landa_api.py::test_handover_get_returns_package -x` | Wave 0 |
| LANDA-10 | POST /handover/tomar cancels actions + sets estado=handover | integration | `pytest tests/test_landa_api.py::test_handover_tomar_cancels_actions -x` | Wave 0 |
| LANDA-11 | POST /reporte-llamada "mal" transitions to nurturing | integration | `pytest tests/test_landa_api.py::test_reporte_mal_transitions_nurturing -x` | Wave 0 |
| LANDA-11 | POST /reporte-llamada "no_pude" ocupado schedules retry 24h | integration | `pytest tests/test_landa_api.py::test_reporte_nopude_ocupado_schedules_retry -x` | Wave 0 |
| LANDA-11 | POST /reporte-llamada "no_pude" incorrecto sets flag on lead | integration | `pytest tests/test_landa_api.py::test_reporte_nopude_incorrecto_sets_flag -x` | Wave 0 |
| LANDA-12 | Frontend: manual verification — checkpoint modal renders on WS lead_checkpoint | manual | Visual check in browser | N/A |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_landa_api.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_landa_api.py` — 8 xfail stubs covering LANDA-09, LANDA-10, LANDA-11 (LANDA-12 is manual frontend verification)
- No new framework install needed — existing pytest + mongomock_motor + httpx ASGI transport covers all cases

---

## Sources

### Primary (HIGH confidence)
- Codebase: `backend/landa/state_machine.py` — VALID_TRANSITIONS dict, update_lead_estado() signature
- Codebase: `backend/landa/scheduler.py` — schedule_retry(), cancel_lead_actions(), APScheduler patterns
- Codebase: `backend/main.py` lines 58-92 — ConnectionManager, send_to_user(), existing endpoint patterns
- Codebase: `frontend/src/hooks/useWebSocket.ts` — handleMessage switch, Zustand store pattern
- Codebase: `backend/database.py` lines 38-44 — existing MongoDB indexes including `[user_id, estado]`
- `.planning/phases/14-landa-api-checkpoint-ui/14-CONTEXT.md` — locked decisions, exact API contracts

### Secondary (MEDIUM confidence)
- Codebase: `frontend/src/store/officeStore.ts` — existing Lead/Agent interfaces, state shape for extension
- Codebase: `frontend/src/components/AgentPanel.tsx` — STATE_LABELS, existing conditional rendering patterns
- Codebase: `frontend/src/components/StaffDashboard.tsx` — ClientData interface, existing staff API patterns
- Codebase: `backend/tests/test_landa_pipeline.py` — xfail stub pattern, mongomock_motor usage

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and in use
- Architecture: HIGH — every pattern is already established in the codebase; this phase extends, does not invent
- Pitfalls: HIGH — derived from direct inspection of VALID_TRANSITIONS, scheduler, and existing test patterns
- Frontend patterns: HIGH — useWebSocket.ts and officeStore.ts are fully readable

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (stable stack, no fast-moving dependencies)
