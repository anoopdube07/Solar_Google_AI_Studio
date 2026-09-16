import React, { useEffect, useState } from "react";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { ROLE_LABELS } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Plus, AlertTriangle, UserCheck, UserX, Loader2 } from "lucide-react";
import { toast } from "sonner";

const ROLES = [
  "OWNER",
  "MANAGER",
  "LEAD",
  "REGISTRATION",
  "ACCOUNTS",
  "DISPATCH",
  "INSTALLATION_MANAGER",
  "INSTALLATION_MEMBER",
  "COMPLAINT",
];

export default function Users() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [statusFilter, setStatusFilter] = useState("ACTIVE"); // Defaults to ACTIVE
  const [loading, setLoading] = useState(false);

  // User create/edit modal
  const [dlg, setDlg] = useState(false);
  const [edit, setEdit] = useState(null);
  const [f, setF] = useState({});

  // Direct deactivation confirmation (for user with 0 assignments)
  const [confirmDlg, setConfirmDlg] = useState(false);
  const [targetUser, setTargetUser] = useState(null);

  // Work-by-work reassignment dialog (for user with >0 assignments)
  const [reassignDlg, setReassignDlg] = useState(false);
  const [pendingWork, setPendingWork] = useState([]);
  const [reassignments, setReassignments] = useState({});
  const [submittingReassign, setSubmittingReassign] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .get("/users")
      .then((r) => setUsers(r.data))
      .catch((e) => toast.error(apiError(e.response?.data?.detail)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const openNew = () => {
    setEdit(null);
    setF({ username: "", password: "", name: "", role: "LEAD", phone: "" });
    setDlg(true);
  };

  const openEdit = (u) => {
    setEdit(u);
    setF({ name: u.name, role: u.role, phone: u.phone || "", password: "" });
    setDlg(true);
  };

  const save = async () => {
    try {
      if (edit) {
        await api.patch(`/users/${edit.id}`, {
          name: f.name,
          role: f.role,
          phone: f.phone,
          password: f.password || undefined,
        });
      } else {
        if (!f.phone || !f.phone.trim()) {
          toast.error("Phone number is required");
          return;
        }
        await api.post("/users", f);
      }
      toast.success("Saved");
      setDlg(false);
      load();
    } catch (e) {
      toast.error(apiError(e.response?.data?.detail));
    }
  };

  const handleToggleActive = async (u) => {
    if (u.id === currentUser?.id) {
      toast.error("You cannot deactivate your own account");
      return;
    }

    // Activating an inactive user
    if (!u.active) {
      try {
        await api.patch(`/users/${u.id}`, { active: true });
        toast.success(`User ${u.name} activated`);
        load();
      } catch (e) {
        toast.error(apiError(e.response?.data?.detail));
      }
      return;
    }

    // Deactivating an active user: query backend for active/pending assignments
    try {
      const res = await api.get(`/users/${u.id}/assignments`);
      const assignments = res.data.assignments || [];
      setTargetUser(u);

      if (assignments.length === 0) {
        // No pending assignments -> simple confirmation
        setConfirmDlg(true);
      } else {
        // Active work present -> work-by-work reassignment dialog
        setPendingWork(assignments);
        const initialMap = {};
        assignments.forEach((a) => {
          initialMap[a.id] = "";
        });
        setReassignments(initialMap);
        setReassignDlg(true);
      }
    } catch (e) {
      toast.error(apiError(e.response?.data?.detail));
    }
  };

  const confirmDirectDeactivate = async () => {
    if (!targetUser) return;
    try {
      await api.patch(`/users/${targetUser.id}`, { active: false });
      toast.success(`User ${targetUser.name} deactivated`);
      setConfirmDlg(false);
      setTargetUser(null);
      load();
    } catch (e) {
      toast.error(apiError(e.response?.data?.detail));
    }
  };

  const submitReassignmentAndDeactivate = async () => {
    if (!targetUser) return;

    // Verify that every assignment has an explicit replacement
    const missing = pendingWork.find((a) => !reassignments[a.id]);
    if (missing) {
      toast.error(`Please select a replacement user for: ${missing.type_label} - ${missing.record_title}`);
      return;
    }

    setSubmittingReassign(true);
    try {
      const payload = {
        reassignments: pendingWork.map((a) => ({
          id: a.id,
          type: a.type,
          record_id: a.record_id,
          new_user_id: reassignments[a.id],
        })),
      };
      await api.post(`/users/${targetUser.id}/reassign-and-deactivate`, payload);
      toast.success(
        `All ${pendingWork.length} assignments reassigned and ${targetUser.name} deactivated successfully.`
      );
      setReassignDlg(false);
      setTargetUser(null);
      setPendingWork([]);
      load();
    } catch (e) {
      toast.error(apiError(e.response?.data?.detail));
    } finally {
      setSubmittingReassign(false);
    }
  };

  // Filtered users according to status filter
  const activeCount = users.filter((u) => u.active).length;
  const inactiveCount = users.filter((u) => !u.active).length;
  const totalCount = users.length;

  const displayedUsers = users.filter((u) => {
    if (statusFilter === "ACTIVE") return u.active;
    if (statusFilter === "INACTIVE") return !u.active;
    return true;
  });

  const allReassigned =
    pendingWork.length > 0 &&
    pendingWork.every((a) => Boolean(reassignments[a.id]));

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="One user = one role = one team. Owner-managed."
        right={
          <Button
            data-testid="new-user-button"
            onClick={openNew}
            className="bg-sky-600 hover:bg-sky-700"
          >
            <Plus size={16} className="mr-1" /> New User
          </Button>
        }
      />

      <div className="p-6 lg:p-8 space-y-4">
        {/* Status Filter: Defaults to ACTIVE */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div
            className="flex items-center gap-2 bg-slate-100 p-1 rounded-lg border border-slate-200"
            data-testid="user-status-filter"
          >
            <button
              type="button"
              data-testid="filter-active"
              onClick={() => setStatusFilter("ACTIVE")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5 ${
                statusFilter === "ACTIVE"
                  ? "bg-white text-emerald-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <UserCheck size={14} />
              Active ({activeCount})
            </button>
            <button
              type="button"
              data-testid="filter-inactive"
              onClick={() => setStatusFilter("INACTIVE")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5 ${
                statusFilter === "INACTIVE"
                  ? "bg-white text-slate-800 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <UserX size={14} />
              Inactive ({inactiveCount})
            </button>
            <button
              type="button"
              data-testid="filter-all"
              onClick={() => setStatusFilter("ALL")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                statusFilter === "ALL"
                  ? "bg-white text-sky-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All ({totalCount})
            </button>
          </div>

          <div className="text-xs text-slate-500">
            Showing {displayedUsers.length} of {totalCount} users
          </div>
        </div>

        {/* Users Table */}
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Username</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Role / Team</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Active State</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayedUsers.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-center py-8 text-slate-500 text-sm"
                  >
                    No {statusFilter.toLowerCase()} users found.
                  </TableCell>
                </TableRow>
              ) : (
                displayedUsers.map((u) => (
                  <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                    <TableCell className="font-semibold text-slate-900">
                      {u.name}
                      {u.id === currentUser?.id && (
                        <span className="ml-2 text-xs font-normal text-sky-600 bg-sky-50 px-1.5 py-0.5 rounded border border-sky-200">
                          You
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-sm text-slate-600">
                      {u.username}
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">
                      {u.phone || "—"}
                    </TableCell>
                    <TableCell>
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                        {ROLE_LABELS[u.role] || u.role}
                      </span>
                    </TableCell>
                    <TableCell>
                      {u.active ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">
                          Inactive
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Switch
                          data-testid={`user-active-${u.id}`}
                          checked={u.active}
                          disabled={u.id === currentUser?.id}
                          onCheckedChange={() => handleToggleActive(u)}
                        />
                        <span className="text-xs text-slate-500">
                          {u.active ? "Active" : "Inactive"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        data-testid={`edit-user-${u.id}`}
                        onClick={() => openEdit(u)}
                      >
                        Edit
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* User Create / Edit Dialog */}
      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{edit ? "Edit User" : "Create User"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {!edit && (
              <div>
                <Label>Username *</Label>
                <Input
                  data-testid="user-username-input"
                  value={f.username || ""}
                  onChange={(e) => setF({ ...f, username: e.target.value })}
                />
              </div>
            )}
            <div>
              <Label>Name *</Label>
              <Input
                data-testid="user-name-input"
                value={f.name || ""}
                onChange={(e) => setF({ ...f, name: e.target.value })}
              />
            </div>
            <div>
              <Label>Phone Number *</Label>
              <Input
                data-testid="user-phone-input"
                value={f.phone || ""}
                onChange={(e) => setF({ ...f, phone: e.target.value })}
              />
            </div>
            <div>
              <Label>Role / Team *</Label>
              <Select
                value={f.role}
                onValueChange={(v) => setF({ ...f, role: v })}
              >
                <SelectTrigger data-testid="user-role-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(edit?.role === "INSTALLATION"
                    ? ["INSTALLATION", ...ROLES]
                    : ROLES
                  ).map((r) => (
                    <SelectItem key={r} value={r}>
                      {ROLE_LABELS[r]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Password {edit ? "(leave blank to keep)" : "*"}</Label>
              <Input
                data-testid="user-password-input"
                type="password"
                value={f.password || ""}
                onChange={(e) => setF({ ...f, password: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              data-testid="user-save"
              onClick={save}
              className="bg-sky-600 hover:bg-sky-700"
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog for user with NO active assignments */}
      <Dialog open={confirmDlg} onOpenChange={setConfirmDlg}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Deactivate User</DialogTitle>
            <DialogDescription>
              Are you sure you want to deactivate{" "}
              <strong className="text-slate-900">{targetUser?.name}</strong>?
            </DialogDescription>
          </DialogHeader>
          <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200 text-sm text-emerald-800 space-y-1">
            <p className="font-semibold">No active assignments found.</p>
            <p className="text-xs text-emerald-700">
              This user has no pending operational work. The user record and all
              past historical data, completed projects, and audit logs will
              remain preserved.
            </p>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => {
                setConfirmDlg(false);
                setTargetUser(null);
              }}
            >
              Cancel
            </Button>
            <Button
              data-testid="confirm-deactivate-btn"
              onClick={confirmDirectDeactivate}
              className="bg-rose-600 hover:bg-rose-700 text-white"
            >
              Deactivate User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Work-by-Work Reassignment Dialog (when user HAS active work) */}
      <Dialog open={reassignDlg} onOpenChange={setReassignDlg}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] flex flex-col p-6">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold text-slate-900">
              Reassign Work Before Inactivation
            </DialogTitle>
            <DialogDescription>
              All active/pending operational work must be individually reassigned
              before deactivating this user.
            </DialogDescription>
          </DialogHeader>

          {/* Context Banner */}
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-900 flex items-start gap-2.5 my-2">
            <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">
                {targetUser?.name} has {pendingWork.length} active assignment(s).
              </p>
              <p className="text-xs text-amber-800 leading-relaxed">
                The user record will be preserved for history and audits. Each
                active task or project below must be explicitly reassigned to an
                eligible active team member before inactivation can proceed.
              </p>
            </div>
          </div>

          {/* Assignments List */}
          <div className="flex-1 overflow-y-auto space-y-3 pr-1 my-2">
            {pendingWork.map((a, idx) => {
              const selectedValue = reassignments[a.id] || "";
              const hasEligible = a.eligible_users && a.eligible_users.length > 0;

              return (
                <div
                  key={a.id}
                  className="p-3.5 border border-slate-200 rounded-lg bg-white shadow-xs space-y-2.5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider bg-slate-100 text-slate-800 border border-slate-200">
                        {a.type_label}
                      </span>
                      <span className="font-semibold text-slate-900 text-sm">
                        {a.record_title}
                      </span>
                    </div>
                    <span className="text-xs font-medium px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">
                      Stage: {a.current_stage}
                    </span>
                  </div>

                  <div className="text-xs text-slate-500 font-mono">
                    {a.details}
                  </div>

                  <div className="pt-1">
                    <Label className="text-xs font-medium text-slate-700 block mb-1">
                      Replacement User (Eligible Active {a.required_role}): *
                    </Label>
                    {!hasEligible ? (
                      <div className="p-2 rounded bg-rose-50 border border-rose-200 text-xs text-rose-700 font-medium">
                        No active eligible {a.required_role} users available.
                        Please create or activate an eligible team member first.
                      </div>
                    ) : (
                      <Select
                        value={selectedValue}
                        onValueChange={(val) =>
                          setReassignments((prev) => ({
                            ...prev,
                            [a.id]: val,
                          }))
                        }
                      >
                        <SelectTrigger
                          data-testid={`replacement-select-${a.id}`}
                          className="w-full bg-white"
                        >
                          <SelectValue placeholder="Select replacement user..." />
                        </SelectTrigger>
                        <SelectContent>
                          {a.eligible_users.map((eu) => (
                            <SelectItem key={eu.id} value={eu.id}>
                              {eu.name} ({ROLE_LABELS[eu.role] || eu.role})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <DialogFooter className="border-t border-slate-200 pt-4 mt-2 gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => {
                setReassignDlg(false);
                setTargetUser(null);
                setPendingWork([]);
              }}
              disabled={submittingReassign}
            >
              Cancel
            </Button>
            <Button
              data-testid="submit-reassign-deactivate"
              onClick={submitReassignmentAndDeactivate}
              disabled={!allReassigned || submittingReassign}
              className="bg-sky-600 hover:bg-sky-700 text-white"
            >
              {submittingReassign && (
                <Loader2 size={16} className="animate-spin mr-1.5" />
              )}
              Reassign All &amp; Deactivate User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
