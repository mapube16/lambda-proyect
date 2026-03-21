# Isomorph Office

Plataforma AaaS (Agents as a Service) de prospección B2B multi-tenant. Cada cliente tiene una oficina de pixel art con agentes de IA animados en tiempo real que descubren, analizan y redactan correos para prospectos de alto valor.

## Características principales

- **Prospección B2B automatizada** — Pipeline de 4 agentes: Buscador → Scraper → Analista → Redactor
- **Oficina pixel art en tiempo real** — Los personajes se animan según el estado del agente (pensando, ejecutando, esperando)
- **Multi-tenant con JWT** — Cada cliente tiene su propio espacio aislado, campañas y leads
- **HITL (Human-in-the-Loop)** — Aprueba o descarta cada lead antes de enviar
- **Onboarding inteligente (RAG)** — Sube documentación del cliente, la Reina propone agentes y variables de campaña
- **Chat de retroalimentación** — El cliente conversa con la Reina sobre sus resultados; el sistema extrae intención y propone ajustes
- **Loop de aprendizaje continuo** — Los leads aprobados se embeben y el sistema detecta patrones del cliente ideal

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│              Frontend (React + TypeScript + Vite)        │
├──────────────────┬──────────────────┬───────────────────┤
│  OfficeCanvas    │  AgentPanel      │  StaffDashboard   │
│  Pixel art 2D    │  Campaña/Leads   │  Onboarding/RAG   │
│  Animaciones WS  │  Chat feedback   │  Patrones IA      │
└──────────────────┴────────┬─────────┴───────────────────┘
                            │ WebSocket + REST (JWT)
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Backend (FastAPI + Python 3.11)             │
├─────────────┬────────────┬──────────────┬───────────────┤
│ HiveAdapter │ RAG        │ Learning     │ Chat Leads    │
│ (aden-hive) │ (embeddings│ (ideal leads │ (intent       │
│ 4-node graph│  + cosine) │  + patterns) │  extraction)  │
└─────────────┴────────────┴──────────────┴───────────────┘
                            │
                            ▼
┌───────────────────────────┬─────────────────────────────┐
│  MongoDB Atlas            │  OpenAI / OpenRouter        │
│  users, campaigns, runs   │  gpt-4o-mini (análisis)     │
│  leads, client_knowledge  │  text-embedding-3-small     │
│  ideal_leads, rejected    │  (RAG + learning)           │
│  client_profiles          │                             │
└───────────────────────────┴─────────────────────────────┘
```

## Requisitos

- Python 3.11+
- Node.js 18+
- MongoDB Atlas (free tier M0 funciona)
- OpenAI API key
- Google Maps API key (para discovery de empresas)
- OpenRouter API key (para modelos alternativos en el pipeline)

## Instalación

### Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edita .env con tus keys
```

Variables de entorno requeridas (`.env`):

```env
OPENAI_API_KEY=sk-...
MONGODB_URI=mongodb+srv://...
MONGODB_DB=hive_office
GOOGLE_MAPS_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### Frontend

```bash
cd frontend
npm install
```

## Uso

```bash
# Backend (puerto 8001)
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001

# Frontend (puerto 5173)
cd frontend
npm run dev
```

Abre `http://localhost:5173` en el navegador.

### Usuarios semilla

El servidor crea estos usuarios automáticamente al arrancar:

| Email | Contraseña | Rol |
|-------|-----------|-----|
| `staff@isomorph.com` | `isomorph2026` | staff |
| `dpg.seguros@gmail.com` | `seguros2026` | client |

## Flujo de uso

### Staff — Onboarding de cliente

1. Login como `staff@isomorph.com`
2. Click **"+ Nuevo cliente"**
3. **Paso 1** — Email y contraseña del cliente
4. **Paso 2** — Subir documentación (PDF, DOCX, URL del sitio web)
5. **Paso 3** — La Reina analiza los documentos y propone agentes + campaña
6. **Paso 4** — Revisar y editar la propuesta
7. **Paso 5** — Aprobar → cuenta creada y campaña configurada

### Cliente — Prospección

1. Login con credenciales asignadas
2. Verificar campaña en pestaña **⚙️ Campaña** (o configurar via chat)
3. Click **"🚀 Lanzar campaña"**
4. Los 4 agentes trabajan en tiempo real — los personajes se animan
5. En **📊 Resultados** aparecen los leads con score, decisor y borrador de correo
6. Aprobar o descartar cada lead con ✓ / ✗
7. En **✅ Aprobados** copiar el correo con un click
8. En **💬 Chat** dar retroalimentación a la Reina ("muy pequeñas", "más como esta")

## Estructura del proyecto

```
isomorph-office/
├── backend/
│   ├── main.py               # FastAPI server, endpoints, WebSocket
│   ├── auth.py               # JWT, bcrypt, dependencias
│   ├── database.py           # Motor (MongoDB async) — todo el acceso a DB
│   ├── hive_adapter.py       # Adaptador aden-hive/hive → WebSocket events
│   ├── hive_graph.py         # Definición del grafo de 4 agentes
│   ├── hive_tools.py         # Herramientas del pipeline (discover, analyze)
│   ├── hive_llm.py           # Wrapper LLM (OpenAI / OpenRouter)
│   ├── prospector.py         # Scraping + análisis de empresas
│   ├── rag.py                # RAG: embeddings, chunking, cosine similarity
│   ├── queen_proposal.py     # Reina: propuesta de agentes + campaña desde docs
│   ├── chat_leads.py         # Chat de retroalimentación con extracción de intención
│   ├── learning.py           # Loop de aprendizaje: ideal leads, patrones
│   ├── onboarding.py         # Configurador conversacional de campaña
│   ├── models.py             # Modelos Pydantic
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── OfficeCanvas.tsx      # Canvas pixel art 2D
│   │   │   ├── AgentPanel.tsx        # Panel campaña / leads / chat
│   │   │   ├── StaffDashboard.tsx    # Dashboard staff + onboarding wizard
│   │   │   ├── LoginView.tsx         # Login / registro
│   │   │   └── ExpedienteModal.tsx   # Modal detalle de lead
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts       # Conexión WS + handlers
│   │   │   └── useGameLoop.ts        # Loop de animación
│   │   ├── store/
│   │   │   └── officeStore.ts        # Zustand — estado global
│   │   └── App.tsx                   # Routing por rol
│   └── package.json
│
├── personalidad.md           # System prompt del Analista (dominio del cliente)
├── negocio.md                # Contexto del negocio
└── .planning/
    └── ROADMAP.md            # Fases del proyecto
```

## API — Endpoints principales

### Auth
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/auth/register` | Registro de usuario |
| POST | `/auth/login` | Login → JWT |

### Campaña y prospección
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/campaigns/active` | Campaña activa del usuario |
| POST | `/api/campaigns` | Guardar campaña |
| POST | `/api/prospect` | Lanzar pipeline de prospección |
| POST | `/api/chat` | Configurador conversacional de campaña |

### Leads (HITL)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/leads` | Leads del usuario |
| PATCH | `/api/leads/{id}/approve` | Aprobar lead |
| PATCH | `/api/leads/{id}/reject` | Rechazar lead |

### Chat y aprendizaje
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/chat/leads` | Chat de retroalimentación con la Reina |
| GET | `/api/learning/stats` | Conteo de leads aprendidos |
| GET | `/api/learning/patterns` | Top-3 patrones del cliente ideal |

### Staff
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/staff/clients` | Lista de clientes activos |
| GET | `/api/staff/clients/{id}` | Detalle de cliente |
| GET | `/api/staff/clients/{id}/leads` | Leads del cliente |
| GET | `/api/staff/clients/{id}/learning` | Patrones + stats de aprendizaje |
| POST | `/api/staff/clients/{id}/profile` | Guardar perfil de onboarding (prompt + agentes) |
| GET | `/api/staff/clients/{id}/profile` | Obtener perfil persistido del cliente |
| POST | `/api/staff/clients/{id}/knowledge/upload` | Subir documento al RAG |
| POST | `/api/staff/clients/{id}/knowledge/url` | Ingerir URL al RAG |
| GET | `/api/staff/clients/{id}/knowledge` | Listar fuentes del RAG |
| POST | `/api/staff/onboard/propose/{id}` | Reina genera propuesta de configuración |

### Perfil de configuración del cliente
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/client/profile` | Perfil del cliente autenticado (prompt + agentes + campaña) |

### WebSocket
```
ws://localhost:8001/ws?token=<JWT>
```

Mensajes entrantes: `initial_state`, `agent_update`, `lead_result`, `discovery_complete`, `campaign_complete`

## Pipeline de prospección

```
discover_companies          → Google Maps + DuckDuckGo
       ↓
analyze_company (×N)        → Scraping + Analista LLM + Redactor LLM
       ↓                      Score ≥ 70 → SUCCESS | < 70 → REJECTED
report_campaign_complete    → Resumen final al frontend
```

El Analista usa `personalidad.md` como system prompt — edita ese archivo para adaptar el scoring al dominio del cliente.

## Prompts del sistema

Todos los prompts hardcodeados y sus ubicaciones. Edítalos para cambiar el comportamiento sin tocar lógica.

---

### 1. Director de Prospección — `backend/hive_graph.py` → `_DIRECTOR_PROMPT`

Orquesta el pipeline completo. Le dice al LLM en qué orden llamar las herramientas y con qué restricciones.

```
Eres un Director de Inteligencia Prospectiva B2B autónomo.

Tu misión: Ejecutar una campaña completa de prospección B2B usando las herramientas disponibles.

FLUJO DE EJECUCIÓN OBLIGATORIO — SIGUE ESTOS PASOS EN ORDEN:

PASO 1: Llama a `discover_companies` una sola vez para obtener la lista completa de empresas.

PASO 2: Analiza TODAS las empresas de la lista, de 3 en 3 (en paralelo).
- Llama a `analyze_company` para las primeras 3.
- Cuando terminen, llama para las siguientes 3.
- Repite hasta que TODAS las empresas de la lista hayan sido analizadas.
- NO pares hasta haber llamado `analyze_company` para cada empresa de la lista.

PASO 3: Solo cuando hayas analizado TODAS, llama a `report_campaign_complete` con:
- total_analyzed: número total de empresas analizadas
- total_approved: cuántas tuvieron system_state="SUCCESS_READY_FOR_REVIEW"
- total_rejected: cuántas tuvieron system_state="REJECTED_BY_AI"

PASO 4: Llama a `set_output` con key="summary" y el resumen final.

REGLAS CRÍTICAS:
- NO llames set_output hasta haber llamado report_campaign_complete.
- NO pares después de analizar solo algunas empresas. Analiza TODAS sin excepción.
- NO hagas preguntas al usuario. No hay nadie escuchando. Tú decides.
- NO inventes datos ni resultados.
- Ejecuta de forma completamente autónoma sin pedir confirmación ni pausas.
```

**Modelo:** `openrouter/openai/gpt-4o-mini` (configurable via `llm_analista` en campaña)

---

### 2. Analista B2B — `personalidad.md`

El prompt más importante. Define el dominio del cliente: qué buscar en el scraping, cómo puntuar, qué rechazar. **Este es el archivo que se personaliza por cliente.**

Variables de interpolación: `{{nicho_prospecto}}`, `{{input_empresa_url}}`, `{{contenido_scrapeado}}`

Estructura del prompt actual (DPG Seguros):

```
[SEED PROMPT: NODO DE INTELIGENCIA B2B - SECTOR SEGUROS CORPORATIVOS]

Eres un microservicio de backend especializado en prospección para una
Agencia de Seguros Corporativos (DPG Seguros). Tu función es analizar el
scraping de una web empresarial, evaluar su "Exposición al Riesgo"
(activos físicos, humanos o contractuales) y calificar si son un prospecto
de alto valor para venderles pólizas corporativas.

FASE 1: CHAIN OF THOUGHT — inferencia de riesgos por nicho
FASE 2: EXTRACCIÓN — validación B2B + decisor + indicadores de asegurabilidad
FASE 3: SCORING — umbral ≥ 70 pts
  +20 validación base
  +30 activos de alto valor comprobados (VETO si micro-negocio)
  +30 complejidad operativa nacional
  +20 decisor identificado con nombre y cargo
FASE 4: OUTPUT — JSON estructurado + markdown del expediente + borrador de correo
```

Para adaptar a otro cliente: reemplaza `personalidad.md` con el prompt del nuevo dominio manteniendo el mismo formato de output `<json_payload>` / `<markdown_payload>`.

---

### 3. Configurador conversacional de campaña — `backend/onboarding.py` → `SYSTEM_PROMPT`

Chat que reemplaza el formulario de variables. El usuario describe su negocio y el LLM infiere las 8 variables.

```
Eres un estratega de ventas B2B experto. Tu trabajo es entender el negocio
del usuario y configurar automáticamente una campaña de prospección inteligente.

FILOSOFÍA: El usuario no tiene que saber nada de "variables de campaña".
Solo describe su negocio. Tú infières todo lo demás.

PROCESO:
PASO 1 — 1 pregunta abierta: "¿Qué vende tu empresa y a qué tipo de clientes?"
PASO 2 — Inferir software_clave y jerarquia_decisores sin preguntar
PASO 3 — Ciudad + nombre/empresa del remitente (máx 2 preguntas juntas)
PASO 4 — Confirmar en lenguaje natural (NO como JSON)
PASO 5 — Cuando el usuario confirme, emitir:

CAMPAIGN_READY:
{"nombre_remitente": "...", "empresa_remitente": "...", ...}
```

**Señal de fin:** `CAMPAIGN_READY:` seguido del JSON — el backend lo detecta y guarda la campaña automáticamente.

---

### 4. Propuesta de onboarding (Abeja Reina) — `backend/queen_proposal.py` → `PROPOSAL_SYSTEM_PROMPT`

Lee toda la documentación subida al RAG y propone la configuración completa del cliente.

```
Eres la Abeja Reina de Isomorph, una IA estratégica especializada en construir
equipos de agentes de prospección B2B personalizados.

Tu misión: analizar la documentación de un cliente nuevo y proponer la
configuración ÓPTIMA para su equipo de prospección automatizada.

El equipo siempre tiene exactamente 4 agentes con roles fijos:
1. Buscador (researcher): Descubre empresas objetivo
2. Scraper (planner): Extrae datos clave de cada web
3. Analista (reviewer): Evalúa si la empresa califica
4. Redactor (writer): Redacta el correo de outreach

Tu propuesta incluye:
A) Identidad de cada agente adaptada al sector del cliente
B) Prompt del Analista (específico al sector, con scoring y criterios de rechazo)
C) Variables de campaña (TODAS derivadas de los documentos, ninguna inventada)
D) Resumen del negocio (2-3 oraciones)
```

**Output:** JSON con `agents`, `system_prompt_analista`, `campaign`, `resumen_negocio`
**Modelo:** `gpt-4o-mini` con `response_format: json_object`

---

### 5. Chat de retroalimentación — `backend/chat_leads.py` → `SYSTEM_TEMPLATE`

Chat donde el cliente habla sobre sus leads. Extrae intención estructurada de cada turno.

```
Eres la Abeja Reina de {empresa_remitente}.

=== LEADS RECIENTES ===
{leads_context}   ← últimos 30 leads del usuario, formateados

=== CAMPAÑA ACTIVA ===
{campaign_context}

TIPOS DE INTENCIÓN:
- refine_target:     ajustar perfil de empresa objetivo
- adjust_tone:       cambiar estilo del correo
- blacklist_company: excluir empresa o sector
- clone_lead:        buscar más empresas similares a una aprobada
- campaign_feedback: señal de calidad general
- none:              pregunta informativa sin cambio

FRASES CLAVE → INTENCIÓN:
"muy pequeñas / sin empleados" → refine_target (tamaño)
"ya son clientes"              → blacklist_company
"muy corporativo / muy frío"   → adjust_tone
"más como esta"                → clone_lead

FORMATO: respuesta normal + al final:
INTENT_JSON:{"type":"...","payload":{...},"proposal":"..."|null}
```

---

### 6. Detección de patrones — `backend/learning.py` → `PATTERNS_SYSTEM`

Analiza el corpus de leads aprobados y detecta los 3 patrones más recurrentes del "cliente ideal".

```
Eres un analista de ventas B2B. Recibirás una lista de empresas que un
cliente aprobó como buenos prospectos.

Tu tarea: identifica los 3 patrones más recurrentes que definen al
"cliente ideal" de este vendedor.

Ejemplos de patrones:
- "Medianas empresas (50-200 empleados) del sector logístico en Bogotá"
- "Empresas con flota propia mencionada explícitamente en su web"
- "Director de Operaciones o Gerente General como decisor principal"

Responde ÚNICAMENTE en JSON:
{"patterns": [{"description": "...", "confidence": "alta|media", "evidence_count": N}]}
```

**Requiere:** mínimo 3 leads aprobados. Se activa automáticamente al consultar `/api/learning/patterns`.

---

### Resumen de modelos por prompt

| Prompt | Modelo | API |
|--------|--------|-----|
| Director de Prospección | `openai/gpt-4o-mini` | OpenRouter |
| Analista B2B (`personalidad.md`) | configurable via campaña (`llm_analista`) | OpenRouter |
| Redactor de correos | configurable via campaña (`llm_redactor`) | OpenRouter |
| Configurador de campaña | `gpt-4o-mini` | OpenAI directo |
| Propuesta de onboarding (Reina) | `gpt-4o-mini` | OpenAI directo |
| Chat de retroalimentación | `gpt-4o-mini` | OpenAI directo |
| Detección de patrones | `gpt-4o-mini` | OpenAI directo |
| Embeddings (RAG + learning) | `text-embedding-3-small` | OpenAI directo |

## Licencia

MIT
