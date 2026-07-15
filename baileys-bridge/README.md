# baileys-bridge

Puente **interno** de alertas WhatsApp mientras Meta aprueba la cuenta oficial de DPG.
Un número **desechable** (sin relación con DPG) conectado vía QR (Baileys = WhatsApp Web)
envía las alertas de ARIA al equipo de cartera/asesores.

## Garantías de uso interno
- **Allowlist en código** (`WA_ALLOWED_TO`): solo los números del equipo DPG pueden
  recibir mensajes. Un cliente jamás puede recibir nada de este servicio.
- **Sin URL pública**: solo accesible por la red privada de Railway.
- **Bearer token** (`BAILEYS_BRIDGE_TOKEN`) en cada request.

## Variables de entorno
| Var | Descripción |
|---|---|
| `BAILEYS_BRIDGE_TOKEN` | Token compartido con lambda-proyect |
| `WA_ALLOWED_TO` | Números permitidos, separados por coma (solo equipo DPG) |
| `AUTH_DIR` | Dónde persiste la sesión (default `/data/auth`, volumen Railway) |
| `PORT` | default 8080 |

## Operación
1. **Primer arranque / re-vinculación**: `railway logs --service baileys-bridge` —
   aparece un QR ASCII. En el teléfono del número puente: WhatsApp → Dispositivos
   vinculados → Vincular dispositivo → escanear.
2. La sesión persiste en el volumen — los redeploys NO piden QR de nuevo.
3. Si los logs dicen `loggedOut`: borrar `/data/auth` (o el volumen) y reiniciar
   el servicio para re-escanear.
4. Health: `GET /health` → `{ok, connected, allowlist_size}`.

## Riesgo conocido (aceptado)
Baileys va contra los ToS de WhatsApp → el número puede ser baneado. Mitigación:
número desechable + volumen bajo + solo mensajes al equipo interno que los espera.
Cuando Meta apruebe la cuenta oficial, este servicio se apaga.

## Consumidor
`lambda-proyect/backend/services/notifications.py::send_whatsapp_text` — intenta
este puente primero (`BAILEYS_BRIDGE_URL`), cae a Twilio si no está configurado.
