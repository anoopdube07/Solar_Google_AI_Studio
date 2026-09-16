import React from "react";

export function PageHeader({ title, subtitle, right }) {
  return (
    <div className="command-header text-white px-6 lg:px-8 py-6 flex items-center justify-between">
      <div>
        <h1 className="font-head text-2xl sm:text-3xl font-extrabold tracking-tight">{title}</h1>
        {subtitle && <p className="text-slate-300 text-sm mt-1">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function StatCard({ label, value, tone = "slate", active, onClick, testid }) {
  const tones = {
    slate: "border-slate-200",
    sky: "border-sky-200",
    amber: "border-amber-200",
    emerald: "border-emerald-200",
    red: "border-red-300",
    indigo: "border-indigo-200",
    teal: "border-teal-200",
  };
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`text-left bg-white rounded-lg border p-4 transition-all hover:shadow-md hover:-translate-y-0.5 ${
        active ? "ring-2 ring-sky-500 border-sky-300" : tones[tone]
      } ${onClick ? "cursor-pointer" : "cursor-default"}`}
    >
      <div className="text-xs font-mono uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-3xl font-black text-slate-900 mt-2 font-head">{value ?? 0}</div>
    </button>
  );
}
