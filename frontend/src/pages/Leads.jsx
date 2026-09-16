import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { StatusBadge } from "@/components/StatusBadge";
import { RETURN_REASON_LABELS, LEAD_STATUS_LABELS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";

const STATUS_OPTS = ["ALL", "PENDING", "FOLLOW_UP", "SITE_VISIT", "ESCALATED", "QUALIFIED", "LOST"];

export default function Leads() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const params = new URLSearchParams(loc.search);
  const statusFilter = params.get("status") || "";
  const followupFilter = params.get("followup") || "";
  const [leads, setLeads] = useState([]);
  const [items, setItems] = useState([]);
  const [req, setReq] = useState({});
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", email: "", address: "", source: "", financing_required: false, project_price: "", item_id: "", quantity: "", location_link: "", remarks: "" });

  const load = () => {
    const p = new URLSearchParams();
    if (statusFilter) p.set("status", statusFilter);
    if (followupFilter) p.set("followup", followupFilter);
    api.get(`/leads${p.toString() ? "?" + p.toString() : ""}`).then((r) => setLeads(r.data));
  };
  useEffect(() => { load(); }, [statusFilter, followupFilter]);
  useEffect(() => {
    api.get("/items?active_only=true").then((r) => setItems(r.data)).catch(() => {});
    api.get("/lead-field-config").then((r) => setReq(r.data.fields || {})).catch(() => {});
  }, []);

  const canCreate = user.role === "LEAD" || user.role === "OWNER";
  const filtered = leads.filter((l) => !q || l.name.toLowerCase().includes(q.toLowerCase()) || (l.phone || "").includes(q));
  const mark = (k) => (req[k] ? " *" : "");

  const create = async () => {
    if (!form.name || !form.phone) { toast.error("Name and phone are required"); return; }
    try {
      await api.post("/leads", {
        ...form,
        project_price: parseFloat(form.project_price) || 0,
        quantity: form.quantity === "" ? null : parseFloat(form.quantity),
        item_id: form.item_id || null,
      });
      toast.success("Lead created");
      setOpen(false);
      setForm({ name: "", phone: "", email: "", address: "", source: "", financing_required: false, project_price: "", item_id: "", quantity: "", location_link: "", remarks: "" });
      load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const setStatus = (v) => {
    if (v === "ALL") nav("/leads");
    else nav(`/leads?status=${v}`);
  };
  const activeStatus = followupFilter ? "FOLLOW_TODAY" : (statusFilter || "ALL");

  return (
    <div>
      <PageHeader title="Leads" subtitle="Lead qualification workspace"
        right={canCreate && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="new-lead-button" className="bg-sky-600 hover:bg-sky-700"><Plus size={16} className="mr-1" /> New Lead</Button>
            </DialogTrigger>
            <DialogContent className="max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>Create Lead</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div><Label>Name *</Label><Input data-testid="lead-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
                <div><Label>Phone *</Label><Input data-testid="lead-phone-input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Email{mark("email")}</Label><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
                  <div><Label>Source</Label><Input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} /></div>
                </div>
                <div><Label>Address{mark("address")}</Label><Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></div>
                <div><Label>Item{mark("item")}</Label>
                  <Select value={form.item_id} onValueChange={(v) => setForm({ ...form, item_id: v })}>
                    <SelectTrigger data-testid="lead-item-select"><SelectValue placeholder="Select item" /></SelectTrigger>
                    <SelectContent>{items.map((it) => <SelectItem key={it.id} value={it.id}>{it.name} ({it.unit})</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Quantity{mark("quantity")}</Label><Input data-testid="lead-quantity-input" type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></div>
                  <div><Label>Project Price (₹){mark("project_price")}</Label><Input data-testid="lead-project-price-input" type="number" value={form.project_price} onChange={(e) => setForm({ ...form, project_price: e.target.value })} /></div>
                </div>
                <div><Label>Location Link{mark("location_link")}</Label><Input data-testid="lead-location-input" placeholder="Google Maps link" value={form.location_link} onChange={(e) => setForm({ ...form, location_link: e.target.value })} /></div>
                <div className="flex items-center gap-2">
                  <Checkbox id="fin" checked={form.financing_required} onCheckedChange={(v) => setForm({ ...form, financing_required: !!v })} data-testid="lead-financing-checkbox" />
                  <Label htmlFor="fin">Financing Required</Label>
                </div>
                <div><Label>Remarks</Label><Textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></div>
              </div>
              <DialogFooter><Button data-testid="lead-create-submit" onClick={create} className="bg-sky-600 hover:bg-sky-700">Create</Button></DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      />
      <div className="p-4 lg:p-8">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-sm min-w-[200px]">
            <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
            <Input data-testid="lead-search" className="pl-9" placeholder="Search name or phone…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select value={activeStatus === "FOLLOW_TODAY" ? "ALL" : activeStatus} onValueChange={setStatus}>
            <SelectTrigger data-testid="lead-status-filter" className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>{STATUS_OPTS.map((s) => <SelectItem key={s} value={s} data-testid={`lead-status-${s}`}>{s === "ALL" ? "All Statuses" : LEAD_STATUS_LABELS[s]}</SelectItem>)}</SelectContent>
          </Select>
          {followupFilter === "today" && <span className="text-xs font-semibold text-sky-700">Follow-ups Today <button className="underline ml-1" onClick={() => nav("/leads")}>clear</button></span>}
        </div>
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead>Name</TableHead><TableHead>Phone</TableHead><TableHead>Status</TableHead>
                <TableHead>Lead Creator</TableHead><TableHead>Current Team</TableHead><TableHead>Note</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((l) => (
                <TableRow key={l.id} data-testid={`lead-row-${l.id}`} className="hover:bg-slate-50 cursor-pointer" onClick={() => nav(`/leads/${l.id}`)}>
                  <TableCell className="font-semibold text-slate-900">{l.name}</TableCell>
                  <TableCell className="font-mono text-sm">{l.phone}</TableCell>
                  <TableCell><StatusBadge value={l.status} /></TableCell>
                  <TableCell className="text-sm">{l.lead_creator_name || "—"}</TableCell>
                  <TableCell className="text-sm">{l.current_team || "—"}</TableCell>
                  <TableCell className="text-xs text-slate-500">
                    {l.action_required && <span className="text-amber-600 font-semibold">Action Required</span>}
                    {l.return_reason && <span className="ml-1">· {RETURN_REASON_LABELS[l.return_reason]}</span>}
                  </TableCell>
                </TableRow>
              ))}
              {filtered.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-slate-400 py-10">No leads found.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
