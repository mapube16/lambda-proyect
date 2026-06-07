# Hive Pixel Office — Plataforma AaaS B2B

## What This Is

Plataforma de **Agentes como Servicio (AaaS)** para prospección B2B donde una interfaz de oficina pixel art es el UI principal. Los agentes Hive (sourcing, scoring, email composer, etc.) aparecen como personajes animados en la oficina — los usuarios pueden configurarlos, lanzar prospecciones y revisar expedientes desde la misma interfaz visual.

El backend actual (FastAPI + WebSocket + HiveOrchestrator) se reemplaza con el framework Hive real (`aden-hive/hive`) para ejecutar grafos de agentes reales.

## Core Value

Un cliente piloto puede entrar a la oficina, configurar su agente prospector con las 10 variables del negocio, ver los agentes trabajar en tiempo real en la oficina pixel art, y recibir expedientes + correos listos para enviar.

## Current Milestone: v1.0 Multi-Tenant SaaS Pipeline

**Goal:** Convertir el pipeline de prospección single-tenant en una plataforma SaaS multi-tenant para brokers de seguros con aislamiento real de tenants, cola de trabajos asíncrona, verticales de seguro parametrizables y observabilidad de costos.

**Target features:**
- Infraestructura Railway: API + Worker + Redis (3 servicios separados)
- ARQ job queue (asyncio-native, reemplaza ejecución in-process)
- tenant_id en todos los modelos MongoDB + queries aisladas por tenant
- VerticalConfig dataclass: parametriza pipeline por vertical (desempleo, arrendamiento, empresarial)
- SignalLead contract: output estándar de todos los signal_sources
- curl_cffi + Crawl4AI: scraping anti-bot con ~80% menos tokens GPT-4o
- Redis pub/sub WebSocket bridge: worker publica eventos → frontend
- CostEvent: tracking de costos por tenant (GPT-4o, Serper, Apollo)
- DIRECTORY_DOMAINS filter + extract_homepage() fix del scraper

**Tenant model:** tenant_id = user_id (1:1, sin orgs, escala a 20-50 brokers)

## Requirements

### Validated

- ✓ Backend FastAPI con WebSocket broadcast en tiempo real — existing
- ✓ Frontend React/Vite con canvas de oficina pixel art y personajes animados — existing
- ✓ Modelo de agente con estados (THINKING, TOOL_USE, WAITING) — existing
- ✓ Sistema prompt del agente prospector B2B definido (personalidad.md con 4 módulos) — existing

### Active

**Infraestructura multi-tenant:**
- [ ] Railway 3-service deployment: API service, Worker service, Redis service
- [ ] ARQ worker process con Redis como broker de cola
- [ ] tenant_id = user_id en todos los documentos MongoDB (campaigns, leads, company_voice, etc.)
- [ ] Redis pub/sub WebSocket bridge: worker publica a `ws:{tenant_id}:{run_id}`, API forwardea al frontend

**Pipeline parametrizable:**
- [ ] VerticalConfig dataclass con todos los parámetros por vertical de seguro
- [ ] SignalLead TypedDict como contrato de output de todos los signal_sources
- [ ] Registro de signal_sources por vertical en VerticalConfig

**Scraping mejorado:**
- [ ] curl_cffi AsyncSession(impersonate="chrome131") reemplaza httpx en el scraper
- [ ] Crawl4AI: HTML → Markdown comprimido antes de pasar a GPT-4o
- [ ] DIRECTORY_DOMAINS blocklist (ciencuadras.com, computrabajo.com, etc.)
- [ ] extract_homepage(url): extrae homepage desde URLs de blog/directorio

**Observabilidad:**
- [ ] CostEvent dataclass para tracking de costos por tenant
- [ ] Logging de costos GPT-4o, Serper, Apollo por run_id y tenant_id

### Out of Scope

- CRM push automático (HubSpot/Salesforce) — v2
- Webhooks Slack/Teams — v2
- Clay enrichment — v2
- Mobile app — web-first
- Email sending directo (SendGrid) — requiere warm-up, v2

## Context

**Codebase existente:**
- `backend/main.py`: FastAPI + WebSocket connection manager + endpoints REST de agentes
- `backend/orchestrator.py`: HiveOrchestrator actual (usa OpenAI SDK, NO el framework Hive real)
- `backend/models.py`: Agent, AgentState, AgentRole, AgentResponse (Pydantic)
- `frontend/src/App.tsx`: Layout principal con OfficeCanvas + AgentPanel
- `frontend/src/`: OfficeCanvas (pixel art), AgentPanel (controles), hooks WebSocket + game loop

**personalidad.md**: System prompt completo del agente prospector B2B. 4 módulos:
1. Sourcing + extracción de decisores + infraestructura + tech stack
2. Kill switches (7 filtros de descalificación)
3. Motor de scoring (0-100, umbral ≥70)
4. Generación de expediente Markdown + JSON + correo hiper-personalizado

**Hive framework** (`aden-hive/hive`): GraphExecutor, NodeContext, LiteLLMProvider, ToolRegistry, SharedMemory (STM/LTM/RLM), BuildSession. Reemplaza el orchestrator actual.

**Variables de campaña (10):** nombre_remitente, empresa_remitente, industria_objetivo, ciudad_objetivo, dolor_operativo, solucion_ofrecida, software_clave, jerarquia_decisores, contenido_scrapeado (dinámico), identidad_remitente.

## Constraints

- **Tech stack**: Python 3.11+ backend, React + TypeScript + Vite frontend — mantener
- **Framework**: Migrar a aden-hive/hive — no construir un orchestrator custom
- **MVP target**: Un cliente piloto puede configurar y correr una prospección real
- **Visualización**: La oficina pixel art se mantiene como UI principal — no reemplazar con dashboard genérico
- **Transparencia de agentes**: Los usuarios deben poder ver la configuración de cada agente sin ir al código

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reemplazar HiveOrchestrator con Hive real | El framework Hive ya tiene GraphExecutor, NodeContext, tools MCP — construirlo de cero es redundante | — Pending |
| Oficina pixel art como UI principal del AaaS | Diferenciador visual vs dashboards genéricos — la metáfora de oficina hace tangible el trabajo de los agentes | — Pending |
| personalidad.md como primer agente seed | Tiene los 4 módulos completos y probados — es el MVP del agente prospector | — Pending |
| HITL en la oficina (pausa visual) | El flujo de aprobación de leads ocurre en la oficina, no en email — más engaging para el cliente | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-26 — Milestone v1.0 Multi-Tenant SaaS Pipeline started*
