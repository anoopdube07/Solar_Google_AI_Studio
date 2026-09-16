import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ROLE_LABELS } from "@/lib/constants";
import {
  LayoutDashboard, Users2, Workflow, MapPin, AlertTriangle,
  Wallet, UserCog, Timer, LogOut, Sun, ClipboardList, Menu, X,
  Package, SlidersHorizontal,
} from "lucide-react";

const NAV = {
  OWNER: [
    ["/", "Dashboard", LayoutDashboard],
    ["/leads", "Leads", Users2],
    ["/ecps", "ECP Projects", Workflow],
    ["/site-visits", "Site Visits", MapPin],
    ["/escalations", "Escalations", AlertTriangle],
    ["/payments", "Payments", Wallet],
    ["/complaints", "Complaints", AlertTriangle],
    ["/work-done", "Work Done", ClipboardList],
    ["/items", "Item Master", Package],
    ["/lead-fields", "Lead Field Rules", SlidersHorizontal],
    ["/users", "Users", UserCog],
    ["/sla", "SLA Config", Timer],
  ],
  MANAGER: [
    ["/", "Dashboard", LayoutDashboard],
    ["/leads", "Leads", Users2],
    ["/ecps", "ECP Projects", Workflow],
    ["/site-visits", "Site Visits", MapPin],
    ["/payments", "Payments", Wallet],
    ["/complaints", "Complaints", AlertTriangle],
  ],
  LEAD: [
    ["/", "Dashboard", LayoutDashboard],
    ["/leads", "Leads", Users2],
    ["/ecps", "ECP Projects", Workflow],
  ],
  REGISTRATION: [
    ["/", "Dashboard", LayoutDashboard],
    ["/ecps", "ECP Projects", Workflow],
  ],
  ACCOUNTS: [
    ["/", "Dashboard", LayoutDashboard],
    ["/ecps", "ECP Projects", Workflow],
    ["/payments", "Payments", Wallet],
  ],
  DISPATCH: [
    ["/", "Dashboard", LayoutDashboard],
    ["/ecps", "ECP Projects", Workflow],
  ],
  INSTALLATION: [
    ["/", "Dashboard", LayoutDashboard],
    ["/site-visits", "Site Visits", MapPin],
    ["/ecps", "ECP Projects", Workflow],
  ],
  INSTALLATION_MANAGER: [
    ["/", "Dashboard", LayoutDashboard],
    ["/site-visits", "Site Visits", MapPin],
    ["/ecps", "ECP Projects", Workflow],
  ],
  INSTALLATION_MEMBER: [
    ["/", "Dashboard", LayoutDashboard],
    ["/site-visits", "Site Visits", MapPin],
    ["/ecps", "ECP Projects", Workflow],
  ],
  COMPLAINT: [
    ["/", "Dashboard", LayoutDashboard],
    ["/complaints", "Complaints", AlertTriangle],
  ],
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const items = NAV[user?.role] || NAV.OWNER;

  const go = (path) => { nav(path); setOpen(false); };

  const SidebarInner = (
    <>
      <div className="px-5 py-5 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sun className="text-amber-400" size={22} />
          <div>
            <div className="font-head font-extrabold text-white text-lg leading-none">ECP Tracker</div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 mt-1">Ops Command</div>
          </div>
        </div>
        <button className="lg:hidden text-slate-300" onClick={() => setOpen(false)} data-testid="sidebar-close"><X size={20} /></button>
      </div>
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {items.map(([path, label, Icon]) => {
          const active = loc.pathname === path || (path !== "/" && loc.pathname.startsWith(path));
          return (
            <button key={path} data-testid={`nav-${label.toLowerCase().replace(/\s+/g, "-")}`} onClick={() => go(path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}>
              <Icon size={17} /> {label}
            </button>
          );
        })}
      </nav>
      <div className="p-3 border-t border-white/10">
        <div className="px-2 py-2">
          <div className="text-sm font-semibold text-white truncate">{user?.name}</div>
          <div className="text-[11px] font-mono uppercase tracking-wide text-sky-300">{ROLE_LABELS[user?.role]}</div>
        </div>
        <button data-testid="logout-button" onClick={() => { logout(); nav("/login"); }}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-300 hover:bg-red-600 hover:text-white transition-colors">
          <LogOut size={16} /> Log out
        </button>
      </div>
    </>
  );

  return (
    <div className="min-h-screen flex bg-background">
      {/* Desktop sidebar */}
      <aside className="w-60 shrink-0 command-header text-slate-200 flex-col fixed h-screen hidden lg:flex z-30">
        {SidebarInner}
      </aside>

      {/* Mobile top bar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-14 command-header text-white flex items-center justify-between px-4 z-30">
        <button data-testid="sidebar-open" onClick={() => setOpen(true)}><Menu size={22} /></button>
        <div className="flex items-center gap-2"><Sun className="text-amber-400" size={18} /><span className="font-head font-extrabold">ECP Tracker</span></div>
        <div className="w-6" />
      </div>

      {/* Mobile drawer */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-40" data-testid="mobile-drawer">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 command-header text-slate-200 flex flex-col">
            {SidebarInner}
          </aside>
        </div>
      )}

      <main className="flex-1 lg:ml-60 min-h-screen pt-14 lg:pt-0">{children}</main>
    </div>
  );
}
