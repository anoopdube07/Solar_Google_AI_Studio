import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { StatusBadge, DelayedBadge } from "@/components/StatusBadge";
import { STAGE_ORDER, STAGE_LABELS, DERIVED_LABELS } from "@/lib/constants";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { InstallationWork } from "@/components/InstallationWork";
import { DeliveryChallanPanel } from "@/components/DeliveryChallanPanel";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CheckCircle2, Circle, Truck, Wrench, Ban, Coins, UserPlus } from "lucide-react";
import { toast } from "sonner";

const CLOSURE_REASONS = ["CUSTOMER_CANCELLED", "DUPLICATE", "NOT_FEASIBLE", "OTHER"];
const STAGE_TEAM = { REGISTRATION_1: "REGISTRATION", ACCOUNTS_1: "ACCOUNTS", DISPATCH: "DISPATCH", INSTALLATION: "INSTALLATION", NET_METERING: "REGISTRATION", REGISTRATION_2: "REGISTRATION", ACCOUNTS_2: "ACCOUNTS" };

export default function ECPDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [closeDlg, setCloseDlg] = useState(false);
  const [cf, setCf] = useState({});
  const [assignDlg, setAssignDlg] = useState(false);
  const [installers, setInstallers] = useState([]);
  const [assignUser, setAssignUser] = useState("");
  const [payDlg, setPayDlg] = useState(false);
  const [payForm, setPayForm] = useState({});

  const load = () => api.get(`/ecps/${id}`).then((r) => setData(r.data));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (user.role === "INSTALLATION_MANAGER" || user.role === "MANAGER" || user.role === "OWNER") {
      api.get("/users/team/INSTALLATION").then((r) => setInstallers(r.data)).catch(() => {});
    }
  }, [user.role]);
  if (!data) return <div className="p-8 text-slate-500">Loading…</div>;

  const { ecp, tasks, history, payments } = data;
  const stage = ecp.current_stage;
  const isStageTeam = user.role === STAGE_TEAM[stage] || user.role === "OWNER";
  const stageTasks = tasks.filter((t) => t.stage === stage && t.applicable);
  const active = ecp.status === "ACTIVE";

  const openEditPay = (p) => { setPayForm({ id: p.id, type: p.type, amount: String(p.amount ?? ""), date: (p.date || "").slice(0, 10), status: p.status, remarks: p.remarks || "" }); setPayDlg(true); };
  const savePayEdit = async () => {
    if (!payForm.amount || !payForm.date) { toast.error("Amount and date are required"); return; }
    try {
      await api.patch(`/payments/${payForm.id}`, { amount: parseFloat(payForm.amount), date: payForm.date, status: payForm.status, remarks: payForm.remarks });
      toast.success("Payment updated"); setPayDlg(false); load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const completeTask = async (taskId) => {
    try { await api.post(`/ecps/${id}/tasks/${taskId}/complete`); toast.success("Task completed"); load().catch(() => nav("/ecps")); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const startDispatch = async () => {
    try { await api.post(`/ecps/${id}/start-dispatch`); toast.success("Dispatch started"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const installAction = async (action) => {
    try { await api.post(`/ecps/${id}/installation`, { action }); toast.success("Updated"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const toggleFinancing = async (val) => {
    try { await api.post(`/ecps/${id}/financing`, { financing_required: val }); toast.success("Financing updated"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const closeEcp = async () => {
    try { await api.post(`/ecps/${id}/close`, { reason: cf.reason, remarks: cf.remarks }); toast.success("ECP closed"); setCloseDlg(false); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const assignInstall = async () => {
    if (!assignUser) { toast.error("Select an installation employee"); return; }
    try { await api.post(`/ecps/${id}/assign-installation`, { assigned_user: assignUser }); toast.success("Installation assigned"); setAssignDlg(false); setAssignUser(""); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const canFinancing = ["LEAD", "MANAGER", "OWNER"].includes(user.role);
  const canClose = ["OWNER", "MANAGER"].includes(user.role) && active;
  const canAssignInstall = ["INSTALLATION_MANAGER", "MANAGER", "OWNER"].includes(user.role);
  const isNM = stage === "NET_METERING";
  const reqNmDone = stageTasks.some((t) => t.task_name === "Request Net Metering from CSPDCL" && t.completed);
  const isAssignedInstaller = ["INSTALLATION", "INSTALLATION_MEMBER"].includes(user.role) && ecp.responsible_user === user.id;
  const visibleStageTasks = (isNM && user.role === "REGISTRATION")
    ? stageTasks.filter((t) => t.task_name !== "Close Net Metering")
    : stageTasks;
  const stageIdx = STAGE_ORDER.indexOf(stage);
  const fmt = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");
  const firstConf = payments.filter((p) => p.type === "FIRST" && p.status === "CONFIRMED").reduce((a, p) => a + p.amount, 0);
  const subConf = payments.filter((p) => p.type === "ADDITIONAL" && p.status === "CONFIRMED").reduce((a, p) => a + p.amount, 0);
  const finalConf = payments.filter((p) => p.type === "FINAL" && p.status === "CONFIRMED").reduce((a, p) => a + p.amount, 0);
  const totalReceived = firstConf + subConf + finalConf;
  const receivable = Math.max((ecp.project_price || 0) - totalReceived, 0);
  const typeLabel = (t) => (t === "FIRST" ? "First" : "Subsequent");

  return (
    <div>
      <PageHeader title={ecp.lead_name} subtitle={ecp.customer_phone}
        right={<Button variant="secondary" onClick={() => nav("/ecps")}>Back</Button>} />
      <div className="p-6 lg:p-8 space-y-6">
        {/* highlight */}
        <Card className="p-5">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <Info label="Current Stage"><StatusBadge value={stage} /></Info>
            <Info label="Display Status"><span className="font-semibold">{ecp.display_status}</span>{ecp.derived_status && <div className="mt-1"><StatusBadge value={ecp.derived_status} label={DERIVED_LABELS[ecp.derived_status]} /></div>}</Info>
            <Info label="Current Team / Person">{ecp.current_team || "—"}{ecp.responsible_user_name ? ` · ${ecp.responsible_user_name}` : ""}</Info>
            <Info label="Project Price"><span data-testid="ecp-project-price">{ecp.project_price ? fmt(ecp.project_price) : "—"}</span></Info>
            <Info label="Days in Stage">{ecp.days_in_stage ?? "—"} {ecp.delayed && <DelayedBadge />}</Info>
            <Info label="Financing">{ecp.financing_required ? "Required" : "Not required"}</Info>
          </div>
          {ecp.status === "COMPLETED" && (
            <div className="mt-4 space-x-2">
              {!ecp.first_payment_confirmed && <span className="text-xs font-semibold text-rose-600">FIRST PAYMENT NOT RECEIVED</span>}
              {!ecp.final_payment_confirmed && <span className="text-xs font-semibold text-amber-600">FINAL PAYMENT PENDING</span>}
            </div>
          )}
          {stage === "PENDING_DOCUMENTS" && (
            <div className="mt-4 text-sm bg-amber-50 border border-amber-200 rounded-md px-3 py-2 text-amber-800" data-testid="ecp-pending-docs-notice">
              <b>Pending Documents</b> — Registration 1 cannot start until all required customer documents are uploaded by the Lead Team.
            </div>
          )}
          {ecp.status === "CLOSED" && (
            <div className="mt-4 text-sm bg-slate-50 border rounded-md px-3 py-2 text-slate-700">
              Closed/Cancelled · reason: <b>{ecp.closure_reason}</b>{ecp.closure_remarks ? ` — ${ecp.closure_remarks}` : ""} · by {ecp.closed_by_name}
            </div>
          )}
        </Card>

        {/* customer & product */}
        <Card className="p-5" data-testid="ecp-customer-card">
          <h3 className="font-head font-semibold mb-3">Customer &amp; Product</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <Info label="Phone">{ecp.customer_phone || "—"}</Info>
            <Info label="Email">{ecp.customer_email || "—"}</Info>
            <Info label="Address">{ecp.customer_address || "—"}</Info>
            <Info label="Location">{ecp.location_link ? <a href={ecp.location_link} target="_blank" rel="noreferrer" className="text-sky-600 underline">Open map</a> : "—"}</Info>
            <Info label="Item">{ecp.item_name ? `${ecp.item_name} (${ecp.item_unit})` : "—"}</Info>
            <Info label="Quantity">{ecp.quantity ?? "—"}</Info>
          </div>
        </Card>

        {/* stepper */}
        {(user.role === "OWNER" || user.role === "LEAD" || user.role === "MANAGER" || (user.role === "REGISTRATION" && stage !== "PENDING_DOCUMENTS")) && (
          <DocumentsPanel leadId={ecp.lead_id}
            canUpload={(user.role === "OWNER" || user.role === "LEAD") && stage === "PENDING_DOCUMENTS"}
            onChange={load} />
        )}
        <Card className="p-5">
          <div className="flex flex-wrap gap-2">
            {STAGE_ORDER.map((s, i) => {
              const done = ecp.status === "COMPLETED" ? true : i < stageIdx;
              const cur = i === stageIdx && active;
              return (
                <div key={s} data-testid={`ecp-stage-node-${i}`} className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm ${
                  cur ? "bg-sky-600 text-white border-sky-600" : done ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-slate-50 text-slate-400 border-slate-200"
                }`}>
                  {done ? <CheckCircle2 size={15} /> : <Circle size={15} />} {STAGE_LABELS[s]}
                </div>
              );
            })}
          </div>
        </Card>

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {/* stage work */}
            {active && (
              <Card className="p-5">
                <h3 className="font-head font-semibold mb-3">{STAGE_LABELS[stage]} — Stage Work</h3>

                {stage === "DISPATCH" && !ecp.dispatch_started && (
                  <div className="mb-4 p-3 rounded-md border bg-slate-50">
                    {ecp.first_payment_confirmed ? (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-teal-700 font-semibold">Ready for Dispatch — First Payment confirmed</span>
                        {isStageTeam && <Button data-testid="start-dispatch-button" onClick={startDispatch} className="bg-sky-600 hover:bg-sky-700"><Truck size={16} className="mr-1.5" /> Start Dispatch</Button>}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-rose-700 text-sm font-semibold"><Ban size={16} /> Payment Blocked — First Payment must be CONFIRMED by Accounts before dispatch can start.</div>
                    )}
                  </div>
                )}

                {stage === "INSTALLATION" ? (
                  <div className="space-y-3">
                    {ecp.install_status === "AWAITING_ASSIGNMENT" && canAssignInstall && (
                      <Button data-testid="assign-install-button" onClick={() => setAssignDlg(true)} className="bg-sky-600 hover:bg-sky-700"><UserPlus size={16} className="mr-1.5" /> Assign Installation Member</Button>
                    )}
                    <InstallationWork ecp={ecp} onChange={load} />
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {visibleStageTasks.length === 0 && <li className="text-sm text-slate-400">No tasks for this stage.</li>}
                    {visibleStageTasks.map((t) => {
                      const closeNM = isNM && t.task_name === "Close Net Metering";
                      return (
                        <li key={t.id} data-testid={`task-${t.id}`} className="flex items-center justify-between border rounded-md px-3 py-2">
                          <span className={`text-sm ${t.completed ? "text-emerald-700 line-through" : "text-slate-800"}`}>{t.task_name}</span>
                          {t.completed ? (
                            <span className="text-xs text-emerald-600 font-semibold">Done · {t.completed_by_name}</span>
                          ) : closeNM ? (
                            canAssignInstall ? (
                              ecp.responsible_user ? (
                                <span className="text-xs text-slate-600 font-semibold" data-testid="close-nm-assigned">Assigned · {ecp.responsible_user_name}</span>
                              ) : reqNmDone ? (
                                <Button size="sm" data-testid="assign-close-nm-button" onClick={() => setAssignDlg(true)}><UserPlus size={14} className="mr-1" /> Assign</Button>
                              ) : (
                                <span className="text-xs text-slate-400" data-testid="close-nm-awaiting-prereq">Complete 'Request Net Metering' first</span>
                              )
                            ) : isAssignedInstaller ? (
                              <Button size="sm" data-testid={`complete-task-${t.id}`} onClick={() => completeTask(t.id)}>Mark Done</Button>
                            ) : (
                              <span className="text-xs text-slate-400">Awaiting installation team</span>
                            )
                          ) : (
                            isStageTeam && <Button size="sm" data-testid={`complete-task-${t.id}`} onClick={() => completeTask(t.id)} disabled={stage === "DISPATCH" && !ecp.dispatch_started}>Mark Done</Button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {!isStageTeam && !(stage === "INSTALLATION" && canAssignInstall) && !(isNM && (canAssignInstall || isAssignedInstaller)) && <p className="text-xs text-slate-400 mt-3">Read-only — this stage is owned by {ecp.current_team}.</p>}
              </Card>
            )}

            {(stage === "DISPATCH" && (user.role === "DISPATCH" || user.role === "OWNER" || user.role === "MANAGER")) && (
              <DeliveryChallanPanel ecpId={ecp.id} canEdit={user.role === "DISPATCH" || user.role === "OWNER"} />
            )}

            {/* financing */}
            {canFinancing && active && (
              <Card className="p-5 flex items-center justify-between">
                <div>
                  <h3 className="font-head font-semibold">Financing</h3>
                  <p className="text-sm text-slate-500">Toggling changes financing tasks without regressing stage.</p>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox id="ecpfin" data-testid="ecp-financing-toggle" checked={ecp.financing_required} onCheckedChange={(v) => toggleFinancing(!!v)} />
                  <Label htmlFor="ecpfin">Financing Required</Label>
                </div>
              </Card>
            )}

            {/* payments summary */}
            <Card className="p-5">
              <h3 className="font-head font-semibold mb-3 flex items-center gap-2"><Coins size={17} /> Payment Position</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                <Info label="Project Price">{fmt(ecp.project_price)}</Info>
                <Info label="Total Received">{fmt(totalReceived)}</Info>
                <Info label="Total Receivable"><span className="text-rose-700 font-semibold">{fmt(receivable)}</span></Info>
                <Info label="Subsequent Received">{fmt(subConf)}</Info>
              </div>
              <ul className="space-y-2">
                {payments.length === 0 && <li className="text-sm text-slate-400">No payments recorded.</li>}
                {payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between text-sm border-b pb-1">
                    <span><b>{typeLabel(p.type)}</b> · {fmt(p.amount)} · {p.date?.slice(0, 10)}</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge value={p.status} kind={p.status === "CONFIRMED" ? "CONFIRMED" : "PENDING"} label={p.status} />
                      {user.role === "ACCOUNTS" && active && <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" data-testid={`edit-payment-${p.id}`} onClick={() => openEditPay(p)}>Edit</Button>}
                    </div>
                  </li>
                ))}
              </ul>
              {user.role === "ACCOUNTS" && <Button variant="outline" className="mt-3" onClick={() => nav("/payments")}>Go to Payments</Button>}
            </Card>

            {canClose && (
              <Button data-testid="ecp-close-button" variant="destructive" onClick={() => setCloseDlg(true)}>Close / Cancel Project</Button>
            )}
          </div>

          {/* history */}
          <Card className="p-5">
            <h3 className="font-head font-semibold mb-3">Workflow History</h3>
            <ul className="space-y-3">
              {history.map((h) => (
                <li key={h.id} className="text-sm border-l-2 border-sky-200 pl-3">
                  <div className="font-medium">{h.from_stage ? `${STAGE_LABELS[h.from_stage] || h.from_stage} → ` : ""}{STAGE_LABELS[h.to_stage] || h.to_stage}</div>
                  <div className="text-xs text-slate-500">{h.note} · {h.changed_by_name} · {h.changed_at?.slice(0, 16).replace("T", " ")}</div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <Dialog open={closeDlg} onOpenChange={setCloseDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Close / Cancel ECP</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Reason *</Label>
              <Select value={cf.reason} onValueChange={(v) => setCf({ ...cf, reason: v })}>
                <SelectTrigger data-testid="closure-reason-select"><SelectValue placeholder="Select reason" /></SelectTrigger>
                <SelectContent>{CLOSURE_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Remarks {cf.reason === "OTHER" && "*"}</Label><Textarea data-testid="closure-remarks-input" value={cf.remarks || ""} onChange={(e) => setCf({ ...cf, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="closure-submit" variant="destructive" onClick={closeEcp}>Confirm Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={assignDlg} onOpenChange={setAssignDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Assign Installation Employee</DialogTitle></DialogHeader>
          <div><Label>Installation Employee *</Label>
            <Select value={assignUser} onValueChange={setAssignUser}>
              <SelectTrigger data-testid="assign-install-select"><SelectValue placeholder="Select employee" /></SelectTrigger>
              <SelectContent>{installers.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <DialogFooter><Button data-testid="assign-install-submit" onClick={assignInstall} className="bg-sky-600 hover:bg-sky-700">Assign</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={payDlg} onOpenChange={setPayDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit {typeLabel(payForm.type)} Payment</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Amount *</Label><Input data-testid="edit-payment-amount" type="number" value={payForm.amount || ""} onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })} /></div>
            <div><Label>Date *</Label><Input data-testid="edit-payment-date" type="date" value={payForm.date || ""} onChange={(e) => setPayForm({ ...payForm, date: e.target.value })} /></div>
            <div><Label>Status</Label>
              <Select value={payForm.status} onValueChange={(v) => setPayForm({ ...payForm, status: v })}>
                <SelectTrigger data-testid="edit-payment-status"><SelectValue /></SelectTrigger>
                <SelectContent>{["PENDING", "CONFIRMED"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Remarks</Label><Textarea data-testid="edit-payment-remarks" value={payForm.remarks || ""} onChange={(e) => setPayForm({ ...payForm, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="edit-payment-submit" onClick={savePayEdit} className="bg-sky-600 hover:bg-sky-700">Save Changes</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Info({ label, children }) {
  return <div><div className="text-xs font-mono uppercase tracking-wider text-slate-500">{label}</div><div className="mt-1 font-medium text-slate-900">{children}</div></div>;
}
