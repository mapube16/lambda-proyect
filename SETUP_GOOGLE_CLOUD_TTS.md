# Setup Google Cloud Text-to-Speech (5 minutos)

## Paso 1: Habilitar Cloud Text-to-Speech API

1. Ve a: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
2. Selecciona tu proyecto
3. Haz clic en **"Enable"** (ENABLE API)
4. Espera 30 segundos a que se active

## Paso 2: Crear Service Account

1. Ve a: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Selecciona tu proyecto
3. Haz clic en **"Create Service Account"**
4. Nombre: `voice-orchestrator`
5. Descripción: `Service account para síntesis de voz (TTS)`
6. Haz clic en **"Create and Continue"**

## Paso 3: Dar Permisos

1. En "Grant this service account access to the project":
   - Rol: **Cloud Text-to-Speech API User** (busca en el dropdown)
   - Haz clic en **"Continue"**
2. En "Grant users access to this service account":
   - Deja en blanco
   - Haz clic en **"Done"**

## Paso 4: Generar JSON Key

1. En la lista de service accounts, busca `voice-orchestrator`
2. Haz clic en el nombre
3. Ve a la pestaña **"Keys"**
4. Haz clic en **"Add Key"** → **"Create new key"**
5. Elige **"JSON"**
6. Haz clic en **"Create"**
7. Se descargará automáticamente un archivo `*.json`

## Paso 5: Codificar a Base64

En tu terminal (MacOS/Linux):
```bash
# En la carpeta donde descargaste el JSON
cat voice-orchestrator-*.json | base64 -w 0
```

**Windows (PowerShell):**
```powershell
$content = Get-Content voice-orchestrator-*.json -Raw
[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
```

Copia la salida (el string base64 muy largo).

## Paso 6: Agrega a `.env`

En `backend/.env`, busca `GOOGLE_CLOUD_TTS_CREDENTIALS_JSON` y pega:

```env
GOOGLE_CLOUD_TTS_CREDENTIALS_JSON=eyJh... (todo el string base64 que copiaste)
GOOGLE_CLOUD_TTS_PROJECT_ID=tu-proyecto-id
```

Puedes encontrar tu `PROJECT_ID` aquí:
https://console.cloud.google.com/home/dashboard

Busca "Project ID" en la tarjeta de proyecto.

## Paso 7: Verifica

En Python/Terminal:
```python
import os
import base64
import json

creds_b64 = os.getenv("GOOGLE_CLOUD_TTS_CREDENTIALS_JSON")
creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
print("✅ Credenciales OK" if "project_id" in creds_dict else "❌ Error")
```

## ¿Listo?

Una vez que tengas `GOOGLE_CLOUD_TTS_CREDENTIALS_JSON` en `.env`:
- [ ] `.env` actualizado
- [ ] `GOOGLE_CLOUD_TTS_PROJECT_ID` setteado
- [ ] Prueba de lectura exitosa

**Siguiente paso:** Implementar el WebSocket handler.
