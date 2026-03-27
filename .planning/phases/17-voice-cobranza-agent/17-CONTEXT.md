# Phase 17: Voice Cobranza Agent — Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Vertical completo de cobranza de voz: el usuario sube su cartera de deudores (CSV o manual), configura la estrategia via onboarding conversacional, y el sistema ejecuta llamadas outbound automatizadas via Vapi — con recordatorios pre-vencimiento y cobro post-vencimiento. El dashboard muestra estado, transcripts, grabaciones e historial completo de cada deudor en tiempo real.

**Fuera de scope:** integración con CRMs externos, pagos en línea, WhatsApp de cobranza (fase futura).

</domain>

<decisions>
## Implementation Decisions

### Guión de llamadas

- **Configurabilidad:** Tono + frases clave. La Queen propone el guión completo; el usuario puede editar 4 secciones: saludo inicial, propuesta de pago, manejo de objeciones y despedida/cierre.
- **Identidad del agente:** El agente siempre se identifica con el nombre de la empresa del cliente (tomado del perfil del cliente en Landa). Nunca usa nombre genérico.
- **Escalación:** Si el deudor hace una pregunta que el agente no puede manejar, el agente dice "voy a comunicarle con un asesor", termina la llamada y deja un flag `escalado: true` en el deudor para que el usuario haga seguimiento humano.

### Lógica de campaña (automática)

- **Pre-vencimiento:** 1 llamada de recordatorio automática 3 días antes del vencimiento.
- **Post-vencimiento:** Llamadas periódicas con frecuencia configurable por el usuario en el onboarding (opciones: cada 1, 2 o 3 días hábiles).
- **Límite de intentos:** El usuario configura el máximo de intentos fallidos (default: 5). Al alcanzarlo, el deudor pasa a estado `agotado` y el sistema deja de llamar.
- **Cumplimiento Ley 2300:** Todas las llamadas (automáticas y manuales) se validan contra la ventana horaria permitida (Lun-Vie 7am-7pm, Sáb 8am-3pm hora Colombia) antes de dispararse. El backend rechaza silenciosamente y reagenda si está fuera de horario.
- **Trigger:** Las llamadas se disparan automáticamente — el usuario aprueba la campaña y el sistema trabaja solo. No hay aprobación manual por llamada.

### Dashboard de cobranza

- **Ubicación:** Nueva tab en `ClientDashboard` (mismo patrón que la tab de leads actual).
- **Vista principal:** Tabla con filtros por estado (pendiente / llamando / promesa_de_pago / pagado / agotado / escalado).
- **Columnas:** nombre, monto, vencimiento, estado, último intento.
- **Vista detalle (modal/drawer por deudor):** Toda la información disponible:
  - Estado actual + historial completo de intentos (fecha, duración, resultado de cada llamada)
  - Transcript de cada llamada
  - Player de audio (grabación) por llamada — Vapi guarda las grabaciones
  - Monto prometido + fecha de promesa (si aplica)
  - Notas manuales del usuario
- **Real-time:** El estado de cada deudor se actualiza en tiempo real via WebSocket (existing `ConnectionManager`).

### Gestión manual de deudores

El usuario tiene control total sobre cada deudor:
- **Editar datos:** puede modificar teléfono, monto y fecha de vencimiento después de cargar.
- **Marcar como pagado:** acción manual para deudores que pagaron fuera del sistema (transferencia, efectivo, etc.).
- **Pausar / reactivar:** saca al deudor de la campaña temporalmente (está negociando directo) y lo reactiva después.
- **Eliminar:** elimina permanentemente al deudor del sistema.
- **Notas libres:** campo de texto libre por deudor para contexto manual ("trabaja de 9 a 5", "pide hablar con gerente").
- **Llamar ahora:** botón que dispara una llamada inmediata fuera del ciclo automático — respeta igual los horarios de Ley 2300.

### Ingreso de deudores

- **CSV upload:** campos requeridos: nombre, teléfono, monto, vencimiento. El parser valida formato E164 del teléfono y rechaza filas inválidas con reporte de errores.
- **Manual:** formulario con los mismos 4 campos + campo de notas opcional.
- Ambos modos coexisten — el usuario puede mezclar (sube CSV + agrega algunos manualmente).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `queen_proposal.py` → `generate_proposal()` — reutilizar patrón completo para `cobranza_queen.py` (mismo OpenAI `json_object` response_format, nuevo prompt especializado)
- `ConnectionManager.send_to_user(user_id, event)` en `main.py` — para WebSocket real-time del dashboard
- `asyncio.create_task()` — para disparar llamadas Vapi sin bloquear el HTTP response
- `APScheduler` en `landa/scheduler.py` — para el job de recordatorios pre-vencimiento y rescate de deudores en estado `llamando` (fallback de Vapi end-of-call-report)
- `python-multipart` (ya instalado) — para el CSV `UploadFile` endpoint
- `httpx` (ya en requirements.txt) — para llamadas REST a Vapi si el SDK no alcanza

### Established Patterns

- Onboarding conversacional: usuario describe → Queen propone → usuario aprueba → se guarda en MongoDB. Mismo patrón para estrategia de cobranza.
- MongoDB collections con `user_id` como índice de tenant isolation (igual que `leads`, `campaigns`, `client_knowledge`)
- `asyncio.create_task()` para fire-and-forget async sin bloquear el response (Phase 13/16)
- JWT auth en todos los endpoints de usuario — los webhooks de Vapi NO usan JWT (usan Vapi-Secret header)

### Integration Points

- `main.py` — incluir el nuevo router de cobranza (`backend/cobranza/router.py`)
- `database.py` — agregar CRUD de `debtors` collection y los índices
- `ClientDashboard.tsx` — nueva tab "Cobranza" junto a la tab de leads existente

</code_context>

<specifics>
## Specific Ideas

- El ciclo de llamadas tiene dos fases claras: recordatorio (pre-vencimiento, 1 sola vez) y cobro (post-vencimiento, periódico hasta agotar intentos).
- El usuario configura la frecuencia post-vencimiento en el onboarding junto con el tono y las frases — todo en una sola sesión conversacional.
- El flag `escalado: true` en el deudor es el mecanismo de handover humano — igual que el handover de leads en el agente prospector.
- Los números gratuitos de Vapi (US-only) se usan durante desarrollo/testing. Para producción Colombia: Twilio +57 importado a Vapi Dashboard.

</specifics>

<deferred>
## Deferred Ideas

- Integración con CRMs externos (Salesforce, HubSpot) para importar deudores automáticamente — fase futura
- Canal de cobranza via WhatsApp (mensajes de texto antes de llamar) — fase futura
- Pagos en línea integrados (link de pago en el SMS post-llamada) — fase futura
- Multi-idioma (inglés para mercados fuera de Colombia) — cuando Landa expanda

</deferred>

---

*Phase: 17-voice-cobranza-agent*
*Context gathered: 2026-03-27*
