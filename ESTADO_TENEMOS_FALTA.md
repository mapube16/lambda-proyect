# DPG Cobranza — Qué TENEMOS y qué FALTA (vs. el informe ARIA)

> Estado al 2026-07-04, rama `eval/dpg-cobranza-microservice`. Mapea cada requisito del
> informe técnico contra lo construido. Leyenda: ✅ hecho · 🟡 parcial · ❌ falta · ➖ fuera de alcance (otro micro).

## Resumen en una línea

**TENEMOS toda la capa de DATOS y PLATAFORMA** (conectar Softseguros, traer la cartera real
en automático, verla enriquecida, y configurarla desde UI). **FALTA el MOTOR de cobranza en sí**
—la secuencia de llamadas del informe— más capacidad, reportes y el puente a WhatsApp.

---

## ✅ Lo que YA tenemos (la base)

| Capacidad | Estado | Detalle |
|---|---|---|
| **Conexión Softseguros por tenant** | ✅ | Credenciales cifradas, auth verificado. |
| **Ingesta automática de la cartera REAL** | ✅ | Endpoint real `list_pagospolizas_filtro_paginados`; sync por **cuota** (una cuota = un deudor), config-driven, con `fecha_pago` (vencimiento) **y** `fecha_realizara_pago` (compromiso) **y** días de mora. Verificado contra API + Mongo. |
| **Sync recurrente diario + carga manual** | ✅ | `run_cartera_sync` (cron diario con soft-delete; carga manual "pinned" que el diario no borra). |
| **Config editable desde UI (cero hardcode)** | ✅ | Sede, ventana de mora, secuencia (offsets/máx intentos), horarios (con tope Ley 2300), cupo, forma de agenda. |
| **Dashboard con deudores reales** | ✅ | Tabla + detalle enriquecido (aseguradora, riesgo, forma de pago, nº cuota, valor, saldo, vencimiento, compromiso, mora). |
| **Datos para el speech** | ✅ | Todos los campos que el §9 pide para interpolar (nombre, cuota, ramo, riesgo, compañía, modalidad, valor, # días de mora). |
| **Kill-switch / pausar / marcar pagado** | ✅ | Controles operativos básicos. |
| **Multi-tenant** | ✅ | DPG = tenant #1; el motor sirve para más corredores. |

---

## ❌ Lo que FALTA (el motor de cobranza)

| Requisito informe | Estado | Qué falta exactamente |
|---|---|---|
| **§3 Secuencia de 3 intentos** | ❌ | El scheduler NO ejecuta aún L1 (día hábil −1) · L2 (día vencimiento) · L3 (+2 días hábiles). Hoy dispara genérico. |
| **§3 Reagendamiento** | ❌ | "Pago el viernes" → reemplaza el siguiente intento. No implementado. |
| **§3 Corrimiento fin de semana** | ❌ | Vence sáb/dom/lun → primera llamada el viernes. Falta. |
| **§3 Jornada de arranque (2 días)** | ❌ | Evacuación de cartera vencida acumulada (~250/día, orden por antigüedad). Falta el modo arranque. |
| **§4 Flujo por cliente** | ❌ | Contesta→speech / no contesta→WhatsApp / seguimiento día hábil. No cableado. |
| **§9 Los 4 speeches diferenciados** | ❌ | No vencida · día venc. · vencida (# días) · entrante. Hoy el motor usa un prompt genérico ("Camila"), no los guiones del informe. |
| **§5 Consulta en llamada** | 🟡 | Existen tools de identidad/póliza en el motor, pero sin cablear a la cuota real. |
| **§7 Alertas tipadas + colas** | ❌ | Asesor, link/cupón, ya-pagó, no-desea-llamadas, número equivocado, fecha estimada. Hoy solo cambia de estado. |
| **§12 Reporte diario (1pm) + semanal** | ❌ | Llamadas programadas/realizadas/contestadas, efectividad, link/cupón, comprobantes, escalados… No existe. |
| **§11 Tabla de escalación (8 áreas)** | ❌ | Routing de consultas fuera de alcance al asesor correcto. Falta. |
| **Capacidad para el arranque** | ❌ | El scheduler colapsaría con 250-500 llamadas (thundering herd). 6 fixes pendientes + workers. |

---

## ➖ Fuera de nuestro alcance (lo cubre `landa-agent-service`, el micro de WhatsApp)

| Requisito | Nota |
|---|---|
| §8 Atención por WhatsApp, §10 los 8 mensajes, menú | Otro microservicio. |
| Validación de comprobantes, envío link/cupón | Cartera/WhatsApp lo maneja. |
| El **contrato REST voz↔WhatsApp** | 🟡 A co-diseñar; su Fase 6 no ha empezado (bloquea link/cupón + "ya-pagó→detener llamadas"). |

---

## Sobre las "2 semanas de evacuación" (tu punto)

El informe define una **jornada de arranque** (§3): los primeros días, ARIA evacúa la **cartera
vencida acumulada desde el 15-jun** (~250/día, orden por antigüedad). Eso es **temporal**. La
**ventana de mora amplia + la carga manual** de Configuración son **para esa evacuación** — no
para el estado normal. Terminada la evacuación, el **sync diario mantiene la cola normal** (~30/día,
mora corta). → La UI de Configuración debe **decirlo explícitamente**.

---

## Traducción para la reunión

- **"Ya conectamos su cartera real y pueden controlar todo desde la plataforma."** ✅ (esto es demo hoy)
- **"El agente que hace las llamadas con la secuencia y los guiones de ustedes — eso es lo que sigue."** (F4)
- **"WhatsApp lo maneja el otro componente; el puente entre ambos se coordina."** (contrato REST)
