---
phase: 14-landa-api-checkpoint-ui
plan: "06"
subsystem: frontend-ui
tags: [react, modal, overlay, checkpoint, handover, landa]
dependency_graph:
  requires: ["14-02", "14-03"]
  provides: ["CheckpointModal", "HandoverModal"]
  affects: ["frontend/src/components"]
tech_stack:
  added: []
  patterns: ["inline-style modals", "fixed overlay", "fetch on mount", "zustand authToken"]
key_files:
  created:
    - frontend/src/components/CheckpointModal.tsx
    - frontend/src/components/HandoverModal.tsx
  modified: []
decisions:
  - "CheckpointModal fetches GET /api/leads/checkpoint on mount to find full lead data by leadId, falls back to prop data if not found"
  - "HandoverModal uses fetchDetail() extracted as named function to enable Reintentar button"
  - "Pre-existing useWebSocket.ts TS error (ImportMeta.env) was out of scope and not modified"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-03-23"
  tasks_completed: 2
  files_created: 2
---

# Phase 14 Plan 06: CheckpointModal + HandoverModal Summary

Two React overlay components providing the human interaction surface for the Landa lead lifecycle, rendered as fixed overlays over the pixel art office.

## Tasks Completed

### Task 1: CheckpointModal.tsx

Component renders over the pixel art when a lead is at checkpoint state. Accepts `LandaCheckpointLead` prop (leadId, empresa, puntaje).

On mount fetches `GET /api/leads/checkpoint` with auth token, finds the matching lead by ID, and displays:
- Header: empresa name + color-coded puntaje badge (red/yellow/green thresholds: <70, 70-84, >=85)
- Decisor name and cargo
- Criterios cumplidos (bulleted with green checkmarks)
- Senales de intencion (bulleted with yellow diamonds)
- Canales with probability bars (color-coded) and percentage labels
- Canal selector `<select>` pre-populated with canales, pre-selected to highest probability

Three action buttons at the footer:
- **Rechazar** (red): POSTs `{decision: "rechazar", motivo: "rechazado_humano"}`
- **Pausar** (yellow): POSTs `{decision: "pausar"}`
- **Aprobar** (green): POSTs `{decision: "aprobar", canal_elegido: selectedCanal}`

All POSTs go to `POST /api/leads/{id}/decision`. On success calls `onClose()`. Error is shown inline below buttons without crashing the modal.

Commit: `80a81a2`

### Task 2: HandoverModal.tsx

Component renders when a lead has reached handover state (prospect responded). Accepts `LandaHandoverLead` prop (leadId, empresa, canal).

On mount fetches `GET /api/leads/{leadId}/handover`. Displays loading state, then on success:
- Header: "Oportunidad lista!" badge + canal badge (color-coded per canal type) + empresa name
- Calificacion section: large puntaje number + criterios list
- Sugerencia de cierre: highlighted box with `#a9dc76` border
- Hilo de conversacion: scrollable list (max 200px), each entry styled by role (humano=yellow/warm, agente=blue/cool), truncated to 100 chars
- Error state with "Reintentar" button

Footer buttons:
- **Cerrar** (gray): calls `onClose()` without any API call
- **Tomar el control** (green): POSTs `POST /api/leads/{id}/handover/tomar`, then calls `onClose()`

Commit: `7d4f711`

## Deviations from Plan

None — plan executed exactly as written.

The single pre-existing TypeScript error (`useWebSocket.ts: Property 'env' does not exist on type 'ImportMeta'`) was present before this plan and is out of scope. Neither new file introduces any TypeScript errors.

## Self-Check

### Files created:
- `frontend/src/components/CheckpointModal.tsx` — FOUND (356 lines)
- `frontend/src/components/HandoverModal.tsx` — FOUND (359 lines)

### Commits:
- `80a81a2` — feat(14-06): add CheckpointModal.tsx — FOUND
- `7d4f711` — feat(14-06): add HandoverModal.tsx — FOUND

### TypeScript:
- Zero errors in CheckpointModal.tsx or HandoverModal.tsx
- Pre-existing error in useWebSocket.ts is unrelated and out of scope

## Self-Check: PASSED
