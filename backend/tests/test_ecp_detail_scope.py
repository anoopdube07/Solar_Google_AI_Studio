"""IDOR fix verification for GET /api/ecps/{ecp_id} scope parity with list."""
import os
import pytest
import requests
from pathlib import Path

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")

BASE = _load_url().rstrip("/")
API = f"{BASE}/api"

CREDS = {
    "OWNER": ("anoopdube07@gmail.com", "Owner@123"),
    "MANAGER": ("manager", "Manager@123"),
    "LEAD": ("lead", "Lead@123"),
    "REGISTRATION": ("registration", "Reg@123"),
    "ACCOUNTS": ("accounts", "Acct@123"),
    "DISPATCH": ("dispatch", "Disp@123"),
    "INSTALLATION_MANAGER": ("instmgr", "InstMgr@123"),
    "INSTALLATION_MEMBER": ("instmem", "InstMem@123"),
    "COMPLAINT": ("complaint", "Comp@123"),
}


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=15)
    assert r.status_code == 200, f"login failed {u}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def tokens():
    out = {}
    for role, (u, p) in CREDS.items():
        d = _login(u, p)
        out[role] = {"token": d["token"], "user": d["user"]}
    return out


def _h(tokens, role):
    return {"Authorization": f"Bearer {tokens[role]['token']}"}


@pytest.fixture(scope="module")
def all_ecps(tokens):
    r = requests.get(f"{API}/ecps", headers=_h(tokens, "OWNER"), timeout=30)
    assert r.status_code == 200
    return r.json()


def _pick(all_ecps, pred):
    for e in all_ecps:
        if pred(e):
            return e
    return None


# ---------- List/detail scope parity ----------
@pytest.mark.parametrize("role", ["OWNER", "MANAGER", "LEAD", "ACCOUNTS", "REGISTRATION", "DISPATCH", "INSTALLATION_MANAGER", "INSTALLATION_MEMBER"])
def test_list_detail_parity(tokens, role):
    r = requests.get(f"{API}/ecps", headers=_h(tokens, role), timeout=30)
    assert r.status_code == 200, r.text
    listed = r.json()
    # Sample up to 5 to keep it fast
    for e in listed[:5]:
        d = requests.get(f"{API}/ecps/{e['id']}", headers=_h(tokens, role), timeout=15)
        assert d.status_code == 200, f"{role} list contains id={e['id']} but detail returned {d.status_code}"
        assert d.json()["ecp"]["id"] == e["id"]


# ---------- COMPLAINT blocked ----------
def test_complaint_gets_404_for_any_ecp(tokens, all_ecps):
    # list should be empty/blocked
    r = requests.get(f"{API}/ecps", headers=_h(tokens, "COMPLAINT"), timeout=15)
    assert r.status_code == 200
    assert r.json() == []
    if all_ecps:
        d = requests.get(f"{API}/ecps/{all_ecps[0]['id']}", headers=_h(tokens, "COMPLAINT"), timeout=15)
        assert d.status_code == 404


# ---------- DISPATCH: only DISPATCH stage ----------
def test_dispatch_only_dispatch_stage(tokens, all_ecps):
    non_dispatch = _pick(all_ecps, lambda e: e.get("current_stage") != "DISPATCH")
    if non_dispatch:
        d = requests.get(f"{API}/ecps/{non_dispatch['id']}", headers=_h(tokens, "DISPATCH"), timeout=15)
        assert d.status_code == 404, f"DISPATCH could read stage={non_dispatch['current_stage']}"
    dispatch_e = _pick(all_ecps, lambda e: e.get("current_stage") == "DISPATCH")
    if dispatch_e:
        d = requests.get(f"{API}/ecps/{dispatch_e['id']}", headers=_h(tokens, "DISPATCH"), timeout=15)
        assert d.status_code == 200
        body = d.json()
        # scrubbing check
        assert "project_price" not in body["ecp"]
        assert body["payments"] == []


# ---------- REGISTRATION allowed stages ----------
def test_registration_scope(tokens, all_ecps):
    allowed = {"REGISTRATION_1", "REGISTRATION_2", "NET_METERING"}
    for e in all_ecps:
        if e.get("current_stage") not in allowed:
            d = requests.get(f"{API}/ecps/{e['id']}", headers=_h(tokens, "REGISTRATION"), timeout=15)
            assert d.status_code == 404, f"REGISTRATION could read stage={e['current_stage']}"
            break
    for e in all_ecps:
        if e.get("current_stage") in allowed:
            d = requests.get(f"{API}/ecps/{e['id']}", headers=_h(tokens, "REGISTRATION"), timeout=15)
            assert d.status_code == 200
            break


# ---------- INSTALLATION_MEMBER: assigned + right stages only ----------
def test_installation_member_scope(tokens, all_ecps):
    mem_id = tokens["INSTALLATION_MEMBER"]["user"]["id"]
    # An ECP NOT assigned to member OR not in install stages -> 404
    off = _pick(all_ecps, lambda e: e.get("responsible_user") != mem_id or e.get("current_stage") not in ("INSTALLATION", "NET_METERING"))
    if off:
        d = requests.get(f"{API}/ecps/{off['id']}", headers=_h(tokens, "INSTALLATION_MEMBER"), timeout=15)
        assert d.status_code == 404


# ---------- Non-existent id ----------
def test_nonexistent_ecp_404(tokens):
    d = requests.get(f"{API}/ecps/does-not-exist-xyz", headers=_h(tokens, "OWNER"), timeout=15)
    assert d.status_code == 404
