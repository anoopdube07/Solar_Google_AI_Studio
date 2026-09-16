"""Iteration 8 targeted scope test:
1) OWNER can create users with roles INSTALLATION_MANAGER / INSTALLATION_MEMBER / COMPLAINT
2) Non-owner (LEAD) POST /api/users -> 403
3) GET /api/dashboard returns the correct keys for the 3 new roles
4) COMPLAINT can create a complaint (creating a category first if none active)
"""
import os
import uuid
import requests
import pytest

_url = os.environ.get("REACT_APP_BACKEND_URL")
if not _url:
    with open("/app/frontend/.env") as _f:
        for _line in _f:
            if _line.startswith("REACT_APP_BACKEND_URL"):
                _url = _line.split("=", 1)[1].strip()
                break
BASE_URL = _url.rstrip("/") + "/api"


def _login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {username}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_token():
    return _login("anoopdube07@gmail.com", "Owner@123")


@pytest.fixture(scope="module")
def lead_token():
    return _login("lead", "Lead@123")


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- User creation RBAC ----------------
@pytest.mark.parametrize("role", ["INSTALLATION_MANAGER", "INSTALLATION_MEMBER", "COMPLAINT"])
def test_owner_can_create_new_role_user(owner_token, role):
    uname = f"TEST_{role.lower()}_{uuid.uuid4().hex[:6]}"
    payload = {"username": uname, "password": "Passw0rd!", "name": f"Test {role}", "phone": f"9{uuid.uuid4().int % 10**9:09d}", "role": role}
    r = requests.post(f"{BASE_URL}/users", json=payload, headers=_h(owner_token), timeout=30)
    assert r.status_code == 200, f"{role} create failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("role") == role
    assert data.get("username") == uname.lower()
    # confirm login works for the freshly created user
    tok = _login(uname.lower(), "Passw0rd!")
    assert tok


def test_lead_cannot_create_user(lead_token):
    uname = f"TEST_forbidden_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/users",
        json={"username": uname, "password": "Passw0rd!", "name": "no", "phone": f"9{uuid.uuid4().int % 10**9:09d}", "role": "INSTALLATION_MEMBER"},
        headers=_h(lead_token),
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


# ---------------- Dashboard keys per role ----------------
EXPECTED_KEYS = {
    "INSTALLATION_MANAGER": {"awaiting_assignment", "install_in_process", "pending_acceptance", "sv_awaiting", "sv_in_process", "net_metering"},
    "INSTALLATION_MEMBER": {"sv_assigned", "sv_today", "sv_completed", "ready_to_install", "install_in_process", "pending_acceptance"},
    "COMPLAINT": {"registered", "assigned", "in_progress", "critical", "overdue", "due_today"},
}


@pytest.mark.parametrize("username,password,role", [
    ("instmgr", "InstMgr@123", "INSTALLATION_MANAGER"),
    ("instmem", "InstMem@123", "INSTALLATION_MEMBER"),
    ("complaint", "Comp@123", "COMPLAINT"),
])
def test_dashboard_keys(username, password, role):
    tok = _login(username, password)
    r = requests.get(f"{BASE_URL}/dashboard", headers=_h(tok), timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    missing = EXPECTED_KEYS[role] - set(data.keys())
    assert not missing, f"{role} missing keys: {missing}. Got: {list(data.keys())}"
    for k in EXPECTED_KEYS[role]:
        assert isinstance(data[k], int), f"{role}.{k} should be int, got {type(data[k])}"


# ---------------- COMPLAINT can register a complaint ----------------
def test_complaint_end_to_end(owner_token):
    comp_tok = _login("complaint", "Comp@123")
    # ensure an active category exists (create as OWNER if list is empty/no active)
    r = requests.get(f"{BASE_URL}/complaint-categories", headers=_h(comp_tok), timeout=30)
    assert r.status_code == 200, r.text
    cats = r.json()
    active = [c for c in cats if c.get("active", True)]
    if not active:
        rc = requests.post(
            f"{BASE_URL}/complaint-categories",
            json={"name": f"TEST_CAT_{uuid.uuid4().hex[:6]}"},
            headers=_h(owner_token),
            timeout=30,
        )
        assert rc.status_code == 200, rc.text
        active = [rc.json()]

    cat = active[0]
    cat_id = cat.get("id") or cat.get("_id") or cat.get("category_id")
    assert cat_id, f"category has no id: {cat}"

    # need a lead reference; grab any lead visible to complaint role, else fall back to owner list
    lead_id = None
    lr = requests.get(f"{BASE_URL}/leads", headers=_h(owner_token), timeout=30)
    if lr.status_code == 200 and isinstance(lr.json(), list) and lr.json():
        lead_id = lr.json()[0].get("id")

    payload = {
        "category_id": cat_id,
        "title": "TEST complaint title",
        "priority": "MEDIUM",
        "description": "TEST_complaint iteration8",
    }
    if lead_id:
        payload["lead_id"] = lead_id

    rp = requests.post(f"{BASE_URL}/complaints", json=payload, headers=_h(comp_tok), timeout=30)
    assert rp.status_code == 200, f"register complaint failed: {rp.status_code} {rp.text}"
    comp = rp.json()
    assert comp.get("status") == "REGISTERED", f"unexpected status {comp.get('status')}"

    # confirm it appears in list
    lr2 = requests.get(f"{BASE_URL}/complaints", headers=_h(comp_tok), timeout=30)
    assert lr2.status_code == 200
    ids = [c.get("id") for c in lr2.json()]
    assert comp.get("id") in ids
