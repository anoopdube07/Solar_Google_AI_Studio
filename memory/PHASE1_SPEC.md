# ECP Project Management & Lead Tracking System — Phase 1 Specification
> Analysis only. No implementation until "APPROVED — START BUILD".

## A. Business Objective Summary
Internal employee app giving the OWNER full visibility of every Lead and ECP project:
where it is, which team/person owns the next action, and what is stuck/delayed.
Two independent workflows: (1) Lead Qualification, (2) ECP Execution. An ECP is created
only when a Lead is qualified YES (max one ECP per Lead). Goal: reduce manual
coordination, make workflow visible, minimal data entry, simple dashboards.

## B. Lead Workflow
New Lead → STATUS=PENDING, CURRENT_TEAM=LEAD TEAM, ACTION_REQUIRED=YES.
Lead Team has 5 actions: YES, NO, FOLLOW-UP, SITE VISIT, ESCALATION.
- YES → Lead=QUALIFIED → auto-create 1 ECP at REGISTRATION 1 (Registration Team). No manual ECP creation.
- NO → Lead=LOST, require Lost Reason (if OTHER → remarks mandatory). Only OWNER reopens; reopened → LEAD TEAM, action required, 5 actions again.
- FOLLOW-UP → require follow-up date (not past) + remarks; Lead stays with Lead Team; keep follow-up history.
- SITE VISIT → qualification tool (see C).
- ESCALATION → to OWNER only (see D).

## C. Site Visit Workflow (Lead-level qualification tool ONLY)
Not the ECP installation. Not mandatory. Only performed if Lead Team requests it.
Flow: Lead → Process Owner/Manager assigns Installation employee + date → Installation employee performs visit → SITE VISIT DONE (requires survey info) → Lead auto-returns to Lead Team, action required, 5 actions again.
- Only ONE open Site Visit per Lead (open = REQUESTED or ASSIGNED).
- Completed visits stay in history. Site Visit attaches to Lead only (never ECP).
- Lead Team may request another visit after one completes.

## D. Escalation Workflow
Lead Team selects ESCALATION → require Reason + Remarks → goes ONLY to OWNER.
Owner can Review, add Owner Remarks (mandatory), Return to Lead Team.
Owner CANNOT decide YES/NO/FOLLOW-UP/SITE VISIT on Lead Team's behalf.
After return: OWNER RETURNED → LEAD TEAM → action required → 5 options again.

## E. ECP Workflow (exists only after Lead=YES)
REGISTRATION 1 → ACCOUNTS 1 → DISPATCH → INSTALLATION → NET METERING → REGISTRATION 2 → ACCOUNTS 2 → CLOSED (Successfully Completed).
- REGISTRATION 1 (Registration Team): mandatory tasks = CSPDCL Registration, PPA Preparation, Cover Letter, CVA. If financing_required=YES also: Loan Documentation, Loan Filing, Bank Submission. All applicable mandatory tasks done → advance.
- ACCOUNTS 1 (Accounts Team): mandatory = Advance Verification. FIRST PAYMENT NOT required here. On completion → auto move to DISPATCH.
- DISPATCH (Dispatch Team): enters regardless of payment. Derived display states: PAYMENT BLOCKED / READY FOR DISPATCH / DISPATCH IN PROCESS. START DISPATCH allowed only when First Payment=CONFIRMED (server-side validated). Steps: Delivery Challan, Material Dispatch Confirmation, Dispatch Completed. Once started legitimately, later payment changes don't stop it. Payment gate only on START DISPATCH. On completion → INSTALLATION.
- INSTALLATION (Installation Team): ECP installation (different from Lead Site Visit). Statuses: READY TO INSTALL, IN PROCESS, COMPLETED → NET METERING.
- NET METERING (Installation Team): complete → REGISTRATION 2.
- REGISTRATION 2 (Registration Team): mandatory = Asset Creation, Completion Certificate → ACCOUNTS 2.
- ACCOUNTS 2 (Accounts Team): Final Payment Follow-up (does NOT block). After Accounts 2 operational task done → CLOSED — SUCCESSFULLY COMPLETED.

## F. Payment Logic
Payments independent of ECP stage; Accounts can update at ANY stage.
Types: FIRST (exactly 1/ECP), ADDITIONAL (many), FINAL (exactly 1/ECP).
Each payment: amount, date, status, remarks, updated_by, updated_at. Status: PENDING/CONFIRMED.
Only Accounts create/update; Owner & Process Owner/Manager view.
Payment changes never auto-change stage. First Payment blocks START DISPATCH only.
Final Payment never blocks progression/closure. Post-closure show indicators only:
"FIRST PAYMENT NOT RECEIVED" and/or "FINAL PAYMENT PENDING".

## G. Financing Logic
financing_required on Lead and ECP. Editable by Lead Team, Process Owner/Manager, Owner; others view only.
- NO→YES: activate Loan Documentation, Loan Filing, Bank Submission. If ECP already past Registration 1: DO NOT rollback, DO NOT create new ECP, keep current stage, show financing tasks as outstanding/pending.
- YES→NO: require confirmation → financing_required=NO, financing tasks applicable=false, preserve history, no longer block, no stage regress, no new records.

## H. Closure Logic
Only OWNER and PROCESS OWNER/MANAGER can manually close/cancel an ECP, at ANY stage.
Require Closure Reason + Closure Remarks (if OTHER → remarks mandatory).
Manual → CLOSED/CANCELLED; record closed_at, closed_by, reason, remarks.
Closure never checks First or Final payment. CLOSED/CANCELLED cannot reopen in V1 (returning customer = new Lead).
Natural completion via Accounts 2 → CLOSED — SUCCESSFULLY COMPLETED.

## I. Role & Permission Matrix
| Capability | Owner | Process Owner/Mgr | Lead Team | Registration | Accounts | Dispatch | Installation |
|---|---|---|---|---|---|---|---|
| Manage users/roles/teams | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Configure SLA | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Receive/return escalations | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Reopen LOST Lead | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Create/manage Leads + 5 actions | ✘ | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Assign Site Visits | ✘ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Perform Site Visit | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ |
| Change financing | ✔ | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| Close/cancel ECP | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Registration tasks | (view) | (view) | ✘ | ✔ | ✘ | ✘ | ✘ |
| Accounts tasks + payments | (view) | (view) | ✘ | ✘ | ✔ | ✘ | ✘ |
| Dispatch tasks | (view) | (view) | ✘ | ✘ | ✘ | ✔ | ✘ |
| ECP Install + Net Metering | (view) | (view) | ✘ | ✘ | ✘ | ✘ | ✔ |
| View everything | ✔ | operational | Leads + read-only ECP | scoped | scoped+payment monitor | scoped | scoped |

Process Owner/Mgr CANNOT: manage users, change permissions, reopen LOST leads, be the escalation destination.

## J. Visibility Matrix
- Owner: everything.
- Process Owner/Manager: all active operational Leads & ECPs.
- Lead Team: Leads + basic read-only ECP info.
- Registration: registration-related ECP work.
- Accounts: accounts-related work + payment monitor for every ECP.
- Dispatch: dispatch-stage ECPs.
- Installation: assigned Lead Site Visits + Installation/Net Metering ECPs.
- Ordinary employees: primarily records assigned to them + relevant team queues.

## K. Dashboard Specification (all counters clickable/drill-down)
- OWNER — Leads: Pending, Follow-up, Site Visit, Escalated, Qualified, Lost. ECP: Active, Registration 1, Accounts 1, Payment Blocked, Ready for Dispatch, Dispatch In Process, Ready to Install, Installation In Process, Net Metering, Registration 2, Accounts 2, Delayed, Successfully Completed, Closed/Cancelled. Payments: First Pending, First Confirmed, Final Pending, Final Confirmed, Additional.
- PROCESS OWNER/MANAGER: Site Visits To Assign, Today's Site Visits, Upcoming Site Visits, Unassigned work, Team workload, Delayed projects, Active Leads, Active ECPs.
- LEAD TEAM: Action Required, Today's Follow-ups, Upcoming Follow-ups, Waiting for Site Visit, Site Visit Completed, Escalated, Qualified, Lost.
- ACCOUNTS: Accounts 1, Accounts 2, First Pending, First Confirmed, Final Pending, Final Confirmed, Additional, Payment Monitor.
- DISPATCH: Payment Blocked, Ready for Dispatch, Dispatch In Process, Completed.
- INSTALLATION: A) Lead Site Visits: Upcoming, Today, Assigned to Me, Completed. B) ECP Installation: Ready to Install, In Process, Net Metering.
- REGISTRATION: Registration 1, Registration 2, My Tasks, Pending, Completed.

## L. Automatic Handoff Rules
Lead YES → ECP → Registration; Reg1 done → Accounts1; Accounts1 done → Dispatch; Dispatch done → Installation; Installation done → Net Metering; Net Metering done → Reg2; Reg2 done → Accounts2; Accounts2 done → Successfully Completed. Site Visit done → Lead Team; Owner escalation return → Lead Team; Owner LOST reopen → Lead Team.
Every ECP transition updates: current stage, current team, responsible user (where applicable), stage dates, workflow history.

## M. Validation Rules (server-side)
No direct ECP creation; one ECP per Lead; NO requires reason; Follow-up requires future date + remarks; Site Visit requires assignment; only one open Site Visit; Site Visit Done requires survey info; Escalation requires reason + remarks; Owner return requires Owner Remarks; Registration mandatory tasks block progression; Accounts 1 Advance Verification blocks progression; Start Dispatch requires First Payment confirmed; Installation requires Dispatch completed; manual closure requires reason + remarks; only Owner/Manager close ECP; closed ECP cannot reopen; Final Payment never blocks; Accounts update payments any stage; financing changes never duplicate/regress; only Owner manages users; only Owner reopens LOST Lead.

## N. Proposed Database / Entity Model
Entities: USERS, STAGE_SLA_CONFIG, LEADS, LEAD_FOLLOWUPS, LEAD_SITE_VISITS, LEAD_ESCALATIONS, ECPS, ECP_STAGE_HISTORY, ECP_TASKS, PAYMENTS.
Relationships: Lead 1→0/1 ECP; ECP 1→many Tasks; ECP 1→many Stage History; ECP 1→many Payments; Lead 1→many Followups; Lead 1→many Site Visits; Lead 1→many Escalations. Site Visit belongs only to Lead.
Key fields (indicative):
- USERS: id, name, email, role/team, active.
- STAGE_SLA_CONFIG: stage, sla_days (default 0 = not configured).
- LEADS: id, contact info, status, current_team, action_required, financing_required, lost_reason, lost_remarks, ecp_id (nullable), timestamps.
- LEAD_FOLLOWUPS: id, lead_id, followup_date, remarks, created_by, created_at.
- LEAD_SITE_VISITS: id, lead_id, status (REQUESTED/ASSIGNED/DONE), assigned_user, visit_date, survey_info, timestamps.
- LEAD_ESCALATIONS: id, lead_id, reason, remarks, owner_remarks, status, timestamps.
- ECPS: id, lead_id, current_stage, current_team, responsible_user, financing_required, status (ACTIVE/CLOSED/CANCELLED/COMPLETED), dispatch_started (bool), stage_dates, closed_at/by/reason/remarks, timestamps.
- ECP_STAGE_HISTORY: id, ecp_id, from_stage, to_stage, changed_by, changed_at.
- ECP_TASKS: id, ecp_id, stage, task_name, applicable (bool), completed (bool), completed_by, completed_at.
- PAYMENTS: id, ecp_id, type (FIRST/ADDITIONAL/FINAL), amount, date, status (PENDING/CONFIRMED), remarks, updated_by, updated_at.

## O. Derived Status Logic (NOT workflow stages)
- PAYMENT BLOCKED: current_stage=DISPATCH AND dispatch not started AND First Payment != CONFIRMED.
- READY FOR DISPATCH: current_stage=DISPATCH AND dispatch not started AND First Payment = CONFIRMED.
- DISPATCH IN PROCESS: current_stage=DISPATCH AND dispatch started.
- DELAYED: SLA configured (>0) AND current date > configured stage due date. (SLA=0 → never delayed.)
- Post-closure indicators: "FIRST PAYMENT NOT RECEIVED", "FINAL PAYMENT PENDING" (display only).

## P. Resolved Business Decisions (FINAL)
1. Advance Verification ≠ First Payment. Advance Verification is an Accounts 1 operational task; completing it does NOT confirm First Payment. Accounts 1 can complete with First Payment unconfirmed. First Payment CONFIRMED required only to START DISPATCH.
2. Only Accounts create/update/confirm payments (via Payment Monitor). Dispatch cannot edit; sees derived PAYMENT BLOCKED / READY FOR DISPATCH. Confirming First Payment auto-flips Dispatch to READY FOR DISPATCH.
3. No ECP escalation in V1. Escalation is Lead-stage only (Lead Team → Owner → return → Lead Team). ECP delays surfaced via dashboards/workload/DELAYED indicators only.
4. Site Visit assignment: Process Owner/Manager normally; OWNER may assign as override. Lead Team cannot assign. Installation performs assigned visits only.
5. Accounts 2 completion: "Final Payment Follow-up" is the operational task. Marking it COMPLETED → ECP CLOSED — SUCCESSFULLY COMPLETED. Final Payment CONFIRMED NOT required; may stay PENDING; show "FINAL PAYMENT PENDING" post-closure indicator until confirmed.
6. SLA: Stage Due Date = Stage Entry Date + configured SLA days. SLA=0 → not configured → never DELAYED. SLA>0 and today > due date → DELAYED (derived indicator, not a stage).
7. One ECP per Lead for entire lifetime. Closed/Cancelled ECP → Lead cannot create another. Returning customer = NEW LEAD. Never duplicate ECP from original Lead.
8. V1: ONE USER = ONE ROLE = ONE TEAM (no multi-team). Only OWNER can create/deactivate users, change role, change team.

### Lead Return Rule (FINAL)
After (A) Site Visit Completed, (B) Owner Escalation Return, (C) Owner Reopen LOST, the Lead auto-appears in LEAD TEAM's ACTION REQUIRED queue. Lead detail shows return reason (SITE VISIT COMPLETED / OWNER RETURNED / REOPENED). Lead Team again gets all five actions and makes the next decision. Neither Installation nor Owner decides on Lead Team's behalf.
