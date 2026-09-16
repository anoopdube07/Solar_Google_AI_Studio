"""P0 regression: LEAD dashboard metrics must scope to lead_owner_id in (user.id, None).
Foreign-owned leads/ECPs/site-visits must not inflate LEAD dashboard counters.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient


def _load_env(key: str, fpath: str):
    p = Path(fpath)
    for line in p.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(f"{key} not in {fpath}")


BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _load_env("REACT_APP_BACKEND_URL", "/app/frontend/.env")).rstrip("/")
API = f"{BASE}/api"
MONGO_URL = _load_env("MONGO_URL", "/app/backend/.env")
DB_NAME = _load_env("DB_NAME", "/app/backend/.env")

CREDS = {
    "OWNER": ("anoopdube07@gmail.com", "Owner@123"),
    "LEAD": ("lead", "Lead@123"),
}

EXPECTED_LEAD_KEYS = {
    "role", "role_label",
    "action_required", "followups_today", "waiting_site_visit",
    "escalated", "qualified", "lost", "pending_documents",
}


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def tokens():
    return {role: _login(u, p) for role, (u, p) in CREDS.items()}


def _h(tokens, role):
    return {"Authorization": f"Bearer {tokens[role]['token']}"}


def _dash(tokens, role):
    r = requests.get(f"{API}/dashboard", headers=_h(tokens, role), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def synthetic_foreign(mongo, tokens):
    """Insert foreign-owned leads (across statuses) + foreign-owned PENDING_DOCUMENTS ECP.
    Also insert an own PENDING_DOCUMENTS ECP for the LEAD user so we can verify
    positive contribution. Yields identifiers; teardown deletes everything.
    """
    lead_user_id = tokens["LEAD"]["user"]["id"]
    foreign_id = f"TEST_FOREIGN_LEAD_{uuid.uuid4().hex[:8]}"

    # Template docs
    lead_tmpl = mongo.leads.find_one({}, {"_id": 0})
    ecp_tmpl = mongo.ecps.find_one({}, {"_id": 0})
    assert lead_tmpl and ecp_tmpl, "Need seed lead + ecp templates"

    created_lead_ids = []
    today = datetime.now(timezone.utc).date().isoformat()

    def mk_lead(status: str, action_required: bool):
        lid = f"TEST_LEAD_{status}_{uuid.uuid4().hex[:8]}"
        d = dict(lead_tmpl)
        d["id"] = lid
        d["name"] = f"TEST {status}"
        d["status"] = status
        d["action_required"] = action_required
        d["lead_owner_id"] = foreign_id
        d["lead_owner_name"] = "TEST Foreign"
        d["created_at"] = datetime.now(timezone.utc).isoformat()
        d["updated_at"] = d["created_at"]
        d.pop("_id", None)
        mongo.leads.insert_one(d)
        created_lead_ids.append(lid)
        return lid

    # PENDING with action_required=True -> would inflate action_required
    pending_id = mk_lead("PENDING", True)
    site_id = mk_lead("SITE_VISIT", False)
    esc_id = mk_lead("ESCALATED", False)
    qual_id = mk_lead("QUALIFIED", False)
    lost_id = mk_lead("LOST", False)
    fu_id = mk_lead("FOLLOW_UP", True)

    # Followup for today on the foreign FOLLOW_UP lead
    fu_doc_id = f"TEST_FU_{uuid.uuid4().hex[:8]}"
    mongo.lead_followups.insert_one({
        "id": fu_doc_id,
        "lead_id": fu_id,
        "followup_date": today,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "TEST fu",
    })

    # Foreign PENDING_DOCUMENTS ECP (active)
    foreign_ecp_id = f"TEST_ECP_FOREIGN_{uuid.uuid4().hex[:8]}"
    fe = dict(ecp_tmpl)
    fe["id"] = foreign_ecp_id
    fe["current_stage"] = "PENDING_DOCUMENTS"
    fe["status"] = "ACTIVE"
    fe["lead_owner_id"] = foreign_id
    fe["lead_owner_name"] = "TEST Foreign"
    fe["created_at"] = datetime.now(timezone.utc).isoformat()
    fe.pop("_id", None)
    mongo.ecps.insert_one(fe)

    # Site visit tied to a foreign lead
    sv_id = f"TEST_SV_{uuid.uuid4().hex[:8]}"
    mongo.lead_site_visits.insert_one({
        "id": sv_id,
        "lead_id": site_id,
        "status": "REQUESTED",
        "assigned_user": None,
        "visit_date": today,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Own PENDING_DOCUMENTS ECP for positive test
    own_ecp_id = f"TEST_ECP_OWN_{uuid.uuid4().hex[:8]}"
    oe = dict(ecp_tmpl)
    oe["id"] = own_ecp_id
    oe["current_stage"] = "PENDING_DOCUMENTS"
    oe["status"] = "ACTIVE"
    oe["lead_owner_id"] = lead_user_id
    oe["lead_owner_name"] = tokens["LEAD"]["user"].get("name") or "lead"
    oe["created_at"] = datetime.now(timezone.utc).isoformat()
    oe.pop("_id", None)
    mongo.ecps.insert_one(oe)

    # Own QUALIFIED lead for positive test
    own_qual_id = f"TEST_LEAD_OWN_QUAL_{uuid.uuid4().hex[:8]}"
    ol = dict(lead_tmpl)
    ol["id"] = own_qual_id
    ol["name"] = "TEST OWN QUAL"
    ol["status"] = "QUALIFIED"
    ol["action_required"] = False
    ol["lead_owner_id"] = lead_user_id
    ol["lead_owner_name"] = tokens["LEAD"]["user"].get("name") or "lead"
    ol["created_at"] = datetime.now(timezone.utc).isoformat()
    ol["updated_at"] = ol["created_at"]
    ol.pop("_id", None)
    mongo.leads.insert_one(ol)
    created_lead_ids.append(own_qual_id)

    yield {
        "foreign_owner_id": foreign_id,
        "foreign_lead_ids": [pending_id, site_id, esc_id, qual_id, lost_id, fu_id],
        "foreign_ecp_id": foreign_ecp_id,
        "own_ecp_id": own_ecp_id,
        "own_qual_lead_id": own_qual_id,
        "fu_doc_id": fu_doc_id,
        "sv_id": sv_id,
    }

    # Teardown
    mongo.leads.delete_many({"id": {"$in": created_lead_ids}})
    mongo.ecps.delete_many({"id": {"$in": [foreign_ecp_id, own_ecp_id]}})
    mongo.lead_followups.delete_one({"id": fu_doc_id})
    mongo.lead_site_visits.delete_one({"id": sv_id})


@pytest.fixture(scope="module")
def baseline(tokens):
    """Dashboards BEFORE inserting synthetic data."""
    return {"LEAD": _dash(tokens, "LEAD"), "OWNER": _dash(tokens, "OWNER")}


# ---------- Contract ----------
def test_lead_dashboard_contract(baseline):
    keys = set(baseline["LEAD"].keys())
    assert keys == EXPECTED_LEAD_KEYS, f"LEAD dashboard keys drift: extra={keys - EXPECTED_LEAD_KEYS} missing={EXPECTED_LEAD_KEYS - keys}"
    assert baseline["LEAD"]["role"] == "LEAD"


# ---------- Security: foreign-owned data must NOT inflate LEAD counts ----------
def test_lead_dashboard_isolated_from_foreign(tokens, synthetic_foreign, baseline):
    """After inserting foreign-owned records AND own-owned records, the LEAD dashboard
    must reflect ONLY the own-owned contribution. Foreign-owned inserts must NOT leak
    into any counter."""
    after = _dash(tokens, "LEAD")
    b = baseline["LEAD"]
    # Expected deltas due only to OWN inserts (foreign inserts must contribute 0)
    expected_delta = {
        "action_required": 0,
        "followups_today": 0,
        "waiting_site_visit": 0,
        "escalated": 0,
        "qualified": 1,           # one OWN QUALIFIED lead inserted
        "lost": 0,
        "pending_documents": 1,   # one OWN PENDING_DOCUMENTS ecp inserted
    }
    for k, delta in expected_delta.items():
        expected = b[k] + delta
        assert after[k] == expected, (
            f"LEAK/wrong-count: LEAD dashboard '{k}' expected {expected} "
            f"(baseline {b[k]} + own delta {delta}) but got {after[k]}. "
            f"A non-zero deviation implies foreign-owned data leaked into the counter."
        )


# ---------- Regression: OWNER dashboard sees the foreign inserts ----------
def test_owner_dashboard_counts_foreign(tokens, synthetic_foreign, baseline):
    after = _dash(tokens, "OWNER")
    b = baseline["OWNER"]
    # OWNER leads counts should each increase for the corresponding status
    for status in ("PENDING", "FOLLOW_UP", "SITE_VISIT", "ESCALATED", "LOST"):
        assert after["leads"][status] >= b["leads"][status] + 1, (
            f"OWNER leads[{status}] did not increase (before={b['leads'][status]} after={after['leads'][status]})"
        )
    # QUALIFIED gets +2 (foreign + own)
    assert after["leads"]["QUALIFIED"] >= b["leads"]["QUALIFIED"] + 2
    # OWNER ecp PENDING_DOCUMENTS should increase by 2 (foreign + own)
    assert after["ecp"]["PENDING_DOCUMENTS"] >= b["ecp"]["PENDING_DOCUMENTS"] + 2, (
        f"OWNER ecp[PENDING_DOCUMENTS] did not increase properly"
    )
    # OWNER contract keys preserved
    for k in ("leads", "ecp", "payments", "pending_commercial"):
        assert k in after, f"OWNER dashboard missing key {k}"


# ---------- Positive: OWN records DO contribute to LEAD dashboard ----------
def test_lead_dashboard_own_records_count(tokens, synthetic_foreign, baseline):
    after = _dash(tokens, "LEAD")
    b = baseline["LEAD"]
    assert after["pending_documents"] == b["pending_documents"] + 1, (
        f"Own PENDING_DOCUMENTS ECP did not increment (before={b['pending_documents']} after={after['pending_documents']})"
    )
    assert after["qualified"] == b["qualified"] + 1, (
        f"Own QUALIFIED lead did not increment (before={b['qualified']} after={after['qualified']})"
    )
