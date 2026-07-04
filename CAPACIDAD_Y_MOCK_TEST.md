# Reporte de Capacidad — Bot de Voz "ARIA" / Cobranza DPG Seguros

**Pregunta:** ¿el código/infra aguanta 250-500 llamadas en la ventana de 5h (9-12 / 14-16)?

## 1. Veredicto: AGUANTA CON AJUSTES (hoy, tal cual, NO aguanta el arranque)

- **Operación normal (~30 llamadas/día ≈ 6/h):** aguanta con holgura en 1 solo proceso Railway. Sin problema.
- **Jornada de arranque (250-500 llamadas / 5h = 50-100/h):** **el código actual COLAPSA.** No es una degradación suave: es un *thundering herd*. El scheduler carga TODA la cartera vencida sin límite (`campaign_scheduler.py:196/238` → `to_list(length=None)`) y dispara un `asyncio.create_task(safe_initiate_call(...))` por cada deudor (`:210/:281`) sin semáforo, sin pacing y **sin chequear el cap**. Con la cartera real (mora 90+180+365 = **1.248 deudores**), el primer tick intentaría encolar ~1.248 llamadas de golpe contra un event loop que solo tolera 1-2 pipelines Gemini Live sanos.
- **El techo NO es Twilio ni Gemini ni el costo.** El techo es la **arquitectura mono-proceso** (un solo `uvicorn` sin `--workers`, confirmado en `docker-entrypoint.sh:23`) + la **ausencia total de compuertas de concurrencia** en la ruta automática.
- **Es recuperable sin reescritura:** con ~5 ajustes acotados (semáforo global, pacing, `run_in_executor`, ventana DPG + cupo, y 2-3 workers horizontales con scheduler singleton) el arranque de 50-100/h se vuelve alcanzable. Por eso el veredicto es *con ajustes* y no un *no* rotundo — pero **sin esos ajustes es un fallo garantizado en el minuto 1 del arranque.**

## 2. La matemática de capacidad

**Ley de Little:** `concurrencia = tasa × duración`. Con hold ≈ 3 min (watchdog corta a 240s, `voice_pipecat.py:1007`):

| Escenario | Contestadas/h | Concurrencia necesaria |
|---|---|---|
| Objetivo bajo (250/5h) | 50/h | **2,5 pipelines** |
| Objetivo alto (500/5h) | 100/h | **5,0 pipelines** |
| 500 marcadas, 30% contesta | 30/h | 1,5 pipelines |

**Throughput real por proceso:** `concurrencia × 3600/hold`.
- A la concurrencia **segura documentada en el propio código (1-2 pipelines/proceso)**: **20-40 contestadas/h → máx ~200 en 5h.**
- El cap default de 5 (`voice_router.py:335`) daría 100/h en teoría, **pero 5 ya está 2-3x por encima del umbral de degradación** (`voice_router.py:329-331`: *"degrades visibly with 2+ simultaneous Gemini Live pipelines"*; incidente real de buzón zombie robando CPU en `voice_pipecat.py:1002-1005`). No es concurrencia alcanzable con calidad.

**Conclusión numérica:** un proceso sano rinde ~40/h (200 en 5h). El objetivo de 50-100/h **excede a 1 proceso**. Se necesitan:
- **~2 workers** para sostener 50/h (250 llamadas).
- **~3 workers** para sostener 100/h (500 llamadas).

(Ojo: el binding es la cantidad de pipelines **contestados** simultáneos, no el ritmo de marcado. Si la tasa de contestación es ~30% hay que **marcar ~3x más**, pero la concurrencia que satura es la de las llamadas contestadas.)

## 3. Recursos a tener en cuenta

**Railway / cómputo (el cuello real):**
- Hoy: 1 proceso `uvicorn` sin `--workers` = 1 event loop / 1 core (GIL). RAM ~50-150 MB/pipeline; el costo es CPU de audio en tiempo real (decode µ-law + resample 8k↔24k + relay de 2 WebSockets) serializado en un core. Silero VAD local está **desactivado** (`voice_pipecat.py:316-320`), la VAD la hace Gemini en servidor → footprint local bajo, pero igual serializado.
- Arranque: **2-3 réplicas/workers horizontales**. ⚠️ Escalar réplicas "naïve" **duplica el scheduler** (APScheduler in-process por réplica) → cada réplica llamaría a los mismos deudores N veces. Requiere convertir el scheduler en **singleton / dispatcher único**.

**Twilio:**
- CPS default = **1 CPS por cuenta**; el exceso se **encola** (hasta 24h). El ritmo promedio requerido es 250/18.000s = **0,014 CPS** y 500/18.000s = **0,028 CPS** → 1 CPS es 36-72x el promedio. **Twilio NO es blocker de volumen.** Solo el *burst* del scheduler (que hoy no pacea) se encola.
- Subir a 5-10 CPS es **opcional y solo útil junto con pacing a nivel app**. Elastic SIP Trunking permite hasta 15 CPS self-service por región.
- Costo Colombia móvil $0.0377/min (~3,5 min/llamada, redondeo al minuto, no-contesta = $0): **250 contestadas ≈ $33; 500 ≈ $66; realista al 30% ≈ $17-25/día** + $14/mes de renta DID.

**Gemini Live:**
- Modelo `models/gemini-3.1-flash-live-preview` (`voice_pipecat.py:531`): hoy **preview gratis ($0)**, pero SIN SLA, cuota baja e inestable, sujeto a retiro. **No apto para producción sin plan de migración a GA/pago.**
- **Free tier = ~3 sesiones concurrentes → tope duro de 3 llamadas simultáneas por API**, aunque el proceso aguantara más. **Necesario subir a Tier 1+ (~50 sesiones)** para tener holgura.
- Precio de pago (post-preview): ~$0.07-0.15/llamada de 3-4 min → 250-500 contestadas ≈ **$18-75/día**.

**Costo total externo jornada de arranque:** ~$0-40/día realista, **<$150/día worst-case. El dinero NO es el cuello de botella; lo es la concurrencia/pacing.**

## 4. Cuellos de botella + ajuste para cada uno

| # | Cuello de botella | Ubicación | Ajuste |
|---|---|---|---|
| 1 | **1 solo proceso uvicorn** (sin `--workers`, sin réplicas): todo el event loop para todas las pipelines; degrada a >1-2 | `docker-entrypoint.sh:23`, `railway.toml` | Escalar a **2-3 workers/réplicas horizontales** |
| 2 | **Thundering herd del scheduler**: fan-out ilimitado sin cap ni pacing (1.248 `create_task` en un tick) | `campaign_scheduler.py:196/210/238/281` | **Semáforo global (BoundedSemaphore)** + **token-bucket/sleep** + batch pequeño en vez de fan-out total |
| 3 | **Cap se salta en la ruta automática**: MAX_CONCURRENT_CALLS solo se chequea en el endpoint manual | Cap solo en `voice_router.py:335-343`; ausente en `safe_initiate_call`, `router.py:547-625`, `router.py:506-544` | **Cap global compartido chequeado en las 4 rutas de inicio** (dentro de `safe_initiate_call`) |
| 4 | **`client.calls.create()` SÍNCRONO bloquea el event loop** (~cientos de ms/llamada), congelando pipelines de voz activos | `campaign_scheduler.py:145`, `router.py:607` (contrasta con `voice_router.py:384` que sí usa executor) | Envolver en **`run_in_executor`** como ya se hace en `voice_router.py:384` |
| 5 | **Cap default (5) > umbral seguro (1-2)** | `voice_router.py:335` | Bajar cap **por proceso a ~2** y escalar procesos; mantener cap **global** |
| 6 | **Ventana operativa DPG (9-12/14-16, 5h) NO existe en código** — solo Ley 2300 (L-V 7-19) | `call_scheduler.py:40-54` | Implementar **gate de ventana DPG** + **cupo horario/diario global** para repartir el arranque en la franja |
| 7 | **Escalado horizontal duplica el scheduler** (APScheduler in-process por réplica → deudores llamados N veces) | APScheduler in-process, `landa/scheduler.py:23` | **Scheduler singleton** o **servicio dispatcher único**; los voice-workers solo atienden WS entrantes |
| 8 | **Gemini Free tier = 3 sesiones** (tope duro de 3 simultáneas) | Config API | **Subir a Tier 1+** y salir de preview |
| 9 | **Tick de 60 min**: si se añade cap pero se mantiene el tick, solo drenan ~5 llamadas/h (resto se resetea a pendiente) | `campaign_scheduler.py:355-375` | **Tick cada ~2-3 min** o worker pool para drenar 500 al ritmo objetivo |

## 5. PLAN DE PRUEBA MOCK

**Objetivo:** demostrar el colapso del *thundering herd* y validar los fixes **sin gastar en Twilio/Gemini ni tocar la cartera real.**

### 5.1 Qué mockear
- Crear **`cobranza/mock_voice.py`** que parchee `twilio.rest.Client` → **`FakeTwilioClient`** (usado por `campaign_scheduler.py:145` y `voice_router.py:346`).
- `FakeTwilioClient.calls.create()`: devuelve sid `CAmock<uuid>`, **NO disca**, y lanza `asyncio.create_task(fake_call_lifecycle(sid, debtor_id))`.
- `fake_call_lifecycle`: `await asyncio.sleep(random.uniform(60,240))`; sortea outcome ponderado `{no_contesta ~50%, contactado ~35%, promesa_de_pago ~15%}`; arma un **`CallResult` sintético** (duration/turns coherentes) y llama a la función **REAL `_process_call_ended`** (`voice_router.py:229-277`, no reimplementar); luego `db.cobranza_calls_in_progress.delete_one` (espeja `voice_router.py:220`).
- Activar con **`COBRANZA_MOCK_MODE=true`** y **`MONGODB_DB=hive_office_loadtest`** (DB desechable, **nunca la cartera real**).

### 5.2 Cómo inyectar 250-500 deudores
- **`scripts/loadtest_seed.py`**: borra `{loadtest:True}` previos e inserta **N=500** deudores past-due (`vencimiento < now` para que `post_vencimiento_job` los capture), `estado` pendiente/sin_contacto, `intentos=0`, `max_intentos=5`, `telefono=+57300000XXXX`, `ultimo_contacto_fecha=None`, `is_test=True`, `loadtest=True`.
- Sembrar también `cobranza_config(user_id)` (frecuencia_dias) y `company_voice(cobranza_enabled=True)` si se prueba el endpoint manual.
- Opción realista: **espejar el envejecimiento real** mora90=162 / mora180=383 / mora365=703.

### 5.3 Qué medir (sampler async cada 1s sobre la DB loadtest)
- **PICO concurrente** = `count_documents({started_at >= now-10min})`.
- **RESPETO DEL CAP** = pico vs `MAX_CONCURRENT_CALLS`.
- **THROUGHPUT** = entradas nuevas en `historial_llamadas`/min → extrapolar a llamadas/hora.
- **ERRORES** = deudores reseteados a `pendiente` por el except de `safe_initiate_call` + atascados en `llamando` rescatados por `rescue_job`.
- **ESTADO FINAL** = agregación `db.debtors` por estado.
- **STARVATION** = jitter del propio sampler (si el loop de 1s deriva a >2s → event loop saturado por demasiados `create_task`).
- **VENTANA** = correr una variante con el reloj fuera de Ley 2300 y **afirmar 0 llamadas**.

### 5.4 Criterios PASA/FALLA (burst de 500, MAX_CONCURRENT_CALLS=5)
**PASA si:** pico ≤ cap+1 · 0 llamadas fuera de ventana · 0 deudor contactado >1x/día · 0 atascados en `llamando` al final (tras rescue) · todos en estado válido con `intentos ≤ max_intentos` · error <1% · throughput ≥ 50/h · jitter <2s.

**FALLA ESPERADA con el código ACTUAL:** el pico se dispara a **~500 (no ~5)** porque el scheduler no aplica el cap. **El mock debe demostrar esto** y forzar el fix (semáforo/pool o cap dentro de `safe_initiate_call` + tick más frecuente). Repetir el mock tras el fix y confirmar pico ≤ cap y throughput ≥ objetivo.

### 5.5 Smoke tests reales mínimos (aparte del mock, a números propios)
- **`scripts/test_call_aria.py`** (local, 1 llamada real → valida STT/TTS/Gemini/prompt/end_call).
- **`scripts/test_call_prod.py`** (prod Railway, 1 llamada → valida red/Twilio media stream/latencia). Ambos ya clonan un deudor real, ponen `is_test`, mintean JWT y hacen POST a `/call/initiate-v2`.
- **AÑADIR** un smoke de **2 llamadas reales simultáneas a 2 números propios** para **confirmar empíricamente la degradación de Gemini con 2 pipelines** y calibrar la concurrencia segura por proceso. Verificar: answered→contactado, transcript y recording guardados, no-answer→sin_contacto.

## 6. Recomendación de siguiente paso

**Orden decisivo:**

1. **Primero, correr el MOCK** (`mock_voice.py` + `loadtest_seed.py` + sampler). Es barato ($0), no toca Twilio/Gemini ni la cartera real, y **prueba el colapso del thundering herd** dándote una línea base cuantitativa. Es la evidencia que justifica los fixes.
2. **Aplicar los fixes en este orden de prioridad (todos acotados, sin reescritura):**
   1. Semáforo/cap **global** dentro de `safe_initiate_call` + las 4 rutas de inicio.
   2. `run_in_executor` en los `calls.create()` del scheduler y de "llamar ahora".
   3. Pacing (token-bucket + sleep) + **tick de ~2-3 min**.
   4. **Ventana DPG (9-12/14-16) + cupo horario/diario global.**
   5. Escalado a **2-3 workers** con **scheduler singleton/dispatcher único**.
   6. **Gemini Tier 1+** (salir de preview).
3. **Re-correr el mock** y confirmar pico ≤ cap, throughput ≥ 50-100/h, jitter <2s, 0 fuera de ventana.
4. **Smoke real de 2 llamadas simultáneas** para calibrar la concurrencia segura por proceso (¿1 o 2?) y ajustar el cap por proceso.
5. **Piloto en vivo limitado** (30-50 marcados dentro de la ventana DPG) antes de soltar el arranque completo de 250-500.

**No salir a producción con el arranque hasta que el mock demuestre pico ≤ cap.** Hoy el sistema aguanta la operación normal (30/día) pero **colapsaría en el primer tick del arranque**; los ajustes son claros, acotados y verificables con el mock antes de gastar un solo peso en llamadas reales.