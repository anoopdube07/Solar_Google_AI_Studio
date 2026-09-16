export const ROLES = [
  "OWNER",
  "MANAGER",
  "LEAD",
  "REGISTRATION",
  "ACCOUNTS",
  "DISPATCH",
  "INSTALLATION",
  "INSTALLATION_MANAGER",
  "INSTALLATION_MEMBER",
  "COMPLAINT",
];

export const ROLE_LABELS: Record<string, string> = {
  OWNER: "Owner",
  MANAGER: "Process Owner / Manager",
  LEAD: "Lead Team",
  REGISTRATION: "Registration Team",
  ACCOUNTS: "Accounts Team",
  DISPATCH: "Dispatch Team",
  INSTALLATION: "Installation Team",
  INSTALLATION_MANAGER: "Installation Team Manager",
  INSTALLATION_MEMBER: "Installation Team Member",
  COMPLAINT: "Complaint Registration Team",
};

export const STAGE_ORDER = [
  "REGISTRATION_1",
  "ACCOUNTS_1",
  "DISPATCH",
  "INSTALLATION",
  "NET_METERING",
  "REGISTRATION_2",
  "ACCOUNTS_2",
];

export const STAGE_LABELS: Record<string, string> = {
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

export const STAGE_TASK_SPECS: Record<
  string,
  Array<{ name: string; team: string; financing_only: boolean; requires?: string | null }>
> = {
  REGISTRATION_1: [
    { name: "Consumer Request", team: "REGISTRATION", financing_only: false },
    { name: "CVA Print & Sign", team: "REGISTRATION", financing_only: false },
    { name: "Feasibility Report Upload", team: "REGISTRATION", financing_only: false },
    { name: "Loan Documentation", team: "REGISTRATION", financing_only: true },
    { name: "Loan Filing", team: "REGISTRATION", financing_only: true },
    { name: "Bank Submission", team: "REGISTRATION", financing_only: true },
  ],
  ACCOUNTS_1: [{ name: "Advance Verification", team: "ACCOUNTS", financing_only: false }],
  DISPATCH: [
    { name: "Delivery Challan", team: "DISPATCH", financing_only: false },
    { name: "Material Dispatch Confirmation", team: "DISPATCH", financing_only: false, requires: "Delivery Challan" },
    { name: "Dispatch Completed", team: "DISPATCH", financing_only: false, requires: "Material Dispatch Confirmation" },
  ],
  NET_METERING: [
    { name: "Upload Installation Photos to CSPDCL Portal", team: "REGISTRATION", financing_only: false },
    { name: "DCR Issuance", team: "REGISTRATION", financing_only: false, requires: "Upload Installation Photos to CSPDCL Portal" },
    { name: "Consumer Approval & Submit", team: "REGISTRATION", financing_only: false, requires: "DCR Issuance" },
    { name: "Request Net Metering from CSPDCL", team: "REGISTRATION", financing_only: false, requires: "Consumer Approval & Submit" },
    { name: "Close Net Metering", team: "INSTALLATION_MEMBER", financing_only: false, requires: "Request Net Metering from CSPDCL" },
  ],
  REGISTRATION_2: [
    { name: "Asset Creation", team: "REGISTRATION", financing_only: false },
    { name: "Completion Certificate", team: "REGISTRATION", financing_only: false, requires: "Asset Creation" },
    { name: "Bank Submission 2nd", team: "REGISTRATION", financing_only: true },
  ],
  ACCOUNTS_2: [{ name: "Final Payment Follow-up", team: "ACCOUNTS", financing_only: false }],
};

export const DOC_REQUIRED_SINGLE = ["PAN", "AADHAAR", "ELECTRICITY_BILL"];
export const DOC_BANK_GROUP = ["BANK_PASSBOOK", "BANK_STATEMENT", "CANCELLED_CHEQUE"];
export const DOC_FINANCE_GROUP = ["PROPERTY_PAPER", "TAX_RECEIPT"];

export function documentsComplete(currentTypes: string[], financing: boolean): boolean {
  const set = new Set(currentTypes);
  if (!DOC_REQUIRED_SINGLE.every((t) => set.has(t))) return false;
  if (!DOC_BANK_GROUP.some((t) => set.has(t))) return false;
  if (financing && !DOC_FINANCE_GROUP.some((t) => set.has(t))) return false;
  return true;
}
