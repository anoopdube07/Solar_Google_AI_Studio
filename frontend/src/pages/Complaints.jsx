import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

const PRIOS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const TEAMS = ["LEAD", "REGISTRATION", "ACCOUNTS", "DISPATCH", "INSTALLATION"];

export default function Complaints() {
  const { user } = useAuth();
  const [list, setList] = useState([]);
  const [cats, setCats] = useState([]);
  const [regDlg, setRegDlg] = useState(false);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState({ title: "", description: "", category_id: "", priority: "MEDIUM", customer_name: "", customer_phone: "" });
  const [assign, setAssign] = useState({ assigned_team: "", assigned_user: "" });
  const [members, setMembers] = useState([]);
  const [reject, setReject] = useState("");

  const isOwner = user.role === "OWNER";
  const isManager = user.role === "MANAGER" || isOwner;
  const canRegister = user.role === "COMPLAINT" || isManager;

  const load = () => api.get("/complaints").then((r) => setList(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/complaint-categories?active_only=true").then((r) => setCats(r.data)).catch(() => {}); }, []);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    if (p.get("new") === "1" && canRegister) setRegDlg(true);
  }, []);

  const register = async () => {
    try { await api.post("/complaints", form); toast.success("Complaint registered"); setRegDlg(false); setForm({ title: "", description: "", category_id: "", priority: "MEDIUM", customer_name: "", customer_phone: "" }); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const open = async (c) => { const r = await api.get(`/complaints/${c.id}`); setDetail(r.data); setAssign({ assigned_team: r.data.complaint.assigned_team || "", assigned_user: "" }); };
  const loadMembers = (team) => { setAssign((a) => ({ ...a, assigned_team: team, assigned_user: "" })); api.get(`/users/team/${team}`).then((r) => setMembers(r.data)).catch(() => setMembers([])); };
  const doAssign = async () => {
    try { await api.post(`/complaints/${detail.complaint.id}/assign`, assign); toast.success("Assigned"); const r = await api.get(`/complaints/${detail.complaint.id}`); setDetail(r.data); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const setStatus = async (status) => {
    try { await api.post(`/complaints/${detail.complaint.id}/status`, { status, remarks: reject }); toast.success(`Marked ${status}`); setReject(""); const r = await api.get(`/complaints/${detail.complaint.id}`); setDetail(r.data); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const c = detail?.complaint;
  const isAssignee = c && c.assigned_user === user.id;

  return (
    <div>
      <PageHeader title="Complaint Portal" subtitle="Register, assign and resolve customer complaints"
        right={canRegister ? <Button data-testid="register-complaint-btn" onClick={() => setRegDlg(true)}>Register Complaint</Button> : null} />
      <div className="p-4 lg:p-8 space-y-3">
        {list.map((x) => (
          <Card key={x.id} data-testid={`complaint-row-${x.id}`} className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-50" onClick={() => open(x)}>
            <div className="min-w-0">
              <div className="font-semibold truncate">{x.title} <span className="text-xs text-slate-400">· {x.category_name}</span></div>
              <div className="text-xs text-slate-500">{x.customer_name || "—"} · {x.assigned_user_name || x.assigned_team || "Unassigned"}</div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-xs font-bold px-2 py-1 rounded-full ${x.priority === "CRITICAL" ? "bg-red-100 text-red-700" : x.priority === "HIGH" ? "bg-orange-100 text-orange-700" : "bg-slate-100 text-slate-600"}`}>{x.priority}</span>
              <span className="text-xs font-semibold px-2 py-1 rounded-full border">{x.status}</span>
              {x.overdue && <span data-testid={`complaint-overdue-${x.id}`} className="text-xs font-bold px-2 py-1 rounded-full bg-red-100 text-red-700">OVERDUE {x.days_overdue}d</span>}
              {x.due_today && <span className="text-xs font-bold px-2 py-1 rounded-full bg-amber-100 text-amber-700">DUE TODAY</span>}
            </div>
          </Card>
        ))}
        {list.length === 0 && <p className="text-slate-400 text-center py-10">No complaints.</p>}
      </div>

      <Dialog open={regDlg} onOpenChange={setRegDlg}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Register Complaint</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Title *</Label><Input data-testid="complaint-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
            <div><Label>Description</Label><Textarea data-testid="complaint-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
            <div><Label>Category *</Label>
              <Select value={form.category_id} onValueChange={(v) => setForm({ ...form, category_id: v })}>
                <SelectTrigger data-testid="complaint-category"><SelectValue placeholder="Select category" /></SelectTrigger>
                <SelectContent>{cats.map((c2) => <SelectItem key={c2.id} value={c2.id}>{c2.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Priority *</Label>
              <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
                <SelectTrigger data-testid="complaint-priority"><SelectValue /></SelectTrigger>
                <SelectContent>{PRIOS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Customer Name</Label><Input data-testid="complaint-cust-name" value={form.customer_name} onChange={(e) => setForm({ ...form, customer_name: e.target.value })} /></div>
              <div><Label>Customer Phone</Label><Input data-testid="complaint-cust-phone" value={form.customer_phone} onChange={(e) => setForm({ ...form, customer_phone: e.target.value })} /></div>
            </div>
          </div>
          <DialogFooter><Button data-testid="complaint-submit" onClick={register} className="bg-sky-600 hover:bg-sky-700">Register</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{c?.title}</DialogTitle></DialogHeader>
          {c && (
            <div className="space-y-3 text-sm">
              <div className="text-slate-600">{c.description}</div>
              <div>Category: <b>{c.category_name}</b> · Priority: <b>{c.priority}</b> · Status: <b data-testid="complaint-detail-status">{c.status}</b></div>
              <div>Assigned: {c.assigned_user_name || c.assigned_team || "—"} {c.sla_due_date ? `· SLA due ${c.sla_due_date}` : ""} {c.overdue ? `· OVERDUE ${c.days_overdue}d` : ""}</div>
              {isManager && !["CLOSED"].includes(c.status) && (
                <div className="border-t pt-3 space-y-2">
                  <Label>Assign to Team / Member</Label>
                  <div className="flex gap-2">
                    <Select value={assign.assigned_team} onValueChange={loadMembers}>
                      <SelectTrigger data-testid="complaint-assign-team"><SelectValue placeholder="Team" /></SelectTrigger>
                      <SelectContent>{TEAMS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                    </Select>
                    <Select value={assign.assigned_user} onValueChange={(v) => setAssign({ ...assign, assigned_user: v })}>
                      <SelectTrigger data-testid="complaint-assign-user"><SelectValue placeholder="Member" /></SelectTrigger>
                      <SelectContent>{members.map((m) => <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>)}</SelectContent>
                    </Select>
                    <Button data-testid="complaint-assign-btn" onClick={doAssign}>Assign</Button>
                  </div>
                </div>
              )}
              <div className="border-t pt-3 flex flex-wrap gap-2">
                {(isAssignee || isOwner) && c.status === "ASSIGNED" && <Button size="sm" data-testid="complaint-inprogress" onClick={() => setStatus("IN_PROGRESS")}>Start (In Progress)</Button>}
                {(isAssignee || isOwner) && c.status === "IN_PROGRESS" && <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" data-testid="complaint-resolve" onClick={() => setStatus("RESOLVED")}>Mark Resolved</Button>}
                {isManager && c.status === "RESOLVED" && <Button size="sm" className="bg-slate-800" data-testid="complaint-close" onClick={() => setStatus("CLOSED")}>Accept &amp; Close</Button>}
              </div>
              <div className="border-t pt-3">
                <div className="text-xs font-mono uppercase text-slate-400 mb-1">History</div>
                <ul className="space-y-1 text-xs text-slate-500">
                  {detail.history.map((h) => <li key={h.id}>{h.ts?.slice(0, 16).replace("T", " ")} · {h.user_name} · {h.action} {h.details ? `— ${h.details}` : ""}</li>)}
                </ul>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
