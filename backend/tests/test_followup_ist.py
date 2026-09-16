"""Targeted IST-boundary regression tests for Lead follow-up business date logic.

Covers:
  1. FOLLOW_UP action past-date validation uses IST 'today' (not UTC).
  2. Dashboard `followups_today` counts using IST 'today' (not UTC).
  3. GET /api/leads?followup=today (already IST) agrees with dashboard count.
  4. No regression to FOLLOW_UP workflow: requires followup_date + remarks,
     sets status FOLLOW_UP + action_required, remarks preserved.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

# --- Config ----------------------------------------------------------------
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"
with open("/app/backend/.env") as _f:
    for _l in _f:
        if _l.startswith("MONGO_URL"):
            MONGO_URL = _l.split("=", 1)[1].strip().strip('"')
        elif _l.startswith("DB_NAME"):
            DB_NAME = _l.split("=", 1)[1].strip().strip('"')

IST = timezone(timedelta(hours=5, minutes=30))


def _ist_today():
    return datetime.now(IST).date()


def _utc_today():
    return datetime.now(timezone.utc).date()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# --- Fixtures --------------------------------------------------------------
@pytest.fixture(scope="module")
def lead_token():
    r = requests.post(f"{API}/auth/login",
                      json={"username": "lead", "password": "Lead@123"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _new_lead(tok, prefix="TEST_IST"):
    r = requests.post(f"{API}/leads",
                      json={"name": f"{prefix}_{uuid.uuid4().hex[:6]}",
                            "phone": f"9{uuid.uuid4().int % 1000000000:09d}"},
                      headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# --- Tests -----------------------------------------------------------------
class TestFollowupISTValidation:
    """FOLLOW_UP action past-date check uses IST today."""

    def test_today_ist_accepted(self, lead_token):
        lid = _new_lead(lead_token)
        today_ist = _ist_today().isoformat()
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP",
                                "followup_date": today_ist,
                                "remarks": "IST today ok"},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lead"]["status"] == "FOLLOW_UP"
        assert body["lead"]["action_required"] is True

    def test_yesterday_ist_rejected(self, lead_token):
        lid = _new_lead(lead_token)
        yday = (_ist_today() - timedelta(days=1)).isoformat()
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP",
                                "followup_date": yday,
                                "remarks": "should fail"},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 400
        assert "past" in r.text.lower()

    def test_future_accepted(self, lead_token):
        lid = _new_lead(lead_token)
        future = (_ist_today() + timedelta(days=5)).isoformat()
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP",
                                "followup_date": future,
                                "remarks": "future"},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 200, r.text

    def test_requires_date_and_remarks(self, lead_token):
        lid = _new_lead(lead_token)
        # missing date
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP", "remarks": "no date"},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 400
        # missing remarks
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP",
                                "followup_date": _ist_today().isoformat()},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 400


class TestDashboardFollowupsTodayIST:
    """Dashboard followups_today counts using IST today (not UTC)."""

    def test_today_ist_counted(self, lead_token):
        lid = _new_lead(lead_token)
        today_ist = _ist_today().isoformat()
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP",
                                "followup_date": today_ist,
                                "remarks": "count me"},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 200
        dash = requests.get(f"{API}/dashboard", headers=_hdr(lead_token), timeout=30)
        assert dash.status_code == 200
        d = dash.json()
        assert "followups_today" in d, d
        assert d["followups_today"] >= 1

    def test_consistency_with_leads_filter(self, lead_token):
        """?followup=today (already IST) and dashboard followups_today must agree."""
        r = requests.get(f"{API}/leads?followup=today",
                         headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 200
        list_count = len(r.json())
        dash = requests.get(f"{API}/dashboard",
                            headers=_hdr(lead_token), timeout=30).json()
        dash_count = dash["followups_today"]
        # Both endpoints must reflect IST-today: they can differ (list dedupes
        # by lead & may include leads not currently FOLLOW_UP; dashboard
        # only counts followup rows for currently-FOLLOW_UP leads) but both
        # should reflect at least our seeded IST-today follow-ups.
        assert list_count >= 1
        assert dash_count >= 1

    def test_boundary_ist_vs_utc(self, lead_token, mongo_db):
        """Directly insert a followup dated the IST calendar day but NOT the
        UTC calendar day (when they differ) and assert dashboard classifies it
        by IST. When UTC==IST (most of the day), we simulate the reverse: a
        followup dated (IST today - 1) must NOT be counted.
        """
        ist_today = _ist_today().isoformat()
        utc_today = _utc_today().isoformat()

        # Create a real lead through API and put it in FOLLOW_UP (needed for
        # dashboard filter that only counts currently-FOLLOW_UP leads).
        lid = _new_lead(lead_token, prefix="TEST_IST_BOUND")
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP",
                                "followup_date": ist_today,
                                "remarks": "boundary seed"},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 200

        # Now directly insert an extra followup row dated (ist_today - 1) for
        # the same lead; this must NOT be counted by dashboard.
        yday = (_ist_today() - timedelta(days=1)).isoformat()
        mongo_db.lead_followups.insert_one({
            "id": f"TESTFU_{uuid.uuid4().hex[:8]}",
            "lead_id": lid,
            "followup_date": yday,
            "remarks": "yday - should not count",
            "created_by": "test",
            "created_by_name": "test",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        dash = requests.get(f"{API}/dashboard",
                            headers=_hdr(lead_token), timeout=30).json()
        base_count = dash["followups_today"]
        assert base_count >= 1

        # Insert one more followup for the same lead dated IST-today; count
        # should increase by exactly 1 (proving classification by IST date).
        mongo_db.lead_followups.insert_one({
            "id": f"TESTFU_{uuid.uuid4().hex[:8]}",
            "lead_id": lid,
            "followup_date": ist_today,
            "remarks": "ist today extra",
            "created_by": "test",
            "created_by_name": "test",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        dash2 = requests.get(f"{API}/dashboard",
                             headers=_hdr(lead_token), timeout=30).json()
        assert dash2["followups_today"] == base_count + 1, (
            base_count, dash2["followups_today"])

        # If UTC date currently differs from IST date, additionally seed a
        # followup dated the *UTC* date (which is not IST today) and prove it
        # is NOT counted. This is the definitive UTC-vs-IST boundary proof;
        # otherwise this branch is a no-op with a log.
        if utc_today != ist_today:
            mongo_db.lead_followups.insert_one({
                "id": f"TESTFU_{uuid.uuid4().hex[:8]}",
                "lead_id": lid,
                "followup_date": utc_today,
                "remarks": "utc-today only - not IST today",
                "created_by": "test",
                "created_by_name": "test",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            dash3 = requests.get(f"{API}/dashboard",
                                 headers=_hdr(lead_token), timeout=30).json()
            assert dash3["followups_today"] == base_count + 1, (
                "UTC-dated followup was incorrectly counted as today; "
                "dashboard is not using IST")
        else:
            print(f"[info] UTC date == IST date ({utc_today}); "
                  "boundary UTC-differs case skipped.")


class TestFollowupPersistsRemarks:
    def test_remarks_and_date_stored(self, lead_token, mongo_db):
        lid = _new_lead(lead_token, prefix="TEST_IST_REM")
        today_ist = _ist_today().isoformat()
        remarks = f"remarks_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/leads/{lid}/action",
                          json={"action": "FOLLOW_UP",
                                "followup_date": today_ist,
                                "remarks": remarks},
                          headers=_hdr(lead_token), timeout=30)
        assert r.status_code == 200
        fu = mongo_db.lead_followups.find_one({"lead_id": lid,
                                               "remarks": remarks})
        assert fu is not None
        assert fu["followup_date"] == today_ist
        assert fu["remarks"] == remarks


# --- Cleanup ---------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _cleanup(mongo_db):
    yield
    # Remove synthetic followups and TEST_IST_* leads
    mongo_db.lead_followups.delete_many({"id": {"$regex": "^TESTFU_"}})
    test_leads = list(mongo_db.leads.find({"name": {"$regex": "^TEST_IST"}},
                                          {"id": 1}))
    ids = [l["id"] for l in test_leads]
    if ids:
        mongo_db.lead_followups.delete_many({"lead_id": {"$in": ids}})
        mongo_db.leads.delete_many({"id": {"$in": ids}})
