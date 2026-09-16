# CHANGELOG

## Phases 4–10 (2026-06) — one coordinated build

### Phase 4 — Registration rework
- REGISTRATION_1 tasks: Consumer Request, CVA Print & Sign, Feasibility Report Upload (+ finance: Loan Documentation, Loan Filing, Bank Submission).
- REGISTRATION_2 tasks: Asset Creation, Completion Certificate (requires Asset Creation), Bank Submission 2nd (finance only, else N/A).
- NET_METERING now a shared stage: Registration does Upload Installation Photos to CSPDCL Portal → DCR Issuance → Consumer Approval & Submit → Request Net Metering from CSPDCL (chained), then INSTALLATION_MEMBER does Close Net Metering (requires the Request task). Server-side `requires` gating + per-task team enforcement. Photo-upload task gated on manager-approved photos existing.
- Task specs centralized in workflow.STAGE_TASK_SPECS (name, team, financing_only, requires); tasks carry team+requires. Historical ECPs untouched (their old task docs remain).

### Phase 5 — Dispatch + Delivery Challan
- Dispatch financial segregation enforced server-side: `_scrub_dispatch` removes project_price from GET /ecps and /ecps/{id}; payments returned empty for DISPATCH.
- Start Dispatch remains gated by FIRST payment CONFIRMED.
- Delivery Challan: delivery_challans collection; POST /ecps/{id}/challan (dispatch/owner, active Item Master), /challan/finalize; GET /challans (accounts/manager/owner). No invoice generation; no partial dispatch.

### Phase 6 — Installation Manager → Member + photos + acceptance
- New roles INSTALLATION_MANAGER, INSTALLATION_MEMBER (legacy INSTALLATION works as member). Seeded: instmgr/instmem.
- Flow: AWAITING_ASSIGNMENT (team INSTALLATION_MANAGER) → assign member → start → 5 mandatory photos (ecp_photos, object storage) → submit (all 5 required) → PENDING_ACCEPTANCE → manager accept (photos approved, advance) / reject (remarks mandatory → REJECTED → re-upload).
- Registration sees install photos only when approved (RBAC on list/download).

### Phase 7 — Site Visit survey
- INSTALLATION_MANAGER (not process Manager) + Owner assign an INSTALLATION_MEMBER; member submits structured survey (structure_height, earthing/dc/ac cable lengths, surveyor_name required; extra_materials via active Item Master). Lead returns to Lead Team with 5 actions. No ECP/installation created.

### Phase 8 — Complaint Portal
- Role COMPLAINT (seeded complaint/Comp@123). Owner-managed categories (dup 409) + SLA config by category|priority (IST). Workflow REGISTERED→ASSIGNED→IN_PROGRESS→RESOLVED→CLOSED (member resolves, manager/owner closes). Optional lead/ecp link. Attachments jpg/png/pdf (object storage) + RBAC. Overdue = IST today > due & not resolved/closed. History tracked.

### Phase 9 — Mobile
- New surfaces use responsive shadcn dialogs/cards; photo inputs use capture="environment"; overflow-y on tall dialogs.

### Phase 10 — Tests
- test_phase4_10.py (6 journey/security tests) PASS. Full backend regression: 159 tests pass (backend_test, test_issues_1_to_6, test_issues_7_to_19, test_audit_spec, test_phase2, test_phase2_final, test_phase3_documents, test_phase4_10). Legacy pipeline/financing/dispatch tests updated to the new rules.

## Final Audit (2026-06) — confirmed-gap fixes + new-role dashboards
- Fixed: Owner user-creation dropdown now lists all 10 roles incl. INSTALLATION_MANAGER, INSTALLATION_MEMBER, COMPLAINT (Users.jsx ROLES + ROLE_LABELS). Backend wf.ROLES already accepted them; create is Owner-only (non-owner 403).
- Added role-specific dashboard data + UI for the 3 new roles (were blank): INSTALLATION_MANAGER (Installation + Site Visit supervision queues), INSTALLATION_MEMBER (my installations / my site visits), COMPLAINT (register + status + SLA overdue/due-today).
- COMPLAINT dashboard has a prominent "+ Register Complaint" CTA deep-linking to /complaints?new=1 (auto-opens the register dialog).
- Verified by testing agent iteration_8: 8/8 targeted backend tests + live UI smoke, no functional bugs. Existing 159-suite untouched.
- NOTE: The broad "operations command-center" redesign of the EXISTING role dashboards (Owner/Manager/Lead/Registration/Accounts/Dispatch) and Site-Visit geo-photo/extra-material capture UI were NOT done in this pass (budget) — existing dashboards remain functional; these are deferred.

## Security fix (2026-06) — ECP detail IDOR
- `GET /api/ecps/{ecp_id}` (`get_ecp`) now applies the same `ecp_filter_for_role(user)` visibility scope as the list endpoint (early 404 for the `__none__` blocked-role case, e.g. COMPLAINT). Previously it fetched by id only, allowing direct-ID retrieval of out-of-scope ECPs. DISPATCH scrubbing (project_price removed, payments empty) preserved after the scope check.
- Verified by testing agent iteration_10: 13/13 backend tests pass (list/detail scope parity for all roles; DISPATCH stage-only; REGISTRATION allowed stages; INSTALLATION_MEMBER assignment gating; COMPLAINT 404; non-existent id 404). Regression test: `tests/test_ecp_detail_scope.py`.

## Security fix (2026-06) — LEAD ECP list visibility
- `ecp_filter_for_role(user)` LEAD branch changed from `{}` (unrestricted — LEAD could list all ECPs) to `{"lead_owner_id": {"$in": [user["id"], None]}}`, matching the detail endpoint (`get_ecp`) and LEAD dashboard scoping. OWNER/MANAGER/ACCOUNTS unchanged (`{}`).
- Verified by testing agent iteration_11: 22 passed, 1 skipped. LEAD list is a proper subset of OWNER's, list/detail parity holds, a synthetic foreign-owned ECP is invisible to LEAD (absent from list + 404 on detail) yet visible to OWNER. Existing IDOR suite still green. Regression test: `tests/test_ecp_lead_list_scope.py`.

## Security fix (2026-06) — LEAD dashboard cross-user leak
- `GET /api/dashboard` previously computed LEAD counters over unrestricted `leads`/`ecps`/`lead_site_visits`, leaking other Lead owners' aggregate counts. Fix in `dashboard()`: for `role=="LEAD"`, `leads` and `ecps` are filtered to `lead_owner_id in (user_id, None)` right after load (before enrich), and `site_visits` filtered to the scoped lead ids. All LEAD counters (action_required, followups_today, waiting_site_visit, escalated, qualified, lost, pending_documents) inherit the scope; response contract unchanged. Non-LEAD branches untouched.
- Verified by testing agent iteration_12: 26 passed, 1 pre-existing skip. Foreign-owned records add 0 to every LEAD counter, own records still count, OWNER still counts all, and the P0 #1/#2 suites stay green. Regression test: `tests/test_lead_dashboard_scope.py`.

## Security fix (2026-06) — LEAD financing endpoint authorization
- `POST /api/ecps/{ecp_id}/financing` required LEAD/MANAGER/OWNER but fetched by id only, letting a LEAD toggle financing on any ECP (and its linked Lead). Fix in `ecp_financing()`: after the 404 fetch and before `_apply_ecp_financing()` + the linked-Lead update, `role=="LEAD"` with `lead_owner_id not in (user_id, None)` -> HTTP 403. MANAGER/OWNER unchanged; response shape unchanged.
- Verified by testing agent iteration_13: 6/6 financing tests pass, no mutation on rejected cross-user request, own/unassigned still work, MANAGER/OWNER unaffected; prior scope suites green. Regression test: `tests/test_ecp_financing_scope.py`.

## Workflow fix (2026-06) — Dispatch Delivery Challan prerequisite
- `workflow.py` DISPATCH task specs now chain `requires`: "Material Dispatch Confirmation" requires "Delivery Challan"; "Dispatch Completed" requires "Material Dispatch Confirmation". `complete_task()` additionally blocks the "Delivery Challan" task (400 "Finalize the Delivery Challan before marking the task complete") unless a `delivery_challans` doc exists with status FINALIZED and non-empty items. First-payment gate on Start Dispatch and auto-advance to INSTALLATION unchanged.
- Verified by testing agent iteration_14: 6/6 tests pass (no/draft challan blocked, finalized allows, requires-chain ordering, full sequence auto-advances DISPATCH→INSTALLATION, RBAC intact); prior scope suites green. Regression test: `tests/test_dispatch_challan_gate.py`.
- Known minor UX (pre-existing, from the detail-scope fix): when a DISPATCH user completes the final Dispatch task, the ECP auto-advances to INSTALLATION and the `get_ecp` response (now role-scoped) 404s for DISPATCH even though the write succeeded. Not a correctness issue for this gate.

## Frontend fix (2026-06) — INSTALLATION_MANAGER assign UI + Login import
- `ECPDetail.jsx`: installers-load condition and `canAssignInstall` now include `INSTALLATION_MANAGER` (backend already authorized it on `POST /ecps/{id}/assign-installation` and `/users/team/INSTALLATION`). Assign button still gated on stage===INSTALLATION && install_status===AWAITING_ASSIGNMENT && canAssignInstall. Frontend-only change; existing dialog/API reused.
- Also fixed a broken empty named-import in `Login.jsx` (`import { } from "@/context/AuthContext"`) that crashed the login page — restored `import { useAuth }`.
- Verified by testing agent iteration_15: 7/7 role scenarios pass — INSTALLATION_MANAGER can load installers, see the button, open the dialog, assign (→ READY_TO_INSTALL); MANAGER/OWNER unchanged; INSTALLATION_MEMBER/REGISTRATION/DISPATCH/LEAD do not gain the capability.

## Frontend fix (2026-06) — NET_METERING stage-team mapping
- `ECPDetail.jsx` STAGE_TEAM: `NET_METERING` corrected from `INSTALLATION` to `REGISTRATION`, matching backend workflow ownership. REGISTRATION users are now treated as the stage team (see Net Metering task-completion controls instead of the read-only notice); other mappings unchanged. Backend `Close Net Metering` ownership (INSTALLATION_MEMBER) unchanged.
- Verified by testing agent iteration_16: 100% frontend pass on a live NET_METERING ECP — REGISTRATION sees Mark Done controls, INSTALLATION does not, no runtime errors.

## Feature (2026-06) — Edit existing payment from ECP Detail
- `ECPDetail.jsx` Payment Position: each payment row now has an "Edit" button for ACCOUNTS (only while ECP is ACTIVE). It opens a dialog pre-filled with the payment's amount/date/status/remarks and submits via the existing `PATCH /api/payments/{id}`; on success shows a toast and reloads via existing `load()`. Payment TYPE is read-only in the dialog, so no duplicate FIRST/FINAL can be created. Added the missing `Input` import.
- Backend unchanged (PATCH is ACCOUNTS-only, sets amount/date/status/remarks only, never touches current_stage).
- Verified by testing agent iteration_17: 100% backend + frontend — edit/prefill/save/toast, current_stage unchanged, no duplicate payment, RBAC enforced (OWNER/MANAGER see no button + 403 backend), creation still works. Regression test: `tests/test_payment_edit_scope.py`.

## Bug fix (2026-06) — Lead Follow-up IST business dates
- `server.py`: FOLLOW_UP action past-date guard now compares against `ist_today_str()` (was UTC `datetime.now(timezone.utc).date()`), and dashboard `followups_today()` counts follow-ups against `ist_today_str()` (was the shared UTC `today`). `list_leads(?followup=today)` already used IST (unchanged). The shared dashboard UTC `today` used by unrelated site-visit/complaint metrics was intentionally left untouched. No stored date-format or data changes.
- Verified by testing agent iteration_18: 10/10 IST-boundary tests + existing follow-up regression pass — IST-today accepted, IST-yesterday rejected/not-counted, dashboard count consistent with `?followup=today`. Regression test: `tests/test_followup_ist.py`.

## UI fix (2026-06) — remove obsolete "Installation Team" role from user creation
- `Users.jsx`: removed `INSTALLATION` from the selectable `ROLES` list (Create/Edit User dropdown). Installation Manager and Installation Member remain; all other roles unchanged. `ROLE_LABELS.INSTALLATION` kept so legacy records still render, and the dropdown still offers `INSTALLATION` when editing an existing INSTALLATION user so their record isn't broken. No backend/role-definition/data changes.
- Verified by code inspection + clean compile (HTTP 200); screenshot harness could not be used due to the documented auth-persistence quirk.

## Prior note: Frontend compiles clean (HTTP 200); Phase 4-10 new-flow UI is wired (Complaints page, InstallationWork, DeliveryChallanPanel, Site Visit survey) but visual QA via the screenshot harness was blocked by an auth-persistence quirk in the preview automation; backend behavior fully verified via automated tests.

## 2026-09-14 — Lead Creator unified + reassignment authorization
- Lead Creator is now always the authenticated creator (backend sets lead_creator_id/name = user id/name); removed lead_creator_id from LeadCreate and the create-lead dropdown in Leads.jsx (no more /lead-employees dependency for creation).
- Reassignment stays OWNER/MANAGER-only (403 for LEAD, verified), targets active users with role LEAD from unified /users/team/LEAD, and now rejects LOST leads server-side (400). Legacy lead_employees module/data left intact.

## 2026-09-14 — Task 3A: Owner Command Center dashboard redesign
- Redesigned OWNER dashboard (frontend/src/pages/Dashboard.jsx) from a flat StatCard grid into a command center: Attention Required (Commercial Approvals, Escalated, Payment Blocked, Delayed), Business Overview KPI row, Lead Pipeline flow (Lost separated), grouped ECP Operations (Registration/Dispatch/Installation/Completion), and Payments (First Pending/First Confirmed/Subsequent — Final removed).
- Reused /dashboard API and existing drill-down routes; no backend changes. Commercial banner + Export CSV preserved. Non-owner dashboards unchanged. Verified via screenshot + drill-down check.

## 2026-09-14 — Task 3A-revision: Owner dashboard reworked to approved visual reference
- Reworked OWNER dashboard to match the approved command-center reference: light full-bleed header (date/time + Export CSV + profile), compact Requires-Your-Attention strip (dominant Commercial Approvals + Payment Blocked/Delayed/Escalated tiles), single-row 6-card Business Snapshot, chevron Lead Pipeline + real Leads Trend chart, one wide 5-column ECP Project Status panel (Registration/Dispatch/Installation/Completion/Attention), compact Payments Overview (First Pending/First Confirmed/Subsequent — no Final), and a real Recent Activity panel.
- Leads Trend derived client-side from existing /leads (real data, no fabrication); Recent Activity from existing owner-only /activities; recharts used for the chart. Zero backend changes. Non-owner dashboards untouched. Verified via screenshot; compiles clean.

## 2026-09-14 — Task 3C: Owner ECP dashboard drill-down filters
- Added an OWNER entry to the existing FILTERS map in ECPs.jsx (All, Pending Documents, Registration 1/2, Accounts 1/2, Payment Blocked, Ready for Dispatch, Dispatch In Process, Installation, Ready to Install, Installation In Process, Net Metering, Successfully Completed, Closed/Cancelled, Delayed) so Owner now gets the ECP filter selector + bookmarkable URL.
- Fixed Owner dashboard ECP links in Dashboard.jsx to exact backend params: Payment Blocked->view=PAYMENT_BLOCKED, Ready for Dispatch->view=READY_FOR_DISPATCH, Dispatch In Process->view=DISPATCH_IN_PROCESS, Ready to Install->view=READY_TO_INSTALL, Installation In Process->view=IN_PROCESS, Delayed->view=DELAYED, Successfully Completed->view=COMPLETED, Closed/Cancelled->view=CLOSED (stage params unchanged for reg/accounts/NM/pending-docs).
- Zero backend changes: reused existing _matches_view + stage filtering (OWNER role filter already returns {}). Verified via curl (each view returns exact subset) and screenshot (refresh preserves filter, selector shows correct label).

## 2026-09-14 — Fix: Installation assignment pool includes INSTALLATION_MEMBER
- backend/server.py /users/team/{role}: when role=="INSTALLATION", query {"role":{"$in":list(wf.INSTALL_MEMBER_ROLES)}} (INSTALLATION + INSTALLATION_MEMBER); all other roles keep exact-role filter. Response shape unchanged.
- Verified by testing_agent (iteration_20.json, backend+frontend 100
## 2026-06 — Fix: Installation assignment pool includes INSTALLATION_MEMBER
- backend/server.py /users/team/{role}: when role=="INSTALLATION", query role in wf.INSTALL_MEMBER_ROLES (INSTALLATION + INSTALLATION_MEMBER); all other roles keep exact-role filter. Response shape unchanged.
- Verified by testing_agent iteration_20.json (backend+frontend 100%): dropdown now lists active INSTALLATION_MEMBER users, assignment succeeds (ECP to READY_TO_INSTALL), no cross-role leakage, inactive excluded.
