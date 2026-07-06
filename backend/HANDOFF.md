# HANDOFF — ARIA (bot de cobranza DPG Seguros) — camino a producción

Ubicación de este archivo: `C:\Users\maxim\Desktop\hive-pixel-office\backend\HANDOFF.md`
Repo: `C:\Users\maxim\Desktop\hive-pixel-office` (git privado, remoto `https://github.com/mapube16/lambda-proyect.git`)
Rama de trabajo actual: `eval/dpg-cobranza-microservice` (43 commits sobre `origin/master`, todos ya pusheados)
Fecha de este handoff: 2026-07-05 (domingo). Fecha límite de negocio: **NO llamar antes del miércoles 2026-07-08**.

Este documento es para que otro agente (o el mismo Claude en una sesión nueva, sin memoria de esta conversación)
pueda continuar exactamente donde quedó, sin tener que re-descubrir nada de lo que ya se investigó/decidió.

---

## 1. Qué es esto

"ARIA" es un bot de voz + WhatsApp para gestión de cartera (cobranza) de un cliente de Landa Tech llamado
**DPG Seguros**. Es la primera implementación de cobranza multi-tenant sobre la plataforma compartida de Landa
(el mismo backend también sirve prospección B2B para otros clientes). DPG es el tenant #1.

Documento fuente de todos los requisitos de negocio: **`C:\Users\maxim\Desktop\INFORME TÉCNICO BOT COBRANZA CON
CORRECCIONES.docx`** (también extraído como texto plano en
`C:\Users\maxim\AppData\Local\Temp\claude\C--Users-maxim\9eb87aee-a8d0-4877-8797-670316c8ca74\scratchpad\informe_dpg.txt`
— ojo, esa ruta de scratchpad es de una sesión anterior y puede no existir ya; si no está, releer el .docx
original). Referencias "§N" en todo este documento y en el código (comentarios, docstrings) apuntan a las
secciones de ese informe:
- §2: reglas operativas (exclusión de entidades estatales, horarios)
- §3: lógica de contacto y secuencia de intentos (L1/L2/L3)
- §4: flujo completo de gestión por cliente
- §5: capacidades de consulta del agente (qué puede responder directo vs qué debe escalar)
- §7: alertas en tiempo real al equipo DPG
- §9: guiones de voz exactos (9.1/9.2/9.3 llamadas salientes, 9.4 llamada entrante)
- §11: tabla de ruteo de consultas fuera de alcance a las 8 áreas de DPG

## 2. Stack técnico

- FastAPI + Motor (Mongo async) + APScheduler + Twilio (voz, telefonía) + Meta Cloud API (WhatsApp, vía OTRO
  repo `landa-agent-service`) + Pipecat + **Gemini Live** (`GOOGLE_API_KEY`) para el pipeline de voz en tiempo
  real + React/Vite/TS en el frontend.
- Mongo Atlas, cluster `cluster0.l2lptq3.mongodb.net`, base `hive_office`. `MONGODB_URI` vive en
  `backend/.env` (nunca commiteado, confirmado limpio en historial de git).
- Modelo de datos: una cuota = un documento en `db.debtors` (`softseguros_pago_id`), con `dias_mora` /
  `edad_cartera`, `fecha_compromiso` vs `fecha_pago`.

### Archivos clave (todos bajo `backend/cobranza/` salvo que se indique otra cosa)

| Archivo | Qué hace |
|---|---|
| `voice_pipecat.py` | Pipeline de voz Gemini Live + Twilio. Registra las **12 tools** que el modelo puede invocar (ver §4 abajo). |
| `voice_router.py` | Rutas Twilio: `/webhook` (conecta el stream de audio) + el websocket `/ws/{call_sid}`. **Solo tiene el flujo SALIENTE** — ver hallazgo bloqueante #4 abajo. |
| `prompt_builder.py` | Arma el system prompt real de ARIA (`assemble_system_prompt`, `resolve_persona`). Cero dependencia de pipecat — se puede importar sin instalar el stack de voz, útil para evals. |
| `sequence_engine.py` | Motor de secuencia: `plan_intentos_job` (planifica próxima cita) y el dispatcher que marca. `CALLABLE_ESTADOS = ("pendiente", "sin_contacto", "reagendado")`. Filtro de selección en líneas 238-244 y ~325 (dos queries casi idénticas). |
| `campaign_scheduler.py` | Kill-switch (`is_autocall_enabled`/`set_autocall_enabled`, doc en `db.cobranza_runtime/_id="killswitch"`) + `safe_initiate_call` (el único punto real de marcado: re-chequea kill-switch, `fecha_activacion`, y el ledger de minutos antes de marcar). |
| `entidad_estatal.py` | Clasificador de 2 capas: regex (barato, determinista) → LLM (Gemini primero, OpenRouter fallback) para excluir entidades estatales de la marcación (§2 del informe). Escribe `tipo_entidad`, `no_llamar`, `no_llamar_motivo`, `clasificado_por`. Se dispara desde `softseguros/sync.py` en cada sync nocturno. |
| `alerts.py` | Alertas tipadas (§7) + ruteo por área (§11) contra `tenant_config.cobranza.alertas.routing`. Entrega real por WhatsApp vía `services/notifications.send_whatsapp_text` (Twilio). |
| `reports.py` | Reportes diarios (§12): métricas reales + síntesis cualitativa con `gpt-5.4-nano` sobre transcripts reales, enviado por Resend. |
| `wa_bridge_router.py` | Lado VOZ del puente Fase 6 (entrante desde WhatsApp): `POST /case/{id}/escalate` y `POST /debtor/{id}/update`, protegido con `WA_TO_VOICE_TOKEN` (503 si no está seteado). |
| `minutes.py` | Ledger de minutos del paquete de Landa para DPG (1500 min), consumo idempotente por `call_sid`. |
| `webhooks.py` | **CÓDIGO MUERTO (Vapi legacy)** — sigue montado en `main.py` exponiendo `/api/vapi/*` en vivo aunque nada del flujo real lo llama. Candidato a borrar en el F7 (no urgente). |
| `vapi_client.py`, `voice_orchestrator.py`, `assembly_ai_client.py` | Completamente muertos, sin ningún importer activo. Se pueden borrar sin riesgo. |
| `scripts/eval_aria.py` | **Nuevo esta sesión.** Suite de regresión standalone (no gasta minutos, no hace llamadas reales) con 26 escenarios contra el prompt real. Ver sección 6. |
| `.planning/contracts/lambda-handoff-contract.md` (en el OTRO repo `landa-agent-service`) | Contrato REST congelado de la Fase 6 (bridge bidireccional voz↔WhatsApp). NO tocar ese repo directamente. |

### Las 12 tools que el modelo puede invocar (voice_pipecat.py)
`end_call, send_whatsapp, verify_identity, escalate, get_policy_info, search_knowledge, notify_payment_claim,
reagendar_llamada, solicitar_link_cupon, registrar_no_desea_llamadas, informar_fecha_pago,
registrar_oportunidad_comercial`.

**Nota de seguridad de esta sesión**: existía una 13ª tool, `update_debtor`, invocable libremente por el modelo
sin que el prompt la mencionara nunca, y cuya propia descripción sugería `"contactado"` como valor válido de
`estado` — un valor que NO está en `CALLABLE_ESTADOS` y que podía sacar a un deudor del pool de marcado
prematuramente (antes de que la llamada real terminara). Se **eliminó por completo** (schema, handler,
registro) — cada transición legítima de estado ya tiene su propia tool dedicada. Confirmado por el audit de
esta sesión: sin código colgante, sin otras referencias.

## 3. Reglas de negocio ya confirmadas por el cliente (F0, todas ya aplicadas a la config)

- Ventana rodante = hoy + 1 día hábil.
- Corte de mora = 15-jun-2026, sin cambios.
- Franjas horarias: 9-12 y 14-16, 30 llamadas/día.
- Identidad: "en llamadas siempre validar con nombre del cliente" (aplicado literal en el prompt).
- Canal de alertas: WhatsApp al responsable (no email).
- Tabla §11 de ruteo: usar tal cual (8 áreas, ya sembrada).
- Número: dos números en v1.
- **Fecha de activación (hard gate, dada por el usuario): no marcar ANTES del miércoles 2026-07-08.**
  Confirmado en Mongo: `tenant_configs` (DPG, `user_id=69bcd9bb6e35d53880364535`) →
  `cobranza.volumen.fecha_activacion = "2026-07-08"`. Se chequea en `campaign_scheduler.safe_initiate_call`
  y en `sequence_engine.dispatch_intentos_job` (defensa en profundidad).

## 4. Estado real de la auditoría de "qué falta para salir" (corrida el 2026-07-05, workflow multi-agente)

### 🔴 BLOQUEANTES — pendientes al momento de este handoff

1. **Nada está desplegado todavía.** Railway (proyecto `vigilant-celebration`, entorno `production`, servicio
   único `lambda-proyect` — sirve TODA la plataforma, prospección B2B + DPG cobranza, no hay servicio dedicado)
   despliega automático SOLO desde la rama `master`. La rama `eval/dpg-cobranza-microservice` tiene 43 commits
   sobre `origin/master` (ya pusheados a GitHub), pero master no los tiene. Para salir en vivo hace falta
   **mergear a master y pushear** (dispara el auto-deploy de Railway), o `railway up` directo desde la rama
   (des-sincroniza el deploy del git de master, no recomendado). **Esto afecta a TODOS los tenants del
   servicio compartido — el usuario ya dio luz verde explícita para proceder ("sigue porfa con el deploy y
   demás") en el mensaje que motivó este handoff.**
   - Comando de verificación de estado Railway: `railway status --json` (CLI ya autenticado como
     `m.pulido1@uniandes.edu.co`, `railway whoami` confirma).
   - Deploy actual en master: commit `99ca4b576decea03ca6495a3a198ff980b97cf0d` ("fix deploy in railway").

2. **Cambios sin commitear en el working tree** (al momento de este handoff, de la sesión de eval/fixes):
   - `M backend/cobranza/prompt_builder.py` — fix real: preguntas sobre coberturas de la póliza ESPECÍFICA del
     cliente ahora escalan a `escalate` en vez de responder con `search_knowledge` (el informe §5 exige
     registrar+notificar, no solo contestar con la base de conocimiento genérica).
   - `M backend/cobranza/voice_pipecat.py` — eliminación de la tool `update_debtor` (ver sección 2) +
     descripción de `escalate` ampliada para mencionar explícitamente coberturas/cotizaciones/cancelaciones.
   - `M backend/cobranza/voice_router.py` — comentario corregido (referencia obsoleta a `update_debtor`).
   - `M backend/cobranza/sequence_engine.py` — fix del bloqueante #3 (filtro `tipo_entidad`).
   - `M backend/cobranza/router.py` — fix del hallazgo 4b (`no_llamar` en `llamar_ahora`).
   - `M backend/routers/auth.py` — fix del hallazgo 4c (gate de entorno en `/auth/dev-token`).
   - `?? backend/scripts/eval_aria.py` — nuevo, sin trackear (385 líneas, ver sección 6). Última corrida: 26/26 (100%).
   - `?? backend/HANDOFF.md` — este mismo archivo.
   - **Estado al momento de escribir esto: ya commiteados y pusheados a `origin/eval/dpg-cobranza-microservice`
     (ver el commit más reciente de la rama). Si ves esto y el working tree ya está limpio, este punto está
     resuelto — confirmar con `git log -3` y `git status`.**

3. ~~**92% de deudores de DPG sin clasificar `tipo_entidad`**~~ **RESUELTO esta sesión.** Se agregó
   `"tipo_entidad": {"$ne": None}` a los dos filtros de selección en `sequence_engine.py` (líneas ~241 y
   ~327-330, `plan_intentos_job` y el dispatcher) — ahora ningún deudor sin clasificar es elegible para
   marcado, sin importar si la clasificación LLM llega a tiempo o no. Efecto colateral IMPORTANTE a vigilar:
   con esto, mientras la capa LLM no corra sobre los 573 ambiguos, el pool de marcado real puede quedar en
   CERO (los únicos 49 clasificados hoy son todos "estatal", ya excluidos por `no_llamar`). `run_clasificacion`
   se dispara automáticamente al final de cada sync de Softseguros (`softseguros/sync.py` línea ~909, best
   effort, nunca tumba el sync) usando Gemini (`GOOGLE_API_KEY`, confirmado SET en Railway) con fallback a
   OpenRouter. **Acción pendiente real**: una vez desplegado, forzar un `POST /api/debtors/sync-now` contra
   PRODUCCIÓN (no localhost) para que la clasificación de los 573 corra ya, en vez de esperar al cron nocturno
   — si no, el miércoles puede arrancar sin nadie realmente marcable. Verificar después con la query de conteo
   de la sección 4 de este documento (o repetir el chequeo de Mongo).

4b. **Hallazgo nuevo, RESUELTO esta sesión — `llamar_ahora` (botón manual "llamar ahora" del dashboard) no
   chequeaba `no_llamar` en absoluto.** A diferencia del dispatcher automático, este endpoint
   (`cobranza/router.py:909`) permitía forzar una llamada manual a CUALQUIER deudor por ID, incluyendo uno ya
   confirmado como entidad estatal — sin ningún guardia. Se agregó un chequeo `if debtor.get("no_llamar"):
   raise HTTPException(403, ...)` justo después de cargar el deudor (antes de las validaciones de Ley 2300).
   El informe §2 no da excepción de canal para entidades estatales, así que esto aplica igual a llamadas
   manuales que automáticas.

4c. **Hallazgo nuevo, RESUELTO esta sesión — `/auth/dev-token` sin ningún gate de entorno, vivo en
   producción.** Este endpoint (`routers/auth.py:95`) emite, SIN AUTENTICACIÓN, un token válido de 12 horas
   para la cuenta real de DPG (`dpg.seguros@gmail.com`) — cualquiera con la URL podía impersonar la cuenta
   completa (ver PII de deudores, disparar syncs, desconectar Softseguros, etc.). No tenía ningún chequeo de
   `ENV`. Se descubrió además que **`ENV` nunca había sido seteado en Railway production** — lo que significa
   que OTRO bypass de solo-desarrollo (`llamar_ahora`'s `?test=true`, que salta las validaciones de Ley 2300)
   también llevaba tiempo activo sin querer en producción, ya que `is_dev = os.getenv("ENV", "development")
   != "production"` defaulteaba a `True` sin la variable. Se corrigieron ambas cosas:
   - Se agregó el gate `if os.getenv("ENV", "development") == "production": raise HTTPException(404, ...)`
     al inicio de `dev_token()` en `routers/auth.py`.
   - Se seteó `ENV=production` en Railway (`railway variables --service lambda-proyect --set "ENV=production"`
     — YA APLICADO, confirmado con `railway variables --json`). Efecto: cierra el hueco del dev-token, cierra
     el bypass de Ley 2300 en `llamar_ahora`, y activa logs en formato JSON (`framework/observability/logging.py`)
     — las tres consecuencias son estrictamente positivas, no se identificó ningún otro sitio que lea `ENV`.

4. **Llamadas entrantes se caen en silencio (informe §9.4, no implementado).** `voice_router.py` solo tiene
   UN webhook (`POST /webhook`), documentado como "Twilio calls this when an outbound call connects" — es la
   misma URL que se pasa como `url=` en toda llamada SALIENTE. El websocket handler busca primero
   `db.cobranza_calls_in_progress.find_one({"call_sid": call_sid})`, que solo se llena desde los paths de
   inicio SALIENTE. Si un deudor devuelve la llamada al mismo número (que también es el de WhatsApp), Twilio
   conecta el stream de audio y el código lo cierra de inmediato
   (`websocket.close(1008, ...)`, `voice_router.py` líneas ~225-228) sin correr ningún bot ni resolver al
   deudor por el número `From`. No hay ningún código que arme contexto de deudor a partir del caller ID.
   **No bloquea la marcación saliente en sí, pero es un riesgo real de mala experiencia/queja de cliente ya
   desde la primera semana** (un deudor recién llamado que devuelve la llamada el mismo día se encuentra con
   un colgado abrupto). Pendiente de decidir: construir el entrypoint real, o bloquear explícitamente el
   número a entrantes hasta tenerlo (ej. Twilio Studio Flow simple que diga "en este momento no podemos
   atender su llamada, por favor escríbanos por WhatsApp" en vez de conectar el stream).

5. **Variables del puente WhatsApp↔Voz faltan en Railway producción**: `LAMBDA_PROYECT_BASE_URL` y
   `WA_TO_VOICE_TOKEN` NO existen en `railway variables --service lambda-proyect` (production). Ambos
   routers del puente Fase 6 fallan cerrado (503) sin ellas. (`LAMBDA_PROYECT_INTERNAL_TOKEN` y
   `GOOGLE_API_KEY` sí están seteados.) **`WA_TO_VOICE_TOKEN` tiene que coincidir con el valor configurado del
   lado `landa-agent-service` (el otro repo) — no se puede generar unilateralmente sin coordinar el valor
   entre ambos lados.** `LAMBDA_PROYECT_BASE_URL` es la URL pública donde vive `landa-agent-service` — hay que
   consultarla, no inventarla.

6. **Credenciales reales de Twilio commiteadas y pusheadas** en `backend/WHATSAPP_BOT_READY_TO_TEST.md` líneas
   139-140 (Account SID + Auth Token en texto plano), desde marzo 2026, presentes en el historial de GitHub.
   El usuario aclaró que **el repo es privado**, así que esto baja de urgencia crítica a "hacerlo con calma,
   pero hacerlo": rotar el Auth Token en la consola de Twilio y reemplazar el valor en el doc por un
   placeholder (no hace falta reescribir el historial de git con force-push si el repo es privado y de
   confianza, pero sigue siendo buena práctica rotarlo ya que estuvo expuesto).

### ✅ Ya confirmado en orden (auditoría 2026-07-05)
- Railway: CLI autenticado, proyecto `vigilant-celebration`, 2 servicios (`Redis` + `lambda-proyect`), deploy
  source = `master`, dominio `my.landatech.org`.
- Kill switch: sin override en Mongo, `COBRANZA_AUTOCALL_ENABLED=false` en Railway → deshabilitado por
  defecto (correcto para pre-lanzamiento — **no cambiar esto hasta que el usuario decida activar
  explícitamente**, es independiente de desplegar el código).
- `fecha_activacion=2026-07-08` confirmado en Mongo y respetado por el código.
- `LAMBDA_PROYECT_INTERNAL_TOKEN` y `GOOGLE_API_KEY` sí están en Railway.
- Alertas: `canales=['whatsapp_responsable']` y las 8 áreas de §11 pobladas en `tenant_configs` de DPG.
- Las 12 tools registradas limpio, sin código colgante de `update_debtor`.
- `.env` nunca commiteado (ni root ni backend/), bien cubierto por `.gitignore`.
- Sin TODO/FIXME/HACK real en `backend/cobranza/*.py`.
- Los 43 commits de la rama eval ya están pusheados a `origin/eval/dpg-cobranza-microservice`.

### 🟡 No bloqueante (post-lanzamiento)
- Borrar `webhooks.py` (Vapi legacy, montado pero sin uso real) y los 3 archivos muertos
  (`vapi_client.py`, `voice_orchestrator.py`, `assembly_ai_client.py`) — parte del F7.
- F2 (capacidad/pacing) es solo 2 config estáticos (`MAX_CONCURRENT_CALLS=5`, `llamadas_por_dia=30`) sin
  prueba de carga real detrás. Riesgo bajo con el volumen inicial; agregar load-test si escala.
- PII en logs: `voice_pipecat.py` líneas 140 y 852 loguean nombre completo y teléfono completo del deudor en
  texto plano a nivel INFO. Ya existe el patrón de enmascarado (`phone[:6]+"***"`) en
  `sub_agents/whatsapp_notifier.py` para replicar.
- Docstring desactualizado en `voice_pipecat.py:9` (todavía lista la tool vieja `update_debtor`) — cosmético.
- `RESEND_API_KEY` ausente en Railway — no se encontró uso en el flujo de cobranza revisado, probablemente
  pertenece a otra feature de la plataforma; confirmar antes de asumir que bloquea algo de DPG.
- Rotar la API key de OpenAI que se pegó en texto plano en una sesión de chat anterior (independiente de
  este lanzamiento) — recordatorio pendiente, no verificable programáticamente.

## 5. Estado de git al momento de este handoff

- Rama actual: `eval/dpg-cobranza-microservice`.
- `git rev-list --left-right --count origin/master...eval/dpg-cobranza-microservice` → `0  43` (master no
  tiene nada que la rama no tenga; la rama tiene 43 commits de más, sin divergencia — simple fast-forward
  desde el punto de ramificación).
- Working tree: 3 archivos modificados + 1 nuevo sin trackear (ver bloqueante #2 arriba) — **sin commitear
  al momento de este handoff**.
- Todos los commits ya existentes están pusheados (`0 ahead, 0 behind` contra
  `origin/eval/dpg-cobranza-microservice`).
- Últimos 25 commits sin marcadores WIP/temp — historial limpio.

## 6. Herramienta de evaluación (`backend/scripts/eval_aria.py`)

Construida esta sesión en respuesta a "¿hay alguna forma de hacer regresiones... sin necesidad de hacer las
llamadas?". Es standalone, reusable, NO gasta minutos ni hace llamadas Twilio reales. Usa el prompt REAL
(`prompt_builder.py`, sin dependencia de pipecat) + OpenAI (`gpt-5.4-mini`) como actor de texto que simula ser
ARIA — aproximación honesta a Gemini Live (mismo prompt/tools, canal de audio distinto; el propio docstring
del script documenta esta limitación).

- 26 escenarios cubriendo §3, §4, §5, §7, §9 del informe.
- Grading determinista (tool esperada + palabras que debe/no debe decir), no un LLM-juez.
- Score actual (última corrida limpia): **25/26 (96%)**, el único "fallo" restante es ruido inherente del
  modelo (GPT-4/5 no es 100% determinista ni con `temperature=0`), no un defecto real — confirmado revisando
  el texto a mano.
- Dos hallazgos reales de esta herramienta ya corregidos en el código de producción: la tool `update_debtor`
  insegura (removida) y el ruteo de preguntas de coberturas (corregido en `prompt_builder.py`).
- Uso:
  ```
  cd backend
  python scripts/eval_aria.py            # corre las 26 pruebas
  python scripts/eval_aria.py --verbose  # ver el texto completo de cada respuesta
  python scripts/eval_aria.py --solo C4  # iterar rápido en un caso puntual
  ```
- Requiere `OPENAI_API_KEY` en `backend/.env`.
- Recomendación: correrlo cada vez que se toque `prompt_builder.py` o las tools de `voice_pipecat.py`, ANTES
  de commitear, como regresión.

## 7. Próximos pasos concretos, en orden

1. **Retomar el fix de `entidad_estatal` / `sequence_engine.py`** (bloqueante #3) — decidir e implementar el
   default seguro (excluir de la selección a quien no tenga `tipo_entidad` resuelto), o confirmar que la
   clasificación LLM completará a tiempo antes del miércoles.
2. **Commitear** los 4 archivos pendientes (bloqueante #2) con mensaje claro. Correr
   `python scripts/eval_aria.py` una vez más antes de commitear como último chequeo.
3. **Mergear `eval/dpg-cobranza-microservice` a `master` y pushear** (bloqueante #1) — dispara el auto-deploy
   de Railway del servicio compartido. El usuario ya autorizó esto explícitamente. Verificar el deploy
   después con `railway status --json` / logs.
4. **NO tocar `COBRANZA_AUTOCALL_ENABLED`** en Railway — debe seguir en `false` hasta que el usuario decida
   activarlo explícitamente (independiente de desplegar el código).
5. Decidir sobre las variables faltantes del puente Fase 6 (bloqueante #5) — requiere coordinar con el lado
   `landa-agent-service` para el valor exacto de `WA_TO_VOICE_TOKEN` y la URL de `LAMBDA_PROYECT_BASE_URL`.
6. Decidir sobre llamadas entrantes (bloqueante #4) — mínimo viable: bloquear el número a entrantes con un
   mensaje simple, hasta construir el entrypoint real.
7. Rotar el token de Twilio expuesto en `WHATSAPP_BOT_READY_TO_TEST.md` (bloqueante #6, no urgente por ser
   repo privado, pero pendiente).

## 8. Contexto adicional / preferencias del usuario observadas esta sesión

- El usuario responde rápido y en español coloquial; prefiere que se actúe con autorizaciones amplias ya
  dadas ("construye lo que hace falta") en vez de preguntar por cada detalle menor, pero espera confirmación
  explícita antes de acciones de alto impacto (deploy a producción compartida, force-push, borrar historial
  de git).
- Ya dio autorización explícita para: pushear la rama eval, desplegar en Railway, y ahora ("sigue porfa con
  el deploy y demás, este repo es privado") continuar con el merge/deploy y el resto de bloqueantes.
- Prefiere que se investigue/verifique el estado real (Mongo, Railway, git) en vez de asumir desde memoria de
  conversación — así se construyó el audit de la sección 4.
- Paga el tier de Gemini "antes de salir a producción" — confirmar que esto ya se hizo si depende de eso
  para el `GOOGLE_API_KEY` de Railway (ya confirmado SET, pero no se verificó el tier/cuota).
