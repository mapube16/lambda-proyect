"""
voice_orchestrator.py — Main orchestration logic for voice calls.

This module coordinates:
1. Audio streaming from Twilio
2. Real-time transcription via Assembly AI
3. Claude decision logic
4. Google TTS synthesis
5. Audio streaming back to Twilio
6. Logging to MongoDB

This is where the "naturalness" comes from:
- Dynamic conversation (not pre-recorded scripts)
- Sub-second latency (Assembly AI ~200-300ms)
- Natural TTS with prosody control
- Call context awareness (how many times we've asked, etc.)
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from database import get_db
from cobranza.assembly_ai_client import AssemblyAIClient
from cobranza.claude_decision import get_next_action
from cobranza.tts_adapter import get_tts_provider

logger = logging.getLogger("cobranza.orchestrator")


class VoiceOrchestrator:
    """
    Manages a single voice call from start to finish.

    Flow:
    1. __init__ — initialize with debtor, estrategia, config
    2. run() — main async loop (receives audio, decides, responds)
    3. on_call_end() — log results to MongoDB
    """

    def __init__(
        self,
        call_id: str,
        user_id: str,
        debtor: dict,
        estrategia: dict,
        db_client=None,
    ):
        self.call_id = call_id
        self.user_id = user_id
        self.debtor = debtor
        self.estrategia = estrategia
        self.db = db_client or get_db()

        # State tracking
        self.transcript_history = []  # [{speaker: "agent"|"debtor", text: "..."}]
        self.decisions_log = []  # For debugging
        self.turn_count = 0
        self.intentos_failed = 0
        self.state = "active"  # active | ended_paid | ended_escalated | ended_failed

        # Identity & debt confirmation
        self.identity_confirmed = False
        self.debt_confirmed = False
        self.payment_agreed = False
        self.payment_date: Optional[str] = None
        self.amount_paid: Optional[float] = None

        logger.info(
            "[Orchestrator] Initialized for call %s, debtor %s",
            call_id,
            debtor.get("nombre"),
        )

    async def run_conversation_turn(
        self,
        debtor_utterance: str,
    ) -> str:
        """
        Single turn of conversation.

        Input: what the debtor just said (from Assembly AI transcript)
        Output: what the agent should say next (to be synthesized)

        Process:
        1. Add debtor's utterance to history
        2. Ask Claude what to do next
        3. Synthesize Claude's response
        4. Log decision
        5. Return response text (or audio bytes if needed)
        """
        self.turn_count += 1

        # Add debtor's utterance to history
        self.transcript_history.append({"speaker": "debtor", "text": debtor_utterance})

        logger.debug(
            "[Orchestrator] Turn %d: debtor said: %s",
            self.turn_count,
            debtor_utterance[:100],
        )

        # Get Claude decision
        decision = await get_next_action(
            estrategia=self.estrategia,
            debtor=self.debtor,
            transcript_history=self.transcript_history,
            latest_debtor_input=debtor_utterance,
            turn_number=self.turn_count,
            intentos_used=self.intentos_failed,
        )

        action = decision["action"]
        response_text = decision["response_text"]
        metadata = decision.get("metadata", {})

        # Update internal state based on Claude's insight
        if metadata.get("identity_confirmed"):
            self.identity_confirmed = True
        if metadata.get("debt_confirmed"):
            self.debt_confirmed = True
        if metadata.get("payment_agreed"):
            self.payment_agreed = True
            self.state = "ended_paid"

        # Log decision
        self.decisions_log.append(
            {
                "turn": self.turn_count,
                "action": action,
                "reasoning": decision["reasoning"],
                "response_text": response_text,
                "metadata": metadata,
            }
        )

        # Add agent's response to history
        self.transcript_history.append({"speaker": "agent", "text": response_text})

        logger.info(
            "[Orchestrator] Turn %d action: %s | Response: %s",
            self.turn_count,
            action,
            response_text[:80],
        )

        # Handle terminal actions
        if action == "escalate":
            self.state = "ended_escalated"
            self.intentos_failed += 1
            if self.intentos_failed >= self.debtor.get("max_intentos", 5):
                logger.warning(
                    "[Orchestrator] Max intentos reached for debtor %s",
                    self.debtor.get("nombre"),
                )
                return response_text  # Caller should close call after this

        elif action == "end":
            self.state = "ended_failed"
            return response_text

        return response_text

    async def synthesize_and_return(self, text: str) -> bytes:
        """
        Convert response text to audio via configured TTS provider.

        Uses TtsProvider adapter pattern — swappable via TTS_PROVIDER env var.

        In actual WebSocket usage, this would be streamed back to Twilio.
        """
        tts = get_tts_provider()
        audio = await tts.synthesize(text)
        if not audio:
            logger.error("[Orchestrator] TTS (%s) failed for: %s", tts.name(), text[:50])
            return b""
        logger.debug("[Orchestrator] Synthesized %d bytes via %s", len(audio), tts.name())
        return audio

    async def on_call_end(self, reason: str = "normal") -> None:
        """
        Log final call state to MongoDB.

        Saves:
        - Full transcript
        - Decisions log
        - Final state (paid/escalated/failed)
        - Metadata (duration, turns, etc.)
        """
        db = self.db

        call_record = {
            "call_id": self.call_id,
            "user_id": self.user_id,
            "debtor_id": str(self.debtor.get("_id")),
            "debtor_name": self.debtor.get("nombre"),
            "estado": self.state,
            "transcript": self.transcript_history,
            "decisions": self.decisions_log,
            "result": {
                "paid": self.payment_agreed,
                "payment_date": self.payment_date,
                "amount_paid": self.amount_paid,
                "escalated": self.state == "ended_escalated",
                "reason_ended": reason,
            },
            "turn_count": self.turn_count,
            "intentos_failed": self.intentos_failed,
            "created_at": datetime.now(timezone.utc),
        }

        try:
            await db.cobranza_calls.insert_one(call_record)
            logger.info(
                "[Orchestrator] Call %s logged (state: %s, turns: %d)",
                self.call_id,
                self.state,
                self.turn_count,
            )
        except Exception as e:
            logger.error("[Orchestrator] Failed to log call %s: %s", self.call_id, e)


# ── Example: How to use the orchestrator in a WebSocket handler ─────────────────

"""
Pseudocode for WebSocket handler:

async def voice_websocket(websocket, call_sid):
    # 1. Fetch debtor, estrategia from DB
    user_id = extract_user_id_from_call_sid(call_sid)
    debtor_id = extract_debtor_id_from_call_sid(call_sid)
    debtor = await get_debtor(debtor_id)
    estrategia = await get_estrategia(user_id)

    # 2. Initialize orchestrator
    orchestrator = VoiceOrchestrator(
        call_id=call_sid,
        user_id=user_id,
        debtor=debtor,
        estrategia=estrategia,
    )

    # 3. Initialize Assembly AI stream
    assembly_ai = AssemblyAIClient()
    async with assembly_ai.stream() as ai_stream:

        # 4. Main loop
        try:
            while True:
                # 4a. Receive audio from Twilio
                audio_chunk = await websocket.receive_bytes()

                # 4b. Send to Assembly AI
                await ai_stream.send(audio_chunk)

                # 4c. Read transcripts (partial then final)
                transcript = await ai_stream.get_transcript()
                if transcript["type"] == "FinalTranscript":
                    debtor_said = transcript["text"]

                    # 4d. Ask Claude what to say next
                    response_text = await orchestrator.run_conversation_turn(debtor_said)

                    # 4e. Synthesize to audio
                    audio = await orchestrator.synthesize_and_return(response_text)

                    # 4f. Send audio back to Twilio (in Twilio media format)
                    await websocket.send_bytes(twilio_audio_frame(audio))

                    # 4g. Check if we should end call
                    if orchestrator.state != "active":
                        break
        finally:
            await orchestrator.on_call_end(reason="websocket_closed")
"""
