"""Backend tests for Issues 7-19 (Lead Employee Master, filters, tiles, phone,
work-done, CSV export, mobile, etc)."""
import os
import uuid
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests

with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "owner":        ("anoopdube07@gmail.com", "Owner@123"),
    "manager":      ("manager",               "Manager@123"),
    "lead":         ("lead",                  "Lead@123"),
    "registration": ("registration",          "Reg@123"),
    "accounts":     ("accounts",              "Acct@123"),
    "dispatch":     ("dispatch",              "Disp@123"),
    "installation": ("installation",          "Install@123"),
}


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    return {k: _login(u, p) for k, (u, p) in CREDS.items()}


IST = timezone(timedelta(hours=5, minutes=30))


def ist_today():
    return datetime.now(IST).date().isoformat()


def _future(days=30):
    return (datetime.now(IST).date() + timedelta(days=days)).isoformat()


def _new_lead(tokens, **extra):
    payload = {"name": f"TEST_J_{uuid.uuid4().hex[:6]}", "phone": f"9{uuid.uuid4().int % 1000000000:09d}"}
    payload.update(extra)
    r = requests.post(f"{API}/leads", json=payload, headers=_hdr(tokens["lead"]))
    assert r.status_code == 200, r.text
    return r.json()


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


# ========================= ISSUE 7 =========================
class TestIssue7LeadEmployeeMaster:
    def test_owner_only_create(self, tokens):
        for role in ["manager", "lead", "registration", "accounts", "dispatch", "installation"]:
            r = requests.post(f"{API}/lead-employees", json={"name": f"E_{role}"},
                              headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} must not create: {r.status_code}"
        r = requests.post(f"{API}/lead-employees",
                          json={"name": f"TEST_LE_{uuid.uuid4().hex[:4]}"},
                          headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert r.json()["active"] is True

    def test_get_allowed_roles(self, tokens):
        for role in ["owner", "manager", "lead", "accounts"]:
            r = requests.get(f"{API}/lead-employees", headers=_hdr(tokens[role]))
            assert r.status_code == 200, f"{role} GET should work"
        for role in ["registration", "dispatch", "installation"]:
            r = requests.get(f"{API}/lead-employees", headers=_hdr(tokens[role]))
            assert r.status_code == 403

    def test_active_only_filter(self, tokens):
        # create one active, one and deactivate it
        n1 = f"TEST_LE_A_{uuid.uuid4().hex[:4]}"
        n2 = f"TEST_LE_D_{uuid.uuid4().hex[:4]}"
        r1 = requests.post(f"{API}/lead-employees", json={"name": n1}, headers=_hdr(tokens["owner"]))
        r2 = requests.post(f"{API}/lead-employees", json={"name": n2}, headers=_hdr(tokens["owner"]))
        eid2 = r2.json()["id"]
        # deactivate second
        r = requests.patch(f"{API}/lead-employees/{eid2}", json={"active": False},
                           headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert r.json()["active"] is False

        # active_only=true excludes it
        r = requests.get(f"{API}/lead-employees?active_only=true", headers=_hdr(tokens["lead"]))
        names = [e["name"] for e in r.json()]
        assert n1 in names
        assert n2 not in names
        # full listing includes it
        r = requests.get(f"{API}/lead-employees", headers=_hdr(tokens["lead"]))
        names = [e["name"] for e in r.json()]
        assert n2 in names

    def test_lead_creator_snapshot_on_lead_and_ecp(self, tokens):
        # create employee
        name = f"TEST_LE_SNAP_{uuid.uuid4().hex[:4]}"
        emp = requests.post(f"{API}/lead-employees", json={"name": name},
                            headers=_hdr(tokens["owner"])).json()
        # create lead referencing this creator
        lead = _new_lead(tokens, lead_creator_id=emp["id"])
        assert lead["lead_creator_id"] == emp["id"]
        assert lead["lead_creator_name"] == name
        # YES => ECP carries snapshot
        r = requests.post(f"{API}/leads/{lead['id']}/action", json={"action": "YES"},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        ecp = r.json()["ecp"]
        assert ecp["lead_creator_id"] == emp["id"]
        assert ecp["lead_creator_name"] == name

        # deactivate employee and rename -> historical lead/ECP still shows original snapshot
        requests.patch(f"{API}/lead-employees/{emp['id']}",
                       json={"active": False, "name": name + "_NEW"},
                       headers=_hdr(tokens["owner"]))
        lead2 = requests.get(f"{API}/leads/{lead['id']}", headers=_hdr(tokens["lead"])).json()
        assert lead2["lead"]["lead_creator_name"] == name  # snapshot preserved
        ecp2 = requests.get(f"{API}/ecps/{ecp['id']}", headers=_hdr(tokens["owner"])).json()
        assert ecp2["ecp"]["lead_creator_name"] == name

    def test_invalid_lead_creator_rejected(self, tokens):
        r = requests.post(f"{API}/leads",
                          json={"name": f"TEST_J_BAD_{uuid.uuid4().hex[:4]}",
                                "phone": f"9{uuid.uuid4().int % 1000000000:09d}", "lead_creator_id": "nonexistent-id"},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 400


# ========================= ISSUE 8 =========================
class TestIssue8LeadStatusFilter:
    def test_status_filter_pending(self, tokens):
        lead = _new_lead(tokens)  # PENDING
        r = requests.get(f"{API}/leads?status=PENDING", headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        rows = r.json()
        assert all(l["status"] == "PENDING" for l in rows)
        assert any(l["id"] == lead["id"] for l in rows)

    def test_status_filter_followup(self, tokens):
        lead = _new_lead(tokens)
        requests.post(f"{API}/leads/{lead['id']}/action",
                      json={"action": "FOLLOW_UP", "followup_date": _future(7), "remarks": "x"},
                      headers=_hdr(tokens["lead"]))
        r = requests.get(f"{API}/leads?status=FOLLOW_UP", headers=_hdr(tokens["lead"]))
        rows = r.json()
        assert all(l["status"] == "FOLLOW_UP" for l in rows)
        assert any(l["id"] == lead["id"] for l in rows)

    def test_status_filter_lost(self, tokens):
        lead = _new_lead(tokens)
        requests.post(f"{API}/leads/{lead['id']}/action",
                      json={"action": "NO", "lost_reason": "OTHER", "lost_remarks": "test"},
                      headers=_hdr(tokens["lead"]))
        r = requests.get(f"{API}/leads?status=LOST", headers=_hdr(tokens["lead"]))
        assert all(l["status"] == "LOST" for l in r.json())


# ========================= ISSUE 9 =========================
class TestIssue9ECPStageFilterLead:
    def test_lead_can_filter_ecps_by_stage(self, tokens):
        # create + qualify to get an ECP in REGISTRATION_1
        lead = _new_lead(tokens)
        requests.post(f"{API}/leads/{lead['id']}/action", json={"action": "YES"},
                      headers=_hdr(tokens["lead"]))
        _release_docs(lead["id"], tokens)
        r = requests.get(f"{API}/ecps?stage=REGISTRATION_1", headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        assert all(e["current_stage"] == "REGISTRATION_1" for e in r.json())

    def test_lead_can_filter_closed_view(self, tokens):
        r = requests.get(f"{API}/ecps?view=CLOSED", headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        assert all(e["status"] == "CLOSED" for e in r.json())


# ========================= ISSUE 11 =========================
class TestIssue11FollowupToday:
    def test_only_today_followup_date_shown(self, tokens):
        # create lead A with today's follow-up
        lead_a = _new_lead(tokens)
        today = ist_today()
        r = requests.post(f"{API}/leads/{lead_a['id']}/action",
                          json={"action": "FOLLOW_UP", "followup_date": today, "remarks": "today"},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 200, r.text
        # create lead B with future follow-up
        lead_b = _new_lead(tokens)
        requests.post(f"{API}/leads/{lead_b['id']}/action",
                      json={"action": "FOLLOW_UP", "followup_date": _future(14),
                            "remarks": "future"}, headers=_hdr(tokens["lead"]))
        r = requests.get(f"{API}/leads?followup=today", headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        ids = [l["id"] for l in r.json()]
        assert lead_a["id"] in ids, "today's FU lead must appear"
        assert lead_b["id"] not in ids, "future FU lead must NOT appear (date-based, not status-based)"
        # all rows are FOLLOW_UP status
        assert all(l["status"] == "FOLLOW_UP" for l in r.json())


# ========================= ISSUE 12/13 =========================
class TestIssue12PaymentsDrill:
    """The endpoints we can verify: /payments/monitor is project-wise; dashboard counters
    match /payments/monitor filtered by the same view semantics."""

    def test_monitor_project_wise_and_dashboard_match(self, tokens):
        # Flake mitigation: read both endpoints together, retry once if racy against parallel test creates
        def _snap():
            rows = requests.get(f"{API}/payments/monitor", headers=_hdr(tokens["accounts"])).json()
            d = requests.get(f"{API}/dashboard", headers=_hdr(tokens["accounts"])).json()
            return d, rows
        for _ in range(3):
            d, rows = _snap()
            active = [r for r in rows if r["status"] == "ACTIVE"]
            first_pending = [r for r in active if not r["first_payment_confirmed"]]
            subsequent = [r for r in active if r["first_payment_confirmed"] and r["total_receivable"] > 0]
            if (d["first_payment_pending_count"] == len(first_pending)
                    and d["subsequent_followup_count"] == len(subsequent)
                    and abs(d["total_receivable"] - sum(r["total_receivable"] for r in active)) < 0.01):
                return
        assert d["first_payment_pending_count"] == len(first_pending)
        assert d["subsequent_followup_count"] == len(subsequent)
        total = sum(r["total_receivable"] for r in active)
        assert abs(d["total_receivable"] - total) < 0.01

    def test_pending_payments_do_not_reduce_receivable(self, tokens):
        # create qualified ECP, set price 1_000_000, add a PENDING payment
        lead = _new_lead(tokens, project_price=1000000)
        r = requests.post(f"{API}/leads/{lead['id']}/action", json={"action": "YES"},
                          headers=_hdr(tokens["lead"]))
        ecp = r.json()["ecp"]
        r = requests.post(f"{API}/payments",
                          json={"ecp_id": ecp["id"], "type": "FIRST", "amount": 300000,
                                "date": ist_today(), "status": "PENDING"},
                          headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200
        rows = requests.get(f"{API}/payments/monitor", headers=_hdr(tokens["accounts"])).json()
        row = next(r for r in rows if r["ecp_id"] == ecp["id"])
        assert row["total_receivable"] == 1000000
        assert row["first_payment_confirmed"] is False


# ========================= ISSUE 14 =========================
class TestIssue14AccountsLeadCreator:
    def test_monitor_includes_lead_creator_name(self, tokens):
        emp = requests.post(f"{API}/lead-employees",
                            json={"name": f"TEST_LE_ACC_{uuid.uuid4().hex[:4]}"},
                            headers=_hdr(tokens["owner"])).json()
        lead = _new_lead(tokens, lead_creator_id=emp["id"])
        r = requests.post(f"{API}/leads/{lead['id']}/action", json={"action": "YES"},
                          headers=_hdr(tokens["lead"]))
        ecp_id = r.json()["ecp"]["id"]
        rows = requests.get(f"{API}/payments/monitor", headers=_hdr(tokens["accounts"])).json()
        row = next(r for r in rows if r["ecp_id"] == ecp_id)
        # server currently spreads _ecp_receivable but not lead_creator_name explicitly.
        # Test what the spec requires:
        assert "lead_creator_name" in row, "Payment monitor row must include lead_creator_name"
        assert row["lead_creator_name"] == emp["name"]


# ========================= ISSUE 15 =========================
class TestIssue15PhoneMandatory:
    def test_create_user_without_phone_400(self, tokens):
        r = requests.post(f"{API}/users",
                          json={"username": f"nophone_{uuid.uuid4().hex[:4]}",
                                "password": "P@ss123", "name": "NP", "role": "LEAD"},
                          headers=_hdr(tokens["owner"]))
        # Pydantic returns 422 when required field missing; our custom check gives 400
        assert r.status_code in (400, 422)

    def test_create_user_with_empty_phone_400(self, tokens):
        r = requests.post(f"{API}/users",
                          json={"username": f"emptyph_{uuid.uuid4().hex[:4]}",
                                "password": "P@ss123", "name": "EP", "role": "LEAD",
                                "phone": "   "},
                          headers=_hdr(tokens["owner"]))
        assert r.status_code == 400

    def test_create_with_phone_and_get(self, tokens):
        uname = f"withph_{uuid.uuid4().hex[:4]}"
        r = requests.post(f"{API}/users",
                          json={"username": uname, "password": "P@ss123",
                                "name": "With Phone", "role": "LEAD", "phone": "9876543210"},
                          headers=_hdr(tokens["owner"]))
        assert r.status_code == 200, r.text
        assert r.json()["phone"] == "9876543210"
        users = requests.get(f"{API}/users", headers=_hdr(tokens["owner"])).json()
        target = next(u for u in users if u["username"] == uname)
        assert target["phone"] == "9876543210"

    def test_patch_phone_update(self, tokens):
        uname = f"patchph_{uuid.uuid4().hex[:4]}"
        r = requests.post(f"{API}/users",
                          json={"username": uname, "password": "P@ss123",
                                "name": "Patch Phone", "role": "LEAD", "phone": "1112223333"},
                          headers=_hdr(tokens["owner"]))
        uid = r.json()["id"]
        r = requests.patch(f"{API}/users/{uid}", json={"phone": "9998887777"},
                           headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert r.json()["phone"] == "9998887777"

    def test_seed_users_without_phone_still_login(self, tokens):
        # 'manager' seed user has no phone field, should still be able to hit /auth/me
        r = requests.get(f"{API}/auth/me", headers=_hdr(tokens["manager"]))
        assert r.status_code == 200


# ========================= ISSUE 16 =========================
class TestIssue16Activities:
    def test_owner_only(self, tokens):
        for role in ["manager", "lead", "registration", "accounts", "dispatch", "installation"]:
            r = requests.get(f"{API}/activities", headers=_hdr(tokens[role]))
            assert r.status_code == 403
        r = requests.get(f"{API}/activities", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_default_returns_ist_today_only(self, tokens):
        # trigger an activity now (lead create)
        lead = _new_lead(tokens)
        r = requests.get(f"{API}/activities", headers=_hdr(tokens["owner"]))
        rows = r.json()
        assert len(rows) > 0
        # every row.ts falls in IST today
        today = ist_today()
        for row in rows:
            # ts is ISO UTC; convert to IST date
            ts_dt = datetime.fromisoformat(row["ts"].replace("Z", "+00:00")) if "Z" in row["ts"] else datetime.fromisoformat(row["ts"])
            ist_dt = ts_dt.astimezone(IST).date().isoformat()
            assert ist_dt == today, f"row ts {row['ts']} -> IST {ist_dt} != today {today}"
        # our lead-create activity should appear
        assert any(r["ref_id"] == lead["id"] and r["activity"] == "Lead Created" for r in rows)

    def test_filter_by_team(self, tokens):
        r = requests.get(f"{API}/activities?team=LEAD", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert all(row["team"] == "LEAD" for row in r.json())

    def test_activities_logged_for_key_events(self, tokens):
        # site visit assign + complete
        lead = _new_lead(tokens)
        requests.post(f"{API}/leads/{lead['id']}/action",
                      json={"action": "SITE_VISIT", "remarks": "req"}, headers=_hdr(tokens["lead"]))
        # find sv
        svs = requests.get(f"{API}/site-visits", headers=_hdr(tokens["manager"])).json()
        sv = next(s for s in svs if s["lead_id"] == lead["id"])
        install_users = requests.get(f"{API}/users/team/INSTALLATION",
                                      headers=_hdr(tokens["manager"])).json()
        assignee = install_users[0]
        requests.post(f"{API}/site-visits/{sv['id']}/assign",
                      json={"assigned_user": assignee["id"], "visit_date": _future(3)},
                      headers=_hdr(tokens["manager"]))
        rows = requests.get(f"{API}/activities", headers=_hdr(tokens["owner"])).json()
        activities = {r["activity"] for r in rows}
        assert "Lead Created" in activities
        assert "Site Visit Assigned" in activities


# ========================= ISSUE 17 =========================
class TestIssue17CSVExport:
    def test_owner_only(self, tokens):
        for role in ["manager", "lead", "registration", "accounts", "dispatch", "installation"]:
            r = requests.get(f"{API}/export/projects", headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} must not access CSV export"

    def test_default_excludes_money(self, tokens):
        r = requests.get(f"{API}/export/projects", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        text = r.text
        header = text.splitlines()[0]
        assert "Customer" in header and "Lead ID" in header and "ECP ID" in header
        assert "Lead Creator" in header
        assert "Project Price" not in header
        assert "First Received" not in header
        assert "Total Receivable" not in header

    def test_include_money(self, tokens):
        r = requests.get(f"{API}/export/projects?include_money=true", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        header = r.text.splitlines()[0]
        assert "Project Price" in header
        assert "First Received" in header
        assert "Subsequent Received" in header
        assert "Total Received" in header
        assert "Total Receivable" in header


# ========================= ISSUE 18 =========================
class TestIssue18ManagerTilesAndFilters:
    def test_manager_dashboard_tiles(self, tokens):
        d = requests.get(f"{API}/dashboard", headers=_hdr(tokens["manager"])).json()
        for k in ["site_visits_to_assign", "awaiting_install_assignment",
                  "active_leads", "active_ecps", "delayed"]:
            assert k in d, f"missing tile {k}"
            assert isinstance(d[k], int)

    def test_manager_sees_awaiting_assignment_view(self, tokens):
        r = requests.get(f"{API}/ecps?view=AWAITING_ASSIGNMENT", headers=_hdr(tokens["manager"]))
        assert r.status_code == 200
        for e in r.json():
            assert e["current_stage"] == "INSTALLATION"
            assert e.get("derived_status") == "AWAITING_ASSIGNMENT"


# ========================= Regression: ISSUE 10 =========================
class TestIssue10ActionRequired:
    def test_pending_filter_returns_action_required(self, tokens):
        lead = _new_lead(tokens)
        r = requests.get(f"{API}/leads?status=PENDING", headers=_hdr(tokens["lead"]))
        ids = [l["id"] for l in r.json()]
        assert lead["id"] in ids
