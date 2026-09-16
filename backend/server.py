from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Header, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, List

from auth import (
    hash_password, verify_password, create_access_token, decode_token, extract_token,
)
import workflow as wf
from extras import ist_today_str, ist_day_bounds, to_csv
from storage import put_object, get_object, init_storage, APP_NAME
from fastapi.responses import Response

# ---- DB ----
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI()
api = APIRouter(prefix="/api")
logger = logging.getLogger("ecp")
logging.basicConfig(level=logging.INFO)

NO_ID = {"_id": 0}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


# ========================= AUTH =========================
async def get_current_user(request: Request) -> dict:
    token = extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.users.find_one({"id": payload.get("sub")}, NO_ID)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")
    user.pop("password_hash", None)
    return user


def require(user: dict, *roles):
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="You do not have permission for this action")


class LoginBody(BaseModel):
    username: str
    password: str


@api.post("/auth/login")
async def login(body: LoginBody):
    user = await db.users.find_one({"username": body.username.strip().lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")
    token = create_access_token(user["id"], user["username"])
    user.pop("password_hash", None)
    user.pop("_id", None)
    return {"token": token, "user": user}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


# ========================= USERS (Owner only) =========================
class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    role: str
    phone: str
    team: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    team: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


def public_user(u: dict):
    u.pop("password_hash", None)
    u.pop("_id", None)
    return u


@api.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    users = await db.users.find({}, NO_ID).to_list(1000)
    for u in users:
        u.pop("password_hash", None)
    return users


@api.get("/users/team/{role}")
async def list_team_users(role: str, user: dict = Depends(get_current_user)):
    require(user, "OWNER", "MANAGER", "INSTALLATION_MANAGER")
    if role not in wf.ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    role_q = {"$in": list(wf.INSTALL_MEMBER_ROLES)} if role == "INSTALLATION" else role
    users = await db.users.find({"role": role_q, "active": True}, NO_ID).to_list(1000)
    return [{"id": u["id"], "name": u["name"], "username": u["username"], "role": u["role"]} for u in users]


@api.post("/users")
async def create_user(body: UserCreate, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    if body.role not in wf.ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if not (body.phone or "").strip():
        raise HTTPException(status_code=400, detail="Phone number is required")
    username = body.username.strip().lower()
    if await db.users.find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Username already exists")
    doc = {
        "id": new_id(),
        "username": username,
        "password_hash": hash_password(body.password),
        "name": body.name.strip(),
        "role": body.role,
        "team": body.role,  # one user = one role = one team
        "phone": body.phone.strip(),
        "active": True,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return public_user(dict(doc))


@api.patch("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    upd = {}
    if body.name is not None:
        upd["name"] = body.name.strip()
    if body.role is not None:
        if body.role not in wf.ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        upd["role"] = body.role
        upd["team"] = body.role
    if body.active is not None:
        upd["active"] = body.active
    if body.password:
        upd["password_hash"] = hash_password(body.password)
    if body.phone is not None:
        upd["phone"] = body.phone.strip()
    if upd:
        await db.users.update_one({"id": user_id}, {"$set": upd})
    fresh = await db.users.find_one({"id": user_id}, NO_ID)
    fresh.pop("password_hash", None)
    return fresh


# ========================= SLA CONFIG (Owner only to edit) =========================
class SLABody(BaseModel):
    config: dict  # {stage: days}


@api.get("/sla")
async def get_sla(user: dict = Depends(get_current_user)):
    docs = await db.stage_sla_config.find({}, NO_ID).to_list(100)
    cfg = {d["stage"]: d["sla_days"] for d in docs}
    for s in wf.STAGE_ORDER:
        cfg.setdefault(s, 0)
    return cfg


@api.put("/sla")
async def set_sla(body: SLABody, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    for stage, days in body.config.items():
        if stage not in wf.STAGE_ORDER:
            continue
        await db.stage_sla_config.update_one(
            {"stage": stage}, {"$set": {"stage": stage, "sla_days": int(days)}}, upsert=True
        )
    return await get_sla(user)


async def get_sla_map():
    docs = await db.stage_sla_config.find({}, NO_ID).to_list(100)
    return {d["stage"]: d["sla_days"] for d in docs}


# ========================= LEADS =========================
class LeadCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = ""
    address: Optional[str] = ""
    source: Optional[str] = ""
    financing_required: bool = False
    project_price: Optional[float] = 0
    item_id: Optional[str] = None
    quantity: Optional[float] = None
    location_link: Optional[str] = ""
    remarks: Optional[str] = ""


class ProjectPriceBody(BaseModel):
    project_price: float


class LeadAction(BaseModel):
    action: str
    lost_reason: Optional[str] = None
    lost_remarks: Optional[str] = None
    followup_date: Optional[str] = None
    remarks: Optional[str] = None
    reason: Optional[str] = None


def lead_visible_roles():
    return ["OWNER", "MANAGER", "LEAD"]


@api.get("/leads")
async def list_leads(status: Optional[str] = None, followup: Optional[str] = None, user: dict = Depends(get_current_user)):
    if user["role"] not in lead_visible_roles():
        # other teams get read-only limited visibility (qualified leads linked to ECPs they see)
        return []
    q = {}
    if status:
        q["status"] = status
    if followup == "today":
        today = ist_today_str()
        fus = await db.lead_followups.find({}, NO_ID).to_list(10000)
        lead_ids = list({f["lead_id"] for f in fus if (f.get("followup_date") or "")[:10] == today})
        q["id"] = {"$in": lead_ids}
        q["status"] = "FOLLOW_UP"
    leads = await db.leads.find(q, NO_ID).sort("created_at", -1).to_list(2000)
    if user["role"] == "LEAD":
        leads = [l for l in leads if l.get("lead_owner_id") in (user["id"], None)]
    return leads


@api.post("/leads")
async def create_lead(body: LeadCreate, user: dict = Depends(get_current_user)):
    require(user, "LEAD", "OWNER")
    # Lead Creator is always the authenticated user who creates the lead.
    creator_id, creator_name = user["id"], user["name"]
    # Duplicate active-lead check (server-side): ACTIVE = any status except LOST
    phone = body.phone.strip()
    dup = await db.leads.find_one({"phone": phone, "status": {"$ne": "LOST"}}, NO_ID)
    if dup:
        raise HTTPException(status_code=409, detail=f"An active lead already exists for {phone} ({dup['name']})")
    item_name, item_unit = None, None
    if body.item_id:
        it = await db.items.find_one({"id": body.item_id}, NO_ID)
        if not it or not it.get("active", True):
            raise HTTPException(status_code=400, detail="Invalid or inactive item")
        item_name, item_unit = it["name"], it["unit"]
    await enforce_lead_mandatory(body, item_name)
    doc = {
        "id": new_id(),
        "name": body.name.strip(),
        "phone": phone,
        "email": (body.email or "").strip(),
        "address": (body.address or "").strip(),
        "source": (body.source or "").strip(),
        "remarks": (body.remarks or "").strip(),
        "item_id": body.item_id,
        "item_name": item_name,
        "item_unit": item_unit,
        "quantity": body.quantity,
        "location_link": (body.location_link or "").strip(),
        "status": "PENDING",
        "current_team": "LEAD",
        "action_required": True,
        "return_reason": None,
        "financing_required": bool(body.financing_required),
        "project_price": float(body.project_price or 0),
        "lead_creator_id": creator_id,
        "lead_creator_name": creator_name,
        "lead_owner_id": user["id"],
        "lead_owner_name": user["name"],
        "lost_reason": None,
        "lost_remarks": None,
        "ecp_id": None,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.leads.insert_one(doc)
    await log_activity(user, "Lead Created", "LEAD", doc["id"], doc["name"], f"Creator: {creator_name or '—'}")
    d = dict(doc)
    d.pop("_id", None)
    return d


async def _current_docs(lead_id: str):
    return await db.lead_documents.find({"lead_id": lead_id, "status": "CURRENT"}, NO_ID).sort("uploaded_at", -1).to_list(200)


async def _documents_status(lead_id: str, financing: bool):
    docs = await _current_docs(lead_id)
    types = {d["doc_type"] for d in docs}
    missing = [wf.DOC_LABELS[t] for t in wf.DOC_REQUIRED_SINGLE if t not in types]
    if not any(t in types for t in wf.DOC_BANK_GROUP):
        missing.append("Bank Proof (Passbook / 3-Month Statement / Cancelled Cheque)")
    if financing and not any(t in types for t in wf.DOC_FINANCE_GROUP):
        missing.append("Finance Proof (Property Paper / Tax Receipt)")
    return {"complete": wf.documents_complete(types, financing),
            "uploaded_types": sorted(types), "missing": missing, "count": len(docs),
            "financing_required": financing}


async def _lead_bundle(lead_id: str):
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    followups = await db.lead_followups.find({"lead_id": lead_id}, NO_ID).sort("created_at", -1).to_list(500)
    site_visits = await db.lead_site_visits.find({"lead_id": lead_id}, NO_ID).sort("created_at", -1).to_list(500)
    escalations = await db.lead_escalations.find({"lead_id": lead_id}, NO_ID).sort("created_at", -1).to_list(500)
    ecp = None
    if lead.get("ecp_id"):
        ecp = await db.ecps.find_one({"id": lead["ecp_id"]}, NO_ID)
    docs_status = await _documents_status(lead_id, bool(lead.get("financing_required")))
    return {"lead": lead, "followups": followups, "site_visits": site_visits,
            "escalations": escalations, "ecp": ecp, "documents_status": docs_status}


@api.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user: dict = Depends(get_current_user)):
    require(user, "OWNER", "MANAGER", "LEAD")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if user["role"] == "LEAD" and lead.get("lead_owner_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="This lead is not assigned to you")
    return await _lead_bundle(lead_id)


class ReassignLead(BaseModel):
    assigned_user: str


@api.post("/leads/{lead_id}/reassign")
async def reassign_lead(lead_id: str, body: ReassignLead, user: dict = Depends(get_current_user)):
    require(user, "MANAGER", "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("status") == "LOST":
        raise HTTPException(status_code=400, detail="LOST leads cannot be reassigned")
    emp = await db.users.find_one({"id": body.assigned_user}, NO_ID)
    if not emp or emp["role"] != "LEAD" or not emp.get("active", True):
        raise HTTPException(status_code=400, detail="Assignee must be an active Lead Team user")
    prev = lead.get("lead_owner_name") or "—"
    await db.leads.update_one({"id": lead_id}, {"$set": {
        "lead_owner_id": emp["id"], "lead_owner_name": emp["name"], "updated_at": now_iso()}})
    await log_activity(user, "Lead Reassigned", "LEAD", lead_id, lead["name"], f"{prev} → {emp['name']}")
    return await _lead_bundle(lead_id)


@api.post("/leads/{lead_id}/project-price")
async def set_project_price(lead_id: str, body: ProjectPriceBody, user: dict = Depends(get_current_user)):
    require(user, "LEAD", "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("ecp_id"):
        raise HTTPException(status_code=400, detail="Lead already handed off. Use a Commercial Change request to modify price.")
    if user["role"] == "LEAD" and lead.get("lead_owner_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="This lead is not assigned to you")
    price = float(body.project_price or 0)
    await db.leads.update_one({"id": lead_id}, {"$set": {"project_price": price, "updated_at": now_iso()}})
    return await _lead_bundle(lead_id)


async def create_ecp_from_lead(lead: dict, user: dict):
    financing = bool(lead.get("financing_required"))
    ecp_id = new_id()
    ecp = {
        "id": ecp_id,
        "lead_id": lead["id"],
        "lead_name": lead["name"],
        "customer_phone": lead.get("phone", ""),
        "customer_email": lead.get("email", ""),
        "customer_address": lead.get("address", ""),
        "location_link": lead.get("location_link", ""),
        "item_id": lead.get("item_id"),
        "item_name": lead.get("item_name"),
        "item_unit": lead.get("item_unit"),
        "quantity": lead.get("quantity"),
        "project_price": float(lead.get("project_price") or 0),
        "lead_creator_id": lead.get("lead_creator_id"),
        "lead_creator_name": lead.get("lead_creator_name"),
        "lead_owner_id": lead.get("lead_owner_id"),
        "lead_owner_name": lead.get("lead_owner_name"),
        "current_stage": "PENDING_DOCUMENTS",
        "current_team": "LEAD",
        "documents_released": False,
        "responsible_user": None,
        "responsible_user_name": None,
        "financing_required": financing,
        "status": "ACTIVE",
        "dispatch_started": False,
        "install_status": None,
        "stage_entry_date": now_iso(),
        "closed_at": None,
        "closed_by": None,
        "closure_reason": None,
        "closure_remarks": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.ecps.insert_one(ecp)
    await db.ecp_stage_history.insert_one({
        "id": new_id(), "ecp_id": ecp_id, "from_stage": None, "to_stage": "PENDING_DOCUMENTS",
        "changed_by": user["id"], "changed_by_name": user["name"], "changed_at": now_iso(),
        "note": "ECP created from qualified lead — pending required documents",
    })
    return ecp_id


async def _create_reg1_tasks(ecp_id: str, financing: bool):
    task_docs = _tasks_from_specs(ecp_id, "REGISTRATION_1", financing)
    if task_docs:
        await db.ecp_tasks.insert_many(task_docs)


async def _release_documents_to_reg1(ecp: dict, user: dict):
    ecp_id = ecp["id"]
    await _create_reg1_tasks(ecp_id, bool(ecp.get("financing_required")))
    await db.ecps.update_one({"id": ecp_id}, {"$set": {
        "current_stage": "REGISTRATION_1", "current_team": wf.STAGE_TEAM["REGISTRATION_1"],
        "documents_released": True, "stage_entry_date": now_iso(), "updated_at": now_iso()}})
    await db.ecp_stage_history.insert_one({
        "id": new_id(), "ecp_id": ecp_id, "from_stage": "PENDING_DOCUMENTS", "to_stage": "REGISTRATION_1",
        "changed_by": user["id"], "changed_by_name": user["name"], "changed_at": now_iso(),
        "note": "All required documents uploaded — released to Registration 1",
    })


def _make_task(ecp_id, stage, name, applicable, team=None, requires=None):
    return {
        "id": new_id(), "ecp_id": ecp_id, "stage": stage, "task_name": name,
        "applicable": applicable, "completed": False, "completed_by": None,
        "completed_by_name": None, "completed_at": None,
        "team": team or wf.STAGE_TEAM.get(stage), "requires": requires,
    }


def _tasks_from_specs(ecp_id, stage, financing):
    specs = wf.STAGE_TASK_SPECS.get(stage, [])
    return [_make_task(ecp_id, stage, name, (not fin_only) or bool(financing), team, req)
            for (name, team, fin_only, req) in specs]


@api.post("/leads/{lead_id}/action")
async def lead_action(lead_id: str, body: LeadAction, user: dict = Depends(get_current_user)):
    require(user, "LEAD")  # Only Lead Team decides the 5 actions (Phase 1 spec D)
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("lead_owner_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="This lead is not assigned to you")
    if lead["status"] in ("QUALIFIED", "LOST") and not lead.get("action_required"):
        raise HTTPException(status_code=400, detail="Lead is not currently actionable")
    action = body.action
    if action not in wf.LEAD_ACTIONS:
        raise HTTPException(status_code=400, detail="Invalid action")

    if action == "YES":
        if lead.get("ecp_id"):
            raise HTTPException(status_code=400, detail="Lead already has an ECP")
        ecp_id = await create_ecp_from_lead(lead, user)
        await db.leads.update_one({"id": lead_id}, {"$set": {
            "status": "QUALIFIED", "action_required": False, "current_team": None,
            "return_reason": None, "ecp_id": ecp_id, "updated_at": now_iso()}})

    elif action == "NO":
        if not body.lost_reason:
            raise HTTPException(status_code=400, detail="Lost reason is required")
        if body.lost_reason == "OTHER" and not (body.lost_remarks or "").strip():
            raise HTTPException(status_code=400, detail="Remarks are mandatory when reason is OTHER")
        await db.leads.update_one({"id": lead_id}, {"$set": {
            "status": "LOST", "action_required": False, "current_team": None,
            "lost_reason": body.lost_reason, "lost_remarks": (body.lost_remarks or "").strip(),
            "updated_at": now_iso()}})

    elif action == "FOLLOW_UP":
        if not body.followup_date:
            raise HTTPException(status_code=400, detail="Follow-up date is required")
        if not (body.remarks or "").strip():
            raise HTTPException(status_code=400, detail="Remarks are required")
        try:
            fdate = datetime.fromisoformat(body.followup_date).date()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid follow-up date")
        if fdate < datetime.fromisoformat(ist_today_str()).date():
            raise HTTPException(status_code=400, detail="Follow-up date cannot be in the past")
        await db.lead_followups.insert_one({
            "id": new_id(), "lead_id": lead_id, "followup_date": body.followup_date,
            "remarks": body.remarks.strip(), "created_by": user["id"],
            "created_by_name": user["name"], "created_at": now_iso()})
        await db.leads.update_one({"id": lead_id}, {"$set": {
            "status": "FOLLOW_UP", "action_required": True, "current_team": "LEAD",
            "return_reason": None, "updated_at": now_iso()}})

    elif action == "SITE_VISIT":
        open_sv = await db.lead_site_visits.find_one(
            {"lead_id": lead_id, "status": {"$in": ["REQUESTED", "ASSIGNED"]}})
        if open_sv:
            raise HTTPException(status_code=400, detail="An open site visit already exists for this lead")
        await db.lead_site_visits.insert_one({
            "id": new_id(), "lead_id": lead_id, "lead_name": lead["name"],
            "status": "REQUESTED", "assigned_user": None, "assigned_user_name": None,
            "visit_date": None, "survey_info": None, "requested_remarks": (body.remarks or "").strip(),
            "requested_by": user["id"], "requested_by_name": user["name"],
            "assigned_by": None, "created_at": now_iso(), "completed_at": None})
        await db.leads.update_one({"id": lead_id}, {"$set": {
            "status": "SITE_VISIT", "action_required": False,
            "current_team": "INSTALLATION", "return_reason": None, "updated_at": now_iso()}})

    elif action == "ESCALATION":
        if not (body.reason or "").strip():
            raise HTTPException(status_code=400, detail="Escalation reason is required")
        if not (body.remarks or "").strip():
            raise HTTPException(status_code=400, detail="Escalation remarks are required")
        await db.lead_escalations.insert_one({
            "id": new_id(), "lead_id": lead_id, "lead_name": lead["name"],
            "reason": body.reason.strip(), "remarks": body.remarks.strip(),
            "owner_remarks": None, "status": "OPEN", "created_by": user["id"],
            "created_by_name": user["name"], "created_at": now_iso(), "returned_at": None})
        await db.leads.update_one({"id": lead_id}, {"$set": {
            "status": "ESCALATED", "action_required": False, "current_team": "OWNER",
            "return_reason": None, "updated_at": now_iso()}})

    await log_activity(user, f"Lead Action: {action}", "LEAD", lead_id, lead["name"],
                       body.remarks or body.reason or body.lost_reason or "")
    return await _lead_bundle(lead_id)


@api.post("/leads/{lead_id}/reopen")
async def reopen_lead(lead_id: str, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead["status"] != "LOST":
        raise HTTPException(status_code=400, detail="Only LOST leads can be reopened")
    await db.leads.update_one({"id": lead_id}, {"$set": {
        "status": "PENDING", "action_required": True, "current_team": "LEAD",
        "return_reason": "REOPENED", "lost_reason": None, "lost_remarks": None,
        "updated_at": now_iso()}})
    return await _lead_bundle(lead_id)


class FinancingBody(BaseModel):
    financing_required: bool


@api.post("/leads/{lead_id}/financing")
async def lead_financing(lead_id: str, body: FinancingBody, user: dict = Depends(get_current_user)):
    require(user, "LEAD", "MANAGER", "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.leads.update_one({"id": lead_id}, {"$set": {
        "financing_required": bool(body.financing_required), "updated_at": now_iso()}})
    if lead.get("ecp_id"):
        await _apply_ecp_financing(lead["ecp_id"], bool(body.financing_required), user)
    return await _lead_bundle(lead_id)


# ========================= SITE VISITS =========================
@api.get("/site-visits")
async def list_site_visits(user: dict = Depends(get_current_user)):
    if user["role"] in ("OWNER", "MANAGER"):
        visits = await db.lead_site_visits.find({}, NO_ID).sort("created_at", -1).to_list(2000)
    elif user["role"] == "INSTALLATION_MANAGER":
        visits = await db.lead_site_visits.find({}, NO_ID).sort("created_at", -1).to_list(2000)
    elif user["role"] in ("INSTALLATION", "INSTALLATION_MEMBER"):
        visits = await db.lead_site_visits.find(
            {"assigned_user": user["id"]}, NO_ID).sort("created_at", -1).to_list(2000)
    else:
        visits = []
    return visits


class AssignSiteVisit(BaseModel):
    assigned_user: str
    visit_date: str


@api.post("/site-visits/{sv_id}/assign")
async def assign_site_visit(sv_id: str, body: AssignSiteVisit, user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION_MANAGER", "OWNER")
    sv = await db.lead_site_visits.find_one({"id": sv_id}, NO_ID)
    if not sv:
        raise HTTPException(status_code=404, detail="Site visit not found")
    if sv["status"] not in ("REQUESTED", "ASSIGNED"):
        raise HTTPException(status_code=400, detail="Site visit is not open")
    emp = await db.users.find_one({"id": body.assigned_user}, NO_ID)
    if not emp or emp["role"] not in wf.INSTALL_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="Assignee must be an Installation team member")
    await db.lead_site_visits.update_one({"id": sv_id}, {"$set": {
        "status": "ASSIGNED", "assigned_user": body.assigned_user,
        "assigned_user_name": emp["name"], "visit_date": body.visit_date,
        "assigned_by": user["id"], "assigned_by_name": user["name"]}})
    await log_activity(user, "Site Visit Assigned", "LEAD", sv["lead_id"], sv.get("lead_name", ""), f"To {emp['name']}")
    return await db.lead_site_visits.find_one({"id": sv_id}, NO_ID)


class ExtraMaterial(BaseModel):
    item_id: Optional[str] = None
    item_name: str
    quantity: float
    unit: str


class CompleteSiteVisit(BaseModel):
    structure_height: str
    earthing_cable_length: str
    dc_cable_length: str
    ac_cable_length: str
    surveyor_name: str
    extra_materials: List[ExtraMaterial] = []


@api.post("/site-visits/{sv_id}/complete")
async def complete_site_visit(sv_id: str, body: CompleteSiteVisit, user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION", "INSTALLATION_MEMBER", "OWNER")
    sv = await db.lead_site_visits.find_one({"id": sv_id}, NO_ID)
    if not sv:
        raise HTTPException(status_code=404, detail="Site visit not found")
    if sv["status"] != "ASSIGNED":
        raise HTTPException(status_code=400, detail="Only assigned site visits can be completed")
    if user["role"] in wf.INSTALL_MEMBER_ROLES and sv["assigned_user"] != user["id"]:
        raise HTTPException(status_code=403, detail="This site visit is not assigned to you")
    for f in ("structure_height", "earthing_cable_length", "dc_cable_length", "ac_cable_length", "surveyor_name"):
        if not (getattr(body, f) or "").strip():
            raise HTTPException(status_code=400, detail="All survey measurement fields and name are required")
    # validate extra material items against active Item Master where an item_id is given
    mats = []
    for m in body.extra_materials:
        if m.item_id:
            it = await db.items.find_one({"id": m.item_id}, NO_ID)
            if not it or not it.get("active", True):
                raise HTTPException(status_code=400, detail="Extra material item must be an active Item Master item")
        mats.append(m.dict())
    survey = {
        "structure_height": body.structure_height.strip(),
        "earthing_cable_length": body.earthing_cable_length.strip(),
        "dc_cable_length": body.dc_cable_length.strip(),
        "ac_cable_length": body.ac_cable_length.strip(),
        "surveyor_name": body.surveyor_name.strip(),
        "extra_materials": mats,
    }
    await db.lead_site_visits.update_one({"id": sv_id}, {"$set": {
        "status": "DONE", "survey_info": survey, "completed_at": now_iso()}})
    await db.leads.update_one({"id": sv["lead_id"]}, {"$set": {
        "status": "PENDING", "action_required": True, "current_team": "LEAD",
        "return_reason": "SITE_VISIT_COMPLETED", "updated_at": now_iso()}})
    await log_activity(user, "Site Visit Completed", "LEAD", sv["lead_id"], sv.get("lead_name", ""), "")
    return await db.lead_site_visits.find_one({"id": sv_id}, NO_ID)


# ========================= ESCALATIONS =========================
@api.get("/escalations")
async def list_escalations(user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    return await db.lead_escalations.find({}, NO_ID).sort("created_at", -1).to_list(2000)


class ReturnEscalation(BaseModel):
    owner_remarks: str


@api.post("/escalations/{esc_id}/return")
async def return_escalation(esc_id: str, body: ReturnEscalation, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    esc = await db.lead_escalations.find_one({"id": esc_id}, NO_ID)
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")
    if esc["status"] != "OPEN":
        raise HTTPException(status_code=400, detail="Escalation already handled")
    if not (body.owner_remarks or "").strip():
        raise HTTPException(status_code=400, detail="Owner remarks are mandatory")
    await db.lead_escalations.update_one({"id": esc_id}, {"$set": {
        "status": "RETURNED", "owner_remarks": body.owner_remarks.strip(), "returned_at": now_iso()}})
    await db.leads.update_one({"id": esc["lead_id"]}, {"$set": {
        "status": "PENDING", "action_required": True, "current_team": "LEAD",
        "return_reason": "OWNER_RETURNED", "updated_at": now_iso()}})
    await log_activity(user, "Escalation Returned", "LEAD", esc["lead_id"], esc.get("lead_name", ""), "Owner remarks added")
    return await db.lead_escalations.find_one({"id": esc_id}, NO_ID)


# ========================= ECP =========================
async def first_payment_confirmed(ecp_id: str) -> bool:
    p = await db.payments.find_one({"ecp_id": ecp_id, "type": "FIRST", "status": "CONFIRMED"})
    return p is not None


async def final_payment_confirmed(ecp_id: str) -> bool:
    p = await db.payments.find_one({"ecp_id": ecp_id, "type": "FINAL", "status": "CONFIRMED"})
    return p is not None


async def enrich_ecp(ecp: dict, sla_map: dict = None):
    if sla_map is None:
        sla_map = await get_sla_map()
    stage = ecp["current_stage"]
    display = wf.STAGE_LABELS.get(stage, stage)
    derived = None
    if ecp["status"] == "CLOSED":
        display = "Closed / Cancelled"
    elif ecp["status"] == "COMPLETED":
        display = "Successfully Completed"
    elif stage == "DISPATCH":
        if not ecp.get("dispatch_started"):
            fp = await first_payment_confirmed(ecp["id"])
            derived = "READY_FOR_DISPATCH" if fp else "PAYMENT_BLOCKED"
        else:
            derived = "DISPATCH_IN_PROCESS"
    elif stage == "INSTALLATION":
        derived = ecp.get("install_status") or "READY_TO_INSTALL"
    elif stage == "PENDING_DOCUMENTS":
        derived = "PENDING_DOCUMENTS"
        ecp["documents_status"] = await _documents_status(ecp["lead_id"], bool(ecp.get("financing_required")))
    # delayed
    delayed = False
    days_in_stage = None
    if ecp["status"] == "ACTIVE" and ecp.get("stage_entry_date"):
        sla_days = sla_map.get(stage, 0)
        entry = datetime.fromisoformat(ecp["stage_entry_date"])
        days_in_stage = (datetime.now(timezone.utc) - entry).days
        if sla_days and sla_days > 0:
            due = entry + timedelta(days=sla_days)
            if datetime.now(timezone.utc) > due:
                delayed = True
    ecp["stage_label"] = wf.STAGE_LABELS.get(stage, stage)
    ecp["display_status"] = display
    ecp["derived_status"] = derived
    ecp["delayed"] = delayed
    ecp["days_in_stage"] = days_in_stage
    ecp["first_payment_confirmed"] = await first_payment_confirmed(ecp["id"])
    ecp["final_payment_confirmed"] = await final_payment_confirmed(ecp["id"])
    return ecp


ALLOWED_STAGES = {
    "REGISTRATION": ["REGISTRATION_1", "REGISTRATION_2", "NET_METERING"],
    "DISPATCH": ["DISPATCH"],
    "INSTALLATION": ["INSTALLATION", "NET_METERING"],
    "INSTALLATION_MANAGER": ["INSTALLATION", "NET_METERING"],
    "INSTALLATION_MEMBER": ["INSTALLATION", "NET_METERING"],
}


def _scrub_dispatch(e: dict):
    """Dispatch must never receive financial data (enforced server-side)."""
    for k in ("project_price",):
        e.pop(k, None)
    return e


def ecp_filter_for_role(user: dict):
    role = user["role"]
    if role in ("OWNER", "MANAGER", "ACCOUNTS"):
        return {}
    if role == "LEAD":
        return {"lead_owner_id": {"$in": [user["id"], None]}}
    if role == "REGISTRATION":
        return {"current_stage": {"$in": ALLOWED_STAGES["REGISTRATION"]}}
    if role == "DISPATCH":
        return {"current_stage": "DISPATCH"}
    if role == "INSTALLATION_MANAGER":
        return {"current_stage": {"$in": ["INSTALLATION", "NET_METERING"]}}
    if role in ("INSTALLATION", "INSTALLATION_MEMBER"):
        return {"current_stage": {"$in": ["INSTALLATION", "NET_METERING"]}, "responsible_user": user["id"]}
    return {"id": "__none__"}


def _matches_view(e: dict, view: str) -> bool:
    if view in ("PAYMENT_BLOCKED", "READY_FOR_DISPATCH", "DISPATCH_IN_PROCESS",
                "READY_TO_INSTALL", "IN_PROCESS", "AWAITING_ASSIGNMENT"):
        return e.get("derived_status") == view and e["status"] == "ACTIVE"
    if view == "PAST_DISPATCH":
        return (e["current_stage"] in ("INSTALLATION", "NET_METERING", "REGISTRATION_2", "ACCOUNTS_2")
                or e["status"] in ("COMPLETED", "CLOSED"))
    if view == "DELAYED":
        return bool(e.get("delayed"))
    if view == "CLOSED":
        return e["status"] == "CLOSED"
    if view == "COMPLETED":
        return e["status"] == "COMPLETED"
    return True


@api.get("/ecps")
async def list_ecps(stage: Optional[str] = None, view: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = ecp_filter_for_role(user)
    if stage:
        allowed = ALLOWED_STAGES.get(user["role"])
        if allowed is None or stage in allowed:
            q = {**q, "current_stage": stage}
    ecps = await db.ecps.find(q, NO_ID).sort("created_at", -1).to_list(3000)
    sla_map = await get_sla_map()
    for e in ecps:
        await enrich_ecp(e, sla_map)
    if view:
        ecps = [e for e in ecps if _matches_view(e, view)]
    if user["role"] == "DISPATCH":
        ecps = [_scrub_dispatch(e) for e in ecps]
    return ecps


@api.get("/ecps/{ecp_id}")
async def get_ecp(ecp_id: str, user: dict = Depends(get_current_user)):
    scope = ecp_filter_for_role(user)
    if scope.get("id") == "__none__":
        raise HTTPException(status_code=404, detail="ECP not found")
    ecp = await db.ecps.find_one({**scope, "id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    await enrich_ecp(ecp)
    tasks = await db.ecp_tasks.find({"ecp_id": ecp_id}, NO_ID).to_list(500)
    history = await db.ecp_stage_history.find({"ecp_id": ecp_id}, NO_ID).sort("changed_at", 1).to_list(500)
    payments = await db.payments.find({"ecp_id": ecp_id}, NO_ID).sort("date", -1).to_list(500)
    if user["role"] == "DISPATCH":
        _scrub_dispatch(ecp)
        payments = []
    return {"ecp": ecp, "tasks": tasks, "history": history, "payments": payments}


async def _advance_stage(ecp: dict, user: dict, note: str = ""):
    target = wf.next_stage(ecp["current_stage"])
    from_stage = ecp["current_stage"]
    upd = {"updated_at": now_iso()}
    if target == "COMPLETED":
        upd.update({"status": "COMPLETED", "current_stage": "ACCOUNTS_2",
                    "current_team": None, "updated_at": now_iso(),
                    "completed_at": now_iso()})
        to_label = "COMPLETED"
    else:
        upd.update({"current_stage": target, "current_team": wf.STAGE_TEAM[target],
                    "stage_entry_date": now_iso(), "responsible_user": None,
                    "responsible_user_name": None})
        to_label = target
        if target == "DISPATCH":
            upd["dispatch_started"] = False
        if target == "INSTALLATION":
            # Dispatch completed -> route to Installation Manager for member assignment
            upd["install_status"] = "AWAITING_ASSIGNMENT"
            upd["current_team"] = "INSTALLATION_MANAGER"
        # NET_METERING: do NOT carry the Installation-stage assignee. Close Net Metering
        # must first be received by the Installation Manager and explicitly assigned, so
        # responsible_user / responsible_user_name are cleared (handled by the else block above).
        # create tasks for the new stage from specs (financing-aware, team + requires)
        docs = _tasks_from_specs(ecp["id"], target, bool(ecp.get("financing_required")))
        if docs:
            await db.ecp_tasks.insert_many(docs)
    await db.ecps.update_one({"id": ecp["id"]}, {"$set": upd})
    await db.ecp_stage_history.insert_one({
        "id": new_id(), "ecp_id": ecp["id"], "from_stage": from_stage, "to_stage": to_label,
        "changed_by": user["id"], "changed_by_name": user["name"], "changed_at": now_iso(),
        "note": note or "Stage advanced"})
    await log_activity(user, "ECP Stage Advanced", "ECP", ecp["id"], ecp.get("lead_name", ""),
                       f"{wf.STAGE_LABELS.get(from_stage, from_stage)} → {wf.STAGE_LABELS.get(to_label, to_label)}")


async def _maybe_advance(ecp_id: str, user: dict):
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp or ecp["status"] != "ACTIVE":
        return
    stage = ecp["current_stage"]
    tasks = await db.ecp_tasks.find({"ecp_id": ecp_id, "stage": stage, "applicable": True}, NO_ID).to_list(100)

    def all_done():
        return all(t["completed"] for t in tasks) and len(tasks) > 0

    if stage in ("REGISTRATION_1", "ACCOUNTS_1", "NET_METERING", "REGISTRATION_2", "ACCOUNTS_2"):
        if all_done():
            await _advance_stage(ecp, user, note=f"{wf.STAGE_LABELS[stage]} tasks completed")
    elif stage == "DISPATCH":
        if ecp.get("dispatch_started") and all_done():
            await _advance_stage(ecp, user, note="Dispatch completed")


@api.post("/ecps/{ecp_id}/tasks/{task_id}/complete")
async def complete_task(ecp_id: str, task_id: str, user: dict = Depends(get_current_user)):
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    if ecp["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="ECP is not active")
    task = await db.ecp_tasks.find_one({"id": task_id, "ecp_id": ecp_id}, NO_ID)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    team = task.get("team") or wf.STAGE_TEAM.get(task["stage"])
    if user["role"] == "OWNER":
        pass
    elif team == "INSTALLATION_MEMBER":
        if user["role"] not in wf.INSTALL_MEMBER_ROLES or ecp.get("responsible_user") != user["id"]:
            raise HTTPException(status_code=403, detail="This task is assigned to the installation member on this project")
    elif user["role"] != team:
        raise HTTPException(status_code=403, detail="Only the responsible team can complete this task")
    if task["stage"] != ecp["current_stage"]:
        raise HTTPException(status_code=400, detail="Task does not belong to the current stage")
    if not task["applicable"]:
        raise HTTPException(status_code=400, detail="Task is not applicable")
    if task.get("requires"):
        req = await db.ecp_tasks.find_one({"ecp_id": ecp_id, "task_name": task["requires"]}, NO_ID)
        if req and req.get("applicable") and not req.get("completed"):
            raise HTTPException(status_code=400, detail=f"Complete '{task['requires']}' first")
    if task["task_name"] == "Upload Installation Photos to CSPDCL Portal":
        photos = await db.ecp_photos.find({"ecp_id": ecp_id, "approved": True}, NO_ID).to_list(50)
        if len({p["photo_type"] for p in photos}) < len(wf.INSTALL_PHOTO_TYPES):
            raise HTTPException(status_code=400, detail="Manager-approved installation photos are not available yet")
    if task["stage"] == "DISPATCH" and not ecp.get("dispatch_started"):
        raise HTTPException(status_code=400, detail="Start Dispatch before completing dispatch tasks")
    if task["task_name"] == "Delivery Challan" and task["stage"] == "DISPATCH":
        ch = await db.delivery_challans.find_one({"ecp_id": ecp_id}, NO_ID)
        if not ch or ch.get("status") != "FINALIZED" or not ch.get("items"):
            raise HTTPException(status_code=400, detail="Finalize the Delivery Challan before marking the task complete")
    await db.ecp_tasks.update_one({"id": task_id}, {"$set": {
        "completed": True, "completed_by": user["id"], "completed_by_name": user["name"],
        "completed_at": now_iso()}})
    await _maybe_advance(ecp_id, user)
    try:
        return await get_ecp(ecp_id, user)
    except HTTPException:
        # Task completion may auto-advance the ECP into a stage no longer visible to this
        # role (e.g. assigned INSTALLATION_MEMBER completing Close Net Metering -> REGISTRATION_2).
        # The write succeeded; return a lightweight success payload instead of a spurious 404.
        fresh = await db.ecps.find_one({"id": ecp_id}, NO_ID)
        return {"status": "completed", "current_stage": fresh["current_stage"] if fresh else None}


@api.post("/ecps/{ecp_id}/start-dispatch")
async def start_dispatch(ecp_id: str, user: dict = Depends(get_current_user)):
    require(user, "DISPATCH", "OWNER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    if ecp["current_stage"] != "DISPATCH":
        raise HTTPException(status_code=400, detail="ECP is not in Dispatch stage")
    if ecp.get("dispatch_started"):
        raise HTTPException(status_code=400, detail="Dispatch already started")
    if not await first_payment_confirmed(ecp_id):
        raise HTTPException(status_code=400, detail="First Payment must be CONFIRMED before starting dispatch")
    await db.ecps.update_one({"id": ecp_id}, {"$set": {"dispatch_started": True, "updated_at": now_iso()}})
    await db.ecp_stage_history.insert_one({
        "id": new_id(), "ecp_id": ecp_id, "from_stage": "DISPATCH", "to_stage": "DISPATCH",
        "changed_by": user["id"], "changed_by_name": user["name"], "changed_at": now_iso(),
        "note": "Dispatch started (First Payment confirmed)"})
    return await get_ecp(ecp_id, user)


class InstallBody(BaseModel):
    action: str  # start | complete


class AssignInstallation(BaseModel):
    assigned_user: str


@api.post("/ecps/{ecp_id}/assign-installation")
async def assign_installation(ecp_id: str, body: AssignInstallation, user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION_MANAGER", "MANAGER", "OWNER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    stage = ecp["current_stage"]
    if stage == "INSTALLATION":
        if ecp.get("install_status") != "AWAITING_ASSIGNMENT":
            raise HTTPException(status_code=400, detail="ECP is not awaiting installation assignment")
    elif stage == "NET_METERING":
        # Close Net Metering assignment — only after the Request Net Metering prerequisite is done
        req = await db.ecp_tasks.find_one(
            {"ecp_id": ecp_id, "task_name": "Request Net Metering from CSPDCL"}, NO_ID)
        if not req or not req.get("completed"):
            raise HTTPException(status_code=400, detail="Complete 'Request Net Metering from CSPDCL' before assigning Close Net Metering")
    else:
        raise HTTPException(status_code=400, detail="ECP is not awaiting installation assignment")
    emp = await db.users.find_one({"id": body.assigned_user}, NO_ID)
    if not emp or emp["role"] not in wf.INSTALL_MEMBER_ROLES or not emp.get("active", True):
        raise HTTPException(status_code=400, detail="Assignee must be an active Installation team member")
    upd = {"responsible_user": emp["id"], "responsible_user_name": emp["name"],
           "current_team": "INSTALLATION_MEMBER", "updated_at": now_iso()}
    if stage == "INSTALLATION":
        upd["install_status"] = "READY_TO_INSTALL"
        note = f"Installation assigned to {emp['name']}"
    else:
        note = f"Close Net Metering assigned to {emp['name']}"
    await db.ecps.update_one({"id": ecp_id}, {"$set": upd})
    await db.ecp_stage_history.insert_one({
        "id": new_id(), "ecp_id": ecp_id, "from_stage": stage, "to_stage": stage,
        "changed_by": user["id"], "changed_by_name": user["name"], "changed_at": now_iso(),
        "note": note})
    await log_activity(user, "Installation Assigned", "ECP", ecp_id, ecp.get("lead_name", ""), f"To {emp['name']}")
    return await get_ecp(ecp_id, user)


@api.post("/ecps/{ecp_id}/installation")
async def installation_action(ecp_id: str, body: InstallBody, user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION", "INSTALLATION_MEMBER", "OWNER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    if ecp["current_stage"] != "INSTALLATION":
        raise HTTPException(status_code=400, detail="ECP is not in Installation stage")
    if user["role"] in wf.INSTALL_MEMBER_ROLES and ecp.get("responsible_user") != user["id"]:
        raise HTTPException(status_code=403, detail="This installation is not assigned to you")
    if body.action == "start":
        if ecp.get("install_status") != "READY_TO_INSTALL":
            raise HTTPException(status_code=400, detail="Installation is not ready to start")
        await db.ecps.update_one({"id": ecp_id}, {"$set": {"install_status": "IN_PROCESS", "updated_at": now_iso()}})
    elif body.action == "submit":
        if ecp.get("install_status") not in ("IN_PROCESS", "REJECTED"):
            raise HTTPException(status_code=400, detail="Installation must be in process to submit")
        photos = await db.ecp_photos.find({"ecp_id": ecp_id}, NO_ID).to_list(50)
        have = {p["photo_type"] for p in photos}
        missing = [wf.INSTALL_PHOTO_LABELS[t] for t in wf.INSTALL_PHOTO_TYPES if t not in have]
        if missing:
            raise HTTPException(status_code=400, detail="Upload all 5 photos before submitting. Missing: " + ", ".join(missing))
        await db.ecps.update_one({"id": ecp_id}, {"$set": {"install_status": "PENDING_ACCEPTANCE", "updated_at": now_iso()}})
        await log_activity(user, "Installation Submitted for Acceptance", "ECP", ecp_id, ecp.get("lead_name", ""), "")
    else:
        raise HTTPException(status_code=400, detail="Invalid installation action")
    return await get_ecp(ecp_id, user)


class AcceptBody(BaseModel):
    remarks: Optional[str] = None


@api.post("/ecps/{ecp_id}/installation/accept")
async def installation_accept(ecp_id: str, body: AcceptBody, user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION_MANAGER", "MANAGER", "OWNER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp or ecp["current_stage"] != "INSTALLATION":
        raise HTTPException(status_code=400, detail="ECP is not in Installation stage")
    if ecp.get("install_status") != "PENDING_ACCEPTANCE":
        raise HTTPException(status_code=400, detail="Installation is not pending acceptance")
    await db.ecp_photos.update_many({"ecp_id": ecp_id}, {"$set": {"approved": True, "approved_by": user["name"], "approved_at": now_iso()}})
    await db.ecps.update_one({"id": ecp_id}, {"$set": {"install_status": "COMPLETED", "updated_at": now_iso()}})
    fresh = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    await _advance_stage(fresh, user, note="Installation accepted by manager")
    await log_activity(user, "Installation Accepted", "ECP", ecp_id, ecp.get("lead_name", ""), body.remarks or "")
    return await get_ecp(ecp_id, user)


@api.post("/ecps/{ecp_id}/installation/reject")
async def installation_reject(ecp_id: str, body: AcceptBody, user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION_MANAGER", "MANAGER", "OWNER")
    if not (body.remarks or "").strip():
        raise HTTPException(status_code=400, detail="Rejection remarks are mandatory")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp or ecp.get("install_status") != "PENDING_ACCEPTANCE":
        raise HTTPException(status_code=400, detail="Installation is not pending acceptance")
    await db.ecps.update_one({"id": ecp_id}, {"$set": {
        "install_status": "REJECTED", "install_reject_remarks": body.remarks.strip(), "updated_at": now_iso()}})
    await log_activity(user, "Installation Rejected", "ECP", ecp_id, ecp.get("lead_name", ""), body.remarks.strip())
    return await get_ecp(ecp_id, user)


async def _apply_ecp_financing(ecp_id: str, financing: bool, user: dict):
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        return
    await db.ecps.update_one({"id": ecp_id}, {"$set": {"financing_required": financing, "updated_at": now_iso()}})
    if ecp.get("current_stage") == "PENDING_DOCUMENTS":
        return  # Registration-1 tasks are created only when documents are released
    for t in wf.REG1_FINANCING_TASKS:
        existing = await db.ecp_tasks.find_one({"ecp_id": ecp_id, "task_name": t})
        if existing:
            await db.ecp_tasks.update_one({"id": existing["id"]}, {"$set": {"applicable": financing}})
        elif financing:
            await db.ecp_tasks.insert_one(_make_task(ecp_id, "REGISTRATION_1", t, True))


@api.post("/ecps/{ecp_id}/financing")
async def ecp_financing(ecp_id: str, body: FinancingBody, user: dict = Depends(get_current_user)):
    require(user, "LEAD", "MANAGER", "OWNER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    if user["role"] == "LEAD" and ecp.get("lead_owner_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="Not permitted for this ECP")
    await _apply_ecp_financing(ecp_id, bool(body.financing_required), user)
    await db.leads.update_one({"id": ecp["lead_id"]}, {"$set": {
        "financing_required": bool(body.financing_required)}})
    return await get_ecp(ecp_id, user)


class CloseBody(BaseModel):
    reason: str
    remarks: Optional[str] = None


@api.post("/ecps/{ecp_id}/close")
async def close_ecp(ecp_id: str, body: CloseBody, user: dict = Depends(get_current_user)):
    require(user, "OWNER", "MANAGER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    if ecp["status"] in ("CLOSED", "COMPLETED"):
        raise HTTPException(status_code=400, detail="ECP is already closed")
    if not body.reason:
        raise HTTPException(status_code=400, detail="Closure reason is required")
    if body.reason == "OTHER" and not (body.remarks or "").strip():
        raise HTTPException(status_code=400, detail="Remarks are mandatory when reason is OTHER")
    await db.ecps.update_one({"id": ecp_id}, {"$set": {
        "status": "CLOSED", "current_team": None, "closed_at": now_iso(),
        "closed_by": user["id"], "closed_by_name": user["name"],
        "closure_reason": body.reason, "closure_remarks": (body.remarks or "").strip(),
        "updated_at": now_iso()}})
    await db.ecp_stage_history.insert_one({
        "id": new_id(), "ecp_id": ecp_id, "from_stage": ecp["current_stage"], "to_stage": "CLOSED",
        "changed_by": user["id"], "changed_by_name": user["name"], "changed_at": now_iso(),
        "note": f"Manually closed/cancelled: {body.reason}"})
    await log_activity(user, "ECP Closed", "ECP", ecp_id, ecp.get("lead_name", ""), body.reason)
    return await get_ecp(ecp_id, user)


# ========================= PAYMENTS =========================
class PaymentCreate(BaseModel):
    ecp_id: str
    type: str  # FIRST | ADDITIONAL | FINAL
    amount: float
    date: str
    status: str  # PENDING | CONFIRMED
    remarks: Optional[str] = ""


class PaymentUpdate(BaseModel):
    amount: Optional[float] = None
    date: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None


@api.post("/payments")
async def create_payment(body: PaymentCreate, user: dict = Depends(get_current_user)):
    require(user, "ACCOUNTS")
    ecp = await db.ecps.find_one({"id": body.ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    if body.type not in ("FIRST", "ADDITIONAL"):
        raise HTTPException(status_code=400, detail="Invalid payment type")
    if body.status not in ("PENDING", "CONFIRMED"):
        raise HTTPException(status_code=400, detail="Invalid payment status")
    if body.type == "FIRST":
        exists = await db.payments.find_one({"ecp_id": body.ecp_id, "type": body.type})
        if exists:
            raise HTTPException(status_code=400, detail=f"{body.type} payment already exists for this ECP")
    if (body.date or "")[:10] > ist_today_str():
        raise HTTPException(status_code=400, detail="Payment date cannot be in the future")
    # Project-value ceiling: existing (PENDING + CONFIRMED) + new must not exceed project_price
    price = float(ecp.get("project_price") or 0)
    existing = await db.payments.find({"ecp_id": body.ecp_id}, NO_ID).to_list(1000)
    existing_sum = sum(float(p.get("amount") or 0) for p in existing)
    if existing_sum + float(body.amount) > price:
        raise HTTPException(status_code=400, detail=f"Total payments (₹{existing_sum + float(body.amount):,.0f}) would exceed the project price (₹{price:,.0f})")
    doc = {
        "id": new_id(), "ecp_id": body.ecp_id, "type": body.type, "amount": float(body.amount),
        "date": body.date, "status": body.status, "remarks": (body.remarks or "").strip(),
        "updated_by": user["id"], "updated_by_name": user["name"], "updated_at": now_iso(),
        "created_at": now_iso()}
    await db.payments.insert_one(doc)
    await log_activity(user, "Payment Created", "ECP", body.ecp_id, ecp.get("lead_name", ""),
                       f"{body.type} {body.status} ₹{body.amount}")
    d = dict(doc)
    d.pop("_id", None)
    return d


@api.patch("/payments/{payment_id}")
async def update_payment(payment_id: str, body: PaymentUpdate, user: dict = Depends(get_current_user)):
    require(user, "ACCOUNTS")
    pay = await db.payments.find_one({"id": payment_id}, NO_ID)
    if not pay:
        raise HTTPException(status_code=404, detail="Payment not found")
    upd = {"updated_by": user["id"], "updated_by_name": user["name"], "updated_at": now_iso()}
    if body.amount is not None:
        ecp = await db.ecps.find_one({"id": pay["ecp_id"]}, NO_ID)
        price = float((ecp or {}).get("project_price") or 0)
        others = await db.payments.find({"ecp_id": pay["ecp_id"], "id": {"$ne": payment_id}}, NO_ID).to_list(1000)
        others_sum = sum(float(p.get("amount") or 0) for p in others)
        if others_sum + float(body.amount) > price:
            raise HTTPException(status_code=400, detail=f"Total payments (₹{others_sum + float(body.amount):,.0f}) would exceed the project price (₹{price:,.0f})")
        upd["amount"] = float(body.amount)
    if body.date is not None:
        if (body.date or "")[:10] > ist_today_str():
            raise HTTPException(status_code=400, detail="Payment date cannot be in the future")
        upd["date"] = body.date
    if body.status is not None:
        if body.status not in ("PENDING", "CONFIRMED"):
            raise HTTPException(status_code=400, detail="Invalid status")
        upd["status"] = body.status
    if body.remarks is not None:
        upd["remarks"] = body.remarks.strip()
    await db.payments.update_one({"id": payment_id}, {"$set": upd})
    ecp = await db.ecps.find_one({"id": pay["ecp_id"]}, NO_ID)
    await log_activity(user, "Payment Updated", "ECP", pay["ecp_id"], (ecp or {}).get("lead_name", ""),
                       f"{pay['type']} → {upd.get('status', pay['status'])}")
    return await db.payments.find_one({"id": payment_id}, NO_ID)


def _ecp_receivable(ecp: dict, ecp_payments: list):
    price = float(ecp.get("project_price") or 0)
    first_conf = sum(p["amount"] for p in ecp_payments if p["type"] == "FIRST" and p["status"] == "CONFIRMED")
    sub_conf = sum(p["amount"] for p in ecp_payments if p["type"] == "ADDITIONAL" and p["status"] == "CONFIRMED")
    final_conf = sum(p["amount"] for p in ecp_payments if p["type"] == "FINAL" and p["status"] == "CONFIRMED")
    total_conf = first_conf + sub_conf + final_conf
    receivable = max(price - total_conf, 0)
    first_confirmed = any(p["type"] == "FIRST" and p["status"] == "CONFIRMED" for p in ecp_payments)
    return {
        "project_price": price, "first_confirmed_amount": first_conf,
        "subsequent_confirmed_amount": sub_conf + final_conf, "final_confirmed_amount": final_conf,
        "total_received": total_conf, "total_receivable": receivable,
        "first_payment_confirmed": first_confirmed,
    }


@api.get("/payments/monitor")
async def payment_monitor(user: dict = Depends(get_current_user)):
    require(user, "ACCOUNTS", "OWNER", "MANAGER")
    ecps = await db.ecps.find({}, NO_ID).sort("created_at", -1).to_list(3000)
    payments = await db.payments.find({}, NO_ID).to_list(5000)
    by_ecp = {}
    for p in payments:
        by_ecp.setdefault(p["ecp_id"], []).append(p)
    rows = []
    for e in ecps:
        ps = by_ecp.get(e["id"], [])
        calc = _ecp_receivable(e, ps)
        rows.append({
            "ecp_id": e["id"], "lead_name": e["lead_name"], "customer_phone": e.get("customer_phone", ""),
            "lead_creator_name": e.get("lead_creator_name"),
            "stage": e["current_stage"],
            "stage_label": wf.STAGE_LABELS.get(e["current_stage"], e["current_stage"]),
            "status": e["status"], "payments": ps, **calc})
    return rows


# ========================= DASHBOARD =========================
@api.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    role = user["role"]
    sla_map = await get_sla_map()
    leads = await db.leads.find({}, NO_ID).to_list(5000)
    ecps = await db.ecps.find({}, NO_ID).to_list(5000)
    if role == "LEAD":
        _own = (user["id"], None)
        leads = [l for l in leads if l.get("lead_owner_id") in _own]
        ecps = [e for e in ecps if e.get("lead_owner_id") in _own]
    for e in ecps:
        await enrich_ecp(e, sla_map)
    payments = await db.payments.find({}, NO_ID).to_list(5000)

    def lead_count(status):
        return len([l for l in leads if l["status"] == status])

    def ecp_stage_count(stage):
        return len([e for e in ecps if e["current_stage"] == stage and e["status"] == "ACTIVE"])

    def derived_count(d):
        return len([e for e in ecps if e.get("derived_status") == d and e["status"] == "ACTIVE"])

    active_ecps = [e for e in ecps if e["status"] == "ACTIVE"]
    delayed = [e for e in active_ecps if e.get("delayed")]

    def pay_count(ptype, status):
        return len([p for p in payments if p["type"] == ptype and p["status"] == status])

    today = datetime.now(timezone.utc).date().isoformat()

    async def followups_today():
        fus = await db.lead_followups.find({}, NO_ID).to_list(5000)
        # only count for currently-in-followup leads (IST business date)
        ist_today = ist_today_str()
        fu_lead_ids = {l["id"] for l in leads if l["status"] == "FOLLOW_UP"}
        return len([f for f in fus if f["lead_id"] in fu_lead_ids and (f.get("followup_date") or "")[:10] == ist_today])

    site_visits = await db.lead_site_visits.find({}, NO_ID).to_list(5000)
    if role == "LEAD":
        _lead_ids = {l["id"] for l in leads}
        site_visits = [s for s in site_visits if s.get("lead_id") in _lead_ids]

    data = {"role": role, "role_label": wf.ROLE_LABELS.get(role, role)}

    if role == "OWNER":
        data["leads"] = {
            "PENDING": lead_count("PENDING"), "FOLLOW_UP": lead_count("FOLLOW_UP"),
            "SITE_VISIT": lead_count("SITE_VISIT"), "ESCALATED": lead_count("ESCALATED"),
            "QUALIFIED": lead_count("QUALIFIED"), "LOST": lead_count("LOST")}
        data["ecp"] = {
            "ACTIVE": len(active_ecps),
            "REGISTRATION_1": ecp_stage_count("REGISTRATION_1"),
            "ACCOUNTS_1": ecp_stage_count("ACCOUNTS_1"),
            "PAYMENT_BLOCKED": derived_count("PAYMENT_BLOCKED"),
            "READY_FOR_DISPATCH": derived_count("READY_FOR_DISPATCH"),
            "DISPATCH_IN_PROCESS": derived_count("DISPATCH_IN_PROCESS"),
            "READY_TO_INSTALL": derived_count("READY_TO_INSTALL"),
            "INSTALLATION_IN_PROCESS": derived_count("IN_PROCESS"),
            "NET_METERING": ecp_stage_count("NET_METERING"),
            "REGISTRATION_2": ecp_stage_count("REGISTRATION_2"),
            "ACCOUNTS_2": ecp_stage_count("ACCOUNTS_2"),
            "DELAYED": len(delayed),
            "COMPLETED": len([e for e in ecps if e["status"] == "COMPLETED"]),
            "CLOSED": len([e for e in ecps if e["status"] == "CLOSED"]),
            "PENDING_DOCUMENTS": ecp_stage_count("PENDING_DOCUMENTS")}
        data["payments"] = {
            "FIRST_PENDING": pay_count("FIRST", "PENDING"), "FIRST_CONFIRMED": pay_count("FIRST", "CONFIRMED"),
            "FINAL_PENDING": pay_count("FINAL", "PENDING"), "FINAL_CONFIRMED": pay_count("FINAL", "CONFIRMED"),
            "ADDITIONAL": len([p for p in payments if p["type"] == "ADDITIONAL"])}
        data["pending_commercial"] = len([l for l in leads if (l.get("pending_commercial_change") or {}).get("status") == "PENDING"])

    elif role == "MANAGER":
        data["site_visits_to_assign"] = len([s for s in site_visits if s["status"] == "REQUESTED"])
        data["site_visits_today"] = len([s for s in site_visits if s["status"] == "ASSIGNED" and (s.get("visit_date") or "")[:10] == today])
        data["site_visits_upcoming"] = len([s for s in site_visits if s["status"] == "ASSIGNED" and (s.get("visit_date") or "")[:10] > today])
        data["awaiting_install_assignment"] = len([e for e in active_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") == "AWAITING_ASSIGNMENT"])
        data["delayed"] = len(delayed)
        data["active_leads"] = len([l for l in leads if l["status"] in ("PENDING", "FOLLOW_UP", "SITE_VISIT", "ESCALATED")])
        data["active_ecps"] = len(active_ecps)

    elif role == "LEAD":
        data["action_required"] = len([l for l in leads if l.get("action_required")])
        data["followups_today"] = await followups_today()
        data["waiting_site_visit"] = lead_count("SITE_VISIT")
        data["escalated"] = lead_count("ESCALATED")
        data["qualified"] = lead_count("QUALIFIED")
        data["lost"] = lead_count("LOST")
        data["pending_documents"] = len([e for e in active_ecps if e["current_stage"] == "PENDING_DOCUMENTS" and e.get("lead_owner_id") in (user["id"], None)])

    elif role == "ACCOUNTS":
        by_ecp = {}
        for p in payments:
            by_ecp.setdefault(p["ecp_id"], []).append(p)
        first_pending_count = 0
        subsequent_followup_count = 0
        subsequent_amount_pending = 0.0
        total_receivable = 0.0
        for e in active_ecps:
            calc = _ecp_receivable(e, by_ecp.get(e["id"], []))
            total_receivable += calc["total_receivable"]
            if not calc["first_payment_confirmed"]:
                first_pending_count += 1
            elif calc["total_receivable"] > 0:
                subsequent_followup_count += 1
                subsequent_amount_pending += calc["total_receivable"]
        data["first_payment_pending_count"] = first_pending_count
        data["subsequent_followup_count"] = subsequent_followup_count
        data["subsequent_amount_pending"] = subsequent_amount_pending
        data["total_receivable"] = total_receivable

    elif role == "DISPATCH":
        data["payment_blocked"] = derived_count("PAYMENT_BLOCKED")
        data["ready_for_dispatch"] = derived_count("READY_FOR_DISPATCH")
        data["dispatch_in_process"] = derived_count("DISPATCH_IN_PROCESS")
        past_dispatch = ["INSTALLATION", "NET_METERING", "REGISTRATION_2", "ACCOUNTS_2"]
        data["completed"] = len([e for e in ecps if e["current_stage"] in past_dispatch or e["status"] in ("COMPLETED", "CLOSED")])

    elif role == "INSTALLATION":
        mine = [s for s in site_visits if s["assigned_user"] == user["id"]]
        data["sv_upcoming"] = len([s for s in mine if s["status"] == "ASSIGNED" and (s.get("visit_date") or "")[:10] > today])
        data["sv_today"] = len([s for s in mine if s["status"] == "ASSIGNED" and (s.get("visit_date") or "")[:10] == today])
        data["sv_assigned"] = len([s for s in mine if s["status"] == "ASSIGNED"])
        data["sv_completed"] = len([s for s in mine if s["status"] == "DONE"])
        my_ecps = [e for e in active_ecps if e.get("responsible_user") == user["id"]]
        data["ready_to_install"] = len([e for e in my_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") == "READY_TO_INSTALL"])
        data["installation_in_process"] = len([e for e in my_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") == "IN_PROCESS"])
        data["net_metering"] = len([e for e in my_ecps if e["current_stage"] == "NET_METERING"])

    elif role == "REGISTRATION":
        data["registration_1"] = ecp_stage_count("REGISTRATION_1")
        data["registration_2"] = ecp_stage_count("REGISTRATION_2")
        data["pending"] = ecp_stage_count("REGISTRATION_1") + ecp_stage_count("REGISTRATION_2")
        data["pending_documents"] = ecp_stage_count("PENDING_DOCUMENTS")

    elif role == "INSTALLATION_MANAGER":
        data["awaiting_assignment"] = len([e for e in active_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") == "AWAITING_ASSIGNMENT"])
        data["install_in_process"] = len([e for e in active_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") in ("IN_PROCESS", "REJECTED", "READY_TO_INSTALL")])
        data["pending_acceptance"] = len([e for e in active_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") == "PENDING_ACCEPTANCE"])
        data["sv_awaiting"] = len([s for s in site_visits if s["status"] == "REQUESTED"])
        data["sv_in_process"] = len([s for s in site_visits if s["status"] == "ASSIGNED"])
        data["net_metering"] = ecp_stage_count("NET_METERING")

    elif role == "INSTALLATION_MEMBER":
        mine = [s for s in site_visits if s["assigned_user"] == user["id"]]
        data["sv_assigned"] = len([s for s in mine if s["status"] == "ASSIGNED"])
        data["sv_today"] = len([s for s in mine if s["status"] == "ASSIGNED" and (s.get("visit_date") or "")[:10] == today])
        data["sv_completed"] = len([s for s in mine if s["status"] == "DONE"])
        my_ecps = [e for e in active_ecps if e.get("responsible_user") == user["id"]]
        data["ready_to_install"] = len([e for e in my_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") == "READY_TO_INSTALL"])
        data["install_in_process"] = len([e for e in my_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") in ("IN_PROCESS", "REJECTED")])
        data["pending_acceptance"] = len([e for e in my_ecps if e["current_stage"] == "INSTALLATION" and e.get("install_status") == "PENDING_ACCEPTANCE"])

    elif role == "COMPLAINT":
        comps = await db.complaints.find({}, NO_ID).to_list(3000)
        open_c = [c for c in comps if c["status"] not in ("RESOLVED", "CLOSED")]
        data["registered"] = len([c for c in comps if c["status"] == "REGISTERED"])
        data["assigned"] = len([c for c in comps if c["status"] == "ASSIGNED"])
        data["in_progress"] = len([c for c in comps if c["status"] == "IN_PROGRESS"])
        data["critical"] = len([c for c in open_c if c["priority"] == "CRITICAL"])
        data["overdue"] = len([c for c in comps if _complaint_overdue(c)[0]])
        data["due_today"] = len([c for c in open_c if c.get("sla_due_date") == today])

    return data


@api.get("/meta")
async def meta(user: dict = Depends(get_current_user)):
    return {
        "roles": wf.ROLES, "role_labels": wf.ROLE_LABELS,
        "stage_order": wf.STAGE_ORDER, "stage_labels": wf.STAGE_LABELS,
        "lost_reasons": wf.LOST_REASONS, "closure_reasons": wf.CLOSURE_REASONS,
        "install_photo_types": wf.INSTALL_PHOTO_TYPES, "install_photo_labels": wf.INSTALL_PHOTO_LABELS,
        "complaint_priorities": wf.COMPLAINT_PRIORITIES, "complaint_statuses": wf.COMPLAINT_STATUSES,
        "complaint_teams": wf.COMPLAINT_TEAMS,
    }


# ========================= ACTIVITIES (lightweight work-done log) =========================
async def log_activity(user, activity, ref_type, ref_id, customer_name="", details=""):
    try:
        await db.activities.insert_one({
            "id": new_id(), "ts": now_iso(), "user_id": user.get("id"),
            "user_name": user.get("name"), "team": user.get("role"),
            "customer_name": customer_name, "ref_type": ref_type, "ref_id": ref_id,
            "activity": activity, "details": details})
    except Exception:
        pass


@api.get("/activities")
async def list_activities(date: Optional[str] = None, activity_user: Optional[str] = None,
                          team: Optional[str] = None, activity: Optional[str] = None,
                          user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    d = date or ist_today_str()
    start, end = ist_day_bounds(d)
    q = {"ts": {"$gte": start, "$lt": end}}
    if activity_user:
        q["user_id"] = activity_user
    if team:
        q["team"] = team
    if activity:
        q["activity"] = activity
    return await db.activities.find(q, NO_ID).sort("ts", -1).to_list(5000)


# ========================= LEAD EMPLOYEE MASTER =========================
class LeadEmpCreate(BaseModel):
    name: str


class LeadEmpUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None


@api.get("/lead-employees")
async def list_lead_employees(active_only: Optional[bool] = False, user: dict = Depends(get_current_user)):
    require(user, "OWNER", "MANAGER", "LEAD", "ACCOUNTS")
    q = {"active": True} if active_only else {}
    return await db.lead_employees.find(q, NO_ID).sort("name", 1).to_list(1000)


@api.post("/lead-employees")
async def create_lead_employee(body: LeadEmpCreate, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    doc = {"id": new_id(), "name": body.name.strip(), "active": True, "created_at": now_iso()}
    await db.lead_employees.insert_one(doc)
    d = dict(doc); d.pop("_id", None)
    return d


@api.patch("/lead-employees/{emp_id}")
async def update_lead_employee(emp_id: str, body: LeadEmpUpdate, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    emp = await db.lead_employees.find_one({"id": emp_id}, NO_ID)
    if not emp:
        raise HTTPException(status_code=404, detail="Lead employee not found")
    upd = {}
    if body.name is not None:
        upd["name"] = body.name.strip()
    if body.active is not None:
        upd["active"] = body.active
    if upd:
        await db.lead_employees.update_one({"id": emp_id}, {"$set": upd})
    return await db.lead_employees.find_one({"id": emp_id}, NO_ID)


# ========================= CSV EXPORT (Owner only) =========================
@api.get("/export/projects")
async def export_projects(include_money: bool = False, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    ecps = await db.ecps.find({}, NO_ID).sort("created_at", -1).to_list(5000)
    payments = await db.payments.find({}, NO_ID).to_list(10000)
    by_ecp = {}
    for p in payments:
        by_ecp.setdefault(p["ecp_id"], []).append(p)
    base_headers = ["Customer", "Phone", "Lead ID", "ECP ID", "Current Stage", "Current Team",
                    "Responsible Employee", "Lead Creator", "Status", "Created At"]
    money_headers = ["Project Price", "First Received", "Subsequent Received", "Total Received", "Total Receivable"]
    headers = base_headers + (money_headers if include_money else [])
    rows = []
    for e in ecps:
        row = [e.get("lead_name", ""), e.get("customer_phone", ""), e.get("lead_id", ""), e["id"],
               wf.STAGE_LABELS.get(e["current_stage"], e["current_stage"]), e.get("current_team") or "",
               e.get("responsible_user_name") or "", e.get("lead_creator_name") or "",
               e.get("status", ""), (e.get("created_at") or "")[:10]]
        if include_money:
            calc = _ecp_receivable(e, by_ecp.get(e["id"], []))
            row += [calc["project_price"], calc["first_confirmed_amount"], calc["subsequent_confirmed_amount"],
                    calc["total_received"], calc["total_receivable"]]
        rows.append(row)
    csv_data = to_csv(headers, rows)
    return Response(content=csv_data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=projects.csv"})


WORKFLOW_MANDATORY = {"name", "phone"}


async def enforce_lead_mandatory(body, item_name):
    cfg = await db.lead_field_config.find_one({"id": "singleton"}, NO_ID) or {}
    fields = cfg.get("fields", {})
    vals = {"email": body.email, "address": body.address, "location_link": body.location_link,
            "quantity": body.quantity, "project_price": body.project_price, "item": item_name}
    for fld, required in fields.items():
        if not required:
            continue
        v = vals.get(fld)
        if v in (None, "", 0):
            raise HTTPException(status_code=400, detail=f"Field '{fld}' is required")


# ---- Item Master ----
class ItemBody(BaseModel):
    name: str
    unit: str


async def _referenced_item_ids():
    ref = set()
    leads = await db.leads.find({}, {"item_id": 1, "pending_commercial_change": 1, "_id": 0}).to_list(20000)
    for l in leads:
        if l.get("item_id"):
            ref.add(l["item_id"])
        pcc = l.get("pending_commercial_change") or {}
        for side in ("proposed", "current"):
            iid = (pcc.get(side) or {}).get("item_id")
            if iid:
                ref.add(iid)
    return ref


@api.get("/items")
async def list_items(active_only: bool = False, user: dict = Depends(get_current_user)):
    q = {"active": True} if active_only else {}
    items = await db.items.find(q, NO_ID).sort("name", 1).to_list(2000)
    ref = await _referenced_item_ids()
    for it in items:
        it["referenced"] = it["id"] in ref
        it["deletable"] = it["id"] not in ref
    return items


@api.post("/items")
async def create_item(body: ItemBody, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    name, unit = body.name.strip(), body.unit.strip()
    if not name or not unit:
        raise HTTPException(status_code=400, detail="Name and unit are required")
    if await db.items.find_one({"name": name, "unit": unit}):
        raise HTTPException(status_code=409, detail="Item with this Name + Unit already exists")
    doc = {"id": new_id(), "name": name, "unit": unit, "active": True, "created_at": now_iso()}
    await db.items.insert_one(doc)
    d = dict(doc); d.pop("_id", None)
    return d


@api.patch("/items/{item_id}")
async def update_item(item_id: str, body: dict, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    it = await db.items.find_one({"id": item_id}, NO_ID)
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    upd = {}
    if "name" in body or "unit" in body:
        nm = (body.get("name") or it["name"]).strip(); un = (body.get("unit") or it["unit"]).strip()
        other = await db.items.find_one({"name": nm, "unit": un, "id": {"$ne": item_id}})
        if other:
            raise HTTPException(status_code=409, detail="Another item with this Name + Unit exists")
        upd["name"] = nm; upd["unit"] = un
    if "active" in body:
        upd["active"] = bool(body["active"])
    await db.items.update_one({"id": item_id}, {"$set": upd})
    return await db.items.find_one({"id": item_id}, NO_ID)


@api.delete("/items/{item_id}")
async def delete_item(item_id: str, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    it = await db.items.find_one({"id": item_id}, NO_ID)
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    ref = await _referenced_item_ids()
    if item_id in ref:
        raise HTTPException(status_code=409, detail="This item is already used in existing records and cannot be deleted. You can deactivate it instead.")
    await db.items.delete_one({"id": item_id})
    return {"deleted": True}


@api.get("/items/export")
async def export_items(user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    items = await db.items.find({}, NO_ID).sort("name", 1).to_list(5000)
    rows = [[i["name"], i["unit"], "active" if i.get("active", True) else "inactive"] for i in items]
    return Response(content=to_csv(["Item Name", "Unit", "Status"], rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=items.csv"})


class ItemCSVBody(BaseModel):
    rows: list  # list of {name, unit}


@api.post("/items/import")
async def import_items(body: ItemCSVBody, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    created, errors = 0, []
    seen = set()
    for idx, r in enumerate(body.rows, 1):
        name = (r.get("name") or "").strip(); unit = (r.get("unit") or "").strip()
        if not name or not unit:
            errors.append(f"Row {idx}: missing name/unit"); continue
        key = (name.lower(), unit.lower())
        if key in seen:
            errors.append(f"Row {idx}: duplicate in file ({name}+{unit})"); continue
        seen.add(key)
        if await db.items.find_one({"name": name, "unit": unit}):
            errors.append(f"Row {idx}: already exists ({name}+{unit})"); continue
        await db.items.insert_one({"id": new_id(), "name": name, "unit": unit, "active": True, "created_at": now_iso()})
        created += 1
    return {"created": created, "errors": errors}


# ---- Lead mandatory-field config ----
@api.get("/lead-field-config")
async def get_field_config(user: dict = Depends(get_current_user)):
    require(user, "OWNER", "LEAD", "MANAGER")
    cfg = await db.lead_field_config.find_one({"id": "singleton"}, NO_ID)
    return cfg or {"id": "singleton", "fields": {}}


@api.put("/lead-field-config")
async def set_field_config(body: dict, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    fields = {k: bool(v) for k, v in (body.get("fields") or {}).items()}
    await db.lead_field_config.update_one({"id": "singleton"}, {"$set": {"id": "singleton", "fields": fields}}, upsert=True)
    return {"id": "singleton", "fields": fields}


# ---- Lead edit after handoff (non-commercial) ----
class LeadEditBody(BaseModel):
    email: Optional[str] = None
    address: Optional[str] = None
    location_link: Optional[str] = None
    remarks: Optional[str] = None


@api.patch("/leads/{lead_id}")
async def edit_lead(lead_id: str, body: LeadEditBody, user: dict = Depends(get_current_user)):
    require(user, "LEAD", "MANAGER", "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if user["role"] == "LEAD" and lead.get("lead_owner_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="This lead is not assigned to you")
    upd = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.dict().items() if v is not None}
    if upd:
        upd["updated_at"] = now_iso()
        await db.leads.update_one({"id": lead_id}, {"$set": upd})
        # Mirror non-commercial contact fields to the linked ECP so subsequent teams see the latest values
        if lead.get("ecp_id"):
            ecp_map = {"email": "customer_email", "address": "customer_address", "location_link": "location_link"}
            ecp_upd = {ecp_map[k]: upd[k] for k in ecp_map if k in upd}
            if ecp_upd:
                ecp_upd["updated_at"] = now_iso()
                await db.ecps.update_one({"id": lead["ecp_id"]}, {"$set": ecp_upd})
        await log_activity(user, "Lead Edited", "LEAD", lead_id, lead["name"], ", ".join(upd.keys()))
    return await _lead_bundle(lead_id)


# ---- Commercial change approval ----
class CommercialChange(BaseModel):
    item_id: Optional[str] = None
    quantity: Optional[float] = None
    project_price: Optional[float] = None


@api.post("/leads/{lead_id}/commercial-change")
async def propose_commercial(lead_id: str, body: CommercialChange, user: dict = Depends(get_current_user)):
    require(user, "LEAD")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("lead_owner_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="This lead is not assigned to you")
    proposed = {}
    if body.item_id is not None:
        it = await db.items.find_one({"id": body.item_id}, NO_ID)
        if not it or not it.get("active", True):
            raise HTTPException(status_code=400, detail="Invalid or inactive item")
        proposed["item_id"] = body.item_id; proposed["item_name"] = it["name"]; proposed["item_unit"] = it["unit"]
    if body.quantity is not None:
        proposed["quantity"] = body.quantity
    if body.project_price is not None:
        proposed["project_price"] = body.project_price
    if not proposed:
        raise HTTPException(status_code=400, detail="No commercial change proposed")
    pcc = {"proposed": proposed,
           "current": {"item_id": lead.get("item_id"), "item_name": lead.get("item_name"),
                       "item_unit": lead.get("item_unit"), "quantity": lead.get("quantity"),
                       "project_price": lead.get("project_price")},
           "requested_by": user["id"], "requested_by_name": user["name"], "requested_at": now_iso(),
           "status": "PENDING"}
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_commercial_change": pcc, "updated_at": now_iso()}})
    await log_activity(user, "Commercial Change Requested", "LEAD", lead_id, lead["name"], str(proposed))
    return await _lead_bundle(lead_id)


class CommercialDecision(BaseModel):
    remarks: Optional[str] = None


@api.post("/leads/{lead_id}/commercial-change/approve")
async def approve_commercial(lead_id: str, body: CommercialDecision, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead or not lead.get("pending_commercial_change") or lead["pending_commercial_change"].get("status") != "PENDING":
        raise HTTPException(status_code=400, detail="No pending commercial change")
    pcc = lead["pending_commercial_change"]
    upd = dict(pcc["proposed"]); upd["updated_at"] = now_iso()
    pcc.update({"status": "APPROVED", "decided_by": user["name"], "decided_at": now_iso(), "decision_remarks": (body.remarks or "")})
    upd["pending_commercial_change"] = pcc
    await db.leads.update_one({"id": lead_id}, {"$set": upd})
    if lead.get("ecp_id"):
        p = pcc["proposed"]
        ecp_upd = {k: p[k] for k in ("item_id", "item_name", "item_unit", "quantity", "project_price") if k in p}
        if ecp_upd:
            ecp_upd["updated_at"] = now_iso()
            await db.ecps.update_one({"id": lead["ecp_id"]}, {"$set": ecp_upd})
    await log_activity(user, "Commercial Change Approved", "LEAD", lead_id, lead["name"], str(pcc["proposed"]))
    return await _lead_bundle(lead_id)


@api.post("/leads/{lead_id}/commercial-change/reject")
async def reject_commercial(lead_id: str, body: CommercialDecision, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead or not lead.get("pending_commercial_change") or lead["pending_commercial_change"].get("status") != "PENDING":
        raise HTTPException(status_code=400, detail="No pending commercial change")
    if not (body.remarks or "").strip():
        raise HTTPException(status_code=400, detail="Rejection remarks are mandatory")
    pcc = lead["pending_commercial_change"]
    pcc.update({"status": "REJECTED", "decided_by": user["name"], "decided_at": now_iso(), "decision_remarks": body.remarks.strip()})
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_commercial_change": pcc}})
    await log_activity(user, "Commercial Change Rejected", "LEAD", lead_id, lead["name"], body.remarks.strip())
    return await _lead_bundle(lead_id)


@api.get("/commercial-changes/pending")
async def pending_commercial(user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    leads = await db.leads.find({"pending_commercial_change.status": "PENDING"}, NO_ID).to_list(1000)
    return leads


# ---- Quotation PDF ----
@api.get("/leads/{lead_id}/quotation")
async def quotation_pdf(lead_id: str, user: dict = Depends(get_current_user)):
    require(user, "LEAD", "MANAGER", "OWNER")
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if user["role"] == "LEAD" and lead.get("lead_owner_id") not in (user["id"], None):
        raise HTTPException(status_code=403, detail="This lead is not assigned to you")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 30 * mm
    c.setFont("Helvetica-Bold", 18); c.drawString(20 * mm, y, "Solar Energy Solutions")
    c.setFont("Helvetica", 10); y -= 6 * mm; c.drawString(20 * mm, y, "Internal Quotation")
    y -= 12 * mm; c.setFont("Helvetica-Bold", 12); c.drawString(20 * mm, y, f"Quotation — Lead {lead['id'][:8].upper()}")
    c.setFont("Helvetica", 10)
    lines = [
        f"Date: {ist_today_str()}",
        f"Customer: {lead.get('name','')}",
        f"Mobile: {lead.get('phone','')}",
        f"Address: {lead.get('address','') or '-'}",
        f"Location: {lead.get('location_link','') or '-'}",
        "",
        f"Item: {lead.get('item_name','-') or '-'}",
        f"Quantity: {lead.get('quantity','-')} {lead.get('item_unit','') or ''}",
        f"Agreed / Project Price: Rs. {lead.get('project_price',0):,.0f}",
    ]
    for ln in lines:
        y -= 8 * mm; c.drawString(20 * mm, y, ln)
    y -= 16 * mm; c.setFont("Helvetica-Oblique", 8)
    c.drawString(20 * mm, y, "This is a system-generated quotation for internal use.")
    c.showPage(); c.save(); buf.seek(0)
    return Response(content=buf.read(), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=quotation_{lead['id'][:8]}.pdf"})


# ========================= PHASE 3: DOCUMENTS =========================
async def _lead_for_doc(lead_id: str, user: dict, mode: str):
    lead = await db.leads.find_one({"id": lead_id}, NO_ID)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    role = user["role"]
    if role == "OWNER":
        return lead
    if role == "LEAD":
        if lead.get("lead_owner_id") not in (user["id"], None):
            raise HTTPException(status_code=403, detail="This lead is not assigned to you")
        return lead
    if mode == "read":
        if role == "MANAGER":
            return lead
        if role == "REGISTRATION":
            ecp = await db.ecps.find_one({"id": lead.get("ecp_id")}, NO_ID) if lead.get("ecp_id") else None
            if ecp and ecp.get("current_stage") != "PENDING_DOCUMENTS":
                return lead
            raise HTTPException(status_code=403, detail="Documents are available only after the lead reaches Registration")
    raise HTTPException(status_code=403, detail="Not authorized to access these documents")


_EXT_BY_CT = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}


@api.post("/leads/{lead_id}/documents")
async def upload_document(lead_id: str, doc_type: str = Form(...), file: UploadFile = File(...),
                          user: dict = Depends(get_current_user)):
    require(user, "LEAD", "OWNER")
    lead = await _lead_for_doc(lead_id, user, "write")
    if doc_type not in wf.DOC_TYPES:
        raise HTTPException(status_code=400, detail="Invalid document type")
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    ct = (file.content_type or "").lower()
    if ct not in wf.DOC_ALLOWED_CONTENT_TYPES and ext not in wf.DOC_ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Only JPG, PNG or PDF files are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > wf.DOC_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    if ext not in wf.DOC_ALLOWED_EXT:
        ext = _EXT_BY_CT.get(ct, "bin")
    path = f"{APP_NAME}/documents/{lead_id}/{new_id()}.{ext}"
    try:
        result = put_object(path, data, ct or "application/octet-stream")
    except Exception as e:
        logger.error(f"storage upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage upload failed")
    await db.lead_documents.update_many(
        {"lead_id": lead_id, "doc_type": doc_type, "status": "CURRENT"},
        {"$set": {"status": "REPLACED", "replaced_at": now_iso()}})
    doc = {"id": new_id(), "lead_id": lead_id, "ecp_id": lead.get("ecp_id"), "doc_type": doc_type,
           "storage_path": result.get("path", path), "original_filename": file.filename or f"{doc_type}.{ext}",
           "content_type": ct or "application/octet-stream", "size": result.get("size", len(data)),
           "uploaded_by": user["id"], "uploaded_by_name": user["name"], "uploaded_at": now_iso(),
           "status": "CURRENT"}
    await db.lead_documents.insert_one(doc)
    await log_activity(user, "Document Uploaded", "LEAD", lead_id, lead.get("name", ""), wf.DOC_LABELS.get(doc_type, doc_type))
    financing = bool(lead.get("financing_required"))
    status = await _documents_status(lead_id, financing)
    released = False
    if status["complete"] and lead.get("ecp_id"):
        ecp = await db.ecps.find_one({"id": lead["ecp_id"]}, NO_ID)
        if ecp and ecp.get("current_stage") == "PENDING_DOCUMENTS":
            await _release_documents_to_reg1(ecp, user)
            released = True
    d = dict(doc); d.pop("_id", None)
    return {"document": d, "documents_status": status, "released": released}


@api.get("/leads/{lead_id}/documents")
async def list_documents(lead_id: str, user: dict = Depends(get_current_user)):
    lead = await _lead_for_doc(lead_id, user, "read")
    current = await db.lead_documents.find({"lead_id": lead_id, "status": "CURRENT"}, NO_ID).sort("uploaded_at", -1).to_list(200)
    history = await db.lead_documents.find({"lead_id": lead_id, "status": "REPLACED"}, NO_ID).sort("uploaded_at", -1).to_list(500)
    ecp_stage = None
    if lead.get("ecp_id"):
        e = await db.ecps.find_one({"id": lead["ecp_id"]}, {"_id": 0, "current_stage": 1})
        ecp_stage = e["current_stage"] if e else None
    return {"documents": current, "history": history,
            "documents_status": await _documents_status(lead_id, bool(lead.get("financing_required"))),
            "ecp_stage": ecp_stage}


@api.get("/leads/{lead_id}/documents/{doc_id}/download")
async def download_document(lead_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    await _lead_for_doc(lead_id, user, "read")
    doc = await db.lead_documents.find_one({"id": doc_id, "lead_id": lead_id}, NO_ID)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        content, ct = get_object(doc["storage_path"])
    except Exception as e:
        logger.error(f"storage download failed: {e}")
        raise HTTPException(status_code=502, detail="File retrieval failed")
    return Response(content=content, media_type=doc.get("content_type") or ct,
                    headers={"Content-Disposition": f'inline; filename="{doc.get("original_filename", "document")}"'})


@api.post("/leads/{lead_id}/documents/release")
async def release_documents(lead_id: str, user: dict = Depends(get_current_user)):
    require(user, "LEAD", "OWNER")
    lead = await _lead_for_doc(lead_id, user, "write")
    if not lead.get("ecp_id"):
        raise HTTPException(status_code=400, detail="Lead has no ECP")
    ecp = await db.ecps.find_one({"id": lead["ecp_id"]}, NO_ID)
    if not ecp or ecp.get("current_stage") != "PENDING_DOCUMENTS":
        raise HTTPException(status_code=400, detail="ECP is not pending documents")
    status = await _documents_status(lead_id, bool(lead.get("financing_required")))
    if not status["complete"]:
        raise HTTPException(status_code=400, detail="Required documents are incomplete")
    await _release_documents_to_reg1(ecp, user)
    await log_activity(user, "Documents Released to Registration", "ECP", ecp["id"], lead.get("name", ""), "")
    return await _lead_bundle(lead_id)


# ========================= PHASE 6: INSTALLATION PHOTOS =========================
_IMG_EXT = {"image/jpeg": "jpg", "image/png": "png"}


@api.post("/ecps/{ecp_id}/install-photos")
async def upload_install_photo(ecp_id: str, photo_type: str = Form(...), file: UploadFile = File(...),
                               user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION", "INSTALLATION_MEMBER", "OWNER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp or ecp["current_stage"] != "INSTALLATION":
        raise HTTPException(status_code=400, detail="ECP is not in Installation stage")
    if user["role"] in wf.INSTALL_MEMBER_ROLES and ecp.get("responsible_user") != user["id"]:
        raise HTTPException(status_code=403, detail="This installation is not assigned to you")
    if photo_type not in wf.INSTALL_PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Invalid photo type")
    ct = (file.content_type or "").lower()
    if ct not in wf.PHOTO_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG or PNG photos are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > wf.DOC_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    path = f"{APP_NAME}/install_photos/{ecp_id}/{new_id()}.{_IMG_EXT.get(ct, 'jpg')}"
    try:
        result = put_object(path, data, ct)
    except Exception as e:
        logger.error(f"storage upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage upload failed")
    await db.ecp_photos.delete_many({"ecp_id": ecp_id, "photo_type": photo_type})
    doc = {"id": new_id(), "ecp_id": ecp_id, "photo_type": photo_type, "storage_path": result.get("path", path),
           "content_type": ct, "approved": False, "uploaded_by": user["id"], "uploaded_by_name": user["name"],
           "uploaded_at": now_iso(), "geo": None}
    await db.ecp_photos.insert_one(doc)
    have = {p["photo_type"] for p in await db.ecp_photos.find({"ecp_id": ecp_id}, NO_ID).to_list(50)}
    return {"uploaded": photo_type, "have": sorted(have),
            "missing": [t for t in wf.INSTALL_PHOTO_TYPES if t not in have]}


@api.get("/ecps/{ecp_id}/install-photos")
async def list_install_photos(ecp_id: str, user: dict = Depends(get_current_user)):
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    # Registration only sees APPROVED photos; installation/manager/owner see all
    if user["role"] == "REGISTRATION":
        photos = await db.ecp_photos.find({"ecp_id": ecp_id, "approved": True}, NO_ID).to_list(50)
    elif user["role"] in (wf.INSTALL_MEMBER_ROLES | {"INSTALLATION_MANAGER", "MANAGER", "OWNER"}):
        photos = await db.ecp_photos.find({"ecp_id": ecp_id}, NO_ID).to_list(50)
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view installation photos")
    return {"photos": photos, "types": wf.INSTALL_PHOTO_TYPES, "labels": wf.INSTALL_PHOTO_LABELS}


@api.get("/ecps/{ecp_id}/install-photos/{photo_id}/download")
async def download_install_photo(ecp_id: str, photo_id: str, user: dict = Depends(get_current_user)):
    p = await db.ecp_photos.find_one({"id": photo_id, "ecp_id": ecp_id}, NO_ID)
    if not p:
        raise HTTPException(status_code=404, detail="Photo not found")
    if user["role"] == "REGISTRATION" and not p.get("approved"):
        raise HTTPException(status_code=403, detail="Photo not yet approved")
    if user["role"] not in (wf.INSTALL_MEMBER_ROLES | {"INSTALLATION_MANAGER", "MANAGER", "OWNER", "REGISTRATION"}):
        raise HTTPException(status_code=403, detail="Not authorized")
    content, ct = get_object(p["storage_path"])
    return Response(content=content, media_type=p.get("content_type") or ct)


# ========================= PHASE 5: DELIVERY CHALLAN =========================
class ChallanItem(BaseModel):
    item_id: Optional[str] = None
    item_name: str
    unit: str
    quantity: float


class ChallanBody(BaseModel):
    items: List[ChallanItem]


@api.get("/ecps/{ecp_id}/challan")
async def get_challan(ecp_id: str, user: dict = Depends(get_current_user)):
    require(user, "DISPATCH", "ACCOUNTS", "MANAGER", "OWNER")
    ch = await db.delivery_challans.find_one({"ecp_id": ecp_id}, NO_ID)
    return ch or {}


@api.post("/ecps/{ecp_id}/challan")
async def save_challan(ecp_id: str, body: ChallanBody, user: dict = Depends(get_current_user)):
    require(user, "DISPATCH", "OWNER")
    ecp = await db.ecps.find_one({"id": ecp_id}, NO_ID)
    if not ecp:
        raise HTTPException(status_code=404, detail="ECP not found")
    existing = await db.delivery_challans.find_one({"ecp_id": ecp_id}, NO_ID)
    if existing and existing.get("status") == "FINALIZED":
        raise HTTPException(status_code=400, detail="Delivery Challan is already finalized")
    for it in body.items:
        if it.item_id:
            m = await db.items.find_one({"id": it.item_id}, NO_ID)
            if not m or not m.get("active", True):
                raise HTTPException(status_code=400, detail="Challan item must be an active Item Master item")
    doc = {"ecp_id": ecp_id, "items": [i.dict() for i in body.items], "status": "DRAFT",
           "updated_by": user["name"], "updated_at": now_iso()}
    if existing:
        await db.delivery_challans.update_one({"ecp_id": ecp_id}, {"$set": doc})
    else:
        doc["id"] = new_id()
        doc["created_by"] = user["name"]
        await db.delivery_challans.insert_one(doc)
    return await db.delivery_challans.find_one({"ecp_id": ecp_id}, NO_ID)


@api.post("/ecps/{ecp_id}/challan/finalize")
async def finalize_challan(ecp_id: str, user: dict = Depends(get_current_user)):
    require(user, "DISPATCH", "OWNER")
    ch = await db.delivery_challans.find_one({"ecp_id": ecp_id}, NO_ID)
    if not ch:
        raise HTTPException(status_code=400, detail="Create the challan before finalizing")
    if ch.get("status") == "FINALIZED":
        raise HTTPException(status_code=400, detail="Already finalized")
    if not ch.get("items"):
        raise HTTPException(status_code=400, detail="Add at least one item before finalizing")
    await db.delivery_challans.update_one({"ecp_id": ecp_id}, {"$set": {
        "status": "FINALIZED", "finalized_by": user["name"], "finalized_at": now_iso()}})
    await log_activity(user, "Delivery Challan Finalized", "ECP", ecp_id, ch.get("ecp_id", ""), "")
    return await db.delivery_challans.find_one({"ecp_id": ecp_id}, NO_ID)


@api.get("/challans")
async def list_finalized_challans(user: dict = Depends(get_current_user)):
    require(user, "ACCOUNTS", "MANAGER", "OWNER")
    return await db.delivery_challans.find({"status": "FINALIZED"}, NO_ID).sort("finalized_at", -1).to_list(2000)


# ========================= PHASE 8: COMPLAINTS =========================
class CategoryBody(BaseModel):
    name: str


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None


@api.get("/complaint-categories")
async def list_categories(active_only: bool = False, user: dict = Depends(get_current_user)):
    q = {"active": True} if active_only else {}
    return await db.complaint_categories.find(q, NO_ID).sort("name", 1).to_list(500)


@api.post("/complaint-categories")
async def create_category(body: CategoryBody, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    if await db.complaint_categories.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}):
        raise HTTPException(status_code=409, detail="Category already exists")
    doc = {"id": new_id(), "name": name, "active": True, "created_at": now_iso()}
    await db.complaint_categories.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@api.patch("/complaint-categories/{cat_id}")
async def update_category(cat_id: str, body: CategoryUpdate, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    upd = {k: v for k, v in body.dict().items() if v is not None}
    if "name" in upd:
        upd["name"] = upd["name"].strip()
    await db.complaint_categories.update_one({"id": cat_id}, {"$set": upd})
    return await db.complaint_categories.find_one({"id": cat_id}, NO_ID)


class ComplaintSLABody(BaseModel):
    config: dict  # {"<category_id>|<PRIORITY>": days}


@api.get("/complaint-sla")
async def get_complaint_sla(user: dict = Depends(get_current_user)):
    doc = await db.complaint_sla.find_one({"id": "singleton"}, NO_ID)
    return doc or {"id": "singleton", "config": {}}


@api.put("/complaint-sla")
async def set_complaint_sla(body: ComplaintSLABody, user: dict = Depends(get_current_user)):
    require(user, "OWNER")
    cfg = {k: int(v) for k, v in body.config.items()}
    await db.complaint_sla.update_one({"id": "singleton"}, {"$set": {"config": cfg}}, upsert=True)
    return {"id": "singleton", "config": cfg}


async def _complaint_due_date(category_id, priority):
    sla = await db.complaint_sla.find_one({"id": "singleton"}, NO_ID)
    cfg = (sla or {}).get("config", {})
    days = cfg.get(f"{category_id}|{priority}")
    if not days:
        return None
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    ist = _dt.now(_tz.utc) + _td(hours=5, minutes=30)
    return (ist.date() + _td(days=int(days))).isoformat()


def _complaint_overdue(c):
    if c.get("status") in ("RESOLVED", "CLOSED") or not c.get("sla_due_date"):
        return False, 0
    today = ist_today_str()
    if today > c["sla_due_date"]:
        from datetime import date as _d
        days = (_d.fromisoformat(today) - _d.fromisoformat(c["sla_due_date"])).days
        return True, days
    return False, 0


def _complaint_enrich(c):
    overdue, days = _complaint_overdue(c)
    c["overdue"] = overdue
    c["days_overdue"] = days
    c["due_today"] = (not overdue) and c.get("sla_due_date") == ist_today_str() and c.get("status") not in ("RESOLVED", "CLOSED")
    return c


class ComplaintCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    category_id: str
    priority: str
    customer_name: Optional[str] = ""
    customer_phone: Optional[str] = ""
    lead_id: Optional[str] = None
    ecp_id: Optional[str] = None


class ComplaintAssign(BaseModel):
    assigned_team: str
    assigned_user: Optional[str] = None


class ComplaintStatusBody(BaseModel):
    status: str
    remarks: Optional[str] = ""


async def _complaint_hist(cid, user, action, details=""):
    await db.complaint_history.insert_one({
        "id": new_id(), "complaint_id": cid, "ts": now_iso(),
        "user_name": user["name"], "role": user["role"], "action": action, "details": details})


@api.post("/complaints")
async def create_complaint(body: ComplaintCreate, user: dict = Depends(get_current_user)):
    require(user, "COMPLAINT", "MANAGER", "OWNER")
    if body.priority not in wf.COMPLAINT_PRIORITIES:
        raise HTTPException(status_code=400, detail="Valid priority is required")
    cat = await db.complaint_categories.find_one({"id": body.category_id}, NO_ID)
    if not cat or not cat.get("active", True):
        raise HTTPException(status_code=400, detail="Valid active category is required")
    due = await _complaint_due_date(body.category_id, body.priority)
    doc = {"id": new_id(), "title": body.title.strip(), "description": (body.description or "").strip(),
           "category_id": body.category_id, "category_name": cat["name"], "priority": body.priority,
           "status": "REGISTERED", "assigned_team": None, "assigned_user": None, "assigned_user_name": None,
           "customer_name": (body.customer_name or "").strip(), "customer_phone": (body.customer_phone or "").strip(),
           "lead_id": body.lead_id, "ecp_id": body.ecp_id, "sla_due_date": due,
           "registered_by": user["id"], "registered_by_name": user["name"], "created_at": now_iso(),
           "resolved_at": None, "closed_at": None}
    await db.complaints.insert_one(doc)
    await _complaint_hist(doc["id"], user, "Registered", cat["name"])
    return _complaint_enrich({k: v for k, v in doc.items() if k != "_id"})


@api.get("/complaints")
async def list_complaints(user: dict = Depends(get_current_user)):
    role = user["role"]
    if role in ("OWNER", "MANAGER", "COMPLAINT"):
        q = {}
    else:
        q = {"assigned_user": user["id"]}
    cs = await db.complaints.find(q, NO_ID).sort("created_at", -1).to_list(3000)
    return [_complaint_enrich(c) for c in cs]


@api.get("/complaints/{cid}")
async def get_complaint(cid: str, user: dict = Depends(get_current_user)):
    c = await db.complaints.find_one({"id": cid}, NO_ID)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    role = user["role"]
    if role not in ("OWNER", "MANAGER", "COMPLAINT") and c.get("assigned_user") != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this complaint")
    hist = await db.complaint_history.find({"complaint_id": cid}, NO_ID).sort("ts", 1).to_list(500)
    atts = await db.complaint_attachments.find({"complaint_id": cid}, NO_ID).to_list(100)
    return {"complaint": _complaint_enrich(c), "history": hist, "attachments": atts}


@api.post("/complaints/{cid}/assign")
async def assign_complaint(cid: str, body: ComplaintAssign, user: dict = Depends(get_current_user)):
    require(user, "MANAGER", "OWNER")
    c = await db.complaints.find_one({"id": cid}, NO_ID)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if body.assigned_team not in wf.COMPLAINT_TEAMS:
        raise HTTPException(status_code=400, detail="Invalid team")
    upd = {"assigned_team": body.assigned_team, "status": "ASSIGNED", "updated_at": now_iso()}
    if body.assigned_user:
        emp = await db.users.find_one({"id": body.assigned_user}, NO_ID)
        if not emp:
            raise HTTPException(status_code=400, detail="Invalid assignee")
        upd["assigned_user"] = emp["id"]
        upd["assigned_user_name"] = emp["name"]
    await db.complaints.update_one({"id": cid}, {"$set": upd})
    await _complaint_hist(cid, user, "Assigned", f"{body.assigned_team}{(' / ' + upd.get('assigned_user_name')) if upd.get('assigned_user_name') else ''}")
    return _complaint_enrich(await db.complaints.find_one({"id": cid}, NO_ID))


@api.post("/complaints/{cid}/status")
async def set_complaint_status(cid: str, body: ComplaintStatusBody, user: dict = Depends(get_current_user)):
    c = await db.complaints.find_one({"id": cid}, NO_ID)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    role = user["role"]
    target = body.status
    if target in ("IN_PROGRESS", "RESOLVED"):
        if role != "OWNER" and c.get("assigned_user") != user["id"]:
            raise HTTPException(status_code=403, detail="Only the assigned member can update this complaint")
        if target == "IN_PROGRESS" and c["status"] != "ASSIGNED":
            raise HTTPException(status_code=400, detail="Complaint must be ASSIGNED first")
        if target == "RESOLVED" and c["status"] != "IN_PROGRESS":
            raise HTTPException(status_code=400, detail="Complaint must be IN_PROGRESS to resolve")
        upd = {"status": target, "updated_at": now_iso()}
        if target == "RESOLVED":
            upd["resolved_at"] = now_iso()
    elif target == "CLOSED":
        if role not in ("MANAGER", "OWNER"):
            raise HTTPException(status_code=403, detail="Only Manager/Owner can close a complaint")
        if c["status"] != "RESOLVED":
            raise HTTPException(status_code=400, detail="Only RESOLVED complaints can be closed")
        upd = {"status": "CLOSED", "closed_at": now_iso(), "updated_at": now_iso()}
    else:
        raise HTTPException(status_code=400, detail="Invalid status transition")
    await db.complaints.update_one({"id": cid}, {"$set": upd})
    await _complaint_hist(cid, user, f"Status → {target}", body.remarks or "")
    return _complaint_enrich(await db.complaints.find_one({"id": cid}, NO_ID))


@api.post("/complaints/{cid}/attachments")
async def upload_complaint_attachment(cid: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    c = await db.complaints.find_one({"id": cid}, NO_ID)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    role = user["role"]
    if role not in ("OWNER", "MANAGER", "COMPLAINT") and c.get("assigned_user") != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    ct = (file.content_type or "").lower()
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    if ct not in wf.DOC_ALLOWED_CONTENT_TYPES and ext not in wf.DOC_ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Only JPG, PNG or PDF files are allowed")
    data = await file.read()
    if len(data) > wf.DOC_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    path = f"{APP_NAME}/complaints/{cid}/{new_id()}.{ext or 'bin'}"
    result = put_object(path, data, ct or "application/octet-stream")
    doc = {"id": new_id(), "complaint_id": cid, "storage_path": result.get("path", path),
           "original_filename": file.filename, "content_type": ct, "uploaded_by_name": user["name"],
           "uploaded_at": now_iso()}
    await db.complaint_attachments.insert_one(doc)
    await _complaint_hist(cid, user, "Attachment Added", file.filename or "")
    return {k: v for k, v in doc.items() if k != "_id"}


@api.get("/complaints/{cid}/attachments/{att_id}/download")
async def download_complaint_attachment(cid: str, att_id: str, user: dict = Depends(get_current_user)):
    c = await db.complaints.find_one({"id": cid}, NO_ID)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    role = user["role"]
    if role not in ("OWNER", "MANAGER", "COMPLAINT") and c.get("assigned_user") != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    a = await db.complaint_attachments.find_one({"id": att_id, "complaint_id": cid}, NO_ID)
    if not a:
        raise HTTPException(status_code=404, detail="Attachment not found")
    content, ct = get_object(a["storage_path"])
    return Response(content=content, media_type=a.get("content_type") or ct,
                    headers={"Content-Disposition": f'inline; filename="{a.get("original_filename", "file")}"'})


@api.post("/site-visits/{sv_id}/photos")
async def upload_sv_photo(sv_id: str, file: UploadFile = File(...), lat: str = Form(None), lng: str = Form(None),
                          user: dict = Depends(get_current_user)):
    require(user, "INSTALLATION", "INSTALLATION_MEMBER", "OWNER")
    sv = await db.lead_site_visits.find_one({"id": sv_id}, NO_ID)
    if not sv:
        raise HTTPException(status_code=404, detail="Site visit not found")
    if user["role"] in wf.INSTALL_MEMBER_ROLES and sv.get("assigned_user") != user["id"]:
        raise HTTPException(status_code=403, detail="This site visit is not assigned to you")
    count = await db.site_visit_photos.count_documents({"sv_id": sv_id})
    if count >= 3:
        raise HTTPException(status_code=400, detail="Maximum 3 photos allowed")
    ct = (file.content_type or "").lower()
    if ct not in wf.PHOTO_ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG or PNG photos are allowed")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > wf.DOC_MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    path = f"{APP_NAME}/site_visit_photos/{sv_id}/{new_id()}.{'png' if 'png' in ct else 'jpg'}"
    result = put_object(path, data, ct)
    geo = None
    if lat and lng:
        try:
            geo = {"lat": float(lat), "lng": float(lng)}
        except ValueError:
            geo = None
    doc = {"id": new_id(), "sv_id": sv_id, "lead_id": sv.get("lead_id"), "storage_path": result.get("path", path),
           "content_type": ct, "geo": geo, "uploaded_by_name": user["name"], "uploaded_at": now_iso()}
    await db.site_visit_photos.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@api.get("/site-visits/{sv_id}/photos")
async def list_sv_photos(sv_id: str, user: dict = Depends(get_current_user)):
    sv = await db.lead_site_visits.find_one({"id": sv_id}, NO_ID)
    if not sv:
        raise HTTPException(status_code=404, detail="Site visit not found")
    if user["role"] not in {"OWNER", "MANAGER", "LEAD", "INSTALLATION_MANAGER"} | wf.INSTALL_MEMBER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"photos": await db.site_visit_photos.find({"sv_id": sv_id}, NO_ID).to_list(10)}


@api.get("/site-visits/{sv_id}/photos/{photo_id}/download")
async def download_sv_photo(sv_id: str, photo_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in {"OWNER", "MANAGER", "LEAD", "INSTALLATION_MANAGER"} | wf.INSTALL_MEMBER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    p = await db.site_visit_photos.find_one({"id": photo_id, "sv_id": sv_id}, NO_ID)
    if not p:
        raise HTTPException(status_code=404, detail="Photo not found")
    content, ct = get_object(p["storage_path"])
    return Response(content=content, media_type=p.get("content_type") or ct)


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("username", unique=True)
    await db.leads.create_index("status")
    await db.ecps.create_index("current_stage")
    await db.payments.create_index("ecp_id")
    try:
        await db.lead_documents.create_index("lead_id")
    except Exception:
        pass
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed (uploads will retry): {e}")
    await seed()


async def seed():
    owner_username = os.environ.get("OWNER_USERNAME", "anoopdube07@gmail.com").strip().lower()
    owner_password = os.environ.get("OWNER_PASSWORD", "Owner@123")
    existing = await db.users.find_one({"username": owner_username})
    if not existing:
        await db.users.insert_one({
            "id": new_id(), "username": owner_username, "password_hash": hash_password(owner_password),
            "name": "Anoop Dube", "role": "OWNER", "team": "OWNER", "active": True, "created_at": now_iso()})
        logger.info("Seeded owner user")
    # demo team users
    demo = [
        ("manager", "Manager@123", "Priya Manager", "MANAGER"),
        ("lead", "Lead@123", "Rahul Lead", "LEAD"),
        ("registration", "Reg@123", "Sunita Reg", "REGISTRATION"),
        ("accounts", "Acct@123", "Vikram Accounts", "ACCOUNTS"),
        ("dispatch", "Disp@123", "Amit Dispatch", "DISPATCH"),
        ("installation", "Install@123", "Ravi Install", "INSTALLATION"),
        ("instmgr", "InstMgr@123", "Iqbal Install-Manager", "INSTALLATION_MANAGER"),
        ("instmem", "InstMem@123", "Manish Install-Member", "INSTALLATION_MEMBER"),
        ("complaint", "Comp@123", "Neha Complaints", "COMPLAINT"),
    ]
    for uname, pwd, name, role in demo:
        if not await db.users.find_one({"username": uname}):
            await db.users.insert_one({
                "id": new_id(), "username": uname, "password_hash": hash_password(pwd),
                "name": name, "role": role, "team": role, "active": True, "created_at": now_iso()})


@app.on_event("shutdown")
async def shutdown():
    client.close()
