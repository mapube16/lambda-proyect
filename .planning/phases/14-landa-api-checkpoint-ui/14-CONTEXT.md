# Phase 14: Lead Lifecycle API & Checkpoint UI - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning
**Source:** Landa vision + análisis de codebase existente

<domain>
## Phase Boundary

Esta fase conecta los agentes de Phase 13 con el humano a través de dos superficies:

1. **Pixel art office** — los personajes cambian de estado y notifican al usuario cuando hay una acción requerida. El usuario hace click en el personaje para ver qué está pasando y actuar.
2. **Staff/Admin dashboard** — configuración por cliente: toggles de fuentes premium (SECOP), activación de canales, ajustes de voz de marca.
3. **API del ciclo de vida** — endpoints que conectan las transiciones de estado de leads con la UI.

**Filosofía Landa para esta fase:**
- El usuario NO va a una pantalla de "gestión de leads" — el personaje en el pixel art le avisa
- Click en personaje → tarjeta del lead con contexto y opciones de acción
- El humano solo interviene cuando hay una oportunidad real lista
- SECOP es una fuente premium: el admin puede activarla por cliente desde el staff dashboard

</domain>

<decisions>
## Implementation Decisions

### Pixel art: estados de agentes para el módulo de captación

Los personajes ya tienen estados (thinking, tool_use, waiting, idle). Esta fase agrega estados semánticos específicos del ciclo de vida de leads, comunicados via WebSocket:

```
Investigador:
  "thinking"  → "Buscando empresas de [industria] en [ciudad]..."
  "tool_use"  → "Analizando [empresa]... [X de Y]"
  "waiting"   → "Tengo [N] candidatos listos para revisión" ← CHECKPOINT
  "idle"      → en espera de nueva campaña

Outreach (personaje nuevo o reutilizado):
  "thinking"  → "Preparando mensaje para [nombre decisor]..."
  "tool_use"  → "Enviando por [canal]..."
  "waiting"   → "Esperando respuesta de [empresa]" ← SEGUIMIENTO ACTIVO
  "idle"      → sin leads en outreach activo

Nurturing (puede ser el mismo personaje en otro estado):
  "thinking"  → "Preparando contenido mensual para [N] leads"
  "tool_use"  → "Enviando a [empresa]..."
  "waiting"   → "Monitoreando señales de reentrada"
  "idle"      → sin leads en nurturing
```

**Click en personaje en estado "waiting" (checkpoint):**
→ Abre un panel/modal con la tarjeta del lead:
  - Empresa, decisor, puntaje, criterios cumplidos
  - Canales recomendados con probabilidad
  - Botones: **Aprobar** (+ selector de canal) | **Pausar** | **Rechazar**
→ No es una pantalla separada — es un overlay sobre el pixel art

**Click en personaje en estado "waiting" (handover — lead respondió):**
→ Panel diferente: "¡Oportunidad lista!"
  - Hilo de conversación completo
  - Sugerencia de cierre generada por IA
  - Botón: **Tomar el control** (congela el agente en ese lead)

### API del ciclo de vida de leads

**Endpoint 1 — Checkpoint:**
```
GET  /api/leads/checkpoint
     → leads en estado "checkpoint" del usuario autenticado
     → respuesta: [{id, empresa, decisor, puntaje, criterios, señales, canales[]}]

POST /api/leads/{id}/decision
     body: {decision: "aprobar"|"pausar"|"rechazar", canal_elegido?, motivo?}
     → ejecuta transición de estado
     → si "aprobar" → dispara run_outreach() en background
     → si "rechazar" → update_lead_estado(→ "nurturing"), motivo="rechazado_humano"
     → notifica via WebSocket al usuario
```

**Endpoint 2 — Handover:**
```
GET  /api/leads/{id}/handover
     → paquete: {lead, hilo_conversacion, calificacion_original, sugerencia_cierre}

POST /api/leads/{id}/handover/tomar
     → update_lead_estado(→ "handover")
     → cancel_lead_actions(lead_id) — pausa scheduler de reintentos
     → notifica via WebSocket: personaje vuelve a "idle"
```

**Endpoint 3 — Reporte de llamada:**
```
POST /api/leads/{id}/reporte-llamada
     body: {resultado: "bien"|"mas_o_menos"|"mal"|"no_pude", detalle?, sub_tipo?}
     → lógica interna:
        "bien" / "mas_o_menos" → IA interpreta detalle → decide acción
        "mal"                  → nurturing, motivo=detalle
        "no_pude" ocupado/apagado → schedule_retry(days=1)
        "no_pude" incorrecto       → buscar número alternativo (flag en lead)
        "no_pude" corto            → cuenta como intento 1, schedule_retry(days=7)
     → si reporte no llega en 48h → scheduler cancela acciones + notifica humano
```

**Notificaciones WebSocket** — todos los endpoints emiten eventos al usuario:
```json
{"type": "lead_checkpoint", "lead_id": "...", "empresa": "...", "puntaje": 84}
{"type": "lead_handover",   "lead_id": "...", "empresa": "...", "canal": "whatsapp"}
{"type": "lead_archived",   "lead_id": "...", "empresa": "..."}
```

### SECOP como feature premium — Staff Dashboard

**Dónde vive el toggle:** en el staff dashboard existente, en la vista de configuración de cada cliente.

**Campo en `company_voice`:**
```python
"fuentes_habilitadas": ["google_maps"]  # default — solo Google Maps
# Premium add-ons:
# "secop_adjudicados"  → empresas que ya ganaron contratos (secop.py)
# "secop_licitaciones" → licitaciones abiertas (secop_radar.py) — nicho aseguradoras/fianzas
```

**UI en staff dashboard** (nuevo panel por cliente):
```
[ Fuentes de descubrimiento ]
☑ Google Maps + Web scraping    (incluido en todos los planes)
☐ SECOP — Empresas adjudicadas  (add-on premium)
☐ SECOP — Licitaciones abiertas (add-on premium — aseguradoras)
```

**Por qué es vendible por separado:**
- SECOP adjudicados: valioso para cualquier empresa que venda a proveedores del Estado
- SECOP licitaciones: nicho específico de aseguradoras, fintechs de fianzas, consultoras de contratación pública
- El staff de Landa activa esto manualmente por cliente hasta que haya self-service de planes

**Implementación:**
- `POST /api/staff/clients/{user_id}/sources` — actualiza `company_voice.fuentes_habilitadas`
- El flag se lee en `run_investigador()` de Phase 13 antes de correr las fuentes
- Compatible con toggle existente `campaign.get("use_secop", False)` en `hive_tools.py`

### Integración pixel art existente

El sistema de WebSocket y estados de agentes ya funciona. Esta fase agrega:
- Nuevos tipos de mensajes WebSocket (`lead_checkpoint`, `lead_handover`)
- El frontend escucha estos eventos y cambia el estado del personaje
- Click en personaje con estado `waiting` abre el panel de acción correcto según el contexto

El AgentPanel existente ya muestra el estado del agente — se extiende con el texto semántico
("Tengo 3 candidatos listos") y con el panel de acción al hacer click.

</decisions>

<specifics>
## Referencias del codebase existente

**`main.py`** — WebSocket manager ya tiene `send_to_user(user_id, message)`. Nuevos tipos de
mensaje se envían siguiendo el mismo patrón que `agent_update`.

**`frontend/src/components/AgentPanel.tsx`** — ya muestra estado del agente y tool_status.
Extender con: texto semántico por estado + onClick que abre modal de checkpoint/handover.

**`frontend/src/components/StaffDashboard.tsx`** — ya existe. Agregar panel de
"Fuentes de descubrimiento" con toggles por cliente.

**`database.py` → `update_lead_hitl()`** — el hook de HITL existente. Phase 14 lo reemplaza
con `POST /api/leads/{id}/decision` que tiene más lógica (motivo, canal, transición de estado).

**`company_voice.py` (Phase 12)** — `fuentes_habilitadas` se define aquí.
Phase 14 expone un endpoint staff para modificarlo.

</specifics>

<deferred>
## Diferido a fases futuras

- Catálogo de agentes (app store de verticales Landa)
- Self-service de planes y precios
- LinkedIn, Instagram, TikTok como canales de outreach
- Notificaciones por Slack webhook
- WhatsApp como canal de onboarding del usuario final

</deferred>

---

*Phase: 14-landa-api-checkpoint-ui*
*Context gathered: 2026-03-22*
