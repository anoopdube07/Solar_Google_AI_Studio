import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/ui-bits";
import { StatusBadge, DelayedBadge } from "@/components/StatusBadge";
import { DERIVED_LABELS } from "@/lib/constants";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

// Filter options per role: [value, label, {stage|view}]
const FILTERS = {
  OWNER: [
    ["ALL", "All", {}],
    ["PENDING_DOCUMENTS", "Pending Documents", { stage: "PENDING_DOCUMENTS" }],
    ["REGISTRATION_1", "Registration 1", { stage: "REGISTRATION_1" }],
    ["ACCOUNTS_1", "Accounts 1", { stage: "ACCOUNTS_1" }],
    ["PAYMENT_BLOCKED", "Payment Blocked", { view: "PAYMENT_BLOCKED" }],
    ["READY_FOR_DISPATCH", "Ready for Dispatch", { view: "READY_FOR_DISPATCH" }],
    ["DISPATCH_IN_PROCESS", "Dispatch In Process", { view: "DISPATCH_IN_PROCESS" }],
    ["INSTALLATION", "Installation", { stage: "INSTALLATION" }],
    ["READY_TO_INSTALL", "Ready to Install", { view: "READY_TO_INSTALL" }],
    ["IN_PROCESS", "Installation In Process", { view: "IN_PROCESS" }],
    ["NET_METERING", "Net Metering", { stage: "NET_METERING" }],
    ["REGISTRATION_2", "Registration 2", { stage: "REGISTRATION_2" }],
    ["ACCOUNTS_2", "Accounts 2", { stage: "ACCOUNTS_2" }],
    ["COMPLETED", "Successfully Completed", { view: "COMPLETED" }],
    ["CLOSED", "Closed / Cancelled", { view: "CLOSED" }],
    ["DELAYED", "Delayed Projects", { view: "DELAYED" }],
  ],
  LEAD: [
    ["ALL", "All", {}],
    ["REGISTRATION_1", "Registration 1", { stage: "REGISTRATION_1" }],
    ["ACCOUNTS_1", "Accounts 1", { stage: "ACCOUNTS_1" }],
    ["DISPATCH", "Dispatch", { stage: "DISPATCH" }],
    ["INSTALLATION", "Installation", { stage: "INSTALLATION" }],
    ["NET_METERING", "Net Metering", { stage: "NET_METERING" }],
    ["REGISTRATION_2", "Registration 2", { stage: "REGISTRATION_2" }],
    ["ACCOUNTS_2", "Accounts 2", { stage: "ACCOUNTS_2" }],
    ["CLOSED", "Closed", { view: "CLOSED" }],
  ],
  MANAGER: [
    ["ALL", "All", {}],
    ["REGISTRATION_1", "Registration 1", { stage: "REGISTRATION_1" }],
    ["ACCOUNTS_1", "Accounts 1", { stage: "ACCOUNTS_1" }],
    ["DISPATCH", "Dispatch", { stage: "DISPATCH" }],
    ["AWAITING_ASSIGNMENT", "Awaiting Install Assignment", { view: "AWAITING_ASSIGNMENT" }],
    ["INSTALLATION", "Installation", { stage: "INSTALLATION" }],
    ["NET_METERING", "Net Metering", { stage: "NET_METERING" }],
    ["REGISTRATION_2", "Registration 2", { stage: "REGISTRATION_2" }],
    ["ACCOUNTS_2", "Accounts 2", { stage: "ACCOUNTS_2" }],
    ["CLOSED", "Closed", { view: "CLOSED" }],
  ],
  REGISTRATION: [
    ["ALL", "All", {}],
    ["REGISTRATION_1", "Registration 1", { stage: "REGISTRATION_1" }],
    ["REGISTRATION_2", "Registration 2", { stage: "REGISTRATION_2" }],
  ],
  DISPATCH: [
    ["ALL", "All", {}],
    ["PAYMENT_BLOCKED", "Payment Blocked", { view: "PAYMENT_BLOCKED" }],
    ["READY_FOR_DISPATCH", "Ready for Dispatch", { view: "READY_FOR_DISPATCH" }],
    ["DISPATCH_IN_PROCESS", "Dispatch In Process", { view: "DISPATCH_IN_PROCESS" }],
    ["PAST_DISPATCH", "Delivered / Past Dispatch", { view: "PAST_DISPATCH" }],
  ],
  INSTALLATION: [
    ["ALL", "All", {}],
    ["READY_TO_INSTALL", "Ready to Install", { view: "READY_TO_INSTALL" }],
    ["IN_PROCESS", "In Process", { view: "IN_PROCESS" }],
    ["NET_METERING", "Net Metering", { stage: "NET_METERING" }],
  ],
};

export default function ECPs() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const params = new URLSearchParams(loc.search);
  const stageParam = params.get("stage") || "";
  const viewParam = params.get("view") || "";
  const [ecps, setEcps] = useState([]);
  const [q, setQ] = useState("");

  const roleFilters = FILTERS[user.role];
  // derive current filter key from URL
  const currentKey =
    (roleFilters &&
      roleFilters.find((f) => f[2].stage === stageParam && stageParam) ) ? stageParam
    : (roleFilters && roleFilters.find((f) => f[2].view === viewParam && viewParam)) ? viewParam
    : "ALL";

  useEffect(() => {
    const qs = [];
    if (stageParam) qs.push(`stage=${stageParam}`);
    if (viewParam) qs.push(`view=${viewParam}`);
    const url = qs.length ? `/ecps?${qs.join("&")}` : "/ecps";
    api.get(url).then((r) => setEcps(r.data));
  }, [stageParam, viewParam]);

  const applyFilter = (key) => {
    const opt = roleFilters.find((f) => f[0] === key);
    if (!opt || key === "ALL") { nav("/ecps"); return; }
    const p = new URLSearchParams();
    if (opt[2].stage) p.set("stage", opt[2].stage);
    if (opt[2].view) p.set("view", opt[2].view);
    nav(`/ecps?${p.toString()}`);
  };

  const filtered = ecps.filter((e) => !q || e.lead_name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div>
      <PageHeader title="ECP Projects" subtitle="Execution workflow tracking" />
      <div className="p-6 lg:p-8">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-sm min-w-[220px]">
            <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
            <Input data-testid="ecp-search" className="pl-9" placeholder="Search customer…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {roleFilters && (
            <Select value={currentKey} onValueChange={applyFilter}>
              <SelectTrigger data-testid="ecp-filter-select" className="w-56"><SelectValue /></SelectTrigger>
              <SelectContent>
                {roleFilters.map(([val, label]) => (
                  <SelectItem key={val} value={val} data-testid={`ecp-filter-${val}`}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <span className="text-xs text-slate-400 font-mono">{filtered.length} project(s)</span>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead>Customer</TableHead><TableHead>Stage</TableHead><TableHead>Status</TableHead>
                <TableHead>Current Team / Person</TableHead><TableHead>Days in Stage</TableHead><TableHead>Flags</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((e) => (
                <TableRow key={e.id} data-testid={`ecp-row-${e.id}`} className="hover:bg-slate-50 cursor-pointer" onClick={() => nav(`/ecps/${e.id}`)}>
                  <TableCell className="font-semibold text-slate-900">{e.lead_name}</TableCell>
                  <TableCell><StatusBadge value={e.current_stage} /></TableCell>
                  <TableCell>
                    {e.derived_status ? <StatusBadge value={e.derived_status} label={DERIVED_LABELS[e.derived_status]} /> :
                      <StatusBadge value={e.status} />}
                  </TableCell>
                  <TableCell className="text-sm">{e.current_team || "—"}{e.responsible_user_name ? ` · ${e.responsible_user_name}` : ""}</TableCell>
                  <TableCell className="text-sm font-mono">{e.days_in_stage ?? "—"}</TableCell>
                  <TableCell className="space-x-1">
                    {e.delayed && <DelayedBadge />}
                    {!e.first_payment_confirmed && e.status === "ACTIVE" && <span className="text-[10px] text-rose-600 font-semibold">FIRST PAY ✗</span>}
                  </TableCell>
                </TableRow>
              ))}
              {filtered.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-slate-400 py-10">No ECP projects match this filter.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
