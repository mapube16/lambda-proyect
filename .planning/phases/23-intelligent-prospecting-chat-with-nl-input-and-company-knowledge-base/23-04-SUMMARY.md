---
phase: 23-intelligent-prospecting-chat-with-nl-input-and-company-knowledge-base
plan: "04"
subsystem: ui
tags: [react, typescript, agentpanel, nl-input, knowledge-base, campaign-config]

# Dependency graph
requires:
  - phase: 23-02
    provides: backend NL extraction endpoint POST /api/chat/prospect and GET/POST /api/knowledge

provides:
  - NLProspectInput sub-component with textarea, gradient send button, hint text, loading/error states
  - ExtractedParamsCard sub-component showing extracted campaign params in 2-col grid
  - KnowledgeBasePanel sub-component with LearningBadge, auto-save on blur
  - CampaignChat retained as clarification fallback path

affects:
  - 23-05 (smoke test / verifier will validate these UI sub-components)
  - AgentPanel.tsx consumers

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "NL single-turn input pattern: textarea + disabled-on-load send button; Enter submits, Shift+Enter newlines"
    - "Clarification fallback: onClarification callback sets clarificationReply state, renders CampaignChat"
    - "Auto-save on blur: handleBlur checks value !== originalValue before firing POST; field label temporarily changes to 'Guardado ✓'"
    - "Learning badge: rendered in panel header from approved_lead_signals.length + rejected_lead_signals.length fetched on mount"

key-files:
  created: []
  modified:
    - frontend/src/components/AgentPanel.tsx

key-decisions:
  - "NLProspectInput placed above CampaignChat function; CampaignChat retained unchanged as clarification fallback"
  - "extractedCampaign and clarificationReply state hooks added to AgentPanel; both cleared by reset button"
  - "ExtractedParamsCard inserted above paramGrid in post-extraction view — reads from extractedCampaign state"
  - "KnowledgeBasePanel inserted between campaign form and sliderSection, not inside the slider block"
  - "KnowledgeBasePanel uses collapsed default state (local React useState, not persisted)"
  - "No save button in KB panel — auto-save fires on textarea onBlur only"

patterns-established:
  - "Pattern: NL extraction flow: NLProspectInput → onExtracted sets extractedCampaign + setCampaignReady(true); onClarification sets clarificationReply → falls back to CampaignChat"
  - "Pattern: KB auto-save guard — handleBlur returns early if value === originalValue to avoid unnecessary POSTs"

requirements-completed: [UI-01, UI-02, UI-03, UI-04]

# Metrics
duration: 3min
completed: 2026-05-29
---

# Phase 23 Plan 04: NL Prospect Input + Knowledge Base Panel UI Summary

**NLProspectInput textarea replaces CampaignChat start screen, ExtractedParamsCard shows AI-extracted params, and KnowledgeBasePanel with auto-save and learning badge complete the Phase 23 frontend UX in AgentPanel.tsx**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-30T01:37:17Z
- **Completed:** 2026-05-30T01:40:33Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- NLProspectInput sub-component: full-width textarea, gradient ➤ send button, Enter-to-submit, Shift+Enter newline, disabled/loading states, inline error message
- ExtractedParamsCard sub-component: 2-col grid showing 8 campaign fields, filled-field count badge in #78dce8, missing values shown as "—"
- KnowledgeBasePanel sub-component: collapsible panel with Learning badge (N aprobados · M rechazados / Sin señales aún), 4-row textarea, auto-save on blur, "Guardado ✓"/"Error al guardar" transient label feedback
- Production build succeeds (107 modules, tsc + vite)

## Task Commits

1. **Task 1: Add NLProspectInput + ExtractedParamsCard, replace campaign start screen** - `228a9af` (feat)
2. **Task 2: Add KnowledgeBasePanel with LearningBadge and auto-save** - `50c38c8` (feat)

## Files Created/Modified

- `frontend/src/components/AgentPanel.tsx` — Added NLProspectInput (line 303), ExtractedParamsCard (line 410), KnowledgeBasePanel (line 450) sub-components; updated AgentPanel state + render logic

## Decisions Made

- NLProspectInput directly renders the "Configurar Campaña" title inline (not from s.campaignHeader) — avoids header duplication since the existing s.campaignHeader section only renders in the campaignReady branch
- extractedCampaign is spread into the campaign state alongside DEFAULT_CAMPAIGN defaults so the existing paramGrid (which reads from `campaign`) shows extracted values immediately
- KnowledgeBasePanel placed before sliderSection per UI-SPEC §3 "Position" (below confirmation card, above launch button)
- No changes to CampaignChat, LeadCard, LeadsChat, tab bar, slider, launch button, or bee preview — all unchanged per UI-SPEC §6

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `npx tsc` on this machine routes to a shim instead of project TypeScript — used `./node_modules/.bin/tsc --noEmit` directly after `npm install` (node_modules was absent). Build succeeded cleanly.

## User Setup Required

None - no external service configuration required. All UI changes are frontend-only.

## Next Phase Readiness

- All 4 UI sub-components per UI-SPEC are implemented: NLProspectInput, ExtractedParamsCard, KnowledgeBasePanel, LearningBadge
- Plan 23-05 (smoke test) can validate: textarea visible, API call fires, confirmation card renders, KB panel expands/auto-saves
- Backend endpoints (POST /api/chat/prospect, GET+POST /api/knowledge) from Plan 23-02 are the runtime dependency

---
*Phase: 23-intelligent-prospecting-chat-with-nl-input-and-company-knowledge-base*
*Completed: 2026-05-29*
