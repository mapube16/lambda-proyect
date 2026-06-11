"""
cobranza_orchestrator.py — Direct-dispatch orchestrator for CobranzaOrchestrator sub-agents.

IMPORTANT: This is NOT framework AgentOrchestrator and does NOT use LLM routing.
LLM routing via AgentOrchestrator._check_all_capabilities() adds 200-500ms latency
(RESEARCH Pitfall 6), violating the 500ms TTFB target for voice agent tool calls.

Instead: each tool call from GeminiLiveLLMService maps to a direct async method call.
Sub-agents are plain async functions, not AgentRunner instances.

Architecture:
  GeminiLiveLLMService → tool call → CobranzaOrchestrator.method() → sub-agent fn()
                                      (dispatch: ~0ms)

See RESEARCH.md Pattern 6 for rationale.
"""
import logging
from typing import Optional

from database import get_db
from cobranza.sub_agents import debtor_updater, whatsapp_notifier, identity_verifier, escalation_handler

logger = logging.getLogger("cobranza.orchestrator")


class CobranzaOrchestrator:
    """
    Direct-dispatch orchestrator: sub-agents are async functions, NOT AgentRunner.

    Provides 4 methods corresponding to Gemini tool call names:
    - update_debtor   → debtor_updater.update_debtor_status()
    - send_whatsapp   → whatsapp_notifier.send_whatsapp()
    - verify_identity → identity_verifier.verify_identity()
    - escalate        → escalation_handler.escalate()

    All methods propagate self.user_id to enforce tenant isolation.
    All methods return {"ok": bool, ...} matching GeminiLiveLLMService result_callback.
    """

    def __init__(self, user_id: str, tenant_config: dict, db=None):
        self.user_id = user_id
        self.config = tenant_config
        self.db = db or get_db()
        logger.info("[CobranzaOrchestrator] initialized for user=%s", user_id)

    async def update_debtor(self, debtor_id: str, fields: dict) -> dict:
        """
        Update debtor status/fields via debtor_updater sub-agent.

        Args:
            debtor_id: String ObjectId of the debtor.
            fields: Fields to patch (e.g. {"estado": "promesa_de_pago"}).

        Returns:
            debtor_updater.update_debtor_status() result dict.
        """
        logger.info("[CobranzaOrchestrator] dispatch update_debtor for user %s", self.user_id)
        return await debtor_updater.update_debtor_status(self.db, self.user_id, debtor_id, fields)

    async def send_whatsapp(self, phone: str, message: str) -> dict:
        """
        Enqueue WhatsApp message via whatsapp_notifier sub-agent (ARQ async dispatch).

        Returns immediately — never blocks for send completion (Pitfall 3).

        Args:
            phone: Destination phone number.
            message: Message body.

        Returns:
            whatsapp_notifier.send_whatsapp() result dict.
        """
        logger.info("[CobranzaOrchestrator] dispatch send_whatsapp for user %s", self.user_id)
        return await whatsapp_notifier.send_whatsapp(self.user_id, phone, message)

    async def verify_identity(self, utterance: str, debtor_name: Optional[str] = None) -> dict:
        """
        Verify caller identity via identity_verifier sub-agent.

        Uses regex fast-path first; LLM fallback only if ambiguous.

        Args:
            utterance: What the called party said.
            debtor_name: Expected debtor name (falls back to tenant_config debtor_name).

        Returns:
            identity_verifier.verify_identity() result dict.
        """
        logger.info("[CobranzaOrchestrator] dispatch verify_identity for user %s", self.user_id)
        name = debtor_name or self.config.get("debtor_name", "")
        return await identity_verifier.verify_identity(utterance, name)

    async def escalate(self, reason: str, debtor_id: Optional[str] = None) -> dict:
        """
        Escalate debtor via escalation_handler sub-agent.

        Sets estado="escalado", increments intentos, pushes WS dashboard event.

        Args:
            reason: Human-readable escalation reason.
            debtor_id: String ObjectId of the debtor (falls back to tenant_config).

        Returns:
            escalation_handler.escalate() result dict.
        """
        logger.info("[CobranzaOrchestrator] dispatch escalate for user %s", self.user_id)
        did = debtor_id or self.config.get("debtor_id", "")
        return await escalation_handler.escalate(self.db, self.user_id, did, reason)
