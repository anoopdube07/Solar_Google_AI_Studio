import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { StatusBadge } from "@/components/StatusBadge";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { RETURN_REASON_LABELS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CheckCircle2, XCircle, CalendarClock, MapPin, AlertTriangle, RotateCcw, FileText, Pencil, TrendingUp } from "lucide-react";
import { toast } from "sonner";

const LOST_REASONS = ["PRICE", "COMPETITOR", "NOT_INTERESTED", "UNREACHABLE", "OTHER"];

export default function LeadDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [dlg, setDlg] = useState(null); // YES|NO|FOLLOW_UP|SITE_VISIT|ESCALATION
  const [f, setF] = useState({});
  const [priceDlg, setPriceDlg] = useState(false);
  const [priceVal, setPriceVal] = useState("");
  const [reassignDlg, setReassignDlg] = useState(false);
  const [leadUsers, setLeadUsers] = useState([]);
  const [reassignTo, setReassignTo] = useState("");
  const [items, setItems] = useState([]);
  const [commDlg, setCommDlg] = useState(false);
  const [comm, setComm] = useState({ item_id: "", quantity: "", project_price: "" });
  const [editDlg, setEditDlg] = useState(false);
  const [editForm, setEditForm] = useState({ email: "", address: "", location_link: "" });
  const [rejectRemarks, setRejectRemarks] = useState("");

  const load = () => api.get(`/leads/${id}`).then((r) => setData(r.data));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (user.role === "MANAGER" || user.role === "OWNER") {
      api.get("/users/team/LEAD").then((r) => setLeadUsers(r.data)).catch(() => {});
    }
    api.get("/items?active_only=true").then((r) => setItems(r.data)).catch(() => {});
  }, [user.role]);
  if (!data) return <div className="p-8 text-slate-500">Loading…</div>;

  const { lead, followups, site_visits, escalations, ecp } = data;
  const canAct = user.role === "LEAD" && lead.action_required;
  const canReopen = user.role === "OWNER" && lead.status === "LOST";
  const canReassign = (user.role === "MANAGER" || user.role === "OWNER") && lead.status !== "LOST";
  const isOwnerLead = user.role === "LEAD" && lead.lead_owner_id && lead.lead_owner_id === user.id;
  const handedOff = !!lead.ecp_id;
  const canEditPrice = (user.role === "LEAD" || user.role === "OWNER") && lead.status !== "LOST" && !handedOff;
  const canEditLead = ((user.role === "LEAD" && (isOwnerLead || !lead.lead_owner_id)) || user.role === "OWNER") && lead.status !== "LOST";
  const canCommercial = (isOwnerLead || (user.role === "LEAD" && !lead.lead_owner_id)) && lead.status !== "LOST";
  const pcc = lead.pending_commercial_change;
  const pccPending = pcc && pcc.status === "PENDING";
  const fmt = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");

  const doReassign = async () => {
    if (!reassignTo) { toast.error("Select a Lead Team user"); return; }
    try { await api.post(`/leads/${id}/reassign`, { assigned_user: reassignTo }); toast.success("Lead reassigned"); setReassignDlg(false); setReassignTo(""); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const doAction = async (payload) => {
    try {
      await api.post(`/leads/${id}/action`, payload);
      toast.success("Lead updated");
      setDlg(null); setF({});
      load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const reopen = async () => {
    try { await api.post(`/leads/${id}/reopen`); toast.success("Lead reopened"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const savePrice = async () => {
    try { await api.post(`/leads/${id}/project-price`, { project_price: parseFloat(priceVal) || 0 }); toast.success("Project price saved"); setPriceDlg(false); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const openEdit = () => { setEditForm({ email: lead.email || "", address: lead.address || "", location_link: lead.location_link || "" }); setEditDlg(true); };
  const saveEdit = async () => {
    try { await api.patch(`/leads/${id}`, editForm); toast.success("Lead updated"); setEditDlg(false); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const openComm = () => { setComm({ item_id: lead.item_id || "", quantity: lead.quantity ?? "", project_price: lead.project_price ?? "" }); setCommDlg(true); };
  const submitComm = async () => {
    const payload = {};
    if (comm.item_id && comm.item_id !== lead.item_id) payload.item_id = comm.item_id;
    if (comm.quantity !== "" && parseFloat(comm.quantity) !== lead.quantity) payload.quantity = parseFloat(comm.quantity);
    if (comm.project_price !== "" && parseFloat(comm.project_price) !== lead.project_price) payload.project_price = parseFloat(comm.project_price);
    if (Object.keys(payload).length === 0) { toast.error("Change at least one value"); return; }
    try { await api.post(`/leads/${id}/commercial-change`, payload); toast.success("Commercial change requested"); setCommDlg(false); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const decideComm = async (approve) => {
    if (!approve && !rejectRemarks.trim()) { toast.error("Rejection remarks are mandatory"); return; }
    try {
      await api.post(`/leads/${id}/commercial-change/${approve ? "approve" : "reject"}`, { remarks: rejectRemarks });
      toast.success(approve ? "Change approved" : "Change rejected"); setRejectRemarks(""); load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const downloadQuotation = async () => {
    try {
      const res = await api.get(`/leads/${id}/quotation`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const fname = `quotation_${lead.name.replace(/\s+/g, "_")}.pdf`;
      const file = new File([blob], fname, { type: "application/pdf" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try { await navigator.share({ files: [file], title: "Quotation", text: `Quotation for ${lead.name}` }); return; }
        catch (_) { /* user cancelled → fall through to download */ }
      }
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = fname; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const submit = () => {
    if (dlg === "YES") return doAction({ action: "YES" });
    if (dlg === "NO") return doAction({ action: "NO", lost_reason: f.lost_reason, lost_remarks: f.lost_remarks });
    if (dlg === "FOLLOW_UP") return doAction({ action: "FOLLOW_UP", followup_date: f.followup_date, remarks: f.remarks });
    if (dlg === "SITE_VISIT") return doAction({ action: "SITE_VISIT", remarks: f.remarks });
    if (dlg === "ESCALATION") return doAction({ action: "ESCALATION", reason: f.reason, remarks: f.remarks });
  };

  const actions = [
    ["YES", "Qualify (YES)", CheckCircle2, "bg-emerald-600 hover:bg-emerald-700"],
    ["NO", "Mark Lost (NO)", XCircle, "bg-slate-600 hover:bg-slate-700"],
    ["FOLLOW_UP", "Follow-up", CalendarClock, "bg-blue-600 hover:bg-blue-700"],
    ["SITE_VISIT", "Request Site Visit", MapPin, "bg-purple-600 hover:bg-purple-700"],
    ["ESCALATION", "Escalate to Owner", AlertTriangle, "bg-red-600 hover:bg-red-700"],
  ];

  return (
    <div>
      <PageHeader title={lead.name} subtitle={`${lead.phone} · ${lead.email || "no email"}`}
        right={<div className="flex gap-2">
          <Button data-testid="lead-quotation-btn" variant="secondary" onClick={downloadQuotation}><FileText size={16} className="mr-1.5" /> Quotation</Button>
          <Button variant="secondary" onClick={() => nav("/leads")}>Back</Button>
        </div>} />
      <div className="p-6 lg:p-8 grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {/* highlight box */}
          <Card className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-head font-semibold">Lead Details</h3>
              {canEditLead && <Button data-testid="lead-edit-btn" size="sm" variant="outline" onClick={openEdit}><Pencil size={14} className="mr-1.5" /> Edit</Button>}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <Field label="Status"><StatusBadge value={lead.status} /></Field>
              <Field label="Current Team">{lead.current_team || "—"}</Field>
              <Field label="Action Required">{lead.action_required ? <span className="text-amber-600 font-semibold">YES</span> : "No"}</Field>
              <Field label="Financing">{lead.financing_required ? "Required" : "Not required"}</Field>
              <Field label="Item">{lead.item_name ? `${lead.item_name} (${lead.item_unit})` : "—"}</Field>
              <Field label="Quantity"><span data-testid="lead-quantity">{lead.quantity ?? "—"}</span></Field>
              <Field label="Location">{lead.location_link ? <a href={lead.location_link} target="_blank" rel="noreferrer" className="text-sky-600 underline">Open map</a> : "—"}</Field>
              <Field label="Project Price">
                <span data-testid="lead-project-price">{lead.project_price ? fmt(lead.project_price) : "—"}</span>
                {canEditPrice && <button data-testid="lead-edit-price-btn" className="ml-2 text-xs text-sky-600 underline" onClick={() => { setPriceVal(lead.project_price || ""); setPriceDlg(true); }}>edit</button>}
              </Field>
            </div>
            {lead.return_reason && (
              <div className="mt-4 text-sm bg-sky-50 border border-sky-200 rounded-md px-3 py-2 text-sky-800" data-testid="lead-return-reason">
                Returned to Lead Team · <b>{RETURN_REASON_LABELS[lead.return_reason]}</b>
              </div>
            )}
            {lead.status === "LOST" && (
              <div className="mt-4 text-sm bg-slate-50 border border-slate-200 rounded-md px-3 py-2 text-slate-700">
                Lost reason: <b>{lead.lost_reason}</b>{lead.lost_remarks ? ` — ${lead.lost_remarks}` : ""}
              </div>
            )}
          </Card>

          {/* actions */}
          {canAct && (
            <Card className="p-5">
              <h3 className="font-head font-semibold mb-3">Lead Team Actions</h3>
              <div className="flex flex-wrap gap-2">
                {actions.map(([key, label, Icon, cls]) => (
                  <Button key={key} data-testid={`lead-action-${key.toLowerCase()}`} className={`${cls} text-white`} onClick={() => { setDlg(key); setF({}); }}>
                    <Icon size={16} className="mr-1.5" /> {label}
                  </Button>
                ))}
              </div>
            </Card>
          )}
          {canReopen && (
            <Card className="p-5">
              <Button data-testid="lead-reopen-button" variant="outline" onClick={reopen}><RotateCcw size={16} className="mr-1.5" /> Reopen Lost Lead</Button>
            </Card>
          )}
          {canReassign && (
            <Card className="p-5 flex items-center justify-between">
              <div>
                <h3 className="font-head font-semibold">Lead Owner</h3>
                <p className="text-sm text-slate-500">Current: <b>{lead.lead_owner_name || "—"}</b> · Creator: {lead.lead_creator_name || "—"}</p>
              </div>
              <Button data-testid="lead-reassign-button" variant="outline" onClick={() => { setReassignTo(""); setReassignDlg(true); }}>Reassign</Button>
            </Card>
          )}
          {canCommercial && handedOff && !pccPending && (
            <Card className="p-5 flex items-center justify-between" data-testid="commercial-request-card">
              <div>
                <h3 className="font-head font-semibold">Commercial Change</h3>
                <p className="text-sm text-slate-500">Lead is handed off. Item, quantity & price changes need Owner approval.</p>
              </div>
              <Button data-testid="commercial-request-btn" variant="outline" onClick={openComm}><TrendingUp size={16} className="mr-1.5" /> Request Change</Button>
            </Card>
          )}
          {pcc && (
            <Card className="p-5" data-testid="commercial-change-card">
              <div className="flex items-center gap-2 mb-3">
                <h3 className="font-head font-semibold">Commercial Change</h3>
                <StatusBadge value={pcc.status} />
              </div>
              <div className="text-sm text-slate-600 space-y-1">
                <div>Requested by <b>{pcc.requested_by_name}</b></div>
                <ChangeRow label="Item" cur={pcc.current.item_name} nxt={pcc.proposed.item_name} />
                <ChangeRow label="Quantity" cur={pcc.current.quantity} nxt={pcc.proposed.quantity} />
                <ChangeRow label="Project Price" cur={pcc.current.project_price} nxt={pcc.proposed.project_price} money fmt={fmt} />
                {pcc.decision_remarks && <div className="mt-2">Decision remarks: <i>{pcc.decision_remarks}</i></div>}
                {pcc.decided_by && <div className="text-xs text-slate-400">{pcc.status} by {pcc.decided_by}</div>}
              </div>
              {user.role === "OWNER" && pccPending && (
                <div className="mt-4 space-y-3 border-t pt-4">
                  <div><Label>Rejection Remarks (required to reject)</Label><Textarea data-testid="commercial-reject-remarks" value={rejectRemarks} onChange={(e) => setRejectRemarks(e.target.value)} /></div>
                  <div className="flex gap-2">
                    <Button data-testid="commercial-approve-btn" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={() => decideComm(true)}>Approve</Button>
                    <Button data-testid="commercial-reject-btn" className="bg-red-600 hover:bg-red-700 text-white" onClick={() => decideComm(false)}>Reject</Button>
                  </div>
                </div>
              )}
            </Card>
          )}
          {ecp && (
            <Card className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-mono uppercase text-slate-500">Linked ECP Project</div>
                  <div className="font-semibold mt-1">{ecp.lead_name} · <StatusBadge value={ecp.current_stage} /></div>
                </div>
                <Button variant="outline" onClick={() => nav(`/ecps/${ecp.id}`)}>Open ECP</Button>
              </div>
            </Card>
          )}
          {ecp && (
            <DocumentsPanel leadId={id}
              canUpload={(isOwnerLead || user.role === "OWNER") && ecp.current_stage === "PENDING_DOCUMENTS"}
              onChange={load} />
          )}
        </div>

        {/* history */}
        <div className="space-y-6">
          <HistoryCard title="Follow-ups" items={followups} render={(x) => `${x.followup_date?.slice(0, 10)} — ${x.remarks}`} empty="No follow-ups" />
          <HistoryCard title="Site Visits" items={site_visits} render={(x) => `${x.status}${x.visit_date ? " · " + x.visit_date.slice(0, 10) : ""}${x.assigned_user_name ? " · " + x.assigned_user_name : ""}${x.survey_info ? " · " + x.survey_info : ""}`} empty="No site visits" />
          <HistoryCard title="Escalations" items={escalations} render={(x) => `${x.status} · ${x.reason}${x.owner_remarks ? " · Owner: " + x.owner_remarks : ""}`} empty="No escalations" />
        </div>
      </div>

      {/* action dialog */}
      <Dialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{dlg && actions.find((a) => a[0] === dlg)?.[1]}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {dlg === "YES" && <p className="text-sm text-slate-600">This will qualify the lead and automatically create one ECP project at Registration 1.</p>}
            {dlg === "NO" && (<>
              <div><Label>Lost Reason *</Label>
                <Select value={f.lost_reason} onValueChange={(v) => setF({ ...f, lost_reason: v })}>
                  <SelectTrigger data-testid="lost-reason-select"><SelectValue placeholder="Select reason" /></SelectTrigger>
                  <SelectContent>{LOST_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Remarks {f.lost_reason === "OTHER" && "*"}</Label><Textarea data-testid="lost-remarks-input" value={f.lost_remarks || ""} onChange={(e) => setF({ ...f, lost_remarks: e.target.value })} /></div>
            </>)}
            {dlg === "FOLLOW_UP" && (<>
              <div><Label>Follow-up Date *</Label><Input data-testid="followup-date-input" type="date" value={f.followup_date || ""} onChange={(e) => setF({ ...f, followup_date: e.target.value })} /></div>
              <div><Label>Remarks *</Label><Textarea data-testid="followup-remarks-input" value={f.remarks || ""} onChange={(e) => setF({ ...f, remarks: e.target.value })} /></div>
            </>)}
            {dlg === "SITE_VISIT" && (<>
              <p className="text-sm text-slate-600">A site visit request will be created for the Manager to assign an Installation employee.</p>
              <div><Label>Remarks</Label><Textarea data-testid="sitevisit-remarks-input" value={f.remarks || ""} onChange={(e) => setF({ ...f, remarks: e.target.value })} /></div>
            </>)}
            {dlg === "ESCALATION" && (<>
              <div><Label>Reason *</Label><Input data-testid="escalation-reason-input" value={f.reason || ""} onChange={(e) => setF({ ...f, reason: e.target.value })} /></div>
              <div><Label>Remarks *</Label><Textarea data-testid="escalation-remarks-input" value={f.remarks || ""} onChange={(e) => setF({ ...f, remarks: e.target.value })} /></div>
            </>)}
          </div>
          <DialogFooter><Button data-testid="lead-action-submit" onClick={submit} className="bg-sky-600 hover:bg-sky-700">Confirm</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={priceDlg} onOpenChange={setPriceDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Project Price / Customer Agreed Price</DialogTitle></DialogHeader>
          <div><Label>Amount (₹)</Label><Input data-testid="lead-price-input" type="number" value={priceVal} onChange={(e) => setPriceVal(e.target.value)} /></div>
          <DialogFooter><Button data-testid="lead-price-save" onClick={savePrice} className="bg-sky-600 hover:bg-sky-700">Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reassignDlg} onOpenChange={setReassignDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reassign Lead Owner</DialogTitle></DialogHeader>
          <div><Label>Lead Team User *</Label>
            <Select value={reassignTo} onValueChange={setReassignTo}>
              <SelectTrigger data-testid="reassign-user-select"><SelectValue placeholder="Select user" /></SelectTrigger>
              <SelectContent>{leadUsers.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <DialogFooter><Button data-testid="reassign-submit" onClick={doReassign} className="bg-sky-600 hover:bg-sky-700">Reassign</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editDlg} onOpenChange={setEditDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Lead</DialogTitle></DialogHeader>
          {handedOff && <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">This lead is handed off. Only contact details can be edited here — use a Commercial Change to modify item, quantity or price.</p>}
          <div className="space-y-3">
            <div><Label>Email</Label><Input data-testid="edit-email-input" value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} /></div>
            <div><Label>Address</Label><Input data-testid="edit-address-input" value={editForm.address} onChange={(e) => setEditForm({ ...editForm, address: e.target.value })} /></div>
            <div><Label>Location Link</Label><Input data-testid="edit-location-input" value={editForm.location_link} onChange={(e) => setEditForm({ ...editForm, location_link: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="edit-lead-save" onClick={saveEdit} className="bg-sky-600 hover:bg-sky-700">Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={commDlg} onOpenChange={setCommDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Request Commercial Change</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-500">Proposed changes require Owner approval before they take effect.</p>
          <div className="space-y-3">
            <div><Label>Item</Label>
              <Select value={comm.item_id} onValueChange={(v) => setComm({ ...comm, item_id: v })}>
                <SelectTrigger data-testid="comm-item-select"><SelectValue placeholder="Select item" /></SelectTrigger>
                <SelectContent>{items.map((it) => <SelectItem key={it.id} value={it.id}>{it.name} ({it.unit})</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Quantity</Label><Input data-testid="comm-quantity-input" type="number" value={comm.quantity} onChange={(e) => setComm({ ...comm, quantity: e.target.value })} /></div>
            <div><Label>Project Price (₹)</Label><Input data-testid="comm-price-input" type="number" value={comm.project_price} onChange={(e) => setComm({ ...comm, project_price: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="comm-submit" onClick={submitComm} className="bg-sky-600 hover:bg-sky-700">Submit for Approval</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ChangeRow({ label, cur, nxt, money, fmt }) {
  if (nxt === undefined || nxt === null) return null;
  const show = (v) => (v === undefined || v === null || v === "" ? "—" : money ? fmt(v) : v);
  return <div><span className="text-slate-400">{label}:</span> <span className="line-through">{show(cur)}</span> → <b>{show(nxt)}</b></div>;
}

function Field({ label, children }) {
  return <div><div className="text-xs font-mono uppercase tracking-wider text-slate-500">{label}</div><div className="mt-1 font-medium text-slate-900">{children}</div></div>;
}
function HistoryCard({ title, items, render, empty }) {
  return (
    <Card className="p-5">
      <h3 className="font-head font-semibold mb-3">{title}</h3>
      <ul className="space-y-2">
        {items.length === 0 && <li className="text-sm text-slate-400">{empty}</li>}
        {items.map((x) => <li key={x.id} className="text-sm text-slate-700 border-l-2 border-slate-200 pl-3">{render(x)}</li>)}
      </ul>
    </Card>
  );
}
