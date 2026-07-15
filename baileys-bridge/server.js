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
const fs = require("fs");
const express = require("express");
const pino = require("pino");
const qrcodeTerminal = require("qrcode-terminal");
const QRCode = require("qrcode");
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
let lastQr = null; // raw payload del QR vigente (para la pagina /qr de vinculacion)

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
      lastQr = qr;
      log.warn("QR NUEVO — escanear con el WhatsApp del numero puente (Dispositivos vinculados):");
      // Payload crudo: permite regenerar el QR como imagen fuera de los logs
      // (el ASCII de abajo a veces se deforma en visores de logs).
      log.warn("QR_RAW %s", qr);
      qrcodeTerminal.generate(qr, { small: true });
    }
    if (connection === "open") {
      ready = true;
      lastQr = null;
      log.info("WhatsApp CONECTADO — el puente esta listo para enviar alertas");
    }
    if (connection === "close") {
      ready = false;
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        // 401: loggedOut O conflict/device_removed (WhatsApp expulso el
        // dispositivo). Las credenciales quedaron invalidas — limpiar la
        // sesion y reconectar emite un QR FRESCO automaticamente, sin tener
        // que borrar el volumen a mano ni reiniciar el servicio.
        log.error("Sesion invalidada (401/device_removed) — limpiando sesion y regenerando QR");
        try {
          fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        } catch (e) {
          log.error(e, "no se pudo limpiar AUTH_DIR");
        }
        setTimeout(connect, 2000);
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

// Pagina de vinculacion: muestra el QR vigente como imagen real (escaneable),
// auto-refrescante. SOLO activa mientras QR_PAGE_TOKEN este seteado — quien
// escanee este QR vincula el numero, asi que se protege con token y se
// desactiva (unset de la var) apenas termina la vinculacion.
app.get("/qr", async (req, res) => {
  const pageToken = process.env.QR_PAGE_TOKEN || "";
  if (!pageToken || req.query.t !== pageToken) return res.status(404).end();
  res.set("Cache-Control", "no-store");
  if (ready) {
    return res.send(
      '<body style="display:grid;place-items:center;height:100vh;font-family:sans-serif">' +
      "<h2>✅ WhatsApp conectado — ya puedes cerrar esta página</h2></body>",
    );
  }
  if (!lastQr) {
    return res.send(
      '<meta http-equiv="refresh" content="5">' +
      '<body style="display:grid;place-items:center;height:100vh;font-family:sans-serif">' +
      "<p>Esperando QR… (esta página se refresca sola)</p></body>",
    );
  }
  const dataUrl = await QRCode.toDataURL(lastQr, { width: 380, margin: 2 });
  res.send(
    '<meta http-equiv="refresh" content="20">' +
    '<body style="display:grid;place-items:center;height:100vh;font-family:sans-serif;text-align:center">' +
    `<div><img src="${dataUrl}" alt="QR WhatsApp">` +
    "<p>WhatsApp → <b>Dispositivos vinculados</b> → <b>Vincular dispositivo</b> → escanear.<br>" +
    "El QR rota cada ~60s; esta página se refresca sola.</p></div></body>",
  );
});

// ── Cola de envio con throttling (anti-baneo) ──────────────────────────────
// WhatsApp expulsa el dispositivo (conflict/device_removed) si detecta envios
// en rafaga — nos paso al mandar 9 seguidos. En vez de enviar de una, el
// endpoint ENCOLA y responde 202 al instante; un unico worker drena la cola de
// a un mensaje con pausa aleatoria entre cada uno (parece humano, no bot).
const SEND_MIN_MS = Number(process.env.SEND_MIN_MS || 5000);
const SEND_MAX_MS = Number(process.env.SEND_MAX_MS || 9000);
const queue = [];
let draining = false;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function drain() {
  if (draining) return;
  draining = true;
  try {
    while (queue.length) {
      if (!ready || !sock) {
        // desconectado: esperar y reintentar sin perder la cola
        await sleep(3000);
        continue;
      }
      const job = queue[0];
      try {
        await sock.sendMessage(`${job.to}@s.whatsapp.net`, { text: job.text });
        log.info({ to: job.to, chars: job.text.length, restantes: queue.length - 1 }, "alerta enviada");
        queue.shift();
      } catch (e) {
        job.tries = (job.tries || 0) + 1;
        log.error({ to: job.to, tries: job.tries, err: String(e?.message || e).slice(0, 120) }, "fallo el envio");
        if (job.tries >= 3) queue.shift(); // descartar tras 3 intentos
      }
      // pausa humana entre mensajes (jitter)
      const wait = SEND_MIN_MS + Math.floor((SEND_MAX_MS - SEND_MIN_MS) * ((Date.now() % 997) / 997));
      await sleep(wait);
    }
  } finally {
    draining = false;
  }
}

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
  queue.push({ to: digits, text: String(text), tries: 0 });
  drain(); // fire-and-forget; no bloquea la respuesta
  res.status(202).json({ ok: true, queued: true, queue_len: queue.length });
});

// '::' para que la red privada IPv6 de Railway pueda alcanzarlo.
app.listen(PORT, "::", () => log.info(`baileys-bridge escuchando en :${PORT}`));
connect();
