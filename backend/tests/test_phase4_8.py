"""Phase 4-8 acceptance tests.

Covers:
- Phase 4 Registration new tasks (REG1 base 3, +3 loan, REG2 Asset/Completion/Bank2nd)
- Phase 4 Net Metering chain (4 reg tasks + Close NM by installation member)
- Phase 5 Dispatch segregation (scrub project_price/payments) + Delivery Challan
- Phase 6 Installation new roles + 5-photo submit + accept/reject
- Phase 7 Site Visit structured survey + INSTALLATION_MANAGER assign
- Phase 8 Complaints (categories, SLA, workflow, RBAC, attachments)
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
    "owner":        ("anoopdube07@gmail.com", "Owner@123"),
    "manager":      ("manager",               "Manager@123"),
    "lead":         ("lead",                  "Lead@123"),
    "registration": ("registration",          "Reg@123"),
    "accounts":     ("accounts",              "Acct@123"),
    "dispatch":     ("dispatch",              "Disp@123"),
    "installation": ("installation",          "Install@123"),
    "instmgr":      ("instmgr",               "InstMgr@123"),
    "instmem":      ("instmem",               "InstMem@123"),
    "complaint":    ("complaint",             "Comp@123"),
}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 128


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    return {k: _login(u, p) for k, (u, p) in CREDS.items()}


# -------- helpers --------
def _new_lead(tok, financing=False, project_price=None):
    payload = {"name": f"TEST_P4_{uuid.uuid4().hex[:6]}",
               "phone": f"9{uuid.uuid4().int % 1000000000:09d}",
               "financing_required": financing}
    if project_price:
        payload["project_price"] = project_price
    r = requests.post(f"{API}/leads", json=payload, headers=H(tok))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _upload_doc(tokens, lid, t):
    for _ in range(4):
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": t},
                          files={"file": ("d.png", PNG, "image/png")}, headers=H(tokens["lead"]))
        if r.status_code == 200:
            return r
    return r


def _release(tokens, lid, financing=False):
    types = ["PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK"]
    if financing:
        types.append("PROPERTY_PAPER")
    for t in types:
        r = _upload_doc(tokens, lid, t)
        assert r.status_code == 200, f"{t}: {r.text}"


def _qualify(tokens, financing=False, price=None):
    lid = _new_lead(tokens["lead"], financing=financing, project_price=price)
    r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=H(tokens["lead"]))
    ecp_id = r.json()["ecp"]["id"]
    _release(tokens, lid, financing)
    return lid, ecp_id


def _tasks(tokens, ecp_id):
    return requests.get(f"{API}/ecps/{ecp_id}", headers=H(tokens["owner"])).json()["tasks"]


def _complete_stage(tokens, ecp_id, stage, tok_key):
    for t in _tasks(tokens, ecp_id):
        if t["stage"] == stage and t["applicable"] and not t["completed"]:
            r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{t['id']}/complete", headers=H(tokens[tok_key]))
            assert r.status_code == 200, f"{t['task_name']}: {r.text}"


def _finish_install(tokens, ecp_id, member_tok):
    requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "start"}, headers=H(member_tok))
    for t in ["INVERTER_SERIAL", "INVERTER_WITH_CUSTOMER", "PANEL_WITH_CUSTOMER",
              "LIGHTNING_ARRESTER", "EARTHING_PIT"]:
        rr = requests.post(f"{API}/ecps/{ecp_id}/install-photos", data={"photo_type": t},
                           files={"file": ("p.png", PNG, "image/png")}, headers=H(member_tok))
        assert rr.status_code == 200, rr.text
    r = requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "submit"}, headers=H(member_tok))
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/ecps/{ecp_id}/installation/accept", json={}, headers=H(tokens["instmgr"]))
    assert r.status_code == 200, r.text


def _to_installation(tokens, financing=False, price=1_000_000):
    _, ecp_id = _qualify(tokens, financing=financing, price=price)
    _complete_stage(tokens, ecp_id, "REGISTRATION_1", "registration")
    _complete_stage(tokens, ecp_id, "ACCOUNTS_1", "accounts")
    requests.post(f"{API}/payments",
        json={"ecp_id": ecp_id, "type": "FIRST", "amount": 10000, "date": "2026-09-01", "status": "CONFIRMED"},
        headers=H(tokens["accounts"]))
    requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=H(tokens["dispatch"]))
    _complete_stage(tokens, ecp_id, "DISPATCH", "dispatch")
    return ecp_id


# ================== Phase 4: REGISTRATION ==================
class TestPhase4Registration:
    def test_reg1_base_3_no_finance(self, tokens):
        _, ecp_id = _qualify(tokens, financing=False)
        reg1 = [t for t in _tasks(tokens, ecp_id) if t["stage"] == "REGISTRATION_1"]
        applicable = [t for t in reg1 if t["applicable"]]
        names = {t["task_name"] for t in applicable}
        assert names == {"Consumer Request", "CVA Print & Sign", "Feasibility Report Upload"}, names

    def test_reg1_finance_6(self, tokens):
        _, ecp_id = _qualify(tokens, financing=True)
        reg1 = [t for t in _tasks(tokens, ecp_id) if t["stage"] == "REGISTRATION_1"]
        applicable = [t for t in reg1 if t["applicable"]]
        names = {t["task_name"] for t in applicable}
        assert names == {"Consumer Request", "CVA Print & Sign", "Feasibility Report Upload",
                         "Loan Documentation", "Loan Filing", "Bank Submission"}


# ================== Phase 4: NET METERING ==================
class TestPhase4NetMetering:
    def test_nm_chain_and_close(self, tokens):
        ecp_id = _to_installation(tokens)
        # assign to instmem
        users = requests.get(f"{API}/users", headers=H(tokens["owner"])).json()
        instmem = next(u for u in users if u["username"] == "instmem")
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": instmem["id"]}, headers=H(tokens["instmgr"]))
        assert r.status_code == 200, r.text
        _finish_install(tokens, ecp_id, tokens["instmem"])
        # Now in NET_METERING
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=H(tokens["owner"])).json()["ecp"]
        assert e["current_stage"] == "NET_METERING", e["current_stage"]
        nm = [t for t in _tasks(tokens, ecp_id) if t["stage"] == "NET_METERING"]
        tmap = {t["task_name"]: t for t in nm}
        # DCR before Upload -> 400
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['DCR Issuance']['id']}/complete",
                          headers=H(tokens["registration"]))
        assert r.status_code == 400
        # Close NM before Request NM -> 400
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Close Net Metering']['id']}/complete",
                          headers=H(tokens["instmem"]))
        assert r.status_code == 400
        # Chain
        for name in ["Upload Installation Photos to CSPDCL Portal", "DCR Issuance",
                     "Consumer Approval & Submit", "Request Net Metering from CSPDCL"]:
            r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap[name]['id']}/complete",
                              headers=H(tokens["registration"]))
            assert r.status_code == 200, f"{name}: {r.text}"
        # Registration cannot close NM (INSTALLATION_MEMBER task)
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Close Net Metering']['id']}/complete",
                          headers=H(tokens["registration"]))
        assert r.status_code == 403
        # Close by member
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Close Net Metering']['id']}/complete",
                          headers=H(tokens["instmem"]))
        assert r.status_code == 200, r.text
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=H(tokens["owner"])).json()["ecp"]
        assert e["current_stage"] == "REGISTRATION_2"

    def test_reg2_tasks_and_bank2nd(self, tokens):
        # Non-financing: no Bank Submission 2nd applicable
        ecp_id = _to_installation(tokens, financing=False)
        users = requests.get(f"{API}/users", headers=H(tokens["owner"])).json()
        instmem = next(u for u in users if u["username"] == "instmem")
        requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": instmem["id"]}, headers=H(tokens["instmgr"]))
        _finish_install(tokens, ecp_id, tokens["instmem"])
        # Run NM
        nm = {t["task_name"]: t for t in _tasks(tokens, ecp_id) if t["stage"] == "NET_METERING"}
        for name in ["Upload Installation Photos to CSPDCL Portal", "DCR Issuance",
                     "Consumer Approval & Submit", "Request Net Metering from CSPDCL"]:
            requests.post(f"{API}/ecps/{ecp_id}/tasks/{nm[name]['id']}/complete", headers=H(tokens["registration"]))
        requests.post(f"{API}/ecps/{ecp_id}/tasks/{nm['Close Net Metering']['id']}/complete", headers=H(tokens["instmem"]))
        # REG2
        reg2 = [t for t in _tasks(tokens, ecp_id) if t["stage"] == "REGISTRATION_2"]
        tmap = {t["task_name"]: t for t in reg2}
        # Completion Certificate before Asset Creation -> 400
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Completion Certificate']['id']}/complete",
                          headers=H(tokens["registration"]))
        assert r.status_code == 400
        # Bank Submission 2nd NOT applicable (finance NO)
        assert tmap["Bank Submission 2nd"]["applicable"] is False


# ================== Phase 5: DISPATCH ==================
class TestPhase5Dispatch:
    def test_dispatch_scrubs_project_price_and_payments(self, tokens):
        _, ecp_id = _qualify(tokens, price=500000)
        _complete_stage(tokens, ecp_id, "REGISTRATION_1", "registration")
        _complete_stage(tokens, ecp_id, "ACCOUNTS_1", "accounts")
        # Dispatch GET /ecps
        rows = requests.get(f"{API}/ecps", headers=H(tokens["dispatch"])).json()
        row = next((r for r in rows if r["id"] == ecp_id), None)
        assert row is not None
        assert "project_price" not in row
        # GET /ecps/{id}
        detail = requests.get(f"{API}/ecps/{ecp_id}", headers=H(tokens["dispatch"])).json()
        assert "project_price" not in detail["ecp"]
        assert detail.get("payments") == [] or detail.get("payments") is None
        # visible fields
        assert "item_name" in detail["ecp"] or "customer_phone" in detail["ecp"]

    def test_dispatch_cannot_read_payments_monitor(self, tokens):
        r = requests.get(f"{API}/payments/monitor", headers=H(tokens["dispatch"]))
        assert r.status_code == 403

    def test_delivery_challan_flow(self, tokens):
        _, ecp_id = _qualify(tokens, price=500000)
        _complete_stage(tokens, ecp_id, "REGISTRATION_1", "registration")
        _complete_stage(tokens, ecp_id, "ACCOUNTS_1", "accounts")
        # Ensure active item exists
        items = requests.get(f"{API}/items?active_only=true", headers=H(tokens["owner"])).json()
        if not items:
            r = requests.post(f"{API}/items",
                json={"name": "Solar Panel 550W", "unit": "pcs"}, headers=H(tokens["owner"]))
            assert r.status_code == 200, r.text
            items = [r.json()]
        item = items[0]
        # Dispatch creates draft
        r = requests.post(f"{API}/ecps/{ecp_id}/challan",
            json={"items": [{"item_id": item["id"], "item_name": item["name"],
                             "unit": item.get("unit", "pcs"), "quantity": 5}]},
            headers=H(tokens["dispatch"]))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "DRAFT"
        # Finalize
        r = requests.post(f"{API}/ecps/{ecp_id}/challan/finalize", headers=H(tokens["dispatch"]))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "FINALIZED"
        # Accounts can list
        r = requests.get(f"{API}/challans", headers=H(tokens["accounts"]))
        assert r.status_code == 200
        assert any(c["ecp_id"] == ecp_id for c in r.json())
        # Dispatch cannot GET /challans
        r = requests.get(f"{API}/challans", headers=H(tokens["dispatch"]))
        assert r.status_code == 403


# ================== Phase 6: INSTALLATION ==================
class TestPhase6Installation:
    def test_rbac_and_5_photos_and_reject_flow(self, tokens):
        ecp_id = _to_installation(tokens)
        users = requests.get(f"{API}/users", headers=H(tokens["owner"])).json()
        instmem = next(u for u in users if u["username"] == "instmem")
        # RBAC: LEAD cannot assign
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": instmem["id"]}, headers=H(tokens["lead"]))
        assert r.status_code == 403
        # INSTALLATION_MANAGER assigns
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": instmem["id"]}, headers=H(tokens["instmgr"]))
        assert r.status_code == 200
        # non-assigned member (installation) cannot start
        r = requests.post(f"{API}/ecps/{ecp_id}/installation",
            json={"action": "start"}, headers=H(tokens["installation"]))
        assert r.status_code == 403
        # assignee starts
        r = requests.post(f"{API}/ecps/{ecp_id}/installation",
            json={"action": "start"}, headers=H(tokens["instmem"]))
        assert r.status_code == 200
        # Submit with <5 photos -> 400
        # upload 2 photos
        for t in ["INVERTER_SERIAL", "INVERTER_WITH_CUSTOMER"]:
            requests.post(f"{API}/ecps/{ecp_id}/install-photos", data={"photo_type": t},
                          files={"file": ("p.png", PNG, "image/png")}, headers=H(tokens["instmem"]))
        r = requests.post(f"{API}/ecps/{ecp_id}/installation",
            json={"action": "submit"}, headers=H(tokens["instmem"]))
        assert r.status_code == 400
        # Registration cannot download un-approved
        pdata = requests.get(f"{API}/ecps/{ecp_id}/install-photos", headers=H(tokens["registration"])).json()
        photos = pdata.get("photos", pdata) if isinstance(pdata, dict) else pdata
        # only approved shown -> empty at this point
        assert all(p.get("status") == "APPROVED" for p in photos)
        # Upload rest and submit
        for t in ["PANEL_WITH_CUSTOMER", "LIGHTNING_ARRESTER", "EARTHING_PIT"]:
            requests.post(f"{API}/ecps/{ecp_id}/install-photos", data={"photo_type": t},
                          files={"file": ("p.png", PNG, "image/png")}, headers=H(tokens["instmem"]))
        r = requests.post(f"{API}/ecps/{ecp_id}/installation",
            json={"action": "submit"}, headers=H(tokens["instmem"]))
        assert r.status_code == 200, r.text
        # Reject without remarks -> 400
        r = requests.post(f"{API}/ecps/{ecp_id}/installation/reject", json={}, headers=H(tokens["instmgr"]))
        assert r.status_code == 400
        # Reject with remarks
        r = requests.post(f"{API}/ecps/{ecp_id}/installation/reject",
            json={"remarks": "redo panel photo"}, headers=H(tokens["instmgr"]))
        assert r.status_code == 200, r.text
        # Member re-uploads and resubmits
        for t in ["INVERTER_SERIAL", "INVERTER_WITH_CUSTOMER", "PANEL_WITH_CUSTOMER",
                  "LIGHTNING_ARRESTER", "EARTHING_PIT"]:
            requests.post(f"{API}/ecps/{ecp_id}/install-photos", data={"photo_type": t},
                          files={"file": ("p.png", PNG, "image/png")}, headers=H(tokens["instmem"]))
        r = requests.post(f"{API}/ecps/{ecp_id}/installation",
            json={"action": "submit"}, headers=H(tokens["instmem"]))
        assert r.status_code == 200, r.text
        # Manager accepts
        r = requests.post(f"{API}/ecps/{ecp_id}/installation/accept", json={}, headers=H(tokens["instmgr"]))
        assert r.status_code == 200
        # Registration can now see approved photos
        pdata = requests.get(f"{API}/ecps/{ecp_id}/install-photos", headers=H(tokens["registration"])).json()
        photos = pdata.get("photos", pdata) if isinstance(pdata, dict) else pdata
        assert len(photos) >= 5


# ================== Phase 7: SITE VISIT ==================
class TestPhase7SiteVisit:
    def test_structured_survey_and_manager_only(self, tokens):
        lid = _new_lead(tokens["lead"])
        r = requests.post(f"{API}/leads/{lid}/action",
            json={"action": "SITE_VISIT", "remarks": "pls"}, headers=H(tokens["lead"]))
        assert r.status_code == 200
        vs = requests.get(f"{API}/site-visits", headers=H(tokens["instmgr"])).json()
        sv = next(v for v in vs if v["lead_id"] == lid and v["status"] == "REQUESTED")
        users = requests.get(f"{API}/users", headers=H(tokens["owner"])).json()
        instmem = next(u for u in users if u["username"] == "instmem")
        # process MANAGER cannot assign
        r = requests.post(f"{API}/site-visits/{sv['id']}/assign",
            json={"assigned_user": instmem["id"], "visit_date": "2027-01-20"},
            headers=H(tokens["manager"]))
        assert r.status_code == 403
        # INSTALLATION_MANAGER can
        r = requests.post(f"{API}/site-visits/{sv['id']}/assign",
            json={"assigned_user": instmem["id"], "visit_date": "2027-01-20"},
            headers=H(tokens["instmgr"]))
        assert r.status_code == 200
        # Missing surveyor_name -> 400
        r = requests.post(f"{API}/site-visits/{sv['id']}/complete",
            json={"structure_height": "10", "earthing_cable_length": "5",
                  "dc_cable_length": "10", "ac_cable_length": "8", "surveyor_name": ""},
            headers=H(tokens["instmem"]))
        assert r.status_code == 400
        # Extra material with inactive item -> 400
        r = requests.post(f"{API}/site-visits/{sv['id']}/complete",
            json={"structure_height": "10", "earthing_cable_length": "5",
                  "dc_cable_length": "10", "ac_cable_length": "8", "surveyor_name": "Alice",
                  "extra_materials": [{"item_id": "nonexistent-id", "item_name": "X", "unit": "pcs", "quantity": 1}]},
            headers=H(tokens["instmem"]))
        assert r.status_code == 400
        # Success
        r = requests.post(f"{API}/site-visits/{sv['id']}/complete",
            json={"structure_height": "10ft", "earthing_cable_length": "5m",
                  "dc_cable_length": "10m", "ac_cable_length": "8m", "surveyor_name": "Alice"},
            headers=H(tokens["instmem"]))
        assert r.status_code == 200, r.text
        lead = requests.get(f"{API}/leads/{lid}", headers=H(tokens["lead"])).json()["lead"]
        assert lead["status"] == "PENDING"
        assert lead["action_required"] is True
        assert lead["current_team"] == "LEAD"


# ================== Phase 8: COMPLAINTS ==================
@pytest.fixture(scope="module")
def category(tokens):
    name = f"TEST_CAT_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/complaint-categories", json={"name": name}, headers=H(tokens["owner"]))
    assert r.status_code == 200, r.text
    return r.json()


class TestPhase8Complaints:
    def test_category_duplicate_409(self, tokens, category):
        r = requests.post(f"{API}/complaint-categories",
            json={"name": category["name"]}, headers=H(tokens["owner"]))
        assert r.status_code == 409

    def test_sla_set_and_workflow(self, tokens, category):
        # Set SLA
        cfg = {f"{category['id']}|HIGH": 3}
        r = requests.put(f"{API}/complaint-sla", json={"config": cfg}, headers=H(tokens["owner"]))
        assert r.status_code == 200
        # Complaint role registers
        r = requests.post(f"{API}/complaints",
            json={"title": "TEST inverter noise", "category_id": category["id"], "priority": "HIGH",
                  "customer_name": "X", "customer_phone": "9999999999"},
            headers=H(tokens["complaint"]))
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["status"] == "REGISTERED"
        assert c["sla_due_date"] is not None
        cid = c["id"]
        # Missing priority -> 400
        r = requests.post(f"{API}/complaints",
            json={"title": "T", "category_id": category["id"], "priority": ""},
            headers=H(tokens["complaint"]))
        assert r.status_code == 400
        # Manager assigns
        users = requests.get(f"{API}/users", headers=H(tokens["owner"])).json()
        instmem = next(u for u in users if u["username"] == "instmem")
        r = requests.post(f"{API}/complaints/{cid}/assign",
            json={"assigned_team": "INSTALLATION", "assigned_user": instmem["id"]},
            headers=H(tokens["manager"]))
        assert r.status_code == 200
        assert r.json()["status"] == "ASSIGNED"
        # Non-assignee accounts -> 403 on GET
        r = requests.get(f"{API}/complaints/{cid}", headers=H(tokens["accounts"]))
        assert r.status_code == 403
        # Non-assignee cannot set IN_PROGRESS
        r = requests.post(f"{API}/complaints/{cid}/status",
            json={"status": "IN_PROGRESS"}, headers=H(tokens["accounts"]))
        assert r.status_code == 403
        # Assignee sets IN_PROGRESS
        r = requests.post(f"{API}/complaints/{cid}/status",
            json={"status": "IN_PROGRESS"}, headers=H(tokens["instmem"]))
        assert r.status_code == 200, r.text
        # Assignee RESOLVED
        r = requests.post(f"{API}/complaints/{cid}/status",
            json={"status": "RESOLVED"}, headers=H(tokens["instmem"]))
        assert r.status_code == 200
        # Member cannot CLOSE
        r = requests.post(f"{API}/complaints/{cid}/status",
            json={"status": "CLOSED"}, headers=H(tokens["instmem"]))
        assert r.status_code == 403
        # Manager CLOSED
        r = requests.post(f"{API}/complaints/{cid}/status",
            json={"status": "CLOSED"}, headers=H(tokens["manager"]))
        assert r.status_code == 200
        assert r.json()["status"] == "CLOSED"

    def test_no_ecp_allowed_and_attachment(self, tokens, category):
        r = requests.post(f"{API}/complaints",
            json={"title": "TEST no ecp", "category_id": category["id"], "priority": "LOW"},
            headers=H(tokens["complaint"]))
        assert r.status_code == 200
        cid = r.json()["id"]
        # attachment upload (PNG)
        for _ in range(3):
            r = requests.post(f"{API}/complaints/{cid}/attachments",
                files={"file": ("a.png", PNG, "image/png")}, headers=H(tokens["complaint"]))
            if r.status_code == 200:
                break
        assert r.status_code == 200, r.text
        # Unsupported ext -> 400
        r = requests.post(f"{API}/complaints/{cid}/attachments",
            files={"file": ("a.exe", b"x", "application/octet-stream")}, headers=H(tokens["complaint"]))
        assert r.status_code == 400
