import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/ui-bits";
import { ROLE_LABELS } from "@/lib/constants";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const ACTIVITIES = ["Lead Created", "Lead Action: YES", "Lead Action: NO", "Lead Action: FOLLOW_UP",
  "Lead Action: SITE_VISIT", "Lead Action: ESCALATION", "Site Visit Assigned", "Site Visit Completed",
  "Escalation Returned", "ECP Stage Advanced", "Installation Assigned", "Payment Created",
  "Payment Updated", "ECP Closed"];

const IST = "en-IN";

export default function WorkDone() {
  const [rows, setRows] = useState([]);
  const [users, setUsers] = useState([]);
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  const [date, setDate] = useState(today);
  const [au, setAu] = useState("ALL");
  const [team, setTeam] = useState("ALL");
  const [act, setAct] = useState("ALL");

  const load = () => {
    const p = new URLSearchParams({ date });
    if (au !== "ALL") p.set("activity_user", au);
    if (team !== "ALL") p.set("team", team);
    if (act !== "ALL") p.set("activity", act);
    api.get(`/activities?${p.toString()}`).then((r) => setRows(r.data));
  };
  useEffect(() => { api.get("/users").then((r) => setUsers(r.data)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [date, au, team, act]);

  const timeStr = (ts) => new Date(ts).toLocaleTimeString(IST, { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });

  return (
    <div>
      <PageHeader title="Today's Work Done" subtitle="Operational activity report (IST). Owner-only." />
      <div className="p-4 lg:p-8">
        <div className="flex flex-wrap gap-3 mb-4">
          <Input data-testid="wd-date" type="date" className="w-44" value={date} onChange={(e) => setDate(e.target.value)} />
          <Select value={au} onValueChange={setAu}><SelectTrigger data-testid="wd-user" className="w-44"><SelectValue placeholder="User" /></SelectTrigger>
            <SelectContent><SelectItem value="ALL">All Users</SelectItem>{users.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent></Select>
          <Select value={team} onValueChange={setTeam}><SelectTrigger data-testid="wd-team" className="w-44"><SelectValue placeholder="Team" /></SelectTrigger>
            <SelectContent><SelectItem value="ALL">All Teams</SelectItem>{Object.keys(ROLE_LABELS).map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>)}</SelectContent></Select>
          <Select value={act} onValueChange={setAct}><SelectTrigger data-testid="wd-activity" className="w-56"><SelectValue placeholder="Activity" /></SelectTrigger>
            <SelectContent><SelectItem value="ALL">All Activities</SelectItem>{ACTIVITIES.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}</SelectContent></Select>
          <span className="text-xs text-slate-400 font-mono self-center">{rows.length} activities</span>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow><TableHead>Time</TableHead><TableHead>User</TableHead><TableHead>Team</TableHead><TableHead>Customer</TableHead><TableHead>Activity</TableHead><TableHead>Details</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} data-testid={`activity-${r.id}`}>
                  <TableCell className="font-mono text-sm whitespace-nowrap">{timeStr(r.ts)}</TableCell>
                  <TableCell className="font-semibold">{r.user_name}</TableCell>
                  <TableCell className="text-sm">{ROLE_LABELS[r.team] || r.team}</TableCell>
                  <TableCell className="text-sm">{r.customer_name || "—"}</TableCell>
                  <TableCell className="text-sm">{r.activity}</TableCell>
                  <TableCell className="text-xs text-slate-500">{r.details}</TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-slate-400 py-10">No activity for this filter.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
