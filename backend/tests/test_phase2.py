"""Phase 2 backend tests: Item Master, mandatory field config, commercial change, quotation PDF."""
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
def _cleanup_field_config(tokens):
    """Ensure lead-field-config is empty before + after run so it doesn't block other tests."""
    requests.put(f"{API}/lead-field-config", json={"fields": {}}, headers=_hdr(tokens["owner"]))
    yield
    requests.put(f"{API}/lead-field-config", json={"fields": {}}, headers=_hdr(tokens["owner"]))


# =========================== ITEM MASTER ===========================
class TestItemMaster:
    def test_owner_create_item(self, tokens):
        name = f"TEST_ITEM_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/items", json={"name": name, "unit": "kW"}, headers=_hdr(tokens["owner"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == name and d["unit"] == "kW" and d["active"] is True

    def test_duplicate_name_unit_409(self, tokens):
        name = f"TEST_DUP_{uuid.uuid4().hex[:6]}"
        r1 = requests.post(f"{API}/items", json={"name": name, "unit": "kW"}, headers=_hdr(tokens["owner"]))
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/items", json={"name": name, "unit": "kW"}, headers=_hdr(tokens["owner"]))
        assert r2.status_code == 409

    def test_toggle_active(self, tokens):
        name = f"TEST_TOG_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/items", json={"name": name, "unit": "nos"}, headers=_hdr(tokens["owner"]))
        item_id = r.json()["id"]
        r2 = requests.patch(f"{API}/items/{item_id}", json={"active": False}, headers=_hdr(tokens["owner"]))
        assert r2.status_code == 200 and r2.json()["active"] is False
        r3 = requests.patch(f"{API}/items/{item_id}", json={"active": True}, headers=_hdr(tokens["owner"]))
        assert r3.json()["active"] is True

    def test_active_only_filter(self, tokens):
        name = f"TEST_AO_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/items", json={"name": name, "unit": "kW"}, headers=_hdr(tokens["owner"]))
        iid = r.json()["id"]
        requests.patch(f"{API}/items/{iid}", json={"active": False}, headers=_hdr(tokens["owner"]))
        items = requests.get(f"{API}/items?active_only=true", headers=_hdr(tokens["lead"])).json()
        assert not any(i["id"] == iid for i in items)

    def test_export_csv(self, tokens):
        r = requests.get(f"{API}/items/export", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert r.text.startswith("Item Name")

    def test_import_csv(self, tokens):
        unique = uuid.uuid4().hex[:6]
        rows = [
            {"name": f"TEST_IMP_A_{unique}", "unit": "kW"},
            {"name": f"TEST_IMP_A_{unique}", "unit": "kW"},  # dup in file
            {"name": f"TEST_IMP_B_{unique}", "unit": "nos"},
            {"name": "", "unit": "kW"},  # missing name
        ]
        r = requests.post(f"{API}/items/import", json={"rows": rows}, headers=_hdr(tokens["owner"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["created"] == 2
        assert len(d["errors"]) == 2

    def test_non_owner_denied(self, tokens):
        payload = {"name": f"TEST_NO_{uuid.uuid4().hex[:6]}", "unit": "kW"}
        r = requests.post(f"{API}/items", json=payload, headers=_hdr(tokens["lead"]))
        assert r.status_code == 403
        r = requests.get(f"{API}/items/export", headers=_hdr(tokens["lead"]))
        assert r.status_code == 403
        r = requests.post(f"{API}/items/import", json={"rows": []}, headers=_hdr(tokens["lead"]))
        assert r.status_code == 403


# =========================== LEAD FIELD CONFIG ===========================
class TestLeadFieldConfig:
    def test_owner_set_and_get(self, tokens):
        r = requests.put(f"{API}/lead-field-config", json={"fields": {"item": True, "quantity": True}},
                         headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert r.json()["fields"]["item"] is True

        r2 = requests.get(f"{API}/lead-field-config", headers=_hdr(tokens["lead"]))
        assert r2.status_code == 200
        assert r2.json()["fields"]["quantity"] is True

    def test_lead_missing_required_fields_400(self, tokens):
        requests.put(f"{API}/lead-field-config", json={"fields": {"item": True, "quantity": True}},
                     headers=_hdr(tokens["owner"]))
        payload = {"name": f"TEST_M_{uuid.uuid4().hex[:6]}", "phone": f"999{uuid.uuid4().int % 10000000:07d}"}
        r = requests.post(f"{API}/leads", json=payload, headers=_hdr(tokens["lead"]))
        assert r.status_code == 400
        assert "required" in r.text.lower()

    def test_lead_creation_after_reset(self, tokens):
        requests.put(f"{API}/lead-field-config", json={"fields": {}}, headers=_hdr(tokens["owner"]))
        payload = {"name": f"TEST_M2_{uuid.uuid4().hex[:6]}", "phone": f"988{uuid.uuid4().int % 10000000:07d}"}
        r = requests.post(f"{API}/leads", json=payload, headers=_hdr(tokens["lead"]))
        assert r.status_code == 200, r.text

    def test_non_owner_put_forbidden(self, tokens):
        r = requests.put(f"{API}/lead-field-config", json={"fields": {}}, headers=_hdr(tokens["lead"]))
        assert r.status_code == 403


# =========================== LEAD WITH ITEMS ===========================
def _make_item(tokens, active=True):
    name = f"TEST_LI_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/items", json={"name": name, "unit": "kW"}, headers=_hdr(tokens["owner"]))
    iid = r.json()["id"]
    if not active:
        requests.patch(f"{API}/items/{iid}", json={"active": False}, headers=_hdr(tokens["owner"]))
    return iid, name


def _make_lead(tokens, **extra):
    phone = f"977{uuid.uuid4().int % 10000000:07d}"
    payload = {"name": f"TEST_LEAD_{uuid.uuid4().hex[:6]}", "phone": phone, **extra}
    r = requests.post(f"{API}/leads", json=payload, headers=_hdr(tokens["lead"]))
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestLeadItemFields:
    def test_lead_create_stores_item_snapshot(self, tokens):
        iid, name = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=5.5, location_link="http://maps.example/x", project_price=100000)
        lead = requests.get(f"{API}/leads/{lid}", headers=_hdr(tokens["lead"])).json()["lead"]
        assert lead["item_id"] == iid
        assert lead["item_name"] == name
        assert lead["item_unit"] == "kW"
        assert lead["quantity"] == 5.5
        assert lead["location_link"] == "http://maps.example/x"
        assert lead["project_price"] == 100000

    def test_inactive_item_400(self, tokens):
        iid, _ = _make_item(tokens, active=False)
        payload = {"name": f"TEST_BAD_{uuid.uuid4().hex[:6]}",
                   "phone": f"966{uuid.uuid4().int % 10000000:07d}",
                   "item_id": iid}
        r = requests.post(f"{API}/leads", json=payload, headers=_hdr(tokens["lead"]))
        assert r.status_code == 400

    def test_nonexistent_item_400(self, tokens):
        payload = {"name": f"TEST_BAD_{uuid.uuid4().hex[:6]}",
                   "phone": f"955{uuid.uuid4().int % 10000000:07d}",
                   "item_id": "not-a-real-id"}
        r = requests.post(f"{API}/leads", json=payload, headers=_hdr(tokens["lead"]))
        assert r.status_code == 400


# =========================== PROJECT PRICE GATING ===========================
class TestProjectPriceGating:
    def test_pre_handoff_owner_can_set(self, tokens):
        lid = _make_lead(tokens)
        r = requests.post(f"{API}/leads/{lid}/project-price", json={"project_price": 55555},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        assert r.json()["lead"]["project_price"] == 55555

    def test_post_handoff_gated(self, tokens):
        lid = _make_lead(tokens)
        # qualify to trigger handoff (ecp created)
        r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        r2 = requests.post(f"{API}/leads/{lid}/project-price", json={"project_price": 77777},
                           headers=_hdr(tokens["lead"]))
        assert r2.status_code == 400
        assert "commercial" in r2.text.lower()


# =========================== LEAD EDIT POST-HANDOFF ===========================
class TestLeadEdit:
    def test_owner_can_patch_non_commercial(self, tokens):
        lid = _make_lead(tokens)
        requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tokens["lead"]))
        r = requests.patch(f"{API}/leads/{lid}",
                           json={"email": "new@example.com", "address": "New Addr", "location_link": "http://x/y"},
                           headers=_hdr(tokens["lead"]))
        assert r.status_code == 200, r.text
        lead = r.json()["lead"]
        assert lead["email"] == "new@example.com"
        assert lead["address"] == "New Addr"
        assert lead["location_link"] == "http://x/y"

    def test_non_owner_lead_forbidden(self, tokens):
        # a lead created by 'lead' user; simulate another LEAD user by creating one
        owner_hdr = _hdr(tokens["owner"])
        uname = f"lead2_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/users",
                          json={"username": uname, "password": "Lead2@123",
                                "name": "Lead Two", "role": "LEAD", "phone": "9000000000"},
                          headers=owner_hdr)
        assert r.status_code == 200, r.text
        tok2 = _login(uname, "Lead2@123")
        lid = _make_lead(tokens)  # owned by 'lead'
        r2 = requests.patch(f"{API}/leads/{lid}", json={"email": "hack@x.com"}, headers=_hdr(tok2))
        assert r2.status_code == 403


# =========================== COMMERCIAL CHANGE ===========================
class TestCommercialChange:
    def test_propose_approve_updates_ecp(self, tokens):
        iid1, _ = _make_item(tokens)
        iid2, name2 = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid1, quantity=3, project_price=50000)
        # qualify
        requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tokens["lead"]))
        # propose
        r = requests.post(f"{API}/leads/{lid}/commercial-change",
                          json={"item_id": iid2, "quantity": 7, "project_price": 90000},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 200, r.text
        lead = r.json()["lead"]
        assert lead["pending_commercial_change"]["status"] == "PENDING"

        # owner dashboard has pending_commercial > 0
        dash = requests.get(f"{API}/dashboard", headers=_hdr(tokens["owner"])).json()
        # accept either field name
        pc = dash.get("pending_commercial") or dash.get("pending_commercial_count") or 0
        assert pc >= 1, f"dashboard should show pending commercial, got: {dash}"

        pend = requests.get(f"{API}/commercial-changes/pending", headers=_hdr(tokens["owner"]))
        assert pend.status_code == 200
        assert any(l["id"] == lid for l in pend.json())

        # approve
        r2 = requests.post(f"{API}/leads/{lid}/commercial-change/approve",
                           json={"remarks": "ok"}, headers=_hdr(tokens["owner"]))
        assert r2.status_code == 200
        lead2 = r2.json()["lead"]
        assert lead2["item_id"] == iid2
        assert lead2["quantity"] == 7
        assert lead2["project_price"] == 90000
        # ecp updated
        ecp = r2.json()["ecp"]
        assert ecp["project_price"] == 90000

    def test_reject_without_remarks_400(self, tokens):
        iid, _ = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=2, project_price=10000)
        requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tokens["lead"]))
        requests.post(f"{API}/leads/{lid}/commercial-change",
                      json={"project_price": 20000}, headers=_hdr(tokens["lead"]))
        r = requests.post(f"{API}/leads/{lid}/commercial-change/reject",
                          json={}, headers=_hdr(tokens["owner"]))
        assert r.status_code == 400
        assert "remark" in r.text.lower()
        r2 = requests.post(f"{API}/leads/{lid}/commercial-change/reject",
                           json={"remarks": "Not approved"}, headers=_hdr(tokens["owner"]))
        assert r2.status_code == 200
        lead = r2.json()["lead"]
        assert lead["pending_commercial_change"]["status"] == "REJECTED"
        # commercial values UNCHANGED
        assert lead["project_price"] == 10000

    def test_rbac(self, tokens):
        iid, _ = _make_item(tokens)
        lid = _make_lead(tokens, item_id=iid, quantity=1, project_price=1000)
        requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tokens["lead"]))
        requests.post(f"{API}/leads/{lid}/commercial-change",
                      json={"project_price": 2000}, headers=_hdr(tokens["lead"]))
        # non-owner approve/reject/pending -> 403
        for role in ["manager", "lead", "accounts", "dispatch", "installation", "registration"]:
            r = requests.post(f"{API}/leads/{lid}/commercial-change/approve",
                              json={}, headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} approve should 403"
            r = requests.get(f"{API}/commercial-changes/pending", headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} pending list should 403"

    def test_lead_not_owner_proposes_403(self, tokens):
        # create second lead user
        uname = f"lead3_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/users",
                          json={"username": uname, "password": "Lead3@123",
                                "name": "Lead Three", "role": "LEAD", "phone": "9111111111"},
                          headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        tok2 = _login(uname, "Lead3@123")
        lid = _make_lead(tokens)
        r2 = requests.post(f"{API}/leads/{lid}/commercial-change",
                          json={"project_price": 5000}, headers=_hdr(tok2))
        assert r2.status_code == 403


# =========================== QUOTATION PDF ===========================
class TestQuotationPDF:
    def test_owner_lead_manager_can_download(self, tokens):
        lid = _make_lead(tokens)
        for role in ["lead", "manager", "owner"]:
            r = requests.get(f"{API}/leads/{lid}/quotation", headers=_hdr(tokens[role]))
            assert r.status_code == 200, f"{role}: {r.status_code}"
            assert "application/pdf" in r.headers.get("content-type", "")
            assert r.content[:4] == b"%PDF"

    def test_non_owner_lead_forbidden(self, tokens):
        uname = f"lead4_{uuid.uuid4().hex[:6]}"
        requests.post(f"{API}/users",
                      json={"username": uname, "password": "Lead4@123",
                            "name": "Lead Four", "role": "LEAD", "phone": "9222222222"},
                      headers=_hdr(tokens["owner"]))
        tok2 = _login(uname, "Lead4@123")
        lid = _make_lead(tokens)
        r = requests.get(f"{API}/leads/{lid}/quotation", headers=_hdr(tok2))
        assert r.status_code == 403

    def test_non_lead_roles_forbidden(self, tokens):
        lid = _make_lead(tokens)
        for role in ["accounts", "dispatch", "installation", "registration"]:
            r = requests.get(f"{API}/leads/{lid}/quotation", headers=_hdr(tokens[role]))
            assert r.status_code == 403
