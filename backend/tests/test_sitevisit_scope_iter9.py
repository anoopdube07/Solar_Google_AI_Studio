"""Iteration 9 - Site Visit scope tests (team endpoint fix + full sv flow).
Resilient to transient 502/empty responses from ingress on multipart uploads.
"""
import os
import time
import uuid
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL"):
                BASE = ln.split("=", 1)[1].strip()
API = BASE.rstrip("/") + "/api"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 128


def _tok(u, p):
    return requests.post(f"{API}/auth/login", json={"username": u, "password": p}).json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _retry_json(method, url, tok, **kw):
    """Retry helper for transient 502/empty responses."""
    r = None
    for _ in range(5):
        r = requests.request(method, url, headers=_h(tok), **kw)
        if r.status_code != 502 and (r.text or "").strip():
            return r
        time.sleep(0.4)
    return r


# ---------- Team endpoint fix ----------
def test_team_endpoint_installation_manager_allowed():
    imgr = _tok("instmgr", "InstMgr@123")
    r = requests.get(f"{API}/users/team/INSTALLATION_MEMBER", headers=_h(imgr))
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    # instmem user should be there
    unames = [u.get("username") for u in data]
    assert "instmem" in unames, unames


def test_team_endpoint_dispatch_forbidden():
    disp = _tok("dispatch", "Disp@123")
    r = requests.get(f"{API}/users/team/INSTALLATION_MEMBER", headers=_h(disp))
    assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"


# ---------- Full site visit E2E (assign, photos, survey, complete) ----------
def _mk_lead_and_sv():
    owner = _tok("anoopdube07@gmail.com", "Owner@123")
    lead = _tok("lead", "Lead@123")
    imgr = _tok("instmgr", "InstMgr@123")
    imem = _tok("instmem", "InstMem@123")
    users = requests.get(f"{API}/users", headers=_h(owner)).json()
    mem = next(u for u in users if u["username"] == "instmem")
    ph = f"9{uuid.uuid4().int % 1000000000:09d}"
    lid = requests.post(f"{API}/leads", json={"name": "TEST_SV9", "phone": ph}, headers=_h(lead)).json()["id"]
    r = requests.post(f"{API}/leads/{lid}/action", json={"action": "SITE_VISIT", "remarks": "check"}, headers=_h(lead))
    assert r.status_code == 200, r.text
    sv = requests.get(f"{API}/site-visits", headers=_h(owner)).json()
    svid = next(s["id"] for s in sv if s["lead_id"] == lid)
    return owner, lead, imgr, imem, mem, lid, svid


def test_assign_by_installation_manager():
    owner, lead, imgr, imem, mem, lid, svid = _mk_lead_and_sv()
    r = requests.post(f"{API}/site-visits/{svid}/assign",
                      json={"assigned_user": mem["id"], "visit_date": "2026-06-01"},
                      headers=_h(imgr))
    assert r.status_code == 200, r.text


def test_assign_by_plain_manager_forbidden():
    owner, lead, imgr, imem, mem, lid, svid = _mk_lead_and_sv()
    mgr = _tok("manager", "Manager@123")
    r = requests.post(f"{API}/site-visits/{svid}/assign",
                      json={"assigned_user": mem["id"], "visit_date": "2026-06-01"},
                      headers=_h(mgr))
    assert r.status_code == 403, f"MANAGER should not assign; got {r.status_code}"


def _upload(svid, tok, geo=True):
    for _ in range(6):
        d = {"lat": "21.2", "lng": "81.6"} if geo else {}
        r = requests.post(f"{API}/site-visits/{svid}/photos", data=d,
                          files={"file": ("p.png", PNG, "image/png")}, headers=_h(tok))
        if r.status_code != 502 and (r.text or "").strip():
            return r
        time.sleep(0.4)
    return r


def test_photo_upload_limits_and_rbac():
    owner, lead, imgr, imem, mem, lid, svid = _mk_lead_and_sv()
    assert requests.post(f"{API}/site-visits/{svid}/assign",
                        json={"assigned_user": mem["id"], "visit_date": "2026-06-01"},
                        headers=_h(imgr)).status_code == 200
    # 3 successful
    for i in range(3):
        r = _upload(svid, imem, geo=True)
        assert r.status_code == 200, f"upload {i} -> {r.status_code} {r.text[:200]}"
        assert r.json()["geo"]["lat"] == 21.2
    # 4th blocked
    r = _upload(svid, imem, geo=False)
    assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text[:200]}"
    # dispatch cannot list
    disp = _tok("dispatch", "Disp@123")
    r = requests.get(f"{API}/site-visits/{svid}/photos", headers=_h(disp))
    assert r.status_code == 403
    # assigned member can list, count 3
    r = _retry_json("GET", f"{API}/site-visits/{svid}/photos", imem)
    assert r.status_code == 200
    assert len(r.json()["photos"]) == 3


def test_survey_validation_and_completion():
    owner, lead, imgr, imem, mem, lid, svid = _mk_lead_and_sv()
    assert requests.post(f"{API}/site-visits/{svid}/assign",
                        json={"assigned_user": mem["id"], "visit_date": "2026-06-01"},
                        headers=_h(imgr)).status_code == 200

    # missing structure_height -> 400
    body = {"structure_height": "", "earthing_cable_length": "1", "dc_cable_length": "2",
            "ac_cable_length": "3", "surveyor_name": "X", "extra_materials": []}
    r = requests.post(f"{API}/site-visits/{svid}/complete", json=body, headers=_h(imem))
    assert r.status_code == 400, r.text

    # each missing field -> 400
    for k in ["earthing_cable_length", "dc_cable_length", "ac_cable_length", "surveyor_name"]:
        b = {"structure_height": "5", "earthing_cable_length": "1", "dc_cable_length": "2",
             "ac_cable_length": "3", "surveyor_name": "X", "extra_materials": []}
        b[k] = ""
        r = requests.post(f"{API}/site-visits/{svid}/complete", json=b, headers=_h(imem))
        assert r.status_code == 400, f"missing {k} should 400; got {r.status_code}"

    # extra_material referencing deactivated item -> 400
    it = requests.post(f"{API}/items", json={"name": f"TEST_SVMat{uuid.uuid4().hex[:5]}", "unit": "m"},
                       headers=_h(owner)).json()
    requests.patch(f"{API}/items/{it['id']}", json={"active": False}, headers=_h(owner))
    r = requests.post(f"{API}/site-visits/{svid}/complete", json={
        "structure_height": "5", "earthing_cable_length": "1", "dc_cable_length": "2",
        "ac_cable_length": "3", "surveyor_name": "Surv",
        "extra_materials": [{"item_id": it["id"], "item_name": it["name"], "quantity": 2, "unit": "m"}]
    }, headers=_h(imem))
    assert r.status_code == 400, f"deactivated item should 400; got {r.status_code} {r.text}"

    # valid with active item -> 200; lead back to Lead Team, ecp still null
    act = requests.post(f"{API}/items", json={"name": f"TEST_SVMat2{uuid.uuid4().hex[:5]}", "unit": "m"},
                        headers=_h(owner)).json()
    r = requests.post(f"{API}/site-visits/{svid}/complete", json={
        "structure_height": "5", "earthing_cable_length": "1", "dc_cable_length": "2",
        "ac_cable_length": "3", "surveyor_name": "Surv",
        "extra_materials": [{"item_id": act["id"], "item_name": act["name"], "quantity": 2, "unit": "m"}]
    }, headers=_h(imem))
    assert r.status_code == 200, r.text

    lead = _tok("lead", "Lead@123")
    bundle = requests.get(f"{API}/leads/{lid}", headers=_h(lead)).json()
    assert bundle["lead"]["action_required"] is True
    assert bundle["lead"]["status"] == "PENDING"
    assert bundle["ecp"] is None
