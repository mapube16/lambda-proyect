# Requirements: Hive Pixel Office — AaaS B2B Prospecting Platform

**Defined:** 2026-03-17
**Core Value:** Un cliente piloto puede configurar su agente prospector, ver los agentes trabajar en la oficina pixel art en tiempo real, y recibir expedientes con correos listos para enviar.

## v1 Requirements

### Authentication

- [x] **AUTH-01**: Usuario puede registrarse con email y password
- [x] **AUTH-02**: Usuario puede hacer login con email y password y recibir JWT
- [x] **AUTH-03**: El JWT protege todos los endpoints REST y el WebSocket connection

### Hive Integration

- [ ] **HIVE-01**: El backend instala y carga `aden-hive/hive` v0.6.0 correctamente
- [ ] **HIVE-02**: `HiveAdapter` reemplaza `orchestrator.py` como única seam entre FastAPI y Hive
- [ ] **HIVE-03**: `ConnectionManager` enruta mensajes WebSocket por `user_id` (no broadcast global)
- [ ] **HIVE-04**: `SharedMemory` se instancia con `namespace=f"user_{user_id}"` para aislamiento multi-tenant
- [ ] **HIVE-05**: Eventos de nodos de `GraphExecutor` se mapean a `AgentState` existente (THINKING, TOOL_USE, WAITING, IDLE)

### Prospecting Pipeline

- [ ] **PIPE-01**: Usuario puede ingresar una URL de empresa y lanzar una corrida de prospección
- [ ] **PIPE-02**: El pipeline ejecuta los 9 nodos completos: `sourcing_node` → `scraping_node` → `scoring_node` → `veto_router` → `spiced_analyzer` → `jtbd_deducer` → `email_composer` → `expediente_generator` → `human_review`
- [ ] **PIPE-03**: El contenido scrapeado se sanitiza (HTML → texto plano, truncado a 8,000 chars, delimitadores estructurales) antes de inyectar al LLM
- [ ] **PIPE-04**: La salida JSON de cada nodo LLM se valida contra un schema estricto antes de pasar al siguiente nodo
- [ ] **PIPE-05**: `personalidad.md` se carga como system prompt del nodo central prospector con las 10 variables de campaña interpoladas

### HITL (Human-in-the-Loop)

- [ ] **HITL-01**: Cuando el pipeline llega al nodo `human_review`, el agente en la oficina se congela visualmente indicando espera
- [ ] **HITL-02**: El estado HITL pendiente se persiste en SQLite antes de suspender (sobrevive reinicios del servidor)
- [ ] **HITL-03**: Usuario puede aprobar o rechazar el lead desde el dashboard; la respuesta reanuda el pipeline

### Agent Configuration

- [ ] **CONF-01**: Usuario puede configurar las 10 variables de campaña a través de un formulario antes de lanzar una corrida: `nombre_remitente`, `empresa_remitente`, `industria_objetivo`, `ciudad_objetivo`, `dolor_operativo`, `solucion_ofrecida`, `software_clave`, `jerarquia_decisores`, `identidad_remitente`, más `input_empresa_url`
- [ ] **CONF-02**: El AgentPanel muestra de forma permanente el nombre, rol y variables activas del agente en la sesión actual (transparencia de configuración)
- [ ] **CONF-03**: La configuración de campaña del usuario se persiste en SQLite para reutilizar entre sesiones

### Lead Dashboard

- [ ] **LEAD-01**: Al completar una corrida exitosa (score ≥ 70), el expediente se muestra con: score, perfil (A/B), decisor clave (nombre, cargo, email), tech stack detectado, trigger, y correo borrador
- [ ] **LEAD-02**: Los correos borrador son copiables con un click desde el expediente
- [ ] **LEAD-03**: Si el pipeline activa un Kill Switch, se muestra el código de rechazo (`KILL_B2C`, `LOW_SCORE_QUALIFICATION`, etc.) y la evidencia textual que lo justificó

### Real-Time Visualization

- [ ] **VIZ-01**: Los personajes de la oficina animan estados correspondientes a los nodos en ejecución (buscando, procesando, escribiendo, esperando)
- [ ] **VIZ-02**: El estado del agente se actualiza en tiempo real via WebSocket durante toda la corrida sin bloquear la UI
- [ ] **VIZ-03**: Los errores de pipeline (scraping fallido, LLM timeout) se muestran como estado de error en el personaje — no pantalla en blanco

### Landa Lead Captation Module

#### Phase 12 — Foundation
- [x] **LANDA-01**: La colección `leads` soporta 8 estados (investigando/checkpoint/pausado/outreach/handover/nurturing/congelado/archivado) con transiciones validadas en código — transiciones inválidas son rechazadas con error explícito
- [x] **LANDA-02**: La función `generate_sector_profile(sector, pais_region, tamaño)` llama a GPT-4o (temp=0.2) y retorna un documento completo con decisor_primario, ganchos[3], objeciones[5], señales_compra[3], señales_reentrada[3], canal_principal, tono, ciclo_venta — guardado en colección `sector_profiles`
- [x] **LANDA-03**: APScheduler (AsyncIOScheduler) arranca con la app y persiste jobs en MongoDB (`scheduled_actions`); `schedule_retry(lead_id, canal, days)` y `schedule_nurturing(lead_id, mes)` crean jobs; `cancel_lead_actions(lead_id)` los elimina todos — jobs sobreviven reinicios
- [x] **LANDA-04**: `build_system_prompt(template, variables)` reemplaza todas las `[VARIABLES]` del template; vacías quedan como `[inferida — KEY]`; función disponible en `core/context.py`

#### Phase 13 — Agent Pipeline
- [x] **LANDA-05**: Agente Investigador recibe sector_profile + campaign_context y retorna lista de leads con puntaje 0-100, criterios cumplidos, señales de intención, y análisis de canal (probabilidad por canal) — usando GPT-4o temp=0.2
- [x] **LANDA-06**: Routing automático: leads <40 pts → descartado; 40-69 → nurturing directo; ≥70 → estado checkpoint + notifica al humano
- [ ] **LANDA-07**: Agente Outreach genera mensaje con variables de `company_voice` y envía por canal_elegido: Email vía SMTP (smtplib) o WhatsApp Business API (graph.facebook.com/v18.0) — retorna bool de éxito y registra en historial_conversacion del lead
- [ ] **LANDA-08**: Agente Nurturing genera contenido según motivo_nurturing usando GPT-4o temp=0.6; detecta señales de reentrada en respuestas del lead; reentrada detectada → transiciona lead a checkpoint

#### Phase 14 — API & Checkpoint UI
- [ ] **LANDA-09**: `GET /api/leads/checkpoint` retorna leads en estado checkpoint del usuario autenticado con puntaje, criterios, señales y canales; `POST /api/leads/{id}/decision` acepta decision(aprobar/pausar/rechazar) + canal_elegido + motivo y ejecuta la transición de estado
- [ ] **LANDA-10**: `GET /api/leads/{id}/handover` retorna paquete completo (lead, hilo_conversacion, calificacion_original, sugerencia_cierre); `POST /api/leads/{id}/handover/tomar` congela el agente en ese lead
- [ ] **LANDA-11**: `POST /api/leads/{id}/reporte-llamada` acepta resultado(bien/mas_o_menos/mal/no_pude) + sub_tipo; ejecuta lógica: bien/mas_o_menos → IA decide; mal → nurturing; no_pude ocupado/apagado → reintento 24h; incorrecto → buscar alternativo; corto → intento 1
- [ ] **LANDA-12**: Frontend muestra vista Checkpoint con cards de leads (empresa, decisor, puntaje, canales con probabilidades), botones Aprobar/Pausar/Rechazar, selector de canal — se actualiza en tiempo real via WebSocket cuando llegan nuevos leads a checkpoint

## v2 Requirements

### Authentication Enhancements
- **AUTH-04**: Sesión persistente con JWT refresh token
- **AUTH-05**: Recuperación de contraseña por email

### Dashboard Enhancements
- **LEAD-04**: Historial completo de corridas pasadas con outcome y score
- **LEAD-05**: Score breakdown con desglose por criterio (base B2B, tensión operativa, escala, decisor, geo)
- **LEAD-06**: Panel de analytics de rechazos (frecuencia de Kill Switches por config de campaña)

### Agent Configuration Enhancements
- **CONF-04**: Click en personaje pixel art → modal con system prompt completo + variables activas
- **CONF-05**: Biblioteca de plantillas de campaña reutilizables

### Integrations
- **INT-01**: CRM push a HubSpot via MCP server
- **INT-02**: Envío de correo via SendGrid (requiere warm-up y compliance Ley 1581 Colombia)
- **INT-03**: Webhooks a Slack/Teams al completar corrida

### Scale
- **SCAL-01**: Procesamiento batch (múltiples URLs en cola por corrida)
- **SCAL-02**: Clay enrichment para datos adicionales de empresa
- **SCAL-03**: Migración de SQLite a PostgreSQL para 3+ clientes concurrentes

## Out of Scope

| Feature | Reason |
|---------|--------|
| Agent Builder UI (BuildSession visual) | Clientes necesitan resultados de prospección, no construcción de agentes — v3+ |
| LinkedIn scraping | Riesgo de violación de ToS — fuera de alcance indefinidamente |
| Self-improving graph (auto-evolución) | Requiere harness de evaluación que no existe aún — v3+ |
| Next.js / SSR migration | El canvas pixel art con game loop ya funciona en React/Vite — SSR no agrega valor |
| Auth0 / Clerk / Supabase Auth | JWT in-house es suficiente para MVP piloto — sin dependencia de vendor externo |
| SQLAlchemy ORM / Alembic | Overhead innecesario para MVP — queries directas con aiosqlite |
| Playwright / Crawl4AI | `aden_tools web_scrape_tool` primero — instalar headless browser solo si falla |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 1 — Auth Infrastructure | Complete |
| AUTH-02 | Phase 1 — Auth Infrastructure | Complete |
| AUTH-03 | Phase 1 — Auth Infrastructure | Complete |
| HIVE-01 | Phase 2 — Hive Adapter and Tenant Isolation | Pending |
| HIVE-02 | Phase 2 — Hive Adapter and Tenant Isolation | Pending |
| HIVE-03 | Phase 2 — Hive Adapter and Tenant Isolation | Pending |
| HIVE-04 | Phase 2 — Hive Adapter and Tenant Isolation | Pending |
| HIVE-05 | Phase 2 — Hive Adapter and Tenant Isolation | Pending |
| PIPE-01 | Phase 3 — Prospecting Graph Definition | Pending |
| PIPE-02 | Phase 3 — Prospecting Graph Definition | Pending |
| PIPE-05 | Phase 3 — Prospecting Graph Definition | Pending |
| PIPE-03 | Phase 4 — Scraping Safety and Output Validation | Pending |
| PIPE-04 | Phase 4 — Scraping Safety and Output Validation | Pending |
| HITL-01 | Phase 5 — HITL Loop | Pending |
| HITL-02 | Phase 5 — HITL Loop | Pending |
| HITL-03 | Phase 5 — HITL Loop | Pending |
| CONF-01 | Phase 6 — Campaign Configuration | Pending |
| CONF-02 | Phase 6 — Campaign Configuration | Pending |
| CONF-03 | Phase 6 — Campaign Configuration | Pending |
| LEAD-01 | Phase 7 — Lead Dashboard | Pending |
| LEAD-02 | Phase 7 — Lead Dashboard | Pending |
| LEAD-03 | Phase 7 — Lead Dashboard | Pending |
| VIZ-01 | Phase 8 — Real-Time Visualization | Pending |
| VIZ-02 | Phase 8 — Real-Time Visualization | Pending |
| VIZ-03 | Phase 8 — Real-Time Visualization | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-03-17*
*Last updated: 2026-03-17 after roadmap creation — traceability updated to 8-phase structure*
