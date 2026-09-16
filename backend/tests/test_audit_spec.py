"""Audit-run tests for spec-adherence changes and RBAC hardening.
Focus:
- OWNER 403 on POST /api/leads/{id}/action (spec D)
- Dispatch continuity: FIRST payment reverted to PENDING after dispatch started must not stop dispatch
- Financing NO->YES after REGISTRATION_1 must not regress stage (already covered) and RBAC on financing toggle
- Users/SLA endpoints owner-only (MANAGER 403 explicit)
- Task completion: wrong-team 403
- Escalations MANAGER 403 (read/return)
- Site visits: INSTALLATION cannot complete another user's visit
- Auth: 401 without token on protected endpoints; deactivated user 403
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "owner":        ("anoopdube07@gmail.com", "Owner@123",   "OWNER"),
    "manager":      ("manager",               "Manager@123", "MANAGER"),
    "lead":         ("lead",                  "Lead@123",    "LEAD"),
    "registration": ("registration",          "Reg@123",     "REGISTRATION"),
    "accounts":     ("accounts",              "Acct@123",    "ACCOUNTS"),
    "dispatch":     ("dispatch",              "Disp@123",    "DISPATCH"),
    "installation": ("installation",          "Install@123", "INSTALLATION"),
    "instmgr":      ("instmgr",               "InstMgr@123", "INSTALLATION_MANAGER"),
    "instmem":      ("instmem",               "InstMem@123", "INSTALLATION_MEMBER"),
}


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    t = {}
    for k, (u, p, role) in CREDS.items():
        j = _login(u, p)
        t[k] = j["token"]
    return t


def _new_lead(tokens, financing=False):
    r = requests.post(f"{API}/leads",
        json={"name": f"TEST_A_{uuid.uuid4().hex[:6]}", "phone": f"9{uuid.uuid4().int % 1000000000:09d}",
              "financing_required": financing},
        headers=_hdr(tokens["lead"]))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _release_docs(lead_id, tokens, financing=False):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    types = ["PAN", "AADHAAR", "ELECTRICITY_BILL"]
    if financing:
        types.append("PROPERTY_PAPER")
    types.append("BANK_PASSBOOK")
    for t in types:
        rr = requests.post(f"{API}/leads/{lead_id}/documents", data={"doc_type": t},
                           files={"file": ("d.png", png, "image/png")}, headers=_hdr(tokens["lead"]))
        assert rr.status_code == 200, f"doc {t}: {rr.text}"


def _qualify(tokens, financing=False):
    lid = _new_lead(tokens, financing=financing)
    r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"},
                      headers=_hdr(tokens["lead"]))
    assert r.status_code == 200, r.text
    ecp_id = r.json()["ecp"]["id"]
    _release_docs(lid, tokens, financing)
    return lid, ecp_id


def _complete_all(ecp_id, stage, token):
    r = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(token))
    for t in r.json()["tasks"]:
        if t["stage"] == stage and t["applicable"] and not t["completed"]:
            rr = requests.post(f"{API}/ecps/{ecp_id}/tasks/{t['id']}/complete", headers=_hdr(token))
            assert rr.status_code == 200, f"complete failed {t['task_name']}: {rr.text}"


# --------- AUTH ---------
class TestAuthHardening:
    def test_protected_endpoints_401_without_token(self):
        for path in ["/auth/me", "/leads", "/ecps", "/dashboard", "/site-visits",
                     "/escalations", "/payments/monitor", "/users", "/sla"]:
            r = requests.get(f"{API}{path}")
            assert r.status_code == 401, f"{path} should require auth: got {r.status_code}"

    def test_login_invalid_401(self):
        r = requests.post(f"{API}/auth/login", json={"username": "lead", "password": "wrong"})
        assert r.status_code == 401


# --------- SPEC D: OWNER 403 on /leads/{id}/action ---------
class TestOwnerCannotDecideLeadAction:
    def test_owner_forbidden_on_all_five_actions(self, tokens):
        lid = _new_lead(tokens)
        for act in [
            {"action": "YES"},
            {"action": "NO", "lost_reason": "PRICE"},
            {"action": "FOLLOW_UP", "followup_date": "2027-06-15", "remarks": "x"},
            {"action": "SITE_VISIT", "remarks": "please"},
            {"action": "ESCALATION", "reason": "r", "remarks": "x"},
        ]:
            r = requests.post(f"{API}/leads/{lid}/action", json=act, headers=_hdr(tokens["owner"]))
            assert r.status_code == 403, f"OWNER should be 403 for {act['action']}, got {r.status_code}: {r.text}"

    def test_manager_also_forbidden(self, tokens):
        lid = _new_lead(tokens)
        r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"},
                          headers=_hdr(tokens["manager"]))
        assert r.status_code == 403


# --------- DISPATCH CONTINUITY ---------
class TestDispatchContinuity:
    def test_first_payment_revert_pending_does_not_stop_dispatch(self, tokens):
        _, ecp_id = _qualify(tokens, financing=False)
        _complete_all(ecp_id, "REGISTRATION_1", tokens["registration"])
        _complete_all(ecp_id, "ACCOUNTS_1", tokens["accounts"])
        # FIRST CONFIRMED
        r = requests.post(f"{API}/payments",
            json={"ecp_id": ecp_id, "type": "FIRST", "amount": 100, "date": "2026-09-10",
                  "status": "CONFIRMED"}, headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200, r.text
        pay_id = r.json()["id"]
        # start dispatch
        r = requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=_hdr(tokens["dispatch"]))
        assert r.status_code == 200
        e = r.json()["ecp"]
        assert e["dispatch_started"] is True
        assert e["derived_status"] == "DISPATCH_IN_PROCESS"
        # revert FIRST to PENDING
        r = requests.patch(f"{API}/payments/{pay_id}",
            json={"status": "PENDING"}, headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200
        # dispatch must remain in progress
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["owner"])).json()["ecp"]
        assert e["current_stage"] == "DISPATCH"
        assert e["dispatch_started"] is True
        assert e["derived_status"] == "DISPATCH_IN_PROCESS", \
            f"Dispatch should not revert; derived={e['derived_status']}"


# --------- FINANCING RBAC ---------
class TestFinancingRBAC:
    def test_only_lead_manager_owner_can_toggle(self, tokens):
        _, ecp_id = _qualify(tokens, financing=False)
        for role in ["registration", "accounts", "dispatch", "installation"]:
            r = requests.post(f"{API}/ecps/{ecp_id}/financing",
                json={"financing_required": True}, headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} must be 403"
        for role in ["lead", "manager", "owner"]:
            r = requests.post(f"{API}/ecps/{ecp_id}/financing",
                json={"financing_required": True}, headers=_hdr(tokens[role]))
            assert r.status_code == 200, f"{role}: {r.text}"


# --------- USERS/SLA OWNER-ONLY ---------
class TestOwnerOnlyEndpoints:
    def test_users_owner_only(self, tokens):
        for role in ["manager", "lead", "registration", "accounts", "dispatch", "installation"]:
            r = requests.get(f"{API}/users", headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} GET /users must be 403"
            r = requests.post(f"{API}/users",
                json={"username": "x_" + uuid.uuid4().hex[:4], "password": "p", "name": "x", "role": "LEAD", "phone": "9999999999"},
                headers=_hdr(tokens[role]))
            assert r.status_code == 403
        r = requests.get(f"{API}/users", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200

    def test_sla_put_owner_only(self, tokens):
        for role in ["manager", "lead", "registration", "accounts", "dispatch", "installation"]:
            r = requests.put(f"{API}/sla", json={"config": {"REGISTRATION_1": 3}},
                             headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} PUT /sla must be 403"


# --------- TASK COMPLETION WRONG TEAM ---------
class TestTaskRBAC:
    def test_registration_cannot_complete_accounts_task(self, tokens):
        _, ecp_id = _qualify(tokens)
        _complete_all(ecp_id, "REGISTRATION_1", tokens["registration"])
        # ecp now in ACCOUNTS_1, get task
        r = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["owner"]))
        acct_task = next(t for t in r.json()["tasks"] if t["stage"] == "ACCOUNTS_1")
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{acct_task['id']}/complete",
                          headers=_hdr(tokens["registration"]))
        assert r.status_code == 403


# --------- ESCALATIONS MANAGER 403 ---------
class TestEscalationsAccess:
    def test_manager_cannot_list_or_return(self, tokens):
        r = requests.get(f"{API}/escalations", headers=_hdr(tokens["manager"]))
        assert r.status_code == 403
        # Create an escalation to try return
        lid = _new_lead(tokens)
        requests.post(f"{API}/leads/{lid}/action",
            json={"action": "ESCALATION", "reason": "r", "remarks": "x"},
            headers=_hdr(tokens["lead"]))
        escs = requests.get(f"{API}/escalations", headers=_hdr(tokens["owner"])).json()
        esc = next(e for e in escs if e["lead_id"] == lid and e["status"] == "OPEN")
        r = requests.post(f"{API}/escalations/{esc['id']}/return",
            json={"owner_remarks": "hi"}, headers=_hdr(tokens["manager"]))
        assert r.status_code == 403


# --------- SITE VISIT: only assignee INSTALLATION can complete ---------
class TestSiteVisitAssigneeOnly:
    def test_installation_cannot_complete_others_visit(self, tokens):
        # Ensure a 2nd installation user exists via OWNER
        uname = "install2_" + uuid.uuid4().hex[:4]
        r = requests.post(f"{API}/users",
            json={"username": uname, "password": "Pass@123", "name": "Install Two", "role": "INSTALLATION", "phone": "9000000002"},
            headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        install2 = r.json()
        install2_tok = _login(uname, "Pass@123")["token"]

        # create lead + site visit + assign to install2
        lid = _new_lead(tokens)
        requests.post(f"{API}/leads/{lid}/action",
            json={"action": "SITE_VISIT", "remarks": "pls"}, headers=_hdr(tokens["lead"]))
        vs = requests.get(f"{API}/site-visits", headers=_hdr(tokens["manager"])).json()
        sv = next(v for v in vs if v["lead_id"] == lid and v["status"] == "REQUESTED")
        r = requests.post(f"{API}/site-visits/{sv['id']}/assign",
            json={"assigned_user": install2["id"], "visit_date": "2027-01-20"},
            headers=_hdr(tokens["instmgr"]))
        assert r.status_code == 200
        # default installation user (not assignee) tries to complete (send valid survey to bypass 422)
        r = requests.post(f"{API}/site-visits/{sv['id']}/complete",
            json={"structure_height": "h", "earthing_cable_length": "1",
                  "dc_cable_length": "2", "ac_cable_length": "3", "surveyor_name": "Hax"},
            headers=_hdr(tokens["installation"]))
        assert r.status_code == 403
        # assignee completes OK (with structured survey)
        r = requests.post(f"{API}/site-visits/{sv['id']}/complete",
            json={"structure_height": "10ft", "earthing_cable_length": "20m",
                  "dc_cable_length": "30m", "ac_cable_length": "40m",
                  "surveyor_name": "S"}, headers=_hdr(install2_tok))
        assert r.status_code == 200
