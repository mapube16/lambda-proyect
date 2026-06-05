"""
Landa Office UI — FastAPI Router
Endpoints for campaign management, leads, KPIs, and real-time updates.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from database import get_db
import state

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Models ────────────────────────────────────────────────────────────────────


class CreateCampaignRequest(BaseModel):
    """Create campaign request (conversational modal)."""
    name: str = Field(..., min_length=1, max_length=200)
    sectors: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    icp_description: str = Field(default="", max_length=1000)
    notes: Optional[str] = None


class UpdateCampaignRequest(BaseModel):
    """Update campaign request."""
    name: Optional[str] = None
    sectors: Optional[list[str]] = None
    cities: Optional[list[str]] = None
    icp_description: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class SendLeadRequest(BaseModel):
    """Send lead via email or WhatsApp."""
    channel: str = Field(..., pattern="^(email|whatsapp)$")
    body: str = Field(..., min_length=10, max_length=5000)
    subject: Optional[str] = None  # for email


class ApproveLeadRequest(BaseModel):
    """Approve lead (move to aprobados)."""
    notes: Optional[str] = None


class EditLeadRequest(BaseModel):
    """Edit lead before sending."""
    email: Optional[str] = None
    phone: Optional[str] = None
    custom_email_body: Optional[str] = None
    notes: Optional[str] = None


# ── 1. Campaigns CRUD ─────────────────────────────────────────────────────────


@router.get("/api/campaigns")
async def list_campaigns(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all campaigns for the user (paginated)."""
    user_id = str(current_user["user_id"])
    db = get_db()

    campaigns = await db.campaigns.find({"user_id": user_id}) \
        .sort("created_at", -1) \
        .skip(offset) \
        .limit(limit) \
        .to_list(length=limit)

    total = await db.campaigns.count_documents({"user_id": user_id})

    return {
        "campaigns": [
            {
                "id": str(c["_id"]),
                "name": c.get("name", "Unnamed Campaign"),
                "sectors": c.get("sectors", []),
                "cities": c.get("cities", []),
                "is_active": c.get("is_active", False),
                "created_at": c.get("created_at", datetime.now(timezone.utc)).isoformat(),
                "updated_at": c.get("updated_at", c.get("created_at", datetime.now(timezone.utc))).isoformat(),
            }
            for c in campaigns
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/api/campaigns")
async def create_campaign(
    request: CreateCampaignRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new campaign."""
    user_id = str(current_user["user_id"])
    db = get_db()

    campaign = {
        "user_id": user_id,
        "name": request.name,
        "sectors": request.sectors,
        "cities": request.cities,
        "icp_description": request.icp_description,
        "notes": request.notes or "",
        "is_active": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "status": "draft",  # draft, active, archived
    }

    result = await db.campaigns.insert_one(campaign)

    return {
        "id": str(result.inserted_id),
        "name": campaign["name"],
        "status": "created",
    }


@router.get("/api/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get campaign detail + KPIs."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        campaign = await db.campaigns.find_one({
            "_id": ObjectId(campaign_id),
            "user_id": user_id,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get KPIs for this campaign
    leads = await db.leads.find({"campaign_id": campaign_id, "user_id": user_id}).to_list(length=1000)
    approved_leads = [l for l in leads if l.get("hitl_status") == "approved"]
    sent_leads = [l for l in leads if l.get("estado") == "sent"]
    replied_leads = [l for l in leads if l.get("email_events", {}).get("replies", 0) > 0]

    return {
        "id": str(campaign["_id"]),
        "name": campaign.get("name", ""),
        "sectors": campaign.get("sectors", []),
        "cities": campaign.get("cities", []),
        "is_active": campaign.get("is_active", False),
        "created_at": campaign.get("created_at", datetime.now(timezone.utc)).isoformat(),
        "kpis": {
            "leads_qualified": len(leads),
            "leads_approved": len(approved_leads),
            "leads_sent": len(sent_leads),
            "leads_replied": len(replied_leads),
            "approval_rate": len(approved_leads) / max(len(leads), 1),
        },
    }


@router.patch("/api/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    request: UpdateCampaignRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update campaign metadata."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        obj_id = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    campaign = await db.campaigns.find_one({"_id": obj_id, "user_id": user_id})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    update_data = {
        "updated_at": datetime.now(timezone.utc),
    }
    if request.name is not None:
        update_data["name"] = request.name
    if request.sectors is not None:
        update_data["sectors"] = request.sectors
    if request.cities is not None:
        update_data["cities"] = request.cities
    if request.icp_description is not None:
        update_data["icp_description"] = request.icp_description
    if request.notes is not None:
        update_data["notes"] = request.notes
    if request.is_active is not None:
        update_data["is_active"] = request.is_active

    result = await db.campaigns.update_one(
        {"_id": obj_id, "user_id": user_id},
        {"$set": update_data},
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update campaign")

    return {"status": "updated", "campaign_id": campaign_id}


@router.delete("/api/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Archive/delete campaign."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        obj_id = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    result = await db.campaigns.update_one(
        {"_id": obj_id, "user_id": user_id},
        {"$set": {"is_active": False, "status": "archived", "updated_at": datetime.now(timezone.utc)}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {"status": "archived", "campaign_id": campaign_id}


@router.post("/api/campaigns/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Launch prospecting run for campaign."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        obj_id = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    campaign = await db.campaigns.find_one({"_id": obj_id, "user_id": user_id})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Check if already running
    active_run = await db.runs.find_one({
        "campaign_id": campaign_id,
        "user_id": user_id,
        "status": {"$in": ["queued", "running"]},
    })
    if active_run:
        raise HTTPException(status_code=409, detail="Campaign already has an active run")

    # Enqueue prospecting job
    import uuid
    run_id = str(uuid.uuid4())
    await db.runs.insert_one({
        "run_id": run_id,
        "campaign_id": campaign_id,
        "user_id": user_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "completed_at": None,
        "total_found": 0,
        "total_approved": 0,
        "agent_logs": {},
    })

    # Mark campaign as active
    await db.campaigns.update_one(
        {"_id": obj_id, "user_id": user_id},
        {"$set": {"is_active": True}},
    )

    # Enqueue ARQ job
    if state.arq_pool:
        await state.arq_pool.enqueue_job(
            "run_prospecting_job",
            run_id=run_id,
            user_id=user_id,
            campaign_id=str(campaign_id),
            campaign={k: v for k, v in campaign.items() if k not in ("_id", "user_id")},
            max_results=50,
            personality_prompt="",
            runtime_agents=[],
            excluded_domains=[],
            source_priority="serper",
            _job_id=run_id,
        )

    return {
        "status": "launched",
        "run_id": run_id,
        "campaign_id": campaign_id,
    }


@router.get("/api/campaigns/{campaign_id}/runs")
async def get_campaign_runs(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List runs for a campaign."""
    user_id = str(current_user["user_id"])
    db = get_db()

    runs = await db.runs.find({
        "campaign_id": campaign_id,
        "user_id": user_id,
    }) \
        .sort("created_at", -1) \
        .skip(offset) \
        .limit(limit) \
        .to_list(length=limit)

    total = await db.runs.count_documents({
        "campaign_id": campaign_id,
        "user_id": user_id,
    })

    return {
        "runs": [
            {
                "id": r["run_id"],
                "status": r.get("status", "queued"),
                "created_at": r.get("created_at", datetime.now(timezone.utc)).isoformat(),
                "total_found": r.get("total_found", 0),
                "total_approved": r.get("total_approved", 0),
            }
            for r in runs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── 2. Leads Management ───────────────────────────────────────────────────────


@router.get("/api/campaigns/{campaign_id}/leads")
async def list_leads(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    status: str = Query("all", regex="^(all|approved|rejected|sent|pending)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("score", regex="^(score|created_at|status)$"),
):
    """List leads for a campaign with optional filtering."""
    user_id = str(current_user["user_id"])
    db = get_db()

    # Build filter
    query = {"campaign_id": campaign_id, "user_id": user_id}
    if status != "all":
        if status == "approved":
            query["hitl_status"] = "approved"
        elif status == "rejected":
            query["hitl_status"] = "rejected"
        elif status == "sent":
            query["estado"] = "sent"
        elif status == "pending":
            query["hitl_status"] = None

    # Sort
    sort_field = "score" if sort_by == "score" else "created_at"
    sort_order = -1 if sort_by == "score" else -1

    leads = await db.leads.find(query) \
        .sort(sort_field, sort_order) \
        .skip(offset) \
        .limit(limit) \
        .to_list(length=limit)

    total = await db.leads.count_documents(query)

    return {
        "leads": [
            {
                "id": str(l["_id"]),
                "company_name": l.get("company_name", ""),
                "sector": l.get("sector", ""),
                "city": l.get("city", ""),
                "score": l.get("score", 0),
                "decision_maker": l.get("decision_maker", ""),
                "email": l.get("email", ""),
                "phone": l.get("phone", ""),
                "reason": l.get("reason", ""),
                "status": l.get("hitl_status") or "pending",
                "sent_at": l.get("sent_at"),
                "opens": l.get("email_events", {}).get("opens", 0),
                "clicks": l.get("email_events", {}).get("clicks", 0),
                "replies": l.get("email_events", {}).get("replies", 0),
            }
            for l in leads
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "kpis": {
            "approved": await db.leads.count_documents({**query, "hitl_status": "approved"}),
            "rejected": await db.leads.count_documents({**query, "hitl_status": "rejected"}),
            "sent": await db.leads.count_documents({**query, "estado": "sent"}),
        },
    }


@router.post("/api/campaigns/{campaign_id}/leads/{lead_id}/approve")
async def approve_lead(
    campaign_id: str,
    lead_id: str,
    request: ApproveLeadRequest,
    current_user: dict = Depends(get_current_user),
):
    """Approve lead (move to aprobados)."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        obj_id = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead ID")

    result = await db.leads.update_one(
        {"_id": obj_id, "campaign_id": campaign_id, "user_id": user_id},
        {
            "$set": {
                "hitl_status": "approved",
                "hitl_notes": request.notes or "",
                "approved_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {"status": "approved", "lead_id": lead_id}


@router.post("/api/campaigns/{campaign_id}/leads/{lead_id}/send")
async def send_lead(
    campaign_id: str,
    lead_id: str,
    request: SendLeadRequest,
    current_user: dict = Depends(get_current_user),
):
    """Send lead via email or WhatsApp."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        obj_id = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead ID")

    lead = await db.leads.find_one({
        "_id": obj_id,
        "campaign_id": campaign_id,
        "user_id": user_id,
    })

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # TODO: Implement email/WhatsApp sending logic
    # For now, just mark as sent and store tracking ID
    import uuid
    tracking_id = str(uuid.uuid4())

    result = await db.leads.update_one(
        {"_id": obj_id},
        {
            "$set": {
                "estado": "sent",
                "channel": request.channel,
                "custom_body": request.body,
                "subject": request.subject,
                "tracking_id": tracking_id,
                "sent_at": datetime.now(timezone.utc),
                "email_events": {
                    "opens": 0,
                    "clicks": 0,
                    "replies": 0,
                },
            }
        },
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to send lead")

    return {
        "status": "sent",
        "lead_id": lead_id,
        "tracking_id": tracking_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "channel": request.channel,
    }


@router.patch("/api/campaigns/{campaign_id}/leads/{lead_id}")
async def edit_lead(
    campaign_id: str,
    lead_id: str,
    request: EditLeadRequest,
    current_user: dict = Depends(get_current_user),
):
    """Edit lead before sending."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        obj_id = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead ID")

    lead = await db.leads.find_one({
        "_id": obj_id,
        "campaign_id": campaign_id,
        "user_id": user_id,
    })

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = {}
    if request.email is not None:
        update_data["email"] = request.email
    if request.phone is not None:
        update_data["phone"] = request.phone
    if request.custom_email_body is not None:
        update_data["custom_email_body"] = request.custom_email_body
    if request.notes is not None:
        update_data["edit_notes"] = request.notes

    update_data["updated_at"] = datetime.now(timezone.utc)

    result = await db.leads.update_one(
        {"_id": obj_id},
        {"$set": update_data},
    )

    return {"status": "updated", "lead_id": lead_id}


@router.delete("/api/campaigns/{campaign_id}/leads/{lead_id}")
async def discard_lead(
    campaign_id: str,
    lead_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Discard/reject lead."""
    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        obj_id = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead ID")

    result = await db.leads.update_one(
        {"_id": obj_id, "campaign_id": campaign_id, "user_id": user_id},
        {
            "$set": {
                "hitl_status": "rejected",
                "rejected_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {"status": "rejected", "lead_id": lead_id}


# ── 3. KPIs & Analytics ──────────────────────────────────────────────────────


@router.get("/api/campaigns/{campaign_id}/kpis")
async def get_campaign_kpis(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get KPIs for a campaign."""
    user_id = str(current_user["user_id"])
    db = get_db()

    leads = await db.leads.find({"campaign_id": campaign_id, "user_id": user_id}).to_list(length=1000)

    approved = [l for l in leads if l.get("hitl_status") == "approved"]
    rejected = [l for l in leads if l.get("hitl_status") == "rejected"]
    sent = [l for l in leads if l.get("estado") == "sent"]

    return {
        "leads_qualified": len(leads),
        "leads_approved": len(approved),
        "leads_rejected": len(rejected),
        "leads_sent": len(sent),
        "approval_rate": len(approved) / max(len(leads), 1),
        "send_rate": len(sent) / max(len(approved), 1),
    }


@router.get("/api/campaigns/{campaign_id}/metrics")
async def get_campaign_metrics(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get email metrics for a campaign."""
    user_id = str(current_user["user_id"])
    db = get_db()

    sent_leads = await db.leads.find({
        "campaign_id": campaign_id,
        "user_id": user_id,
        "estado": "sent",
    }).to_list(length=1000)

    total_opens = sum(l.get("email_events", {}).get("opens", 0) for l in sent_leads)
    total_clicks = sum(l.get("email_events", {}).get("clicks", 0) for l in sent_leads)
    total_replies = sum(l.get("email_events", {}).get("replies", 0) for l in sent_leads)

    total_sent = len(sent_leads)

    return {
        "total_sent": total_sent,
        "opens": total_opens,
        "open_rate": total_opens / max(total_sent, 1),
        "clicks": total_clicks,
        "click_rate": total_clicks / max(total_sent, 1),
        "replies": total_replies,
        "reply_rate": total_replies / max(total_sent, 1),
    }


@router.get("/api/tenant/quota")
async def get_tenant_quota(
    current_user: dict = Depends(get_current_user),
):
    """Get quota/billing info for tenant."""
    user_id = str(current_user["user_id"])
    db = get_db()

    quota = await db.tenant_quotas.find_one({"user_id": user_id})

    if not quota:
        return {
            "plan": "free",
            "credits_remaining": 0,
            "credits_total": 0,
            "usage_percent": 0,
            "reset_date": None,
        }

    remaining = quota.get("credits_remaining", 0)
    total = quota.get("credits_total", 13500)

    return {
        "plan": quota.get("plan", "pro"),
        "credits_remaining": remaining,
        "credits_total": total,
        "usage_percent": ((total - remaining) / total * 100) if total > 0 else 0,
        "reset_date": quota.get("reset_date"),
    }
