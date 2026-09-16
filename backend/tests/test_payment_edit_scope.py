"""Tests for PATCH /api/payments/{id} - ECP payment edit feature.

Covers:
- ACCOUNTS can update amount/date/status/remarks
- ECP current_stage must not change on payment update
- Non-ACCOUNTS roles are rejected (403)
- Payment count for ECP stays same (no dup created)
- Editing does not change payment type
- Future date rejected
- Invalid status rejected
- Payment CREATION still works
"""
import os
import requests
from pathlib import Path


def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env = Path("/app/frontend/.env")
    for line in env.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _load_base()
API = f"{BASE}/api"


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=20)
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text}"
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# Session-scoped tokens
ACC_TOK = None
OWN_TOK = None
MGR_TOK = None


def setup_module(_):
    global ACC_TOK, OWN_TOK, MGR_TOK
    ACC_TOK = _login("accounts", "Acct@123")
    OWN_TOK = _login("anoopdube07@gmail.com", "Owner@123")
    MGR_TOK = _login("manager", "Manager@123")


def _find_active_ecp_with_payment():
    """Return (ecp_id, payment_id, current_stage). Create a payment if none exists."""
    r = requests.get(f"{API}/ecps", headers=_h(ACC_TOK), timeout=20)
    assert r.status_code == 200
    ecps = r.json()
    # Prefer ACTIVE ECP
    active_ecps = [e for e in ecps if (e.get("status") or "").upper() == "ACTIVE"]
    candidates = active_ecps or ecps
    for e in candidates:
        rd = requests.get(f"{API}/ecps/{e['id']}", headers=_h(ACC_TOK), timeout=20)
        if rd.status_code != 200:
            continue
        detail = rd.json()
        pays = detail.get("payments") or []
        if pays:
            return e["id"], pays[0]["id"], detail.get("current_stage"), detail
    # Otherwise create one on first active
    for e in candidates:
        # attempt create FIRST payment (may fail if exists)
        for ptype in ("ADDITIONAL", "FIRST"):
            payload = {"ecp_id": e["id"], "type": ptype, "amount": 100.0,
                       "date": "2025-01-01", "status": "PENDING", "remarks": "TEST_seed"}
            rc = requests.post(f"{API}/payments", headers=_h(ACC_TOK), json=payload, timeout=20)
            if rc.status_code == 200:
                rd = requests.get(f"{API}/ecps/{e['id']}", headers=_h(ACC_TOK), timeout=20)
                detail = rd.json()
                pays = detail.get("payments") or []
                if pays:
                    return e["id"], pays[-1]["id"], detail.get("current_stage"), detail
    raise AssertionError("No ECP with payment available and could not seed one")


def test_accounts_can_update_payment_and_stage_unchanged():
    ecp_id, pay_id, stage_before, detail_before = _find_active_ecp_with_payment()
    pay_before = next(p for p in detail_before["payments"] if p["id"] == pay_id)
    pay_count_before = len(detail_before["payments"])
    ptype_before = pay_before["type"]

    new_amount = float(pay_before["amount"]) + 11
    new_status = "CONFIRMED" if pay_before["status"] == "PENDING" else "PENDING"
    body = {"amount": new_amount, "date": pay_before["date"][:10],
            "status": new_status, "remarks": "TEST_edited"}
    r = requests.patch(f"{API}/payments/{pay_id}", headers=_h(ACC_TOK), json=body, timeout=20)
    assert r.status_code == 200, f"PATCH failed: {r.status_code} {r.text}"
    updated = r.json()
    assert updated["id"] == pay_id
    assert updated["type"] == ptype_before, "Payment type must not change"
    assert abs(updated["amount"] - new_amount) < 0.001
    assert updated["status"] == new_status
    assert updated["remarks"] == "TEST_edited"

    # Reload ECP to verify persistence + stage unchanged + no dup created
    r2 = requests.get(f"{API}/ecps/{ecp_id}", headers=_h(ACC_TOK), timeout=20)
    assert r2.status_code == 200
    detail_after = r2.json()
    assert detail_after.get("current_stage") == stage_before, \
        f"current_stage changed! before={stage_before} after={detail_after.get('current_stage')}"
    pays_after = detail_after.get("payments") or []
    assert len(pays_after) == pay_count_before, "Payment count changed (dup?)"
    pay_after = next(p for p in pays_after if p["id"] == pay_id)
    assert pay_after["type"] == ptype_before
    assert pay_after["status"] == new_status
    assert abs(pay_after["amount"] - new_amount) < 0.001


def test_owner_cannot_update_payment():
    _, pay_id, _, _ = _find_active_ecp_with_payment()
    r = requests.patch(f"{API}/payments/{pay_id}", headers=_h(OWN_TOK),
                       json={"remarks": "TEST_owner"}, timeout=20)
    assert r.status_code == 403, f"OWNER should be rejected, got {r.status_code}"


def test_manager_cannot_update_payment():
    _, pay_id, _, _ = _find_active_ecp_with_payment()
    r = requests.patch(f"{API}/payments/{pay_id}", headers=_h(MGR_TOK),
                       json={"remarks": "TEST_mgr"}, timeout=20)
    assert r.status_code == 403


def test_future_date_rejected():
    _, pay_id, _, _ = _find_active_ecp_with_payment()
    r = requests.patch(f"{API}/payments/{pay_id}", headers=_h(ACC_TOK),
                       json={"date": "2099-01-01"}, timeout=20)
    assert r.status_code == 400


def test_invalid_status_rejected():
    _, pay_id, _, _ = _find_active_ecp_with_payment()
    r = requests.patch(f"{API}/payments/{pay_id}", headers=_h(ACC_TOK),
                       json={"status": "BOGUS"}, timeout=20)
    assert r.status_code == 400


def test_payment_creation_still_works():
    # Find any ECP, try to create ADDITIONAL payment
    r = requests.get(f"{API}/ecps", headers=_h(ACC_TOK), timeout=20)
    ecps = r.json()
    active = [e for e in ecps if (e.get("status") or "").upper() == "ACTIVE"]
    assert active, "No ACTIVE ECP found"
    ecp_id = active[0]["id"]
    payload = {"ecp_id": ecp_id, "type": "ADDITIONAL", "amount": 1.0,
               "date": "2025-01-01", "status": "PENDING", "remarks": "TEST_create_smoke"}
    r = requests.post(f"{API}/payments", headers=_h(ACC_TOK), json=payload, timeout=20)
    assert r.status_code == 200, f"POST create failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["type"] == "ADDITIONAL"
    assert body["ecp_id"] == ecp_id
