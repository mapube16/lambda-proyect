# Testing Voice Orchestrator — Phase C

**Status:** WebSocket handler + outbound call logic implemented.

## What Works

✅ **Configuration**
- Assembly AI API key validated
- Google Cloud TTS credentials validated
- Twilio account configured
- All env vars present

✅ **Code Structure**
- `VoiceOrchestrator` class ready
- `voice_router.py` has WebSocket handler
- Call initiation logic implemented
- MongoDB schemas ready

## What Needs Testing

### Level 1: Unit Tests (Isolated)

Test the helpers WITHOUT a real call:

**File to create:** `backend/tests/test_voice_integration.py`

```python
# Test 1: Claude decision logic
@pytest.mark.asyncio
async def test_claude_decides_naturally():
    """Claude should decide dynamically based on what debtor says."""
    from cobranza.claude_decision import get_next_action
    
    estrategia = {
        "tono": "profesional",
        "guion": {"saludo": "Hola", "propuesta": "...", "objeciones": "...", "cierre": "..."},
    }
    debtor = {"nombre": "Juan", "monto": 500000}
    
    decision = await get_next_action(
        estrategia=estrategia,
        debtor=debtor,
        transcript_history=[],
        latest_debtor_input="No tengo dinero",
        turn_number=1,
    )
    
    # Claude should understand the objection
    assert decision["action"] in ("handle_objection", "offer_payment", "escalate")
    assert "dinero" in decision["response_text"].lower() or "pago" in decision["response_text"].lower()

# Test 2: TTS provider selection
@pytest.mark.asyncio
async def test_tts_provider_google_cloud():
    """TTS provider should be Google Cloud."""
    from cobranza.tts_adapter import get_tts_provider
    
    tts = get_tts_provider()
    assert tts.name() == "google-cloud"

# Test 3: Assembly AI client initialization
def test_assembly_ai_client_init():
    """Assembly AI client should initialize with API key."""
    from cobranza.assembly_ai_client import AssemblyAIClient
    
    client = AssemblyAIClient()
    assert client.api_key is not None
```

### Level 2: Integration Tests (Full Flow, Mocked)

**File to create:** `backend/tests/test_voice_e2e.py`

```python
# Mock the full call flow
@pytest.mark.asyncio
async def test_voice_call_full_flow():
    """Full call flow: debtor speaks → transcribed → Claude decides → TTS synthesizes."""
    from cobranza.voice_orchestrator import VoiceOrchestrator
    from unittest.mock import AsyncMock, MagicMock
    
    # Mock data
    debtor = {
        "_id": "test_debtor",
        "nombre": "Juan",
        "telefono": "+573001234567",
        "monto": 500000,
        "vencimiento": "2026-06-01",
        "max_intentos": 5,
    }
    
    estrategia = {
        "tono": "profesional",
        "frecuencia_dias": 2,
        "max_intentos": 5,
        "guion": {
            "saludo": "Hola Juan",
            "propuesta": "Te llamo sobre una deuda",
            "objeciones": "Entiendo tu situación",
            "cierre": "Muchas gracias",
        },
    }
    
    # Initialize orchestrator
    orchestrator = VoiceOrchestrator(
        call_id="test_call_123",
        user_id="test_user",
        debtor=debtor,
        estrategia=estrategia,
        db_client=AsyncMock(),  # Mock DB
    )
    
    # Simulate debtor's first response
    response = await orchestrator.run_conversation_turn("Hola, ¿quién eres?")
    
    assert response is not None
    assert len(response) > 0
    assert orchestrator.turn_count == 1
    
    # Simulate second turn (objection)
    response2 = await orchestrator.run_conversation_turn("No tengo dinero ahora mismo")
    
    assert response2 is not None
    assert orchestrator.turn_count == 2
```

### Level 3: Manual E2E Testing (Real Twilio Calls)

**Requirements:**
- Twilio account with voice-enabled number
- Test number to call yourself
- Backend running on staging/prod

**Steps:**

1. **Start backend**
   ```bash
   cd backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
   ```

2. **Verify webhook is reachable**
   ```bash
   curl -X POST http://localhost:8001/api/cobranza/voice/webhook \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "CallSid=CA123&Called=%2B573001234567"
   ```

3. **Create a test debtor**
   ```bash
   curl -X POST http://localhost:8001/api/cobranza/debtors \
     -H "Authorization: Bearer {token}" \
     -H "Content-Type: application/json" \
     -d '{
       "nombre": "Test Debtor",
       "telefono": "+573001234567",
       "monto": 100000,
       "vencimiento": "2026-06-01"
     }'
   ```

4. **Trigger a call via API**
   ```bash
   curl -X POST http://localhost:8001/api/cobranza/voice/call/initiate-v2 \
     -H "Authorization: Bearer {token}" \
     -H "Content-Type: application/json" \
     -d '{"debtor_id": "{debtor_id}"}'
   ```

5. **Check call logs in MongoDB**
   ```bash
   # In MongoDB console:
   db.cobranza_calls.findOne({}, {sort: {created_at: -1}})
   ```

6. **Listen for quality issues:**
   - Does the voice agent sound natural?
   - Are there long pauses between turns?
   - Does Claude understand objections?
   - Does the call end properly?

## Test Checklist

### Unit Tests (Recommended)

- [ ] `test_claude_decides_naturally` — Claude responds to objections
- [ ] `test_tts_provider_google_cloud` — TTS configured correctly
- [ ] `test_assembly_ai_client_init` — Assembly AI client works
- [ ] `test_voice_orchestrator_state_machine` — State transitions correct
- [ ] `test_debtor_lookup` — Call mapping works

### Integration Tests

- [ ] `test_voice_call_full_flow` — Full conversation loop
- [ ] `test_call_logging_to_mongodb` — Logs saved correctly
- [ ] `test_ley_2300_compliance` — Contact hours validated
- [ ] `test_call_escalation_on_max_intentos` — Escalation works

### Manual E2E

- [ ] [ ] Backend starts without errors
- [ ] [ ] WebSocket connects successfully
- [ ] [ ] Audio flows (check logs for audio_chunk sizes)
- [ ] [ ] Transcription works (check Assembly AI logs)
- [ ] [ ] Claude decides naturally (check MongoDB decision logs)
- [ ] [ ] TTS synthesizes audio (check for audio bytes returned)
- [ ] [ ] Call quality sounds natural (no long pauses, conversational)
- [ ] [ ] Call logs to MongoDB with full transcript

## Debugging Commands

### Check WebSocket connection
```python
# In Python:
import asyncio
import websockets

async def test_ws():
    async with websockets.connect("ws://localhost:8001/api/cobranza/voice/ws/test_call") as ws:
        # Send test audio frame
        await ws.send(b"\x00\x00" + b"\x00" * 100)  # Twilio format: 2-byte header + audio
        print("✓ WebSocket connected")

asyncio.run(test_ws())
```

### Check MongoDB logs
```javascript
// In MongoDB:
db.cobranza_calls.findOne({})
// View full transcript + decisions
db.cobranza_calls.findOne({}, {projection: {transcript: 1, decisions: 1}})
```

### Check Assembly AI integration
```python
# In Python:
from cobranza.assembly_ai_client import AssemblyAIClient

client = AssemblyAIClient()
# This will test the API key without connecting
print("✓ Assembly AI client initialized")
```

## Known Issues & Workarounds

### Issue 1: Twilio Media Format
**Status:** Partially implemented
**Workaround:** Current code treats audio as raw PCM. May need to parse Twilio's 2-byte header properly.

### Issue 2: Assembly AI Real-Time Streaming
**Status:** Skeleton only
**Workaround:** Current implementation collects audio but doesn't stream to Assembly AI yet. Need to wire the async stream properly.

### Issue 3: Turn-Taking Timing
**Status:** Design complete, not tested
**Concern:** Latency between Assembly AI → Claude → TTS might cause pauses. Monitor in E2E tests.

## Next Steps

1. **Run unit tests** — `pytest backend/tests/test_voice_*.py -v`
2. **Check logs** — Tail backend logs while testing
3. **Manual E2E** — Call yourself from Twilio console
4. **Iterate** — Fix issues found, commit to feature branch
5. **Code review** — Have team review before merging to master

## Questions?

- Assembly AI streaming: see `backend/cobranza/assembly_ai_client.py`
- Claude decisions: see `backend/cobranza/claude_decision.py`
- Orchestration flow: see `backend/cobranza/voice_orchestrator.py`

Good luck testing! 🚀
