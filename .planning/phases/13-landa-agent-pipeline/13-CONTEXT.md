# Phase 13: Lead Outreach & Nurturing Agents - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning
**Source:** Extensión del pipeline existente inspirada en arquitectura Landa (Documento B)

<domain>
## Phase Boundary

El pipeline existente termina cuando el humano aprueba un lead. Esta fase agrega lo que viene después:

1. **Agente Outreach** — cuando el humano aprueba un lead en el HITL, el sistema envía el primer mensaje automáticamente por el canal elegido (Email o WhatsApp)
2. **Agente Nurturing** — leads rechazados o sin respuesta reciben contenido mensual hasta que muestren señal de reactivación
3. **Mejora del scoring** — el Investigador existente usa `sector_profile` (Phase 12) para calificar mejor y analizar canales con probabilidad

**El Investigador NO se reescribe** — se mejora con sector_profile. Los agentes Outreach y Nurturing son genuinamente nuevos.

**Fuera de scope:**
- Endpoints REST del ciclo de vida (Phase 14)
- Frontend checkpoint UI (Phase 14)
- LinkedIn, Instagram, TikTok
- SECOP Radar (licitaciones) — toggle existe, se activa por config

</domain>

<decisions>
## Implementation Decisions

### Filosofía de integración
- **NO crear subdirectorios** — archivos planos en `backend/`: `outreach_agent.py`, `nurturing_agent.py`
- El Investigador existente (`prospector.py` + `hive_tools.py`) se mejora, no se reemplaza
- Cada agente nuevo es una función async principal: `run_outreach(...)`, `run_nurturing(...)`
- Los agentes se invocan desde endpoints en Phase 14 y desde el scheduler de Phase 12

### Mejora del Investigador existente

El scoring actual es básico. Con `sector_profile` se enriquece así:

**Antes (hoy):** LLM evalúa la empresa contra criterios genéricos del campaign
**Después:** LLM evalúa contra `sector_profile.decisor_primario`, `sector_profile.señales_compra`, `sector_profile.ganchos` — scoring más preciso y consistente

**Output del scoring mejorado** (nuevo campo en lead):
```json
{
  "puntaje": 84,
  "criterios": ["sector exacto", "tamaño correcto", "decisor verificado"],
  "señales_intencion": ["perfil LinkedIn activo", "publicó oferta laboral"],
  "recomendacion_agente": "contactar ahora",
  "canales": [
    {"canal": "email", "probabilidad": 82, "razon": "correo verificado en web"},
    {"canal": "whatsapp", "probabilidad": 54, "razon": "WhatsApp Business activo"}
  ]
}
```

**Routing automático post-scoring:**
```python
puntaje < 40   → system_state="REJECTED_BY_AI", estado permanece "investigando"
40 <= puntaje < 70 → update_lead_estado(→ "nurturing"), motivo="score_bajo"
puntaje >= 70  → update_lead_estado(→ "checkpoint")  # humano decide
```

**Toggle SECOP** — ya existe `campaign.get("use_secop", False)` en `hive_tools.py:133`
Agregar `use_secop_radar` siguiendo el mismo patrón para `secop_radar.py`.
Ambos toggles se configuran en `company_voice.fuentes_habilitadas[]`.

### Agente Outreach

**Cuándo corre:** cuando `hitl_status` pasa a `"approved"` → dispara `run_outreach()`

**Pipeline interno:**
1. Carga `company_voice` del usuario (Phase 12)
2. Carga `sector_profile` del sector del lead (Phase 12)
3. `build_system_prompt(OUTREACH_TEMPLATE, variables)` — temp=0.7
4. GPT-4o genera mensaje personalizado con voz de empresa
5. Envía por `canal_elegido`:
   - `"email"` → `smtplib` con SMTP_HOST/PORT/USER/PASS (env vars)
   - `"whatsapp"` → `graph.facebook.com/v18.0/{WA_PHONE_ID}/messages` con WA_TOKEN
6. Registra en `historial_conversacion[]` del lead
7. Programa reintento: `schedule_retry(lead_id, canal, days=7)` (Phase 12)
8. Actualiza `intento_actual` del lead

**Archivo:** `backend/outreach_agent.py`

```python
async def run_outreach(
    lead_id: str,
    user_id: str,
    canal: str,           # "email" | "whatsapp"
    intento: int = 1,     # 1, 2, o 3
) -> bool:
    # carga company_voice, sector_profile, genera mensaje, envía, registra
```

**Máximo 3 intentos:**
- Intento 1: mensaje principal
- Intento 2 (7 días después, vía scheduler): follow-up diferente
- Intento 3 (14 días después): último intento
- Sin respuesta tras 3 → `update_lead_estado(→ "nurturing")`

### Agente Nurturing

**Cuándo corre:** scheduler mensual (Phase 12) llama `run_nurturing()` para cada lead en estado `nurturing`

**Pipeline interno:**
1. Carga lead + `motivo_nurturing`
2. Carga `company_voice` + `sector_profile`
3. Genera contenido según motivo (temp=0.6):
   - `"score_bajo"` → contenido educativo del sector, sin pitch
   - `"rechazado_humano"` → valor puro, sin mencionar la empresa
   - `"sin_respuesta"` → toque suave diferente al outreach previo
   - `"respuesta_negativa"` → largo plazo, foco en tendencias del sector
4. Envía por `canal_elegido` del lead (mismo canal que outreach)
5. Evalúa si la respuesta (si hay) contiene señales de `sector_profile.señales_reentrada`
6. Si señal detectada → `update_lead_estado(→ "checkpoint")`
7. Si `ciclo_nurturing >= 12` y sin señal → `update_lead_estado(→ "archivado")`

**Archivo:** `backend/nurturing_agent.py`

```python
async def run_nurturing(
    lead_id: str,
    user_id: str,
) -> dict:
    # retorna: {mensaje_enviado: str, señal_detectada: bool, nuevo_estado: str}
```

### Email sender

`backend/email_sender.py` — wrapper de `smtplib`:
```python
async def send_email(to: str, subject: str, body: str, sender_name: str, sender_email: str) -> bool
```
Variables de entorno: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (agregar a `.env`)

### WhatsApp sender

`backend/whatsapp_sender.py` — ya existe `whatsapp_agent.py` con httpx + Meta Graph API
Extraer la función de envío de texto simple de `whatsapp_agent.py` en lugar de duplicarla:
```python
async def send_whatsapp_text(phone: str, message: str) -> bool
```
Variables de entorno: `WA_TOKEN`, `WA_PHONE_ID` (agregar a `.env`)

### Integración con pipeline existente

El hook de integración es el endpoint HITL existente en `main.py`:
```python
# Cuando hitl_status="approved" → invocar run_outreach() en background
# Cuando hitl_status="rejected" → update_lead_estado(→ "nurturing")
```
Phase 14 agrega los endpoints del ciclo de vida completo. En esta fase, el hook
va directamente en el endpoint HITL existente (`POST /api/leads/{id}/hitl`).

</decisions>

<specifics>
## Referencias del codebase existente

**`whatsapp_agent.py`** — ya tiene httpx + Meta Graph API implementado
Reutilizar la lógica de envío en vez de duplicar. `send_whatsapp_text()` es una extracción.

**`hive_tools.py:133`** — `use_secop=bool(campaign.get("use_secop", False))`
Patrón exacto a seguir para `use_secop_radar`.

**`database.py` → `update_lead_hitl(lead_id, user_id, decision)`**
Este es el hook de integración. Phase 13 modifica este flujo para disparar `run_outreach()`
cuando `decision="approved"` y transicionar a nurturing cuando `decision="rejected"`.

**`prospector.py`** — función principal del pipeline de descubrimiento
El scoring mejorado se inyecta aquí: cargar sector_profile y usarlo en el prompt del analista.

**Variables de entorno a agregar al `.env`:**
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
WA_TOKEN=
WA_PHONE_ID=
```

</specifics>

<deferred>
## Diferido a Phase 14

- `GET /api/leads/checkpoint` — lista de leads esperando decisión humana
- `POST /api/leads/{id}/decision` — aprobar/pausar/rechazar con canal y motivo
- `GET /api/leads/{id}/handover` — paquete completo cuando lead responde positivo
- `POST /api/leads/{id}/reporte-llamada` — reporte del humano tras llamar
- Frontend checkpoint UI — cards de leads con botones de acción

</deferred>

---

*Phase: 13-lead-outreach-nurturing-agents*
*Context actualizado: 2026-03-22 — integración en codebase existente, sin módulo separado*
