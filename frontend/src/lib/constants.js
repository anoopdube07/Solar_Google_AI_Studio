// Shared business labels & badge styles (visual only; business rules from backend)

export const ROLE_LABELS = {
  OWNER: "Owner",
  MANAGER: "Process Owner / Manager",
  LEAD: "Lead Team",
  REGISTRATION: "Registration Team",
  ACCOUNTS: "Accounts Team",
  DISPATCH: "Dispatch Team",
  INSTALLATION: "Installation Team",
  INSTALLATION_MANAGER: "Installation Manager",
  INSTALLATION_MEMBER: "Installation Member",
  COMPLAINT: "Complaint Team",
};

export const STAGE_LABELS = {
  PENDING_DOCUMENTS: "Pending Documents",
  REGISTRATION_1: "Registration 1",
  ACCOUNTS_1: "Accounts 1",
  DISPATCH: "Dispatch",
  INSTALLATION: "Installation",
  NET_METERING: "Net Metering",
  REGISTRATION_2: "Registration 2",
  ACCOUNTS_2: "Accounts 2",
  COMPLETED: "Successfully Completed",
  CLOSED: "Closed / Cancelled",
};

export const STAGE_ORDER = [
  "REGISTRATION_1", "ACCOUNTS_1", "DISPATCH", "INSTALLATION",
  "NET_METERING", "REGISTRATION_2", "ACCOUNTS_2",
];

export const DOC_LABELS = {
  PAN: "PAN Card",
  AADHAAR: "Aadhaar Card",
  ELECTRICITY_BILL: "Electricity Bill",
  BANK_PASSBOOK: "Bank Passbook Photo",
  BANK_STATEMENT: "3-Month Bank Statement",
  CANCELLED_CHEQUE: "Cancelled Cheque",
  PROPERTY_PAPER: "Property Paper",
  TAX_RECEIPT: "Tax Receipt",
};

export const LEAD_STATUS_LABELS = {
  PENDING: "Pending",
  FOLLOW_UP: "Follow-up",
  SITE_VISIT: "Site Visit",
  ESCALATED: "Escalated",
  QUALIFIED: "Qualified",
  LOST: "Lost",
};

export const RETURN_REASON_LABELS = {
  SITE_VISIT_COMPLETED: "Site Visit Completed",
  OWNER_RETURNED: "Owner Returned",
  REOPENED: "Reopened",
};

export function badgeClass(key) {
  const map = {
    PENDING: "bg-amber-100 text-amber-800 border-amber-300",
    FOLLOW_UP: "bg-blue-100 text-blue-800 border-blue-300",
    SITE_VISIT: "bg-purple-100 text-purple-800 border-purple-300",
    ESCALATED: "bg-red-100 text-red-800 border-red-300",
    QUALIFIED: "bg-emerald-100 text-emerald-800 border-emerald-300",
    LOST: "bg-slate-100 text-slate-600 border-slate-300",
    ACTIVE: "bg-sky-100 text-sky-800 border-sky-300",
    COMPLETED: "bg-emerald-100 text-emerald-800 border-emerald-300",
    CLOSED: "bg-slate-200 text-slate-700 border-slate-400",
    PAYMENT_BLOCKED: "bg-rose-100 text-rose-800 border-rose-300",
    READY_FOR_DISPATCH: "bg-teal-100 text-teal-800 border-teal-300",
    DISPATCH_IN_PROCESS: "bg-indigo-100 text-indigo-800 border-indigo-300",
    READY_TO_INSTALL: "bg-cyan-100 text-cyan-800 border-cyan-300",
    IN_PROCESS: "bg-indigo-100 text-indigo-800 border-indigo-300",
    COMPLETED_INSTALL: "bg-emerald-100 text-emerald-800 border-emerald-300",
    DELAYED: "bg-red-50 text-red-700 border-red-400 animate-pulse",
    CONFIRMED: "bg-emerald-100 text-emerald-800 border-emerald-300",
  };
  return map[key] || "bg-slate-100 text-slate-700 border-slate-300";
}

export const DERIVED_LABELS = {
  PAYMENT_BLOCKED: "Payment Blocked",
  READY_FOR_DISPATCH: "Ready for Dispatch",
  DISPATCH_IN_PROCESS: "Dispatch In Process",
  AWAITING_ASSIGNMENT: "Awaiting Install Assignment",
  READY_TO_INSTALL: "Ready to Install",
  IN_PROCESS: "Installation In Process",
  COMPLETED: "Installation Completed",
};
