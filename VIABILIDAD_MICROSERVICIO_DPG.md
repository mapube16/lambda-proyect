# Reporte de Viabilidad — Microservicio de Voz dedicado (ARIA) para DPG Seguros

> Alcance evaluado: extraer el bot de cobranza de **VOZ** (ARIA) del monolito FastAPI (`lambda-proyect`, carpeta local `hive-pixel-office/backend`) a un microservicio **dedicado single-tenant DPG**. El canal de WhatsApp queda **fuera** (lo cubre `landa-agent-service`); de él solo importa el contrato REST de handoff.
> Fecha: 2026-07-04 · Síntesis de 5 evaluaciones dimensionales + lectura directa de `HANDOFF.md`, `DPG_GAP_ANALYSIS.md` y `backend/softseguros/CARTERA_ENDPOINT.md`.

---

## 1. Veredicto ejecutivo

**VIABLE CON RESERVAS.** Construir el microservicio de voz es técnicamente sólido y barato de separar: cobranza ya es un *bounded context* aislado, corre sobre exactamente el stack objetivo (FastAPI + Motor/Mongo + APScheduler + Twilio/Pipecat/Gemini Live) y su acoplamiento al monolito resultó ser **superficial y enumerable** (`get_db` de 3 líneas, `auth.py` de 81 líneas, y un `connection_manager` que es un **stub no-op**). La reserva central no es la separación: es que **la mayor parte del comportamiento que exige el informe ARIA está especificado pero NO construido** (secuencia de 3 intentos en días hábiles, 4 speeches, horarios DPG, reagendamiento, alertas tipadas, reportes) y ese trabajo es **idéntico se extraiga o no**. A eso se suma una dependencia externa dura: el contrato REST voz↔WhatsApp es *greenfield* y está **bloqueado** porque `landa-agent-service` no ha iniciado su Fase 6.

---

## 2. Tabla resumen por dimensión

| Dimensión | Veredicto | Una línea |
|---|---|---|
| Cobertura funcional | 🟡 viable con reservas | El micro de voz es un servicio coherente y bien acotado, pero ~70% del comportamiento del informe está especificado y no construido (y hay defaults genéricos que lo contradicen). |
| Reutilización de código | 🟢 viable | ~90% del código se levanta tal cual o con cambios mecánicos; el acoplamiento al monolito es superficial y de un solo patrón repetido. |
| Integraciones (Softseguros · Voz · REST WhatsApp) | 🟡 viable con reservas | Softseguros y Voz ya funcionan end-to-end; el contrato REST de handoff no existe y está bloqueado por un tercero. |
| Arquitectura y esfuerzo | 🟡 viable con reservas | La carve-out es de bajo riesgo y barata (~4-7 días), pero por sí sola no entrega ninguna feature DPG. |
| Riesgos y costos | 🔴 no viable *(como micro dedicado ahora)* | Sería el 3er servicio para un solo cliente y descarta el motor multi-tenant; recomienda un perfil DPG sobre el monolito. |

> **Cómo se resuelve el disenso 4-a-1:** la única dimensión en rojo (`riesgos-costos`) apoya su veredicto en dos premisas que el análisis a nivel de código refuta: (a) que "extraer cobranza es desenredar BD/infra compartida" — pero `reutilizacion-codigo`, que efectivamente hizo grep, encontró que el acoplamiento es trivial y que el temido `ConnectionManager`/WebSocket **no existe** (es un stub de 24 líneas); y (b) `riesgos-costos` y `DPG_GAP_ANALYSIS` subestiman lo ya construido. La objeción **estratégica** de esa dimensión (fragmentar la operación para 1 cliente) sí es válida y se recoge como reserva, no como bloqueo técnico.

---

## 3. Alcance funcional del micro propuesto

### Qué SÍ es del microservicio de voz (dueño único)
- **Motor de marcado y secuenciación de intentos** (informe §3, TABLA 1: L1 día hábil −1, L2 día de vencimiento, L3 +2 días hábiles; tope duro de 3).
- **Los 4 speeches** (§9.1-9.4): no vencida, día de vencimiento, vencida (# días de mora), y **entrante/devolución** (inbound).
- **Consulta EN llamada** (§5): validar identidad por documento + dar info administrativa de póliza. Ya hay primitivas vivas: `verify_identity`, `get_policy_info`, `search_knowledge` (`voice_pipecat.py` tools_schema ~487-491).
- **Horarios DPG** (§2: 9-12 y 14-16, solo L-V), distribución/cupo diario, y **jornada de arranque** (~250/día × 2 días, orden cronológico).
- **Alertas generadas EN llamada** (§7) como eventos tipados.
- **Ingesta de cartera** (Softseguros, autocontenida) y el **lado-voz de los reportes** (§12).
- **REST saliente** hacia `landa-agent-service` (disparo de link/cupón, Mensajes 1/2/3, handoff de caso) y **REST entrante** (comprobante-validado / ya-pagó → detener marcación).

### Qué NO (fuera de alcance — es de `landa-agent-service`)
- Atención y **Q&A por WhatsApp** (§8), contenido de los 8 mensajes (§10), menú (§11), validación de comprobantes, escalación a Chatwoot.

### Zona compartida / huérfana (decidir dueño)
- **Disparo de WhatsApp desde voz**: la voz **decide y dispara**, pero el render/envío es del otro micro (confirmado en `HANDOFF.md` L20-28).
- **Reporte diario/semanal**: el lado-voz posee casi todos los insumos, pero "comprobantes recibidos" (§12) proviene del micro de WhatsApp → agregación compartida. Hoy figura como **huérfano** (`HANDOFF.md` L26).

---

## 4. Reutilización de código — qué se levanta limpio vs. qué está acoplado

**Conclusión:** ~90% reutilizable. El esfuerzo real de extracción no es desacoplar dominio, sino re-aprovisionar infraestructura (Mongo/Redis/scheduler/auth) y decidir qué hacer con ~7-8 archivos de código muerto.

### Se levanta limpio (sin imports del monolito, verificado por grep)
- **Todo el paquete `softseguros/`**: `adapter.py` (httpx+tenacity), `classifier.py`, `credentials.py` (Fernet), `sync.py`, `verify.py`, `scheduler.py` (crea su propio `AsyncIOScheduler`). Único toque: `from cobranza import debtor_crud`.
- **`debtor_crud.py`** (437 líneas, PURO): cada función recibe `db` como argumento. Es el activo más reutilizable, compartido por cobranza y softseguros.
- **Librería limpia**: `prompt_builder.py`, `call_scheduler.py`, `csv_parser.py`, `es_numbers.py`, `rag_service.py`, `config_cache.py`, clientes TTS/STT.
- **`sub_agents/`** (existe en la rama viva, contra lo que dice `DPG_GAP_ANALYSIS`): `debtor_updater.py`, `escalation_handler.py`, `identity_verifier.py` reciben `db`; su único toque es el stub no-op.
- **`voice_pipecat.py`** (motor vivo, 1032 líneas): reutilizable; toques mínimos a `config_cache`, `cobranza_orchestrator` y un `get_db` perezoso.

### Puntos de acoplamiento (todos superficiales, mismo patrón repetido)
| Punto | Naturaleza | Costo de resolver |
|---|---|---|
| `database.get_db()` | Handle Motor de 3 líneas, `_client[DB_NAME]` | Crear `db.py` local; reapuntar ~10 imports |
| `auth.get_current_user/require_staff` | JWT HS256 autocontenido, 81 líneas | Copiar tal cual, o colapsar a API-key single-tenant |
| `services.connection_manager` | **STUB NO-OP** (24 líneas; "WebSocket removed in favour of HTTP polling") | Copiar 24 líneas o borrarlas — el acoplamiento temido **no existe** |
| `state.arq_pool` (Redis/ARQ) | Solo lo usa `whatsapp_notifier` y el DLQ de Vapi | Se elimina al reemplazar el notifier por REST |
| `landa.scheduler` (singleton) | Registro de jobs | Crear `AsyncIOScheduler` propio (patrón ya presente) |
| Índices de `debtors` en `init_db()` (L72-143) | **No viajan con el código** | **Copiar ese bloque** o el upsert idempotente y la de-dup fallan |

### Riesgo de reutilización: código muerto que NO migrar
- **Stack Vapi** (`vapi_client.py`, `webhooks.py` con `_push_dlq` **duplicado**) y **stack Assembly AI/orchestrator** (`voice_orchestrator.py` termina en pseudocódigo, TTS Deepgram/Google/ElevenLabs). El informe ARIA no exige Vapi. **Borrar al extraer**, no copiar a ciegas.

---

## 5. Integraciones

Las tres son factibles pero con **madurez muy dispar**. Dos supuestos del enunciado están **desactualizados frente al código real** y conviene corregirlos:
- La voz **NO usa OpenAI Realtime**, usa **Gemini Live** (`voice_pipecat.py:35`, `models/gemini-3.1-flash-live-preview`) sobre **Twilio** (no Telnyx; el naming Telnyx es ruido a limpiar).
- El endpoint real de cartera **está documentado pero AÚN NO cableado**.

### Softseguros — BAJO/MEDIO (base madura, falta un cableado bien especificado)
- `adapter.py` es sólido y portable: auth por **Token DRF** (no Bearer), re-auth en 401, backoff con `tenacity` en 429/5xx, paginación, 404→soft-delete.
- **TODO concreto**: hoy `adapter.py` solo tiene `list_polizas` (workaround `/api/poliza/`, escanea 53K pólizas) y `list_pagopoliza` (504). El método real `list_pagospolizas_filtro_paginados` (**count≈2279**, la cartera real) solo vive en `CARTERA_ENDPOINT.md`. Migrar es **correctitud + rendimiento** (2.279 vs 53.062).
- **Brecha de datos que bloquea el informe**: `sync.py` mapea solo `vencimiento` y **no** trae `fecha_pago`, `fecha_realizara_pago` (compromiso) ni `edad_cartera` (mora). Sin ellos no se cumple §3 (agenda por compromiso vs. mora) ni el Speech de póliza vencida.
- **Config a modelar**: `sede=1047`, `estadopolizas_selected[]`, `ramos` deben ir a `tenant_config` (hoy solo están en el `.md`).
- **Incógnita abierta**: falta confirmar el `tipo` para "próximos a vencer" (Llamada 1). Mitigación del propio doc: traer todo y filtrar `fecha_pago` localmente (viable a 2.279 filas).

### Voz — BAJO para portar lo vivo, MEDIO-ALTO por escalado
- Twilio + Pipecat + Gemini Live ya funciona, con 8 tools alineadas al informe (`end_call`, `update_debtor`, `send_whatsapp`, `verify_identity`, `escalate`, `get_policy_info`, `search_knowledge`, `notify_payment_claim`).
- **Restricciones de Gemini Live que el micro hereda**: <3s por tool (ya mitigado con despacho directo + ARQ fire-and-forget) y **degradación con >1-2 pipelines por proceso** (`MAX_CONCURRENT_CALLS=5`). El régimen (~30/día) entra holgado, pero la **jornada de arranque (~250/día × 2 días) exige escalado horizontal real**; con un solo uvicorn no se evacúa la cartera.

### Contrato REST WhatsApp — MEDIO en código, **INCERTIDUMBRE ALTA** (ruta crítica)
- **No existe nada**: `escalate` es 100% interno (flip de estado + evento WS a un dashboard). No hay `POST /case/handoff` saliente ni endpoints entrantes.
- **Conflicto de responsabilidad a resolver**: hoy la voz **envía WhatsApp ella misma** vía Meta Graph API (`send_whatsapp`→ARQ→`whatsapp_sender.py`), lo que **solapa** el mandato de `landa-agent-service`. En el micro DPG limpio esto debe convertirse en un **handoff REST**, no un emisor interno duplicado. Es refactor + decisión de arquitectura.
- **Bloqueo externo**: `HANDOFF.md` L29-34 → `landa-agent-service` está en Fase 4/8, **Fase 6 (integración) no ha empezado**. El contrato (payloads, auth inter-servicio, idempotencia, y el sentido inverso "ya-pagó/comprobante-validado → detener llamadas") hay que **co-diseñarlo**.

---

## 6. Arquitectura propuesta y fasing

Arquitectura objetivo: microservicio backend-only FastAPI + Motor/Mongo (DB propia, mismo cluster admisible) + APScheduler propio + Pipecat/Gemini/Twilio, desplegado en Railway (Dockerfile recortado, sin `npm run build` ni base Playwright), simétrico a `landa-agent-service`.

| Fase | Contenido | Tamaño |
|---|---|---|
| **Fase 0 — Carve-out del esqueleto** | Nuevo repo/servicio; copiar `backend/cobranza` + `backend/softseguros` + `routes/debtors.py`; `db.py` local (get_db de 3 líneas); `auth.py` (81 líneas) o API-key; **copiar bloque de índices de `debtors` (init_db L72-143)**; `AsyncIOScheduler` propio; **migrar intactos** el hack de SSL-context cache y el warmup de Gemini (`main.py:84-121`) o la latencia sube ~1.5s; sembrar tenant DPG; secretos. | **Pequeño-Mediano (~3-5 días)** |
| **Fase 1 — Simplificación single-tenant** | Colapsar `tenant_config` a config estática (sede 1047, estados, ramos, timings, persona); **eliminar** `config_cache.py` (Redis TTL) + gating por módulo + `tenant_admin`; **cablear** `list_pagospolizas_filtro_paginados` en adapter/sync; **borrar** stacks Vapi + Assembly AI. | **Pequeño (~1-2 días)** |
| **Fases 2..N — Lógica de negocio DPG** *(bloque dominante, ortogonal a la extracción)* | Reescritura del scheduler (días hábiles, tope 3, corrimiento fin de semana, jornada de arranque, cupo diario); selector de 4 speeches + extender modelo de deudor (fecha_pago/fecha_compromiso separadas, ramo/riesgo/compañía/nº cuota/modalidad, enum de estados); horarios DPG; 5 alertas tipadas + colas explícitas (pre-vuelo, reagendados, link/cupón); reportes diario 1pm/semanal; **contrato REST bidireccional** (bloqueado por landa-agent-service). | **GRANDE** |

**Lección de esfuerzo:** la SEPARACIÓN es barata y de bajo riesgo; el costo y el riesgo reales están en el **motor de voz (latencia/escalado)** y en el **volumen de lógica de negocio**, no en dividir el monolito.

---

## 7. Microservicio dedicado VS perfil de config en el monolito — recomendación

Este es el verdadero punto de decisión, y las evaluaciones chocan aquí.

| | Micro dedicado single-tenant | Perfil/tenant DPG en el monolito |
|---|---|---|
| Costo de separación | Bajo (Fase 0-1, ~4-7 días) — coupling superficial | Cero |
| Reutiliza motor multi-tenant | No (lo descarta) | Sí (`tenant_config`, Pinecone, personas) |
| Aísla flujo de dinero real del tren de releases de otro producto (prospección B2B) | **Sí** | No (blast radius compartido) |
| Simetría con `landa-agent-service` (ya es micro single-tenant DPG) | **Sí, coherente** | Asimétrico |
| Superficie de ops/on-call | 3er servicio para 1 cliente | Sin nuevo servicio |
| Reversibilidad si entra 2º cliente de voz | Hay que re-generalizar | El motor ya es multi-tenant |
| Lógica de negocio del gap (§1-7) | **Idéntica** | **Idéntica** |

**Recomendación decisiva:** proceder con el **microservicio dedicado**, pero haciendo la **carve-out barata PRIMERO (Fase 0-1) y construyendo las features DPG ya dentro del micro** — nunca al revés (construirlas en el monolito y extraer después = doble gasto). El argumento decisivo no es técnico-de-costo (la separación es trivial) sino arquitectónico: (1) `landa-agent-service` **ya es** un micro single-tenant DPG por diseño, así que un compañero de voz single-tenant es la elección coherente y simétrica; (2) aísla un **marcador de dinero real** (llamadas de cobranza, exposición a Ley 2300/reputación) del tren de releases del producto de prospección B2B que también vive en el monolito.

**Cuándo NO hacerlo (y quedarse con el perfil de config):** si el negocio prevé un **2º cliente de voz** a corto plazo (entonces conviene invertir en el motor multi-tenant que ya existe, no bifurcarlo), o si no se quiere sumar un 3er servicio a la carga de ops. Ambas son posturas defendibles; la de `riesgos-costos` no es incorrecta, es una apuesta distinta sobre el futuro del portafolio.

---

## 8. Riesgos principales y condiciones

### Riesgos
1. **El gap de negocio es el 80% del trabajo y es independiente de la arquitectura.** Extraer no reduce ni un día de las §1-7 del gap. La reescritura del scheduler + selector de speeches no es un ajuste menor.
2. **Contrato REST greenfield Y bloqueado por un tercero** (`landa-agent-service` Fase 6 no iniciada). Bloquea link/cupón, Mensajes 1/2/3 y el sentido inverso "ya-pagó → detener llamadas". Riesgo de cronograma y de retrabajo si el contrato cambia.
3. **Doble emisor de WhatsApp**: si se arrastra el emisor interno Meta Graph al micro DPG, se duplica el canal y se rompe la división acordada. Decisión explícita de retirarlo/redirigirlo a REST.
4. **Escalado de la jornada de arranque**: Gemini Live degrada con >1-2 pipelines/proceso; ~250 llamadas/día exigen workers horizontales, no un uvicorn.
5. **Feed Softseguros frágil y no oficial**: endpoint reverse-engineered del SPA; da 504 sin el scope exacto (sede+estados+ramos); riesgo de ruptura silenciosa si Softseguros cambia el bundle. Y **aún sin cablear**.
6. **Dependencia humana**: `fecha_compromiso` y las exclusiones pre-vuelo se editan A MANO en Softseguros. Datos desactualizados degradan la cobranza sin importar la arquitectura (riesgo Ley 2300).
7. **Divergencia de documentación**: `DPG_GAP_ANALYSIS.md` (rama `feature/dpg-cobranza`) **subestima** lo ya construido en la rama viva (dice OpenAI Realtime cuando es Gemini Live; dice que `sub_agents/`/`whatsapp_notifier.py` no existen cuando sí). **Planificar contra el código vivo, no contra el gap analysis**, o se re-hace trabajo existente.
8. **Deuda de proveedor y código muerto**: Vapi/Telnyx/AssemblyAI montados sin uso; naming `engine='pipecat-telnyx-gemini-live'` sobre transporte Twilio genera logs engañosos.

### Condiciones para que el micro dedicado sea claramente recomendable (estado actual)
- ✅ **Simetría**: `landa-agent-service` ya es micro single-tenant DPG. **Se cumple.**
- ✅ **Aislamiento de flujo crítico de dinero** del tren de releases de otro producto. **Se cumple.**
- ⚠️ **Contrato REST co-diseñado** antes de depender de él. **Pendiente / bloqueado.**
- ⚠️ **DB propia** (mismo cluster admisible) para aislamiento real de datos. **A decidir.**
- ❌ 2º cliente de voz, mandato de compliance/data-residency, o escalado que el monolito no soporte: **ninguno se cumple hoy** — son los argumentos que sostiene `riesgos-costos` para preferir el perfil de config.

---

## 9. Siguiente paso concreto

**Antes de decidir el fasing completo, desbloquear las dos únicas piezas de la ruta crítica que no dependen de la decisión micro-vs-monolito:**

1. **Cablear el endpoint real de cartera** (2-3 días, ya especificado paso a paso en `CARTERA_ENDPOINT.md` §"Integración — próximos pasos"): añadir `list_pagos_filtrados` a `adapter.py`, reapuntar el scan en `sync.py`, mover `sede/estados/ramos` a `tenant_config`, y mapear `fecha_pago` / `fecha_realizara_pago` (compromiso) / `edad_cartera` (mora). Es prerequisito duro de §3 y del Speech de póliza vencida, y mejora el rendimiento (2.279 vs 53K). No depende de la arquitectura.

2. **Convocar el co-diseño del contrato REST voz↔WhatsApp con el equipo de `landa-agent-service`** (payloads de `/case/handoff`, `/cobranza/case/{id}/escalate`, `/cobranza/debtor/{id}/update`; auth inter-servicio; idempotencia; y el sentido inverso comprobante-validado → detener marcación). Es la mayor incógnita y está bloqueada; cuanto antes se destrabe, antes se puede comprometer un cronograma real.

3. **Solo después**, ejecutar la **Fase 0 (carve-out)** contra el **código vivo** (no contra el gap analysis) y construir las features DPG dentro del micro. Como paso 0.1, decidir y **borrar Vapi + Assembly AI** para no inflar la superficie del nuevo servicio.
