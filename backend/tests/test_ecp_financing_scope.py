"""Regression: POST /api/ecps/{ecp_id}/financing must enforce LEAD ownership.

Cross-user LEAD -> 403; own/None LEAD -> 200; MANAGER/OWNER on foreign -> 200.
Neither ecp.financing_required nor the linked lead.financing_required may
change on the forbidden call.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient


def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _load_url().rstrip("/")
API = f"{BASE}/api"

CREDS = {
    "OWNER": ("anoopdube07@gmail.com", "Owner@123"),
    "MANAGER": ("manager", "Manager@123"),
    "LEAD": ("lead", "Lead@123"),
}


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=15)
    assert r.status_code == 200, f"login failed {u}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def tokens():
    return {role: _login(u, p) for role, (u, p) in CREDS.items()}


def _h(tokens, role):
    return {"Authorization": f"Bearer {tokens[role]['token']}"}


@pytest.fixture(scope="module")
def db_handle():
    env = dict(
        line.split("=", 1)
        for line in Path("/app/backend/.env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    mongo_url = env["MONGO_URL"].strip().strip('"')
    db_name = env["DB_NAME"].strip().strip('"')
    client = MongoClient(mongo_url)
    yield client[db_name]
    client.close()


def _insert_ecp_and_lead(db, lead_owner_id, financing_required=False):
    """Insert a synthetic ECP + linked Lead with the given lead_owner_id."""
    ecp_template = db.ecps.find_one({}, {"_id": 0})
    lead_template = db.leads.find_one({}, {"_id": 0})
    assert ecp_template and lead_template, "Need existing docs as templates"
    suffix = uuid.uuid4().hex[:8]
    lead_id = f"TEST_LEAD_{suffix}"
    ecp_id = f"TEST_ECP_{suffix}"
    now = datetime.now(timezone.utc).isoformat()

    lead_doc = dict(lead_template)
    lead_doc.update({
        "id": lead_id,
        "lead_owner_id": lead_owner_id,
        "lead_owner_name": "TEST Owner" if lead_owner_id else None,
        "financing_required": financing_required,
        "ecp_id": ecp_id,
        "created_at": now,
        "updated_at": now,
    })
    ecp_doc = dict(ecp_template)
    ecp_doc.update({
        "id": ecp_id,
        "lead_id": lead_id,
        "lead_owner_id": lead_owner_id,
        "lead_owner_name": "TEST Owner" if lead_owner_id else None,
        "financing_required": financing_required,
        "current_stage": "REGISTRATION_1",  # avoid PENDING_DOCUMENTS short-circuit
        "created_at": now,
        "updated_at": now,
    })
    db.leads.insert_one(lead_doc)
    db.ecps.insert_one(ecp_doc)
    return ecp_id, lead_id


def _cleanup(db, ecp_id, lead_id):
    db.ecps.delete_one({"id": ecp_id})
    db.leads.delete_one({"id": lead_id})
    db.ecp_tasks.delete_many({"ecp_id": ecp_id})


# ---------- SECURITY: LEAD on foreign ECP -> 403, no mutation ----------
def test_lead_forbidden_on_foreign_ecp(tokens, db_handle):
    foreign_id = f"TEST_FOREIGN_LEAD_{uuid.uuid4().hex[:8]}"
    ecp_id, lead_id = _insert_ecp_and_lead(db_handle, foreign_id, financing_required=False)
    try:
        r = requests.post(
            f"{API}/ecps/{ecp_id}/financing",
            headers=_h(tokens, "LEAD"),
            json={"financing_required": True},
            timeout=15,
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"
        # verify no mutation
        ecp_after = db_handle.ecps.find_one({"id": ecp_id}, {"_id": 0})
        lead_after = db_handle.leads.find_one({"id": lead_id}, {"_id": 0})
        assert ecp_after["financing_required"] is False, "ECP financing mutated on 403"
        assert lead_after["financing_required"] is False, "Lead financing mutated on 403"
    finally:
        _cleanup(db_handle, ecp_id, lead_id)


# ---------- POSITIVE: LEAD on own ECP -> 200, mutation applied ----------
def test_lead_allowed_on_own_ecp(tokens, db_handle):
    lead_user_id = tokens["LEAD"]["user"]["id"]
    ecp_id, lead_id = _insert_ecp_and_lead(db_handle, lead_user_id, financing_required=False)
    try:
        r = requests.post(
            f"{API}/ecps/{ecp_id}/financing",
            headers=_h(tokens, "LEAD"),
            json={"financing_required": True},
            timeout=15,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code} {r.text}"
        body = r.json()
        assert "ecp" in body, f"Expected ECP detail payload, got {body}"
        assert body["ecp"]["id"] == ecp_id
        assert body["ecp"]["financing_required"] is True
        lead_after = db_handle.leads.find_one({"id": lead_id}, {"_id": 0})
        assert lead_after["financing_required"] is True
    finally:
        _cleanup(db_handle, ecp_id, lead_id)


# ---------- POSITIVE: LEAD on unassigned (lead_owner_id=None) ECP -> 200 ----------
def test_lead_allowed_on_unassigned_ecp(tokens, db_handle):
    ecp_id, lead_id = _insert_ecp_and_lead(db_handle, None, financing_required=False)
    try:
        r = requests.post(
            f"{API}/ecps/{ecp_id}/financing",
            headers=_h(tokens, "LEAD"),
            json={"financing_required": True},
            timeout=15,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code} {r.text}"
        assert r.json()["ecp"]["financing_required"] is True
    finally:
        _cleanup(db_handle, ecp_id, lead_id)


# ---------- REGRESSION: MANAGER on foreign ECP -> 200 ----------
def test_manager_allowed_on_foreign_ecp(tokens, db_handle):
    foreign_id = f"TEST_FOREIGN_LEAD_{uuid.uuid4().hex[:8]}"
    ecp_id, lead_id = _insert_ecp_and_lead(db_handle, foreign_id, financing_required=False)
    try:
        r = requests.post(
            f"{API}/ecps/{ecp_id}/financing",
            headers=_h(tokens, "MANAGER"),
            json={"financing_required": True},
            timeout=15,
        )
        assert r.status_code == 200, f"MANAGER blocked on foreign: {r.status_code} {r.text}"
        assert r.json()["ecp"]["financing_required"] is True
    finally:
        _cleanup(db_handle, ecp_id, lead_id)


# ---------- REGRESSION: OWNER on foreign ECP -> 200 ----------
def test_owner_allowed_on_foreign_ecp(tokens, db_handle):
    foreign_id = f"TEST_FOREIGN_LEAD_{uuid.uuid4().hex[:8]}"
    ecp_id, lead_id = _insert_ecp_and_lead(db_handle, foreign_id, financing_required=True)
    try:
        r = requests.post(
            f"{API}/ecps/{ecp_id}/financing",
            headers=_h(tokens, "OWNER"),
            json={"financing_required": False},
            timeout=15,
        )
        assert r.status_code == 200, f"OWNER blocked on foreign: {r.status_code} {r.text}"
        assert r.json()["ecp"]["financing_required"] is False
    finally:
        _cleanup(db_handle, ecp_id, lead_id)


# ---------- 404 on non-existent id ----------
def test_nonexistent_ecp_404(tokens):
    r = requests.post(
        f"{API}/ecps/does-not-exist-xyz/financing",
        headers=_h(tokens, "OWNER"),
        json={"financing_required": True},
        timeout=15,
    )
    assert r.status_code == 404
