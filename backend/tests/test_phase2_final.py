"""Phase 2 FINAL ACCEPTANCE: post-handoff lead edit propagation, commercial-change ECP sync,
ECP carries item/contact at creation, workflow safe, RBAC. Independent of test_phase2.py."""
import os
import uuid
import pytest
import requests

BASE_URL = None
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = (BASE_URL or "").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "owner":        ("anoopdube07@gmail.com", "Owner@123"),
    "manager":      ("manager", "Manager@123"),
    "lead":         ("lead", "Lead@123"),
    "registration": ("registration", "Reg@123"),
    "accounts":     ("accounts", "Acct@123"),
    "dispatch":     ("dispatch", "Disp@123"),
    "installation": ("installation", "Install@123"),
}


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text}"
    return r.json()["token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="session")
def tokens():
    return {k: _login(u, p) for k, (u, p) in CREDS.items()}


@pytest.fixture(scope="session", autouse=True)
def _reset_fc(tokens):
    requests.put(f"{API}/lead-field-config", json={"fields": {}}, headers=_hdr(tokens["owner"]))
    yield
    requests.put(f"{API}/lead-field-config", json={"fields": {}}, headers=_hdr(tokens["owner"]))


def _make_item(tokens):
    name = f"TEST_FINAL_ITEM_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/items", json={"name": name, "unit": "kW"}, headers=_hdr(tokens["owner"]))
    assert r.status_code == 200, r.text
    return r.json()["id"], name


def _phone():
    return f"95{uuid.uuid4().int % 100000000:08d}"


def _make_lead(tokens, **extra):
    payload = {"name": f"TEST_FINAL_LEAD_{uuid.uuid4().hex[:6]}", "phone": _phone(), **extra}
    r = requests.post(f"{API}/leads", json=payload, headers=_hdr(tokens["lead"]))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _qualify(tokens, lid):
    r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tokens["lead"]))
    assert r.status_code == 200, r.text
    lead = requests.get(f"{API}/leads/{lid}", headers=_hdr(tokens["lead"])).json()["lead"]
    return lead["ecp_id"]


# ============ 1. POST-HANDOFF EDIT (non-commercial) + PROPAGATION ============
class TestPostHandoffEditPropagation:
    def test_patch_email_address_location_persists_on_lead(self, tokens):
        iid, _ = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=3, location_link="http://old/x",
                         project_price=50000, email="old@x.com", address="Old Addr")
        ecp_id = _qualify(tokens, lid)

        new = {"email": "new@example.com", "address": "New Address 42",
               "location_link": "http://maps.example/new"}
        r = requests.patch(f"{API}/leads/{lid}", json=new, headers=_hdr(tokens["lead"]))
        assert r.status_code == 200, r.text
        lead = r.json()["lead"]
        for k, v in new.items():
            assert lead[k] == v, f"lead[{k}] expected {v}, got {lead.get(k)}"

        # Also verify with fresh GET
        lead2 = requests.get(f"{API}/leads/{lid}", headers=_hdr(tokens["lead"])).json()["lead"]
        for k, v in new.items():
            assert lead2[k] == v

    def test_patch_propagates_to_ecp(self, tokens):
        iid, iname = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=4,
                         location_link="http://old", email="a@a.com", address="A")
        ecp_id = _qualify(tokens, lid)

        new = {"email": "z@z.com", "address": "Z-Addr", "location_link": "http://maps/z"}
        r = requests.patch(f"{API}/leads/{lid}", json=new, headers=_hdr(tokens["lead"]))
        assert r.status_code == 200

        ecp = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["lead"])).json()
        # ecp may be under 'ecp' key or root
        ecp = ecp.get("ecp", ecp)
        assert ecp["customer_email"] == "z@z.com"
        assert ecp["customer_address"] == "Z-Addr"
        assert ecp["location_link"] == "http://maps/z"


# ============ 2. COMMERCIAL FIELDS BLOCKED ON DIRECT API ============
class TestCommercialBlocked:
    def test_patch_ignores_commercial_fields(self, tokens):
        iid, iname = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=3, project_price=50000)
        _qualify(tokens, lid)
        # Try to smuggle commercial fields
        r = requests.patch(f"{API}/leads/{lid}",
                           json={"item_id": "hacker", "quantity": 999, "project_price": 999999,
                                 "email": "keep@x.com"},
                           headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        lead = r.json()["lead"]
        # commercial unchanged
        assert lead["item_id"] == iid
        assert lead["quantity"] == 3
        assert lead["project_price"] == 50000
        # non-commercial updated
        assert lead["email"] == "keep@x.com"

    def test_direct_project_price_400_post_handoff(self, tokens):
        lid = _make_lead(tokens)
        _qualify(tokens, lid)
        r = requests.post(f"{API}/leads/{lid}/project-price", json={"project_price": 77777},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 400
        assert "commercial" in r.text.lower()


# ============ 3. COMMERCIAL CHANGE -> APPROVE PROPAGATES TO ECP ============
class TestCommercialApproveEcpSync:
    def test_approve_syncs_ecp_item_qty_price(self, tokens):
        iid1, _ = _make_item(tokens)
        iid2, name2 = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid1, quantity=2, project_price=30000)
        ecp_id = _qualify(tokens, lid)

        r = requests.post(f"{API}/leads/{lid}/commercial-change",
                          json={"item_id": iid2, "quantity": 9, "project_price": 111111},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 200

        r2 = requests.post(f"{API}/leads/{lid}/commercial-change/approve",
                           json={"remarks": "ok"}, headers=_hdr(tokens["owner"]))
        assert r2.status_code == 200

        ecp = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["owner"])).json()
        ecp = ecp.get("ecp", ecp)
        assert ecp["item_id"] == iid2
        assert ecp["item_name"] == name2
        assert ecp["item_unit"] == "kW"
        assert ecp["quantity"] == 9
        assert ecp["project_price"] == 111111

    def test_reject_no_remarks_400_then_with_remarks_unchanged(self, tokens):
        iid, _ = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=5, project_price=44444)
        ecp_id = _qualify(tokens, lid)
        requests.post(f"{API}/leads/{lid}/commercial-change",
                      json={"project_price": 99999}, headers=_hdr(tokens["lead"]))
        r = requests.post(f"{API}/leads/{lid}/commercial-change/reject", json={},
                          headers=_hdr(tokens["owner"]))
        assert r.status_code == 400
        r2 = requests.post(f"{API}/leads/{lid}/commercial-change/reject",
                           json={"remarks": "No"}, headers=_hdr(tokens["owner"]))
        assert r2.status_code == 200
        lead = requests.get(f"{API}/leads/{lid}", headers=_hdr(tokens["lead"])).json()["lead"]
        assert lead["project_price"] == 44444
        assert lead["quantity"] == 5


# ============ 4. RBAC / OWNERSHIP ============
class TestRBAC:
    @pytest.fixture(scope="class")
    def other_lead_token(self, tokens):
        uname = f"lead_final_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/users",
                          json={"username": uname, "password": "Lead@123", "name": "Other Lead",
                                "role": "LEAD", "phone": f"9{uuid.uuid4().int % 1000000000:09d}"},
                          headers=_hdr(tokens["owner"]))
        assert r.status_code == 200, r.text
        return _login(uname, "Lead@123")

    def test_non_owner_lead_patch_403(self, tokens, other_lead_token):
        lid = _make_lead(tokens)
        r = requests.patch(f"{API}/leads/{lid}", json={"email": "h@h.com"},
                           headers=_hdr(other_lead_token))
        assert r.status_code == 403

    def test_non_owner_lead_commercial_change_403(self, tokens, other_lead_token):
        lid = _make_lead(tokens)
        _qualify(tokens, lid)
        r = requests.post(f"{API}/leads/{lid}/commercial-change",
                          json={"project_price": 1}, headers=_hdr(other_lead_token))
        assert r.status_code == 403

    def test_non_owner_roles_denied_approve_reject_pending(self, tokens):
        iid, _ = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=1, project_price=1)
        _qualify(tokens, lid)
        requests.post(f"{API}/leads/{lid}/commercial-change",
                      json={"project_price": 2}, headers=_hdr(tokens["lead"]))
        for role in ["manager", "lead", "accounts", "dispatch", "installation", "registration"]:
            assert requests.post(f"{API}/leads/{lid}/commercial-change/approve",
                                 json={}, headers=_hdr(tokens[role])).status_code == 403
            assert requests.post(f"{API}/leads/{lid}/commercial-change/reject",
                                 json={"remarks": "x"}, headers=_hdr(tokens[role])).status_code == 403
            assert requests.get(f"{API}/commercial-changes/pending",
                                headers=_hdr(tokens[role])).status_code == 403


# ============ 5. WORKFLOW FIELDS SAFE ============
class TestWorkflowSafe:
    def test_patch_cannot_change_status_or_stage_or_team(self, tokens):
        lid = _make_lead(tokens)
        before = requests.get(f"{API}/leads/{lid}", headers=_hdr(tokens["lead"])).json()["lead"]
        # try to smuggle
        r = requests.patch(f"{API}/leads/{lid}",
                           json={"status": "HACKED", "current_team": "OWNER", "stage": "END",
                                 "email": "safe@x.com"},
                           headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        after = r.json()["lead"]
        assert after.get("status") == before.get("status")
        assert after.get("current_team") == before.get("current_team")
        assert after.get("stage") == before.get("stage")
        assert after.get("email") == "safe@x.com"


# ============ 6. NEW ECP CARRIES ITEM/CONTACT AT CREATION ============
class TestEcpAtCreation:
    def test_new_ecp_carries_item_and_contact(self, tokens):
        iid, iname = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=6.5, project_price=88888,
                         location_link="http://maps/here", email="c@c.com",
                         address="Full Customer Address")
        ecp_id = _qualify(tokens, lid)

        ecp = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["lead"])).json()
        ecp = ecp.get("ecp", ecp)
        assert ecp["item_id"] == iid
        assert ecp["item_name"] == iname
        assert ecp["item_unit"] == "kW"
        assert ecp["quantity"] == 6.5
        assert ecp["project_price"] == 88888
        assert ecp["customer_email"] == "c@c.com"
        assert ecp["customer_address"] == "Full Customer Address"
        assert ecp["location_link"] == "http://maps/here"


# ============ 7. REGRESSION: core Phase-1 flows ============
class TestRegression:
    def test_all_role_logins(self):
        for k, (u, p) in CREDS.items():
            r = requests.post(f"{API}/auth/login", json={"username": u, "password": p})
            assert r.status_code == 200, f"{k} login failed: {r.text}"

    def test_lead_yes_creates_one_ecp(self, tokens):
        lid = _make_lead(tokens)
        r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        lead = requests.get(f"{API}/leads/{lid}", headers=_hdr(tokens["lead"])).json()["lead"]
        assert lead.get("ecp_id")
        # calling YES again should not create a duplicate ECP
        r2 = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"},
                          headers=_hdr(tokens["lead"]))
        # allowed or blocked either way; just ensure ecp_id stable
        lead2 = requests.get(f"{API}/leads/{lid}", headers=_hdr(tokens["lead"])).json()["lead"]
        assert lead2["ecp_id"] == lead["ecp_id"]

    def test_duplicate_active_phone_409(self, tokens):
        phone = _phone()
        p1 = {"name": f"TEST_DUP_A_{uuid.uuid4().hex[:6]}", "phone": phone}
        r1 = requests.post(f"{API}/leads", json=p1, headers=_hdr(tokens["lead"]))
        assert r1.status_code == 200
        p2 = {"name": f"TEST_DUP_B_{uuid.uuid4().hex[:6]}", "phone": phone}
        r2 = requests.post(f"{API}/leads", json=p2, headers=_hdr(tokens["lead"]))
        assert r2.status_code == 409

    def test_reassign_manager_owner_ok_others_403(self, tokens):
        lid = _make_lead(tokens)
        # get a lead user id
        users = requests.get(f"{API}/users", headers=_hdr(tokens["owner"])).json()
        lead_users = [u for u in users if u.get("role") == "LEAD"]
        assert lead_users
        target = lead_users[0]["id"]
        body = {"assigned_user": target}
        # manager
        r = requests.post(f"{API}/leads/{lid}/reassign", json=body,
                          headers=_hdr(tokens["manager"]))
        assert r.status_code in (200, 204), r.text
        # owner
        r2 = requests.post(f"{API}/leads/{lid}/reassign", json=body,
                           headers=_hdr(tokens["owner"]))
        assert r2.status_code in (200, 204)
        # non-owner role denied
        for role in ["accounts", "dispatch", "installation", "registration", "lead"]:
            r3 = requests.post(f"{API}/leads/{lid}/reassign", json=body,
                               headers=_hdr(tokens[role]))
            assert r3.status_code == 403, f"{role} reassign should 403 got {r3.status_code}"

    def test_ecp_dashboard_and_payments_monitor_load(self, tokens):
        r = requests.get(f"{API}/ecps", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        r2 = requests.get(f"{API}/payments/monitor", headers=_hdr(tokens["owner"]))
        assert r2.status_code == 200
