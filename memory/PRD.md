# PRD — ECP Project Management & Lead Tracking System

## Original Problem Statement
Internal employee web app for a solar company so the OWNER can see the status of every Lead and ECP project — where it is, which team/person owns the next action, and which projects are stuck/delayed. Two separate workflows: Lead Qualification and ECP Execution. Full finalized business spec: `/app/memory/PHASE1_SPEC.md`.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`, `auth.py`, `workflow.py`, `extras.py`), MongoDB (UUID string ids), JWT username+password auth (Bearer token in login body, stored in localStorage as `ecp_token`).
- Frontend: React + Tailwind + shadcn/ui; role-based sidebar layout; sonner toasts. AuthContext bootstraps via `/api/auth/me`.
- PDF: ReportLab (quotation generation).

## User Personas / Roles (V1: one user = one role = one team)
OWNER, MANAGER (Process Owner), LEAD, REGISTRATION, ACCOUNTS, DISPATCH, INSTALLATION (+ future INSTALLATION_MANAGER, INSTALLATION_MEMBER, COMPLAINT roles seeded).

## Core Requirements (static — from Phase 1 spec)
- Lead: PENDING + 5 actions (YES/NO/FOLLOW_UP/SITE_VISIT/ESCALATION). Only Lead Team decides.
- YES auto-creates exactly one ECP (max 1 per lead lifetime), held at PENDING_DOCUMENTS until required documents are uploaded (Phase 3), then REGISTRATION_1.
- ECP pipeline REGISTRATION_1 → ACCOUNTS_1 → DISPATCH → INSTALLATION → NET_METERING → REGISTRATION_2 → ACCOUNTS_2 → COMPLETED, with automatic handoffs.
- START DISPATCH gated server-side on FIRST payment CONFIRMED; final payment never blocks; closure ignores payments.
- Derived statuses (Payment Blocked / Ready for Dispatch / Dispatch In Process / Delayed) — never workflow stages.
- SLA per stage (0 = never delayed). RBAC per role; only Owner manages users, SLA, reopens LOST.

## Implemented Phases (summary)
- Phase 1: full auth, lead + ECP workflows, site visits, escalations, payments, dashboards, users, SLA.
- Issues 1-6: role-aware filters, dispatch derived-status filters, manager install assignment, site-visit installer dropdown, lead project price → ECP, accounts payments page.
- Issues 7-19: Lead Employee master, lead_creator snapshots, filters + drilldowns, IST follow-up, phone required, work-done report, owner CSV export, mobile drawer.
- Master Spec Phase 1: new roles, lead_owner + ownership scoping + reassign, duplicate-phone 409, payment future-date reject, Subsequent folding.

## Master Spec Phase 2 — DONE & verified (2026-09-12)
- **Item Master** (Owner-only): `/api/items` list/create/patch(active toggle)/**delete**, `/api/items/export` + `/api/items/import` CSV (dup key = normalized Name+Unit). Frontend `/items` page with ACTIVE/INACTIVE badges, "In use" marker, Edit / Deactivate / Delete.
  - **Delete data-integrity**: `DELETE /api/items/{id}` Owner-only; blocked (409, "used in existing records… deactivate instead") if the item is referenced by any lead `item_id` or by a `pending_commercial_change` (proposed/current). List response includes `referenced`/`deletable` flags; UI disables delete for non-deletable items.
  - Deactivated items: excluded from `active_only` list, rejected on new lead creation (400 "Invalid or inactive item"), historical leads keep `item_name`/`item_unit` snapshot so records still display.
- **Lead item fields**: `item_id` + snapshot `item_name`/`item_unit`, `quantity`, `location_link` (+ existing `project_price`). Server validates item active/exists.
- **Owner-configurable mandatory fields**: `/api/lead-field-config`. Toggleable: email, address, location_link, item, quantity, project_price. Name & Phone always mandatory. Server-side `enforce_lead_mandatory` (400). Owner page `/lead-fields`.
- **Post-handoff Lead editing**: `PATCH /api/leads/{id}` (LEAD owner / OWNER) for non-commercial fields (email/address/location_link/remarks), with an amber UI warning when handed off. Edited contact fields are **mirrored to the linked ECP** (customer_email/customer_address/location_link) so subsequent teams see them via a read-only "Customer & Product" card on ECP detail. Direct `project-price` POST returns 400 once handed off. LeadEditBody cannot change item/quantity/price or workflow/stage fields.
- **Commercial change approval**: propose (LEAD owner) → Owner approve/reject; reject remarks mandatory. On approve, item_id/item_name/item_unit/quantity/project_price sync to the ECP. Owner dashboard banner + `pending_commercial` count. RBAC enforced (non-owner 403). ECP now also carries item/contact snapshot at creation.
- **Quotation PDF**: `GET /api/leads/{id}/quotation` (LEAD owner / MANAGER / OWNER; non-owner LEAD → 403). Frontend Web Share + download fallback.
- Verified: `/app/backend/tests/test_phase2.py` 25/25 PASS (iteration_5.json) + Playwright UI smoke. Item DELETE additions re-verified via curl (owner delete unused 200, non-owner 403, referenced 409, deactivated-selection 400).

## REMAINING PHASES (pending, in order) — DO NOT START P3 UNTIL PHASE 2 USER-VERIFIED
- P3 Documents: object-storage integration + YES→PENDING_DOCUMENTS gate before Registration 1.
- P4 Registration 1/2 rework + task-set versioning + CSPDCL/DCR/NM sequencing.
- P5 Dispatch financial-field stripping + Delivery Challan (finalize→Accounts). NOTE: challans will reference items → include in item reference-check when built.
- P6 Installation Manager→Member assignment, 5 mandatory photos, submit→acceptance/rework.
- P7 Site Visit structured survey + geo photos + extra materials. NOTE: extra-materials will reference items → include in reference-check.
- P8 Complaint module. P9 Mobile passes. P10 Full regression + security tests.

## Known test hygiene note
Legacy Phase-1 pytest files were updated (2026-09-12) to comply with approved rules: lead-creation phones are now uuid-based (no duplicate-phone 409 collisions); the obsolete direct post-handoff price test now expects 400 + commercial-change flow; the ADDITIONAL-payment test uses IST today (no future-date rejection). Full relevant suite green: 77 legacy + 25 Phase 2 + 16 Phase 2-final.

## Master Spec Phase 3 — Documents + Pending Documents Gate — DONE & verified (2026-06 / iteration_7)
- **New ECP stage `PENDING_DOCUMENTS`** (team LEAD): YES now creates the ECP here with NO Registration-1 tasks. Registration cannot start Reg 1 until docs complete (PENDING_DOCUMENTS ECPs excluded from Registration's `/api/ecps`, no tasks exist, doc read 403 pre-registration).
- **Mandatory docs**: PAN, Aadhaar, Electricity Bill, + ONE of {Bank Passbook, 3-Month Statement, Cancelled Cheque}; if Finance=YES also ONE of {Property Paper, Tax Receipt}. `workflow.documents_complete()`.
- **Auto-release**: the upload that completes the applicable set advances PENDING_DOCUMENTS → REGISTRATION_1 (creates Reg1 tasks; base 4, +3 loan if financing). Manual `POST /api/leads/{id}/documents/release` (LEAD owner/OWNER) 400s if incomplete.
- **Object storage** (`backend/storage.py`, Emergent): files in object storage, metadata in `lead_documents` (doc_type, storage_path, original_filename, content_type, size, uploaded_by, uploaded_at, status CURRENT/REPLACED). Re-upload marks prior CURRENT as REPLACED (history preserved). Content-type limited to jpg/png/pdf; max 10 MB.
- **APIs**: `POST/GET /api/leads/{id}/documents`, `GET /api/leads/{id}/documents/{doc_id}/download`, `POST /api/leads/{id}/documents/release`.
- **RBAC** (`_lead_for_doc`): OWNER full; LEAD only own lead (previous owner loses access after reassign); MANAGER read; REGISTRATION read only after reaching Registration; ACCOUNTS/DISPATCH/INSTALLATION 403.
- **Financing changes** while PENDING re-evaluate the finance-doc requirement (`_apply_ecp_financing` skips task creation while PENDING_DOCUMENTS). Grandfathering: existing REGISTRATION_1+ ECPs untouched.
- **UI**: `DocumentsPanel` on LeadDetail + ECPDetail (per-type rows, upload/replace, overall COMPLETE/INCOMPLETE badge, missing list, download); ECPDetail `ecp-pending-docs-notice`; Dashboard counters (Owner ECP "Pending Documents", Registration + Lead "Awaiting Documents").
- **Tests**: `tests/test_phase3_documents.py` 35/35 pass; full backend suite 118 legacy/phase2 green (4 unrelated pre-existing flakes: transient upload 502 + stateful money math).

## Net Metering Close-Task Handoff — DONE & verified (2026-06 / iteration_21)
- **Bug**: entering NET_METERING carried the Installation-stage `responsible_user`, letting REGISTRATION complete the INSTALLATION_MEMBER-team "Close Net Metering" task via the pre-carried assignee.
- **Fix (`backend/server.py` `_advance_stage`)**: removed the NET_METERING special-case; `responsible_user`/`responsible_user_name` are now cleared on entry (default else-branch). NET_METERING stage ownership stays REGISTRATION; 5 tasks + prerequisites unchanged.
- **Fix (`backend/server.py` `assign_installation`, POST `/api/ecps/{id}/assign-installation`)**: now branches on stage. In NET_METERING it requires "Request Net Metering from CSPDCL" completed, then assigns an active Installation worker to Close NM via existing `responsible_user` mechanism. INSTALLATION-stage behavior unchanged. Authority: INSTALLATION_MANAGER / MANAGER / OWNER.
- **`complete_task`**: existing INSTALLATION_MEMBER-team gate (`responsible_user == user.id`) + prerequisite enforcement is authoritative (unchanged). Added: response now returns lightweight `{status:"completed", current_stage}` (200) instead of 404 when the completion auto-advances the ECP out of the caller's role scope (e.g. member completing Close NM → REGISTRATION_2).
- **Fix (`frontend/src/pages/ECPDetail.jsx`)**: `visibleStageTasks` filters "Close Net Metering" out of the REGISTRATION stage-work list entirely; Close NM row renders assign / assigned / awaiting-prereq for Installation Manager and Mark Done for the assigned worker; `completeTask` gracefully navigates to /ecps if the ECP leaves the caller's scope.
- Completion of Close NM auto-advances NET_METERING → REGISTRATION_2 (existing `_maybe_advance`/`_advance_stage`, stage history preserved).
- Verified: testing_agent iteration_21 (backend + Playwright, 100%) + 19/19 focused end-to-end API validation driving a fresh ECP INSTALLATION → NET_METERING → REGISTRATION_2.

## Pending (from prior handoff, NOT started)
- P0: Operations Command-Center Dashboard redesign for the 9 non-OWNER roles (Manager/Lead/Registration/Accounts/Dispatch/Install Mgr/Install Member/Complaint) to match the Owner "Command Center" aesthetic.
- P1: Sidebar redesign ("Task 3B").

## Next Tasks (awaiting user approval — do NOT start until approved)
- Phase 4: Registration task rework (Consumer Request / Vendor Acceptance / conditional loan tasks, NM sequencing).
- Phase 5: Delivery Challan (Dispatch finalizes in-app → Accounts; hide financials from Dispatch).
- Phase 6: Installation Manager → Member; Phase 7: Site Visit survey; Phase 8: Complaints module.
