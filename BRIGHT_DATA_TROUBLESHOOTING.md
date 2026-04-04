# Bright Data API Troubleshooting Guide

## El Problema
Bright Data no está funcionando cuando buscas leads. Los logs muestran errores de autenticación o endpoints inaccesibles.

## Diagnóstico Rápido

### 1. Verificar la configuración
Primero, ejecuta el script de test:

```bash
cd backend
python3 test_bright_data.py
```

Este script verifica:
- ✅ Si `BRIGHT_DATA_API_KEY` está configurada
- ✅ Si el endpoint SERP responde
- ✅ Si el endpoint Web Scraper responde

### 2. Errores Comunes

#### Error 401: Unauthorized
**Causa:** La API key es inválida o ha expirado

**Solución:**
1. Ve a tu dashboard de Bright Data: https://brightdata.com
2. Copia tu API token exacto
3. Actualiza en `.env` o variable de entorno:
   ```
   BRIGHT_DATA_API_KEY=tu_token_exacto
   ```
4. Reinicia el backend

#### Error 403: Forbidden
**Causa:** El dataset no está configurado en el dashboard de Bright Data

**Solución:**
1. Inicia sesión en https://brightdata.com
2. Ve a **Datasets** → **Create Dataset**
3. Crea dos datasets:

   **Dataset 1: SERP (Google Search)**
   - Nombre: `serp`
   - Tipo: Dataset Collector
   - Source: Google Search
   - Configurar campos: title, url, phone, address, rating

   **Dataset 2: Web Scraper**
   - Nombre: `web_scraper`
   - Tipo: Dataset Collector
   - Source: Custom Website Scraper
   - Configurar campos: name, email, phone, address, website, industry

4. Activa ambos datasets
5. Verifica que tengan quota disponible (credit budget)

#### No hay resultados
**Causa:** El dataset está configurado pero vacío o sin datos coincidentes

**Solución:**
1. Verifica en el dashboard que el dataset tiene datos
2. Ejecuta una búsqueda manual en el dashboard para confirmar
3. Asegúrate que el filtro country=CO y language=es sean válidos

#### Timeout (> 30 segundos)
**Causa:** Bright Data está procesando la solicitud pero es lento

**Solución:**
- Los primeros requests son más lentos (set-up de conexión)
- Bright Data típicamente toma 5-15 segundos por búsqueda
- Si consistentemente excede 30s: reduce `max_results` en `hive_tools.py`

## Configuración Correcta

### Backend (.env)
```env
BRIGHT_DATA_API_KEY=your_actual_api_key
```

### Frontend (hive_tools.py)
El parámetro `source_priority` controla qué fuente usar:

```python
source_priority="bright_data"   # Solo Bright Data (premium)
source_priority="serper"        # Solo Serper (economical)
source_priority="hybrid"        # Bright Data + Serper (best)
```

Ahora está en: `hive_tools.py` línea 51

### Logs para Debugging

Cuando busques leads, mira el archivo de logs del backend para:

```
[discover_companies] source_priority=... bright_data_key=SET
[Bright Data SERP] query='...' status=200
[Bright Data Web] source=LinkedIn status=200
[Discovery] Bright Data returned 15 results
```

Si ves errors:
```
[Bright Data SERP] status=401 query='...'
→ API key inválida

[Bright Data SERP] status=403 query='...'
→ Dataset no configurado en dashboard

[Bright Data Web] error: ... timeout
→ Request tomó demasiado tiempo
```

## Plan de Fallback

Si Bright Data no funciona, el sistema **automáticamente fallback** a:
1. Serper (si está configurado)
2. Google Maps
3. DuckDuckGo

Esto significa que **aunque Bright Data falle, igual obtendrás leads** de otras fuentes.

## Verificación Final

Después de configurar todo:

1. Ejecuta el test:
   ```bash
   python3 test_bright_data.py
   ```
   Debe mostrar: `SERP API: ✅ OK` y `Web Scraper: ✅ OK`

2. En la UI, busca leads
   Debe ver resultados en pocos segundos

3. En los logs, debe aparecer:
   ```
   [Discovery] Bright Data returned N results
   ```

## Soporte

Si el problema persiste:
1. Verifica el dashboard de Bright Data (crédito disponible?)
2. Contacta a Bright Data support: support@brightdata.com
3. Asegúrate que los datasets están **ACTIVE** (no pausados)

---

**Última actualización:** 2026-04-04
**Endpoints utilizados:**
- SERP: `https://api.brightdata.com/datasets/geos/parse`
- Web Scraper: `https://api.brightdata.com/datasets/geos/parse`
