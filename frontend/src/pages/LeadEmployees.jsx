import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/ui-bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus } from "lucide-react";
import { toast } from "sonner";

export default function LeadEmployees() {
  const [emps, setEmps] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [edit, setEdit] = useState(null);
  const [name, setName] = useState("");

  const load = () => api.get("/lead-employees").then((r) => setEmps(r.data));
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!name.trim()) { toast.error("Name is required"); return; }
    try {
      if (edit) await api.patch(`/lead-employees/${edit.id}`, { name });
      else await api.post("/lead-employees", { name });
      toast.success("Saved"); setDlg(false); setName(""); setEdit(null); load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const toggle = async (emp) => {
    try { await api.patch(`/lead-employees/${emp.id}`, { active: !emp.active }); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <PageHeader title="Lead Employees" subtitle="Master list of Lead Team employees (Owner-managed)."
        right={<Button data-testid="new-lead-emp-button" onClick={() => { setEdit(null); setName(""); setDlg(true); }} className="bg-sky-600 hover:bg-sky-700"><Plus size={16} className="mr-1" /> Add Employee</Button>} />
      <div className="p-4 lg:p-8">
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <Table>
            <TableHeader className="bg-slate-50"><TableRow><TableHead>Name</TableHead><TableHead>Active</TableHead><TableHead></TableHead></TableRow></TableHeader>
            <TableBody>
              {emps.map((e) => (
                <TableRow key={e.id} data-testid={`lead-emp-${e.id}`}>
                  <TableCell className="font-semibold">{e.name}</TableCell>
                  <TableCell><Switch data-testid={`lead-emp-active-${e.id}`} checked={e.active} onCheckedChange={() => toggle(e)} /></TableCell>
                  <TableCell><Button size="sm" variant="outline" onClick={() => { setEdit(e); setName(e.name); setDlg(true); }}>Edit</Button></TableCell>
                </TableRow>
              ))}
              {emps.length === 0 && <TableRow><TableCell colSpan={3} className="text-center text-slate-400 py-10">No lead employees yet.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </div>
      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>{edit ? "Edit" : "Add"} Lead Employee</DialogTitle></DialogHeader>
          <div><Label>Name *</Label><Input data-testid="lead-emp-name-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <DialogFooter><Button data-testid="lead-emp-save" onClick={save} className="bg-sky-600 hover:bg-sky-700">Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
