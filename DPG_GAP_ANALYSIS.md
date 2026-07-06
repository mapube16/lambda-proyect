# Gap Analysis — Informe DPG (ARIA) vs Fase 17 construida

> **Propósito:** comparar la spec funcional del bot de cobranza DPG (`INFORME TÉCNICO BOT COBRANZA CON CORRECCIONES.docx`) contra lo que la Fase 17 (`voice-cobranza-agent`) realmente construyó en el código. **No modifica el roadmap.** Insumo para decidir si se abre una Fase 18 de especialización DPG.
>
> **Rama:** `feature/dpg-cobranza` (desde `master`) · **Fecha:** 2026-07-03
> **Fuentes:** informe técnico DPG · `.planning/phases/17-.../17-CONTEXT.md` · `.planning/ROADMAP.md` · lectura directa de `backend/cobranza/`.

---

## TL;DR

La Fase 17 construyó un **motor de cobranza de voz genérico multi-tenant** (Pipecat + Twilio + OpenAI Realtime, con un guión configurable de 4 secciones y cumplimiento Ley 2300). El informe DPG describe un **bot específico (ARIA)** con reglas de negocio mucho más rígidas y detalladas. La mayoría de las decisiones del informe **no se pueden cumplir hoy sin código nuevo**: la secuencia de 3 intentos, los 4 speeches diferenciados, los horarios DPG, el reagendamiento, las alertas al equipo, los reportes y el puente WhatsApp **no existen o están hardcodeados con valores distintos**.

**Veredicto de encaje:** el informe es una **especialización sobre el motor genérico**, no un ajuste menor. Confirma el "siguiente paso NO iniciado" del handoff.

---

## Leyenda

- ✅ **EXISTE** — cumple el requisito del informe tal cual.
- 🟡 **PARCIAL** — hay base reutilizable, pero con valores/forma distintos a lo que pide DPG.
- ❌ **FALTA** — no existe; es código nuevo.
- 🔴 **CONFLICTO** — existe algo que *contradice* la spec DPG y habría que cambiar.

---

## 1. Secuencia de contacto (3 intentos)

| Requisito informe | Estado F17 | Gap |
|---|---|---|
| Máx **3** intentos: L1 día hábil −1, L2 día vencimiento, L3 +2 días hábiles | 🔴 CONFLICTO | Default **5** intentos (`debtor_crud.py`, `max_intentos`). Offsets distintos: pre-venc **3 días** hardcodeado (`campaign_scheduler.py:90`), post-venc cada `frecuencia_dias` (1-3). No hay concepto de "día hábil −1". |
| Reagendamiento reemplaza el siguiente intento | ❌ FALTA | No hay campo `reagendado_para`, ni herramienta `reagendar`. `get_next_allowed_slot()` existe pero es **código muerto** (`call_scheduler.py:73`, sin callers). El prompt "ofrece llamar otro día" solo cuelga, no persiste nada. |
| Vencimiento en sáb/dom/lun → primera llamada el viernes anterior | ❌ FALTA | No hay lógica de corrimiento por fin de semana. |
| Consultar estado de póliza antes de cada contacto | 🟡 PARCIAL | El scheduler consulta Mongo, pero no re-consulta Softseguros ni recalcula días de mora en vivo. |

**Trabajo:** reescribir el scheduler para offsets en **días hábiles** relativos al vencimiento, tope duro de 3 intentos DPG, corrimiento de fin de semana, y un modelo de intentos programados explícito (no "cada N días").

---

## 2. Speeches diferenciados (§9)

| Requisito informe | Estado F17 | Gap |
|---|---|---|
| **4 guiones distintos**: L1 no vencida · L2 no vencida (día venc.) · L3 vencida (# días mora) · entrante/devolución | 🔴 CONFLICTO | **Un solo speech.** El guión de 4 *secciones* de la Queen (`cobranza_queen.py:43`) **lo ignora el motor vivo**: Pipecat usa un prompt monolítico hardcodeado ("Camila", `voice_pipecat.py:145-202`). No diferencia por estado de póliza. |
| Interpolar {Nombre}, {Cuota}, {Ramo}, {Riesgo}, {Compañía}, modalidad de pago, {Valor} | 🟡 PARCIAL | Solo interpola `nombre`, `monto`, `vencimiento`. **No existe** ramo/riesgo/compañía/nº cuota/modalidad en el modelo (viven a lo sumo en `notas`). |
| Ramas: link / cupón / ya-pagó / consulta / reagendar | 🟡 PARCIAL | El prompt sugiere ofrecer pago, pero no hay herramientas para "solicitó link", "solicitó cupón" como eventos. |
| Speech de llamada entrante (cliente devuelve la llamada) | ❌ FALTA | No hay flujo inbound diferenciado. |

**Trabajo:** modelar los 4 speeches como plantillas seleccionables por estado, extender el modelo de deudor con los campos de póliza, y darle al motor Pipecat un selector de guión (hoy ignora la estrategia).

---

## 3. Modelo de datos del deudor

| Requisito informe | Estado F17 | Gap |
|---|---|---|
| `fecha_pago` (vencimiento real → días mora) **vs** `fecha_compromiso` (agenda de llamadas) | 🔴 CONFLICTO | Un solo campo `vencimiento`. `fecha_promesa` es ad-hoc y **el scheduler no la usa** (`webhooks.py:75`). |
| Datos de póliza: ramo, riesgo, compañía, nº cuota, nº total cuotas, modalidad, financiera | ❌ FALTA | Ninguno existe en `debtors`. |
| Estados del informe (implícitos): pendiente→llamando→promesa→pagado→sin_contacto | 🟡 PARCIAL | Hay ~10 estados, pero **sin enum central** y con "terminales" duplicados/inconsistentes (`webhooks.py:29` vs `voice_router.py:23`). Deuda técnica del pivote Vapi→Pipecat. |

**Trabajo:** separar `fecha_pago`/`fecha_compromiso`, añadir bloque de datos de póliza, y centralizar el enum de estados.

---

## 4. Horarios y jornada

| Requisito informe | Estado F17 | Gap |
|---|---|---|
| Franjas DPG: **9–12 y 14–16, solo L–V** | 🔴 CONFLICTO | Hardcodeado a **Ley 2300** (L–V 7–19, Sáb 8–15) en `call_scheduler.py:40`. Más amplio y con sábado. No configurable. |
| Distribución de arranque 9/10/11am, ~30 llamadas/día | ❌ FALTA | No hay distribución por franjas ni cupo diario. |
| **Jornada de arranque** (2 días, ~250/día, evacuar cartera vencida, orden cronológico por antigüedad) | ❌ FALTA | No existe modo "arranque". El scheduler es puramente incremental. |
| Excepción día 1 (venc. mismo día / venc. día siguiente) | ❌ FALTA | — |
| Festivos | 🟡 PARCIAL | Set hardcodeado **solo 2026** (`call_scheduler.py:17`); se rompe en 2027. |

**Trabajo:** horarios configurables por tenant (franjas), cupo diario con distribución, y un modo "jornada de arranque" con priorización cronológica.

---

## 5. Alertas al equipo y colas pendientes (§7)

| Requisito informe | Estado F17 | Gap |
|---|---|---|
| Alertas: solicitud de asesor, interés en otros productos, ya-pagó a validar, solicitud link/cupón, no-desea-llamadas, número equivocado, fecha estimada de pago, no-contactado | 🟡/❌ | Escalación existe **solo como flip de estado** (`escalado=True`) + evento WS al dashboard del dueño (`webhooks.py:243`). **No hay** notificación real al equipo, ni email, ni las categorías específicas del informe. |
| Colas pendientes explícitas (revisión pre-vuelo diaria, link/cupón por enviar, comprobantes por validar) | ❌ FALTA | No modeladas como datos. Se perderían como alertas efímeras. |
| Solicitud link/cupón con payload (nombre, tel, póliza, tipo, fecha/hora) → envío manual | ❌ FALTA | No existe evento ni registro estructurado. |

**Trabajo:** modelar las colas como colecciones/estados explícitos + un canal de notificación real al equipo (esto conecta con el punto 8).

---

## 6. Puente REST hacia `landa-agent-service` (WhatsApp)

| Requisito handoff/informe | Estado F17 | Gap |
|---|---|---|
| `POST /case/handoff`, `POST /cobranza/case/{id}/escalate`, `POST /cobranza/debtor/{id}/update` | ❌ FALTA | No existen. Único update es CRUD genérico `PATCH /api/cobranza/debtors/{id}`. |
| Stub muerto `whatsapp_notifier.py` a reemplazar | ⚠️ N/A | **No existe** ese archivo ni `sub_agents/` en esta rama (el handoff describía otro estado de repo). |
| Cliente HTTP saliente a WhatsApp | ❌ FALTA | Ningún `httpx` de cobranza sale hacia landa-agent-service (solo proxy de grabaciones Twilio y ElevenLabs). |

**Trabajo:** definir e implementar el contrato REST bidireccional voz↔WhatsApp. **Ojo:** el `landa-agent-service` aún no empezó su Fase 6 de integración, así que el contrato hay que co-diseñarlo.

---

## 7. Reportes (§12)

| Requisito informe | Estado F17 | Gap |
|---|---|---|
| Reporte diario 1pm (programadas, realizadas, contactadas, efectividad, link/cupón, ya-pagó, comprobantes, reagendos, no-más-llamadas, escalados+motivo, consultas top, incidencias) | ❌ FALTA | No hay agregaciones ni endpoint de reportes. Solo listado crudo `GET /debtors`. |
| Reporte semanal consolidado con tendencias | ❌ FALTA | — |

**Trabajo:** capa de agregación + job de reporte diario/semanal.

---

## 8. Capacidades de consulta / WhatsApp / menú (§5, §8, §10, §11)

**Responsabilidad de `landa-agent-service`, NO de este repo** (según división acordada en el handoff): Q&A de pólizas, validación de comprobantes, menú WhatsApp, 8 mensajes, tabla de escalación §11. Se listan aquí solo para trazabilidad — **no son gap de la Fase 17**.

---

## 9. Deuda técnica relevante (a limpiar antes o durante)

- **Stack Vapi muerto** (`vapi_client.py`, `webhooks.py`): montado pero sin callers. El campo `vapi_call_id` guarda un Twilio `call_sid`. Decidir: ¿borrar o revivir? (El informe no exige Vapi.)
- **Stack orchestrator/TTS-adapter/Claude/AssemblyAI muerto** (`voice_orchestrator.py` termina en pseudocódigo comentado).
- **Estados terminales duplicados** en dos archivos.
- **Festivos solo 2026.**

---

## Resumen de esfuerzo

| # | Área | Veredicto | Tamaño |
|---|------|-----------|--------|
| 1 | Secuencia 3 intentos + reagendamiento | 🔴/❌ | Grande |
| 2 | 4 speeches diferenciados | 🔴 | Grande |
| 3 | Modelo deudor (fechas + póliza + enum) | 🔴/❌ | Mediano |
| 4 | Horarios DPG + jornada arranque | 🔴/❌ | Grande |
| 5 | Alertas + colas pendientes | 🟡/❌ | Mediano |
| 6 | Puente REST WhatsApp | ❌ | Mediano (bloqueado por landa-agent-service) |
| 7 | Reportes diario/semanal | ❌ | Mediano |
| 9 | Limpieza deuda técnica | 🟡 | Chico |

**Reutilizable tal cual:** onboarding conversacional (Queen), CRUD/CSV de deudores, cumplimiento horario (como patrón), WebSocket real-time, motor de voz Pipecat vivo.

---

## Decisiones abiertas (para cuando se planee)

1. **¿Multi-tenant configurable o DPG hardcodeado?** El informe es 100% DPG. ¿Se parametriza el motor genérico (mejor a largo plazo, más trabajo) o se hace un perfil DPG rígido?
2. **¿Vapi se borra?** No lo pide el informe y está muerto. Recomendación: borrarlo para bajar deuda.
3. **Contrato REST voz↔WhatsApp:** hay que co-diseñarlo con `landa-agent-service` (su Fase 6 no empezó).
4. **Franja/jornada de arranque:** ¿modo temporal de 2 días activable por el staff, o script one-shot?

---

*Documento de análisis. No commitea cambios al roadmap ni al código de la Fase 17.*
