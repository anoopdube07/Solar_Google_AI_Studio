import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, StatCard } from "@/components/ui-bits";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import {
  Download, CalendarDays, AlertTriangle, Ban, Clock, Users2, Building2, Target, CreditCard,
  Trophy, FileText, Truck, Wrench, CheckCircle2, ShieldAlert, IndianRupee, Plus, Check,
} from "lucide-react";

/* ---------- Owner helper components ---------- */

function KpiCard({ icon: Icon, value, label, iconCls, testid, onClick }) {
  return (
    <button data-testid={testid} onClick={onClick}
      className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3.5 text-left transition-all hover:shadow-md hover:-translate-y-0.5 hover:border-slate-300">
      <div className={`shrink-0 h-10 w-10 rounded-lg grid place-items-center ${iconCls}`}><Icon size={20} /></div>
      <div className="min-w-0">
        <div className="text-2xl font-black font-head text-slate-900 leading-none">{value ?? 0}</div>
        <div className="text-[11px] text-slate-500 font-medium mt-1 truncate">{label}</div>
      </div>
    </button>
  );
}

function AlertTile({ icon: Icon, value, label, tone, testid, onClick }) {
  const tones = {
    red: "bg-red-50 border-red-100 text-red-600",
    amber: "bg-amber-50 border-amber-100 text-amber-600",
    indigo: "bg-indigo-50 border-indigo-100 text-indigo-600",
  };
  return (
    <button data-testid={testid} onClick={onClick}
      className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all hover:shadow-sm ${tones[tone]}`}>
      <Icon size={22} className="shrink-0" />
      <div>
        <div className="text-2xl font-black font-head text-slate-900 leading-none">{value ?? 0}</div>
        <div className="text-[11px] font-semibold text-slate-600 mt-1">{label}</div>
      </div>
    </button>
  );
}

function EcpColumn({ title, icon: Icon, headerCls, rows }) {
  return (
    <div className="rounded-lg border border-slate-100 overflow-hidden bg-white">
      <div className={`flex items-center gap-2 px-3 py-2 ${headerCls}`}>
        <Icon size={15} />
        <span className="font-head font-bold text-xs uppercase tracking-wide">{title}</span>
      </div>
      <div className="divide-y divide-slate-50">
        {rows.map(([value, label, onClick, testid]) => (
          <button key={label} data-testid={testid} onClick={onClick}
            className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-slate-50 transition-colors">
            <span className="text-lg font-black font-head text-slate-900 w-9 shrink-0">{value ?? 0}</span>
            <span className="text-xs text-slate-600 leading-tight">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function PayCard({ icon: Icon, value, label, iconCls, testid, onClick }) {
  return (
    <button data-testid={testid} onClick={onClick}
      className="rounded-xl border border-slate-200 bg-white p-4 text-left transition-all hover:shadow-md hover:-translate-y-0.5">
      <div className={`h-9 w-9 rounded-lg grid place-items-center mb-3 ${iconCls}`}><Icon size={18} /></div>
      <div className="text-2xl font-black font-head text-slate-900 leading-none">{value ?? 0}</div>
      <div className="text-[11px] text-slate-500 font-medium mt-1.5">{label}</div>
    </button>
  );
}

const CHEVRON_MID = "polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%, 14px 50%)";
const CHEVRON_FIRST = "polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%)";

function activityDot(a) {
  const t = (a.activity || "").toLowerCase();
  if (t.includes("payment")) return "bg-emerald-500";
  if (t.includes("complaint") || t.includes("escalat") || t.includes("reject")) return "bg-red-500";
  if (t.includes("commercial")) return "bg-amber-500";
  if (t.includes("install") || t.includes("stage")) return "bg-indigo-500";
  if (t.includes("lead")) return "bg-sky-500";
  return "bg-slate-400";
}

function fmtActivityTs(ts) {
  try {
    return new Date(ts).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).replace(",", ",");
  } catch { return ""; }
}

function OwnerCommandCenter({ d, go, onReviewCommercial, pendingCommCount, activities, trend }) {
  const ecp = d.ecp || {};
  const leads = d.leads || {};
  const pay = d.payments || {};

  const kpis = [
    { icon: Building2, value: ecp.ACTIVE, label: "Active ECP Projects", iconCls: "bg-sky-50 text-sky-600", route: "/ecps" },
    { icon: Users2, value: leads.PENDING, label: "Pending Leads", iconCls: "bg-amber-50 text-amber-600", route: "/leads?status=PENDING" },
    { icon: Target, value: leads.QUALIFIED, label: "Qualified Leads", iconCls: "bg-emerald-50 text-emerald-600", route: "/leads?status=QUALIFIED" },
    { icon: CreditCard, value: ecp.PAYMENT_BLOCKED, label: "Payment Blocked", iconCls: "bg-red-50 text-red-600", route: "/ecps?view=PAYMENT_BLOCKED" },
    { icon: Clock, value: ecp.DELAYED, label: "Delayed Projects", iconCls: "bg-orange-50 text-orange-600", route: "/ecps?view=DELAYED" },
    { icon: Trophy, value: ecp.COMPLETED, label: "Successfully Completed", iconCls: "bg-emerald-50 text-emerald-600", route: "/ecps?view=COMPLETED" },
  ];

  const pipe = [
    { label: "Pending", v: leads.PENDING, tint: "bg-slate-100", num: "text-slate-800", route: "/leads?status=PENDING" },
    { label: "Follow-up", v: leads.FOLLOW_UP, tint: "bg-sky-100", num: "text-sky-700", route: "/leads?status=FOLLOW_UP" },
    { label: "Site Visit", v: leads.SITE_VISIT, tint: "bg-teal-100", num: "text-teal-700", route: "/leads?status=SITE_VISIT" },
    { label: "Escalated", v: leads.ESCALATED, tint: "bg-amber-100", num: "text-amber-700", route: "/leads?status=ESCALATED" },
    { label: "Qualified", v: leads.QUALIFIED, tint: "bg-emerald-100", num: "text-emerald-700", route: "/leads?status=QUALIFIED" },
  ];

  return (
    <div className="space-y-5" data-testid="owner-command-center">
      {/* REQUIRES YOUR ATTENTION */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <button data-testid="attn-commercial" onClick={onReviewCommercial}
          className="lg:col-span-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-5 py-3.5 text-left transition-all hover:shadow-md">
          <div className="shrink-0 h-9 w-9 rounded-full bg-red-100 text-red-600 grid place-items-center"><AlertTriangle size={18} /></div>
          <div>
            <div className="font-head font-bold text-red-700 text-sm">Requires Your Attention</div>
            <div className="text-xs text-slate-600 mt-0.5">
              {pendingCommCount > 0
                ? `${pendingCommCount} commercial change${pendingCommCount > 1 ? "s are" : " is"} awaiting your approval. Please review at the earliest.`
                : "No commercial changes are awaiting approval right now."}
            </div>
          </div>
        </button>
        <div className="lg:col-span-2"><AlertTile testid="attn-payment-blocked" icon={AlertTriangle} tone="red" value={ecp.PAYMENT_BLOCKED} label="Payment Blocked" onClick={go("/ecps?view=PAYMENT_BLOCKED")} /></div>
        <div className="lg:col-span-2"><AlertTile testid="attn-delayed" icon={Clock} tone="amber" value={ecp.DELAYED} label="Delayed Projects" onClick={go("/ecps?view=DELAYED")} /></div>
        <div className="lg:col-span-2"><AlertTile testid="attn-escalated" icon={Users2} tone="indigo" value={leads.ESCALATED} label="Escalated Leads" onClick={go("/leads?status=ESCALATED")} /></div>
      </div>

      {/* BUSINESS SNAPSHOT */}
      <div>
        <h2 className="font-head text-lg font-bold text-slate-800 mb-3">Business Snapshot</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {kpis.map((k) => (
            <KpiCard key={k.label} icon={k.icon} value={k.value} label={k.label} iconCls={k.iconCls}
              onClick={go(k.route)} testid={`kpi-${k.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} />
          ))}
        </div>
      </div>

      {/* LEAD PIPELINE + LEADS TREND */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-5 rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="font-head text-base font-bold text-slate-800 mb-3">Lead Pipeline</h3>
          <div className="flex items-stretch">
            {pipe.map((s, i) => (
              <button key={s.label} data-testid={`pipeline-${s.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} onClick={go(s.route)}
                style={{ clipPath: i === 0 ? CHEVRON_FIRST : CHEVRON_MID, marginLeft: i === 0 ? 0 : "-10px" }}
                className={`relative flex-1 h-[74px] flex flex-col items-center justify-center transition-opacity hover:opacity-80 ${s.tint}`}>
                <span className={`text-xl font-black font-head leading-none ${s.num}`}>{s.v ?? 0}</span>
                <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mt-1">{s.label}</span>
              </button>
            ))}
            <div className="w-3" />
            <button data-testid="pipeline-lost" onClick={go("/leads?status=LOST")}
              className="w-[76px] h-[74px] rounded-lg bg-slate-50 border border-slate-200 flex flex-col items-center justify-center hover:border-slate-400 transition-colors">
              <span className="text-xl font-black font-head text-slate-500 leading-none">{leads.LOST ?? 0}</span>
              <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mt-1">Lost</span>
            </button>
          </div>
        </div>

        <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-head text-base font-bold text-slate-800">Leads Trend <span className="text-xs font-normal text-slate-400">(Last 6 Months)</span></h3>
            <div className="flex items-center gap-4 text-[11px] text-slate-500">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-sky-500" /> New Leads</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" /> Qualified Leads</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={trend} margin={{ top: 5, right: 10, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f7" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#94a3b8" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#94a3b8" }} width={34} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
              <Line type="monotone" dataKey="New" name="New Leads" stroke="#0ea5e9" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Qualified" name="Qualified Leads" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ECP PROJECT STATUS */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="font-head text-lg font-bold text-slate-800 mb-3">ECP Project Status</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <EcpColumn title="Registration" icon={FileText} headerCls="bg-blue-50 text-blue-700" rows={[
            [ecp.PENDING_DOCUMENTS, "Pending Documents", go("/ecps?stage=PENDING_DOCUMENTS"), "ecp-pending-documents"],
            [ecp.REGISTRATION_1, "Registration 1", go("/ecps?stage=REGISTRATION_1"), "ecp-registration-1"],
            [ecp.ACCOUNTS_1, "Accounts 1", go("/ecps?stage=ACCOUNTS_1"), "ecp-accounts-1"],
          ]} />
          <EcpColumn title="Dispatch" icon={Truck} headerCls="bg-amber-50 text-amber-700" rows={[
            [ecp.PAYMENT_BLOCKED, "Payment Blocked", go("/ecps?view=PAYMENT_BLOCKED"), "ecp-payment-blocked"],
            [ecp.READY_FOR_DISPATCH, "Ready for Dispatch", go("/ecps?view=READY_FOR_DISPATCH"), "ecp-ready-for-dispatch"],
            [ecp.DISPATCH_IN_PROCESS, "Dispatch In Process", go("/ecps?view=DISPATCH_IN_PROCESS"), "ecp-dispatch-in-process"],
          ]} />
          <EcpColumn title="Installation" icon={Wrench} headerCls="bg-teal-50 text-teal-700" rows={[
            [ecp.READY_TO_INSTALL, "Ready to Install", go("/ecps?view=READY_TO_INSTALL"), "ecp-ready-to-install"],
            [ecp.INSTALLATION_IN_PROCESS, "Installation In Process", go("/ecps?view=IN_PROCESS"), "ecp-installation-in-process"],
            [ecp.NET_METERING, "Net Metering", go("/ecps?stage=NET_METERING"), "ecp-net-metering"],
          ]} />
          <EcpColumn title="Completion" icon={CheckCircle2} headerCls="bg-indigo-50 text-indigo-700" rows={[
            [ecp.REGISTRATION_2, "Registration 2", go("/ecps?stage=REGISTRATION_2"), "ecp-registration-2"],
            [ecp.ACCOUNTS_2, "Accounts 2", go("/ecps?stage=ACCOUNTS_2"), "ecp-accounts-2"],
            [ecp.COMPLETED, "Successfully Completed", go("/ecps?view=COMPLETED"), "ecp-completed"],
            [ecp.CLOSED, "Closed / Cancelled", go("/ecps?view=CLOSED"), "ecp-closed"],
          ]} />
          <EcpColumn title="Attention" icon={ShieldAlert} headerCls="bg-red-50 text-red-700" rows={[
            [ecp.DELAYED, "Delayed Projects", go("/ecps?view=DELAYED"), "ecp-delayed"],
          ]} />
        </div>
      </div>

      {/* PAYMENTS OVERVIEW + RECENT ACTIVITY */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7">
          <div className="flex items-center gap-2 mb-3">
            <IndianRupee size={18} className="text-emerald-600" />
            <h2 className="font-head text-lg font-bold text-slate-800">Payments Overview</h2>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <PayCard testid="pay-first-pending" icon={IndianRupee} iconCls="bg-amber-50 text-amber-600" value={pay.FIRST_PENDING} label="First Pending" onClick={go("/payments")} />
            <PayCard testid="pay-first-confirmed" icon={Check} iconCls="bg-sky-50 text-sky-600" value={pay.FIRST_CONFIRMED} label="First Confirmed" onClick={go("/payments")} />
            <PayCard testid="pay-subsequent" icon={Plus} iconCls="bg-indigo-50 text-indigo-600" value={pay.ADDITIONAL} label="Subsequent" onClick={go("/payments")} />
          </div>
        </div>

        <div className="lg:col-span-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-head text-lg font-bold text-slate-800">Recent Activity</h2>
            <button data-testid="activity-view-all" onClick={go("/work-done")} className="text-xs font-semibold text-sky-600 hover:text-sky-700">View All</button>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            {activities.length === 0 ? (
              <div className="text-sm text-slate-400 py-6 text-center">No activity recorded today.</div>
            ) : (
              <div className="space-y-3">
                {activities.slice(0, 6).map((a, i) => (
                  <div key={i} data-testid={`activity-row-${i}`} className="flex items-start gap-3">
                    <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${activityDot(a)}`} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm text-slate-700 truncate">{a.activity}{a.customer_name ? ` - ${a.customer_name}` : ""}</div>
                    </div>
                    <div className="text-[11px] text-slate-400 shrink-0 whitespace-nowrap">{fmtActivityTs(a.ts)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* FOOTER */}
      <div className="flex items-center justify-between pt-2 pb-1 text-xs text-slate-400">
        <div className="flex items-center gap-2 text-slate-500"><span className="text-emerald-500">❖</span> Cleaner Energy. Brighter Tomorrow.</div>
        <div className="hidden sm:block">Tracking Progress • Empowering Growth • A Sustainable Future</div>
      </div>
    </div>
  );
}

/* ---------- Dashboard ---------- */

export default function Dashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const [pendingComm, setPendingComm] = useState([]);
  const [activities, setActivities] = useState([]);
  const [leadsRaw, setLeadsRaw] = useState([]);
  const [exportDlg, setExportDlg] = useState(false);
  const [inclMoney, setInclMoney] = useState(false);
  const [now] = useState(() => new Date());

  const isOwner = user.role === "OWNER";

  useEffect(() => { api.get("/dashboard").then((r) => setD(r.data)); }, []);
  useEffect(() => {
    if (!isOwner) return;
    api.get("/commercial-changes/pending").then((r) => setPendingComm(r.data)).catch(() => {});
    api.get("/activities").then((r) => setActivities(r.data)).catch(() => {});
    api.get("/leads").then((r) => setLeadsRaw(r.data)).catch(() => {});
  }, [isOwner]);

  const trend = useMemo(() => {
    const buckets = [];
    const base = new Date(now.getFullYear(), now.getMonth(), 1);
    for (let i = 5; i >= 0; i--) {
      const dt = new Date(base.getFullYear(), base.getMonth() - i, 1);
      buckets.push({ key: `${dt.getFullYear()}-${dt.getMonth()}`, label: dt.toLocaleString("en-US", { month: "short" }), New: 0, Qualified: 0 });
    }
    const idx = Object.fromEntries(buckets.map((b, i) => [b.key, i]));
    leadsRaw.forEach((l) => {
      if (!l.created_at) return;
      const dt = new Date(l.created_at);
      const key = `${dt.getFullYear()}-${dt.getMonth()}`;
      if (key in idx) {
        buckets[idx[key]].New += 1;
        if (l.status === "QUALIFIED") buckets[idx[key]].Qualified += 1;
      }
    });
    return buckets;
  }, [leadsRaw, now]);

  if (!d) return <div className="p-8 text-slate-500">Loading…</div>;

  const go = (path) => () => nav(path);
  const reviewCommercial = () => { if (pendingComm.length) nav(`/leads/${pendingComm[0].id}`); };

  const downloadCsv = async () => {
    try {
      const res = await api.get(`/export/projects?include_money=${inclMoney}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = "projects.csv"; a.click();
      window.URL.revokeObjectURL(url);
      setExportDlg(false);
    } catch (e) { /* owner-only enforced server-side */ }
  };

  const exportDialog = (triggerCls) => (
    <Dialog open={exportDlg} onOpenChange={setExportDlg}>
      <DialogTrigger asChild><Button data-testid="export-csv-button" className={triggerCls}><Download size={16} className="mr-1.5" /> Export CSV</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Export Customer & Project Status</DialogTitle></DialogHeader>
        <div className="flex items-center gap-2 py-2">
          <Checkbox id="money" data-testid="export-money-checkbox" checked={inclMoney} onCheckedChange={(v) => setInclMoney(!!v)} />
          <Label htmlFor="money">Also Include Monetary Values</Label>
        </div>
        <DialogFooter><Button data-testid="export-download-button" onClick={downloadCsv} className="bg-sky-600 hover:bg-sky-700">Download CSV</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );

  if (isOwner) {
    const dateStr = now.toLocaleDateString("en-GB", { weekday: "long", day: "2-digit", month: "short", year: "numeric" });
    const timeStr = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    const initials = (user.name || "").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
    return (
      <div className="min-h-screen bg-slate-50">
        <div className="bg-white border-b border-slate-200 px-6 lg:px-8 py-4 flex items-center justify-between gap-4">
          <div>
            <h1 className="font-head text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Owner Command Center</h1>
            <p className="text-slate-500 text-sm mt-0.5">Business overview • Operations • Attention required</p>
          </div>
          <div className="flex items-center gap-4 lg:gap-5">
            <div className="hidden md:flex items-center gap-2 text-slate-500">
              <CalendarDays size={16} />
              <div className="leading-tight"><div className="text-xs font-semibold text-slate-700">{dateStr}</div><div className="text-[11px]">{timeStr}</div></div>
            </div>
            {exportDialog("border border-sky-200 bg-white text-sky-700 hover:bg-sky-50")}
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-full bg-indigo-600 text-white grid place-items-center text-sm font-bold">{initials || "OW"}</div>
              <div className="hidden sm:block leading-tight"><div className="text-sm font-semibold text-slate-800">{user.name}</div><div className="text-[11px] text-slate-500">Owner</div></div>
            </div>
          </div>
        </div>
        <div className="px-6 lg:px-8 py-6">
          <OwnerCommandCenter d={d} go={go} onReviewCommercial={reviewCommercial}
            pendingCommCount={pendingComm.length} activities={activities} trend={trend} />
        </div>
      </div>
    );
  }

  // ---- Non-owner role sections (unchanged) ----
  const sections = [];
  if (user.role === "MANAGER") {
    sections.push(["Operations", [
      ["Site Visits To Assign", d.site_visits_to_assign, "amber", go("/site-visits?status=REQUESTED")],
      ["Today's Site Visits", d.site_visits_today, "sky", go("/site-visits?status=ASSIGNED")],
      ["Upcoming Site Visits", d.site_visits_upcoming, "indigo", go("/site-visits?status=ASSIGNED")],
      ["Awaiting Install Assignment", d.awaiting_install_assignment, "amber", go("/ecps?view=AWAITING_ASSIGNMENT")],
      ["Delayed Projects", d.delayed, "red", go("/ecps")],
      ["Active Leads", d.active_leads, "slate", go("/leads")],
      ["Active ECPs", d.active_ecps, "sky", go("/ecps")],
    ]]);
  } else if (user.role === "LEAD") {
    sections.push(["My Lead Queue", [
      ["Action Required", d.action_required, "amber", go("/leads?status=PENDING")],
      ["Follow-ups Today", d.followups_today, "sky", go("/leads?followup=today")],
      ["Waiting for Site Visit", d.waiting_site_visit, "indigo", go("/leads?status=SITE_VISIT")],
      ["Escalated", d.escalated, "red", go("/leads?status=ESCALATED")],
      ["Qualified", d.qualified, "emerald", go("/leads?status=QUALIFIED")],
      ["Awaiting Documents", d.pending_documents, "amber", go("/leads?status=QUALIFIED")],
      ["Lost", d.lost, "slate", go("/leads?status=LOST")],
    ]]);
  } else if (user.role === "ACCOUNTS") {
    const fmt = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");
    sections.push(["Receivables", [
      ["First Payment Pending", `${d.first_payment_pending_count} Projects`, "amber", go("/payments?view=first_pending")],
      ["Total Receivable", fmt(d.total_receivable), "red", go("/payments?view=receivable")],
    ]]);
  } else if (user.role === "DISPATCH") {
    sections.push(["Dispatch Hub", [
      ["Payment Blocked", d.payment_blocked, "red", go("/ecps?view=PAYMENT_BLOCKED")],
      ["Ready for Dispatch", d.ready_for_dispatch, "teal", go("/ecps?view=READY_FOR_DISPATCH")],
      ["Dispatch In Process", d.dispatch_in_process, "indigo", go("/ecps?view=DISPATCH_IN_PROCESS")],
      ["Delivered / Past Dispatch", d.completed, "emerald", go("/ecps?view=PAST_DISPATCH")],
    ]]);
  } else if (user.role === "INSTALLATION") {
    sections.push(["Lead Site Visits", [
      ["Upcoming", d.sv_upcoming, "indigo", go("/site-visits")],
      ["Today", d.sv_today, "sky", go("/site-visits")],
      ["Assigned to Me", d.sv_assigned, "amber", go("/site-visits")],
      ["Completed", d.sv_completed, "emerald", go("/site-visits")],
    ]]);
    sections.push(["ECP Installation", [
      ["Ready to Install", d.ready_to_install, "teal", go("/ecps?view=READY_TO_INSTALL")],
      ["In Process", d.installation_in_process, "indigo", go("/ecps?view=IN_PROCESS")],
      ["Net Metering", d.net_metering, "slate", go("/ecps?stage=NET_METERING")],
    ]]);
  } else if (user.role === "REGISTRATION") {
    sections.push(["Registration", [
      ["Awaiting Documents", d.pending_documents, "amber", () => {}],
      ["Registration 1", d.registration_1, "sky", go("/ecps?stage=REGISTRATION_1")],
      ["Registration 2", d.registration_2, "sky", go("/ecps?stage=REGISTRATION_2")],
      ["Pending Total", d.pending, "amber", go("/ecps")],
    ]]);
  } else if (user.role === "INSTALLATION_MANAGER") {
    sections.push(["Installation Supervision", [
      ["Awaiting Assignment", d.awaiting_assignment, "amber", go("/ecps?view=READY_TO_INSTALL")],
      ["In Process", d.install_in_process, "indigo", go("/ecps?view=IN_PROCESS")],
      ["Pending Acceptance", d.pending_acceptance, "red", go("/ecps?view=IN_PROCESS")],
      ["Net Metering", d.net_metering, "slate", go("/ecps?stage=NET_METERING")],
    ]]);
    sections.push(["Site Visit Supervision", [
      ["Awaiting Assignment", d.sv_awaiting, "amber", go("/site-visits?status=REQUESTED")],
      ["In Process", d.sv_in_process, "indigo", go("/site-visits?status=ASSIGNED")],
    ]]);
  } else if (user.role === "INSTALLATION_MEMBER") {
    sections.push(["My Installations", [
      ["Ready to Install", d.ready_to_install, "teal", go("/ecps?view=READY_TO_INSTALL")],
      ["In Process", d.install_in_process, "indigo", go("/ecps?view=IN_PROCESS")],
      ["Pending Acceptance", d.pending_acceptance, "amber", go("/ecps?view=IN_PROCESS")],
    ]]);
    sections.push(["My Site Visits", [
      ["Assigned to Me", d.sv_assigned, "amber", go("/site-visits?status=ASSIGNED")],
      ["Due Today", d.sv_today, "sky", go("/site-visits?status=ASSIGNED")],
      ["Completed", d.sv_completed, "emerald", go("/site-visits?status=DONE")],
    ]]);
  } else if (user.role === "COMPLAINT") {
    sections.push(["Complaint Register", [
      ["Registered", d.registered, "amber", go("/complaints?status=REGISTERED")],
      ["Assigned", d.assigned, "sky", go("/complaints?status=ASSIGNED")],
      ["In Progress", d.in_progress, "indigo", go("/complaints?status=IN_PROGRESS")],
      ["Critical (open)", d.critical, "red", go("/complaints?priority=CRITICAL")],
      ["Due Today", d.due_today, "amber", go("/complaints")],
      ["Overdue", d.overdue, "red", go("/complaints")],
    ]]);
  }

  return (
    <div>
      <PageHeader title={`${d.role_label} Dashboard`} subtitle="Click any counter to drill down into the records."
        right={user.role === "COMPLAINT" ? (
          <Button data-testid="dashboard-register-complaint" className="bg-white text-slate-900 hover:bg-white/90 font-semibold" onClick={() => nav("/complaints?new=1")}>+ Register Complaint</Button>
        ) : null} />
      <div className="p-6 lg:p-8 space-y-8">
        {sections.map(([title, cards]) => (
          <div key={title}>
            <h2 className="font-head text-lg font-bold text-slate-800 mb-3">{title}</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
              {cards.map(([label, value, tone, onClick]) => (
                <StatCard key={label} label={label} value={value} tone={tone} onClick={onClick}
                  testid={`stat-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
