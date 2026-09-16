import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Search } from "lucide-react";
import { toast } from "sonner";

const fmt = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");
// UI label -> backend type
const TYPE_OPTIONS = [
  ["FIRST", "First Payment"],
  ["ADDITIONAL", "Subsequent Payment"],
];

export default function Payments() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const viewParam = new URLSearchParams(loc.search).get("view") || "";
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [dlg, setDlg] = useState(false);
  const [detail, setDetail] = useState(null); // ecp row for transaction view
  const [f, setF] = useState({});

  const canEdit = user.role === "ACCOUNTS";
  const load = () => api.get("/payments/monitor").then((r) => setRows(r.data));
  useEffect(() => { load(); }, []);

  const openNew = (row) => { setF({ ecp_id: row.ecp_id, lead_name: row.lead_name, type: "FIRST", status: "PENDING", amount: "", date: "", remarks: "" }); setDlg(true); };

  const save = async () => {
    if (!f.amount || !f.date) { toast.error("Amount and date are required"); return; }
    try {
      await api.post("/payments", { ecp_id: f.ecp_id, type: f.type, amount: parseFloat(f.amount), date: f.date, status: f.status, remarks: f.remarks });
      toast.success("Payment recorded"); setDlg(false); load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const matchesView = (r) => {
    if (r.status !== "ACTIVE") return viewParam ? false : true;
    if (viewParam === "first_pending") return !r.first_payment_confirmed;
    if (viewParam === "subsequent") return r.first_payment_confirmed && r.total_receivable > 0;
    if (viewParam === "receivable") return r.total_receivable > 0;
    return true;
  };
  const filtered = rows.filter((r) => (!q || r.lead_name.toLowerCase().includes(q.toLowerCase())) && matchesView(r));
  const VIEW_LABELS = { first_pending: "First Payment Pending", subsequent: "Subsequent Payment Follow-up", receivable: "Total Receivable" };

  return (
    <div>
      <PageHeader title="Payments" subtitle="Project-wise receivables. Only Accounts can record payments." />
      <div className="p-4 lg:p-8">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="relative max-w-sm flex-1 min-w-[200px]">
            <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
            <Input data-testid="payment-search" className="pl-9" placeholder="Search project / customer…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {viewParam && <span className="text-xs font-semibold text-sky-700" data-testid="payment-view-chip">{VIEW_LABELS[viewParam]} <button className="underline ml-1" onClick={() => nav("/payments")}>clear</button></span>}
          <span className="text-xs text-slate-400 font-mono">{filtered.length} project(s)</span>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead>Customer</TableHead><TableHead>Lead Creator</TableHead><TableHead>Stage</TableHead>
                <TableHead className="text-right">Project Price</TableHead>
                <TableHead className="text-right">First</TableHead>
                <TableHead className="text-right">Subsequent</TableHead>
                <TableHead className="text-right">Total Received</TableHead>
                <TableHead className="text-right">Total Receivable</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r) => (
                <TableRow key={r.ecp_id} data-testid={`pay-row-${r.ecp_id}`} className="hover:bg-slate-50">
                  <TableCell>
                    <button className="font-semibold text-sky-700 hover:underline" onClick={() => setDetail(r)}>{r.lead_name}</button>
                  </TableCell>
                  <TableCell className="text-sm">{r.lead_creator_name || "—"}</TableCell>
                  <TableCell><StatusBadge value={r.stage} /></TableCell>
                  <TableCell className="text-right font-mono">{fmt(r.project_price)}</TableCell>
                  <TableCell className="text-right font-mono">{fmt(r.first_confirmed_amount)}</TableCell>
                  <TableCell className="text-right font-mono">{fmt(r.subsequent_confirmed_amount)}</TableCell>
                  <TableCell className="text-right font-mono font-semibold">{fmt(r.total_received)}</TableCell>
                  <TableCell className="text-right font-mono font-semibold text-rose-700">{fmt(r.total_receivable)}</TableCell>
                  <TableCell className="text-right">
                    {canEdit && r.status === "ACTIVE" && <Button size="sm" data-testid={`add-payment-${r.ecp_id}`} onClick={() => openNew(r)}>+ Payment</Button>}
                  </TableCell>
                </TableRow>
              ))}
              {filtered.length === 0 && <TableRow><TableCell colSpan={9} className="text-center text-slate-400 py-10">No projects.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* New payment dialog */}
      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>Record Payment · {f.lead_name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Payment Type *</Label>
              <Select value={f.type} onValueChange={(v) => setF({ ...f, type: v })}>
                <SelectTrigger data-testid="payment-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{TYPE_OPTIONS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Amount *</Label><Input data-testid="payment-amount-input" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
            <div><Label>Date *</Label><Input data-testid="payment-date-input" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></div>
            <div><Label>Status *</Label>
              <Select value={f.status} onValueChange={(v) => setF({ ...f, status: v })}>
                <SelectTrigger data-testid="payment-status-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["PENDING", "CONFIRMED"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Remarks</Label><Textarea value={f.remarks || ""} onChange={(e) => setF({ ...f, remarks: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="payment-save" onClick={save} className="bg-sky-600 hover:bg-sky-700">Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Transaction detail dialog */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{detail?.lead_name} · Payment History</DialogTitle></DialogHeader>
          {detail && (
            <Table>
              <TableHeader className="bg-slate-50">
                <TableRow><TableHead>Type</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Date</TableHead><TableHead>Status</TableHead><TableHead>By</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {detail.payments.length === 0 && <TableRow><TableCell colSpan={5} className="text-slate-400 py-4 text-sm">No payments yet.</TableCell></TableRow>}
                {detail.payments.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-semibold">{p.type === "FIRST" ? "First" : "Subsequent"}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(p.amount)}</TableCell>
                    <TableCell>{p.date?.slice(0, 10)}</TableCell>
                    <TableCell><StatusBadge value={p.status} kind={p.status === "CONFIRMED" ? "CONFIRMED" : "PENDING"} label={p.status} /></TableCell>
                    <TableCell className="text-xs text-slate-500">{p.updated_by_name}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <div className="flex items-center justify-between pt-2">
            <button className="text-sm text-sky-600 underline" onClick={() => { const r = detail; setDetail(null); nav(`/ecps/${r.ecp_id}`); }}>Open ECP</button>
            {canEdit && detail?.status === "ACTIVE" && <Button size="sm" onClick={() => { openNew(detail); setDetail(null); }}>+ Payment</Button>}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
