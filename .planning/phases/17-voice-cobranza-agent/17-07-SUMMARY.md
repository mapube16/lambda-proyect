---
phase: 17-voice-cobranza-agent
plan: "07"
subsystem: cobranza-frontend
tags: [react, typescript, websocket, cobranza, dashboard, real-time, inline-styles]

# Dependency graph
requires:
  - phase: 17-voice-cobranza-agent
    plan: "04"
    provides: POST /api/cobranza/debtors/{id}/llamar-ahora endpoint
  - phase: 17-voice-cobranza-agent
    plan: "05"
    provides: debtor_update WebSocket event from webhooks.py
provides:
  - frontend/src/components/CobranzaTab.tsx — full cobranza tab UI
  - frontend/src/components/ClientDashboard.tsx — section switcher (leads/cobranza)
affects:
  - useWebSocket.ts — debtor_update now dispatched as CustomEvent

# Tech tracking
tech-stack:
  added: []
  patterns:
    - custom-event-bridge: useWebSocket dispatches cobr:debtor_update CustomEvent; CobranzaTab listens with window.addEventListener — decouples WS hook from tab without store coupling
    - display-none-section: CobranzaTab rendered hidden (display:none) when leads section active — avoids remounting and preserves tab state
    - cobr-keyframe-injection: style tag injected once with id='cobr-styles' — same pattern as cd-styles in ClientDashboard

key-files:
  created:
    - frontend/src/components/CobranzaTab.tsx
  modified:
    - frontend/src/components/ClientDashboard.tsx
    - frontend/src/hooks/useWebSocket.ts

key-decisions:
  - "CustomEvent bridge (cobr:debtor_update) preferred over store coupling — CobranzaTab is self-contained with no store mutations"
  - "Section switcher uses display:none for leads panel when cobranza active — avoids remount and preserves leads scroll position"
  - "DebtorRow extracted as separate component to avoid inline hover handler closure issues"
  - "All actions (llamar, pagar, pausar, eliminar, save-notas) call real API endpoints with optimistic local state updates"

# Metrics
duration: 9min
completed: 2026-03-27
---

# Phase 17 Plan 07: Voice Cobranza Agent — Frontend Cobranza Tab Summary

**Full cobranza dashboard tab: debtor table with estado filters, detail modal with historial + transcript, real-time WebSocket updates, and manual control actions — added as new section to ClientDashboard**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-03-27T19:40:20Z
- **Completed:** 2026-03-27T19:49:00Z
- **Tasks:** 2 (Task 1: CobranzaTab, Task 2: ClientDashboard integration)
- **Files modified:** 3

## Accomplishments

- Created `frontend/src/components/CobranzaTab.tsx` (969 lines):
  - Stats header: cartera total, en llamada ahora, promesas activas — recalculated from local state
  - Filter pills: 9 estado values + "TODOS" — active pill highlighted per estado color
  - Debtor table: Nombre | Monto | Vencimiento | Estado | Último intento | Acciones columns
  - `EstadoBadge` component: color-coded per state with pulsing animation for `llamando`
  - `DebtorRow`: hover highlight, quick-action buttons (📞 ✓ ⏸ ↗), stopPropagation on action clicks
  - `DebtorModal`: 2-column layout (historial + transcript), promise card, notas textarea with save, action grid, keyboard close (Escape)
  - Historial de llamadas: timeline with expandable transcripts and audio player
  - Transcript viewer: chat-style bubbles (agent left, debtor right) for last call
  - All 6 API actions: llamar-ahora, pagar, pausar, reactivar, save-notas (PATCH), eliminar (DELETE with confirm)
  - Loading skeletons, empty state, in-modal toast, global toast stack
  - Real-time: `window.addEventListener('cobr:debtor_update')` updates debtor estado + intentos in place

- Modified `frontend/src/hooks/useWebSocket.ts`:
  - Added `case 'debtor_update'` to `handleMessage` switch
  - Dispatches `new CustomEvent('cobr:debtor_update', { detail: { debtor_id, estado, intentos } })`

- Modified `frontend/src/components/ClientDashboard.tsx`:
  - Added `section` state (`'leads' | 'cobranza'`, default `'leads'`)
  - Imported `CobranzaTab` from `./CobranzaTab`
  - Added section switcher (2 buttons) at top of sidebar nav
  - Leads nav items (Pipeline/Aprobados/Descartados) conditional on `section === 'leads'`
  - `{section === 'cobranza' && <CobranzaTab />}` renders tab
  - Existing leads scroll area wrapped with `display: section === 'leads' ? undefined : 'none'` — no regressions

## Task Commits

1. **Task 1: CobranzaTab.tsx + useWebSocket.ts debtor_update** - `d6566f5` (feat)
2. **Task 2: ClientDashboard section switcher** - `5c13e32` (feat)

## Files Created/Modified

- `frontend/src/components/CobranzaTab.tsx` — 969 lines; full cobranza tab
- `frontend/src/components/ClientDashboard.tsx` — section switcher added; CobranzaTab imported
- `frontend/src/hooks/useWebSocket.ts` — debtor_update case dispatches CustomEvent

## Decisions Made

- CustomEvent bridge (`cobr:debtor_update`) chosen over adding state to officeStore — keeps CobranzaTab self-contained and avoids polluting the store with cobranza-specific data
- `display:none` for leads panel instead of conditional rendering — preserves scroll position and avoids refetching leads when switching back to Leads section
- `DebtorRow` extracted as top-level function to avoid React hooks-in-callbacks lint issues
- Confirmation dialog (`window.confirm`) for eliminar — simple and reliable without a custom modal

## Deviations from Plan

None — plan executed exactly as written. All must_haves implemented and TypeScript compiles clean.

## Issues Encountered

None.

## User Setup Required

None — CobranzaTab auto-appears in ClientDashboard sidebar under "Cobro" section for all client users.

## Next Phase Readiness

- 17-08 (router registration in main.py): CobranzaTab already calls the correct endpoints (`/api/cobranza/debtors`, `/api/cobranza/debtors/{id}/llamar-ahora`, etc.)
- Real-time updates flow end-to-end: Vapi webhook (17-05) → debtor_update WS event → useWebSocket → CustomEvent → CobranzaTab state update
- COBR-04 requirement fulfilled: users can monitor and manage collection campaign in real time

## Self-Check

- [x] `frontend/src/components/CobranzaTab.tsx` — created (969 lines, > 200 min)
- [x] `frontend/src/components/ClientDashboard.tsx` — modified (section switcher added)
- [x] `frontend/src/hooks/useWebSocket.ts` — modified (debtor_update case)
- [x] Commit `d6566f5` — feat(17-07) CobranzaTab
- [x] Commit `5c13e32` — feat(17-07) ClientDashboard section switcher
- [x] TypeScript: Exit code 0 (0 errors)

## Self-Check: PASSED

---
*Phase: 17-voice-cobranza-agent*
*Completed: 2026-03-27*
