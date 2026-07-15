/**
 * baileys-bridge — puente INTERNO de alertas WhatsApp (Baileys = WhatsApp Web).
 *
 * Mientras Meta aprueba la cuenta oficial de DPG: un numero DESECHABLE (sin
 * relacion con DPG) conectado via QR envia las alertas de ARIA al equipo de
 * cartera. SOLO uso interno, garantizado EN CODIGO:
 *   - allowlist de destinatarios (WA_ALLOWED_TO) — cualquier numero fuera de
 *     la lista se rechaza con 403, un cliente jamas puede recibir nada.
 *   - sin URL publica: se despliega solo en la red privada de Railway
 *     (lambda-proyect le pega por http://baileys-bridge.railway.internal).
 *   - bearer token compartido (BAILEYS_BRIDGE_TOKEN) en cada request.
 *
 * Riesgo conocido: Baileys va contra los ToS de WhatsApp — el numero puede ser
 * baneado. Por eso: numero desechable + bajo volumen + solo equipo interno.
 * Cuando Meta apruebe, este servicio se apaga y no queda deuda.
 *
 * Operacion:
 *   - Primer arranque: imprime un QR en los logs (railway logs) — escanear con
 *     el WhatsApp del telefono del numero puente. La sesion persiste en el
 *     volumen (/data/auth); no hay que re-escanear en cada deploy.
 *   - Si los logs dicen "loggedOut": borrar /data/auth y re-escanear.
 */
const express = require("express");
const pino = require("pino");
const qrcodeTerminal = require("qrcode-terminal");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
} = require("@whiskeysockets/baileys");

const PORT = process.env.PORT || 8080;
const TOKEN = process.env.BAILEYS_BRIDGE_TOKEN || "";
const AUTH_DIR = process.env.AUTH_DIR || "/data/auth";
const ALLOWED = (process.env.WA_ALLOWED_TO || "")
  .split(",")
  .map((s) => s.replace(/\D/g, ""))
  .filter(Boolean);

const log = pino({ level: process.env.LOG_LEVEL || "info" });

let sock = null;
let ready = false;
let lastQrAt = null;

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();
  sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "warn" }),
    markOnlineOnConnect: false,
    // No sincronizar historial: este numero solo ENVIA alertas.
    shouldSyncHistoryMessage: () => false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      lastQrAt = new Date().toISOString();
      log.warn("QR NUEVO — escanear con el WhatsApp del numero puente (Dispositivos vinculados):");
      qrcodeTerminal.generate(qr, { small: true });
    }
    if (connection === "open") {
      ready = true;
      log.info("WhatsApp CONECTADO — el puente esta listo para enviar alertas");
    }
    if (connection === "close") {
      ready = false;
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        log.error(
          "Sesion CERRADA por WhatsApp (loggedOut) — borrar el contenido de %s y reiniciar para re-escanear QR",
          AUTH_DIR,
        );
      } else {
        log.warn({ code }, "conexion cerrada — reintentando en 3s");
        setTimeout(connect, 3000);
      }
    }
  });
}

const app = express();
app.use(express.json());

function requireToken(req, res, next) {
  if (!TOKEN || req.headers.authorization !== `Bearer ${TOKEN}`) {
    return res.status(401).json({ error: "unauthorized" });
  }
  next();
}

app.get("/health", (_req, res) => {
  res.json({ ok: true, connected: ready, allowlist_size: ALLOWED.length, last_qr_at: lastQrAt });
});

app.post("/send", requireToken, async (req, res) => {
  const { to, text } = req.body || {};
  const digits = String(to || "").replace(/\D/g, "");
  if (!digits || !text) {
    return res.status(400).json({ error: "'to' y 'text' son requeridos" });
  }
  // Garantia de uso interno: fuera del allowlist NO se envia, punto.
  if (!ALLOWED.includes(digits)) {
    log.warn({ to: digits }, "destinatario fuera del allowlist interno — rechazado");
    return res.status(403).json({ error: "destinatario fuera del allowlist interno" });
  }
  if (!ready || !sock) {
    return res.status(503).json({ error: "whatsapp no conectado (falta escanear QR o esta reconectando)" });
  }
  try {
    await sock.sendMessage(`${digits}@s.whatsapp.net`, { text: String(text) });
    log.info({ to: digits, chars: String(text).length }, "alerta enviada");
    res.json({ ok: true });
  } catch (e) {
    log.error(e, "fallo el envio");
    res.status(500).json({ error: String(e?.message || e).slice(0, 200) });
  }
});

// '::' para que la red privada IPv6 de Railway pueda alcanzarlo.
app.listen(PORT, "::", () => log.info(`baileys-bridge escuchando en :${PORT}`));
connect();
