"""Phase 3: Documents gate + Pending Documents + RBAC + storage + release."""
import uuid
import pytest
import requests

BASE_URL = None
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = (BASE_URL or "").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "owner":        ("anoopdube07@gmail.com", "Owner@123"),
    "manager":      ("manager", "Manager@123"),
    "lead":         ("lead", "Lead@123"),
    "registration": ("registration", "Reg@123"),
    "accounts":     ("accounts", "Acct@123"),
    "dispatch":     ("dispatch", "Disp@123"),
    "installation": ("installation", "Install@123"),
}

# Tiny valid PNG (1x1 transparent-ish)
PNG_BYTES = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
             b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
             b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200, f"login {u}: {r.status_code} {r.text}"
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="session")
def tokens():
    return {k: _login(u, p) for k, (u, p) in CREDS.items()}


def _phone():
    return f"95{uuid.uuid4().int % 100000000:08d}"


def _mk_lead(tokens, financing=False):
    payload = {"name": f"TEST_P3_{uuid.uuid4().hex[:6]}", "phone": _phone(),
               "financing_required": financing}
    r = requests.post(f"{API}/leads", json=payload, headers=H(tokens["lead"]))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _yes(tokens, lid, who="lead"):
    r = requests.post(f"{API}/leads/{lid}/action", json={"action": "YES"}, headers=H(tokens[who]))
    return r


def _upload(tokens, lid, doc_type, who="lead", data=PNG_BYTES, ct="image/png", fname=None):
    files_factory = lambda: {"file": (fname or f"{doc_type.lower()}.png", data, ct)}
    # Retry once on 502 (transient cloudflare gateway)
    for _ in range(3):
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": doc_type},
                          files=files_factory(), headers=H(tokens[who]), timeout=60)
        if r.status_code != 502:
            return r
    return r


def _get_lead(tokens, lid, who="lead"):
    return requests.get(f"{API}/leads/{lid}", headers=H(tokens[who]))


def _get_ecp(tokens, ecp_id, who="lead"):
    return requests.get(f"{API}/ecps/{ecp_id}", headers=H(tokens[who]))


# ============ 1. YES creates exactly one ECP at PENDING_DOCUMENTS ============
class TestYesCreatesPendingDocsEcp:
    def test_yes_creates_pending_docs_ecp(self, tokens):
        lid = _mk_lead(tokens)
        r = _yes(tokens, lid)
        assert r.status_code == 200, r.text
        lead = _get_lead(tokens, lid).json()["lead"]
        assert lead["ecp_id"]
        ecp = _get_ecp(tokens, lead["ecp_id"]).json()["ecp"]
        assert ecp["current_stage"] == "PENDING_DOCUMENTS"
        assert ecp["current_team"] == "LEAD"
        assert ecp.get("documents_released") is False

    def test_second_yes_returns_400(self, tokens):
        lid = _mk_lead(tokens)
        assert _yes(tokens, lid).status_code == 200
        r2 = _yes(tokens, lid)
        assert r2.status_code == 400


# ============ 2. Registration cannot see PENDING_DOCUMENTS ============
class TestRegistrationBlockedWhilePending:
    def test_pending_ecp_absent_from_registration_ecps_list(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        lead = _get_lead(tokens, lid).json()["lead"]
        ecp_id = lead["ecp_id"]
        r = requests.get(f"{API}/ecps", headers=H(tokens["registration"]))
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        assert ecp_id not in ids

    def test_registration_get_docs_403_while_pending(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        r = requests.get(f"{API}/leads/{lid}/documents", headers=H(tokens["registration"]))
        assert r.status_code == 403

    def test_no_reg1_tasks_while_pending(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        lead = _get_lead(tokens, lid).json()["lead"]
        r = _get_ecp(tokens, lead["ecp_id"], who="owner").json()
        tasks = r.get("tasks", [])
        assert tasks == [] or all(t.get("stage") != "REGISTRATION_1" for t in tasks)


# ============ 3. All doc types upload works, response schema ============
class TestUploadEachDocType:
    def test_upload_pan_returns_status(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        r = _upload(tokens, lid, "PAN")
        assert r.status_code == 200, r.text
        b = r.json()
        assert "documents_status" in b and "released" in b
        assert b["released"] is False
        assert "PAN" in b["documents_status"]["uploaded_types"]

    @pytest.mark.parametrize("dt", ["AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK",
                                     "BANK_STATEMENT", "CANCELLED_CHEQUE",
                                     "PROPERTY_PAPER", "TAX_RECEIPT"])
    def test_upload_each_type(self, tokens, dt):
        lid = _mk_lead(tokens, financing=True)  # so finance types are allowed anytime
        _yes(tokens, lid)
        r = _upload(tokens, lid, dt)
        assert r.status_code == 200, f"{dt}: {r.text}"
        assert dt in r.json()["documents_status"]["uploaded_types"]


# ============ 4. Bank alternatives — any one satisfies ============
class TestBankAlternatives:
    @pytest.mark.parametrize("bank_type", ["BANK_PASSBOOK", "BANK_STATEMENT", "CANCELLED_CHEQUE"])
    def test_any_bank_completes_no_financing(self, tokens, bank_type):
        lid = _mk_lead(tokens, financing=False)
        _yes(tokens, lid)
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL"]:
            assert _upload(tokens, lid, t).status_code == 200
        r = _upload(tokens, lid, bank_type)
        assert r.status_code == 200
        body = r.json()
        assert body["documents_status"]["complete"] is True
        assert body["released"] is True


# ============ 5. Finance=YES: bank alone not enough; finance doc completes ============
class TestFinanceRequirement:
    def test_finance_yes_needs_finance_doc(self, tokens):
        lid = _mk_lead(tokens, financing=True)
        _yes(tokens, lid)
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK"]:
            r = _upload(tokens, lid, t)
            assert r.status_code == 200
        body = r.json()
        assert body["documents_status"]["complete"] is False
        assert body["released"] is False
        lead = _get_lead(tokens, lid).json()
        assert lead["ecp"]["current_stage"] == "PENDING_DOCUMENTS"

        # Add property paper -> completes and releases
        r = _upload(tokens, lid, "PROPERTY_PAPER")
        assert r.status_code == 200
        assert r.json()["released"] is True
        ecp = _get_ecp(tokens, lead["lead"]["ecp_id"]).json()["ecp"]
        assert ecp["current_stage"] == "REGISTRATION_1"
        assert ecp["current_team"] == "REGISTRATION"

    def test_tax_receipt_also_satisfies_finance(self, tokens):
        lid = _mk_lead(tokens, financing=True)
        _yes(tokens, lid)
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_STATEMENT", "TAX_RECEIPT"]:
            r = _upload(tokens, lid, t)
            assert r.status_code == 200
        assert r.json()["released"] is True


# ============ 6. Finance=NO auto-releases with base+bank ============
class TestFinanceNoReleases:
    def test_no_finance_auto_release_creates_reg1_tasks(self, tokens):
        lid = _mk_lead(tokens, financing=False)
        _yes(tokens, lid)
        ecp_id = _get_lead(tokens, lid).json()["lead"]["ecp_id"]
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL", "CANCELLED_CHEQUE"]:
            r = _upload(tokens, lid, t)
        assert r.json()["released"] is True
        data = _get_ecp(tokens, ecp_id).json()
        assert data["ecp"]["current_stage"] == "REGISTRATION_1"
        assert data["ecp"]["current_team"] == "REGISTRATION"
        reg1 = [t for t in data["tasks"] if t["stage"] == "REGISTRATION_1"]
        applicable = [t for t in reg1 if t.get("applicable")]
        assert len(applicable) == 3  # Phase 4: base 3 applicable when financing False
        # No financing tasks applicable when financing is False
        names = {t["task_name"] for t in applicable}
        assert {"Consumer Request", "CVA Print & Sign", "Feasibility Report Upload"} == names


# ============ 7. Financing YES creates 3 extra loan tasks after release ============
class TestFinancingLoanTasks:
    def test_reg1_has_6_tasks_when_financing(self, tokens):
        lid = _mk_lead(tokens, financing=True)
        _yes(tokens, lid)
        ecp_id = _get_lead(tokens, lid).json()["lead"]["ecp_id"]
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK", "PROPERTY_PAPER"]:
            _upload(tokens, lid, t)
        data = _get_ecp(tokens, ecp_id).json()
        reg1 = [t for t in data["tasks"] if t["stage"] == "REGISTRATION_1"]
        applicable = [t for t in reg1 if t.get("applicable")]
        assert len(applicable) == 6  # Phase 4: 3 base + 3 loan
        loan = {t["task_name"] for t in applicable if t["task_name"] in ("Loan Documentation", "Loan Filing", "Bank Submission")}
        assert loan == {"Loan Documentation", "Loan Filing", "Bank Submission"}


# ============ 8. Missing doc -> release endpoint 400 ============
class TestManualRelease400:
    def test_release_400_when_incomplete(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        _upload(tokens, lid, "PAN")
        r = requests.post(f"{API}/leads/{lid}/documents/release", headers=H(tokens["lead"]))
        assert r.status_code == 400
        assert "incomplete" in r.text.lower() or "required" in r.text.lower()


# ============ 9. RBAC: non-owner LEAD gets 403 ============
class TestOwnershipRbac:
    @pytest.fixture(scope="class")
    def other_lead(self, tokens):
        uname = f"lead_p3_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/users", json={
            "username": uname, "password": "Xx123456!", "name": uname,
            "role": "LEAD", "phone": _phone()
        }, headers=H(tokens["owner"]))
        assert r.status_code == 200, r.text
        user_id = r.json()["id"]
        return {"id": user_id, "username": uname, "token": _login(uname, "Xx123456!")}

    def test_other_lead_upload_list_download_release_403(self, tokens, other_lead):
        other_lead_token = other_lead["token"]
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        _upload(tokens, lid, "PAN")  # owner-lead uploads one first
        # other lead: upload
        files = {"file": ("x.png", PNG_BYTES, "image/png")}
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": "AADHAAR"},
                          files=files, headers=H(other_lead_token))
        assert r.status_code == 403
        # list
        r = requests.get(f"{API}/leads/{lid}/documents", headers=H(other_lead_token))
        assert r.status_code == 403
        # release
        r = requests.post(f"{API}/leads/{lid}/documents/release", headers=H(other_lead_token))
        assert r.status_code == 403

    def test_reassign_swaps_access(self, tokens, other_lead):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        _upload(tokens, lid, "PAN")
        r = requests.post(f"{API}/leads/{lid}/reassign",
                          json={"assigned_user": other_lead["id"]}, headers=H(tokens["owner"]))
        assert r.status_code == 200, r.text
        # Original lead now gets 403
        r = requests.get(f"{API}/leads/{lid}/documents", headers=H(tokens["lead"]))
        assert r.status_code == 403
        # New owner (other) gets 200
        r = requests.get(f"{API}/leads/{lid}/documents", headers=H(other_lead["token"]))
        assert r.status_code == 200


# ============ 10. Unauthorized roles blocked ============
class TestUnauthorizedRoles:
    def test_accounts_dispatch_installation_403(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        for who in ("accounts", "dispatch", "installation"):
            r = requests.get(f"{API}/leads/{lid}/documents", headers=H(tokens[who]))
            assert r.status_code == 403, f"{who} list expected 403 got {r.status_code}"
            files = {"file": ("x.png", PNG_BYTES, "image/png")}
            r = requests.post(f"{API}/leads/{lid}/documents",
                              data={"doc_type": "PAN"}, files=files, headers=H(tokens[who]))
            assert r.status_code == 403, f"{who} upload expected 403 got {r.status_code}"


# ============ 11. Unsupported file types + oversized ============
class TestFileValidation:
    def test_txt_rejected(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        files = {"file": ("bad.txt", b"hello", "text/plain")}
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": "PAN"},
                          files=files, headers=H(tokens["lead"]))
        assert r.status_code == 400
        assert "JPG" in r.text or "PDF" in r.text

    def test_octet_stream_rejected(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        files = {"file": ("bad.exe", b"MZ\x90\x00", "application/octet-stream")}
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": "PAN"},
                          files=files, headers=H(tokens["lead"]))
        assert r.status_code == 400

    def test_oversized_rejected(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        big = b"\x89PNG\r\n\x1a\n" + b"a" * (11 * 1024 * 1024)
        files = {"file": ("big.png", big, "image/png")}
        r = requests.post(f"{API}/leads/{lid}/documents", data={"doc_type": "PAN"},
                          files=files, headers=H(tokens["lead"]))
        assert r.status_code == 400
        assert "10" in r.text or "large" in r.text.lower()


# ============ 12. Re-upload preserves history ============
class TestReuploadHistory:
    def test_replace_moves_old_to_history(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        r1 = _upload(tokens, lid, "PAN", fname="v1.png")
        assert r1.status_code == 200
        r2 = _upload(tokens, lid, "PAN", fname="v2.png")
        assert r2.status_code == 200
        r = requests.get(f"{API}/leads/{lid}/documents", headers=H(tokens["lead"])).json()
        pans_current = [d for d in r["documents"] if d["doc_type"] == "PAN"]
        pans_hist = [d for d in r["history"] if d["doc_type"] == "PAN"]
        assert len(pans_current) == 1
        assert pans_current[0]["original_filename"] == "v2.png"
        assert len(pans_hist) >= 1
        assert pans_hist[0]["status"] == "REPLACED"
        assert pans_hist[0]["uploaded_by_name"]


# ============ 13. Financing change while pending ============
class TestFinancingFlipWhilePending:
    def test_flip_no_to_yes_blocks_release(self, tokens):
        lid = _mk_lead(tokens, financing=False)
        _yes(tokens, lid)
        # Flip to YES before uploads
        r = requests.post(f"{API}/leads/{lid}/financing",
                          json={"financing_required": True}, headers=H(tokens["lead"]))
        assert r.status_code == 200
        # Upload base+bank -> should NOT release
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK"]:
            r = _upload(tokens, lid, t)
        assert r.json()["released"] is False
        ecp_id = _get_lead(tokens, lid).json()["lead"]["ecp_id"]
        ecp = _get_ecp(tokens, ecp_id).json()["ecp"]
        assert ecp["current_stage"] == "PENDING_DOCUMENTS"
        # Add finance doc -> releases
        r = _upload(tokens, lid, "PROPERTY_PAPER")
        assert r.json()["released"] is True

    def test_flip_yes_to_no_allows_release(self, tokens):
        lid = _mk_lead(tokens, financing=True)
        _yes(tokens, lid)
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK"]:
            r = _upload(tokens, lid, t)
        assert r.json()["released"] is False
        # Flip to NO
        r = requests.post(f"{API}/leads/{lid}/financing",
                          json={"financing_required": False}, headers=H(tokens["lead"]))
        assert r.status_code == 200
        # Trigger status: upload same PAN again OR call release
        r = requests.post(f"{API}/leads/{lid}/documents/release", headers=H(tokens["lead"]))
        assert r.status_code == 200
        ecp_id = _get_lead(tokens, lid).json()["lead"]["ecp_id"]
        ecp = _get_ecp(tokens, ecp_id).json()["ecp"]
        assert ecp["current_stage"] == "REGISTRATION_1"


# ============ 14. Download returns bytes ============
class TestDownload:
    def test_download_returns_png(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        r = _upload(tokens, lid, "PAN")
        doc_id = r.json()["document"]["id"]
        r = requests.get(f"{API}/leads/{lid}/documents/{doc_id}/download",
                         headers=H(tokens["lead"]))
        assert r.status_code == 200
        assert r.content.startswith(b"\x89PNG")
        assert "image" in (r.headers.get("Content-Type") or "").lower() or "png" in (r.headers.get("Content-Type") or "").lower()


# ============ 15. Grandfathering: enrich existing REGISTRATION_1 ECPs unaffected ============
class TestGrandfathering:
    def test_reg1_ecp_still_visible_to_registration(self, tokens):
        # Create + fully release one
        lid = _mk_lead(tokens, financing=False)
        _yes(tokens, lid)
        for t in ["PAN", "AADHAAR", "ELECTRICITY_BILL", "BANK_PASSBOOK"]:
            _upload(tokens, lid, t)
        ecp_id = _get_lead(tokens, lid).json()["lead"]["ecp_id"]
        # Registration sees it now
        ids = [e["id"] for e in requests.get(f"{API}/ecps", headers=H(tokens["registration"])).json()]
        assert ecp_id in ids
        # And can GET documents (read) once released
        r = requests.get(f"{API}/leads/{lid}/documents", headers=H(tokens["registration"]))
        assert r.status_code == 200


# ============ 16. Dashboard counters ============
class TestDashboardCounters:
    def test_registration_awaiting_documents_counter(self, tokens):
        # Create at least one pending
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        r = requests.get(f"{API}/dashboard", headers=H(tokens["registration"]))
        assert r.status_code == 200
        data = r.json()
        assert "pending_documents" in data
        assert data["pending_documents"] >= 1

    def test_owner_pending_documents_counter(self, tokens):
        r = requests.get(f"{API}/dashboard", headers=H(tokens["owner"]))
        assert r.status_code == 200
        # ecp counters — owner sees PENDING_DOCUMENTS somewhere
        body = r.json()
        # Owner dashboard has ecp block per spec
        assert "ecp" in body or "pending_documents" in body

    def test_lead_awaiting_documents_counter(self, tokens):
        lid = _mk_lead(tokens)
        _yes(tokens, lid)
        r = requests.get(f"{API}/dashboard", headers=H(tokens["lead"]))
        assert r.status_code == 200
        assert "pending_documents" in r.json()
