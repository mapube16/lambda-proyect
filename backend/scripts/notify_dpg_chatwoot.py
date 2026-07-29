"""Envía al equipo DPG el correo explicando el acceso a Chatwoot (plataforma de
conversaciones de ARIA). Reusa el mailer del sistema (MailerSend HTTPS primario).

Se envía UNO por destinatario (no se exponen los correos entre sí). Salida:
OK/FALLO por dirección. No toca la base de datos.

Correr en prod (con la MAILERSEND_API_KEY real):
  railway run --service lambda-proyect <venv-python> scripts/notify_dpg_chatwoot.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mailer import send_smtp

# Destinatarios (mismos del equipo DPG con cuenta). Ajusta si Chatwoot invitó a
# otros correos distintos.
TEAM = [
    "administracion@dpgseguros.com",
    "auxiliar.cartera@dpgseguros.com",
    "gerencia@dpgseguros.com",
    "proyectos@dpgseguros.com",
    "innovaciondpg@gmail.com",
]

SUBJECT = "Acceso a la plataforma de conversaciones del asistente virtual ARIA"
CHATWOOT_URL = "https://chat.landatech.org"

HTML = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#222;line-height:1.55">
  <h2 style="color:#1a7f6e;margin-bottom:4px">Acceso a la plataforma de conversaciones de ARIA</h2>
  <p>Hola equipo DPG,</p>
  <p>Les acabamos de dar acceso a la plataforma donde podrán ver y gestionar
  <b>todas las conversaciones de WhatsApp</b> del asistente virtual ARIA con sus clientes.</p>

  <p><b>Para activar su cuenta:</b> les llegó un correo de invitación con el asunto de
  <b>Chatwoot</b> — hagan clic en el enlace y creen su contraseña. Luego pueden entrar
  siempre desde: <a href="{CHATWOOT_URL}">{CHATWOOT_URL}</a></p>

  <p style="margin-bottom:6px"><b>Qué van a encontrar:</b></p>
  <ul style="margin-top:0;padding-left:20px">
    <li>Todas las conversaciones del bot con los clientes en tiempo real
        (consultas de pólizas, envío de comprobantes, solicitudes de pago).</li>
    <li>Cuando un cliente pide hablar con un humano, la conversación se marca como
        <b>escalada</b> — cualquiera del equipo puede responder directamente desde la
        plataforma y el mensaje le llega al cliente por WhatsApp.</li>
    <li>Historial completo de cada cliente para dar contexto.</li>
  </ul>

  <p style="background:#fff6e5;border-left:4px solid #e0a500;padding:10px 14px;border-radius:4px">
    <b>Importante:</b> para responderle a un cliente, escriban en el campo
    <b>"Responder"</b> (no <b>"Nota privada"</b> — esa es solo interna y el cliente no la ve).</p>

  <p>Cualquier duda, quedamos atentos.</p>
  <p style="margin-top:22px">Saludos,<br>Equipo <b>LANDA Tech</b></p>
</div>
"""


def main() -> None:
    ok, fail = 0, 0
    for email in TEAM:
        try:
            send_smtp([email], SUBJECT, HTML)
            print(f"OK    {email}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FALLO {email}: {type(exc).__name__}: {str(exc)[:160]}")
            fail += 1
    print(f"\n{ok} enviados, {fail} fallidos, {len(TEAM)} total")


if __name__ == "__main__":
    main()
