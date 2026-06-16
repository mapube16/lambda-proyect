# Landa Office Endpoints — Test Suite

## ✅ Implemented Endpoints

### 1. Campaigns CRUD

```bash
# List campaigns
GET /api/campaigns?status=all&limit=50&offset=0
Authorization: Bearer {jwt_token}

# Create campaign
POST /api/campaigns
{
  "name": "Q3 Telecom",
  "sectors": ["Telecomunicaciones", "IT"],
  "cities": ["Bogotá", "Medellín"],
  "icp_description": "Empresas con 50-200 empleados",
  "notes": "Optional notes"
}

# Get campaign details + KPIs
GET /api/campaigns/{campaign_id}

# Update campaign
PATCH /api/campaigns/{campaign_id}
{
  "name": "Updated name",
  "sectors": ["IT"],
  "cities": ["Bogotá"],
  "is_active": true
}

# Delete/archive campaign
DELETE /api/campaigns/{campaign_id}

# Launch prospecting
POST /api/campaigns/{campaign_id}/launch
→ Creates run, enqueues ARQ job

# Get campaign runs
GET /api/campaigns/{campaign_id}/runs?limit=20&offset=0
```

### 2. Leads Management

```bash
# List leads (with filtering)
GET /api/campaigns/{campaign_id}/leads?status=all&limit=50&offset=0&sort_by=score
Status: all, approved, rejected, sent, pending
Sort: score, created_at, status

# Approve lead
POST /api/campaigns/{campaign_id}/leads/{lead_id}/approve
{
  "notes": "optional approval notes"
}

# Reject/discard lead
DELETE /api/campaigns/{campaign_id}/leads/{lead_id}
→ Sets hitl_status = "rejected"

# Edit lead before sending
PATCH /api/campaigns/{campaign_id}/leads/{lead_id}
{
  "email": "nuevo@email.com",
  "phone": "+57 300 555 0123",
  "custom_email_body": "Updated email content",
  "notes": "Editor notes"
}

# Send lead via email or WhatsApp
POST /api/campaigns/{campaign_id}/leads/{lead_id}/send
{
  "channel": "email",
  "body": "Personalized email body",
  "subject": "Optional subject for email"
}
→ Returns tracking_id, marks as sent
```

### 3. KPIs & Analytics

```bash
# Get campaign KPIs
GET /api/campaigns/{campaign_id}/kpis
Returns:
{
  "leads_qualified": 24,
  "leads_approved": 16,
  "leads_rejected": 8,
  "leads_sent": 7,
  "approval_rate": 0.67,
  "send_rate": 0.43
}

# Get campaign email metrics
GET /api/campaigns/{campaign_id}/metrics
Returns:
{
  "total_sent": 7,
  "opens": 4,
  "open_rate": 0.57,
  "clicks": 2,
  "click_rate": 0.29,
  "replies": 1,
  "reply_rate": 0.14
}

# Get tenant quota/billing
GET /api/tenant/quota
Returns:
{
  "plan": "pro",
  "credits_remaining": 8420,
  "credits_total": 13500,
  "usage_percent": 37.6,
  "reset_date": "2026-06-30T00:00:00Z"
}
```

---

## 🔄 Request/Response Examples

### Create Campaign
```bash
curl -X POST http://localhost:8001/api/campaigns \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q3 Telecom Campaign",
    "sectors": ["Telecomunicaciones"],
    "cities": ["Bogotá"],
    "icp_description": "50-200 employees, revenue >$2M",
    "notes": "Target CXOs"
  }'

Response:
{
  "id": "507f1f77bcf86cd799439011",
  "name": "Q3 Telecom Campaign",
  "status": "created"
}
```

### Launch Campaign
```bash
curl -X POST http://localhost:8001/api/campaigns/507f1f77bcf86cd799439011/launch \
  -H "Authorization: Bearer {token}"

Response:
{
  "status": "launched",
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "campaign_id": "507f1f77bcf86cd799439011"
}
```

### List Leads
```bash
curl -X GET "http://localhost:8001/api/campaigns/507f1f77bcf86cd799439011/leads?status=approved&limit=50" \
  -H "Authorization: Bearer {token}"

Response:
{
  "leads": [
    {
      "id": "507f1f77bcf86cd799439012",
      "company_name": "Transportes Andina",
      "sector": "Logística",
      "city": "Bogotá",
      "score": 86,
      "decision_maker": "Carolina Rojas",
      "email": "crojas@andina.co",
      "phone": "+57 310 555 0142",
      "reason": "Flota propia de 40+ vehículos",
      "status": "approved",
      "opens": 0,
      "clicks": 0,
      "replies": 0
    }
  ],
  "total": 16,
  "limit": 50,
  "offset": 0,
  "kpis": {
    "approved": 16,
    "rejected": 8,
    "sent": 0
  }
}
```

### Send Lead
```bash
curl -X POST http://localhost:8001/api/campaigns/507f1f77bcf86cd799439011/leads/507f1f77bcf86cd799439012/send \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "email",
    "body": "Hola Carolina, hemos identificado que Transportes Andina tiene oportunidades..."
  }'

Response:
{
  "status": "sent",
  "lead_id": "507f1f77bcf86cd799439012",
  "tracking_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "sent_at": "2026-05-31T19:30:00Z",
  "channel": "email"
}
```

---

## 🚀 Testing Checklist (Frontend)

- [ ] GET /api/campaigns → List campaigns
- [ ] POST /api/campaigns → Create campaign
- [ ] GET /api/campaigns/{id} → Get campaign + KPIs
- [ ] PATCH /api/campaigns/{id} → Update campaign
- [ ] DELETE /api/campaigns/{id} → Archive campaign
- [ ] POST /api/campaigns/{id}/launch → Launch prospecting + enqueue job
- [ ] GET /api/campaigns/{id}/runs → Get runs
- [ ] GET /api/campaigns/{id}/leads → List leads with filters
- [ ] POST /api/campaigns/{id}/leads/{id}/approve → Approve lead
- [ ] DELETE /api/campaigns/{id}/leads/{id} → Reject lead
- [ ] PATCH /api/campaigns/{id}/leads/{id} → Edit lead
- [ ] POST /api/campaigns/{id}/leads/{id}/send → Send lead
- [ ] GET /api/campaigns/{id}/kpis → Get KPIs
- [ ] GET /api/campaigns/{id}/metrics → Get email metrics
- [ ] GET /api/tenant/quota → Get quota info

---

## ⚠️ Still TODO

### Missing: WebSocket Real-Time Updates
```javascript
// Not yet implemented, but planned
const socket = io('http://localhost:8001', { 
  extraHeaders: { 'Authorization': `Bearer ${token}` }
});

socket.on('/ws/campaigns/{id}/live', (event) => {
  // { type: 'agent_status', role: 'buscador', count: 38, task: 'Buscando en Bogotá...' }
});

socket.on('/ws/campaigns/{id}/feed', (event) => {
  // { type: 'lead_scored', lead_name: 'Transportes Andina', score: 86 }
});
```

### Missing: Polling endpoint for agent progress
```bash
GET /api/campaigns/{campaign_id}/run/{run_id}/progress
→ { status: 'running', agent_logs: {...}, leads_found: 12, leads_approved: 4 }
```

---

## 🔐 Authentication

All endpoints require JWT token in header:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Token includes:
```json
{
  "user_id": "507f1f77bcf86cd799439000",
  "email": "user@example.com",
  "role": "client"
}
```

---

## 📊 Data Model

### Campaign
```json
{
  "_id": "ObjectId",
  "user_id": "str",
  "name": "str",
  "sectors": ["str"],
  "cities": ["str"],
  "icp_description": "str",
  "notes": "str",
  "is_active": "bool",
  "status": "draft|active|archived",
  "created_at": "datetime",
  "updated_at": "datetime",
  "total_found": "int",
  "total_approved": "int"
}
```

### Lead
```json
{
  "_id": "ObjectId",
  "campaign_id": "str",
  "user_id": "str",
  "company_name": "str",
  "sector": "str",
  "city": "str",
  "score": "int (0-100)",
  "decision_maker": "str",
  "email": "str",
  "phone": "str",
  "reason": "str",
  "hitl_status": "pending|approved|rejected",
  "estado": "draft|sent|opened|clicked|replied|bounced",
  "custom_email_body": "str",
  "tracking_id": "str",
  "sent_at": "datetime",
  "email_events": {
    "opens": "int",
    "clicks": "int",
    "replies": "int"
  }
}
```

---

## 📝 Notes

- All timestamps are UTC ISO 8601
- Lead scores auto-extracted from `expediente_json.score`
- Filtering/sorting is case-sensitive
- Pagination defaults: limit=50, offset=0
- Max limit: 100 for campaigns/runs, 500 for leads
