# Lambda Office — Landa Prospecting Platform

Plataforma SaaS multi-tenant para prospección B2B automatizada. Busca, analiza y genera correos para prospectos calificados usando 4 pipelines de prospección configurable: **Serper** (búsqueda web), **RUES** (registro de empresas), **SECOP** (contratos públicos) y **Fincaraíz** (propiedades en arriendo).

## Características principales

- **Prospección multi-fuente** — 4 pipelines de búsqueda: Serper, RUES, SECOP, Fincaraíz
- **Flujo de campaña completa** — Crear → Configurar → Lanzar → Revisar → Aprobar/Rechazar leads
- **Template-based campaigns** — Selecciona el tipo de prospección, completa el wizard, lanza
- **HITL (Human-in-the-Loop)** — Revisión manual de cada lead antes de enviar
- **Multi-tenant con JWT** — Cada cliente aislado por user_id
- **AsyncIO con ARQ** — Prospecting jobs corren en background, resultados se persisten en MongoDB
- **API REST + React frontend** — TypeScript end-to-end

## Arquitectura

```
┌─────────────────────────────────────┐
│  Frontend (React + TypeScript)       │
│  - App.tsx: Campaign wizard + views  │
│  - api.ts: REST client layer         │
│  - 6 views: Inicio, Campañas,        │
│    Aprobados, Chat, Resultados,      │
│    Aprendizaje                       │
└──────────────┬──────────────────────┘
               │ HTTPS / REST API
               │ (Bearer JWT token)
               ▼
┌─────────────────────────────────────┐
│  Backend (FastAPI + Python)          │
│  - main.py: Server + routing         │
│  - routers/landa.py: Campaign API    │
│  - worker.py: ARQ async jobs         │
│  - database.py: MongoDB operations   │
└──────────────┬──────────────────────┘
               │
      ┌────────┴───────────┐
      ▼                    ▼
┌───────────────┐  ┌──────────────────┐
│  MongoDB      │  │  Railway Redis   │
│  - campaigns  │  │  - ARQ queue     │
│  - leads      │  │  - job results   │
│  - runs       │  │                  │
│  - users      │  │                  │
└───────────────┘  └──────────────────┘
      ▲
      │ (via HiveAdapter)
      │
  ┌───┴──────────────────────┐
  │  Hive Prospecting Engine  │
  │  - discover_companies()   │
  │  - analyze_company()      │
  │  - Multiple data sources  │
  └──────────────────────────┘
```

## Tech Stack

- **Frontend:** React 18, TypeScript, Vite, Hero Icons
- **Backend:** FastAPI, Python 3.11, Motor (MongoDB async driver)
- **Database:** MongoDB Atlas (cloud)
- **Queue:** ARQ (async job queue with Redis)
- **Deployment:** Railway (Backend + Redis + Frontend)
- **Auth:** JWT (HS256)
- **LLM/Search:** Serper API, Hive prospecting engine

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

**Variables de entorno requeridas (.env):**

```env
# Backend
SECRET_KEY=your-secret-key-here
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?appName=Cluster0
MONGODB_DB=hive_office
REDIS_URL=redis://default:password@host:port

# APIs
OPENAI_API_KEY=sk-...
SERPER_API_KEY=your-serper-key
MAILERSEND_API_KEY=mlsn-...

# Frontend
FRONTEND_URL=https://my.landatech.org
ACCESS_TOKEN_EXPIRE_MINUTES=15
```

### Frontend

```bash
cd frontend
npm install
```

## Deployment

### Local Development

```bash
# Terminal 1 — Backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001

# Terminal 2 — ARQ Worker (para async jobs)
cd backend
python -m arq worker.WorkerSettings

# Terminal 3 — Frontend
cd frontend
npm run dev
```

Abre `http://localhost:5173`

### Production (Railway)

El backend y frontend se despliegan automáticamente a Railway cuando haces push a `master`:

```bash
git add .
git commit -m "feat: your changes"
git push origin master
```

Railway detecta cambios en:
- `backend/` → rebuilds backend service, redeploy
- `frontend/dist/` → serves static files

**Deploy status:**

```bash
# Ver logs del deploy
railway logs --project=20ca37bb-eaad-4fc4-988a-4934a365096c --environment=0113fb74-7e30-4b17-9ea7-143ae6a092f9

# Build en prod
https://my.landatech.org
```

## Estructura del Proyecto

```
lambda-proyect/
├── backend/
│   ├── main.py                 # FastAPI server entry point
│   ├── database.py             # MongoDB operations
│   ├── auth.py                 # JWT + user auth
│   ├── routers/
│   │   ├── auth.py             # Auth endpoints + /auth/dev-token
│   │   ├── landa.py            # Campaign CRUD + /api/campaigns/{id}/launch
│   │   └── ...                 # Other routers
│   ├── worker.py               # ARQ worker: run_prospecting_job
│   ├── hive_adapter.py         # Hive engine adapter
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Main app + 6 views + campaign wizard
│   │   ├── api.ts              # REST client layer
│   │   ├── components/
│   │   │   ├── landa/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   └── Topbar.tsx
│   │   │   └── ...
│   │   ├── index.css           # Tailwind + custom CSS variables
│   │   └── main.tsx            # React entry point
│   ├── dist/                   # Production build (served by Railway)
│   └── package.json
│
└── README.md (you are here)
```

## API Reference

### Auth

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/dev-token` | — | Get JWT token (dev: no rate limit) |
| POST | `/auth/register` | — | Register new user |
| POST | `/auth/login` | — | Login, return JWT |

### Campaigns

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/campaigns` | JWT | List campaigns |
| POST | `/api/campaigns` | JWT | Create campaign |
| GET | `/api/campaigns/{id}` | JWT | Get campaign detail |
| POST | `/api/campaigns/{id}/launch` | JWT | Launch prospecting job (enqueue ARQ job) |
| GET | `/api/campaigns/{id}/kpis` | JWT | Get KPIs (leads_qualified, leads_approved, etc.) |

### Leads

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/campaigns/{cid}/leads` | JWT | List leads for campaign |
| GET | `/api/campaigns/{cid}/leads/{lid}` | JWT | Get lead detail |
| PATCH | `/api/campaigns/{cid}/leads/{lid}/approve` | JWT | Mark as approved |
| DELETE | `/api/campaigns/{cid}/leads/{lid}` | JWT | Delete lead |

### Runs (Prospecting Jobs)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/campaigns/{cid}/runs` | JWT | List runs (jobs) |
| GET | `/api/runs/{run_id}/status` | JWT | Poll job status |

## Flujo de Uso

### 1. Crear Campaña (Frontend)

1. Click **"Lanzar campaña"** en topbar
2. Wizard step 1: Elige pipeline (Serper / RUES / SECOP / Fincaraíz)
3. Step 2-5: Completa nombre, sectores, ciudades, ICP, leads estimados
4. Submit → `api.createCampaign()` crea el documento en MongoDB
5. `api.launchCampaign(campaignId)` enqueue un ARQ job

### 2. Prospecting Job (Backend)

ARQ worker ejecuta `run_prospecting_job`:

```python
# Hive engine descubre → analiza → genera leads
await adapter.start_run(
    user_id=user_id,
    inputs={
        "campaign": campaign,
        "use_serper": True,
        "use_rues": False,
        "use_secop": False,
        "use_fincaraiz": False,
    },
    save_lead=database.save_lead,
)
# Cada lead: save_lead(run_id, user_id, lead_data, campaign_id)
# Al final: update_run_status(run_id, "complete")
```

### 3. Review Leads (Frontend)

1. Frontend polls `/api/campaigns/{id}/leads`
2. ViewAprobados muestra tabla con company_name, decisor, ciudad, status
3. User click ✓ (approve) → `api.approveLead(campaignId, leadId)`
4. Lead status → "approved" en MongoDB

### 4. Resultados

ViewInicio muestra KPIs:
- Leads calificados
- Aprobados por ti
- Tasa de aprobación
- Enviados

## Signal-Source Pipeline Flags

Cada campaign tiene estos flags para controlar qué prospecting engines corren:

```typescript
{
  name: "Búsqueda de Arriendos",
  use_rues: false,
  use_secop: false,
  use_fincaraiz: true,  // ← only Fincaraíz
  use_serper: false,
  source_priority: "fincaraiz"
}
```

Templates en `App.tsx`:

```typescript
const PIPELINE_TEMPLATES = [
  {
    id: "serper",
    icon: "globe",
    title: "Búsqueda Web",
    use_serper: true,
    use_rues: false,
    use_secop: false,
    use_fincaraiz: false,
  },
  // ... más templates
];
```

## Development Workflow

### Local Testing

```bash
# 1. Start backend (watch for reload)
cd backend && python -m uvicorn main:app --reload

# 2. Start ARQ worker (in another terminal)
cd backend && python -m arq worker.WorkerSettings

# 3. Start frontend (hot reload)
cd frontend && npm run dev

# 4. Test in browser
curl http://localhost:8001/auth/dev-token
# → returns JWT, store in localStorage
```

### Build & Deploy

```bash
# Build frontend for production
cd frontend && npm run build
# → creates frontend/dist/

# Commit everything
git add -A
git commit -m "feat: your feature"
git push origin master
# → Railway auto-deploys
```

## Troubleshooting

### "Unauthorized — token inválido o expirado"

- Clear localStorage: `localStorage.clear(); location.reload();`
- Verify backend is running on port 8001
- Check JWT in browser console: `localStorage.getItem('token')`

### Leads not appearing after launching campaign

- Verify ARQ worker is running: `python -m arq worker.WorkerSettings`
- Check MongoDB: `db.leads.find({campaign_id: "..."})` should have docs
- Check runs collection: `db.runs.find()` should show status="complete"

### Build errors

```bash
# Clean and rebuild
cd frontend && rm -rf node_modules dist && npm install && npm run build
```

### Redis connection error

Ensure `REDIS_URL` in `.env` points to the correct Railway Redis instance:

```env
REDIS_URL=redis://default:password@zephyr.proxy.rlwy.net:45384
```

## Key Files & Sections

| File | Purpose |
|------|---------|
| `frontend/src/App.tsx:90` | ViewInicio (KPI dashboard) |
| `frontend/src/App.tsx:200+` | ViewCampanas, ViewAprobados |
| `frontend/src/App.tsx:620+` | Campaign creation wizard |
| `frontend/src/api.ts` | All REST API calls |
| `backend/routers/landa.py:250` | POST `/api/campaigns/{id}/launch` |
| `backend/worker.py:22` | `run_prospecting_job` (ARQ entry point) |
| `backend/database.py` | MongoDB save_lead, update_run_status |

## License

MIT
