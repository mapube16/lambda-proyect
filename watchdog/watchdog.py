"""
watchdog — perro guardián de la operación de cobranza ARIA.

Corre como servicio SEPARADO (sobrevive si el backend principal se cae) y cada
CHECK_INTERVAL_SEC verifica:

  1. SALUD DEL BACKEND: GET a WATCHDOG_HEALTH_URL. Si falla 2 veces seguidas →
     alerta "backend caído". Avisa también cuando se recupera.

  2. ¿DEJÓ DE MARCAR?: solo en franja hábil (9-12 / 14-16 Bogotá, L-V), con
     autocall encendido y habiendo deudores pendientes: si no hay ninguna
     llamada COMPLETADA en los últimos STALE_CALL_MIN minutos → alerta
     "ARIA no está marcando".

Alertas por WhatsApp (baileys-bridge) + email (SMTP), con cooldown para no
spamear. Expone /health propio para que un UptimeRobot externo vigile al
vigilante.
"""
import os
import ssl
import time
import smtplib
import threading
import http.server
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr

import certifi
import httpx
import pytz
from pymongo import MongoClient

# ── Config ──────────────────────────────────────────────────────────────────
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "hive_office")
DPG_USER_ID = os.getenv("DPG_USER_ID", "69bcd9bb6e35d53880364535")

HEALTH_URL = os.getenv("WATCHDOG_HEALTH_URL", "https://my.landatech.org/api/health")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SEC", "300"))
STALE_CALL_MIN = int(os.getenv("STALE_CALL_MIN", "30"))
COOLDOWN_MIN = int(os.getenv("ALERT_COOLDOWN_MIN", "45"))
PORT = int(os.getenv("PORT", "8080"))

ALERT_PHONE = os.getenv("WATCHDOG_ALERT_PHONE", "+573123528153")
ALERT_EMAIL = os.getenv("WATCHDOG_ALERT_EMAIL", "")

BRIDGE_URL = os.getenv("BAILEYS_BRIDGE_URL", "").rstrip("/")
BRIDGE_TOKEN = os.getenv("BAILEYS_BRIDGE_TOKEN", "")

SMTP_HOST = os.getenv("SMTP_HOST", "mail.privateemail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

BOGOTA = pytz.timezone("America/Bogota")
FRANJAS = [(9, 12), (14, 16)]  # informe §2

_mongo = MongoClient(MONGODB_URI, tlsCAFile=certifi.where()) if MONGODB_URI else None
_db = _mongo[MONGODB_DB] if _mongo else None

# estado en memoria (proceso único)
_state = {"health_fails": 0, "was_down": False, "last_alert": {}}


def _log(msg):
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


# ── Envío de alertas (WhatsApp + email, con cooldown por tipo) ──────────────
def _send_whatsapp(text):
    if not BRIDGE_URL or not BRIDGE_TOKEN:
        return
    try:
        httpx.post(f"{BRIDGE_URL}/send", json={"to": ALERT_PHONE, "text": text},
                   headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"}, timeout=20)
    except Exception as e:
        _log(f"[wa] fallo: {e}")


def _send_email(subject, body):
    if not ALERT_EMAIL or not SMTP_PASS:
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = formataddr(("Watchdog ARIA", SMTP_FROM))
        msg["To"] = ALERT_EMAIL
        html = f'<div style="font-family:Arial,sans-serif;font-size:14px">{body}</div>'
        msg.attach(MIMEText(html, "html", "utf-8"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [e.strip() for e in ALERT_EMAIL.split(",") if e.strip()], msg.as_string())
    except Exception as e:
        _log(f"[email] fallo: {e}")


def _alert(incident, text, *, bypass_cooldown=False):
    """Envía por ambos canales, con cooldown por tipo de incidente."""
    now = time.time()
    last = _state["last_alert"].get(incident, 0)
    if not bypass_cooldown and (now - last) < COOLDOWN_MIN * 60:
        _log(f"[alert] {incident} en cooldown — se omite")
        return
    _state["last_alert"][incident] = now
    _log(f"[ALERT] {incident}: {text}")
    _send_whatsapp(f"🚨 WATCHDOG ARIA\n{text}")
    _send_email(f"🚨 Watchdog ARIA — {incident}", text)


# ── Chequeos ────────────────────────────────────────────────────────────────
def check_health():
    try:
        r = httpx.get(HEALTH_URL, timeout=15)
        ok = r.status_code == 200
    except Exception:
        ok = False

    if ok:
        if _state["was_down"]:
            _state["was_down"] = False
            _alert("backend_recuperado", "✅ El backend de ARIA volvió a responder.", bypass_cooldown=True)
        _state["health_fails"] = 0
    else:
        _state["health_fails"] += 1
        _log(f"[health] fallo #{_state['health_fails']} ({HEALTH_URL})")
        if _state["health_fails"] >= 2:
            _state["was_down"] = True
            _alert("backend_caido", f"⚠️ El backend de ARIA NO responde ({HEALTH_URL}). Revisar Railway.")


def _in_franja(now_co):
    if now_co.weekday() >= 5:  # sáb/dom
        return False
    h = now_co.hour + now_co.minute / 60
    return any(ini + 0.25 <= h <= fin for ini, fin in FRANJAS)  # +15min de gracia


def check_calling():
    if _db is None:
        return
    now_co = datetime.now(BOGOTA)
    if not _in_franja(now_co):
        return
    # autocall encendido?
    ks = _db.cobranza_runtime.find_one({"_id": "killswitch"})
    autocall = (ks or {}).get("enabled")
    if not autocall:
        return
    # hay trabajo pendiente?
    pendientes = _db.debtors.count_documents({
        "user_id": DPG_USER_ID, "estado": "pendiente",
        "no_llamar": {"$ne": True}, "is_test": {"$ne": True},
    })
    if pendientes == 0:
        return
    # última llamada completada (ledger)
    ultimo = _db.cobranza_minutos_ledger.find_one(
        {"user_id": DPG_USER_ID, "tipo": "consumo"}, sort=[("created_at", -1)]
    )
    ref = (ultimo or {}).get("created_at")
    if ref is None:
        _alert("no_marca", f"⚠️ En franja y con {pendientes} deudores pendientes, pero ARIA no ha registrado NINGUNA llamada. Puede estar caída la marcación.")
        return
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    mins = (datetime.now(timezone.utc) - ref).total_seconds() / 60
    if mins > STALE_CALL_MIN:
        _alert("no_marca", f"⚠️ ARIA no marca hace {int(mins)} min (hay {pendientes} pendientes, estamos en franja). Última llamada: {ref.astimezone(BOGOTA).strftime('%H:%M')}.")


# ── /health propio (para UptimeRobot) ───────────────────────────────────────
class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true,"service":"watchdog"}')

    def log_message(self, *a):
        pass


def _serve_health():
    http.server.HTTPServer(("", PORT), _H).serve_forever()


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    _log(f"watchdog iniciado — health={HEALTH_URL} cada {CHECK_INTERVAL}s, alerta a {ALERT_PHONE} + {ALERT_EMAIL}")
    threading.Thread(target=_serve_health, daemon=True).start()
    while True:
        try:
            check_health()
            check_calling()
        except Exception as e:
            _log(f"[loop] error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
