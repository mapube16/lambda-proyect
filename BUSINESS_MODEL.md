# LANDA: B2B Lead Generation Platform
## Business Model & Cost Analysis

---

## 1. PRODUCTO

**Landa** es una plataforma **SaaS de generación de leads B2B** para empresas colombianas que buscan prospectos calificados en construcción, manufactura, transporte y otros sectores.

### Características Principales
- 🔍 **Discovery automático** vía Bright Data Web Scraper + Serper
- 📞 **Enriquecimiento de datos** (teléfono, email, dirección, rating)
- 🤖 **Análisis LLM** de cada prospecto (scoring + análisis sectorial)
- 📧 **Contacto automatizado** vía Email + WhatsApp
- 📊 **Dashboard** con leads, patrones, exclusiones
- 🧠 **Learning Loop** que mejora calidad con cada interacción

---

## 2. STACK TECNOLÓGICO

### Backend
- **Framework**: FastAPI + Uvicorn
- **Database**: MongoDB Atlas (M0 free / M2 $57/mes)
- **LLM**: OpenAI gpt-4o-mini
- **Search**: Serper + Bright Data Web Scraper
- **Email**: MailerSend
- **Chat**: Twilio WhatsApp
- **Hosting**: Railway

### Frontend
- **Framework**: React + TypeScript + Vite
- **UI**: Pixel art office canvas (unique UX)
- **Real-time**: WebSocket (FastAPI)

### Key APIs
| API | Uso | Costo |
|-----|-----|-------|
| Bright Data Web Scraper | LinkedIn, Directorio Colombia, CCB | $0.020/lead |
| Serper Search | Búsqueda web + enriquecimiento | $0.001/lead |
| OpenAI API | Análisis LLM | $0.00015/token |
| MailerSend | Email masivo | FREE (3k/mes) |
| Twilio | WhatsApp | $0.0065/msg |
| MongoDB | Base de datos | $0-57/mes |
| Railway | Backend hosting | $15/mes |

---

## 3. FLUJO DEL PIPELINE (1 Lead)

```
1. DISCOVERY (30 segundos)
   └─ Bright Data Web Scraper raspa LinkedIn + Directorios
   └─ Extrae: nombre, email, teléfono, dirección, website
   └─ Costo: $0.020

2. ENRICHMENT (15 segundos)
   └─ Serper Places valida datos
   └─ Agrega: rating, industria, año fundación
   └─ Costo: $0.001

3. LLM ANALYSIS (45 segundos)
   └─ OpenAI gpt-4o-mini analiza:
      - Sector / Oportunidad
      - Score (1-10)
      - Análisis de viabilidad
   └─ Costo: $0.00027

4. STORAGE
   └─ MongoDB guarda lead + metadata
   └─ Costo: $0.00 (included in $15/mes)

5. OUTREACH (Automated)
   └─ Email vía MailerSend: FREE
   └─ WhatsApp vía Twilio: $0.0065

TOTAL COSTO POR LEAD: ~$0.04
```

---

## 4. MODELO PREMIUM (50 Leads/Día)

### Volumen Mensual
- **50 leads/día × 30 días = 1,500 leads/mes**

### Desglose de Costos

#### Discovery & Enrichment
```
Bright Data Web Scraper:    1,500 × $0.020 = $30.00
Serper Search:              1,500 × $0.001 = $1.50
Serper Places:              1,500 × $0.001 = $1.50
                            Subtotal: $33.00
```

#### LLM Analysis
```
OpenAI gpt-4o-mini:
  1,500 leads × 1,200 tokens × $0.00015/token = $0.27
                            Subtotal: $0.27
```

#### Communication
```
Email (MailerSend):         1,500 × FREE = $0.00
WhatsApp (Twilio):          1,500 × $0.0065 = $9.75
                            Subtotal: $9.75
```

#### Infrastructure & Storage
```
MongoDB Atlas (M0):         $0.00
Railway Backend:            $15.00
Twilio Base:                $1.00
Other:                      $0.00
                            Subtotal: $16.00
```

### TOTAL COSTO MENSUAL: **$59.02**

#### Cost Per Lead
```
$59.02 ÷ 1,500 = $0.039/lead
```

---

## 5. PRICING STRATEGY

### Opción A: Pay-per-Lead
```
Cost:           $0.04/lead
+ Markup (333%): $0.13/lead
Price:          $0.17/lead

For 1,500 leads/month: 1,500 × $0.17 = $255/mes
```

### Opción B: Fixed Monthly (Recommended)
```
Plan: PREMIUM (50 leads/día)
Price: $200/mes

Includes:
✅ Bright Data Web Scraper (LinkedIn + Directorios)
✅ Full contact enrichment (email, phone, address)
✅ LLM analysis & scoring
✅ Automated email campaigns
✅ WhatsApp messaging
✅ Lead dashboard & exclusions
✅ Learning loop (ideal lead patterns)
✅ API access
```

### Opción C: Tiered Plans
```
STARTER (10 leads/día):
  - 300 leads/mes
  - Serper Search only
  - Email only
  Price: $50/mes

PROFESSIONAL (25 leads/día):
  - 750 leads/mes
  - Bright Data + Serper
  - Email + WhatsApp
  Price: $120/mes

PREMIUM (50 leads/día):
  - 1,500 leads/mes
  - Full Bright Data Web Scraper
  - All enrichment
  - Email + WhatsApp + Dashboard
  Price: $200/mes

ENTERPRISE (100+ leads/día):
  - Custom pricing
  - Dedicated support
  - Custom integrations
```

---

## 6. UNIT ECONOMICS (1 Customer @ Premium)

### Monthly
```
Revenue:        $200
COGS:           $59.02
Gross Profit:   $140.98
Margin:         70.5%
```

### Annual
```
Revenue:        $2,400
COGS:           $708.24
Gross Profit:   $1,691.76
Margin:         70.5%
```

### Per Lead (Premium Plan)
```
Price per lead:   $200 ÷ 1,500 = $0.133/lead
Cost per lead:    $0.039/lead
Margin:           $0.094/lead (240% markup)
```

---

## 7. BREAKEVEN & PROFITABILITY

### Breakeven Analysis
```
Fixed Costs (Monthly):
  - Railway Backend: $15
  - Twilio Base: $1
  - Monitoring/Support: ~$10
  Total Fixed: $26/mes

Variable Cost per Lead: $0.039

For 50 leads/day pricing ($200/mes):
  Revenue: $200
  Variable Cost: $59.02
  Fixed Cost: $26
  
  Profit = $200 - $59.02 - $26 = $114.98/customer
```

### 10 Customers (Minimum Viable)
```
Revenue:        10 × $200 = $2,000/mes
COGS:           10 × $59.02 = $590.20
Fixed Costs:    $200 (team, ops, etc)
Net Profit:     $1,209.80/mes ($14,518/year)
Margin:         60%
```

---

## 8. COMPETITIVE ADVANTAGES

1. **Bright Data Integration** - Full contact extraction (not just leads)
2. **LLM Scoring** - AI-powered lead qualification
3. **Automated Outreach** - Email + WhatsApp built-in
4. **Learning Loop** - Improves with each customer
5. **Colombia-Focused** - Optimized for Colombian directories
6. **Low CAC** - B2B SaaS with viral potential
7. **High Margin** - 70%+ gross margin at scale

---

## 9. REVENUE PROJECTIONS (Year 1)

### Conservative (1-5 customers by month 12)
```
Month 1:  1 customer  = $200/mes revenue
Month 6:  3 customers = $600/mes revenue
Month 12: 5 customers = $1,000/mes revenue

Year 1 Total Revenue: ~$4,200
Year 1 Net Profit: ~$2,000 (after fixed costs)
```

### Aggressive (5-20 customers by month 12)
```
Month 1:  1 customer  = $200
Month 3:  2 customers = $400
Month 6:  5 customers = $1,000
Month 9:  10 customers = $2,000
Month 12: 20 customers = $4,000/mes

Year 1 Total Revenue: ~$18,600
Year 1 Net Profit: ~$10,000 (after fixed costs)
```

---

## 10. CUSTOMER ACQUISITION

### Target Market
- **B2B Servicios** (Construcción, Transporte, Manufactura, etc)
- **Tamaño**: 10-50 empleados (decision makers accessible)
- **Presupuesto**: $5k-50k/year en lead gen
- **Pain**: Manual prospecting, low conversion, no quality metrics

### CAC Strategy
```
Channel 1: Direct Outreach ($0 cost)
  - Pitch to construction companies, logistics, manufacturing
  - Demo: 50 free leads for first customer

Channel 2: Partner integrations
  - CRM integrations (HubSpot, Pipedrive)
  - Affiliate commission: 20%

Channel 3: Referral Program
  - Customer brings friend: both get 1 month free

Channel 4: Content Marketing
  - Blog: "How to find construction companies in Colombia"
  - SEO target: lead generation keywords

Estimated CAC: $100-300/customer
LTV: $2,400/year (customer keeps ~6 months min)
LTV:CAC Ratio: 8:1 (healthy)
```

---

## 11. NEXT STEPS

### Phase 1: Validation (Now)
- ✅ Build MVP (DONE)
- ✅ Test Bright Data integration (IN PROGRESS)
- ⏳ Get first 3 paying customers
- ⏳ Validate unit economics

### Phase 2: Scale (Month 3)
- Build sales playbook
- Create customer success process
- Add tier pricing (Starter/Professional)
- Build integrations (CRM, Zapier)

### Phase 3: Growth (Month 6)
- Expand to other sectors (healthcare, finance, etc)
- Build AI-powered scoring system
- Add more channels (LinkedIn, phone, SMS)
- Hire sales + support team

---

## 12. KEY METRICS TO TRACK

```
Unit Economics:
- CAC (Customer Acquisition Cost)
- LTV (Lifetime Value)
- LTV:CAC Ratio
- Churn Rate
- ARPU (Average Revenue Per User)

Product Metrics:
- Lead Quality Score (% > 7/10)
- Email Open Rate
- WhatsApp Response Rate
- Customer Retention (target: 90%+)
- Gross Margin (target: 70%+)
```

---

## 13. PRICING RECOMMENDATION

**Start with Option B: Fixed Monthly at $200/mes for Premium**

Why:
- ✅ Simple to understand
- ✅ Predictable revenue
- ✅ High margin (70%)
- ✅ Easy to sell ("$200/mes for 1,500 leads")
- ✅ Can add upsells (reporting, API, integrations)

Add upsells later:
- Premium reports: +$50/mes
- API access: +$50/mes
- WhatsApp automation: +$30/mes
- Dedicated account manager: +$100/mes

---

## 14. FINANCIALS SUMMARY

| Metric | Value |
|--------|-------|
| CAC (estimated) | $150 |
| LTV (6 month customer) | $1,200 |
| LTV:CAC | 8:1 |
| Gross Margin | 70.5% |
| Break-even Customers | 1 |
| 10-Customer Revenue | $2,000/mes |
| 10-Customer Profit | $1,210/mes |
| 10-Customer Margin | 60% |

---

**Status**: Ready to pitch to first customers ✅
**Next Action**: Find 1-2 customers willing to pay $200/mes for 50 leads/day
