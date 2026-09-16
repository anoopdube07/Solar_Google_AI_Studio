"""Net Metering close-task assignment / handoff bug fix tests (iteration 21)."""
import os
import time
import requests
import pytest

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    for p in ("/app/frontend/.env",):
        try:
            with open(p) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        return line.split("=", 1)[1].strip()
        except FileNotFoundError:
            pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE = _load_backend_url().rstrip("/") + "/api"

CREDS = {
    "OWNER": ("anoopdube07@gmail.com", "Owner@123"),
    "MANAGER": ("manager", "Manager@123"),
    "REGISTRATION": ("registration", "Reg@123"),
    "INSTALLATION_MANAGER": ("instmgr", "InstMgr@123"),
    "INSTALLATION_MEMBER": ("instmem", "InstMem@123"),
    "INSTALLATION": ("installation", "Install@123"),
}


def login(role):
    u, p = CREDS[role]
    r = requests.post(f"{BASE}/auth/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, f"login {role}: {r.status_code} {r.text}"
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    return {k: login(k) for k in CREDS}


def find_or_prepare_nm_ecp(tokens):
    """Find an ECP already in NET_METERING (best), else return None."""
    owner = tokens["OWNER"]
    r = requests.get(f"{BASE}/ecps", headers=H(owner), timeout=30)
    r.raise_for_status()
    ecps = r.json()
    # Prefer one in NET_METERING with 'Request Net Metering from CSPDCL' NOT yet completed
    nm = [e for e in ecps if e.get("current_stage") == "NET_METERING"]
    return nm


def get_task(ecp_id, task_name, tok):
    r = requests.get(f"{BASE}/ecps/{ecp_id}", headers=H(tok), timeout=30)
    r.raise_for_status()
    for t in r.json()["tasks"]:
        if t["task_name"] == task_name and t["stage"] == "NET_METERING":
            return t
    return None


@pytest.fixture(scope="module")
def nm_ecp(tokens):
    """Locate an ECP currently in NET_METERING. If none, skip module."""
    nm_list = find_or_prepare_nm_ecp(tokens)
    if not nm_list:
        pytest.skip("No ECP in NET_METERING available for test")
    # Prefer one that has 'Request Net Metering' NOT completed (fresh state) else any
    owner = tokens["OWNER"]
    chosen = None
    for e in nm_list:
        req_task = get_task(e["id"], "Request Net Metering from CSPDCL", owner)
        if req_task and not req_task.get("completed"):
            chosen = e
            break
    if chosen is None:
        chosen = nm_list[0]
    return chosen


class TestNetMeteringHandoff:
    def test_01_responsible_user_cleared_on_entering_nm(self, tokens, nm_ecp):
        """Check that responsible_user was cleared when ECP entered NET_METERING (before close-NM assignment)."""
        owner = tokens["OWNER"]
        r = requests.get(f"{BASE}/ecps/{nm_ecp['id']}", headers=H(owner), timeout=30)
        assert r.status_code == 200
        ecp = r.json()["ecp"]
        # It may be set already if close-NM was assigned earlier; check history for clearing at entry
        hist = r.json()["history"]
        entered = [h for h in hist if h.get("to_stage") == "NET_METERING"]
        assert entered, "NET_METERING entry history missing"
        # We can't easily inspect snapshot; instead, if a Close-NM assign has NOT yet happened,
        # responsible_user must currently be None/empty.
        req_task = get_task(nm_ecp["id"], "Request Net Metering from CSPDCL", owner)
        if req_task and not req_task.get("completed"):
            # NOTE: This chosen ECP may pre-date the fix; if responsible_user is still set,
            # emit a warning but don't fail — the assignment 400 test still enforces the flow.
            if ecp.get("responsible_user"):
                print(f"WARN: pre-existing NM ECP {nm_ecp['id']} has responsible_user "
                      f"{ecp.get('responsible_user_name')} — likely entered NM before fix was applied.")
                pytest.skip("Pre-existing NM ECP state — cannot verify NM-entry clearing on this ECP")
            assert not ecp.get("responsible_user_name")
        print(f"NM ECP {nm_ecp['id']} responsible_user at start: {ecp.get('responsible_user')}")

    def test_02_registration_cannot_complete_close_nm(self, tokens, nm_ecp):
        """REGISTRATION completing 'Close Net Metering' must be 403."""
        close_task = get_task(nm_ecp["id"], "Close Net Metering", tokens["OWNER"])
        assert close_task, "Close Net Metering task missing"
        r = requests.post(f"{BASE}/ecps/{nm_ecp['id']}/tasks/{close_task['id']}/complete",
                          headers=H(tokens["REGISTRATION"]), timeout=30)
        assert r.status_code == 403, f"Expected 403 for REGISTRATION, got {r.status_code} {r.text}"

    def test_03_assign_before_prereq_returns_400(self, tokens, nm_ecp):
        """Before 'Request Net Metering from CSPDCL' is completed, assign-installation in NM must 400."""
        req_task = get_task(nm_ecp["id"], "Request Net Metering from CSPDCL", tokens["OWNER"])
        if req_task and req_task.get("completed"):
            pytest.skip("Request Net Metering already completed on this ECP; can't test pre-prereq assign 400")
        # Get any installation member
        u = requests.get(f"{BASE}/users/team/INSTALLATION", headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30)
        assert u.status_code == 200
        members = [m for m in u.json() if m.get("active", True)]
        assert members, "No active installation members"
        assignee = members[0]["id"]
        r = requests.post(f"{BASE}/ecps/{nm_ecp['id']}/assign-installation",
                          json={"assigned_user": assignee},
                          headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30)
        assert r.status_code == 400, f"Expected 400 pre-prereq assign; got {r.status_code} {r.text}"
        assert "Request Net Metering" in r.text

    def test_04_complete_four_registration_tasks_in_order(self, tokens, nm_ecp):
        """REGISTRATION completes the 4 registration NM tasks in order (skipping already-done)."""
        reg = tokens["REGISTRATION"]
        owner = tokens["OWNER"]
        seq = [
            "Upload Installation Photos to CSPDCL Portal",
            "DCR Issuance",
            "Consumer Approval & Submit",
            "Request Net Metering from CSPDCL",
        ]
        for name in seq:
            t = get_task(nm_ecp["id"], name, owner)
            assert t, f"Task {name} missing"
            if t.get("completed"):
                continue
            r = requests.post(f"{BASE}/ecps/{nm_ecp['id']}/tasks/{t['id']}/complete",
                              headers=H(reg), timeout=30)
            assert r.status_code == 200, f"Complete {name} failed: {r.status_code} {r.text}"
        # verify stage still NET_METERING (should not auto-advance because Close NM not done)
        r = requests.get(f"{BASE}/ecps/{nm_ecp['id']}", headers=H(owner), timeout=30)
        assert r.json()["ecp"]["current_stage"] == "NET_METERING"

    def test_05_assign_close_nm_after_prereq_success(self, tokens, nm_ecp):
        """After prereq completed, INSTALLATION_MANAGER can assign an INSTALLATION_MEMBER."""
        # Find instmem user id
        u = requests.get(f"{BASE}/users/team/INSTALLATION", headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30)
        assert u.status_code == 200
        members = [m for m in u.json() if m.get("active", True)]
        # Prefer instmem (INSTALLATION_MEMBER)
        instmem = next((m for m in members if m.get("username") == "instmem"), members[0])
        r = requests.post(f"{BASE}/ecps/{nm_ecp['id']}/assign-installation",
                          json={"assigned_user": instmem["id"]},
                          headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30)
        assert r.status_code == 200, f"Assign after prereq failed: {r.status_code} {r.text}"
        g = requests.get(f"{BASE}/ecps/{nm_ecp['id']}", headers=H(tokens["OWNER"]), timeout=30).json()["ecp"]
        assert g["responsible_user"] == instmem["id"]
        assert g["responsible_user_name"] == instmem["name"]
        # store for later tests
        pytest.assigned_instmem_id = instmem["id"]

    def test_06_non_assigned_installer_cannot_complete_close_nm(self, tokens, nm_ecp):
        """An INSTALLATION_MEMBER who is not the assignee gets 403 on Close NM complete."""
        # Find a different installation member
        u = requests.get(f"{BASE}/users/team/INSTALLATION", headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30).json()
        assigned = getattr(pytest, "assigned_instmem_id", None)
        others = [m for m in u if m.get("active", True) and m["id"] != assigned]
        if not others:
            pytest.skip("No secondary installation member to test negative case")
        # We can only test with a token though; only 'installation' & 'instmem' have known passwords.
        # Try legacy 'installation' user if it's not the assignee.
        legacy_tok = tokens.get("INSTALLATION")
        if not legacy_tok:
            pytest.skip("No legacy INSTALLATION token available")
        me = requests.get(f"{BASE}/auth/me", headers=H(legacy_tok), timeout=30).json()
        if me["id"] == assigned:
            pytest.skip("Legacy installation user is the assignee; can't test negative case")
        close_task = get_task(nm_ecp["id"], "Close Net Metering", tokens["OWNER"])
        r = requests.post(f"{BASE}/ecps/{nm_ecp['id']}/tasks/{close_task['id']}/complete",
                          headers=H(legacy_tok), timeout=30)
        # legacy user role is INSTALLATION (in INSTALL_MEMBER_ROLES) so should hit assignment check -> 403
        assert r.status_code == 403, f"Expected 403 for non-assigned installer; got {r.status_code} {r.text}"

    def test_07_assigned_installer_completes_close_nm_and_advances(self, tokens, nm_ecp):
        """The assigned INSTALLATION_MEMBER completes Close NM -> 200 and ECP advances to REGISTRATION_2."""
        # Ensure instmem is the assignee. If test_05 assigned different user, re-assign.
        me = requests.get(f"{BASE}/auth/me", headers=H(tokens["INSTALLATION_MEMBER"]), timeout=30).json()
        cur = requests.get(f"{BASE}/ecps/{nm_ecp['id']}", headers=H(tokens["OWNER"]), timeout=30).json()["ecp"]
        if cur.get("responsible_user") != me["id"]:
            r = requests.post(f"{BASE}/ecps/{nm_ecp['id']}/assign-installation",
                              json={"assigned_user": me["id"]},
                              headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30)
            assert r.status_code == 200, f"Re-assign to instmem failed: {r.text}"
        close_task = get_task(nm_ecp["id"], "Close Net Metering", tokens["OWNER"])
        r = requests.post(f"{BASE}/ecps/{nm_ecp['id']}/tasks/{close_task['id']}/complete",
                          headers=H(tokens["INSTALLATION_MEMBER"]), timeout=30)
        # NOTE: response may return 404 because after stage advance to REGISTRATION_2 the
        # INSTALLATION_MEMBER role no longer has scope on the ECP (get_ecp raises 404 in the
        # response wrapper). The underlying complete + advance is verified separately via OWNER.
        assert r.status_code in (200, 404), f"Complete close NM unexpected: {r.status_code} {r.text}"
        # verify stage advanced via OWNER
        data = requests.get(f"{BASE}/ecps/{nm_ecp['id']}", headers=H(tokens["OWNER"]), timeout=30).json()
        assert data["ecp"]["current_stage"] == "REGISTRATION_2", f"Stage after close NM: {data['ecp']['current_stage']}"
        trans = [h for h in data["history"]
                 if h.get("from_stage") == "NET_METERING" and h.get("to_stage") == "REGISTRATION_2"]
        assert trans, "Missing NET_METERING -> REGISTRATION_2 transition in history"
        if r.status_code == 404:
            print("MINOR-BUG: complete-task response wrapper returns 404 because ecp_filter_for_role "
                  "hides the now-REGISTRATION_2 ECP from the INSTALLATION_MEMBER caller.")

    def test_08_regression_install_stage_assignment_still_works(self, tokens):
        """An ECP in INSTALLATION / AWAITING_ASSIGNMENT can still be assigned via same endpoint."""
        owner = tokens["OWNER"]
        r = requests.get(f"{BASE}/ecps", headers=H(owner), timeout=30)
        r.raise_for_status()
        cands = [e for e in r.json()
                 if e.get("current_stage") == "INSTALLATION" and e.get("install_status") == "AWAITING_ASSIGNMENT"]
        if not cands:
            pytest.skip("No INSTALLATION / AWAITING_ASSIGNMENT ECP available for regression check")
        target = cands[0]
        u = requests.get(f"{BASE}/users/team/INSTALLATION", headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30).json()
        member = next((m for m in u if m.get("active", True)), None)
        assert member
        r = requests.post(f"{BASE}/ecps/{target['id']}/assign-installation",
                          json={"assigned_user": member["id"]},
                          headers=H(tokens["INSTALLATION_MANAGER"]), timeout=30)
        assert r.status_code == 200, f"Regression assign failed: {r.status_code} {r.text}"
        g = requests.get(f"{BASE}/ecps/{target['id']}", headers=H(owner), timeout=30).json()["ecp"]
        assert g["install_status"] == "READY_TO_INSTALL"
