# Softseguros — Endpoint real de cartera (descubrimiento)

> **TL;DR:** La cola de cobranza (cuotas por cobrar, con fecha de vencimiento **y** fecha
> de compromiso **y** días de mora) se obtiene de **un solo endpoint** que sí funciona:
> `GET /api/pagopoliza/list_pagospolizas_filtro_paginados/`.
> El truco para que no dé 504 es scopearlo con `sede` + `estadopolizas_selected[]`.
>
> Fecha: 2026-07-03 · Cuenta: DPG Seguros (usuario de cartera). Credenciales en el gestor
> de secretos / `softseguros_credentials` — **no** en este doc.

> **⚠️ CORRECCIÓN 2026-07-04 — el `tipo` correcto para la DEUDA VIVA:**
> `tipo=consultar_nominas_pasadas` es la vista de pagos **YA cobrados** (recaudado=True) —
> NO sirve para la cola. La vista de **deuda viva** (recaudado=False, con días vencidos y
> compromiso) es **`tipo=cartera_por_pagar_compania`** (`fecha_a_buscar` = igual).
> Filtro de fecha: **`fecha_inicio`/`fecha_fin`** filtran por `fecha_pago` (único filtro de
> fecha server-side; el compromiso NO tiene filtro propio → filtrar local). Con la ventana
> del informe (`fecha_inicio=2026-06-15`) la cola real de DPG es **~45 cuotas** (vs 9.718 sin
> ventana, que incluye basura de 1900/2016). Verificado en vivo 2026-07-04.
> Nota: en la cartera actual `fecha_realizara_pago` (compromiso) == `fecha_pago` porque nadie
> ha renegociado aún; el compromiso empezará a diferir cuando ARIA registre "pago el viernes".

---

## El endpoint

```
GET /api/pagopoliza/list_pagospolizas_filtro_paginados/
Host: app.softseguros.com
Authorization: Token <token de /api-token-auth/>
Accept: application/json
```

- **200 OK, ~1s, ~46 KB/página**, paginado (`count/next/previous/results`, 10/pág).
- Con el filtro DPG de abajo: **`count ≈ 2279`** (la cartera real — no las 53.062 pólizas).
- Es un "method" del recurso `pagopoliza` (`/api/pagopoliza/<method>/`). El bundle del
  SPA lo teje dinámicamente, por eso no aparece como string literal.

### Auth
`POST /api-token-auth/` con `{username, password}` → `{"token": "..."}`.
Luego `Authorization: Token <token>` en cada request. (El UI usa `token` en minúscula;
DRF acepta ambas.)

---

## Parámetros que SÍ funcionan (capturados del UI real)

El scope mínimo que evita el 504 es **`sede`** + los estados de póliza. Params completos
tal como los manda la vista *Cobros → Listado de pagos*:

| Param | Valor (DPG) | Nota |
|---|---|---|
| `sede` | `1047` | **CLAVE.** Sin esto → 504. |
| `estadopolizas_selected[]` | `6576,6577,6579,9976,18887` | Estados "cobrables". Se repite el param por cada id. |
| `estado_polizas_selected[]` | (mismos ids) | El UI manda ambas variantes; con una basta. |
| `ramos_selected[]` | `1..126` (todos) | Un param por ramo. |
| `tipo` | `consultar_nominas_pasadas` | Modo de la consulta (vencidos/pasados). |
| `fecha_a_buscar` | `consultar_nominas_pasadas` | |
| `order_by` / `sort_by` | `fecha_pago` / `asc` | Ordena por vencimiento asc. |
| `dias_vencidos` | `-1` | -1 = todos. |
| `fecha_busqueda_pagos` | `-1` | |
| `page` | `1..N` | Paginación. |
| `search_in` | `poliza_numero_poliza` | |
| resto (`tipo_moneda`, `forma_pago_selected`, `tipo_cliente`, `with_override_commission`, `liquidados_vendedor`, `pendiente_pagar_cliente`, …) | `-1` / `0` / `""` | Sin filtro. |

> Los ids de `sede`, `estadopolizas_selected` y `ramos` son **config de DPG**, no secretos.
> Deben vivir en `tenant_config`, no hardcodeados.

---

## Respuesta — campos relevantes de cada cuota

Envelope: `{count, next, previous, results:[...], data_cache_stats}`.
Cada item de `results` es una **cuota/pago** con ~140 campos. Los que importan para cobranza:

| Necesidad (informe ARIA) | Campo API | Notas |
|---|---|---|
| **Fecha de pago** (vencimiento → días mora, speech vencida) | `fecha_pago` | Fecha original de vencimiento de la cuota. |
| **Fecha de compromiso** (fecha acordada → agenda de llamadas) | **`fecha_realizara_pago`** | ✅ Confirmado ≠ `fecha_pago`. Ej: venció 2017-07-04, comprometió 2017-08-09. |
| Fecha en que pagó | `fecha_realizo_pago` | |
| Días de mora | `edad_cartera` | Entero (días). |
| ¿Pagó? | `recaudado` | `True/False`. Cola viva = `recaudado=False`. |
| Saldo / valor cuota | `saldo_pendiente`, `valor_a_pagar`, `valor_neto_a_pagar` | |
| Nº de cuota | `numero_pago`, `pago_poliza_consecutivo` | |
| Teléfono | `poliza_cliente_celular` | 10 dígitos → prefijar `+57` para Twilio. |
| Cliente / documento | `poliza_cliente_nombres`, `poliza_cliente_apellidos`, `poliza_cliente_numero_documento` | |
| Ramo | `ramo_nombre`, `ramo_id` | |
| Nº póliza | `poliza_numero_poliza`, `poliza_id` | |
| Aseguradora | `aseguradora_nombre` | Recordar: "Inversiones Comerciales San Germán" → decir "Crediestado". |
| Modalidad de pago | `poliza_forma_pago` | `Contado` / `Financiado`. |
| Objeto asegurado (riesgo) | `poliza_codio_objeto_asegurado` | |
| Estado póliza | `poliza_estado_poliza_codigo_generico`, `poliza_activa` | |

**Todo lo que el informe pide sale de esta única llamada.** No hace falta cruzar endpoints.

---

## Callejones sin salida (NO reintentar — documentado para no re-quemar tiempo)

| Ruta | Resultado | Por qué |
|---|---|---|
| `GET /api/pagopoliza/` (lista global) | **504** | Intenta serializar toda la tabla. |
| `GET /api/pagopoliza/?poliza=<id>` | **504** | Ignora el filtro `poliza`. |
| `GET /api/pagopoliza/get_pagos_by_parameters/` | **504** | Sale del bundle pero le falta el scope de `sede`; usar `list_pagospolizas_filtro_paginados` en su lugar. |
| `GET /api/poliza/{id}/cartera/` | `count=0` siempre | No es el cronograma de cuotas. |
| `GET /api/poliza/{id}/pagopoliza/` | 404 | No existe. |
| `GET /api/poliza/` con filtros/`ordering` | Ignorados | El recurso `poliza` no tiene filtros server-side (53.062, 10/pág, orden por id asc, más viejas primero). |

---

## Cómo se descubrió (reproducible)

1. DevTools (F12) → **Network** → filtrar `Fetch/XHR`.
2. En Softseguros: menú **Cobros → Listado de pagos**.
3. Cambiar de página / aplicar filtro → aparece la request `list_pagospolizas_filtro_paginados/`.
4. *Copy → Copy as cURL* → replicar la URL con `Authorization: Token`.

El SPA vive en `/assets/index-*.js` (bundle único ~4.7 MB) y define los recursos como
métodos `/api/<recurso>/<method>/`.

---

## Integración — próximos pasos

1. **`adapter.py`** — añadir método:
   ```python
   async def list_pagos_filtrados(self, page: int = 1, *, sede, estados, ramos, extra=None) -> dict:
       """GET /api/pagopoliza/list_pagospolizas_filtro_paginados/ — cartera real (cuotas)."""
   ```
   Con los params de arriba. `sede`/`estados`/`ramos` desde `tenant_config`.
2. **`sync.py`** — reapuntar el scan a este método (reemplaza el workaround de `/api/poliza/`
   que sólo daba `fecha_limite_pago || fecha_fin`). Ahora cada `debtor` obtiene:
   `fecha_pago`, **`fecha_compromiso`** (`fecha_realizara_pago`), `edad_cartera`, valor de
   cuota real, nº de cuota. Filtrar cola viva por `recaudado=False`.
3. **Scheduler** — agendar por `fecha_compromiso` cuando exista; si no, por `fecha_pago`.
4. Mantener el upsert idempotente por `softseguros_poliza_id` + soft-delete que ya existen.

## Pendiente menor

La captura fue de la vista de **vencidos** (`tipo=consultar_nominas_pasadas`). Para
**próximos a vencer** (la Llamada 1 = día hábil −1) falta confirmar el `tipo`/filtro de
fecha correcto. Alternativa inmediata: como `count≈2279` es chico, traer todo y filtrar
`fecha_pago` localmente.
