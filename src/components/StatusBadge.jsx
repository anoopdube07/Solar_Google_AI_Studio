import React from "react";
import { badgeClass, DERIVED_LABELS, LEAD_STATUS_LABELS, STAGE_LABELS } from "@/lib/constants";

export function StatusBadge({ value, label, kind }) {
  const text = label || LEAD_STATUS_LABELS[value] || DERIVED_LABELS[value] || STAGE_LABELS[value] || value;
  return (
    <span
      data-testid={`badge-${(value || "").toLowerCase()}`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-xs font-semibold ${badgeClass(kind || value)}`}
    >
      {text}
    </span>
  );
}

export function DelayedBadge() {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full border text-xs font-semibold ${badgeClass("DELAYED")}`}>
      DELAYED
    </span>
  );
}
