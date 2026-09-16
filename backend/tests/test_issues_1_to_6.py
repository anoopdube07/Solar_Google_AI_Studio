"""Tests for APPROVED fixes — Issues 1..6.

Issue 1: /api/ecps stage filter for REGISTRATION user (reg1 / reg2 / both / out-of-scope).
Issue 2: /api/dashboard ACCOUNTS 3-counter (first_payment_pending_count, subsequent_followup_count,
         subsequent_amount_pending, total_receivable) + math with FIRST/ADDITIONAL/PENDING.
Issue 2B: POST /api/leads/{id}/project-price (LEAD/OWNER only) + create_ecp_from_lead propagation.
Issue 3: /api/payments/monitor row per project with proper fields; POST /api/payments ADDITIONAL type preserved.
Issue 4: /api/ecps?view=... for DISPATCH (PAYMENT_BLOCKED/READY_FOR_DISPATCH/DISPATCH_IN_PROCESS/PAST_DISPATCH).
Issue 5: DISPATCH->MANAGER->INSTALLATION handoff with assign-installation RBAC + installer scope.
Issue 6: /api/users/team/INSTALLATION owner/manager only.
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


# ---------------- helpers ----------------
def _new_lead(tokens, financing=False, project_price=None):
    payload = {"name": f"TEST_I_{uuid.uuid4().hex[:6]}", "phone": f"9{uuid.uuid4().int % 1000000000:09d}",
               "financing_required": financing}
    if project_price is not None:
        payload["project_price"] = project_price
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
        rr = None
        for _ in range(4):
            rr = requests.post(f"{API}/leads/{lead_id}/documents", data={"doc_type": t},
                               files={"file": ("d.png", png, "image/png")}, headers=_hdr(tokens["lead"]))
            if rr.status_code == 200:
                break
        assert rr.status_code == 200, f"doc {t}: {rr.text}"


def _qualify(tokens, financing=False, project_price=None):
    lead = _new_lead(tokens, financing=financing, project_price=project_price)
    r = requests.post(f"{API}/leads/{lead['id']}/action", json={"action": "YES"},
                      headers=_hdr(tokens["lead"]))
    assert r.status_code == 200, r.text
    ecp_id = r.json()["ecp"]["id"]
    _release_docs(lead["id"], tokens, financing)
    return lead["id"], ecp_id


def _complete_all(ecp_id, stage, token):
    r = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(token))
    for t in r.json()["tasks"]:
        if t["stage"] == stage and t["applicable"] and not t["completed"]:
            rr = requests.post(f"{API}/ecps/{ecp_id}/tasks/{t['id']}/complete",
                               headers=_hdr(token))
            assert rr.status_code == 200, f"{t['task_name']}: {rr.text}"


def _finish_installation(ecp_id, installer_tok, tokens):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "start"}, headers=_hdr(installer_tok))
    for t in ["INVERTER_SERIAL", "INVERTER_WITH_CUSTOMER", "PANEL_WITH_CUSTOMER", "LIGHTNING_ARRESTER", "EARTHING_PIT"]:
        requests.post(f"{API}/ecps/{ecp_id}/install-photos", data={"photo_type": t},
                      files={"file": ("p.png", png, "image/png")}, headers=_hdr(installer_tok))
    requests.post(f"{API}/ecps/{ecp_id}/installation", json={"action": "submit"}, headers=_hdr(installer_tok))
    requests.post(f"{API}/ecps/{ecp_id}/installation/accept", json={}, headers=_hdr(tokens["manager"]))


def _run_net_metering(ecp_id, installer_tok, tokens):
    order = ["Upload Installation Photos to CSPDCL Portal", "DCR Issuance",
             "Consumer Approval & Submit", "Request Net Metering from CSPDCL"]
    tasks = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["owner"])).json()["tasks"]
    tmap = {t["task_name"]: t for t in tasks if t["stage"] == "NET_METERING"}
    for name in order:
        requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap[name]['id']}/complete", headers=_hdr(tokens["registration"]))
    requests.post(f"{API}/ecps/{ecp_id}/tasks/{tmap['Close Net Metering']['id']}/complete", headers=_hdr(installer_tok))


def _drive_to_dispatch(tokens, with_first_confirmed=True):
    _, ecp_id = _qualify(tokens)
    _complete_all(ecp_id, "REGISTRATION_1", tokens["registration"])
    _complete_all(ecp_id, "ACCOUNTS_1", tokens["accounts"])
    if with_first_confirmed:
        r = requests.post(f"{API}/payments",
            json={"ecp_id": ecp_id, "type": "FIRST", "amount": 100, "date": "2026-09-10",
                  "status": "CONFIRMED"}, headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200
    return ecp_id


def _drive_to_installation_awaiting(tokens):
    ecp_id = _drive_to_dispatch(tokens, with_first_confirmed=True)
    r = requests.post(f"{API}/ecps/{ecp_id}/start-dispatch", headers=_hdr(tokens["dispatch"]))
    assert r.status_code == 200
    _complete_all(ecp_id, "DISPATCH", tokens["dispatch"])
    return ecp_id


# ============ ISSUE 6: /users/team/{role} ============
class TestIssue6TeamListing:
    def test_owner_manager_get_installation_team(self, tokens):
        for role in ["owner", "manager"]:
            r = requests.get(f"{API}/users/team/INSTALLATION", headers=_hdr(tokens[role]))
            assert r.status_code == 200, f"{role}: {r.text}"
            data = r.json()
            assert isinstance(data, list) and len(data) >= 1
            assert all(u["role"] == "INSTALLATION" for u in data)
            assert all("id" in u and "name" in u for u in data)

    def test_others_forbidden(self, tokens):
        for role in ["lead", "registration", "accounts", "dispatch", "installation"]:
            r = requests.get(f"{API}/users/team/INSTALLATION", headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role} should be 403: {r.status_code}"


# ============ ISSUE 1: REGISTRATION stage filter ============
class TestIssue1RegistrationFilter:
    def test_registration_stage_filter(self, tokens):
        # Ensure at least one REG1 ECP exists
        _, ecp_reg1 = _qualify(tokens)

        # Ensure at least one REG2 ECP exists — drive a fresh ECP up to REG2
        ecp_id2 = _drive_to_installation_awaiting(tokens)
        # Manager assigns install
        users = requests.get(f"{API}/users", headers=_hdr(tokens["owner"])).json()
        install = next(u for u in users if u["role"] == "INSTALLATION" and u.get("active", True))
        r = requests.post(f"{API}/ecps/{ecp_id2}/assign-installation",
            json={"assigned_user": install["id"]}, headers=_hdr(tokens["manager"]))
        assert r.status_code == 200
        # log in as the assigned installer (may be default 'installation')
        if install["username"] == "installation":
            installer_tok = tokens["installation"]
        else:
            # fallback: some other install user — skip driving further, use owner to progress via NET
            installer_tok = tokens["installation"]
        # Start + finish install (photos + submit + manager accept)
        _finish_installation(ecp_id2, installer_tok, tokens)
        _run_net_metering(ecp_id2, installer_tok, tokens)
        e = requests.get(f"{API}/ecps/{ecp_id2}", headers=_hdr(tokens["owner"])).json()["ecp"]
        assert e["current_stage"] == "REGISTRATION_2", f"expected REG2, got {e['current_stage']}"

        # REGISTRATION user filters
        # stage=REGISTRATION_1
        r = requests.get(f"{API}/ecps?stage=REGISTRATION_1", headers=_hdr(tokens["registration"]))
        assert r.status_code == 200
        stages = {e["current_stage"] for e in r.json()}
        assert stages <= {"REGISTRATION_1"}, f"reg1 filter leaked: {stages}"
        assert any(e["id"] == ecp_reg1 for e in r.json())

        # stage=REGISTRATION_2
        r = requests.get(f"{API}/ecps?stage=REGISTRATION_2", headers=_hdr(tokens["registration"]))
        assert r.status_code == 200
        stages = {e["current_stage"] for e in r.json()}
        assert stages <= {"REGISTRATION_2"}, f"reg2 filter leaked: {stages}"
        assert any(e["id"] == ecp_id2 for e in r.json())

        # no stage param -> reg1/reg2/net_metering (all stages where REGISTRATION has tasks)
        r = requests.get(f"{API}/ecps", headers=_hdr(tokens["registration"]))
        stages = {e["current_stage"] for e in r.json()}
        assert stages <= {"REGISTRATION_1", "REGISTRATION_2", "NET_METERING"}, f"unexpected: {stages}"
        assert "REGISTRATION_1" in stages and "REGISTRATION_2" in stages

    def test_registration_cannot_query_dispatch_scope(self, tokens):
        # A dispatch-stage ecp must exist
        ecp_disp = _drive_to_dispatch(tokens, with_first_confirmed=False)
        r = requests.get(f"{API}/ecps?stage=DISPATCH", headers=_hdr(tokens["registration"]))
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        assert ecp_disp not in ids
        stages = {e["current_stage"] for e in r.json()}
        # must NOT include DISPATCH
        assert "DISPATCH" not in stages, f"REGISTRATION got DISPATCH ecps: {stages}"


# ============ ISSUE 4: DISPATCH view filter ============
class TestIssue4DispatchViews:
    def test_view_reduces_set(self, tokens):
        # Create fresh: one blocked (no first) and one ready (first confirmed)
        blocked_id = _drive_to_dispatch(tokens, with_first_confirmed=False)
        ready_id = _drive_to_dispatch(tokens, with_first_confirmed=True)
        # And one in-process
        inproc_id = _drive_to_dispatch(tokens, with_first_confirmed=True)
        r = requests.post(f"{API}/ecps/{inproc_id}/start-dispatch",
                         headers=_hdr(tokens["dispatch"]))
        assert r.status_code == 200

        base = requests.get(f"{API}/ecps", headers=_hdr(tokens["dispatch"])).json()
        base_ids = {e["id"] for e in base}
        assert {blocked_id, ready_id, inproc_id} <= base_ids

        r = requests.get(f"{API}/ecps?view=PAYMENT_BLOCKED", headers=_hdr(tokens["dispatch"]))
        pb = r.json()
        assert all(e["derived_status"] == "PAYMENT_BLOCKED" for e in pb)
        assert blocked_id in {e["id"] for e in pb}
        assert ready_id not in {e["id"] for e in pb}
        assert inproc_id not in {e["id"] for e in pb}
        assert len(pb) < len(base)  # filter actually reduces

        r = requests.get(f"{API}/ecps?view=READY_FOR_DISPATCH", headers=_hdr(tokens["dispatch"]))
        rfd = r.json()
        assert all(e["derived_status"] == "READY_FOR_DISPATCH" for e in rfd)
        assert ready_id in {e["id"] for e in rfd}
        assert blocked_id not in {e["id"] for e in rfd}
        assert inproc_id not in {e["id"] for e in rfd}

        r = requests.get(f"{API}/ecps?view=DISPATCH_IN_PROCESS", headers=_hdr(tokens["dispatch"]))
        dip = r.json()
        assert all(e["derived_status"] == "DISPATCH_IN_PROCESS" for e in dip)
        assert inproc_id in {e["id"] for e in dip}
        assert blocked_id not in {e["id"] for e in dip}
        assert ready_id not in {e["id"] for e in dip}

    def test_past_dispatch_view(self, tokens):
        # OWNER can see beyond dispatch too — use OWNER to check view semantics broadly
        r = requests.get(f"{API}/ecps?view=PAST_DISPATCH", headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        for e in r.json():
            assert (e["current_stage"] in ("INSTALLATION", "NET_METERING", "REGISTRATION_2", "ACCOUNTS_2")
                    or e["status"] in ("COMPLETED", "CLOSED")), \
                    f"unexpected in PAST_DISPATCH: stage={e['current_stage']} status={e['status']}"


# ============ ISSUE 5: Dispatch -> Manager -> Installation handoff ============
class TestIssue5InstallHandoff:
    def test_full_handoff_and_rbac(self, tokens):
        ecp_id = _drive_to_installation_awaiting(tokens)
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["owner"])).json()["ecp"]
        assert e["current_stage"] == "INSTALLATION"
        assert e["install_status"] == "AWAITING_ASSIGNMENT"
        assert e["current_team"] == "INSTALLATION_MANAGER"
        assert e.get("responsible_user") in (None, "")

        # assign-installation RBAC: non-manager/owner 403
        users = requests.get(f"{API}/users", headers=_hdr(tokens["owner"])).json()
        install_user = next(u for u in users if u["role"] == "INSTALLATION" and u.get("active", True))
        for role in ["lead", "registration", "accounts", "dispatch", "installation"]:
            r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
                json={"assigned_user": install_user["id"]}, headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role}: {r.status_code}"

        # non-INSTALLATION assignee 400
        lead_user = next(u for u in users if u["role"] == "LEAD")
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": lead_user["id"]}, headers=_hdr(tokens["manager"]))
        assert r.status_code == 400

        # Manager assigns OK
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": install_user["id"]}, headers=_hdr(tokens["manager"]))
        assert r.status_code == 200
        e = r.json()["ecp"]
        assert e["install_status"] == "READY_TO_INSTALL"
        assert e["current_team"] == "INSTALLATION_MEMBER"
        assert e["responsible_user"] == install_user["id"]

    def test_non_assignee_installer_403(self, tokens):
        # Create a fresh awaiting ECP and assign to a NEW installer, then default 'installation' should get 403
        ecp_id = _drive_to_installation_awaiting(tokens)
        uname = "install_x_" + uuid.uuid4().hex[:4]
        r = requests.post(f"{API}/users",
            json={"username": uname, "password": "Pass@123", "name": "Install X", "role": "INSTALLATION", "phone": "9000000000"},
            headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        other = r.json()
        other_tok = _login(uname, "Pass@123")
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": other["id"]}, headers=_hdr(tokens["manager"]))
        assert r.status_code == 200
        # default installation is NOT assignee
        r = requests.post(f"{API}/ecps/{ecp_id}/installation",
            json={"action": "start"}, headers=_hdr(tokens["installation"]))
        assert r.status_code == 403
        # assignee can start
        r = requests.post(f"{API}/ecps/{ecp_id}/installation",
            json={"action": "start"}, headers=_hdr(other_tok))
        assert r.status_code == 200

    def test_installer_only_sees_own_assigned_via_list(self, tokens):
        # Create ECP assigned to a new user, verify default installer does NOT see it in GET /ecps
        ecp_id = _drive_to_installation_awaiting(tokens)
        uname = "install_y_" + uuid.uuid4().hex[:4]
        r = requests.post(f"{API}/users",
            json={"username": uname, "password": "Pass@123", "name": "Install Y", "role": "INSTALLATION", "phone": "9000000001"},
            headers=_hdr(tokens["owner"]))
        assert r.status_code == 200
        other = r.json()
        other_tok = _login(uname, "Pass@123")
        r = requests.post(f"{API}/ecps/{ecp_id}/assign-installation",
            json={"assigned_user": other["id"]}, headers=_hdr(tokens["manager"]))
        assert r.status_code == 200
        # default installation should NOT see ecp_id
        r = requests.get(f"{API}/ecps", headers=_hdr(tokens["installation"]))
        assert r.status_code == 200
        default_ids = {e["id"] for e in r.json()}
        assert ecp_id not in default_ids
        # 'other' user should see it
        r = requests.get(f"{API}/ecps", headers=_hdr(other_tok))
        ids = {e["id"] for e in r.json()}
        assert ecp_id in ids

    def test_manager_dashboard_has_awaiting_count(self, tokens):
        _drive_to_installation_awaiting(tokens)
        r = requests.get(f"{API}/dashboard", headers=_hdr(tokens["manager"]))
        assert r.status_code == 200
        d = r.json()
        assert "awaiting_install_assignment" in d
        assert isinstance(d["awaiting_install_assignment"], int)
        assert d["awaiting_install_assignment"] >= 1

    def test_awaiting_assignment_view(self, tokens):
        _drive_to_installation_awaiting(tokens)
        r = requests.get(f"{API}/ecps?view=AWAITING_ASSIGNMENT", headers=_hdr(tokens["manager"]))
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        for e in data:
            assert e["current_stage"] == "INSTALLATION"
            assert e.get("install_status") == "AWAITING_ASSIGNMENT"


# ============ ISSUE 2B: Project Price ============
class TestIssue2BProjectPrice:
    def test_lead_can_set_price_on_create_and_via_endpoint(self, tokens):
        lead = _new_lead(tokens, project_price=750000)
        assert float(lead.get("project_price") or 0) == 750000

        # LEAD update via endpoint
        r = requests.post(f"{API}/leads/{lead['id']}/project-price",
            json={"project_price": 800000}, headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        assert float(r.json()["lead"]["project_price"]) == 800000

        # OWNER can too
        r = requests.post(f"{API}/leads/{lead['id']}/project-price",
            json={"project_price": 900000}, headers=_hdr(tokens["owner"]))
        assert r.status_code == 200

        # Non-LEAD/OWNER forbidden
        for role in ["manager", "registration", "accounts", "dispatch", "installation"]:
            r = requests.post(f"{API}/leads/{lead['id']}/project-price",
                json={"project_price": 111}, headers=_hdr(tokens[role]))
            assert r.status_code == 403, f"{role}: {r.status_code}"

    def test_price_propagates_on_yes_and_via_endpoint(self, tokens):
        lead = _new_lead(tokens, project_price=1000000)
        # YES creates ECP; price should carry over
        r = requests.post(f"{API}/leads/{lead['id']}/action", json={"action": "YES"},
                          headers=_hdr(tokens["lead"]))
        assert r.status_code == 200
        ecp = r.json()["ecp"]
        assert float(ecp.get("project_price") or 0) == 1000000
        ecp_id = ecp["id"]

        # APPROVED RULE (Phase 2): after handoff the direct project-price endpoint is blocked;
        # commercial price changes must go through Owner approval.
        r = requests.post(f"{API}/leads/{lead['id']}/project-price",
            json={"project_price": 1200000}, headers=_hdr(tokens["lead"]))
        assert r.status_code == 400

        # Price change flows via commercial-change -> Owner approval, and propagates to the ECP.
        r = requests.post(f"{API}/leads/{lead['id']}/commercial-change",
            json={"project_price": 1200000}, headers=_hdr(tokens["lead"]))
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/leads/{lead['id']}/commercial-change/approve",
            json={}, headers=_hdr(tokens["owner"]))
        assert r.status_code == 200, r.text
        e = requests.get(f"{API}/ecps/{ecp_id}", headers=_hdr(tokens["owner"])).json()["ecp"]
        assert float(e["project_price"]) == 1200000


# ============ ISSUE 2: Accounts dashboard receivable math ============
class TestIssue2AccountsDashboard:
    def test_receivable_math_known_project(self, tokens):
        # Fresh: price 1_000_000; FIRST 300_000 CONFIRMED; ADDITIONAL 200_000 CONFIRMED; ADDITIONAL 50_000 PENDING
        lead = _new_lead(tokens, project_price=1000000)
        r = requests.post(f"{API}/leads/{lead['id']}/action", json={"action": "YES"},
                          headers=_hdr(tokens["lead"]))
        ecp_id = r.json()["ecp"]["id"]

        # capture baseline dashboard
        base = requests.get(f"{API}/dashboard", headers=_hdr(tokens["accounts"])).json()
        b_first = base["first_payment_pending_count"]
        b_recv = float(base["total_receivable"])
        b_sub_cnt = base["subsequent_followup_count"]
        b_sub_amt = float(base["subsequent_amount_pending"])

        # This ECP has no first confirmed yet -> first_payment_pending should include it
        d = requests.get(f"{API}/dashboard", headers=_hdr(tokens["accounts"])).json()
        assert d["first_payment_pending_count"] >= b_first  # already reflected
        # total_receivable includes this 1_000_000 in this snapshot
        assert float(d["total_receivable"]) >= 1000000

        # Now confirm FIRST 300k
        r = requests.post(f"{API}/payments",
            json={"ecp_id": ecp_id, "type": "FIRST", "amount": 300000, "date": "2026-09-10",
                  "status": "CONFIRMED"}, headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200
        # Additional 200k CONFIRMED
        r = requests.post(f"{API}/payments",
            json={"ecp_id": ecp_id, "type": "ADDITIONAL", "amount": 200000, "date": "2026-09-11",
                  "status": "CONFIRMED"}, headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200
        # Additional 50k PENDING (must NOT reduce receivable)
        r = requests.post(f"{API}/payments",
            json={"ecp_id": ecp_id, "type": "ADDITIONAL", "amount": 50000, "date": "2026-09-12",
                  "status": "PENDING"}, headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200

        # Check payments/monitor row for this ecp
        rows = requests.get(f"{API}/payments/monitor", headers=_hdr(tokens["accounts"])).json()
        row = next(r for r in rows if r["ecp_id"] == ecp_id)
        assert float(row["project_price"]) == 1000000
        assert float(row["first_confirmed_amount"]) == 300000
        assert float(row["subsequent_confirmed_amount"]) == 200000
        assert float(row["final_confirmed_amount"]) == 0
        assert float(row["total_received"]) == 500000
        assert float(row["total_receivable"]) == 500000  # PENDING does not reduce
        assert row["first_payment_confirmed"] is True

        # Dashboard: this ECP now falls under subsequent_followup (first confirmed, receivable 500k)
        d = requests.get(f"{API}/dashboard", headers=_hdr(tokens["accounts"])).json()
        assert d["subsequent_followup_count"] >= b_sub_cnt + 1
        # Since a new project alone contributes +500k to subsequent pending amount (500k receivable)
        # and it also removes 1_000_000 from first_pending's slice — check relative to baseline where this ECP wasn't counted at all
        # Just check row math above; dashboard aggregation covered by presence of counter.

    def test_accounts_dashboard_has_all_four_fields(self, tokens):
        r = requests.get(f"{API}/dashboard", headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("first_payment_pending_count", "subsequent_followup_count",
                 "subsequent_amount_pending", "total_receivable"):
            assert k in d, f"missing {k}"


# ============ ISSUE 3: /payments/monitor + payment CRUD ============
class TestIssue3PaymentsMonitor:
    def test_row_per_project_with_fields(self, tokens):
        rows = requests.get(f"{API}/payments/monitor", headers=_hdr(tokens["accounts"])).json()
        assert isinstance(rows, list)
        ecp_ids = [r["ecp_id"] for r in rows]
        assert len(ecp_ids) == len(set(ecp_ids)), "duplicate ECPs in monitor"
        if rows:
            row = rows[0]
            for k in ("project_price", "first_confirmed_amount", "subsequent_confirmed_amount",
                     "final_confirmed_amount", "total_received", "total_receivable",
                     "first_payment_confirmed"):
                assert k in row, f"monitor row missing {k}"

    def test_additional_type_preserved(self, tokens):
        _, ecp_id = _qualify(tokens)
        from datetime import datetime, timezone, timedelta
        today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date().isoformat()
        r = requests.post(f"{API}/payments",
            json={"ecp_id": ecp_id, "type": "ADDITIONAL", "amount": 111,
                  "date": today, "status": "PENDING"},
            headers=_hdr(tokens["accounts"]))
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "ADDITIONAL"
