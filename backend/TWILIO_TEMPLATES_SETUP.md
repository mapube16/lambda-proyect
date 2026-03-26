# ⚙️ Twilio WhatsApp Templates - Setup Guide

## Overview

Los botones interactivos en WhatsApp ahora funcionan a través de **Twilio Content Templates** (WhatsApp Content API). Esto requiere crear 3 templates en Twilio Console y copiar sus `ContentSid` al archivo `.env`.

---

## 🚀 Paso 1: Acceder a Twilio Console

1. Ve a [twilio.com/console](https://www.twilio.com/console)
2. Inicia sesión con tu cuenta Twilio
3. En el sidebar izquierdo, busca **Messaging** → **WhatsApp** → **Content Templates**

---

## 📋 Paso 2: Crear los 3 Templates

### Template 1: **Prospect Selection** (TWILIO_TEMPLATE_PROSPECT_SELECT)

**Nombre:** `prospect_selection`

**Tipo:** List or Quick Replies with up to 3 buttons

**Contenido:**

```
🎯 {{1}} · {{2}}

Selecciona un prospecto:
```

**Botones (buttons):**
- Botón 1: Label `1`, ID: `1`
- Botón 2: Label `2`, ID: `2`
- Botón 3: Label `3`, ID: `3`

**Copiar ContentSid:** `HXxxxxxxxxxxxxxxxxxxxxxxx`

---

### Template 2: **Channel Selection** (TWILIO_TEMPLATE_CHANNEL_SELECT)

**Nombre:** `channel_selection`

**Tipo:** Buttons (up to 3)

**Contenido:**

```
¿Cómo los contactamos?
```

**Botones:**
- Botón 1: Label `📧 Email`, ID: `email`
- Botón 2: Label `💬 WhatsApp`, ID: `whatsapp`
- Botón 3: Label `❌ Cancelar`, ID: `cancel`

**Copiar ContentSid:** `HXxxxxxxxxxxxxxxxxxxxxxxx`

---

### Template 3: **Confirmation** (TWILIO_TEMPLATE_CONFIRMATION)

**Nombre:** `contact_confirmation`

**Tipo:** Text message (simple)

**Contenido:**

```
✅ {{1}}

Queda registrado en el seguimiento.
```

**Sin botones**

**Copiar ContentSid:** `HXxxxxxxxxxxxxxxxxxxxxxxx`

---

## 🔑 Paso 3: Agregar ContentSids al .env

Una vez creados los templates, abre `.env` y actualiza:

```bash
TWILIO_TEMPLATE_PROSPECT_SELECT=HXxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_TEMPLATE_CHANNEL_SELECT=HXxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_TEMPLATE_CONFIRMATION=HXxxxxxxxxxxxxxxxxxxxxxxx
```

---

## ✅ Paso 4: Validate

### En Twilio Console:

1. Ve a **Test** en cada template
2. Dale "Send Test" (debería llegar en tu WhatsApp)

### En la aplicación:

```bash
cd backend
python -m pytest tests/test_whatsapp.py -v
```

Debería ver logs como:
```
[TWILIO-TEMPLATE] Sent to +57... with ContentSid HXxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 🔄 Fallback Behavior

Si **NO configuras los ContentSids** (dejas en blanco):
- El código automáticamente envía un mensaje de **texto con opciones numeradas**
- Ejemplo:
  ```
  🎯 Construcción · Bogotá

  Selecciona un prospecto:

  1. Constructor Plus
  2. BuildTech SAS
  3. Obras Colombia
  ```
- El usuario responde con el número y funciona igual ✅

---

## 🐛 Troubleshooting

### "Template not found"
- Asegúrate de que el `ContentSid` es válido (empieza con `HX`)
- Verifica que el template esté en estado **APPROVED**

### "No buttons visible"
- Los templates deben estar **aprobados por Twilio** (puede tardar hasta 24h)
- Si no están aprobados, el fallback de texto se activa automáticamente

### "Message sent but no buttons"
- Probable: el número receptor usa una versión vieja de WhatsApp
- Fallback automático a texto con números

---

## 📞 Support

Para crear templates con formato avanzado (imágenes, videos, etc):
- [Twilio WhatsApp API Docs](https://www.twilio.com/docs/whatsapp)
- [WhatsApp Content API Guide](https://www.twilio.com/docs/whatsapp/message-templates)

