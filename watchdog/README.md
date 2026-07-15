# watchdog

Perro guardián de la operación de cobranza ARIA. Servicio **separado** del
backend (si `lambda-proyect` se cae, este sigue vivo para avisar).

## Qué vigila (cada `CHECK_INTERVAL_SEC`, default 300s)
1. **Salud del backend** — GET a `WATCHDOG_HEALTH_URL`. 2 fallos seguidos →
   alerta "backend caído". Avisa también al recuperarse.
2. **¿Dejó de marcar?** — solo en franja hábil (9-12/14-16 Bogotá, L-V) con
   autocall ON y deudores pendientes: si no hay llamada completada en
   `STALE_CALL_MIN` min → alerta "ARIA no está marcando".

Alertas por **WhatsApp** (baileys-bridge) **+ email** (SMTP), con cooldown.
Expone `/health` propio para que un **UptimeRobot** externo vigile al vigilante
(quién vigila al vigilante).

## Env vars
| Var | Descripción |
|---|---|
| `MONGODB_URI`, `MONGODB_DB` | acceso a la base (mismo que el backend) |
| `WATCHDOG_HEALTH_URL` | `https://my.landatech.org/api/health` |
| `WATCHDOG_ALERT_PHONE` | `+573123528153` |
| `WATCHDOG_ALERT_EMAIL` | correo(s) de respaldo, coma-separados |
| `BAILEYS_BRIDGE_URL`, `BAILEYS_BRIDGE_TOKEN` | canal WhatsApp |
| `SMTP_*` | canal email (Private Email) |
| `DPG_USER_ID` | tenant a vigilar |
| `CHECK_INTERVAL_SEC`, `STALE_CALL_MIN`, `ALERT_COOLDOWN_MIN` | ajustes |

## Fast-follow
Apuntar un **UptimeRobot** gratis al `/health` público de este servicio, así si
el propio watchdog muere, te enteras.
