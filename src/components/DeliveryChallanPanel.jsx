import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash2, FileCheck2 } from "lucide-react";
import { toast } from "sonner";

export function DeliveryChallanPanel({ ecpId, canEdit }) {
  const [ch, setCh] = useState(null);
  const [items, setItems] = useState([]);
  const [master, setMaster] = useState([]);

  const load = () => api.get(`/ecps/${ecpId}/challan`).then((r) => { setCh(r.data && r.data.ecp_id ? r.data : null); setItems((r.data && r.data.items) || []); }).catch(() => {});
  useEffect(() => { load(); if (canEdit) api.get("/items?active_only=true").then((r) => setMaster(r.data)).catch(() => {}); }, [ecpId]);

  const finalized = ch?.status === "FINALIZED";
  const addItem = () => setItems([...items, { item_id: "", item_name: "", unit: "", quantity: 1 }]);
  const setItem = (i, patch) => setItems(items.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));
  const pickMaster = (i, id) => { const m = master.find((x) => x.id === id); setItem(i, { item_id: id, item_name: m?.name || "", unit: m?.unit || "" }); };

  const save = async () => {
    try { await api.post(`/ecps/${ecpId}/challan`, { items: items.map((it) => ({ ...it, quantity: parseFloat(it.quantity) || 0 })) }); toast.success("Challan saved"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const finalize = async () => {
    try { await api.post(`/ecps/${ecpId}/challan/finalize`); toast.success("Challan finalized"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <Card className="p-5" data-testid="challan-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-head font-semibold">Delivery Challan</h3>
        <span className={`text-xs font-bold px-2 py-1 rounded-full ${finalized ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{finalized ? "FINALIZED" : ch ? "DRAFT" : "NOT CREATED"}</span>
      </div>
      <div className="space-y-2">
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-2" data-testid={`challan-item-${i}`}>
            {canEdit && !finalized ? (
              <Select value={it.item_id || ""} onValueChange={(v) => pickMaster(i, v)}>
                <SelectTrigger data-testid={`challan-item-select-${i}`} className="flex-1"><SelectValue placeholder="Select item" /></SelectTrigger>
                <SelectContent>{master.map((m) => <SelectItem key={m.id} value={m.id}>{m.name} ({m.unit})</SelectItem>)}</SelectContent>
              </Select>
            ) : <span className="flex-1 text-sm">{it.item_name} ({it.unit})</span>}
            {canEdit && !finalized ? (
              <Input type="number" className="w-24" data-testid={`challan-qty-${i}`} value={it.quantity} onChange={(e) => setItem(i, { quantity: e.target.value })} />
            ) : <span className="text-sm w-24">Qty: {it.quantity}</span>}
            {canEdit && !finalized && <Button size="icon" variant="ghost" onClick={() => setItems(items.filter((_, idx) => idx !== i))}><Trash2 size={15} /></Button>}
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-slate-400">No items.</p>}
      </div>
      {canEdit && !finalized && (
        <div className="flex gap-2 mt-3">
          <Button size="sm" variant="outline" data-testid="challan-add-item" onClick={addItem}><Plus size={14} className="mr-1" />Add Item</Button>
          <Button size="sm" data-testid="challan-save" className="bg-sky-600 hover:bg-sky-700" onClick={save}>Save Draft</Button>
          <Button size="sm" data-testid="challan-finalize" className="bg-emerald-600 hover:bg-emerald-700" onClick={finalize}><FileCheck2 size={14} className="mr-1" />Finalize</Button>
        </div>
      )}
    </Card>
  );
}
