"""Regression tests for the Dispatch stage prerequisite chain.

Sequence enforced:
  Start Dispatch (requires first payment CONFIRMED)
  -> Delivery Challan (requires FINALIZED challan with items)
  -> Material Dispatch Confirmation (requires Delivery Challan complete)
  -> Dispatch Completed (requires Material Dispatch Confirmation)
  -> auto-advance ECP to INSTALLATION.
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
    "lead":         ("lead",                  "Lead@123"),
    "registration": ("registration",          "Reg@123"),
    "accounts":     ("accounts",              "Acct@123"),
    "dispatch":     ("dispatch",              "Disp@123"),
}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 128


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tk():
    return {k: _login(u, p) for k, (u, p) in CREDS.items()}


# -------- helpers --------
def _new_lead(tok):
    payload = {"name": f"TEST_DCG_{uuid.uuid4().hex[:6]}",
               "phone": f"9{uuid.uuid4().int % 1000000000:09d}",
               "financing_required": False,
               "project_price": 500000}
    r = requests.post(f"{API}/leads", json=payload, headers=H(tok))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _upload_doc(tk, lid, t):
    r = None
    for _ in range(4):
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": t},
                          files={"file": ("d.png", PNG, "image/png")}, headers=H(tk["lead"]))
        if r.status_code == 200:
            return r
    return r


def _tasks(tk, ecp_id):
    return requests.get(f"{API}/ecps/{ecp_id}", headers=H(tk["owner"])).json()["tasks"]


def _find_task(tk, ecp_id, name, stage="DISPATCH"):
    for t in _tasks(tk, ecp_id):
        if t["stage"] == stage and t["task_name"] == name:
            return t
    return None


def _complete_stage(tk, ecp_id, stage, role_key):
    for t in _tasks(tk, ecp_id):
        if t["stage"] == stage and t["applicable"] and not t["completed"]:
            r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{t['id']}/complete",
                              headers=H(tk[role_key]))
            assert r.status_code == 200, f"{t['task_name']}: {r.text}"


def _drive_to_dispatch(tk, confirm_first_payment=True):
    lid = _new_lead(tk["lead"])
    r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=H(tk["lead"]))
    assert r.status_code == 200, r.text
    ecp_id = r.json()["ecp"]["id"]
    for t in ("PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK"):
        r = _upload_doc(tk, lid, t)
        assert r.status_code == 200, f"{t}: {r.text}"
    _complete_stage(tk, ecp_id, "REGISTRATION_1", "owner")
    _complete_stage(tk, ecp_id, "ACCOUNTS_1", "owner")
    detail = requests.get(f"{API}/ecps/{ecp_id}", headers=H(tk["owner"])).json()
    ecp = detail.get("ecp", detail)
    assert ecp["current_stage"] == "DISPATCH", ecp.get("current_stage")
    if confirm_first_payment:
        r = requests.post(f"{API}/payments",
            json={"ecp_id": ecp_id, "type": "FIRST", "amount": 10000,
                  "date": "2026-01-15", "status": "CONFIRMED"},
            headers=H(tk["accounts"]))
        assert r.status_code == 200, r.text
    return ecp_id


def _active_item(tk):
    items = requests.get(f"{API}/items?active_only=true", headers=H(tk["owner"])).json()
    if items:
        return items[0]
    r = requests.post(f"{API}/items",
        json={"name": "TEST_DCG_Panel", "unit": "pcs"}, headers=H(tk["owner"]))
    assert r.status_code == 200, r.text
    return r.json()


# ================== Tests ==================
class TestDispatchChallanGate:

    def test_1_start_dispatch_without_first_payment(self, tk):
        ecp_id = _drive_to_dispatch(tk, confirm_first_payment=False)
        r = requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=H(tk["dispatch"]))
        assert r.status_code == 400, r.text
        assert "First Payment" in r.text or "first" in r.text.lower()
        ecp = requests.get(f"{API}/ecps/{ecp_id}", headers=H(tk["owner"])).json().get("ecp", {})
        assert not ecp.get("dispatch_started")

    def test_2_start_dispatch_with_first_payment(self, tk):
        ecp_id = _drive_to_dispatch(tk, confirm_first_payment=True)
        r = requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text
        assert r.json().get("ecp", {}).get("dispatch_started") is True

    def test_3_delivery_challan_task_no_challan(self, tk):
        ecp_id = _drive_to_dispatch(tk)
        r = requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text
        dc = _find_task(tk, ecp_id, "Delivery Challan")
        assert dc is not None
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{dc['id']}/complete",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 400, r.text
        assert "Finalize the Delivery Challan" in r.text
        dc_after = _find_task(tk, ecp_id, "Delivery Challan")
        assert dc_after["completed"] is False

    def test_4_delivery_challan_task_draft_only(self, tk):
        ecp_id = _drive_to_dispatch(tk)
        requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=H(tk["dispatch"]))
        item = _active_item(tk)
        r = requests.post(f"{API}/ecps/{ecp_id}/challan",
            json={"items": [{"item_id": item["id"], "item_name": item["name"],
                             "unit": item.get("unit", "pcs"), "quantity": 3}]},
            headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "DRAFT"
        dc = _find_task(tk, ecp_id, "Delivery Challan")
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{dc['id']}/complete",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 400, r.text
        assert "Finalize the Delivery Challan" in r.text
        dc_after = _find_task(tk, ecp_id, "Delivery Challan")
        assert dc_after["completed"] is False

    def test_5_full_sequence_and_auto_advance(self, tk):
        ecp_id = _drive_to_dispatch(tk)
        r = requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text

        # Attempt Material Dispatch Confirmation before Delivery Challan is complete
        mdc = _find_task(tk, ecp_id, "Material Dispatch Confirmation")
        assert mdc is not None
        assert mdc.get("requires") == "Delivery Challan", mdc
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{mdc['id']}/complete",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 400, r.text
        assert "Delivery Challan" in r.text

        # Save + finalize challan
        item = _active_item(tk)
        r = requests.post(f"{API}/ecps/{ecp_id}/challan",
            json={"items": [{"item_id": item["id"], "item_name": item["name"],
                             "unit": item.get("unit", "pcs"), "quantity": 4}]},
            headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/ecps/{ecp_id}/challan/finalize",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "FINALIZED"

        # Now Delivery Challan task completes
        dc = _find_task(tk, ecp_id, "Delivery Challan")
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{dc['id']}/complete",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text

        # Attempt Dispatch Completed before Material Dispatch Confirmation
        dcomp = _find_task(tk, ecp_id, "Dispatch Completed")
        assert dcomp.get("requires") == "Material Dispatch Confirmation", dcomp
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{dcomp['id']}/complete",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 400, r.text
        assert "Material Dispatch Confirmation" in r.text

        # Complete MDC
        mdc = _find_task(tk, ecp_id, "Material Dispatch Confirmation")
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{mdc['id']}/complete",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 200, r.text

        # Complete Dispatch Completed -> should auto-advance to INSTALLATION.
        # Use OWNER so scoped get_ecp response still returns 200 after stage advance.
        dcomp = _find_task(tk, ecp_id, "Dispatch Completed")
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{dcomp['id']}/complete",
                          headers=H(tk["owner"]))
        assert r.status_code == 200, r.text
        detail = requests.get(f"{API}/ecps/{ecp_id}", headers=H(tk["owner"])).json()
        assert detail["ecp"]["current_stage"] == "INSTALLATION", detail["ecp"].get("current_stage")
        assert detail["ecp"].get("install_status") == "AWAITING_ASSIGNMENT", detail["ecp"].get("install_status")

    def test_6_rbac_challan_and_task_completion(self, tk):
        ecp_id = _drive_to_dispatch(tk)
        requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=H(tk["dispatch"]))
        item = _active_item(tk)
        # ACCOUNTS cannot save challan
        r = requests.post(f"{API}/ecps/{ecp_id}/challan",
            json={"items": [{"item_id": item["id"], "item_name": item["name"],
                             "unit": item.get("unit", "pcs"), "quantity": 1}]},
            headers=H(tk["accounts"]))
        assert r.status_code == 403, r.text
        # ACCOUNTS cannot finalize
        # (create draft first as DISPATCH so finalize path exists)
        r = requests.post(f"{API}/ecps/{ecp_id}/challan",
            json={"items": [{"item_id": item["id"], "item_name": item["name"],
                             "unit": item.get("unit", "pcs"), "quantity": 1}]},
            headers=H(tk["dispatch"]))
        assert r.status_code == 200
        r = requests.post(f"{API}/ecps/{ecp_id}/challan/finalize",
                          headers=H(tk["accounts"]))
        assert r.status_code == 403, r.text
        # ACCOUNTS cannot complete DISPATCH task
        r = requests.post(f"{API}/ecps/{ecp_id}/challan/finalize",
                          headers=H(tk["dispatch"]))
        assert r.status_code == 200
        dc = _find_task(tk, ecp_id, "Delivery Challan")
        r = requests.post(f"{API}/ecps/{ecp_id}/tasks/{dc['id']}/complete",
                          headers=H(tk["accounts"]))
        assert r.status_code == 403, r.text
