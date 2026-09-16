import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
CREDS = {"owner": ("anoopdube07@gmail.com", "Owner@123"), "manager": ("manager", "Manager@123"),
         "lead": ("lead", "Lead@123"), "registration": ("registration", "Reg@123"),
         "accounts": ("accounts", "Acct@123"), "dispatch": ("dispatch", "Disp@123"),
         "instmgr": ("instmgr", "InstMgr@123"), "instmem": ("instmem", "InstMem@123"),
         "complaint": ("complaint", "Comp@123")}


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def tk():
    out = {}
    for k, (u, p) in CREDS.items():
        r = requests.post(f"{API}/auth/login", json={"username": u, "password": p})
        assert r.status_code == 200, f"login {u}: {r.text}"
        out[k] = r.json()["token"]
    out["instmem_id"] = requests.get(f"{API}/auth/me", headers=_hdr(out["instmem"])).json()["id"]
    return out


def _phone():
    return f"9{uuid.uuid4().int % 1000000000:09d}"


def _release_docs(lid, tk, finance=False):
    types = ["PAN", "AADHAAR", "ELECTRICITY_BILL"] + (["PROPERTY_PAPER"] if finance else []) + ["BANK_PASSBOOK"]
    for t in types:
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": t},
                          files={"file": ("d.png", PNG, "image/png")}, headers=_hdr(tk["lead"]))
        assert r.status_code == 200, f"doc {t}: {r.text}"


def _complete_stage(ecp_id, stage, tok, tk):
    tasks = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tk["owner"])).json()["tasks"]
    for t in [x for x in tasks if x["stage"] == stage and x["applicable"] and not x["completed"]]:
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{t['id']}/complete", headers=_hdr(tok))
        assert r.status_code == 200, f"{t['task_name']}: {r.text}"


def _to_installation(tk, finance=False):
    lid = requests.post(f"{API}/leads", json={"name": "P410", "phone": _phone(), "financing_required": finance,
                        "project_price": 500000}, headers=_hdr(tk["lead"])).json()["id"]
    requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tk["lead"]))
    _release_docs(lid, tk, finance)
    ecp_id = requests.get(f"{API}/leads/{lid}", headers=_hdr(tk["lead"])).json()["ecp"]["id"]
    _complete_stage(ecp_id, "REGISTRATION_1", tk["registration"], tk)
    _complete_stage(ecp_id, "ACCOUNTS_1", tk["accounts"], tk)
    # dispatch needs first payment confirmed
    p = requests.post(f"{API}/payments", json={"ecp_id": ecp_id, "type": "FIRST", "amount": 100,
                      "date": "2026-01-01", "status": "CONFIRMED"}, headers=_hdr(tk["accounts"])).json()
    requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=_hdr(tk["dispatch"]))
    _complete_stage(ecp_id, "DISPATCH", tk["dispatch"], tk)
    return lid, ecp_id


def _finish_install(ecp_id, tk):
    requests.post(f"{API}/ecps/{ecp_id}/assign-installation", json={"assigned_user": tk["instmem_id"]}, headers=_hdr(tk["instmgr"]))
    requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "start"}, headers=_hdr(tk["instmem"]))
    for t in ["INVERTER_SERIAL", "INVERTER_WITH_CUSTOMER", "PANEL_WITH_CUSTOMER", "LIGHTNING_ARRESTER", "EARTHING_PIT"]:
        requests.post(f"{API}/ecps/{ecp_id}/install-photos", data={"photo_type": t},
                      files={"file": ("p.png", PNG, "image/png")}, headers=_hdr(tk["instmem"]))
    requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "submit"}, headers=_hdr(tk["instmem"]))
    requests.post(f"{API}/ecps/{ecp_id}/installation/accept", json={}, headers=_hdr(tk["instmgr"]))


class TestJourneyInstallation:
    def test_installation_assign_photos_accept(self, tk):
        lid, ecp_id = _to_installation(tk)
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tk["owner"])).json()["ecp"]
        assert e["current_stage"] == "INSTALLATION" and e["install_status"] == "AWAITING_ASSIGNMENT"
        assert e["current_team"] == "INSTALLATION_MANAGER"
        # non-manager cannot assign
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation", json={"assigned_user": tk["instmem_id"]}, headers=_hdr(tk["accounts"]))
        assert r.status_code == 403
        requests.post(f"{API}/ecps/{ecp_id}/assign-installation", json={"assigned_user": tk["instmem_id"]}, headers=_hdr(tk["instmgr"]))
        requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "start"}, headers=_hdr(tk["instmem"]))
        # submit with <5 photos -> 400
        r = requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "submit"}, headers=_hdr(tk["instmem"]))
        assert r.status_code == 400
        for t in ["INVERTER_SERIAL", "INVERTER_WITH_CUSTOMER", "PANEL_WITH_CUSTOMER", "LIGHTNING_ARRESTER", "EARTHING_PIT"]:
            requests.post(f"{API}/ecps/{ecp_id}/install-photos", data={"photo_type": t},
                          files={"file": ("p.png", PNG, "image/png")}, headers=_hdr(tk["instmem"]))
        r = requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "submit"}, headers=_hdr(tk["instmem"]))
        assert r.status_code == 200
        # registration sees no approved photos yet
        rp = requests.get(f"{API}/ecps/{ecp_id}/install-photos", headers=_hdr(tk["registration"])).json()
        assert len(rp["photos"]) == 0
        # reject without remarks -> 400
        r = requests.post(f"{API}/ecps/{ecp_id}/installation/reject", json={}, headers=_hdr(tk["instmgr"]))
        assert r.status_code == 400
        requests.post(f"{API}/ecps/{ecp_id}/installation/reject", json={"remarks": "redo earthing"}, headers=_hdr(tk["instmgr"]))
        # resubmit + accept
        requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "submit"}, headers=_hdr(tk["instmem"]))
        r = requests.post(f"{API}/ecps/{ecp_id}/installation/accept", json={}, headers=_hdr(tk["instmgr"]))
        assert r.status_code == 200
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tk["owner"])).json()["ecp"]
        assert e["current_stage"] == "NET_METERING"
        # now registration sees 5 approved photos
        rp = requests.get(f"{API}/ecps/{ecp_id}/install-photos", headers=_hdr(tk["registration"])).json()
        assert len(rp["photos"]) == 5


class TestNetMeteringSecurity:
    def test_nm_sequencing(self, tk):
        lid, ecp_id = _to_installation(tk)
        _finish_install(ecp_id, tk)
        tasks = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tk["owner"])).json()["tasks"]
        tmap = {t["task_name"]: t for t in tasks if t["stage"] == "NET_METERING"}
        # member cannot close NM before request
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Close Net Metering']['id']}/complete", headers=_hdr(tk["instmem"]))
        assert r.status_code == 400
        # registration cannot do DCR before photo upload task
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['DCR Issuance']['id']}/complete", headers=_hdr(tk["registration"]))
        assert r.status_code == 400
        order = ["Upload Installation Photos to CSPDCL Portal", "DCR Issuance", "Consumer Approval & Submit", "Request Net Metering from CSPDCL"]
        for n in order:
            r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap[n]['id']}/complete", headers=_hdr(tk["registration"]))
            assert r.status_code == 200, f"{n}: {r.text}"
        # registration cannot close NM (member team)
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Close Net Metering']['id']}/complete", headers=_hdr(tk["registration"]))
        assert r.status_code == 403
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Close Net Metering']['id']}/complete", headers=_hdr(tk["instmem"]))
        assert r.status_code == 200
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tk["owner"])).json()["ecp"]
        assert e["current_stage"] == "REGISTRATION_2"


class TestDispatchSegregation:
    def test_no_financials(self, tk):
        _, ecp_id = _to_installation(tk)
        # (already advanced past dispatch to installation) create a fresh one at dispatch
        lid = requests.post(f"{API}/leads", json={"name": "DS", "phone": _phone(), "project_price": 777000}, headers=_hdr(tk["lead"])).json()["id"]
        requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tk["lead"]))
        _release_docs(lid, tk)
        eid = requests.get(f"{API}/leads/{lid}", headers=_hdr(tk["lead"])).json()["ecp"]["id"]
        _complete_stage(eid, "REGISTRATION_1", tk["registration"], tk)
        _complete_stage(eid, "ACCOUNTS_1", tk["accounts"], tk)
        d = requests.get(f"{API}/ecps/{eid}", headers=_hdr(tk["dispatch"])).json()
        assert "project_price" not in d["ecp"]
        assert d["payments"] == []
        lst = requests.get(f"{API}/ecps", headers=_hdr(tk["dispatch"])).json()
        assert all("project_price" not in e for e in lst)
        # owner still sees price
        o = requests.get(f"{API}/ecps/{eid}", headers=_hdr(tk["owner"])).json()
        assert o["ecp"]["project_price"] == 777000

    def test_challan(self, tk):
        lid = requests.post(f"{API}/leads", json={"name": "CH", "phone": _phone()}, headers=_hdr(tk["lead"])).json()["id"]
        requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=_hdr(tk["lead"]))
        _release_docs(lid, tk)
        eid = requests.get(f"{API}/leads/{lid}", headers=_hdr(tk["lead"])).json()["ecp"]["id"]
        _complete_stage(eid, "REGISTRATION_1", tk["registration"], tk)
        _complete_stage(eid, "ACCOUNTS_1", tk["accounts"], tk)
        item = requests.post(f"{API}/items", json={"name": f"Panel {uuid.uuid4().hex[:5]}", "unit": "pcs"}, headers=_hdr(tk["owner"])).json()
        r = requests.post(f"{API}/ecps/{eid}/challan", json={"items": [{"item_id": item["id"], "item_name": item["name"], "unit": "pcs", "quantity": 4}]}, headers=_hdr(tk["dispatch"]))
        assert r.status_code == 200
        r = requests.post(f"{API}/ecps/{eid}/challan/finalize", headers=_hdr(tk["dispatch"]))
        assert r.status_code == 200
        acc = requests.get(f"{API}/challans", headers=_hdr(tk["accounts"])).json()
        assert any(c["ecp_id"] == eid for c in acc)
        r = requests.get(f"{API}/challans", headers=_hdr(tk["dispatch"]))
        assert r.status_code == 403


class TestSiteVisit:
    def test_site_visit_survey(self, tk):
        lid = requests.post(f"{API}/leads", json={"name": "SV", "phone": _phone()}, headers=_hdr(tk["lead"])).json()["id"]
        requests.post(f"{API}/leads/{lid}/action", json={"action": "SITE_VISIT"}, headers=_hdr(tk["lead"]))
        sv = requests.get(f"{API}/site-visits", headers=_hdr(tk["owner"])).json()
        svid = next(s["id"] for s in sv if s["lead_id"] == lid)
        # process manager cannot assign; installation manager can
        r = requests.post(f"{API}/site-visits/{svid}/assign", json={"assigned_user": tk["instmem_id"], "visit_date": "2026-02-01"}, headers=_hdr(tk["manager"]))
        assert r.status_code == 403
        r = requests.post(f"{API}/site-visits/{svid}/assign", json={"assigned_user": tk["instmem_id"], "visit_date": "2026-02-01"}, headers=_hdr(tk["instmgr"]))
        assert r.status_code == 200
        # missing measurement -> 400
        r = requests.post(f"{API}/site-visits/{svid}/complete", json={"structure_height": "", "earthing_cable_length": "5", "dc_cable_length": "5", "ac_cable_length": "5", "surveyor_name": "X"}, headers=_hdr(tk["instmem"]))
        assert r.status_code == 400
        r = requests.post(f"{API}/site-visits/{svid}/complete", json={"structure_height": "3m", "earthing_cable_length": "5", "dc_cable_length": "5", "ac_cable_length": "5", "surveyor_name": "Ravi", "extra_materials": []}, headers=_hdr(tk["instmem"]))
        assert r.status_code == 200
        lead = requests.get(f"{API}/leads/{lid}", headers=_hdr(tk["lead"])).json()["lead"]
        assert lead["action_required"] is True and lead["current_team"] == "LEAD"


class TestComplaints:
    def test_complaint_flow(self, tk):
        name = f"Cat {uuid.uuid4().hex[:5]}"
        cat = requests.post(f"{API}/complaint-categories", json={"name": name}, headers=_hdr(tk["owner"])).json()
        # dup 409
        r = requests.post(f"{API}/complaint-categories", json={"name": name}, headers=_hdr(tk["owner"]))
        assert r.status_code == 409
        # non-owner cannot create category
        assert requests.post(f"{API}/complaint-categories", json={"name": "x"}, headers=_hdr(tk["complaint"])).status_code == 403
        # SLA
        requests.put(f"{API}/complaint-sla", json={"config": {f"{cat['id']}|HIGH": 3}}, headers=_hdr(tk["owner"]))
        # register (priority mandatory)
        r = requests.post(f"{API}/complaints", json={"title": "No power", "category_id": cat["id"], "priority": "HIGH"}, headers=_hdr(tk["complaint"]))
        assert r.status_code == 200
        cid = r.json()["id"]
        assert r.json()["status"] == "REGISTERED" and r.json()["sla_due_date"]
        # assign (manager only)
        assert requests.post(f"{API}/complaints/{cid}/assign", json={"assigned_team": "ACCOUNTS", "assigned_user": None}, headers=_hdr(tk["complaint"])).status_code == 403
        acc_id = requests.get(f"{API}/auth/me", headers=_hdr(tk["accounts"])).json()["id"]
        r = requests.post(f"{API}/complaints/{cid}/assign", json={"assigned_team": "ACCOUNTS", "assigned_user": acc_id}, headers=_hdr(tk["manager"]))
        assert r.status_code == 200 and r.json()["status"] == "ASSIGNED"
        # non-assignee cannot progress; dispatch cannot even view
        assert requests.post(f"{API}/complaints/{cid}/status", json={"status": "IN_PROGRESS"}, headers=_hdr(tk["dispatch"])).status_code == 403
        assert requests.get(f"{API}/complaints/{cid}", headers=_hdr(tk["dispatch"])).status_code == 403
        # assignee progresses
        assert requests.post(f"{API}/complaints/{cid}/status", json={"status": "IN_PROGRESS"}, headers=_hdr(tk["accounts"])).status_code == 200
        assert requests.post(f"{API}/complaints/{cid}/status", json={"status": "RESOLVED"}, headers=_hdr(tk["accounts"])).status_code == 200
        # member cannot close; manager closes
        assert requests.post(f"{API}/complaints/{cid}/status", json={"status": "CLOSED"}, headers=_hdr(tk["accounts"])).status_code == 403
        r = requests.post(f"{API}/complaints/{cid}/status", json={"status": "CLOSED"}, headers=_hdr(tk["manager"]))
        assert r.status_code == 200 and r.json()["status"] == "CLOSED"
        assert r.json()["overdue"] is False
        # attachment
        r = requests.post(f"{API}/complaints/{cid}/attachments", files={"file": ("a.png", PNG, "image/png")}, headers=_hdr(tk["complaint"]))
        assert r.status_code == 200
