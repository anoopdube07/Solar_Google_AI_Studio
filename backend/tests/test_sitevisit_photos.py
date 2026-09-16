import os
import uuid
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL"):
                BASE = ln.split("=", 1)[1].strip()
API = BASE.rstrip("/") + "/api"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _tok(u, p):
    return requests.post(f"{API}/auth/login", json={"username": u, "password": p}).json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _upload_photo(svid, tok, geo=True):
    for _ in range(4):
        d = {"lat": "21.2", "lng": "81.6"} if geo else {}
        r = requests.post(f"{API}/site-visits/{svid}/photos", data=d,
                          files={"file": ("p.png", PNG, "image/png")}, headers=_h(tok))
        if r.status_code != 502 and (r.text or "").strip():
            return r
    return r


def test_sitevisit_photos_and_survey():
    owner = _tok("anoopdube07@gmail.com", "Owner@123")
    lead = _tok("lead", "Lead@123")
    imgr = _tok("instmgr", "InstMgr@123")
    imem = _tok("instmem", "InstMem@123")
    # find instmem user id
    users = requests.get(f"{API}/users", headers=_h(owner)).json()
    mem = next(u for u in users if u["username"] == "instmem")
    # create a lead + initiate site visit
    ph = f"9{uuid.uuid4().int % 1000000000:09d}"
    lid = requests.post(f"{API}/leads", json={"name": "SVTest", "phone": ph}, headers=_h(lead)).json()["id"]
    r = requests.post(f"{API}/leads/{lid}/action", json={"action": "SITE_VISIT", "remarks": "check"}, headers=_h(lead))
    assert r.status_code == 200, r.text
    sv = requests.get(f"{API}/site-visits", headers=_h(owner)).json()
    svid = next(s["id"] for s in sv if s["lead_id"] == lid)
    # manager assigns member
    r = requests.post(f"{API}/site-visits/{svid}/assign", json={"assigned_user": mem["id"], "visit_date": "2026-06-01"}, headers=_h(imgr))
    assert r.status_code == 200, r.text
    # upload photos: 3 ok, 4th rejected
    for i in range(3):
        r = _upload_photo(svid, imem, geo=True)
        assert r.status_code == 200, r.text
        assert r.json()["geo"]["lat"] == 21.2
    r = _upload_photo(svid, imem, geo=False)
    assert r.status_code == 400  # max 3
    # photo without geo allowed (delete one first not needed since already at 3 -> use a fresh check: list has 3)
    assert len(requests.get(f"{API}/site-visits/{svid}/photos", headers=_h(imem)).json()["photos"]) == 3
    # unauthorized photo access (dispatch) blocked
    disp = _tok("dispatch", "Disp@123")
    assert requests.get(f"{API}/site-visits/{svid}/photos", headers=_h(disp)).status_code == 403
    # complete missing field -> 400
    r = requests.post(f"{API}/site-visits/{svid}/complete", json={"structure_height": "", "earthing_cable_length": "1", "dc_cable_length": "2", "ac_cable_length": "3", "surveyor_name": "X", "extra_materials": []}, headers=_h(imem))
    assert r.status_code == 400
    # extra material with inactive item -> 400
    it = requests.post(f"{API}/items", json={"name": f"SVMat{uuid.uuid4().hex[:5]}", "unit": "m"}, headers=_h(owner)).json()
    requests.patch(f"{API}/items/{it['id']}", json={"active": False}, headers=_h(owner))
    r = requests.post(f"{API}/site-visits/{svid}/complete", json={"structure_height": "5", "earthing_cable_length": "1", "dc_cable_length": "2", "ac_cable_length": "3", "surveyor_name": "X", "extra_materials": [{"item_id": it["id"], "item_name": it["name"], "quantity": 2, "unit": "m"}]}, headers=_h(imem))
    assert r.status_code == 400
    # valid complete -> lead returns to Lead Team, no ECP
    act = requests.post(f"{API}/items", json={"name": f"SVMat2{uuid.uuid4().hex[:5]}", "unit": "m"}, headers=_h(owner)).json()
    r = requests.post(f"{API}/site-visits/{svid}/complete", json={"structure_height": "5", "earthing_cable_length": "1", "dc_cable_length": "2", "ac_cable_length": "3", "surveyor_name": "X", "extra_materials": [{"item_id": act["id"], "item_name": act["name"], "quantity": 2, "unit": "m"}]}, headers=_h(imem))
    assert r.status_code == 200, r.text
    bundle = requests.get(f"{API}/leads/{lid}", headers=_h(lead)).json()
    assert bundle["lead"]["action_required"] is True
    assert bundle["ecp"] is None
