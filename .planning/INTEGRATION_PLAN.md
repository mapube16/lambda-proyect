# Integration Map: Signal Sources ↔ Existing Architecture

## Current Pipeline (Fases 1-23)

```
User submits campaign
        ↓
enqueue_job(tenant_id, vertical)
        ↓
[ARQ Worker]
        ↓
├─ Buscador         ← Google Maps + Serper (actual)
├─ Scraper          ← curl_cffi + Crawl4AI (actual)
├─ Analista B2B     ← GPT-4o con personalidad.md (actual)
└─ Redactor         ← GPT-4o pitch (actual)
        ↓
MongoDB + WebSocket broadcast
```

---

## Proposed Extension: Signal Sources Layer

El SPEC de Signal Sources **REEMPLAZA y EXTIENDE el Buscador**, NO reinventa la rueda:

```
User submits campaign (con vertical seleccionado)
        ↓
enqueue_job(tenant_id, vertical='desempleo')  ← ⭐ Vertical es nuevo
        ↓
[ARQ Worker]
        ↓
├─ Buscador 2.0         ← ⭐ NUEVA: Signal Sources (RUES + Google + LinkedIn)
│  ├─ RUES Searcher      │
│  ├─ Google Enricher    │ (Reusa Serper existente)
│  ├─ LinkedIn Signals   │ (Nuevo)
│  ├─ Decisores Extract  │ (Nuevo)
│  └─ Ranking Engine     │ (Nuevo: relevance score)
│
├─ Scraper          ← curl_cffi + Crawl4AI (SIN CAMBIOS)
│
├─ Analista B2B     ← GPT-4o con prompts ADAPTADOS POR VERTICAL (Modificado)
│  └─ Si vertical='desempleo', prompt incluye: "Valida: ¿tienen empleados permanentes? ¿qué rotación estimas?"
│
└─ Redactor         ← GPT-4o pitch ADAPTADO POR VERTICAL (Modificado)
   └─ Si vertical='desempleo', genera: "Seguro de desempleo para X empleados"
        ↓
MongoDB (con tenant_id + vertical) + WebSocket broadcast
```

---

## How Signal Sources Integrates

### Current Buscador (Existing)
```python
# backend/prospector.py current
def run_buscador(campaign, ciudad):
    """Find companies via Google Maps → Serper API"""
    urls = serper_search(f"empresa {campaign['industria_objetivo']} {ciudad}")
    return urls  # List of 10-20 URLs
```

### New Buscador 2.0 (Extended)
```python
# backend/prospector.py (MODIFIED)
from signal_sources import SignalSourceRegistry

def run_buscador(campaign, ciudad, vertical, tenant_id):
    """Find companies via MULTIPLE sources + rank by vertical"""
    
    # Signal Sources Pipeline (NEW)
    signal_registry = SignalSourceRegistry()
    signal_leads = await signal_registry.search(
        query=SignalQuery(
            vertical=vertical,  # 'desempleo' | 'arrendamiento' | 'empresarial'
            ciudad=ciudad,
            sector_industria=campaign.get('sector_ciiu'),
            tamaño_empresa_min=campaign.get('tamaño_min', 50),
            filters=VERTICAL_FILTERS[vertical]
        ),
        tenant_id=tenant_id
    )
    
    # Convert SignalLead → URLs (for backward compatibility with Scraper)
    urls = [lead.website for lead in signal_leads if lead.website]
    
    # ENHANCE: Attach signal metadata to each URL for downstream use
    enriched_urls = [
        {
            'url': lead.website,
            'empresa_id': lead.empresa_id,
            'decisores': lead.decisores,  # ← Scraper can pre-inject these
            'hiring_signal': lead.hiring_signal,
            'confidence': lead.confidence_score
        }
        for lead in signal_leads
    ]
    
    return enriched_urls  # Enhanced with metadata
```

---

## Integration Points: What Stays, What Changes

### ✅ STAYS THE SAME
| Component | Why |
|-----------|-----|
| **ARQ Worker** | Perfect para async job queueing |
| **curl_cffi + Crawl4AI** | Best-in-class scraping (Fase 20 optimized) |
| **Prompts base** | Keep personalidad.md structure |
| **WebSocket broadcast** | Just add tenant_id to channel |
| **MongoDB** | Just add tenant_id + vertical fields |
| **Redis pub/sub** | Just namespace by tenant_id |

### 🔄 GETS EXTENDED
| Component | What Changes | Why |
|-----------|--------------|-----|
| **Buscador** | Add signal sources pipeline | Replace single-source (Google) with multi-source |
| **Analista prompts** | Add vertical-specific context | "¿Tienen desempleados? ¿Cuántos?" for desempleo |
| **Redactor prompts** | Add vertical-specific pitch | "Seguro desempleo" vs "Arrendamiento" copy |
| **Campaign schema** | Add `vertical` field | So user selects vertical before launching |
| **Lead schema** | Add `vertical` + `signal_source` fields | Track which source found this lead |
| **Cost tracking** | Track by signal source | RUES=free, LinkedIn=scrap cost, etc |

### 🆕 NEW COMPONENTS (Isolated)
| Component | Purpose | Impact |
|-----------|---------|--------|
| **signal_sources.py** | RUES + Google + LinkedIn aggregation | New module, doesn't touch existing code |
| **SignalSourceRegistry** | Pluggable interface for sources | Extensible for arrendamiento + empresarial later |
| **VERTICAL_FILTERS dict** | Per-vertical filtering rules | Config, not code |
| **signal_leads collection** | MongoDB caching of signal data | New collection, no schema changes to existing |

---

## Concrete Implementation: Minimal Changes to Existing Code

### 1. Models (Add 2 lines)
```python
# backend/models.py
@dataclass
class Campaign:
    name: str
    user_id: str
    vertical: str = 'desempleo'      # ← NEW (with default)
    tenant_id: str = None             # ← Already needed for Phase 19
    # ... rest stays same
```

### 2. Prospector (Replace 1 function)
```python
# backend/prospector.py
async def run_prospect(campaign, run_id, tenant_id):
    """Main 4-stage pipeline"""
    
    # Stage 1: Buscador (MODIFIED to use Signal Sources)
    if ENABLE_SIGNAL_SOURCES:  # Feature flag for gradual rollout
        from signal_sources import SignalSourceRegistry
        registry = SignalSourceRegistry()
        urls = await registry.search(campaign, tenant_id)
    else:
        # Fallback to Google-only (current code)
        urls = await serper_search(campaign)
    
    # Stages 2-4: Same as before
    for url in urls:
        lead = await stage_2_scraper(url, tenant_id)
        analyzed = await stage_3_analyzer(lead, campaign, tenant_id)
        redacted = await stage_4_redactor(analyzed, campaign, tenant_id)
        yield redacted
```

### 3. Worker (Add tenant_id to Redis channel)
```python
# backend/worker.py (already uses tenant_id per Phase 19)
# Just ensure channel is: ws:{tenant_id}:{run_id}
# No changes needed if Phase 19 is done correctly
```

### 4. Frontend (Show vertical selector)
```typescript
// frontend/src/CampaignForm.tsx
<select name="vertical" onChange={(e) => setCampaign({...campaign, vertical: e.target.value})}>
  <option value="desempleo">Desempleo</option>
  <option value="arrendamiento">Arrendamiento (Coming Soon)</option>
  <option value="empresarial">Empresarial (Coming Soon)</option>
</select>
```

---

## Dependency Chain: What Must Happen First

```
Phase 19: Multi-tenant isolation (BLOCKER for Signal Sources)
    ↓ (provides tenant_id infrastructure)
Phase 24: Signal Sources Colombianas (NEW)
    ├─ RUES scraper
    ├─ LinkedIn extractor
    ├─ Decisores discovery
    └─ Search API
        ↓ (feeds into existing pipeline)
Phase 25: Vertical-Specific Prompts (MODIFICATION)
    ├─ Analista B2B prompt per vertical
    └─ Redactor prompt per vertical
        ↓ (uses vertical from campaign)
Phase 26: Testing + Desempleo MVP (VALIDATION)
    └─ End-to-end test: campaign creation → Signal Sources → Scraper → Analysis
```

---

## Effort Re-estimate (Integrated View)

| Phase | Component | New Effort | Reuses | Total |
|-------|-----------|-----------|--------|-------|
| 19 | Multi-tenant | 5 days | All existing | 5 days |
| 24 | Signal Sources | 18 days | Serper API | 18 days |
| 25 | Vertical Prompts | 2 days | personalidad.md | 2 days |
| 26 | Validation | 3 days | pytest | 3 days |
| **Total** | **Full Integration** | **28 days** | **High reuse** | **28 days** |

**vs Apollo SaaS:**
- Apollo: $5,000/month (50 brokers)
- Build: ~28 days (1 dev) = $7,000 cost, ROI in 6 weeks
- **Break-even: Month 2, profit thereafter**

---

## Architecture Diagram: Integrated Flow

```
┌─ Frontend ─────────────────────────────────────────────┐
│                                                         │
│  Campaign Form (MODIFIED)                              │
│  ├─ vertical: 'desempleo' | 'arrendamiento' | etc ← NEW│
│  ├─ sector_industria                                   │
│  └─ POST /api/prospect                                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
             ↓
     POST /api/prospect
        (tenant_id, vertical)
             ↓
┌─ API Layer (FastAPI) ──────────────────────────────────┐
│                                                         │
│  POST /api/prospect                                    │
│  └─ enqueue_job(tenant_id, vertical, campaign) → ARQ  │
│                                                         │
└─────────────────────────────────────────────────────────┘
             ↓
┌─ Redis ────────────────────────────────────────────────┐
│                                                         │
│  Job Queue: {tenant_id}:{run_id}                      │
│  Pub/Sub: ws:{tenant_id}:{run_id}                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
             ↓
┌─ ARQ Worker Pool ──────────────────────────────────────┐
│                                                         │
│  run_prospect(tenant_id, vertical, campaign)          │
│                                                         │
│  Stage 1: Buscador 2.0 (NEW SIGNAL SOURCES)           │
│  ├─ SignalSourceRegistry.search()                     │
│  ├─ RUES + Google + LinkedIn → SignalLead[]           │
│  └─ Filter by vertical (hiring_signal, size, etc)     │
│     └─ URLs → Scraper (with decisores metadata)       │
│                                                         │
│  Stage 2: Scraper (UNCHANGED)                         │
│  ├─ curl_cffi Chrome131                               │
│  ├─ Crawl4AI compress                                 │
│  └─ Extract text + contacts                           │
│                                                         │
│  Stage 3: Analista B2B (MODIFIED)                     │
│  ├─ Prompt includes vertical context                  │
│  ├─ "For desempleo: validate permanent employees"     │
│  └─ Score 0-100                                       │
│                                                         │
│  Stage 4: Redactor (MODIFIED)                         │
│  ├─ Prompt includes vertical pitch                    │
│  ├─ "Generate desempleo insurance email"              │
│  └─ Return formatted lead                             │
│                                                         │
│  → Publish to ws:{tenant_id}:{run_id}                │
│     [Real-time updates to frontend]                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
             ↓
┌─ MongoDB ──────────────────────────────────────────────┐
│                                                         │
│  leads:                                                │
│  ├─ tenant_id (Phase 19)                              │
│  ├─ vertical (NEW)                                     │
│  ├─ signal_source (NEW: 'RUES', 'LinkedIn', etc)      │
│  ├─ empresa_id (for dedup)                            │
│  ├─ decisores (pre-populated from signals)            │
│  └─ email_draft                                        │
│                                                         │
│  signal_leads (NEW collection):                        │
│  └─ Cached Signal Lead profiles for reuse             │
│                                                         │
└─────────────────────────────────────────────────────────┘
             ↓
┌─ Frontend (Real-time WebSocket) ──────────────────────┐
│                                                         │
│  Live Office Canvas                                    │
│  ├─ Character animation per stage                     │
│  ├─ Real-time lead cards as they arrive               │
│  └─ Score badges + email draft preview                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Rollout Strategy

### Week 1: Phase 19 (Multi-tenant) ✓
- Add tenant_id to all collections
- Refactor all queries
- Ensure Redis channels are namespaced

### Week 2: Phase 24 (Signal Sources) ← YOU ARE HERE
- Implement RUES scraper
- Implement LinkedIn extractor
- Implement decisores discovery
- Deploy behind feature flag: `ENABLE_SIGNAL_SOURCES=false` (default)

### Week 3: Phase 25 (Vertical Prompts)
- Refactor personalidad.md into vertical variants
- Modify Analista + Redactor to use vertical context

### Week 4: Phase 26 (Validation)
- Feature flag: `ENABLE_SIGNAL_SOURCES=true`
- End-to-end test with desempleo vertical
- Demo to customer

---

## Summary: You're NOT Starting From Scratch

✅ **Reuse existing:**
- FastAPI + ARQ worker infrastructure
- curl_cffi + Crawl4AI scraping
- HiveOrchestrator + WebSocket broadcast
- personalidad.md prompt framework
- MongoDB + Redis stack
- Frontend office canvas

🆕 **Add only:**
- Signal Sources layer (modular, isolated)
- Vertical selection in campaign
- Vertical-specific prompt context
- Multi-tenant isolation (Phase 19 prerequisite)

**Result:** 28 days → Fully integrated desempleo MVP that reuses 90% of existing architecture

¿Vamos a planificar las fases de integración entonces?
