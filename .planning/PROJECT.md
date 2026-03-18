# Hive Pixel Office — Plataforma AaaS B2B

## What This Is

Plataforma de **Agentes como Servicio (AaaS)** para prospección B2B donde una interfaz de oficina pixel art es el UI principal. Los agentes Hive (sourcing, scoring, email composer, etc.) aparecen como personajes animados en la oficina — los usuarios pueden configurarlos, lanzar prospecciones y revisar expedientes desde la misma interfaz visual.

El backend actual (FastAPI + WebSocket + HiveOrchestrator) se reemplaza con el framework Hive real (`aden-hive/hive`) para ejecutar grafos de agentes reales.

## Core Value

Un cliente piloto puede entrar a la oficina, configurar su agente prospector con las 10 variables del negocio, ver los agentes trabajar en tiempo real en la oficina pixel art, y recibir expedientes + correos listos para enviar.

## Requirements

### Validated

- ✓ Backend FastAPI con WebSocket broadcast en tiempo real — existing
- ✓ Frontend React/Vite con canvas de oficina pixel art y personajes animados — existing
- ✓ Modelo de agente con estados (THINKING, TOOL_USE, WAITING) — existing
- ✓ Sistema prompt del agente prospector B2B definido (personalidad.md con 4 módulos) — existing

### Active

**Integración Hive:**
- [ ] Reemplazar HiveOrchestrator con AgentRunner + GraphExecutor real de aden-hive/hive
- [ ] Implementar grafo prospector: sourcing → scoring → veto → SPICED → email → expediente → HITL
- [ ] Conectar herramientas MCP (web_search_tool, web_scrape_tool) al ToolRegistry de Hive
- [ ] Integrar personalidad.md como system prompt del nodo central prospector

**UI de configuración de agentes:**
- [ ] Panel en la oficina que muestra la configuración completa de cada agente (personalidad, módulos, variables)
- [ ] Al hacer click en un personaje de la oficina, ver su configuración (nombre, rol, system prompt, variables de campaña)
- [ ] Formulario para configurar las 10 variables de campaña antes de lanzar prospección

**Flujo de prospección:**
- [ ] Input de URL de empresa → agente scraper → pipeline completo → expediente
- [ ] Nodo HITL: pausa en la oficina para revisión humana antes de aprobar/rechazar lead
- [ ] Dashboard de leads: expedientes generados con score, decisor, email borrador

**Auth y multi-usuario:**
- [ ] Login básico (email/password) para separar sesiones de clientes
- [ ] Cada usuario tiene sus propios agentes y runs aislados

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

---
*Last updated: 2026-03-17 after initialization*
