import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/ui-bits";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

export default function Escalations() {
  const nav = useNavigate();
  const [items, setItems] = useState([]);
  const [dlg, setDlg] = useState(null);
  const [remarks, setRemarks] = useState("");

  const load = () => api.get("/escalations").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const doReturn = async () => {
    try { await api.post(`/escalations/${dlg.id}/return`, { owner_remarks: remarks }); toast.success("Returned to Lead Team"); setDlg(null); setRemarks(""); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <PageHeader title="Escalations" subtitle="Lead escalations directed to the Owner" />
      <div className="p-6 lg:p-8 grid md:grid-cols-2 gap-4">
        {items.length === 0 && <div className="text-slate-400">No escalations.</div>}
        {items.map((e) => (
          <Card key={e.id} data-testid={`escalation-${e.id}`} className="p-5">
            <div className="flex items-center justify-between">
              <button className="font-semibold text-sky-700 hover:underline" onClick={() => nav(`/leads/${e.lead_id}`)}>{e.lead_name}</button>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${e.status === "OPEN" ? "bg-red-100 text-red-700 border-red-300" : "bg-emerald-100 text-emerald-700 border-emerald-300"}`}>{e.status}</span>
            </div>
            <div className="mt-3 text-sm"><b>Reason:</b> {e.reason}</div>
            <div className="text-sm text-slate-600 mt-1">{e.remarks}</div>
            <div className="text-xs text-slate-400 mt-1">By {e.created_by_name} · {e.created_at?.slice(0, 16).replace("T", " ")}</div>
            {e.owner_remarks && <div className="mt-2 text-sm bg-emerald-50 border border-emerald-200 rounded px-3 py-2">Owner: {e.owner_remarks}</div>}
            {e.status === "OPEN" && <Button className="mt-3 bg-sky-600 hover:bg-sky-700" data-testid={`return-escalation-${e.id}`} onClick={() => { setDlg(e); setRemarks(""); }}>Review & Return</Button>}
          </Card>
        ))}
      </div>

      <Dialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Return to Lead Team</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-600">Owner remarks are mandatory. The Lead Team makes the next decision (you cannot decide YES/NO/Follow-up/Site Visit on their behalf).</p>
          <div><Label>Owner Remarks *</Label><Textarea data-testid="owner-remarks-input" value={remarks} onChange={(e) => setRemarks(e.target.value)} /></div>
          <DialogFooter><Button data-testid="owner-return-submit" onClick={doReturn} className="bg-sky-600 hover:bg-sky-700">Return to Lead Team</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
