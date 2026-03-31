"""
webhooks.py — Vapi webhook handlers for the cobranza voice agent.

Two endpoints:
  POST /api/vapi/tool-call   — real-time tool dispatch during a live call
  POST /api/vapi/call-ended  — end-of-call-report processing and debtor state update

CRITICAL: Both endpoints ALWAYS return HTTP 200 regardless of errors.
Vapi requires 200 to proceed; non-200 responses abort the call.
"""
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import get_db

logger = logging.getLogger("cobranza.webhooks")

vapi_router = APIRouter(tags=["vapi-webhooks"])

# Intentos states that are "terminal" — call-ended must not overwrite them
_TERMINAL_ESTADOS = {"promesa_de_pago", "escalado", "pagado"}


# ── Tool dispatch helper ───────────────────────────────────────────────────────

async def dispatch_tool(name: str, params: dict, call_obj: dict) -> str:
    """
    Dispatch a Vapi tool call to the appropriate handler.
    Always returns a plain string suitable for Vapi's result field.

    debtor_id is extracted from params first, then from assistantOverrides.variableValues.
    """
    debtor_id = (
        params.get("debtor_id")
        or call_obj.get("assistantOverrides", {})
                   .get("variableValues", {})
                   .get("debtor_id")
    )
    db = get_db()

    try:
        if name == "consultar_deuda":
            debtor = (
                await db.debtors.find_one({"_id": ObjectId(debtor_id)})
                if debtor_id
                else None
            )
            if not debtor:
                return "Deudor no encontrado en el sistema."
            vencimiento = debtor.get("vencimiento")
            if hasattr(vencimiento, "strftime"):
                fecha_str = vencimiento.strftime("%d/%m/%Y")
            else:
                fecha_str = str(vencimiento)
            return (
                f"Deuda: ${debtor['monto']:,.0f} COP. "
                f"Vencimiento: {fecha_str}."
            )

        elif name == "registrar_promesa":
            monto_prom = params.get("monto_prometido")
            fecha_prom = params.get("fecha_prometida")
            if debtor_id:
                await db.debtors.update_one(
                    {"_id": ObjectId(debtor_id)},
                    {
                        "$set": {
                            "estado": "promesa_de_pago",
                            "monto_prometido": monto_prom,
                            "fecha_promesa": fecha_prom,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
            return f"Promesa registrada: ${monto_prom} para {fecha_prom}. Gracias."

        elif name == "escalar_a_humano":
            motivo = params.get("motivo", "")  # noqa: F841
            if debtor_id:
                await db.debtors.update_one(
                    {"_id": ObjectId(debtor_id)},
                    {
                        "$set": {
                            "estado": "escalado",
                            "escalado": True,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
            return "Escalado a agente humano. Un asesor le contactará pronto."

        else:
            return "Herramienta no reconocida."

    except Exception as exc:
        logger.error("[webhook] dispatch_tool error: %s", exc)
        return "Error interno al procesar la herramienta."


# ── POST /api/vapi/tool-call ──────────────────────────────────────────────────

@vapi_router.post("/api/vapi/tool-call")
@vapi_router.post("/api/vapi/webhook")
async def handle_tool_call(request: Request):
    """
    Unified Vapi serverUrl handler.
    Routes by message.type:
      - tool-calls / toolWithToolCallList  → dispatch tools
      - end-of-call-report                 → update debtor state (same as /call-ended)
    Always returns HTTP 200.
    """
    try:
        body = await request.json()
        message = body.get("message", {})
        msg_type = message.get("type", "")

        # ── end-of-call-report: delegate to call-ended logic ──────────────────
        if msg_type == "end-of-call-report":
            return await _process_call_ended(body)

        # ── tool call ─────────────────────────────────────────────────────────
        call_obj = message.get("call", {})
        tool_list = message.get("toolWithToolCallList", [])

        results = []
        for item in tool_list:
            tool_name = item.get("name", "")
            tool_call = item.get("toolCall", {})
            tool_call_id = tool_call.get("id", "")
            params = tool_call.get("parameters", {}) or {}

            result_str = await dispatch_tool(tool_name, params, call_obj)
            results.append({"toolCallId": tool_call_id, "result": result_str})

        return JSONResponse({"results": results}, status_code=200)

    except Exception as exc:
        logger.error("[webhook] handle_tool_call top-level error: %s", exc)
        return JSONResponse({"results": []}, status_code=200)


# ── Shared call-ended processing logic ───────────────────────────────────────

async def _process_call_ended(body: dict) -> JSONResponse:
    """Process an end-of-call-report payload. Returns JSONResponse."""
    try:
        message = body.get("message", {})

        # Only process end-of-call-report messages
        if message.get("type") != "end-of-call-report":
            return JSONResponse({"ok": True})

        call_id = (message.get("call") or {}).get("id")
        ended_reason = message.get("endedReason", "unknown")
        artifact = message.get("artifact") or {}
        duration_seconds = message.get("durationSeconds", 0) or 0

        db = get_db()

        # Find debtor by the active call id
        debtor = await db.debtors.find_one({"vapi_call_id": call_id})
        if not debtor:
            logger.warning("[webhook] call-ended: no debtor with vapi_call_id=%s", call_id)
            return JSONResponse({"ok": True})

        current_estado = debtor.get("estado", "pendiente")

        # Map endedReason to new_estado — terminal states take precedence
        if current_estado in _TERMINAL_ESTADOS:
            new_estado = current_estado
        elif ended_reason in ("no-answer", "busy", "voicemail"):
            new_estado = "sin_contacto"
        elif ended_reason in ("customer-ended-call", "assistant-ended-call", "hangup"):
            # Tool calls should have already set the state; keep existing
            new_estado = current_estado if current_estado not in ("llamando", "pendiente") else "sin_contacto"
        else:
            new_estado = "fallido"

        # Check if we've exhausted max_intentos
        current_intentos = debtor.get("intentos", 0)
        max_intentos = debtor.get("max_intentos", 5)
        new_intentos = current_intentos + 1
        if new_intentos >= max_intentos:
            new_estado = "agotado"

        # Build call record for historial
        transcript = artifact.get("transcript", "") or ""
        recording_url = artifact.get("recordingUrl", "") or ""
        summary = artifact.get("summary", "") or ""
        call_record = {
            "call_id": call_id,
            "fecha": datetime.now(timezone.utc),
            "duracion_segundos": int(duration_seconds),
            "resultado": ended_reason,
            "transcript": transcript[:2000],
            "summary": summary[:1000],
            "recording_url": recording_url,
        }

        now = datetime.now(timezone.utc)
        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {
                "$set": {
                    "estado": new_estado,
                    "updated_at": now,
                    "ultimo_contacto_fecha": now,
                },
                "$inc": {"intentos": 1},
                "$push": {"historial_llamadas": call_record},
                "$unset": {"vapi_call_id": ""},
            },
        )

        # Push real-time WebSocket event to the debtor owner
        # Lazy import inside function body to avoid circular import at module load
        try:
            from main import manager  # noqa: PLC0415
            await manager.send_to_user(
                str(debtor["user_id"]),
                {
                    "type": "debtor_update",
                    "debtor_id": str(debtor["_id"]),
                    "estado": new_estado,
                    "intentos": new_intentos,
                },
            )
        except Exception as ws_exc:
            logger.warning("[webhook] WS push failed (non-fatal): %s", ws_exc)

        return JSONResponse({"ok": True})

    except Exception as exc:
        logger.error("[webhook] _process_call_ended error: %s", exc)
        return JSONResponse({"ok": True})


# ── POST /api/vapi/call-ended ─────────────────────────────────────────────────

@vapi_router.post("/api/vapi/call-ended")
async def handle_call_ended(request: Request):
    """Kept for backwards compatibility. Delegates to _process_call_ended."""
    body = await request.json()
    return await _process_call_ended(body)
