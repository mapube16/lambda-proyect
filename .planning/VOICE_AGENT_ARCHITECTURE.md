# Voice Agent Architecture (Camila) — Scalable Multi-Tenant Design

**Status**: Architecture Design  
**Date**: 2026-04-10  
**Scope**: Transforming POC into scalable, multi-tenant voice agent system

---

## 1. Problem Statement

Current state:
- ✅ POC works for single client (DPG)
- ❌ System prompt hardcoded with company name
- ❌ Campaign parameters missing
- ❌ No per-client onboarding flow
- ❌ Not designed for multi-tenant use

Requirements:
- Each client gets own agent persona (name, company, tone)
- Each user parametrizes campaign on activation (call limits, hours, escalation rules)
- Each user's debtor pool has different complexity (SMEs vs high-volume)
- Graceful fallback if OpenAI fails
- Clear audit trail & state management

---

## 2. Agent Configuration System

### 2.1 Client Config (Set once, rarely changes)

**Collection**: `cobranza_clients` (new)

```python
{
  "_id": ObjectId,
  "user_id": str,
  "company_name": str,           # "De Pe Ge Seguros", "XYZ Corp", etc.
  "agent_name": str,             # "Camila", "Sofia", "Juan", etc.
  "agent_persona": {
    "tone": str,                 # "amable", "profesional", "firme"
    "dialect": str,              # "colombiana", "mexicana", "neutral"
    "style": str,                # "conversacional", "directo"
    "max_completion_tokens": int # 80 default, client might need more
  },
  "legal_framework": {
    "country": str,              # "CO", "MX", "AR"
    "law": str,                  # "Ley 2300", "LRCD", etc.
    "max_contacts_per_day": int,
    "call_hours_start": int,     # 7 (7am)
    "call_hours_end": int,       # 19 (7pm)
    "call_days": list,           # ["MON", "TUE", ..., "SAT"]
  },
  "escalation_rules": {
    "max_attempts": int,         # 5
    "escalate_after_attempts": int,
    "escalate_to": str,          # "supervisor", "legal", "collections"
  },
  "tts_config": {
    "voice": str,                # "coral", "sage", "alloy"
    "language": str,             # "es", "en"
  },
  "created_at": datetime,
  "updated_at": datetime,
}
```

**Set during**: Client onboarding (first time activating cobranzas module)

---

### 2.2 Campaign Config (Set per activation, can change)

**Collection**: `cobranza_campaigns` (new, replaces ad-hoc activation)

```python
{
  "_id": ObjectId,
  "user_id": str,
  "client_id": ObjectId,  # Ref to cobranza_clients
  "campaign_name": str,   # "Q2 2026 Collections", "Urgent Follow-up"
  "status": str,          # "active", "paused", "archived"
  
  "campaign_rules": {
    "debtor_filters": {
      "min_days_overdue": int,      # Only call if >30 days overdue
      "max_days_overdue": int,      # Don't call if >180 days
      "min_amount": int,            # >100k COP
      "max_amount": int,            # <50M COP
      "estado_include": list,       # ["pendiente", "sin_contacto"]
      "estado_exclude": list,       # ["pagado", "promesa_de_pago"]
    },
    "daily_limits": {
      "max_calls_per_day": int,    # 100
      "max_simultaneous": int,      # 1 (for now)
      "priority_order": str,        # "oldest_first", "highest_amount", "random"
    },
    "call_strategy": {
      "max_duration_seconds": int,  # 180 (3 min)
      "allow_recording": bool,
      "allow_voicemail": bool,
      "retry_on_no_answer": bool,
      "retry_delay_hours": int,
    },
  },
  
  "agent_overrides": {
    # Can override client defaults for this campaign
    "tone": str | None,
    "agent_name": str | None,
    "custom_system_instruction": str | None,  # Specific to campaign goal
  },
  
  "metrics": {
    "total_calls_made": int,
    "successful_contacts": int,
    "promises_of_payment": int,
    "escalations": int,
    "last_run": datetime,
  },
  
  "created_at": datetime,
  "updated_at": datetime,
}
```

**Set during**: User activates/configures cobranzas (after onboarding chooses client config)

---

## 3. Agent Control & Oversight

### 3.1 Autonomy Boundaries

Agent can:
✅ Speak naturally (OpenAI Realtime)  
✅ Listen to debtor responses  
✅ Decide next sentence dynamically  
✅ End call gracefully  

Agent CANNOT:
❌ Exceed daily call limits  
❌ Call outside legal hours  
❌ Contact same debtor twice in one day  
❌ Skip Ley 2300 checks  
❌ Modify debtor status without post-call review  

**Implementation**: Checks happen BEFORE call initiation + AFTER call ends (post-call processing validates state change)

### 3.2 Graceful Degradation

If OpenAI Realtime fails:
```
Flow:
1. Call initiated → reserve debtor slot
2. WebSocket connects → load system prompt
3. OpenAI service unavailable (timeout/error)
4. Agent raises exception
5. Post-call: estado stays "llamando" (not updated)
6. UI shows: "Llamada fallida, reintentar"
7. Debtor slot released for retry
```

No silent failures. Always log + expose to UI.

---

## 4. Prompt Templating System

### Current (Hardcoded)

```python
system_prompt = (
    f"Eres Camila, asesora de cobranza colombiana de De Pe Ge Seguros. "
    f"Tu tono es suave, tranquilo y amable. ..."
)
```

### Proposed (Templated)

**File**: `backend/cobranza/prompt_templates.py`

```python
SYSTEM_PROMPT_TEMPLATE = """
Eres {agent_name}, asesora de cobranza colombiana de {company_name}.

ESTILO:
- Tu tono es {tone}
- Tu dialecto es {dialect}
- Habla despacio y con calma
- Máximo 1 oración por turno
- Muletillas naturales: aja, listo, que pena, mire, claro

DATOS DEL DEUDOR:
- Nombre: {debtor_name}
- Debe: {debtor_amount} pesos
- Vencido: {debtor_overdue_days} días
- Intentos previos: {attempt_count}

FLUJO:
1. Saluda calmadamente y confirma identidad
2. Menciona el saldo y vencimiento
3. Ofrece opciones de pago
4. Despídete amablemente

LEY 2300:
- Hablando con {debtor_name} (contacto #{attempt_count} en 24h)
- Si rechaza/cuelga, respeta su decisión

PERSONALIZACIÓN POR CLIENTE:
{custom_instruction}
"""

def build_system_prompt(client: dict, campaign: dict, debtor: dict, attempt: int) -> str:
    """Dynamically build prompt from templates + configs."""
    client_override = campaign.get("agent_overrides", {})
    
    return SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=client_override.get("agent_name") or client["agent_name"],
        company_name=client["company_name"],
        tone=client_override.get("tone") or client["agent_persona"]["tone"],
        dialect=client["agent_persona"]["dialect"],
        debtor_name=debtor["nombre"],
        debtor_amount=f"{debtor['monto']:,.0f}",
        debtor_overdue_days=(datetime.now().date() - debtor["vencimiento"]).days,
        attempt_count=attempt,
        custom_instruction=client_override.get("custom_system_instruction") or "",
    )
```

**In run_bot()**:
```python
async def run_bot(websocket, call_sid: str, debtor: dict, client: dict, campaign: dict, attempt: int):
    system_prompt = build_system_prompt(client, campaign, debtor, attempt)
    llm = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAIRealtimeLLMService.Settings(
            model="gpt-4o-mini-realtime-preview-2024-12-17",
            system_instruction=system_prompt,  # ← Dynamic!
            temperature=0.8,
            ...
        ),
    )
    ...
```

---

## 5. Tool Registry & Agent Actions

Agent's available "tools" (not function calling, but state modifications):

```python
class AgentToolRegistry:
    """Available actions agent can request after call."""
    
    TOOLS = {
        "update_debtor_status": {
            "description": "Mark debtor as contactado, sin_contacto, escalado, etc.",
            "params": ["call_sid", "new_estado", "reason"],
            "requires_approval": False,  # Post-call processing does this
        },
        "schedule_retry": {
            "description": "Schedule retry in N hours",
            "params": ["debtor_id", "hours", "reason"],
            "requires_approval": True,  # Manual review
        },
        "escalate_to_supervisor": {
            "description": "Send to supervisor queue",
            "params": ["debtor_id", "reason", "priority"],
            "requires_approval": True,
        },
        "log_interaction": {
            "description": "Save transcript to historial",
            "params": ["call_sid", "transcript", "summary"],
            "requires_approval": False,
        },
    }
```

Agent doesn't directly call these—post-call processor handles them based on:
- Call duration
- User turn count
- Debtor response sentiment (could infer from transcript)
- Campaign rules

---

## 6. Database Schema Updates

### New Collections

1. **cobranza_clients**
   - One per user (or shared across users in same org?)
   - Stores: persona, legal framework, escalation rules

2. **cobranza_campaigns**
   - Many per user
   - Stores: active campaign config + metrics

3. **cobranza_call_logs** (new, more detailed than historial_llamadas)
   - Full transcript + audio + metadata
   - Indexed for audit + analytics
   - Linked to campaign for metrics

### Existing Collection Updates

**debtors** (add fields):
```python
{
  ...
  "campaign_id": ObjectId,  # Which campaign is this part of
  "assigned_at": datetime,
  "last_contacted_by_agent": datetime,  # For Ley 2300 enforcement
  "agent_notes": str,  # Notes from agent interactions
}
```

**cobranza_calls_in_progress** (add):
```python
{
  ...
  "campaign_id": ObjectId,
  "client_id": ObjectId,
  "attempt_number": int,
}
```

---

## 7. Onboarding Flow (New)

### Step 1: Client Setup (Company Info)

**UI**: "Configurar Empresa de Cobranza"

```
1. Nombre de empresa → cobranza_clients.company_name
2. Nombre del agente → cobranza_clients.agent_name
3. Tono preferido (amable/profesional/firme) → agent_persona.tone
4. País → legal_framework.country
5. Horario de llamadas (7am-7pm default, editable)
6. Máximo intentos por deudor (default 5)
7. Escalación: ¿a dónde van los casos difíciles?
```

**Backend**: Crea documento en `cobranza_clients`

### Step 2: Campaign Setup (Activation)

**UI**: "Crear Campaña de Cobranza"

```
1. Nombre de campaña
2. Filtros de deudores (monto, días vencido, estado)
3. Límites diarios (X llamadas/día)
4. Duración máxima por llamada
5. ¿Permitir grabaciones?
```

**Backend**: Crea documento en `cobranza_campaigns` + establece como activa

### Step 3: Debtor Assignment (Automatic)

```
1. Fetch debtors matching campaign filters
2. Assign campaign_id a each
3. Compute attempt_number (calls since campaign started)
4. Ready to start calling
```

---

## 8. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                        │
│  Cobranza Tab → Campaign Selector → Debtor List → Call Btn  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│            FastAPI Router (voice_router.py)                  │
│                                                               │
│  POST /call/initiate-v2                                      │
│  ├─ Load client config (cobranza_clients)                   │
│  ├─ Load campaign (cobranza_campaigns)                       │
│  ├─ Validate Ley 2300 (hours, contacts/day, max attempts)  │
│  ├─ Create call mapping + reserve debtor                    │
│  └─ Trigger Twilio outbound call                            │
│                                                               │
│  WebSocket /ws/{call_sid}                                    │
│  ├─ Accept connection                                        │
│  └─ Call run_bot() with client, campaign, debtor            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Pipecat Pipeline (voice_pipecat.py)                 │
│                                                               │
│  1. build_system_prompt(client, campaign, debtor)           │
│  2. OpenAI Realtime LLM Service                              │
│     ├─ STT (Whisper-1, Spanish)                             │
│     ├─ LLM (gpt-4o-mini-realtime)                           │
│     └─ TTS (Coral voice)                                     │
│  3. Capture transcript (user + bot turns)                    │
│  4. Return CallResult (duration, transcript, turns)          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│      Post-Call Processing (_process_call_ended)              │
│                                                               │
│  1. Analyze CallResult                                        │
│  2. Apply escalation rules (if max attempts reached)         │
│  3. Update debtor estado (contactado/sin_contacto/escalado) │
│  4. Save to historial_llamadas                              │
│  5. Save detailed log to cobranza_call_logs                 │
│  6. Update campaign metrics                                  │
│  7. Push WebSocket event (debtor_update)                    │
│  8. Release debtor slot                                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │    MongoDB Updated      │
            │  - debtors (estado++)   │
            │  - historial_llamadas   │
            │  - cobranza_call_logs   │
            │  - cobranza_campaigns   │
            └────────────────────────┘
```

---

## 9. Immediate TODOs (Phase 2)

1. **Create `cobranza_clients` collection** + CRUD endpoints
2. **Create `cobranza_campaigns` collection** + CRUD endpoints
3. **Refactor `voice_pipecat.run_bot()`** to accept client + campaign params
4. **Build prompt templating** system (move hardcoding to config)
5. **Update `voice_router.initiate_call_v2()`** to load client + campaign
6. **Create onboarding UI** for client setup + campaign creation
7. **Add audit logging** to `cobranza_call_logs`
8. **Build campaign metrics dashboard** (calls/day, success rate, escalations)

---

## 10. Success Criteria

After Phase 2:
- [ ] Multi-tenant: Same codebase serves DPG + XYZ Corp (different agents, personas)
- [ ] Parametrizable: Each user configures own campaign on activation
- [ ] Scalable: Can handle 50+ campaigns simultaneously
- [ ] Auditable: Every call logged with full context
- [ ] Controlled: Ley 2300 + escalation rules enforced automatically
- [ ] Graceful: Failures don't corrupt state, UI always reflects truth

---

## 11. Notes on Control vs Autonomy

This architecture keeps agent **highly autonomous** (speaks naturally, makes real-time decisions) while maintaining **strict boundaries**:

- Agent has **no DB write access** (all through post-call processor)
- Agent's "tools" are **declarative, not executable** (processor decides if action is valid)
- Agent can't **override campaign limits** (checked pre-call)
- Agent can't **ignore Ley 2300** (checked pre-call + post-call validated)

Result: Agent feels alive & responsive, but system never enters invalid state.
