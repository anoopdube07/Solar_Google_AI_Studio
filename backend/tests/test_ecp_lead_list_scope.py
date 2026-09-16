"""LEAD list visibility regression: GET /api/ecps must only return ECPs
owned by the requesting LEAD user (lead_owner_id == user.id or None)."""
import os
import pytest
import requests
from pathlib import Path


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
    "ACCOUNTS": ("accounts", "Acct@123"),
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
def owner_ecps(tokens):
    r = requests.get(f"{API}/ecps", headers=_h(tokens, "OWNER"), timeout=30)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def lead_ecps(tokens):
    r = requests.get(f"{API}/ecps", headers=_h(tokens, "LEAD"), timeout=30)
    assert r.status_code == 200
    return r.json()


# ---------- Core security fix: LEAD list scoped to own lead_owner_id ----------
def test_lead_list_only_own_or_null(tokens, lead_ecps):
    lead_id = tokens["LEAD"]["user"]["id"]
    assert isinstance(lead_ecps, list)
    for e in lead_ecps:
        loi = e.get("lead_owner_id", None)
        assert loi in (lead_id, None), (
            f"LEAD received ECP {e.get('id')} with lead_owner_id={loi} "
            f"(expected {lead_id} or None)"
        )


def test_lead_list_is_subset_of_owner_list(owner_ecps, lead_ecps, tokens):
    owner_ids = {e["id"] for e in owner_ecps}
    lead_ids = {e["id"] for e in lead_ecps}
    assert lead_ids.issubset(owner_ids), "LEAD list must be subset of OWNER list"

    # Sanity: if OWNER sees ECPs owned by other lead owners, they must be excluded.
    lead_id = tokens["LEAD"]["user"]["id"]
    excluded = [e for e in owner_ecps if e.get("lead_owner_id") not in (lead_id, None)]
    for e in excluded:
        assert e["id"] not in lead_ids, (
            f"Leak: ECP {e['id']} owned by lead_owner_id={e.get('lead_owner_id')} "
            f"visible to LEAD"
        )
    # Complement check: every ECP with matching lead_owner_id in OWNER list must appear in LEAD list.
    should_see = {e["id"] for e in owner_ecps if e.get("lead_owner_id") in (lead_id, None)}
    missing = should_see - lead_ids
    assert not missing, f"LEAD missing own ECPs from list: {missing}"


# ---------- List/detail parity for LEAD ----------
def test_lead_list_detail_parity(tokens, lead_ecps):
    for e in lead_ecps[:10]:
        d = requests.get(f"{API}/ecps/{e['id']}", headers=_h(tokens, "LEAD"), timeout=15)
        assert d.status_code == 200, f"LEAD listed {e['id']} but detail={d.status_code}"
        assert d.json()["ecp"]["id"] == e["id"]


def test_lead_detail_404_for_other_owner_ecp(tokens, owner_ecps):
    lead_id = tokens["LEAD"]["user"]["id"]
    other = next(
        (e for e in owner_ecps if e.get("lead_owner_id") not in (lead_id, None)),
        None,
    )
    if other is None:
        pytest.skip("No ECP owned by a different lead_owner available to test IDOR")
    d = requests.get(f"{API}/ecps/{other['id']}", headers=_h(tokens, "LEAD"), timeout=15)
    assert d.status_code == 404, (
        f"IDOR: LEAD could read ECP {other['id']} owned by {other.get('lead_owner_id')}"
    )


# ---------- Synthetic isolation: insert a foreign-owned ECP, verify LEAD can't see it ----------
@pytest.fixture(scope="module")
def synthetic_foreign_ecp():
    """Directly insert an ECP with a different (foreign) lead_owner_id to prove isolation.
    Uses backend MongoDB. Cleans up afterwards."""
    import uuid
    from datetime import datetime, timezone
    from pymongo import MongoClient
    from pathlib import Path

    env = dict(
        line.split("=", 1)
        for line in Path("/app/backend/.env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    mongo_url = env["MONGO_URL"].strip().strip('"')
    db_name = env["DB_NAME"].strip().strip('"')
    client = MongoClient(mongo_url)
    db = client[db_name]

    foreign_id = f"TEST_FOREIGN_LEAD_{uuid.uuid4().hex[:8]}"
    ecp_id = f"TEST_ECP_FOREIGN_{uuid.uuid4().hex[:8]}"
    # Fetch a real ecp to copy shape
    template = db.ecps.find_one({}, {"_id": 0})
    assert template, "No ECP template found in DB"
    doc = dict(template)
    doc["id"] = ecp_id
    doc["lead_owner_id"] = foreign_id
    doc["lead_owner_name"] = "TEST Foreign Lead"
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    db.ecps.insert_one(doc)
    yield {"id": ecp_id, "lead_owner_id": foreign_id}
    db.ecps.delete_one({"id": ecp_id})
    client.close()


def test_lead_cannot_see_foreign_owned_ecp_in_list(tokens, synthetic_foreign_ecp):
    r = requests.get(f"{API}/ecps", headers=_h(tokens, "LEAD"), timeout=30)
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert synthetic_foreign_ecp["id"] not in ids, (
        "LEAD list leaked a foreign-owned ECP (lead_owner_id mismatch)"
    )


def test_lead_cannot_get_foreign_owned_ecp_detail(tokens, synthetic_foreign_ecp):
    d = requests.get(
        f"{API}/ecps/{synthetic_foreign_ecp['id']}",
        headers=_h(tokens, "LEAD"),
        timeout=15,
    )
    assert d.status_code == 404, (
        f"IDOR: LEAD read foreign-owned ECP, got {d.status_code}"
    )


def test_owner_can_see_foreign_owned_ecp(tokens, synthetic_foreign_ecp):
    r = requests.get(f"{API}/ecps", headers=_h(tokens, "OWNER"), timeout=30)
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert synthetic_foreign_ecp["id"] in ids, "OWNER should see all ECPs"


# ---------- Regression: OWNER/MANAGER/ACCOUNTS still see all ----------
@pytest.mark.parametrize("role", ["OWNER", "MANAGER", "ACCOUNTS"])
def test_privileged_roles_see_all(tokens, role):
    # Refetch OWNER list fresh so ordering vs synthetic insert doesn't matter
    ro = requests.get(f"{API}/ecps", headers=_h(tokens, "OWNER"), timeout=30)
    assert ro.status_code == 200
    owner_ids = {e["id"] for e in ro.json()}
    r = requests.get(f"{API}/ecps", headers=_h(tokens, role), timeout=30)
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert ids == owner_ids, f"{role} list differs from OWNER (delta={owner_ids ^ ids})"
