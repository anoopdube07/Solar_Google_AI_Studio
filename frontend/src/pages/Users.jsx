import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/ui-bits";
import { ROLE_LABELS } from "@/lib/constants";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus } from "lucide-react";
import { toast } from "sonner";

const ROLES = ["OWNER", "MANAGER", "LEAD", "REGISTRATION", "ACCOUNTS", "DISPATCH", "INSTALLATION_MANAGER", "INSTALLATION_MEMBER", "COMPLAINT"];

export default function Users() {
  const [users, setUsers] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [edit, setEdit] = useState(null);
  const [f, setF] = useState({});

  const load = () => api.get("/users").then((r) => setUsers(r.data));
  useEffect(() => { load(); }, []);

  const openNew = () => { setEdit(null); setF({ username: "", password: "", name: "", role: "LEAD", phone: "" }); setDlg(true); };
  const openEdit = (u) => { setEdit(u); setF({ name: u.name, role: u.role, phone: u.phone || "", password: "" }); setDlg(true); };

  const save = async () => {
    try {
      if (edit) {
        await api.patch(`/users/${edit.id}`, { name: f.name, role: f.role, phone: f.phone, password: f.password || undefined });
      } else {
        if (!f.phone || !f.phone.trim()) { toast.error("Phone number is required"); return; }
        await api.post("/users", f);
      }
      toast.success("Saved"); setDlg(false); load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  const toggleActive = async (u) => {
    try { await api.patch(`/users/${u.id}`, { active: !u.active }); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <PageHeader title="Users" subtitle="One user = one role = one team. Owner-managed."
        right={<Button data-testid="new-user-button" onClick={openNew} className="bg-sky-600 hover:bg-sky-700"><Plus size={16} className="mr-1" /> New User</Button>} />
      <div className="p-6 lg:p-8">
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow><TableHead>Name</TableHead><TableHead>Username</TableHead><TableHead>Phone</TableHead><TableHead>Role / Team</TableHead><TableHead>Active</TableHead><TableHead></TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                  <TableCell className="font-semibold">{u.name}</TableCell>
                  <TableCell className="font-mono text-sm">{u.username}</TableCell>
                  <TableCell className="text-sm">{u.phone || "—"}</TableCell>
                  <TableCell>{ROLE_LABELS[u.role]}</TableCell>
                  <TableCell><Switch data-testid={`user-active-${u.id}`} checked={u.active} onCheckedChange={() => toggleActive(u)} /></TableCell>
                  <TableCell><Button size="sm" variant="outline" data-testid={`edit-user-${u.id}`} onClick={() => openEdit(u)}>Edit</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle>{edit ? "Edit User" : "Create User"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {!edit && <div><Label>Username *</Label><Input data-testid="user-username-input" value={f.username || ""} onChange={(e) => setF({ ...f, username: e.target.value })} /></div>}
            <div><Label>Name *</Label><Input data-testid="user-name-input" value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
            <div><Label>Phone Number *</Label><Input data-testid="user-phone-input" value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} /></div>
            <div><Label>Role / Team *</Label>
              <Select value={f.role} onValueChange={(v) => setF({ ...f, role: v })}>
                <SelectTrigger data-testid="user-role-select"><SelectValue /></SelectTrigger>
                <SelectContent>{(edit?.role === "INSTALLATION" ? ["INSTALLATION", ...ROLES] : ROLES).map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Password {edit ? "(leave blank to keep)" : "*"}</Label><Input data-testid="user-password-input" type="password" value={f.password || ""} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
          </div>
          <DialogFooter><Button data-testid="user-save" onClick={save} className="bg-sky-600 hover:bg-sky-700">Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
