# Plan de Implementación — Voice Orchestrator

**Estado:** Ya tienes Assembly AI API key. Faltan Google Cloud TTS + Twilio voice setup.

## Checklist Inmediato (Hoy)

### ✅ DONE
- [x] Assembly AI API key: `7a2168f1d53846eeb7b69317a57325ac`
- [x] Código base creado (claude_decision, orchestrator, etc.)
- [x] Documentación completa

### ⏳ TODAY (Next 1-2 hours)

#### 1️⃣ **Google Cloud TTS Setup** (30 min)
   - [ ] Lee: `SETUP_GOOGLE_CLOUD_TTS.md` (en este repo)
   - [ ] Activa Cloud Text-to-Speech API en GCP
   - [ ] Crea service account
   - [ ] Descarga JSON key
   - [ ] Encode a base64 (comando en guide)
   - [ ] Pega en `.env` → `GOOGLE_CLOUD_TTS_CREDENTIALS_JSON`
   - [ ] Pega PROJECT_ID en `.env` → `GOOGLE_CLOUD_TTS_PROJECT_ID`

#### 2️⃣ **Twilio Voice Setup** (15 min)
   - [ ] ¿Ya tienes número de Twilio para VOICE (no solo WhatsApp)?
   - [ ] Si NO: Compra número en https://www.twilio.com/console/phone-numbers/search
   - [ ] Actualiza `.env`:
     ```env
     TWILIO_VOICE_PHONE_NUMBER=+1234567890  # Tu número de Twilio
     VOICE_WEBHOOK_HOST=http://localhost:8001  # Backend URL
     ```

#### 3️⃣ **Verifica Configuración** (15 min)
   ```bash
   cd backend
   python test_voice_config.py
   ```
   - [ ] Si todo muestra `✓`, estás listo
   - [ ] Si hay `✗`, arregla antes de continuar

## Próximos Pasos (Semana 2)

### Phase B: Implementar WebSocket Handler
**Archivo:** `backend/cobranza/voice_router.py:voice_websocket()`

Esto es lo CRÍTICO. El WebSocket handler es donde:
1. Recibes audio de Twilio
2. Lo envías a Assembly AI
3. Recibes transcripción
4. Llamas a Claude para decidir qué decir
5. Sintetizas con Google TTS
6. Devuelves audio a Twilio

**Complejidad:** 3-4 horas de implementación concentrada

**Helpers que ya existen:**
- `AssemblyAIClient()` — ready to use
- `get_next_action()` — ready to use
- `VoiceOrchestrator()` — ready to use
- `get_tts_provider()` — ready to use

### Phase C: Testing
- Unit tests (claude_decision mocked)
- Integration tests (full flow)
- Manual E2E (real Twilio calls)

### Phase D: Rollout
- Staging deployment
- Beta test (10% of calls)
- Full switch from Vapi

---

## Paso a Paso: Google Cloud TTS (si no lo has hecho)

### 1. Ve a Google Cloud Console
https://console.cloud.google.com/apis/library/texttospeech.googleapis.com

### 2. Enable the API
- Selecciona tu proyecto
- Haz clic en **"Enable"**

### 3. Create Service Account
Menú: **IAM & Admin** → **Service Accounts** → **Create Service Account**

```
Name: voice-orchestrator
Description: Service account for voice synthesis TTS
```

### 4. Grant Roles
- Search for: `Cloud Text-to-Speech API User`
- Selecciona ese rol
- Click Continue, Done

### 5. Create JSON Key
- Click en el service account `voice-orchestrator`
- Tab: **Keys**
- **Add Key** → **Create new key** → **JSON**
- Se descarga automáticamente

### 6. Encode to Base64

**En MacOS/Linux:**
```bash
cat voice-orchestrator-*.json | base64 -w 0 | pbcopy
```

**En Windows PowerShell:**
```powershell
$json = Get-Content voice-orchestrator-*.json -Raw
$base64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($json))
$base64 | Set-Clipboard
```

### 7. Update .env

Abre `backend/.env` y busca:
```env
GOOGLE_CLOUD_TTS_CREDENTIALS_JSON=eyJh...
GOOGLE_CLOUD_TTS_PROJECT_ID=your-project-id
```

Pega el base64 en `GOOGLE_CLOUD_TTS_CREDENTIALS_JSON` (todo en una línea)

Y encuentra tu PROJECT_ID aquí:
https://console.cloud.google.com/home/dashboard

### 8. Verify

```bash
cd backend
python test_voice_config.py
```

Si ves `✓ OK` para todos, estás listo.

---

## Twilio Voice Number

¿Ya tienes un número de Twilio para **VOICE** calls?

**Opción 1:** Si ya tienes Twilio (para WhatsApp)
- [ ] Compra un número adicional para voz
- [ ] Ve a: https://www.twilio.com/console/phone-numbers/search
- [ ] Busca número (e.g., Colombia: +57)
- [ ] Compra y agrega a `.env`: `TWILIO_VOICE_PHONE_NUMBER`

**Opción 2:** Si no tienes Twilio aún
- [ ] Crea cuenta gratis: https://www.twilio.com
- [ ] Obtén número (se asigna automáticamente en trial)
- [ ] Upgrade a paid (necesario para production)
- [ ] Agrega a `.env`

---

## Validation Checklist

Antes de implementar WebSocket handler:

- [ ] `ASSEMBLY_AI_API_KEY` está en `.env`
- [ ] `GOOGLE_CLOUD_TTS_CREDENTIALS_JSON` está en `.env`
- [ ] `GOOGLE_CLOUD_TTS_PROJECT_ID` está en `.env`
- [ ] `TWILIO_VOICE_PHONE_NUMBER` está en `.env`
- [ ] `VOICE_WEBHOOK_HOST` está en `.env` (http://localhost:8001 para dev)
- [ ] `python test_voice_config.py` muestra todo `✓ OK`
- [ ] Puedes importar `AssemblyAIClient` sin error
- [ ] Puedes importar `get_next_action` sin error

---

## Next: WebSocket Handler

Una vez que todos los checkboxes arriba estén `✓`:

**Call me**, te ayudo a implementar el WebSocket handler. Es straightforward:

```python
@router.websocket("/ws/{call_sid}")
async def voice_websocket(websocket: WebSocket, call_sid: str):
    # 1. Accept connection
    # 2. Initialize Assembly AI stream
    # 3. Main loop:
    #    - Receive audio from Twilio
    #    - Send to Assembly AI
    #    - Read transcript
    #    - Ask Claude (get_next_action)
    #    - Synthesize (get_tts_provider)
    #    - Send back to Twilio
    # 4. On end: log to MongoDB
```

¡Vamos! 🚀
