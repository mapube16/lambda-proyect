# Auditoría de Migración — Landa UI

> Generado 2026-06-05. Estado real del código tras inspección de backend (12 routers, ~90 endpoints) y frontend (App.tsx nuevo + 10.411 líneas de componentes viejos huérfanos).

## TL;DR

El **backend está mucho más completo que el UI**. El nuevo Landa (`App.tsx`) solo cubre prospección: consume 10 de ~90 endpoints. Cobranza tiene backend funcional Y un componente viejo ya cableado (`CobranzaTab`), pero no está en el nuevo UI. Soft Seguros no existe en absoluto.

Orden recomendado: **(1) Limpiar mockups → (2) Migrar Cobranza → (3) Construir Soft Seguros**. Razón: los mockups son engaños activos con backend ya listo (horas, no días); cobranza es re-alojar código existente; Soft Seguros es greenfield y necesita requisitos tuyos antes de empezar.

---

## 1. Estado del UI nuevo (`frontend/src/App.tsx`)

6 vistas. Solo 3 conectadas a datos reales:

| Vista | Estado | Backend disponible |
|-------|--------|--------------------|
| `ViewInicio` | ✅ Real (`getKPIs`) | `/api/campaigns/{id}/kpis` |
| `ViewCampanas` | ✅ Real (`getCampaigns`, `createCampaign`, `launchCampaign`) | `/api/campaigns*` |
| `ViewAprobados` | ✅ Real (`getLeads`, `approveLead`) | `/api/campaigns/{id}/leads*` |
| `ViewResultados` | ❌ **MOCKUP** — embudo 142/96/24, KPIs "69%"/"$4.2" hardcodeados | ✅ `/api/campaigns/{id}/metrics` existe |
| `ViewChat` | ❌ **MOCKUP** — 3 mensajes fijos, Send no llama backend | ✅ `/api/chat/prospect` existe |
| `ViewAprendizaje` | ❌ **MOCKUP** — estático | ✅ `/api/learning/stats` + `/api/learning/patterns` existen |
| `Sidebar` (widgets) | ❌ **MOCKUP** — "DPG Seguros", "Plan Pro 62%", "8.420/13.500", badge "8" | ✅ `/api/tenant/quota` o `/api/quota/me` existen |

**api.ts** expone 20 funciones; App.tsx usa 10. Faltan helpers para metrics/chat/learning/quota.

## 2. Componentes viejos huérfanos (NO migrados)

10.411 líneas en `components/` que el `App.tsx` nuevo **no importa**:

| Componente | Líneas | ¿Migrar? | Backend |
|-----------|--------|----------|---------|
| `CobranzaTab.tsx` | 1.811 | ✅ **Sí — prioridad** | `/api/cobranza/*` (15 endpoints) ya cableados en el componente |
| `StaffDashboard.tsx` | 1.988 | ⚠️ Evaluar | `/api/staff/*` (25 endpoints) |
| `ClientDashboard.tsx` | 1.420 | ⚠️ Evaluar | `/api/prospect`, `/api/leads/*` |
| `AgentPanel.tsx` | 2.108 | ❓ Quizá obsoleto | legacy |
| `LoginView.tsx` | 970 | ⚠️ Auth real | `/auth/*` |
| `OfficeCanvas.tsx` | 510 | ❓ Quizá obsoleto | — |
| `RoadmapTab.tsx` | 352 | ❓ | `/api/roadmap-state` |
| 4 modales (Checkpoint/Expediente/Handover/LeadDossier) | 1.252 | ⚠️ Según vista padre | `/api/leads/*` |

## 3. Cobranza — backend completo, sin UI nuevo

**Backend (montado y corriendo, scheduler activo):**
- `cobranza/router.py` → `/api/cobranza/*`: status, debtors (CRUD + CSV), pagar/pausar/reactivar, onboarding start/approve, **llamar-ahora**
- `cobranza/voice_router.py` → `/api/cobranza/voice/*`: webhook, recording, **call/initiate-v2**
- `cobranza/`: `cobranza_queen`, `vapi_client`, `voice_orchestrator`, `claude_decision`, `campaign_scheduler`, TTS (Google/Deepgram), STT (AssemblyAI)
- Activación por cliente: `/api/staff/clients/{id}/cobranza/enable|disable`

**`CobranzaTab.tsx` (1.811 líneas) ya consume:** status, debtors, debtors/csv, onboarding/start, onboarding/approve, pagar/pausar/reactivar. **Es self-contained** (`export function CobranzaTab()` sin props, maneja su propio fetch/auth).

→ **Migrar = re-alojar, no reescribir.** Añadir item de nav + wrapper de vista + adaptar estilos/auth al nuevo App.

## 4. Soft Seguros — NO EXISTE

Cero referencias en código (`backend/**/*.py`) y cero en docs (`*.md`). Greenfield total.

**Bloqueado por requisitos.** Antes de codear necesito saber:
- ¿Qué es Soft Seguros? (software de gestión de seguros colombiano)
- Tipo de integración: ¿API REST documentada? ¿scraping de portal? ¿import/export de archivos (CSV/Excel)? ¿webhook?
- ¿Hay credenciales / sandbox / documentación de su API?
- Dirección del flujo: ¿leemos pólizas/cartera de Soft → Landa? ¿escribimos resultados de cobranza Landa → Soft? ¿bidireccional?
- ¿Qué entidad conecta: deudores de cobranza, o pólizas para prospección?

---

## Plan de tareas (orden recomendado)

### FASE A — Limpiar mockups (rápido, alto impacto, backend listo)
- **A1** — `api.ts`: añadir `getMetricsFunnel`, `sendChatMessage`, `getLearning`, `getQuota` (parcial existe).
- **A2** — `ViewResultados` → consumir `/api/campaigns/{id}/metrics`. Embudo y KPIs reales.
- **A3** — `ViewChat` → `POST /api/chat/prospect`. Que la Reina responda de verdad.
- **A4** — `ViewAprendizaje` → `/api/learning/stats` + `/patterns`.
- **A5** — `Sidebar` → `/api/tenant/quota` para créditos/plan reales; quitar "DPG Seguros" y badge fijo.

### FASE B — Migrar Cobranza al nuevo UI
- **B1** — Añadir item "Cobranza" al `Sidebar` (nav array).
- **B2** — Crear `ViewCobranza` que envuelva/adapte `CobranzaTab` con estilos del nuevo design system (`landa.css`).
- **B3** — Unificar auth: `CobranzaTab` usa su propio fetch → migrar a `api.ts` (token compartido).
- **B4** — Verificar flujo end-to-end: subir CSV deudores → onboarding/approve → llamar-ahora → webhook Vapi. Probar en local con worker.
- **B5** — Gating por feature flag: mostrar Cobranza solo si el tenant tiene `cobranza/enable`.

### FASE C — Integración Soft Seguros (BLOQUEADA — requiere requisitos)
- **C0** — Definir requisitos (ver sección 4). **No empezar sin esto.**
- **C1** — `backend/integrations/soft_seguros/` cliente + auth.
- **C2** — Endpoint(s) de sync + modelo de datos de mapeo.
- **C3** — UI: pantalla de conexión/credenciales + estado de sync.
- **C4** — Job de sincronización (ARQ) si es pull periódico.

### FASE D — Decidir destino de componentes viejos
- **D1** — Confirmar si Staff/Client Dashboard y AgentPanel se migran o se archivan (`App.old.tsx` ya existe como respaldo).
- **D2** — Borrar muertos para reducir 10k líneas de ruido.

---

## ESTADO ACTUAL (actualizado 2026-06-06)

✅ **Migrado y funcionando:** Fase A (mockups conectados), Fase B (Cobranza con auth Bearer), restyle claro de Cobranza (desde bundle de Claude Design).

### Lo que FALTA migrar — análisis completo (nuevo UI vs App.old.tsx + backend)

`App.old.tsx` era el orquestador: login con roles (staff/cliente) → StaffDashboard | ClientDashboard (secciones leads/cobranza/email/canales) + OfficeCanvas. El nuevo App auto-loguea como `dpg.seguros` y solo cubre prospección + cobranza. Huecos:

| # | Área | Estado actual | Backend listo | Prioridad |
|---|------|---------------|---------------|-----------|
| 1 | **Login / auth real + roles** | Auto-login hardcodeado dev-token (App.tsx:934). Sin pantalla login, logout, registro ni rol. `LoginView.tsx` (970L) huérfano | ✅ `/auth/login`, `/register`, `/register-request`, `/google-login` | **ALTA** |
| 2 | **Onboarding** (sube docs → campaña propuesta) | No existe. El diseño del bundle trae `landa-view-onboarding.jsx` (wizard completo) | ✅ `/api/staff/onboard/*`, `/api/cobranza/onboarding/*` | **ALTA** |
| 3 | **Conexión de Email** (Gmail/Outlook/SMTP) | No existe. ViewAprobados envía con **body de correo HARDCODEADO** (App.tsx:668) y sin buzón conectado → el envío real no funciona bien | ✅ `/auth/gmail/connect`, `/outlook/connect`, `/api/me/email-connect`, `/smtp-config`, `/email-template`, `/email-test` | **ALTA** (bloquea envíos reales) |
| 4 | **Canales / WhatsApp** | Envío fija canal `'email'`. Sin selección de canal ni config WhatsApp. Old tenía sección 'canales' | ✅ `/api/whatsapp-agents`, `/api/staff/wa-config` | MEDIA |
| 5 | **Staff / Admin dashboard** | No existe, sin ruteo por rol. `StaffDashboard.tsx` (1988L) huérfano | ✅ 25× `/api/staff/*` (clients, stats, knowledge, cobranza enable/disable, activate-bot) | MEDIA (si hay usuarios staff) |
| 6 | **Workflow rico de lead** (editar draft, dossier, handover humano, reporte llamada) | ViewAprobados solo aprueba + envía hardcodeado. Modales huérfanos: LeadDossier/Handover/Checkpoint/Expediente | ✅ `/api/leads/{id}/draft`, `/decision`, `/handover`, `/handover/tomar`, `/reporte-llamada` | MEDIA |
| 7 | **Knowledge base / perfil cliente** | Sin UI de gestión (el chat la usa implícito) | ✅ `/api/knowledge` GET/POST, `/api/client/profile`, `/api/staff/clients/{id}/knowledge/*` | BAJA-MEDIA |
| 8 | **Oficina Viva (OfficeCanvas)** | Huérfano (game/HUD). El design system dice ❌ "HUD de juego". El bundle trae una `ViewOficina` limpia (card), no el canvas | parcial | **DROP** (reemplazar por card limpia opcional) |
| 9 | **Signal sources: config/uso/audit** | El wizard setea flags, pero no hay vista de config/consumo | ✅ `/api/prospect/signal-sources/config`, `/usage`, `/signals/audit` | BAJA |

### Orden sugerido para cerrar la migración
1. **#3 Email connection** — sin esto, "enviar" no funciona de verdad (y hoy manda un body fijo). Mayor impacto funcional.
2. **#1 Login + roles** — para salir del usuario hardcodeado y soportar clientes reales.
3. **#2 Onboarding** — el diseño ya lo tiene listo (`landa-view-onboarding.jsx`), es portarlo + cablear.
4. **#6 Workflow de lead** (draft editable + handover) — calidad del core de prospección.
5. **#5 Staff dashboard** y **#4 Canales** — según si hay rol staff / envíos WhatsApp.
6. **#8/#9 y limpieza** — DROP OfficeCanvas, borrar huérfanos (~10k líneas).

### Gotchas detectados
- `ViewAprobados` envía un **correo hardcodeado** (App.tsx:668) — es semi-mock, depende de #3.
- Worker local usa **Redis remoto de Railway** → se cae con cualquier corte de red. Considerar Redis local para dev.
