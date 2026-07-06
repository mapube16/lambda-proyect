# Handoff — DPG Cobranza (ARIA)

> Rama: `claude/dpg-checklist-review` · Repo: `mapube16/lambda-proyect` (agente de voz)
> Última actualización: 2026-07-03

## Contexto
DPG Seguros es cliente de Landa Tech. Existe un informe técnico
(`INFORME_TECNICO_BOT_COBRANZA...docx`) con los requisitos del bot de cobranza
ARIA (voz + WhatsApp). Ese informe se comparó contra dos repos reales.

## Repos en juego
- **`mapube16/lambda-proyect`** (ESTE repo) — monolito con el agente de voz
  (Twilio + Pipecat + Gemini). Rama de trabajo: **`claude/dpg-checklist-review`**
  (sincronizada con `master`, con 1 commit propio: `6432362`).
- **`mapube16/landa-agent-service`** — microservicio aparte, ya en progreso, dueño
  del canal de WhatsApp. Stack: FastAPI + LangGraph + Meta Cloud API + Chatwoot +
  Postgres/Redis, 13 capas de seguridad, single-tenant DPG por diseño.
  **NO tocar ese repo desde acá.**

## División de responsabilidad acordada
- **`lambda-proyect` (este repo) es responsable de:** secuencia de 3 intentos de
  llamada, speeches diferenciados, reagendamiento, jornada de arranque, horarios
  DPG, y el puente REST hacia `landa-agent-service`.
- **`landa-agent-service` cubre:** Q&A por WhatsApp, validación de comprobantes,
  escalación a Chatwoot.
- **Huérfanos (nadie los tiene todavía):** reportes diario/semanal, solicitud de
  link/cupón por WhatsApp.

## Estado de `landa-agent-service` (al 2026-07-03)
17/31 planes hechos, Fase 4 de 8 en progreso. Atascado en task `04-04` (subgrafo
de pago LangGraph) — 3 intentos fallidos por timeout de sesión, no por bug real.
**Fase 6 (integración con el voice agent) no ha empezado** — ahí vive el contrato
REST pendiente.

## Trabajo ya entregado (committeado y pusheado)
En `claude/dpg-checklist-review` (commit `6432362`):
- `GET /api/client/modules` (`backend/routers/misc.py`) y
  `POST /api/staff/clients/{id}/modules` (`backend/routers/staff.py`) — sistema de
  gating de secciones del dashboard por tenant.
- `FeatureLockedModal.tsx` — modal "no disponible en tu plan, contacta a Landa Tech".
- `ClientDashboard.tsx` — nav siempre visible, bloqueo con modal en vez de ocultar
  secciones; se eliminó el query duplicado de `cobranza-status`.

**Pendiente del lado del usuario:** llamar
`POST /api/staff/clients/{dpg_user_id}/modules` con
`{"modules_enabled":["cobranza"]}` una vez desplegado — Claude no tiene acceso a la
BD en vivo para hacerlo.

## Siguiente paso acordado (NO iniciado todavía)
1. Extender `tenant_config`/`estrategia` para que los timings (offsets de intento,
   franjas horarias, `frecuencia_dias`) sean configurables sin deploy.
2. Modelar las "colas pendientes" como datos explícitos (no solo alertas que se
   pierden): revisión pre-vuelo diaria, solicitudes de link/cupón, comprobantes por
   validar.
3. Recién ahí, implementar la secuencia real de 3 intentos + los 4 speeches
   diferenciados.
4. El puente de integración: reemplazar el stub muerto
   `cobranza/sub_agents/whatsapp_notifier.py` por `POST /case/handoff`, y exponer
   `POST /cobranza/case/{case_id}/escalate` +
   `POST /cobranza/debtor/{debtor_id}/update` que `landa-agent-service` espera
   consumir.

## Explorado fuera de alcance (no instalado)
- **GSD (`get-shit-done`):** el repo `gsd-build/get-shit-done` está archivado; el
  activo es `open-gsd/gsd-core`. Paquete npm (`get-shit-done-cc`) que instala
  comandos/agentes en `.claude/`. No instalado en este entorno.
- **Ponytail (`DietrichGebert/ponytail`):** revisado a fondo (hooks, MCP server,
  package.json) — legítimo y seguro. No instalable acá porque `/plugin` no está
  disponible en el entorno remoto; correrlo desde el CLI local:
  `/plugin marketplace add DietrichGebert/ponytail` →
  `/plugin install ponytail@ponytail`.

## Nota de entorno (al reanudar en 2026-07-03)
El repo está clonado localmente en `C:\Users\maxim\Desktop\hive-pixel-office`
(nombre de carpeta engañoso — es `lambda-proyect`). El repo de WhatsApp está en
`C:\Users\maxim\Desktop\landa-agent-service`. La rama `feature/retell-voice-poc`
tiene trabajo aparte sin commitear (email/form/railway) guardado en un `git stash`.
