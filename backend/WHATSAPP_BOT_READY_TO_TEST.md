# ✅ WhatsApp Bot - Ready for Testing

## 🎯 What Was Fixed

The WhatsApp agent now has **proper Twilio integration** that works in TRIAL mode:

1. ✅ **Fixed button sending** → Now uses Twilio Content API (templates)
2. ✅ **Added fallback** → Text with numbered options (works in trial)
3. ✅ **Proper error handling** → Graceful degradation if templates unavailable
4. ✅ **Public entity filtering** → Excludes gov orgs from results
5. ✅ **Conversational flow** → Help → Search → Select → Choose channel → Send/Email

---

## 🚀 Quick Start (Development)

### 1. Start the backend server:

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### 2. Test locally (no Twilio needed):

```bash
# Test the message flow logic
python test_whatsapp_flow.py

# Test the full webhook flow with mocks
python test_whatsapp_webhook_manual.py
```

Expected output: ✅ All tests pass

---

## 📱 Real WhatsApp Testing with Twilio

### Prerequisites:
- ✅ Twilio account (trial OK, you have one)
- ✅ WhatsApp Business Account linked to Twilio
- ✅ ngrok or similar tunnel (to expose your local server)

### Setup:

1. **Start ngrok tunnel:**
   ```bash
   ngrok http 8001
   ```
   Copy the HTTPS URL: `https://xxxx.ngrok.io`

2. **Configure Twilio Webhook:**
   - Go to [Twilio Console](https://www.twilio.com/console)
   - Messaging → WhatsApp → Sandbox
   - "When a message comes in" → Set to:
     ```
     https://xxxx.ngrok.io/api/whatsapp/webhook
     ```
   - Click "Save"

3. **Test the bot:**
   - Send WhatsApp message to your Twilio number (+1 415-523-8886)
   - Try: `construccion bogota`
   - Bot responds with 3 prospects + their contact info

---

## 📊 Expected Bot Behavior

### User: "ayuda"
**Bot responds:**
```
👋 *Agente de Pólizas SECOP*

Envíame el sector que quieres prospectar:
• `construccion bogota`
• `tecnologia medellin`
• `transporte`
• `de todo tipo` (busca múltiples sectores)

Yo busco en SECOP las empresas que más contratan con el Estado
y te digo a quiénes contactar hoy. 🎯
```

### User: "construccion bogota"
**Bot responds (text fallback, since trial):**
```
🎯 *Construcción · Bogotá*

*1.* Constructor Plus SAS
📞 +573001234567  📧 contacto@constructor.co
_Acaban de ganar $250M en contrato con Ministerio de Obras_

*2.* BuildTech Innovations
📞 +573105678901  📧 info@buildtech.co
_3 adjudicaciones en últimos 90 días por $1.2B total_

*3.* Obras Colombia S.A.
📞 +573209876543  📧 ventas@obrasco.co
_Especialista en licitaciones del sector construcción_

Responde el *número* para contactar.
```

### User: "1"
**Bot responds:**
```
Seleccionaste: Constructor Plus SAS
📧 contacto@constructor.co
📞 +573001234567

¿Cómo los contactamos?
*E* → Email
*W* → WhatsApp
*C* → Cancelar
```

### User: "E"
**Bot responds:**
```
✅ Email enviado a Constructor Plus SAS.
Queda registrado en el seguimiento.
```

---

## 🔧 Configuration

Key environment variables in `.env`:

```bash
# Twilio (already set)
TWILIO_ACCOUNT_SID=ACd5677305fa10ade3226105243b960431
TWILIO_AUTH_TOKEN=aa784e30ec7d161ca254f10b9a4ac5ad
TWILIO_FROM_NUMBER=whatsapp:+14155238886

# Templates (empty for trial, will use text fallback)
TWILIO_TEMPLATE_PROSPECT_SELECT=
TWILIO_TEMPLATE_CHANNEL_SELECT=
TWILIO_TEMPLATE_CONFIRMATION=

# Sender info
SENDER_NAME=Maximiliano Pulido Beltran
SENDER_COMPANY=Seguros
SENDER_PHONE=3123528153

# Email (for sending outreach)
MAILERSEND_API_KEY=...
MAILERSEND_FROM_EMAIL=noreply@tudominio.com
```

---

## 🐛 Troubleshooting

### "No response from bot"
- Check ngrok tunnel is active: `ngrok http 8001`
- Verify webhook URL in Twilio Console
- Check server logs: `tail -f backend.log`

### "No prospects found"
- Try: `de todo tipo` (searches multiple sectors)
- Check SECOP API is responding
- Verify sector keywords are correct

### "Email not sending"
- Verify `MAILERSEND_API_KEY` is set
- Check domain is verified in MailerSend
- Look for logging: `[MAILERSEND-SEND]`

---

## ✨ Future Improvements (Phase A++)

When you upgrade from Trial:

1. **Real buttons** → Template-based interactive messages
2. **Rich media** → Images, documents in WhatsApp
3. **Webhooks callbacks** → Track message delivery
4. **Contact enrichment** → Auto-fetch CRM data
5. **Analytics** → Tracking conversions per prospect

---

## 📞 Testing Right Now

Ready to test? Run:

```bash
# Terminal 1: Start server
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8001

# Terminal 2: Verify with local tests
cd backend && python test_whatsapp_flow.py

# Terminal 3: Start ngrok
ngrok http 8001

# Terminal 4: Send WhatsApp message to +1 415-523-8886 with text "ayuda"
```

Then check your WhatsApp! 🚀
