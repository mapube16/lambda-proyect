# Plan Maestro — Microservicio de Cobranza de Voz (DPG tenant #1)

> Consolida todo lo trabajado: ingesta Softseguros, capacidad/resiliencia, lógica del informe ARIA,
> y la constitución de producción de `ARCHITECTURE.md`. Rama: `eval/dpg-cobranza-microservice`.
> Fecha: 2026-07-04.

---

## 0. Dónde estamos (hecho y verificado)

| # | Entregable | Estado |
|---|---|---|
| ✅ | Endpoint real de cartera crackeado (`list_pagospolizas_filtro_paginados`, `tipo=cartera_por_pagar_compania` + ventana fecha) | `CARTERA_ENDPOINT.md` |
| ✅ | Pipeline config-driven: `_build_cartera_query`, `_pago_to_debtor_doc`, `classify_cuota`, `set_cobranza_config` | verificado vs API real |
| ✅ | Índice `debtors` por cuota (`softseguros_pago_id`) + migración en vivo | commit `18ee8ca` |
| ✅ | **45 deudores reales poblados** en Mongo (config en `tenant_config`, cero hardcode) | prod Atlas |
| ✅ | Análisis de viabilidad (micro dedicado multi-tenant) | `VIABILIDAD_MICROSERVICIO_DPG.md` |
| ✅ | Análisis de capacidad + plan de mock | `CAPACIDAD_Y_MOCK_TEST.md` |
| ⚠️ | La cola real NO son 45 — es **rango de mora**: 90d=162, **180d=383**, 365d=703. Falta decidir el corte. |

---

## 1. Review de `ARCHITECTURE.md` — veredicto: **ADOPTAR como constitución**

Es sólida y **valida lo que ya encontramos**. Mapeo directo regla ↔ hallazgo:

| Regla ARCHITECTURE.md | Nuestro hallazgo (mismo problema) |
|---|---|
| **I.3 Async real** (nada bloqueante en `async`) | `twilio.calls.create()` síncrono bloquea el event loop (`campaign_scheduler.py:145`) → fix `run_in_executor` |
| **I.8 Rate limiting / backpressure** | *Thundering herd*: `create_task` sin límite ni pacing → fix semáforo global |
| **I.11 Paginación obligatoria** | `to_list(length=None)` carga toda la cartera (`campaign_scheduler.py:196`) |
| **I.6 Statelessness / escala horizontal** | APScheduler in-process se duplica por réplica → fix scheduler singleton |
| **I.9 Idempotencia en escrituras** | ya aplicado: clave `(user_id, softseguros_pago_id)` |
| **I.15 Enums, no strings** | `estado` es string libre con "terminales" duplicados → fix enum central |
| **III.1 Anti-duplicación / código muerto** | stacks **Vapi y AssemblyAI muertos** + naming "telnyx" engañoso → **borrar** |

**Adaptaciones a NUESTRA realidad** (el doc está escrito para el stack general LangGraph/MCP/Postgres de Landa; este micro difiere):
- Voz = **Twilio + Pipecat + Gemini Live** (NO Telnyx, NO OpenAI Realtime). El ejemplo "Telnyx sobre Twilio" del doc (§II.6.2) **no aplica** — corregir ese `DECISIONS.md`.
- DB = **Mongo (motor)**, no Postgres. El checkpointer `AsyncPostgresSaver` (§II.4.1) no aplica; sí aplica el patrón "pointer state" y idempotencia de jobs (§II.4.3).
- Este micro **no usa LangGraph** (eso es de `landa-agent-service`). Las evals LLM-as-judge (§II.2.1) aplican a los speeches, no a un grafo.

**Brechas de constitución en el código actual** (deuda a saldar, no bloqueante para el piloto):
estructura en capas (hoy lógica en routers, no `router→service→repo`) · payloads como `dict`/`Any` · sin `correlation_id` · sin `/health/ready` con checks reales · sin `mypy --strict` en CI · CORS por confirmar.

---

## 2. EL PLAN (por fases, en orden de ejecución)

### Fase 0 — Desbloquear decisiones de negocio (tú)
- [ ] **Corte de mora** para la cola: recomendado **180 días (≈383)**. Es 1 valor de config → re-puebla al instante.
- [ ] **Creds Softseguros por-tenant**: las del `.env` dieron 400; confirmar que las encriptadas de DPG (`softseguros_credentials`) son válidas (si no, el cron falla).
- [ ] **Contrato REST voz↔WhatsApp**: co-diseñar con `landa-agent-service` (su Fase 6 no empezó) — **bloquea** link/cupón, Mensajes 1/2/3 y "ya-pagó → detener llamadas".
- [ ] **Gemini**: salir de preview → **Tier 1+** (free tier tope 3 sesiones concurrentes).

### Fase 1 — Ingesta correcta y config editable (casi hecho)
- [ ] **`run_sync` al modelo de cuota** (hoy el populate es one-off; el cron aún usa el camino viejo por póliza) + ventana **por mora** (no fecha fija).
- [ ] **API `GET/PATCH /api/cobranza/config`** (Pydantic anidado, `extra="forbid"`, clamp Ley 2300) — regla I.7/I.12.
- [ ] **UI**: `SoftSegurosSetup` + panel `CobranzaSettings` (editar sede/estados/ramos/mora/horarios/timings/volumen/speeches).

### Fase 2 — Capacidad / resiliencia (los 6 fixes, alineados a la constitución)
- [ ] **Semáforo/cap global** dentro de `safe_initiate_call` en las 4 rutas (I.8).
- [ ] **`run_in_executor`** en los `calls.create()` (I.3).
- [ ] **Pacing** (token-bucket) + **tick 2-3 min** (no 60).
- [ ] **Ventana DPG (9-12/14-16) + cupo** horario/diario (no existe hoy).
- [ ] **2-3 workers** + **scheduler singleton/dispatcher único** (I.6).

### Fase 3 — Probar ANTES de salir (barato, $0)
- [ ] **Mock load test**: `FakeTwilioClient` (no disca, duerme 1-4min, resultado sintético → `_process_call_ended` real) + seed 500 deudores en DB desechable + sampler. **Demuestra el colapso** → valida fixes.
- [ ] **Smoke real**: 2 llamadas simultáneas a números propios → calibrar concurrencia segura por proceso (¿1 o 2 pipelines Gemini?).
- [ ] **Piloto limitado**: 30-50 marcados dentro de la ventana DPG antes del arranque completo.
- **Gate:** no salir al arranque hasta que el mock dé pico ≤ cap y throughput ≥ 50-100/h.

### Fase 4 — Lógica de negocio del informe ARIA (el bloque grande, §1-7 del gap)
- [ ] **Secuencia de 3 intentos** en días hábiles (L1 −1, L2 vencimiento, L3 +2) con offsets desde `tenant_config`.
- [ ] **4 speeches diferenciados** (no vencida / día venc. / vencida#días / entrante) — selector por bucket.
- [ ] **Reagendamiento** ("pago el viernes" → reemplaza siguiente intento) + `fecha_compromiso` viva.
- [ ] **Jornada de arranque** (2 días, cupo alto, orden por mora).
- [ ] **Alertas tipadas + colas explícitas** (asesor, link/cupón, ya-pagó, no-contesta, no-más-llamadas).
- [ ] **Reportes** diario (1pm) + semanal.
- [ ] **Puente REST → WhatsApp** (bloqueado por Fase 0).

### Fase 5 — Endurecer a producción (adoptar la constitución)
- [ ] **Higiene (III):** borrar stacks muertos (Vapi, AssemblyAI, orchestrator), limpiar naming "telnyx", `.gitignore`, docs modulares.
- [ ] **Enum de estados** central (I.15) — quita los "terminales" duplicados.
- [ ] **Observabilidad:** `correlation_id` end-to-end, `/health/ready` real, métricas + **costo por tenant**, logging estructurado.
- [ ] **Seguridad:** audit de secretos, CORS por ambiente, rate limiting en endpoints públicos, `mypy --strict` como gate de CI.
- [ ] **Testing:** integración con camino de error + evals de los 4 speeches (LLM-as-judge).

### Fase 6 — Carve-out al microservicio dedicado (cuando esté probado)
- [ ] Extraer `cobranza/` + `softseguros/` a micro **multi-tenant** dedicado (Fase 0-1 de la viabilidad, ~4-7 días) — separado del monolito de prospección, DPG = tenant #1. Construir las features DPG **dentro** del micro, nunca en el monolito y extraer después.

---

## 3. Orden recomendado y siguiente paso

**Ruta crítica:** Fase 0 (decisiones) ∥ Fase 1 (ingesta) → **Fase 3 mock** (barato, revela el colapso) → Fase 2 (fixes) → re-mock → smoke → piloto → Fase 4 (lógica informe) → Fase 5 (endurecer) → Fase 6 (carve-out).

**Siguiente paso concreto sugerido:** **construir el mock load test (Fase 3)** — es $0, no toca la cartera real, y da la evidencia cuantitativa del colapso que justifica los fixes de la Fase 2. En paralelo, tú desbloqueas la Fase 0 (corte de mora + creds + contrato WhatsApp + Gemini tier).

---

## 4. Decisiones abiertas (tuyas)
1. **Corte de mora** de la cola (90/180/365). → recomendado 180.
2. ¿Arrancamos por el **mock** o por **run_sync + API/UI de config**?
3. Confirmar **creds Softseguros por-tenant** y **tier de Gemini**.
4. Agendar el **co-diseño del contrato REST** con el equipo de WhatsApp.
