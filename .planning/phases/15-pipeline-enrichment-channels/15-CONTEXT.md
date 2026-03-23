# Phase 15: Pipeline Enrichment + Real Channel Activation — Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Esta fase conecta tres módulos ya escritos pero desconectados al pipeline operativo:

1. **SECOP bridge (B)** — El toggle de SECOP ya se guarda en `company_voice.fuentes_habilitadas` (Phase 14). El investigador (`hive_tools.py`) aún lee `campaign.get("use_secop", False)`. Hay que leer `fuentes_habilitadas` de `company_voice` al inicio de cada run y derivar los flags.

2. **NIT Enricher (C+D)** — `nit_enricher.enrich_nit(nit_raw)` existe con pipeline completo (RUES → SECOP histórico → Supersociedades → web). No se llama desde ningún punto del pipeline. Hay que insertarlo después del análisis del Analista, antes de guardar el expediente.

3. **WhatsApp real (A)** — `whatsapp_sender.send_whatsapp_text()` existe y está wired en `outreach.py`. La brecha es aguas arriba: el Investigador no extrae el teléfono del decisor, así que cuando el humano elige canal="whatsapp" no hay número. Hay que agregar extracción de teléfono al análisis + fallback a email cuando no hay número.

**Fuera de scope:** `whatsapp_agent.py` (bot Twilio para asesores) es un sistema separado — queda diferido.

</domain>

<decisions>
## Implementation Decisions

### SECOP bridge — cómo leer fuentes_habilitadas

- En `hive_tools.py`, la función `make_prospecting_registry(user_id, campaign, ...)` recibe `user_id`. Antes de llamar `discover_companies()`, hacer `await get_or_create_company_voice(user_id)` para obtener `fuentes_habilitadas`.
- Mapeo:
  - `"secop_adjudicados" in fuentes_habilitadas` → `use_secop=True`
  - `"secop_licitaciones" in fuentes_habilitadas` → `use_secop_radar=True`
- Los flags del `campaign` dict sirven como fallback si `fuentes_habilitadas` no existe (compatibilidad hacia atrás).
- Si `company_voice` no existe (cliente nuevo sin config), usar defaults: `use_secop=False`, `use_secop_radar=False`.

### NIT enrichment — dónde insertarlo en el pipeline

- Se llama en `hive_tools.py` dentro de la función `_analyze_company()` (Tool 2 — el Analista), después de que el Analista retorna su análisis pero antes de guardar el lead en MongoDB.
- El NIT se extrae del `expediente_json` si ya fue detectado por el Analista, o de los datos de SECOP/RUES si el nombre de empresa coincide.
- Si el NIT no se puede determinar → `enrich_nit()` se salta silenciosamente (no bloquea el pipeline).
- El resultado de `enrich_nit()` se merge en `lead.nit_data` como subcampo separado — NO reemplaza `expediente_json`.
- Cache de 24h del `nit_enricher.py` ya existe en memoria — no hay que implementarla.
- El enriquecimiento es **no bloqueante**: se lanza como `asyncio.create_task()` para no ralentizar el pipeline. Si falla, log warning y continúa.

### WhatsApp phone extraction — estrategia

- En `hive_tools.py` Tool 2 (`_analyze_company()`), el prompt al Analista ya extrae `decisor: {nombre, cargo, email}`. Agregar `telefono` al schema de salida esperada.
- El Analista ya tiene acceso a datos scrapeados — si hay teléfono visible en la web, lo extrae; si no, queda `null`.
- En `outreach.py`, cuando `canal_elegido == "whatsapp"` y `decisor.get("phone")` es vacío:
  - Fallback a email si hay email disponible
  - Registrar en `historial_conversacion`: `{tipo: "fallback", razon: "no_phone", canal_usado: "email"}`
  - Log warning con lead_id
- **No fallar silenciosamente**: el outreach siempre intenta enviar por algún canal y registra qué pasó.

### WhatsApp env vars

- `WA_TOKEN` y `WA_PHONE_ID` son vars de Meta Graph API ya soportadas en `whatsapp_sender.py`.
- Agregar al `.env.example` y documentar en un comentario en `railway.toml` / `vercel.json`.
- En modo dev sin estas vars: `whatsapp_sender` ya loguea error y retorna `False` — comportamiento correcto.

### Orden de ejecución en el pipeline

```
discover_companies()  ← lee fuentes_habilitadas → use_secop / use_secop_radar
  ↓
_analyze_company()    ← extrae NIT y teléfono del decisor en el prompt
  ↓
[asyncio.create_task] enrich_nit(nit)   ← no bloquea
  ↓
guardar lead en MongoDB (con nit_data cuando enriquecimiento completa)
  ↓
emit lead_checkpoint via WebSocket
```

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `nit_enricher.enrich_nit(nit_raw: str) -> dict` — función principal, cachea 24h, retorna dict con `razon_social_rues`, `rep_legal`, `contratos_secop`, `valor_total_contratado`, `entidades_contratantes`, `web`, `email_contacto`
- `nit_enricher.enrich_nits_batch(nits, max_concurrent=5)` — para batch processing futuro
- `get_or_create_company_voice(user_id)` en `landa/company_voice.py` — ya disponible en `hive_tools.py` (importado en `outreach.py`)
- `whatsapp_sender.send_whatsapp_text(phone, message)` — ya wired en `outreach.py`
- `asyncio.create_task()` — patrón ya usado en `main.py` para `run_outreach` y learning hooks

### Established Patterns

- **Fire-and-forget enrichment**: `main.py` usa `asyncio.create_task(run_outreach(...))` — mismo patrón para NIT enricher
- **Company voice loading**: `outreach.py` ya llama `get_or_create_company_voice(user_id)` — replicar en `hive_tools.py`
- **Fallback logging**: `outreach.py` usa `logger.error("[outreach_agent] No email for lead %s decisor", lead_id)` — mismo patrón para fallback de WhatsApp
- **Flag derivation**: `hive_tools.py` línea 127-134 ya maneja `use_secop` y `use_secop_radar` desde `campaign` dict — agregar lectura desde `company_voice` antes de esas líneas

### Integration Points

- **`hive_tools.py:127`** — donde se leen los flags de SECOP desde `campaign`. Agregar lectura de `company_voice.fuentes_habilitadas` antes de esta línea.
- **`hive_tools.py` Tool 2 (`_analyze_company`)** — donde el Analista genera el expediente. Agregar `telefono` al schema esperado y lanzar `enrich_nit()` como create_task.
- **`landa/agents/outreach.py:120-128`** — bloque `elif canal_elegido == "whatsapp"`. Agregar fallback cuando `phone` es vacío.
- **`database.py`** — puede necesitar `$set: {"nit_data": enriched}` en el update del lead una vez que el task completa.

### Files that need changes

| File | Change |
|------|--------|
| `backend/hive_tools.py` | Leer `company_voice.fuentes_habilitadas` → derivar use_secop/use_secop_radar + agregar `telefono` al schema del Analista + lanzar enrich_nit task |
| `backend/landa/agents/outreach.py` | Fallback email cuando phone=null para canal whatsapp |
| `backend/database.py` | Función `update_lead_nit_data(lead_id, nit_data)` si no existe |
| `.env.example` | Documentar WA_TOKEN, WA_PHONE_ID |

</code_context>

<specifics>
## Specific Ideas

- El enriquecimiento NIT NO debe bloquear el pipeline — `create_task` es correcto. El lead llega a checkpoint con los datos básicos; el NIT se agrega después. El CheckpointModal puede mostrar "Enriqueciendo..." si `nit_data` no está disponible aún.
- Si un lead viene de SECOP (no de Google Maps), ya tiene NIT en los datos de SECOP — `enrich_nit()` lo aprovecha directamente sin depender de que el Analista lo extraiga.
- El teléfono del decisor es oportunista: si el Analista lo ve en la web scrapeada lo incluye, si no, no. No hay búsqueda activa de teléfonos.

</specifics>

<deferred>
## Deferred Ideas

- `whatsapp_agent.py` — bot conversacional Twilio para que los asesores controlen el pipeline via WhatsApp. Sistema separado, requiere webhook Twilio + sesiones MongoDB. Diferido a Phase 16.
- NIT batch enrichment al inicio de una campaña (enriquecer todos los descubiertos en paralelo) — diferido, primero validar que el enriquecimiento individual funciona.
- Mostrar `nit_data` en el CheckpointModal (tarjeta del lead) — puede ser Phase 15.5 o Phase 16 dependiendo de esfuerzo.

</deferred>

---

*Phase: 15-pipeline-enrichment-channels*
*Context gathered: 2026-03-23*
