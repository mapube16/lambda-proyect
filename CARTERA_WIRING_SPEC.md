# SPEC DE IMPLEMENTACIÓN — Cableado del endpoint real de cartera Softseguros (CERO hardcodeo, config por tenant)

> Repo: `C:/Users/maxim/Desktop/hive-pixel-office` · Rama base: `eval/dpg-cobranza-microservice`
> Endpoint objetivo: `GET /api/pagopoliza/list_pagospolizas_filtro_paginados/` (contrato en `backend/softseguros/CARTERA_ENDPOINT.md`)
> Principio rector: **ningún literal de scope/timing en código**. Todo vive en `tenant_configs.cobranza`, editable desde UI, cacheado con invalidación (CACHE-01). DPG = tenant #1.

---

## 1. Resumen del cambio (qué se toca y por qué)

| # | Archivo | Cambio | Por qué |
|---|---|---|---|
| A | `backend/cobranza/tenant_config.py` (tras `set_voice_persona`, l.118-141) | Nuevo `set_cobranza_config(user_id, block)` con whitelist de sub-bloques + `_invalidate(user_id)`. | Un único hogar de config cacheado (`config_cache.py` TTL 300s, l.30) e invalidado en cada write (l.39-50). Hoy la config está fragmentada en 3 colecciones. |
| B | `backend/softseguros/adapter.py` (tras `get_poliza`, l.222) | Nuevo `list_pagos_filtrados(page, *, params)` que pega a `/api/pagopoliza/list_pagospolizas_filtro_paginados/` reutilizando `_get_json` (l.188-190). | Es el único endpoint que trae `fecha_pago` + `fecha_realizara_pago` + `edad_cartera` (CARTERA_ENDPOINT.md l.64-82). `list_pagopoliza` (l.194-199) da 504; `list_polizas` (l.211-218) no trae cronograma de cuotas. |
| C | `backend/softseguros/sync.py` (`_fetch_page` l.421-422; mapper l.178-224; probe l.434-471, l.509-524) | Reapuntar el scan al método nuevo con params armados desde `tenant_config`; nuevo `_pago_to_debtor_doc`; desactivar early-cutoff para cartera; filtrar `recaudado=False`. | Cambia el modelo de PÓLIZA a CUOTA con vencimiento/compromiso/mora reales. |
| D | `backend/cobranza/debtor_crud.py` (`_SOFTSEGUROS_SET_FIELDS` l.262-273; clave de upsert l.276-353) | Ampliar whitelist con los campos de cuota; nueva clave idempotente por-cuota `softseguros_pago_id`. | La whitelist descarta silenciosamente campos no listados; la clave `(user_id, softseguros_poliza_id)` colapsa las N cuotas de una póliza en 1 deudor. |
| E | `backend/softseguros/classifier.py` (l.51-78) | `classify_cuota(fecha_pago, recaudado, today, ventana_dias)`; ventana +30 (l.76) → config. | Clasificar por la fecha de la cuota, no por `fecha_fin`; ventana editable por tenant. |
| F | `backend/cobranza/router.py` (nuevos `GET`/`PATCH /api/cobranza/config`) | Leer/escribir el bloque `cobranza` completo. Hoy sólo hay `onboarding/approve` (write) y `status` (bool). | Sin GET no se puede pre-cargar la config para editarla; sin PATCH no se re-edita tras onboarding. |
| G | `backend/routes/debtors.py` (`ImportFilters` l.73-86; `configure_softseguros` l.126-158) | Mantener credenciales aquí; el scope de cartera se lee de `tenant_config`, no de `sync_state`. | Consolidar fuente de verdad del scope. |
| H | `backend/softseguros/scheduler.py` (l.24-63) | Hora/frecuencia por tenant en vez de env global `SOFTSEGUROS_SYNC_DAILY_HOUR_UTC`. | Multi-tenant: cada tenant su cadencia. |
| I | `backend/cobranza/call_scheduler.py` (l.17-70) + `campaign_scheduler.py` (l.187, l.243, l.263, l.295) | Franjas/festivos/max-contactos/intervalos → `tenant_config`, **clampeando** contra Ley 2300 como techo legal duro. | Timings/horarios/volumen hoy son literales globales. |
| J | `frontend/src/components/SoftSegurosSetup.tsx` + `frontend/src/hooks/useSoftSegurosDebtors.ts` (tipo l.30-39, DEFAULT_FILTERS l.94-100) + nuevo panel `CobranzaSettings` en `CobranzaTab.tsx` | Formularios para sede/estados/ramos/tipo/orden + timings/horarios/volumen/estrategia. | Requisito "editable desde UI". |

---

## 2. `tenant_config`: shape JSON completo propuesto

Se guarda en `tenant_configs` (colección ya cacheada) bajo la llave `cobranza`. Se lee con `config_cache.get_tenant_config(user_id)` (`config_cache.py` l.65). Ver el JSON de ejemplo completo en el campo `tenant_config_shape`. Bloques:

- **`cobranza.softseguros_cartera`** — todo el querystring del endpoint + reglas de importación/clasificación:
  - `base_url` (hoy hardcodeado en `adapter.py` l.59), `sede` (**obligatorio**, anti-504), `estadopolizas_selected[]`, `ramos_selected[]`, `tipo`, `fecha_a_buscar`, `order_by`, `sort_by`, `dias_vencidos`, `fecha_busqueda_pagos`, `search_in`, `extra_filtros{}` (filtros neutros), `solo_no_recaudadas` (cola viva `recaudado=False`), `ventana_proximos_dias` (hoy `classifier.py` l.76), `import_filters{}` (migra desde `softseguros_sync_state.import_filters`), `max_concurrency` (hoy `sync.py` l.41), `alias_aseguradoras{}` (p.ej. "Inversiones Comerciales San Germán" → "Crediestado", CARTERA_ENDPOINT.md l.77).
- **`cobranza.sync`** — `frecuencia`, `hora_utc` (hoy env, `scheduler.py` l.24-28).
- **`cobranza.timings`** — `offsets_intentos_dias_habiles`, `frecuencia_dias` (hoy `cobranza_config.estrategia`, `campaign_scheduler.py` l.263), `max_intentos` (hoy default 5 en `debtor_crud.py` l.298/l.339 y `campaign_scheduler.py` l.243), `pre_vencimiento_dias` (l.187), `job_interval_min`/`rescue_stuck_min` (l.295), `agendar_por` (`fecha_compromiso`|`fecha_pago`).
- **`cobranza.horarios`** — `dias_habiles`, `franjas`, `franjas_sabado`, `festivos`, `max_contactos_dia`, `timezone` (hoy hardcodeado `call_scheduler.py` l.14-70).
- **`cobranza.volumen`** — `llamadas_por_dia`, `distribucion` (no existen hoy).
- **`cobranza.estrategia`** — `tono` + `guion{saludo,propuesta,objeciones,cierre}` (hoy en `cobranza_config.estrategia`).

> **Ley 2300 = techo, no default:** al persistir `horarios`, el backend debe **clampear** contra L-V 7-19 / Sáb 8-15 / Dom-festivo nunca / máx 1 contacto-día (`call_scheduler.py` l.40-70). La UI nunca puede habilitar una franja que exceda el límite.

---

## 3. `adapter.py`: firma exacta + construcción de params

Añadir tras `get_poliza` (l.222). El adapter es "tonto": recibe los params ya armados (cero literales de scope), sólo agrega `page` y delega en `_get_json`/`_request` (auth Token + retry ya resueltos l.122-190).

```python
async def list_pagos_filtrados(self, page: int = 1, *, params) -> dict:
    """GET /api/pagopoliza/list_pagospolizas_filtro_paginados/ — cartera real (cuotas).

    `params` llega ARMADO desde tenant_config (list[tuple[str,str]] o dict).
    NADA hardcodeado aquí: sede/estados/ramos/tipo/order vienen por argumento.
    Los params-lista (estadopolizas_selected[], ramos_selected[]) deben venir
    como tuplas repetidas para que httpx repita la clave por id.
    """
    query = list(params.items()) if isinstance(params, dict) else list(params)
    query.append(("page", str(page)))
    return await self._get_json(
        "/api/pagopoliza/list_pagospolizas_filtro_paginados/", params=query
    )
```

La **construcción del querystring** vive en `sync.py` (no en el adapter) como `list[tuple]` para controlar el nombre exacto de la clave y la repetición:

```python
def _build_cartera_query(c: dict) -> list[tuple[str, str]]:
    q: list[tuple[str, str]] = [
        ("sede", str(c["sede"])),                 # OBLIGATORIO — sin él → 504
        ("tipo", c.get("tipo", "consultar_nominas_pasadas")),
        ("fecha_a_buscar", c.get("fecha_a_buscar", c.get("tipo"))),
        ("order_by", c.get("order_by", "fecha_pago")),
        ("sort_by", c.get("sort_by", "asc")),
        ("dias_vencidos", str(c.get("dias_vencidos", -1))),
        ("fecha_busqueda_pagos", str(c.get("fecha_busqueda_pagos", -1))),
        ("search_in", c.get("search_in", "poliza_numero_poliza")),
    ]
    for eid in c.get("estadopolizas_selected", []):
        q.append(("estadopolizas_selected[]", str(eid)))
        # DRF también acepta la variante; con una basta (CARTERA_ENDPOINT.md l.42-43).
    for rid in c.get("ramos_selected", []):
        q.append(("ramos_selected[]", str(rid)))
    for k, v in (c.get("extra_filtros") or {}).items():
        q.append((k, str(v)))
    return q
```

El adapter se instancia en `run_sync` (`sync.py` l.314) pasándole `base_url` desde config:
`adapter = SoftSegurosAdapter(username, password, base_url=cartera_cfg.get("base_url", "https://app.softseguros.com"))`.

> **Riesgo de encoding (verificar en integración):** httpx URL-encodea `[]` a `%5B%5D`. DRF normalmente lo decodifica. Confirmar con una llamada real que el filtro se aplica (`count≈2279`, no 504). Si el server exige brackets literales, usar `httpx.QueryParams` o serializar a mano.

---

## 4. `sync.py`: reapuntar el scan + mapeo API→debtor

**Repunte del scan** (`_fetch_page`, l.421-422):
```python
# cartera_query se computa 1 vez al inicio de run_sync desde tenant_config:
#   cfg = await get_tenant_config(user_id)
#   cartera_cfg = (cfg.get("cobranza") or {}).get("softseguros_cartera") or {}
#   cartera_query = _build_cartera_query(cartera_cfg)
async def _fetch_page(page: int) -> dict:
    return await call(lambda: adapter.list_pagos_filtrados(page=page, params=cartera_query))
```

**Early-cutoff / probe** (`_probe_start_page` l.434-471; Fase A l.509-524): **desactivar** para el recurso de cartera. `_page_max_fecha` (l.424-432) asume monotonía `fecha_fin~id` de `/api/poliza/`, supuesto que NO aplica a las cuotas. Con `count≈2279` (≈228 páginas de 10) traer todo: `pages_to_fetch = range(1, last_page+1)`.

**Cola viva:** en `_persist_poliza` (l.377-405) descartar/soft-marcar cuotas con `recaudado=True` cuando `solo_no_recaudadas=True`.

**Nuevo mapper** `_pago_to_debtor_doc(pago, bucket)` (reemplaza `_poliza_to_debtor_doc` l.178-224). El teléfono se normaliza con `cobranza.csv_parser.normalize_phone(valor, 'CO')` (produce `+57XXXXXXXXXX`; verificar firma en `csv_parser.py`) — `poliza_cliente_celular` viene a 10 dígitos sin prefijo.

### Tabla de mapeo campo-API → campo-debtor

| Campo API (`results[i]`) | Campo debtor (`$set`) | Notas |
|---|---|---|
| `id` (de la cuota) | `softseguros_pago_id` | **Clave idempotente nueva.** Fallback compuesto si no hay id global: `f"{poliza_id}:{numero_pago}"`. Ver §8. |
| `poliza_id` | `softseguros_poliza_id` | Se conserva para agrupar cuotas de una póliza. |
| `fecha_pago` | `vencimiento`, `fecha_pago` | Vencimiento real de la cuota; `fecha_referencia` de mora. |
| `fecha_realizara_pago` | `fecha_compromiso` | Compromiso ≠ vencimiento (CARTERA_ENDPOINT.md l.67). Agenda del scheduler. |
| `fecha_realizo_pago` | `fecha_realizo_pago` | Informativo. |
| `edad_cartera` | `edad_cartera` (`dias_mora`) | Entero días — sustituye cálculo local. |
| `recaudado` | `recaudado` | Cola viva = `False`. |
| `valor_a_pagar` (o `valor_neto_a_pagar`) | `monto`, `valor_cuota` | `float()`. Decidir cuál es el "monto" a cobrar (§8). |
| `saldo_pendiente` | `saldo_pendiente` | |
| `numero_pago` (o `pago_poliza_consecutivo`) | `numero_cuota` | |
| `poliza_cliente_celular` | `telefono` | `normalize_phone(..., 'CO')` → `+57…`. |
| `poliza_cliente_nombres` + `poliza_cliente_apellidos` | `nombre` | `join`. |
| `poliza_cliente_numero_documento` | `cliente_documento` | |
| `poliza_numero_poliza` | `numero_poliza` | |
| `ramo_nombre` | `ramo_nombre` | |
| `ramo_id` | `ramo_id` | |
| `aseguradora_nombre` | `aseguradora_nombre` | Aplicar `alias_aseguradoras` de config. |
| `poliza_forma_pago` | `forma_pago` | `Contado`/`Financiado`. |
| `poliza_codio_objeto_asegurado` | `objeto_asegurado` | |
| (bucket clasificado) | `status_softseguros` | `ya_vencidos`/`proximos_a_vencer`. |
| — | `is_active` | `True` (cola viva). |

---

## 5. API de config: leer/guardar `tenant_config`

**Backend helper** (`tenant_config.py`, tras l.141), imitando `set_voice_persona`:
```python
COBRANZA_BLOCK_KEYS = ("softseguros_cartera", "sync", "timings", "horarios", "volumen", "estrategia")

async def set_cobranza_config(user_id: str, block: dict) -> None:
    clean = {f"cobranza.{k}": block[k] for k in COBRANZA_BLOCK_KEYS if k in block and block[k] is not None}
    if not clean:
        return
    db = get_db(); now = _utcnow()
    await db.tenant_configs.update_one(
        {"user_id": user_id},
        {"$set": {**clean, "user_id": user_id, "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await _invalidate(user_id)   # CACHE-01
```

**Endpoints** en `backend/cobranza/router.py` (junto a `status` l.74-89):
- `GET /api/cobranza/config` → `get_cached_tenant_config(user_id)`, devuelve `cobranza` (o defaults DPG si vacío). Sirve para pre-cargar la UI.
- `PATCH /api/cobranza/config` → valida con Pydantic anidado (`SoftsegurosCarteraBlock`, `TimingsBlock`, `HorariosBlock`, `VolumenBlock`, `EstrategiaBlock`), **clampea horarios contra Ley 2300**, valida `sede`/`estadopolizas_selected` no vacíos, llama `set_cobranza_config`. `user_id` SIEMPRE del JWT (`Depends(get_current_user)`), nunca del body.

> No usar `PATCH /api/tenant/config` existente: su `TenantConfigUpdateRequest` (`tenant_admin.py` l.37-41) whitelistea 4 campos y filtra con `model_dump()` (l.72) → descartaría el bloque `cobranza`. (Alternativa: ampliar ese modelo; se prefiere endpoint dedicado en cobranza.)

`configure-softseguros` (`debtors.py` l.126-158) queda **sólo para credenciales**; el scope de cartera ya no viaja ahí.

---

## 6. UI: componentes y campos exactos

### 6.1 `SoftSegurosSetup.tsx` + `useSoftSegurosDebtors.ts` (scope de cartera)
Ampliar el tipo `SoftSegurosImportFilters` (l.30-39) y `DEFAULT_FILTERS` (l.94-100) → nuevo tipo `CarteraScope` y form:
- **Sede** — input numérico (requerido, validación no-vacío). Default DPG `1047`.
- **Estados de póliza** — multiselect de chips `{id,label}`. Default `[6576,6577,6579,9976,18887]`.
- **Ramos** — multiselect (o "Todos" = `1..126`).
- **Tipo / order_by / sort_by** — selects. Default `consultar_nominas_pasadas` / `fecha_pago` / `asc`.
- **Ventana próximos (días)** — pill. Default `30`.
- Se conservan los checkboxes actuales de `import_filters` (vencidos/proximos/cartera_states/max_age_months/include_cancelled).
Enviar en el body del nuevo `PATCH /api/cobranza/config`.

### 6.2 `DebtorsSoftSegurosTab.tsx` (panel Re-importar, l.754-788)
Exponer los mismos campos de scope para ajustarlos post-onboarding sin desconectar.

### 6.3 Nuevo panel `CobranzaSettings` en `CobranzaTab.tsx` (visible cuando `configured=true`)
Hoy `CobranzaOnboarding` sólo aparece con `!configured` (l.1641-1648) y no hay pantalla de edición posterior. El panel hace `GET /api/cobranza/config` y renderiza editable:
- **Estrategia:** `tono` (input) + `guion` (4 textarea) + `frecuencia_dias` + `max_intentos`.
- **Timings:** `offsets_intentos_dias_habiles` (p.ej. `[-1,+1,+3]`), `pre_vencimiento_dias`, `job_interval_min`, `rescue_stuck_min`, `agendar_por`.
- **Horarios:** editor de `franjas` (rango horario por día), `dias_habiles`, `festivos` (date-picker), `max_contactos_dia` — con indicador visual del techo Ley 2300.
- **Volumen:** `llamadas_por_dia`, `distribucion`.
- **Sync:** `frecuencia`, `hora_utc`.
Guarda con `PATCH /api/cobranza/config`.

---

## 7. Orden de implementación (pasos atómicos + qué verificar)

1. **Config store** — `tenant_config.set_cobranza_config` + `COBRANZA_BLOCK_KEYS`. **Verificar:** write invalida Redis (`_invalidate`); `get_cached_tenant_config` devuelve el bloque.
2. **Adapter** — `list_pagos_filtrados(page, *, params)`. **Verificar (test):** serialización repite `estadopolizas_selected[]`/`ramos_selected[]` por id y agrega `page`; reutiliza auth Token.
3. **Sync — query builder + repunte** — `_build_cartera_query`, repuntar `_fetch_page` (l.421-422), pasar `base_url` al adapter (l.314), desactivar probe (l.509-524). **Verificar:** una llamada real trae `count≈2279` sin 504; se recorren todas las páginas.
4. **Sync — mapper + cola viva** — `_pago_to_debtor_doc` (tabla §4), filtrar `recaudado=False`, `normalize_phone`. **Verificar:** un deudor de muestra trae `fecha_pago`, `fecha_compromiso`, `edad_cartera`, `valor_cuota`, `numero_cuota`, teléfono `+57…`.
5. **debtor_crud — whitelist + clave** — añadir a `_SOFTSEGUROS_SET_FIELDS` (l.262-273): `softseguros_pago_id, fecha_pago, fecha_compromiso, fecha_realizo_pago, edad_cartera, valor_cuota, saldo_pendiente, numero_cuota, aseguradora_nombre, forma_pago, objeto_asegurado, ramo_id` (+ los ya seteados que hoy se pierden: `aseguradora_nombre/forma_pago/medio_pago/objeto_asegurado/numero_de_cuotas`). Nuevas `upsert_debtor_by_softseguros_pago_id` / `build_softseguros_pago_upsert_op` con clave `(user_id, softseguros_pago_id)`; índice único. **Verificar:** N cuotas de una póliza → N deudores distintos (no colapsan).
6. **Classifier** — `classify_cuota(fecha_pago, recaudado, today, ventana_dias)`; ventana desde config. **Verificar:** cuota vencida→`ya_vencidos`, dentro de ventana→`proximos_a_vencer`, `recaudado=True`→`pagado`.
7. **API config** — `GET`/`PATCH /api/cobranza/config` con Pydantic anidado + clamp Ley 2300 + validación `sede`/estados no vacíos. **Verificar:** PATCH persiste y GET devuelve; body sin `sede` → 400; franja fuera de 7-19 → clampeada.
8. **Schedulers tenant-aware** — `scheduler.py` (hora/frecuencia por tenant; cron horario que compara `hora_utc` del tenant), `call_scheduler.py` `is_contact_allowed_now(cfg)`/`has_been_contacted_today(debtor, max)`, `campaign_scheduler.py` leer `timings`. **Verificar:** dos tenants con horas distintas sincronizan a horas distintas; franja fuera de config no llama.
9. **UI** — §6.1/6.2/6.3. **Verificar (e2e):** editar sede/estados desde UI → nuevo sync trae distinto `count`; editar franja/festivo → scheduler respeta.

---

## 8. Incógnitas / decisiones a cerrar

1. **`tipo` para PRÓXIMOS a vencer** — la captura fue de vencidos (`consultar_nominas_pasadas`, CARTERA_ENDPOINT.md l.126-131). El `tipo`/filtro de fecha para "próximos" está **sin confirmar**. Mitigación: como `count≈2279` es chico, traer todo y filtrar `fecha_pago` localmente con `ventana_proximos_dias`. Dejar `tipo` configurable.
2. **ID único de la cuota** — CARTERA_ENDPOINT.md no nombra el campo `id` global de la cuota (`numero_pago`/`pago_poliza_consecutivo` son consecutivos por póliza, no globales). **Confirmar** que cada `results[i]` trae `id`. Si no, usar clave compuesta `f"{poliza_id}:{numero_pago}"`. Bloquea la clave idempotente (paso 5).
3. **`estadopolizas_selected[]` vs `estado_polizas_selected[]`** — el UI real manda ambas; el .md dice "con una basta" (l.43). Decidir una; validar contra DRF. Igual para el encoding `%5B%5D` (§3).
4. **Cuál campo es el "monto" a cobrar** — `valor_a_pagar` vs `valor_neto_a_pagar` vs `saldo_pendiente` (l.71). Definir precedencia de negocio (recomendado: `saldo_pendiente` como deuda viva, `valor_a_pagar` como valor de cuota).
5. **Precedencia de `max_intentos`** — hoy doble fuente: `cobranza_config.estrategia` y doc del deudor (`campaign_scheduler.py` l.243). Al unificar en `timings.max_intentos`, definir que config-tenant gana salvo override explícito por deudor.
6. **Lista real de `ramos_selected`** — el .md dice `1..126` (todos). Confirmar el rango exacto o exponer "Todos" en UI y expandir en backend.
7. **Migración de `import_filters`** — hoy en `softseguros_sync_state.import_filters` (`sync.py` l.615). Decidir: leer primero de `tenant_config.cobranza.softseguros_cartera.import_filters` con fallback a `sync_state` durante la transición, luego deprecar el store viejo.
8. **`agendar_por`** — usar `fecha_compromiso` (`fecha_realizara_pago`) si existe, si no `fecha_pago` (CARTERA_ENDPOINT.md l.123). Confirmar con negocio para la agenda de llamadas.
9. **Festivos** — hoy `COLOMBIA_HOLIDAYS_2026` sólo cubre 2026 (`call_scheduler.py` l.17-36). Al hacerlos config, definir formato (`YYYY-MM-DD`) y quién los provee por año; sin esto en 2027 el guard queda vacío.

---

## Anexo — tenant_config_shape (JSON de ejemplo)

```json
{
  "user_id": "<uid>",
  "cobranza": {
    "softseguros_cartera": {
      "base_url": "https://app.softseguros.com",
      "sede": 1047,
      "estadopolizas_selected": [6576, 6577, 6579, 9976, 18887],
      "ramos_selected": [1, 2, 3, "...", 126],
      "tipo": "consultar_nominas_pasadas",
      "fecha_a_buscar": "consultar_nominas_pasadas",
      "order_by": "fecha_pago",
      "sort_by": "asc",
      "dias_vencidos": -1,
      "fecha_busqueda_pagos": -1,
      "search_in": "poliza_numero_poliza",
      "extra_filtros": {
        "tipo_moneda": -1,
        "forma_pago_selected": -1,
        "tipo_cliente": -1,
        "with_override_commission": 0,
        "liquidados_vendedor": 0,
        "pendiente_pagar_cliente": ""
      },
      "solo_no_recaudadas": true,
      "ventana_proximos_dias": 30,
      "max_concurrency": 5,
      "import_filters": {
        "include_vencidos": true,
        "include_proximos": true,
        "cartera_states": ["Pendiente por pagar"],
        "max_age_months": 12,
        "include_cancelled": false
      },
      "alias_aseguradoras": {
        "Inversiones Comerciales San Germán": "Crediestado"
      }
    },
    "sync": {
      "frecuencia": "diaria",
      "hora_utc": 3
    },
    "timings": {
      "offsets_intentos_dias_habiles": [-1, 1, 3],
      "frecuencia_dias": 2,
      "max_intentos": 5,
      "pre_vencimiento_dias": 3,
      "job_interval_min": 60,
      "rescue_stuck_min": 15,
      "agendar_por": "fecha_compromiso"
    },
    "horarios": {
      "timezone": "America/Bogota",
      "dias_habiles": [1, 2, 3, 4, 5],
      "franjas": [["09:00", "12:00"], ["14:00", "16:00"]],
      "franjas_sabado": [["09:00", "12:00"]],
      "festivos": ["2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03"],
      "max_contactos_dia": 1
    },
    "volumen": {
      "llamadas_por_dia": 200,
      "distribucion": "uniforme"
    },
    "estrategia": {
      "tono": "empatico y profesional",
      "guion": {
        "saludo": "",
        "propuesta": "",
        "objeciones": "",
        "cierre": ""
      }
    }
  }
}
```
