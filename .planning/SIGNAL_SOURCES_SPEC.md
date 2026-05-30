# SPEC.md: Signal Sources Colombianas - Data Pipeline Local

**Phase:** Signal Sources Colombianas (Desempleo v1)  
**Version:** 1.0  
**Date:** 2026-05-30  
**Status:** SPEC for Planning  

---

## Executive Summary

This phase builds a **local Colombian signal aggregation pipeline** that:
- Replaces generic Apollo.io with data specifically optimized for Colombian insurance markets
- Aggregates 4 public data sources (RUES, Google Maps, LinkedIn, Serper) into unified `SignalLead` schema
- Enables vertical-specific lead filtering (desempleo, arrendamiento, empresarial)
- Reduces lead acquisition cost from ~$5k/month (Apollo SaaS) to ~$500/month (self-hosted infrastructure)

**Target:** 1st vertical = **Desempleo** (unemployment insurance prospects)

---

## What We're Building

### Input: Search Query
```python
@dataclass
class SignalQuery:
    vertical: str                          # 'desempleo' | 'arrendamiento' | 'empresarial'
    ciudad: str                            # 'Bogota', 'Medellín', etc
    sector_industria: Optional[str]        # CIIU code or description
    tamaño_empresa_min: int = 20           # Min employees
    tamaño_empresa_max: int = 500
    filters: dict = {}                     # Vertical-specific filters
```

### Output: Ranked Signal Leads
```python
@dataclass
class SignalLead:
    # Identity
    empresa_id: str                        # Canonical ID (RUES NIT if available)
    razon_social: str
    nit: str
    
    # Location
    ciudad: str
    departamento: str
    direccion: str
    lat_lng: Tuple[float, float]
    
    # Company Profile
    tamaño_empresa: str                    # '1-10' | '11-50' | '51-200' | '200+'
    sector_ciiu: str                       # CIIU 4-digit code
    sector_nombre: str                     # Human-readable industry
    ingresos_anuales_usd: Optional[float]  # From DIAN if available
    estado_tributario: str                 # 'Activo' | 'Suspendido' | 'Cancelado'
    
    # Decision Makers
    decisores: List[ContactSignal]         # name + email + title + confidence
    
    # Behavioral Signals
    hiring_signal: Optional[bool]          # Has job postings (LinkedIn) in last 30 days
    hiring_scale: Optional[int]            # Number of open positions
    tech_stack: Optional[List[str]]        # Observed tech: ['Salesforce', 'SAP', etc]
    
    # Vertical-Specific
    tiene_empleados_permanentes: bool      # For desempleo vertical
    tipo_contratacion: Optional[str]       # 'Directos' | 'Contratistas' | 'Mixto'
    rotacion_estimada: Optional[str]       # 'Alta' | 'Media' | 'Baja'
    
    # Metadata
    sources: List[str]                     # ['RUES', 'Google', 'LinkedIn']
    confidence_score: float                # 0-100 (weighted by sources)
    last_updated: datetime
    freshness_days: int                    # Days since last refresh
    
    # For matching
    relevance_score: float                 # 0-100 (query-specific ranking)
    match_reasons: List[str]               # ['Hiring signal', 'Size match', 'Sector match']

@dataclass
class ContactSignal:
    nombre: str
    titulo: str
    email: Optional[str]
    telefono: Optional[str]
    linkedin_url: Optional[str]
    confianza: float                       # 0-100 (accuracy of contact)
    fuente: str                            # 'RUES' | 'Google' | 'LinkedIn' | 'Directorio'
```

---

## Data Sources: Colombian Public Data

### Source 1: RUES (Registro Único Empresarial - Superintendencia)

**What:** Official Colombian business registry. All legally constituted companies.

**API:**
```
GET https://www.rues.org.co/RM/
Query params: NIT or Razón Social
Response: XML → Parse to JSON
```

**Fields extracted:**
- NIT (empresa_id canonical)
- Razón Social
- Domicilio (cidade + dirección)
- Actividad económica (CIIU)
- Fecha constitución
- Estado (Activo/Suspendido/Cancelado)

**Frequency:** Daily cron (9 PM UTC-5)  
**Cost:** Free  
**Reliability:** 99.9% (government source)  

**MongoDB collection:**
```javascript
db.rues_companies.insertOne({
  _id: ObjectId(),
  nit: "800123456",
  razon_social: "EMPRESA LTDA",
  estado: "Activo",
  ciiu: "4723",
  domicilio: { ciudad: "Bogota", departamento: "Cundinamarca", direccion: "Cra 7 #25-40" },
  fecha_constitucion: ISODate("2015-03-10"),
  last_scraped: ISODate("2026-05-30"),
  source: "rues"
})
```

---

### Source 2: Google Maps / Serper (Operational Contact Signal)

**What:** Live business listings. Phone + hours + location + employee estimates.

**Mechanism:** Already integrated via Serper API in prospector.py. Extend to:
1. Extract phone + contact email
2. Parse employee count (Google displays "~50-100 employees")
3. Detect if company is "actively hiring" (careers link on Google Business)

**Fields extracted:**
- Teléfono operativo
- Email de contacto (si visible en GMB)
- Horario de operación (signals operational vs closed)
- Estimado de empleados (Google estimates)
- Website URL
- "We're hiring" label (if present)

**Frequency:** Weekly refresh per company  
**Cost:** Already budgeted (Serper subscription)  
**Reliability:** 95% (some businesses not on Google)  

**MongoDB collection:**
```javascript
db.google_signals.insertOne({
  _id: ObjectId(),
  nit: "800123456",
  google_business_id: "ChIJ...",
  telefono: "+571234567890",
  email_operativo: "info@empresa.com",
  empleados_estimados: 75,
  hiring_detected: true,
  careers_url: "https://empresa.com/careers",
  website: "https://empresa.com",
  last_updated: ISODate("2026-05-28"),
  source: "google"
})
```

---

### Source 3: LinkedIn Signals (Hiring + Growth Patterns)

**What:** Job postings + employee count changes = hiring signal.

**Mechanism:** 
1. Query LinkedIn company page (no API, but scrapeable)
2. Extract: job postings count in last 30 days
3. Extract: employee growth (if company updated employee count)
4. Extract: recent hires (from feed if public)

**Tools:** Linkedin-api (python) OR Bright Data LinkedIn connector (if in budget)

**Fields extracted:**
- current_openings (count of active job posts)
- followers_count (estimate of company size)
- employee_count (if updated recently)
- recent_hire_count (approx hires in last 30 days)
- industry_tags (LinkedIn's classification)

**Frequency:** 2x per week  
**Cost:** $0 (scraping legal if not logged in) OR $50-200/month (Bright Data)  
**Reliability:** 90% (LinkedIn occasionally blocks scrapers)  

**MongoDB collection:**
```javascript
db.linkedin_signals.insertOne({
  _id: ObjectId(),
  nit: "800123456",
  linkedin_company_id: "12345",
  linkedin_url: "https://linkedin.com/company/empresa-ltda",
  current_job_openings: 8,
  estimated_employee_count: 65,
  hiring_signal: true,
  recent_hires_30d: 5,
  tech_mentions: ["Python", "AWS", "React"],
  last_updated: ISODate("2026-05-29"),
  source: "linkedin"
})
```

---

### Source 4: Decision Maker Discovery (Contact Enrichment)

**What:** Map empresa_id → actual human contacts at company.

**Mechanism:**
1. From RUES: Extract "Representante Legal" name
2. From Google: Extract business phone, call and ask for "Gerente General" (common Colombian title)
3. From LinkedIn: Extract company employees with titles (Gerente, Director, etc)
4. From email patterns: Generate probable email addresses (firstname.lastname@empresa.com)

**Fields extracted:**
- nombre
- titulo (Gerente General, Director, etc)
- email (confirmed if LinkedIn or found in web search)
- telefono (from Google Business or LinkedIn)

**Frequency:** On-demand (per lead query)  
**Cost:** $0-50/month (if using email validation service)  
**Reliability:** 70% (contact info often private in Colombia)  

**MongoDB collection:**
```javascript
db.decisores.insertOne({
  _id: ObjectId(),
  nit: "800123456",
  nombre: "Juan García",
  titulo: "Gerente General",
  email: "jgarcia@empresa.com",
  email_confianza: 85,
  telefono: "+571234567890",
  linkedin_url: "https://linkedin.com/in/jgarcia",
  sources: ["LinkedIn", "Email validation"],
  last_verified: ISODate("2026-05-25")
})
```

---

## Data Processing Pipeline

```
┌─ Trigger: /api/signals/search?vertical=desempleo&ciudad=Bogota ──┐
│                                                                    │
├─ PHASE 1: Query Dispatch (Parallel)                               │
│  ├─ RUES Searcher                                                 │
│  │  └─ Search for "Empresa sector 4723 en Bogota tamaño 50-100"  │
│  │     └─ Return [50 RUES entities]                              │
│  │                                                                │
│  ├─ Google Maps Searcher                                          │
│  │  └─ Search for "Oficina tamaño empresa Bogota CIIU 4723"     │
│  │     └─ Return [30 Google entities]                            │
│  │                                                                │
│  ├─ LinkedIn Searcher                                             │
│  │  └─ Search for "Jobs in Bogota hiring sector 4723"           │
│  │     └─ Return [20 LinkedIn entities]                          │
│  │                                                                │
│  └─ Directorio Searcher (fallback)                               │
│     └─ Query yellowpages-equivalent or Chamber of Commerce       │
│        └─ Return [10 directory entities]                         │
│                                                                  │
├─ PHASE 2: Deduplication Engine                                  │
│  └─ Match same company across sources:                           │
│     1. By NIT (exact match)                                      │
│     2. By Razón Social (fuzzy match >90% similarity)             │
│     3. By lat/lng proximity + name (for partial matches)         │
│     └─ Output: Canonical SignalLead list [50 unique leads]      │
│                                                                  │
├─ PHASE 3: Enrichment Pipeline                                   │
│  ├─ For each canonical lead:                                     │
│  │  ├─ Fetch RUES details (if NIT exists)                       │
│  │  ├─ Fetch Google signals (phone, employees, hiring)          │
│  │  ├─ Fetch LinkedIn signals (jobs, growth)                    │
│  │  ├─ Extract decisores (Gerente + contacts)                   │
│  │  └─ Calculate confidence_score (weighted by sources)         │
│  │                                                               │
│  └─ Output: Enriched SignalLead list [50 complete profiles]    │
│                                                                  │
├─ PHASE 4: Vertical-Specific Filtering                           │
│  └─ For DESEMPLEO vertical:                                      │
│     ├─ Filter: tamaño >= 50 (employees)                         │
│     ├─ Filter: hiring_signal = true (recruiting now)           │
│     ├─ Filter: estado_tributario = 'Activo'                    │
│     ├─ Filter: NOT [agency/temp work/outsourcing]              │
│     └─ Output: [25 qualified leads]                             │
│                                                                  │
├─ PHASE 5: Relevance Ranking                                     │
│  └─ Score each lead:                                             │
│     score = (                                                    │
│       0.3 × hiring_signal_strength +  # Most important          │
│       0.2 × company_size_match +                                │
│       0.2 × confidence_score +                                  │
│       0.15 × recency_of_data +                                  │
│       0.15 × industry_match                                      │
│     )                                                            │
│     └─ Sort descending, return top 20                           │
│                                                                  │
└─ RESPONSE: Ranked leads to user ────────────────────────────────┘
```

---

## API Endpoints

### 1. Search Signals
```http
POST /api/signals/search
Content-Type: application/json

{
  "vertical": "desempleo",
  "ciudad": "Bogota",
  "sector_industria": "4723",  # Optional
  "tamaño_empresa_min": 50,
  "filters": {
    "hiring_signal_required": true,
    "min_confidence": 70
  },
  "limit": 20
}

Response 200:
{
  "total": 45,
  "returned": 20,
  "leads": [
    {
      "empresa_id": "800123456",
      "razon_social": "EMPRESA LTDA",
      "ciudad": "Bogota",
      "tamaño_empresa": "51-200",
      "decisores": [
        {
          "nombre": "Juan García",
          "titulo": "Gerente General",
          "email": "jgarcia@empresa.com",
          "confianza": 85
        }
      ],
      "hiring_signal": true,
      "relevance_score": 92,
      "match_reasons": ["Recent hiring activity", "Size match", "Active tax status"],
      "sources": ["RUES", "LinkedIn", "Google"]
    }
    // ... 19 more
  ]
}
```

### 2. Get Signal Details
```http
GET /api/signals/{empresa_id}

Response 200:
{
  "empresa_id": "800123456",
  "razon_social": "EMPRESA LTDA",
  "nit": "800123456",
  "rues_data": {
    "estado": "Activo",
    "ciiu": "4723",
    "fecha_constitucion": "2015-03-10",
    "domicilio": { ... }
  },
  "google_data": {
    "telefono": "+571234567890",
    "empleados_estimados": 75,
    "hiring_detected": true,
    "website": "https://empresa.com"
  },
  "linkedin_data": {
    "current_job_openings": 8,
    "recent_hires_30d": 5,
    "tech_stack": ["Python", "AWS"]
  },
  "decisores": [ ... ],
  "last_updated": "2026-05-30T10:30:00Z"
}
```

### 3. Verify Contact
```http
POST /api/signals/{empresa_id}/verify-contact
Content-Type: application/json

{
  "nombre": "Juan García",
  "email": "jgarcia@empresa.com",
  "metodo": "email_validation"  # or "phone_call"
}

Response 200:
{
  "contact_id": "...",
  "verified": true,
  "confidence": 92,
  "method_used": "email_validation",
  "timestamp": "2026-05-30T11:00:00Z"
}
```

---

## Database Schema

### Collections to Create

```javascript
// 1. Colombian companies master data
db.createCollection("signal_leads", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["empresa_id", "razon_social", "nit", "ciudad"],
      properties: {
        _id: { bsonType: "objectId" },
        empresa_id: { bsonType: "string", description: "Canonical ID" },
        razon_social: { bsonType: "string" },
        nit: { bsonType: "string" },
        ciudad: { bsonType: "string" },
        tamaño_empresa: { enum: ["1-10", "11-50", "51-200", "200+"] },
        sector_ciiu: { bsonType: "string" },
        estado_tributario: { enum: ["Activo", "Suspendido", "Cancelado"] },
        hiring_signal: { bsonType: "bool" },
        confidence_score: { bsonType: "double" },
        sources: { bsonType: "array" },
        last_updated: { bsonType: "date" }
      }
    }
  }
})

// 2. Decision makers per company
db.createCollection("signal_decisores")

// 3. RUES raw data cache
db.createCollection("rues_raw_cache")

// 4. Google signals cache
db.createCollection("google_signals_cache")

// 5. LinkedIn signals cache
db.createCollection("linkedin_signals_cache")

// Indexes
db.signal_leads.createIndex({ "nit": 1 }, { unique: true })
db.signal_leads.createIndex({ "ciudad": 1, "sector_ciiu": 1 })
db.signal_leads.createIndex({ "hiring_signal": 1, "confidence_score": -1 })
db.signal_leads.createIndex({ "last_updated": -1 })
```

---

## Implementation Constraints

### In Scope
- ✅ RUES scraper (daily)
- ✅ Google Maps enrichment (already have Serper)
- ✅ LinkedIn signal extraction (2x/week)
- ✅ Decision maker extraction
- ✅ Deduplication logic
- ✅ Vertical-specific filtering (desempleo v1)
- ✅ Search API + ranking
- ✅ MongoDB schema

### Out of Scope (v2+)
- ❌ Tax records from DIAN (restricted access)
- ❌ Phone verification calls (too expensive initially)
- ❌ Email validation service integration (add later if ROI justifies)
- ❌ Arrendamiento + Empresarial verticals (do desempleo first, then iterate)

---

## Success Criteria

1. ✓ 50+ Colombian companies indexed in MongoDB with complete SignalLead profile
2. ✓ Search API returns top 20 leads ranked by relevance in <2s
3. ✓ Hiring signal detection accurate (>80% precision for "actively hiring" companies)
4. ✓ Decision maker extraction captures ≥70% of companies with valid contact
5. ✓ Deduplication engine correctly merges same company across sources (0 duplicates in results)
6. ✓ Desempleo vertical filter: returns only companies with +50 employees + active hiring

---

## Effort Estimate

| Component | Effort | Owner |
|-----------|--------|-------|
| RUES scraper | 3 days | Backend |
| Google enrichment | 2 days | Backend |
| LinkedIn extractor | 3 days | Backend |
| Decisores extractor | 2 days | Backend |
| Deduplication engine | 2 days | Backend |
| Search API + ranking | 3 days | Backend |
| MongoDB schema | 1 day | Backend |
| Testing + QA | 2 days | QA |
| **Total** | **18 days** | **1 dev + QA** |

---

## Next Step: Planning

Ready for `/gsd-discuss-phase` to:
1. Validate signal sources and RUES access strategy
2. Confirm decision maker extraction approach
3. Finalize desempleo vertical filtering rules
4. Lock API contract before implementation

