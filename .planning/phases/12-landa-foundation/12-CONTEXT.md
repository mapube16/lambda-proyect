# Phase 12: Lead Lifecycle Foundation - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning
**Source:** Extensión del pipeline existente inspirada en arquitectura Landa (Documento B)

<domain>
## Phase Boundary

El sistema actual encuentra y califica leads, pero se detiene cuando el humano aprueba o rechaza. Esta fase agrega la infraestructura para que el sistema pueda **continuar trabajando después del HITL** — enviar mensajes, hacer seguimiento, nutrir leads fríos.

No se crea un módulo separado. Todo se integra en los archivos existentes: `database.py`, `main.py`, y nuevas funciones en `backend/` siguiendo el patrón ya establecido.

**Qué entrega esta fase:**
- Lead state machine de 8 estados (extiende la colección `leads` existente)
- `sector_profiles`: colección nueva — contexto IA del sector para mejor scoring y mensajes
- `company_voice`: colección nueva — voz de marca consistente para outreach y nurturing
- `scheduled_actions` + APScheduler: reintentos automáticos y nurturing mensual
- `build_system_prompt()`: builder de variables para los prompts de outreach y nurturing

**Fuera de scope en esta fase:**
- Envío real de mensajes (Phase 13)
- Endpoints REST de checkpoint/handover/reporte-llamada (Phase 14)
- Frontend UI (Phase 14)

</domain>

<decisions>
## Implementation Decisions

### Filosofía de integración
- **NO crear `backend/landa/`** — todo va en archivos existentes o nuevos en `backend/` plano
- `database.py`: se extienden funciones al final del archivo (patrón ya establecido)
- `main.py`: solo se agrega el start/stop del scheduler al lifespan
- Nuevos archivos planos en `backend/`: `state_machine.py`, `sector_profiles.py`, `company_voice.py`, `scheduler.py`, `context_builder.py`
- El pipeline Hive existente (prospector, hive_graph, hive_tools) no se toca

### Lead State Machine
- 8 estados: `investigando | checkpoint | pausado | outreach | handover | nurturing | congelado | archivado`
- La colección `leads` ya existe — se agrega el campo `estado` (string) sin tocar los campos existentes
- `hitl_status` (pending/approved/rejected) se mantiene como está — es el campo del HITL actual
- La relación: `hitl_status="approved"` → dispara transición a `estado="outreach"`
- `VALID_TRANSITIONS` es un dict hardcoded en `backend/state_machine.py`
- `update_lead_estado(lead_id, user_id, new_estado)` en `database.py` — valida antes de escribir

**Transiciones válidas (14 en total):**
```
investigando → checkpoint
investigando → nurturing        (score 40-69)
checkpoint   → outreach         (humano aprueba)
checkpoint   → pausado          (humano pausa)
checkpoint   → nurturing        (humano rechaza)
pausado      → outreach         (humano aprueba después)
pausado      → nurturing        (30 días sin acción)
outreach     → handover         (lead responde positivo)
outreach     → nurturing        (respuesta negativa o sin respuesta tras 3 intentos)
outreach     → congelado        (llamada sin reporte del humano)
congelado    → outreach         (humano reporta resultado de llamada)
nurturing    → checkpoint       (señal de reentrada detectada)
nurturing    → archivado        (12 meses sin señal)
handover     → nurturing        (humano no toma acción en 7 días)
```

### sector_profiles — nueva colección
- Una entrada por (sector, pais_region, tamaño_empresa) — se reutiliza si tiene < 30 días
- GPT-4o temp=0.2 genera: decisor_primario, influenciador, bloqueador, canal_principal, canal_respaldo, tono, ciclo_venta, ganchos[3], objeciones[5], señales_compra[3], señales_reentrada[3], consideraciones_legales
- **Uso inmediato**: enriquece el prompt del scoring en el pipeline existente → mejores puntajes
- **Uso en Phase 13**: informa al Outreach (qué decir) y al Nurturing (qué señales detectar)
- Archivo: `backend/sector_profiles.py`

### company_voice — nueva colección
- Una entrada por `user_id` (un perfil de voz por cliente)
- Sincroniza desde `client_profiles` existente (no parte de cero)
- Agrega campos que hoy no existen: tono_empresa, largo_mensajes, usa_emojis, formato, palabras_clave[], palabras_prohibidas[], frase_apertura, frase_cierre, estilos_canal{email, whatsapp}
- **Uso en Phase 13**: Outreach y Nurturing inyectan estos valores como variables de prompt
- Archivo: `backend/company_voice.py`

### APScheduler + scheduled_actions
- `AsyncIOScheduler` — compatible con FastAPI async
- Jobstore: en memoria + escritura manual a `scheduled_actions` MongoDB para durabilidad
- Bootstrap al iniciar: lee `scheduled_actions` con estado `pendiente` y re-registra jobs
- Funciones: `schedule_retry(lead_id, canal, days=7)`, `schedule_nurturing(lead_id, mes)`, `cancel_lead_actions(lead_id)`
- Arranque en el `lifespan` de `main.py` junto a `init_db()`
- Archivo: `backend/scheduler.py`

### build_system_prompt
- `build_system_prompt(template: str, variables: dict) -> str`
- Reemplaza `[KEY]` → valor; si None o vacío → `[inferida — KEY]`
- Constantes de temperatura: `TEMP_INVESTIGADOR=0.2`, `TEMP_OUTREACH=0.7`, `TEMP_NURTURING=0.6`
- `call_agent(system_prompt, user_message, temperature) -> str` — wrapper AsyncOpenAI
- Usa `OPENAI_API_KEY` ya presente en el proyecto
- Archivo: `backend/context_builder.py`

### Nuevos índices MongoDB (se agregan a `init_db()`)
```python
await db.leads.create_index('estado')
await db.leads.create_index([('user_id', 1), ('estado', 1)])
await db.sector_profiles.create_index([('sector', 1), ('pais_region', 1)])
await db.scheduled_actions.create_index([('estado', 1), ('fecha_programada', 1)])
await db.scheduled_actions.create_index('lead_id')
```

</decisions>

<specifics>
## Referencias del codebase existente

**`database.py`** — patrón Motor establecido: `get_db()`, `await db.collection.op()`
Todas las funciones nuevas siguen este patrón exacto. Se agregan al final del archivo.

**`main.py` lifespan** — ya maneja `init_db()` en startup. Solo agregar:
```python
from scheduler import start_scheduler, shutdown_scheduler
# en lifespan: start_scheduler() antes del yield, shutdown_scheduler() después
```

**`client_profiles`** — colección existente con `business_summary`, `personality_prompt`, `agents[]`
`company_voice` sincroniza desde aquí: lee `client_profiles`, mapea campos, escribe en `company_voice`.

**`hitl_status`** → **`estado`** relación:
```
hitl_status="approved" + lead.estado="checkpoint" → transition to "outreach" (Phase 13 lo dispara)
hitl_status="rejected" + lead.estado="checkpoint" → transition to "nurturing" (Phase 13 lo dispara)
```
En esta fase solo se crea la infraestructura — Phase 13 usa las transiciones reales.

</specifics>

<deferred>
## Diferido a phases siguientes

- Envío de Email y WhatsApp (Phase 13)
- Lógica interna de los 3 agentes (Phase 13)
- Endpoints REST del ciclo de vida (Phase 14)
- Frontend checkpoint UI (Phase 14)

</deferred>

---

*Phase: 12-lead-lifecycle-foundation*
*Context actualizado: 2026-03-22 — integración en codebase existente, sin módulo separado*
