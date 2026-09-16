import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/ui-bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Download, Upload, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function ItemMaster() {
  const [items, setItems] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [editing, setEditing] = useState(null);
  const [f, setF] = useState({ name: "", unit: "" });
  const [delItem, setDelItem] = useState(null);

  const load = () => api.get("/items").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);

  const openNew = () => { setEditing(null); setF({ name: "", unit: "" }); setDlg(true); };
  const openEdit = (it) => { setEditing(it); setF({ name: it.name, unit: it.unit }); setDlg(true); };

  const save = async () => {
    try {
      if (editing) { await api.patch(`/items/${editing.id}`, f); toast.success("Item updated"); }
      else { await api.post("/items", f); toast.success("Item added"); }
      setDlg(false); setEditing(null); setF({ name: "", unit: "" }); load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const toggle = async (it) => {
    try { await api.patch(`/items/${it.id}`, { active: !it.active }); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const doDelete = async () => {
    try { await api.delete(`/items/${delItem.id}`); toast.success("Item deleted"); setDelItem(null); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); setDelItem(null); }
  };

  const exportCsv = async () => {
    const res = await api.get("/items/export", { responseType: "blob" });
    const url = window.URL.createObjectURL(new Blob([res.data])); const a = document.createElement("a");
    a.href = url; a.download = "items.csv"; a.click(); window.URL.revokeObjectURL(url);
  };
  const importCsv = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const text = await file.text();
    const lines = text.split(/\r?\n/).filter((l) => l.trim());
    const rows = lines.slice(1).map((l) => { const [name, unit] = l.split(","); return { name: (name || "").trim(), unit: (unit || "").trim() }; });
    try { const r = await api.post("/items/import", { rows }); toast.success(`Imported ${r.data.created}. ${r.data.errors.length} skipped.`); if (r.data.errors.length) console.log(r.data.errors); load(); }
    catch (er) { toast.error(apiError(er.response?.data?.detail)); }
    e.target.value = "";
  };

  return (
    <div>
      <PageHeader title="Item Master" subtitle="Owner-managed products. Duplicate key = Name + Unit. Items used in records can be deactivated but not deleted."
        right={<div className="flex gap-2">
          <Button data-testid="item-export-btn" variant="secondary" onClick={exportCsv}><Download size={16} className="mr-1" /> CSV</Button>
          <label className="inline-flex items-center px-3 py-2 rounded-md bg-white/10 text-white text-sm cursor-pointer"><Upload size={16} className="mr-1" /> Import<input type="file" accept=".csv" className="hidden" data-testid="item-import-input" onChange={importCsv} /></label>
          <Button data-testid="new-item-btn" className="bg-sky-600 hover:bg-sky-700" onClick={openNew}><Plus size={16} className="mr-1" /> New Item</Button>
        </div>} />
      <div className="p-4 lg:p-8">
        <div className="bg-white rounded-lg border overflow-x-auto">
          <Table>
            <TableHeader className="bg-slate-50"><TableRow>
              <TableHead>Item Name</TableHead><TableHead>Unit</TableHead><TableHead>Status</TableHead>
              <TableHead>Active</TableHead><TableHead className="text-right">Actions</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {items.map((it) => (
                <TableRow key={it.id} data-testid={`item-row-${it.id}`}>
                  <TableCell className="font-semibold">{it.name}</TableCell>
                  <TableCell>{it.unit}</TableCell>
                  <TableCell>
                    <span data-testid={`item-status-${it.id}`} className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${it.active ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>
                      {it.active ? "ACTIVE" : "INACTIVE"}
                    </span>
                    {!it.deletable && <span className="ml-2 text-[10px] font-mono uppercase text-amber-600" title="Referenced by existing records">In use</span>}
                  </TableCell>
                  <TableCell><Switch data-testid={`item-active-${it.id}`} checked={it.active} onCheckedChange={() => toggle(it)} /></TableCell>
                  <TableCell className="text-right">
                    <Button data-testid={`item-edit-${it.id}`} size="sm" variant="ghost" onClick={() => openEdit(it)}><Pencil size={15} /></Button>
                    <Button data-testid={`item-delete-${it.id}`} size="sm" variant="ghost" disabled={!it.deletable}
                      title={it.deletable ? "Delete item" : "Used in records — deactivate instead"}
                      className={it.deletable ? "text-red-600 hover:text-red-700" : "text-slate-300"}
                      onClick={() => setDelItem(it)}><Trash2 size={15} /></Button>
                  </TableCell>
                </TableRow>
              ))}
              {items.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-slate-400 py-8">No items.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing ? "Edit Item" : "New Item"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Item Name *</Label><Input data-testid="item-name-input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
            <div><Label>Unit *</Label><Input data-testid="item-unit-input" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="item-save" onClick={save} className="bg-sky-600 hover:bg-sky-700">Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!delItem} onOpenChange={(o) => !o && setDelItem(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Item</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-600">Permanently delete <b>{delItem?.name} ({delItem?.unit})</b>? This cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDelItem(null)}>Cancel</Button>
            <Button data-testid="item-delete-confirm" className="bg-red-600 hover:bg-red-700 text-white" onClick={doDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
