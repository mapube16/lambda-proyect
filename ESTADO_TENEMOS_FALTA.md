# DPG ARIA — Informe de cumplimiento vs. informe técnico + Plan

> **Estado al 2026-07-04.** Cruce exhaustivo del "INFORME TÉCNICO BOT COBRANZA CON
> CORRECCIONES" (§1–§12) contra el código real de los DOS repos:
> **VOICE** = `lambda-proyect` (este repo, rama `eval/dpg-cobranza-microservice`) y
> **WA** = `landa-agent-service` (WhatsApp, Meta Cloud API, desplegado en Railway).
> Leyenda: ✅ hecho · 🟡 parcial · ❌ falta · 🏷️ decisión de negocio pendiente.

---

## Resumen ejecutivo

| Área | Cobertura | Dónde vive |
|---|---|---|
| Datos y plataforma (ingesta Softseguros, dashboard, config) | **~90%** ✅ | VOICE |
| Canal WhatsApp standalone (Q&A, comprobantes, escalación humana) | **~85%** ✅ | WA (desplegado, CI verde, 419 tests) |
| Infraestructura de llamada (Twilio+Pipecat+Gemini, tools, Ley 2300) | **~70%** 🟡 | VOICE |
| **Secuencia de cobranza del informe (§3–§4)** | **~15%** ❌ | VOICE — **el gap principal** |
| Puente voz↔WhatsApp (Fase 6) | **0%** ❌ (contrato REST ya definido) | AMBOS |
| Alertas tipadas al equipo DPG (§7, §11) | ~25% 🟡 | VOICE |
| Reportes diario/semanal (§12) | ~5% ❌ | VOICE |

**En una frase:** los dos "cuerpos" del sistema (datos+plataforma, y el bot de WhatsApp)
están construidos; lo que falta es el **cerebro de la campaña de voz** (la máquina de
3 intentos del informe), el **puente** entre ambos, y la capa de **alertas/reportes**
que es lo que el equipo de cartera de DPG ve a diario.

---

## PARTE 1 — Cobertura sección por sección del informe

### §1 Identificación del agente

| Requisito | Estado | Detalle |
|---|---|---|
| Nombre ARIA, persona configurable | 🟡 | El prompt de voz es de 3 capas con persona por tenant editable (`prompt_builder.py`, `voice_persona`). Falta **cargar la persona DPG** (nombre ARIA + textos del informe). |
| Número único para llamadas Y WhatsApp | ❌🏷️ | **Hoy son números distintos:** voz sale por un número Twilio; WhatsApp opera en `+1 641 541 6615` (Meta Cloud API directo). Unificarlos requiere registrar el número de voz en Meta (o portar). Decisión de infra pendiente. |
| Links/cupones se envían manual por cartera | ✅ | Alineado por diseño: el bot solo registra la solicitud (guion del engine lo dice explícito). Falta la *alerta tipada* que avisa a cartera (ver §7). |

### §2 Reglas operativas

| Requisito | Estado | Detalle |
|---|---|---|
| Excluir entidades estatales automáticamente | ❌ | No hay campo `tipo_cliente` ni filtro. Softseguros no lo expone directo en la cuota; se puede aproximar por nombre/NIT. 🏷️ Definir criterio con DPG. |
| Exclusión manual desde plataforma Landa | ✅ | Pausar/reactivar por deudor en el dashboard + `pinned` + kill-switch global. |
| Horarios 9–12 / 14–16 L-V | 🟡 | La config existe y es editable desde UI (bloque `horarios`, validado contra Ley 2300). **Pero el motor NO la lee**: los jobs de campaña solo validan la ventana legal amplia (7–19). Gap de cableado. |
| Distribución: ~30 llamadas/día en franjas 9/10/11am | ❌ | Bloque `volumen` existe en config; ningún job lo consume. No hay cupo diario ni pacing por franja. |
| Revisión previa del listado del día por colaborador DPG | ❌ | No existe la vista "programados para hoy" ni gate de aprobación pre-jornada. |
| Gestión desde vencimientos 15-jun-2026 | ✅ | Ventana de ingesta configurada exactamente así (`fecha_desde=2026-06-15`). |
| "San Germán" → decir "Crediestado" | ✅ | `alias_aseguradoras` en tenant_config, aplicado en el mapper del sync. |

### §3 Lógica de contacto y secuencia — **EL GAP PRINCIPAL**

| Requisito | Estado | Detalle |
|---|---|---|
| Vencida desde día 1 de mora | ✅ | `classify_cuota` + `dias_mora`/`edad_cartera` reales por cuota. |
| Compromiso programa la llamada; fecha_pago valida si está vencida | 🟡 | **Los datos ya están** (ambas fechas por cuota, desde el endpoint real). La lógica de *agendar por compromiso* no existe. |
| Consultar estado actual ANTES de cada llamada | ❌ | Ningún re-check pre-llamada contra Softseguros (¿ya pagó? ¿cuántos días de mora hoy?). |
| **3 intentos: día −1 hábil / día 0 / +2 hábiles** | ❌ | Los jobs actuales son genéricos ("recordar 3 días antes", "reintentar después con frecuencia_dias"). No hay máquina de intentos por deudor (`numero_intento`, `proximo_intento_at`). Además `max_intentos` default es 5, el informe pide 3. |
| Speech de vencida si ya venció (en cualquier intento) | ❌ | No hay selección de speech por estado/intento (ver §9). |
| Reagendamiento pedido por el cliente (reemplaza siguiente intento, trazable) | 🟡 | El estado `reagendado` + `fecha_reagendada` existen, **pero la tool `reagendar_llamada` vive en `webhooks.py` = el stack Vapi MUERTO**. El motor vivo (Pipecat) no la tiene, y nada dispara la llamada en la fecha/hora pedida. |
| Vence sáb/dom/lun → llamar el viernes anterior | ❌ | Falta. La base sí está: `call_scheduler.py` ya tiene festivos CO 2026 + días hábiles. |
| Seguimiento +1 día hábil tras cada gestión | ❌ | Sin trigger. (El template Meta `voice_no_answer_followup` ya existe en WA, pendiente de aprobación — la entrega está lista, falta quién la dispare.) |
| **Jornada de arranque** (2 días, ~250/día, prioridad: vencen hoy → mañana → backlog por antigüedad desc) | ❌ | No hay modo arranque. El dashboard ya permite operarlo semi-manual (filtro/orden por mora, agregado hoy). |
| Transición arranque → régimen | ❌ | La ventana de ingesta está **congelada** (15-jun→07-jul): la cola se drena con los pagos pero **no se rellena** con compromisos nuevos. Falta ventana rodante (`fecha_hasta = hoy + N hábiles`). 🏷️ N lo define el cliente. |

### §4 Flujo completo por cliente

| Rama del flujo | Estado | Detalle |
|---|---|---|
| Contesta → speech según estado/intento | 🟡 | Hay UN guion (≈ Llamada 1 + elementos de vencida). Sin variantes por intento. |
| Dice "ya pagué" → WhatsApp pide comprobante | 🟡 | Voz: `notify_payment_claim` registra el claim ✅. El envío del WhatsApp NO ocurre (ver puente). WA: el flujo de comprobante completo **ya está desplegado** (cliente envía → cartera con botones aprueba/rechaza → confirma o escala a Chatwoot) ✅. |
| No contesta L1 → WhatsApp Mensaje 1 (presentación) | 🟡 | WA **ya expone** `POST /case/handoff/no_answer` para esto. VOICE no lo llama: su `whatsapp_notifier.py` es un **stub muerto** (encola un job ARQ que no está registrado en ningún worker). |
| No contesta L3 → alerta a cartera para gestión manual | ❌ | Sin alerta tipada. |
| Cliente devuelve la llamada → speech 9.4 | ❌ | No hay ruta de voz entrante con lookup por caller-id. |
| Llamada interrumpida → registrar + Mensaje 1 + mantener programación | ❌ | Sin manejo específico. |
| Cliente responde el WhatsApp → bot conversa | ✅ | WA desplegado: NLU en lenguaje natural, Q&A de pólizas, seguridad 13 capas. |

### §5 Capacidades de consulta

| Requisito | Estado | Detalle |
|---|---|---|
| En llamada: validar identidad + responder consultas de póliza | 🟡 | Tools reales en el motor vivo: `verify_identity`, `get_policy_info`, `search_knowledge`, datos runtime del deudor + regla anti-invento. Falta cubrir el catálogo administrativo completo (valor asegurado, periodicidad, total de cuotas — varios ya vienen en el doc del deudor tras el sync por cuota). |
| Recordatorio de mora al consultar con pagos pendientes | 🟡 | El engine lo hace en el flujo de cobranza; falta el texto exacto del informe como regla en consulta. |
| Fuera de alcance → registrar + notificar al área responsable | 🟡 | `escalate` existe (estado + evento WS), pero genérico: sin categoría ni enrutamiento a los 8 responsables (§11). |
| En WhatsApp | ✅ | Q&A desplegado. ⚠️ Divergencia: WA identifica por **número de póliza**; el informe pide por **documento**. 🏷️ Unificar criterio (WA ya contempla fallback a `listar_cliente_por_documento`). |

### §7 Alertas en tiempo real

| Alerta | Estado |
|---|---|
| Pide asesor humano | 🟡 voz: `escalate` (estado+WS) · WA: escala a Chatwoot con humano real ✅ |
| Dice que ya pagó → validar | 🟡 voz: `notify_payment_claim` · WA: flujo completo ✅ |
| Solicitud link/cupón (con nombre, tel, póliza, tipo, fecha/hora) | ❌ sin alerta tipada ni cola de validación |
| No desea más llamadas (opt-out, con los 4 campos) | ❌ |
| Número equivocado → validar datos | ❌ |
| Fecha estimada de pago → registrar + notificar | ❌ (el dato cabe en `fecha_reagendada`/compromiso, sin flujo) |
| Interés en otros productos / oportunidad comercial | ❌ |
| No contestó nada (3 intentos) → cartera | ❌ (hoy queda `agotado`, sin notificación) |
| **Canal de entrega de las alertas al equipo** | 🏷️ sin definir: ¿WhatsApp al responsable? ¿dashboard? ¿email? |

### §8 Atención por WhatsApp

| Requisito | Estado | Detalle |
|---|---|---|
| Bot conversacional (menú + lenguaje natural) | ✅ | Desplegado (LangGraph + OpenRouter). |
| Validación identidad → lista de pólizas → detalle | ✅🟡 | Funciona; identifica por póliza (ver §5 🏷️). |
| Comprobantes → cartera valida → confirma/escala | ✅ | Flujo completo con botones y Chatwoot bidireccional. Comprobantes jamás pasan por LLM (seguridad). |
| Acceso del equipo (Chat Landa Tech) | ✅ | Chatwoot self-hosted en Railway. |
| **Ops para producción (lado WA)** | ❌ | Rotar `CHATWOOT_API_KEY` (se filtró) · `APP_ENV=dev→production` · aprobar template Meta `voice_no_answer_followup` · pasar el número de modo test a live (hoy solo 5 números de prueba) · smoke E2E completo (criterios 1, 2, 5) · 3 bugs menores documentados en su repo. |

### §9 Guiones de voz (4 speeches)

| Speech | Estado |
|---|---|
| 9.1 Llamada 1 — no vencida | 🟡 el engine actual cubre ~el esqueleto (presentación, recordatorio con datos reales, link/cupón, ya-pagó, consulta→asesor, reagendar-si-pide) |
| 9.2 Llamada 2 — día del vencimiento | ❌ variante no existe |
| 9.3 Llamada 3 / vencida ("presenta vencimiento de # días") | ❌ variante no existe (el dato `dias_mora` ya está en runtime) |
| 9.4 Llamada entrante / devolución | ❌ no hay inbound |
| Selección automática por intento + estado vencida | ❌ | 
| Textos editables sin deploy | ✅ mecánica lista (`voice_persona` por tenant); falta cargar los 4 textos DPG |

### §10 Mensajes de WhatsApp (plantillas)

Mensajes 6/7 (comprobante recibido/validado): ✅ cubiertos por el flujo WA.
Mensaje 1 (presentación no-contesta): 🟡 template Meta creado, **pendiente aprobación**, y falta que voz lo dispare.
Mensajes 2, 3, link/cupón, menú, 2–5, 8: 🟡/❌ — el bot WA responde en lenguaje natural equivalente, pero las plantillas exactas del informe como templates aprobados + sus **triggers desde voz** no están.

### §11 Routing de consultas fuera de alcance (tabla de 8 áreas)

❌ No existe. `escalate` no clasifica ni enruta a Annie/Paola/Juan Diego/etc.
Es config pura: la tabla (área → responsable → teléfono → keywords) debe vivir en
`tenant_config` y el escalate del motor clasificar contra ella. WA escala a Chatwoot
(genérico) — tampoco enruta por área.

### §12 Reportes y administración

| Requisito | Estado | Detalle |
|---|---|---|
| Reporte diario 1:00 pm (14 métricas) | ❌ | **La materia prima ya se captura** (estados, intentos, historial, llamadas, promesas, montos). Falta la agregación + generación + envío programado. |
| Reporte semanal consolidado | ❌ | Ídem. |
| Colaborador: excluir clientes | ✅ pausar |
| Colaborador: actualizar fecha de compromiso | 🟡 edición en modal existe; falta que re-agende el intento |
| Colaborador: validar solicitudes link/cupón | ❌ requiere la cola de alertas tipadas (§7) |
| Colaborador: revisar comprobantes | ✅ vía flujo WA/Chatwoot |
| Administración de la plataforma por DPG | ✅ config UI completa (ingesta, secuencia, horarios, volumen, carga manual con aviso de arranque) |
| Capacitación | ➖ operativo, no código |

---

## PARTE 2 — Hallazgos estructurales (lo que el cruce destapó)

1. **La secuencia del informe no existe; hay un dialer genérico.** `campaign_scheduler.py`
   dispara "3 días antes" y "reintentos post-vencimiento" — no la máquina −1/0/+2 hábiles
   con speech por intento. Es LA pieza a construir.
2. **La config es editable pero el motor no la consume.** Franjas, volumen y timings ya
   se editan desde UI; los jobs no los leen (solo Ley 2300 hardcoded). Cablear config→motor
   es prerequisito de todo lo operativo.
3. **`whatsapp_notifier.py` (voz) es un stub muerto** — encola un job que ningún worker
   registra. Confirmado por el repo WA. El reemplazo ya está definido en el contrato:
   `POST /case/handoff` a WA. Todo "voz manda WhatsApp" depende de esto (Fase 6).
4. **La única implementación de `reagendar_llamada` vive en el stack Vapi muerto**
   (`webhooks.py`). Portarla al motor Pipecat vivo antes de borrar Vapi.
5. **Bug: los jobs de campaña no filtran `is_active`** → marcarían/llamarían deudores
   archivados por el sync. (El dashboard ya se corrigió; los jobs no.)
6. **La ventana de ingesta es fija** → la cola se evacúa y no se rellena. Ventana rodante
   pendiente (decisión del cliente: N días hacia adelante).
7. **Dos números distintos** (Twilio voz vs Meta WA) vs. el "número único" del informe.
8. **Capacidad:** Gemini free tier = 3 sesiones concurrentes; sin semáforo ni pacing,
   una jornada de 250 llamadas es imposible hoy. (6 fixes identificados en
   `CAPACIDAD_Y_MOCK_TEST.md`.)
9. **Identidad divergente:** informe pide documento; WA identifica por póliza.

---

## PARTE 3 — Plan para cumplir TODO el informe

> Orden recomendado: **F0 → F1 ∥ F2 → piloto → F3 → F4 ∥ F5 → F6 → F7.**
> Tamaños: S = horas · M = 1–3 días · L = ~1 semana.

### F0 — Decisiones de negocio (reunión con DPG — bloquean lo demás) 🏷️
1. Ventana rodante de régimen: ¿cuántos días hacia adelante se cargan compromisos? (propuesta: hoy + 1 hábil)
2. Corte de mora definitivo del arranque (¿15-jun como está?).
3. Canal de entrega de alertas al equipo (WhatsApp al responsable / dashboard / email).
4. Confirmar tabla §11 (responsables y teléfonos vigentes).
5. Número único: ¿registrar el número de voz en Meta, o convivir con dos números en v1?
6. Identidad: ¿documento (informe) o póliza (WA actual)?
7. Gemini tier de pago (3 → 50+ sesiones concurrentes) — necesario para el arranque.
8. Franja definitiva y cupo diario (30/día en 9/10/11am como propone el informe).

### F1 — VOICE: el motor de secuencia del informe (§3, §4, §9) — **la fase grande**
| # | Entregable | Tamaño |
|---|---|---|
| 1.1 | Utilidades día hábil (base ya existe) + regla del viernes | S |
| 1.2 | **Máquina de intentos**: `numero_intento` + `proximo_intento_at` por deudor; dispatcher que reemplaza los jobs genéricos y **lee timings/horarios/volumen del tenant_config** (cierra el gap config→motor). Fixes: `is_active`, max 3 intentos, agendar por compromiso / validar por fecha_pago | L |
| 1.3 | Selección de speech por intento + vencida; cargar los 4 textos DPG en `voice_persona` (ARIA) | M |
| 1.4 | Re-check pre-llamada (re-sync ligero antes de cada franja + verificar `recaudado`/mora del día) | M |
| 1.5 | Reagendar en el motor vivo: tool Pipecat (portada de webhooks.py) + disparo a la fecha/hora pedida + trazabilidad | M |
| 1.6 | **Modo jornada de arranque**: prioridad (vencen hoy → mañana → backlog antigüedad desc), cupo ~250/día, 2 días, apagado automático → régimen | M |
| 1.7 | Ventana rodante post-arranque (`fecha_hasta = hoy + N hábiles` del config) | S |
| 1.8 | Vista "programados para hoy" + exclusión pre-jornada (§2.1) | M |

### F2 — VOICE: capacidad (prerequisito del arranque; paralelizable con F1)
Semáforo global de sesiones (3 → tier pago), pacing por franja según `volumen`,
`run_in_executor` para bloqueantes, scheduler singleton + workers, mock load test,
smoke real y piloto con 5–10 números del equipo. (M)

### F3 — Fase 6: puente voz↔WhatsApp (contrato ya escrito, ambos repos)
| Lado | Entregable |
|---|---|
| VOICE | `POST /cobranza/case/{id}/escalate` (B1) · `POST /cobranza/debtor/{id}/update` (B2) · reemplazar el stub muerto por `POST /case/handoff` a WA · `case_id` UUID al iniciar llamada · copia de modelos + test de contrato |
| WA | `POST /case/handoff` genérico (A) · migración 0004 cases cross-canal · `debtor_flags` en prompt · cliente REST B1/B2 |
| Triggers | no contesta → `/case/handoff/no_answer` (ya existe en WA) · "ya pagué" → handoff Mensaje 2 · +1 hábil → Mensaje 3 (job de seguimiento) · interrumpida → Mensaje 1 |

(M en voz + M en WA; el contrato elimina el riesgo de adivinar.)

### F4 — Alertas tipadas + routing §11 (VOICE)
Colección `alerts` (tipo, payload del informe, estado atendida/no) · tools nuevas del
agente: solicitud link/cupón, opt-out, número equivocado, fecha estimada de pago,
interés comercial · tabla §11 en tenant_config + clasificador en `escalate` · cola de
validación en el dashboard (cierra "validar link/cupón" de §12) · entrega por el canal
decidido en F0. (M/L)

### F5 — Reportes §12 (VOICE)
Agregación diaria de las 14 métricas (data ya capturada) · job 1:00 pm de envío ·
reporte semanal con tendencias/franjas de mayor contacto. (M)

### F6 — Voz entrante / devolución de llamada (§9.4)
Ruta Twilio inbound → lookup caller-id → deudor → speech 9.4; no identificado →
mensaje genérico + registro. (M)

### F7 — Producción y limpieza (continuo)
**VOICE:** borrar stack Vapi/AssemblyAI muerto (tras portar reagendar), enum de estados,
correlation_id, `/health/ready`, mypy CI. **WA (ops):** rotar `CHATWOOT_API_KEY`,
`APP_ENV=production`, aprobar template Meta, número a modo live, smoke E2E completo,
3 bugs menores. **Infra:** número único si F0 lo decide. Carve-out del microservicio al final.

---

## PARTE 4 — Para la reunión de hoy (chuleta)

**Demostrable ya:** cartera real conectada (577 cuotas de la vista "Por cobrar", por
compromiso, como pide §3) · dashboard operativo con filtro/orden por mora · config
completa editable · bot WhatsApp desplegado con validación de comprobantes · motor de
voz que conversa con datos reales y cumple Ley 2300.

**Las 8 decisiones de F0 son del cliente** — sacarlas de la reunión desbloquea F1–F3.

**Compromiso honesto de alcance:** la secuencia automática de 3 intentos, el puente
voz→WhatsApp, alertas y reportes son las 4 piezas por construir; todo lo demás es
cableado sobre lo que ya existe.
