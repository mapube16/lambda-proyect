# Arquitectura de Integración: Stack de Prospección B2B

**Proyecto:** Lambda Proyect  
**Objetivo:** Prospección B2B escalable y automatizada  
**Versión:** 1.0  
**Estado:** Ready for Implementation

---

## 🏗️ Arquitectura de Sistema Recomendada

```
┌─────────────────────────────────────────────────────────────────┐
│                     LAMBDA PROSPECTING STACK                     │
└─────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ CAPA 1: DESCUBRIMIENTO & VALIDACIÓN (Discovery Layer)          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Hunter.io API                                            │  │
│  │ ├─ Email Finder (contactos)                             │  │
│  │ ├─ Domain Search (búsquedas por dominio)                │  │
│  │ ├─ Email Verifier (verificación real-time)             │  │
│  │ └─ Integration: REST API + Python SDK                  │  │
│  │                                                          │  │
│  │ Output: [email, first_name, last_name, position,       │  │
│  │          company, linkedin_url, confidence]            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ZeroBounce API                                           │  │
│  │ ├─ Validación con 99.6% accuracy                        │  │
│  │ ├─ Detección spam traps                                │  │
│  │ ├─ IP geolocation                                      │  │
│  │ └─ Batch processing (100k/hora)                        │  │
│  │                                                          │  │
│  │ Output: [status: valid/invalid, confidence, etc]       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│ Status: ✅ RECOMENDADO                                         │
│ Costo: ~$140/mes                                               │
│ Latencia: Real-time                                            │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ CAPA 2: ENRIQUECIMIENTO & SCORING (Enrichment Layer)          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Apollo (Optional) o Clearbit (Enterprise)               │ │
│  │ ├─ Datos firmográficos                                 │ │
│  │ ├─ Información sobre inversión                         │ │
│  │ ├─ Datos de crecimiento                                │ │
│  │ └─ Integración: REST API                               │ │
│  └──────────────────────────────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Lead Scoring Engine (HubSpot/Custom)                    │ │
│  │ ├─ Score de 0-100                                      │ │
│  │ ├─ Basado en firmographics                             │ │
│  │ ├─ Basado en company intent (optional)                 │ │
│  │ └─ Output: prospects_scored collection                 │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Status: ⭐ OPTIONAL                                            │
│ Costo: $0 (Apollo included) - $500+ (Clearbit)               │
│ Latencia: < 2 segundos                                        │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ CAPA 3: PERSONALIZACIÓN & TIMING (Orchestration Layer)        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Mailgun API (Email Sending)                            │ │
│  │ ├─ Envío personalizado                                 │ │
│  │ ├─ A/B testing (subject lines)                         │ │
│  │ ├─ Open/Click tracking                                 │ │
│  │ ├─ Timing optimization                                 │ │
│  │ └─ DKIM/SPF management                                 │ │
│  │                                                         │ │
│  │ Inputs: [email, subject_template, html_template,      │ │
│  │          personalization_vars]                        │ │
│  │ Output: [message_id, timestamp, status]               │ │
│  └──────────────────────────────────────────────────────────┘ │
│                           │                                     │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Chili Piper (Optional - Routing & Scheduling)          │ │
│  │ ├─ Routing automático de respuestas                    │ │
│  │ ├─ Meeting scheduling                                  │ │
│  │ ├─ No-show management                                  │ │
│  │ └─ Integración: Salesforce, HubSpot                    │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Status: ✅ RECOMENDADO                                        │
│ Costo: $35-150/mes (Mailgun) + $1,250/mes (Chili Piper opt) │
│ Latencia: < 1 segundo                                         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ CAPA 4: MULTICANAL (Multi-Channel Layer)                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ LinkedIn    │  │ WhatsApp/SMS │  │ Llamadas de Voz    │   │
│  │ (Manual)    │  │ (Twilio)     │  │ (Vapi)             │   │
│  │             │  │              │  │                    │   │
│  │ Integración │  │ Integración: │  │ Integración:       │   │
│  │ manual a    │  │ REST API     │  │ REST API + Webhook │   │
│  │ través de   │  │              │  │                    │   │
│  │ UI LinkedIn │  │ Precio:      │  │ Precio:            │   │
│  │             │  │ $0.008/SMS   │  │ $0.05/min hosting  │   │
│  │ Precio: $0  │  │ $0.03-0.05/  │  │ + model costs      │   │
│  │             │  │ WhatsApp msg │  │                    │   │
│  └─────────────┘  └──────────────┘  └────────────────────┘   │
│                                                                │
│ Status: ⭐ OPCIONAL (implementar post-email base)             │
│ Costo: $0 + $0.05/msg + $0.05/min                            │
│ Latencia: < 5 segundos (SMS), < 2s (Llamadas)               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ CAPA 5: DATASTORE & ANALYTICS (Core Infrastructure)           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ CRM Central (HubSpot/Salesforce)                        │ │
│  │ ├─ Source of truth para todos los datos               │ │
│  │ ├─ Sincronización bi-directional                       │ │
│  │ ├─ Custom fields para tracking                         │ │
│  │ └─ Integración: REST API + Webhooks                    │ │
│  └──────────────────────────────────────────────────────────┘ │
│                           │                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Base de Datos (PostgreSQL/MongoDB)                     │ │
│  │ ├─ prospects table                                     │ │
│  │ ├─ campaigns table                                     │ │
│  │ ├─ emails_sent table                                   │ │
│  │ ├─ email_interactions table                            │ │
│  │ └─ webhook_events table                                │ │
│  └──────────────────────────────────────────────────────────┘ │
│                           │                                     │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Analytics Engine (Metabase/Looker)                     │ │
│  │ ├─ Email metrics (open rate, click rate)              │ │
│  │ ├─ Conversion funnel                                   │ │
│  │ ├─ ROI por campaña                                     │ │
│  │ └─ Dashboards reales                                   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│ Status: ✅ CRÍTICO                                            │
│ Costo: Incluido en infraestructura existente                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Flujo de Datos (Data Flow)

### Paso 1: Descubrimiento
```
Input: Company domains to prospect
    ↓
Hunter.io: Search emails by domain
    ↓
Output: [email, first_name, company, position, confidence]
    ↓
Database: Save as prospects_raw (status: discovered)
```

### Paso 2: Validación
```
Input: prospects_raw with emails
    ↓
ZeroBounce: Validate emails
    ↓
Output: [status: valid/invalid, confidence]
    ↓
Filter: Keep only valid emails
    ↓
Database: Update status to "validated"
```

### Paso 3: Enriquecimiento (Optional)
```
Input: Validated emails + company
    ↓
Apollo/Clearbit: Get company data
    ↓
Output: [funding, revenue, growth, industry]
    ↓
Database: Enrich prospects with company data
    ↓
Custom Scoring: Calculate lead score (0-100)
    ↓
Database: Update status to "scored"
```

### Paso 4: Personalización
```
Input: prospects (status: scored, score > 50)
    ↓
Template Engine: Personalize subject + body
    ↓
Mailgun: Send email with tracking
    ↓
Database: 
  - Insert: emails_sent
  - Update: prospect.last_email_sent
  - Status: email_sent
    ↓
Webhook: Mailgun → Your Server
  - On open: Update email_interactions
  - On click: Update email_interactions
  - On bounce: Mark as invalid
```

### Paso 5: Follow-up
```
Check: Day 3 → Email 2
Check: Day 5 → LinkedIn message (manual)
Check: Day 7 → Email 3
Check: Day 10 → WhatsApp message (if consent)
Check: Day 14 → Phone call (if no response, Vapi)
```

---

## 🗄️ Esquema de Base de Datos

### Tabla: `prospects`
```sql
CREATE TABLE prospects (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    position VARCHAR(200),
    company VARCHAR(200),
    company_domain VARCHAR(255),
    company_size VARCHAR(50),
    industry VARCHAR(100),
    confidence_score INT,  -- 0-100
    lead_score INT,        -- 0-100 (calculated)
    source VARCHAR(50),    -- hunter, apollo, etc
    status VARCHAR(50),    -- discovered, validated, scored, emailed, replied, etc
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    email_sent_at TIMESTAMP,
    last_opened_at TIMESTAMP,
    last_clicked_at TIMESTAMP,
    replied_at TIMESTAMP,
    meeting_scheduled_at TIMESTAMP,
    
    -- Custom fields
    hunter_confidence FLOAT,
    zerobounce_status VARCHAR(50),
    zerobounce_confidence FLOAT,
    
    -- Tracking
    email_open_count INT DEFAULT 0,
    email_click_count INT DEFAULT 0,
    linkedin_connected BOOLEAN DEFAULT FALSE,
    linkedin_messaged BOOLEAN DEFAULT FALSE
);
```

### Tabla: `email_campaigns`
```sql
CREATE TABLE email_campaigns (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    template_subject VARCHAR(500),
    template_body TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50),  -- draft, active, completed
    
    -- Stats
    total_sent INT DEFAULT 0,
    total_opened INT DEFAULT 0,
    total_clicked INT DEFAULT 0,
    total_replied INT DEFAULT 0,
    
    -- Tracking
    a_b_test_variant VARCHAR(50),  -- A, B, etc
    optimal_send_time VARCHAR(50)  -- 10am, 2pm, etc
);
```

### Tabla: `email_interactions`
```sql
CREATE TABLE email_interactions (
    id SERIAL PRIMARY KEY,
    prospect_id INT REFERENCES prospects(id),
    campaign_id INT REFERENCES email_campaigns(id),
    message_id VARCHAR(255),  -- Mailgun message ID
    
    -- Events
    sent_at TIMESTAMP,
    opened_at TIMESTAMP,
    clicked_at TIMESTAMP,
    bounced_at TIMESTAMP,
    
    -- Metadata
    open_count INT DEFAULT 0,
    click_count INT DEFAULT 0,
    user_agent VARCHAR(255),
    ip_address VARCHAR(50),
    
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Tabla: `webhook_events`
```sql
CREATE TABLE webhook_events (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50),  -- mailgun, vapi, twilio
    event_type VARCHAR(100),  -- delivered, opened, clicked, called
    payload JSONB,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🔗 Integraciones API

### Hunter.io Integration

```python
# Endpoints principales
GET /domain-search      # Buscar contactos por dominio
GET /email-verifier     # Verificar email individual
POST /domain-search     # Batch search

# Rate limits
- Free: 50 requests/mes
- Starter: 2,000 requests/mes
- Growth: 10,000 requests/mes
- Scale: 25,000 requests/mes
```

### Mailgun Integration

```python
# Endpoints principales
POST /messages              # Enviar email
GET /events                 # Obtener eventos (opens, clicks)
POST /lists                 # Crear listas
POST /lists/{id}/members    # Agregar contactos

# Rate limits
- Unlimited (basado en plan de pago)
- Webhooks para tracking en tiempo real
```

### ZeroBounce Integration

```python
# Endpoints principales
POST /v2/validatebatch      # Batch validation
GET /v2/validateemail       # Single email validation
GET /v2/scoring             # AI Scoring

# Rate limits
- 1,000 requests/hora por API key
```

### Twilio Integration (SMS/WhatsApp)

```python
# Endpoints principales
POST /Accounts/{sid}/Messages              # Enviar SMS/WhatsApp
GET /Accounts/{sid}/Messages/{sid}         # Status mensaje
GET /Accounts/{sid}/IncomingPhoneNumbers   # Números disponibles

# Rate limits
- Unlimited (basado en plan de pago)
```

### Vapi Integration (Llamadas)

```python
# Endpoints principales
POST /call                  # Iniciar llamada
GET /call/{id}              # Status llamada
POST /call/{id}/transfer    # Transferir llamada
POST /call/{id}/hang-up     # Terminar llamada

# Rate limits
- Unlimited (basado en plan de pago)
- Webhooks para eventos de llamada
```

---

## 🛠️ Stack Tecnológico Recomendado

### Backend
```
- Framework: FastAPI (Python) o Node.js/Express
- Database: PostgreSQL (datos transaccionales)
- Cache: Redis (rate limiting, cache)
- Queue: Celery/Bull (procesamiento async)
- Logging: ELK Stack o Datadog
```

### Frontend
```
- Dashboard: React + Recharts (Analytics)
- CRM UI: Salesforce/HubSpot (embebido)
- Admin Panel: Next.js + TypeScript
```

### Infraestructura
```
- Hosting: AWS EC2/Lambda o Railway/Render
- CDN: CloudFront
- DNS: Route53
- Monitoring: Datadog/New Relic
- CI/CD: GitHub Actions/GitLab CI
```

---

## 📋 Checklist de Implementación

### Fase 1: Setup Base (1 semana)
- [ ] Registrarse en Hunter.io (Growth plan)
- [ ] Registrarse en ZeroBounce
- [ ] Registrarse en Mailgun
- [ ] Obtener API keys
- [ ] Setup variables de entorno
- [ ] Crear base de datos PostgreSQL

### Fase 2: Integración Backend (1-2 semanas)
- [ ] Implementar Hunter.io client
- [ ] Implementar ZeroBounce client
- [ ] Implementar Mailgun client
- [ ] Crear modelos de DB (prospects, campaigns, interactions)
- [ ] Crear endpoints REST para discoverer/validator/sender
- [ ] Implementar rate limiting

### Fase 3: Email Sequences (1 semana)
- [ ] Crear templates de email personalizados
- [ ] Implementar template rendering con variables
- [ ] A/B testing framework
- [ ] Timing optimization logic
- [ ] Webhook handlers para Mailgun

### Fase 4: Analytics (1 semana)
- [ ] Dashboard de métricas (open rate, click rate)
- [ ] Reporte de ROI
- [ ] Exportar datos a CSV
- [ ] Alertas (low open rate, etc)

### Fase 5: Multicanal (2-3 semanas)
- [ ] Integrar Twilio (SMS)
- [ ] Integrar Vapi (llamadas)
- [ ] LinkedIn manual sequencing guide
- [ ] WhatsApp Business API (optional)

### Fase 6: Production (1 semana)
- [ ] Testing completo
- [ ] Load testing
- [ ] Security audit
- [ ] Documentation
- [ ] Deploy a producción

---

## 🚀 Plan de Rollout

### Week 1-2: MVP
```
✅ Hunter.io + Mailgun running
✅ Basic prospect discovery working
✅ Email sending with tracking
✅ Dashboard de métricas básico
```

### Week 3-4: v1.0
```
✅ ZeroBounce validation integrado
✅ Chili Piper routing (optional)
✅ A/B testing de subject lines
✅ Analytics completo
```

### Week 5-6: v2.0
```
✅ Twilio SMS/WhatsApp integrado
✅ Vapi voice calling integrado
✅ LinkedIn sequencing guide
✅ Advanced lead scoring
```

### Month 2+: Optimization
```
✅ Timing optimization por timezone
✅ Personalization engine mejorado
✅ Intent signals (Clearbit/Apollo)
✅ Chili Piper meeting orchestration
```

---

## 💰 Costos Mensales Estimados

### Mínimo (MVP)
```
Hunter.io Growth:      $104
Mailgun:                $35
PostgreSQL (AWS RDS):   $20
Compute (AWS/Railway):  $50
Total:                $209/mes
```

### Estándar (v1.0)
```
Hunter.io Scale:       $209
ZeroBounce:            $100
Mailgun:                $50
Twilio SMS/WA:         $200
PostgreSQL:             $40
Compute:               $100
Total:                $699/mes
```

### Completo (v2.0 + Multicanal)
```
Hunter.io Scale:       $209
RocketReach Pro:        $69
ZeroBounce:            $150
Mailgun:                $80
Chili Piper:         $1,250
Vapi Voice:            $500
Twilio:                $300
Clearbit (intent):     $500
PostgreSQL:             $50
Compute:               $200
Monitoring:            $200
Total:              $3,908/mes
```

---

## 🎯 KPIs a Monitorear

### Level 1: Email Metrics
- Open Rate: Target 25-30%
- Click Rate: Target 3-5%
- Bounce Rate: Target < 2%
- Unsubscribe Rate: Target < 0.5%

### Level 2: Engagement Metrics
- Reply Rate: Target 1-2%
- Meeting Booking Rate: Target 0.5-1%
- Sales Cycle Reduction: Target 30% vs baseline

### Level 3: Business Metrics
- Cost per Lead: Target < $1
- Cost per Meeting: Target < $50
- Cost per Deal: Target < $500
- ROI: Target 10x+

---

## 📚 Documentación por API

### Hunter.io
- Docs: https://hunter.io/api
- SDK Python: `pip install hunter`
- Rate limits: Según plan
- Latencia: < 200ms

### ZeroBounce
- Docs: https://www.zerobounce.net/api
- SDK Python: `pip install zerobounce`
- Rate limits: 1,000 req/hora
- Latencia: < 300ms

### Mailgun
- Docs: https://documentation.mailgun.com
- SDK Python: `pip install mailgun-python`
- Rate limits: Unlimited (según plan)
- Latencia: < 100ms

### Vapi
- Docs: https://docs.vapi.ai
- SDK: REST API + Webhooks
- Rate limits: Unlimited (según plan)
- Latencia: < 500ms

---

## ✅ Arquitectura: Checklist de Validación

- [ ] Hunter.io API conectada y funcional
- [ ] ZeroBounce API conectada y funcional
- [ ] Mailgun API conectada y funcional
- [ ] Database schema creada
- [ ] Webhook handlers implementados
- [ ] Email templates personalizables
- [ ] Dashboard de analytics funcionando
- [ ] Rate limiting implementado
- [ ] Error handling y retries
- [ ] Logging completo
- [ ] Monitoring y alertas
- [ ] Security (API keys, auth, encryption)
- [ ] Testing (unit, integration, load)
- [ ] Documentation actualizada
- [ ] Backup y disaster recovery

---

**Documento:** Arquitectura de Integración  
**Versión:** 1.0  
**Fecha:** Mayo 2026  
**Responsable:** Lambda Proyect Platform Team

