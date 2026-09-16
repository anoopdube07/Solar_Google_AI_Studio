import bcrypt from "bcryptjs";

export interface User {
  id: string;
  username: string;
  password_hash: string;
  name: string;
  role: string;
  team: string;
  phone: string;
  active: boolean;
  created_at: string;
}

export interface Lead {
  id: string;
  name: string;
  phone: string;
  email: string;
  address: string;
  source: string;
  status: string; // PENDING, FOLLOW_UP, SITE_VISIT, ESCALATED, QUALIFIED, LOST
  financing_required: boolean;
  project_price: number;
  item_id?: string | null;
  quantity?: number | null;
  location_link?: string;
  remarks?: string;
  lost_reason?: string;
  lost_remarks?: string;
  created_at: string;
  updated_at: string;
  lead_owner_id?: string;
  lead_owner_name?: string;
  assigned_user?: string;
  pending_commercial_change?: any;
}

export interface Task {
  id: string;
  ecp_id: string;
  stage: string;
  name: string;
  team: string;
  applicable: boolean;
  completed: boolean;
  completed_at?: string;
  completed_by?: string;
  completed_by_name?: string;
}

export interface Ecp {
  id: string;
  lead_id: string;
  project_name: string;
  current_stage: string; // REGISTRATION_1, ACCOUNTS_1, DISPATCH, INSTALLATION, NET_METERING, REGISTRATION_2, ACCOUNTS_2, COMPLETED, CLOSED
  status: string; // ACTIVE, COMPLETED, CLOSED
  financing_required: boolean;
  project_price: number;
  customer_name: string;
  customer_phone: string;
  created_at: string;
  updated_at: string;
  stage_entered_at: string;
  lead_owner_id?: string;
  responsible_user?: string;
  install_status?: string; // AWAITING_ASSIGNMENT, READY_TO_INSTALL, IN_PROCESS, PENDING_ACCEPTANCE, COMPLETED
  derived_status?: string;
  delayed?: boolean;
  days_in_stage?: number;
  sla_days?: number;
  closed_reason?: string;
  closed_remarks?: string;
}

export interface Payment {
  id: string;
  ecp_id: string;
  type: string; // FIRST, ADDITIONAL, FINAL
  amount: number;
  date: string;
  status: string; // PENDING, CONFIRMED
  reference_no?: string;
  notes?: string;
  created_at: string;
  created_by?: string;
  created_by_name?: string;
}

export interface SiteVisit {
  id: string;
  lead_id: string;
  lead_name: string;
  lead_phone: string;
  address: string;
  status: string; // REQUESTED, ASSIGNED, DONE, CANCELLED
  requested_by_name: string;
  assigned_user?: string;
  assigned_user_name?: string;
  visit_date?: string;
  remarks?: string;
  created_at: string;
  completed_at?: string;
  report?: string;
}

export interface Complaint {
  id: string;
  ticket_no: string;
  lead_id?: string;
  customer_name: string;
  customer_phone: string;
  category: string;
  priority: string; // LOW, MEDIUM, HIGH, CRITICAL
  status: string; // REGISTERED, ASSIGNED, IN_PROGRESS, RESOLVED, CLOSED
  assigned_team: string;
  assigned_user?: string;
  assigned_user_name?: string;
  subject: string;
  description: string;
  created_at: string;
  updated_at: string;
  resolved_at?: string;
}

export interface Item {
  id: string;
  name: string;
  code: string;
  category: string;
  price: number;
  unit: string;
  active: boolean;
  created_at: string;
}

export interface Activity {
  id: string;
  activity: string;
  timestamp: string;
  user_name: string;
  lead_name?: string;
  ecp_name?: string;
}

export interface DocumentItem {
  id: string;
  lead_id: string;
  doc_type: string;
  original_filename: string;
  content_type: string;
  size: number;
  uploaded_by_name: string;
  uploaded_at: string;
  buffer?: Buffer;
}

export interface ChallanItem {
  item_id: string;
  name: string;
  code: string;
  quantity: number;
  unit: string;
}

export interface Challan {
  ecp_id: string;
  challan_no: string;
  items: ChallanItem[];
  dispatch_date: string;
  status: "DRAFT" | "FINALIZED";
  vehicle_no?: string;
  driver_contact?: string;
}

// Global In-Memory Stores
export const db = {
  users: new Map<string, User>(),
  leads: new Map<string, Lead>(),
  ecps: new Map<string, Ecp>(),
  tasks: new Map<string, Task>(),
  payments: new Map<string, Payment>(),
  site_visits: new Map<string, SiteVisit>(),
  complaints: new Map<string, Complaint>(),
  items: new Map<string, Item>(),
  activities: [] as Activity[],
  documents: new Map<string, DocumentItem>(),
  site_visit_photos: new Map<string, any>(),
  install_photos: new Map<string, any>(),
  challans: new Map<string, Challan>(),
  sla_config: {
    REGISTRATION_1: 2,
    ACCOUNTS_1: 2,
    DISPATCH: 3,
    INSTALLATION: 4,
    NET_METERING: 5,
    REGISTRATION_2: 2,
    ACCOUNTS_2: 3,
  } as Record<string, number>,
  lead_field_config: [] as any[],
  lead_employees: [
    { id: "emp-1", name: "Rahul Lead", active: true },
    { id: "emp-2", name: "Suresh Marketing", active: true },
    { id: "emp-3", name: "Kavita Sales", active: true },
  ],
};

export function logActivity(activity: string, user_name = "System", lead_name = "", ecp_name = "") {
  db.activities.unshift({
    id: `act-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    activity,
    timestamp: new Date().toISOString(),
    user_name,
    lead_name,
    ecp_name,
  });
  if (db.activities.length > 500) db.activities.pop();
}

export function initSeedData() {
  if (db.users.size > 0) return; // already seeded

  const now = new Date().toISOString();

  // 1. Seed Users
  const seedUsers = [
    { id: "u-owner", username: "anoopdube07@gmail.com", name: "Anoop Dube", role: "OWNER", phone: "9876543210" },
    { id: "u-mgr", username: "manager", name: "Priya Manager", role: "MANAGER", phone: "9876543211" },
    { id: "u-lead", username: "lead", name: "Rahul Lead", role: "LEAD", phone: "9876543212" },
    { id: "u-reg", username: "registration", name: "Sunita Reg", role: "REGISTRATION", phone: "9876543213" },
    { id: "u-acct", username: "accounts", name: "Vikram Accounts", role: "ACCOUNTS", phone: "9876543214" },
    { id: "u-disp", username: "dispatch", name: "Amit Dispatch", role: "DISPATCH", phone: "9876543215" },
    { id: "u-inst", username: "installation", name: "Ravi Install", role: "INSTALLATION", phone: "9876543216" },
    { id: "u-instmgr", username: "instmgr", name: "Iqbal Install-Manager", role: "INSTALLATION_MANAGER", phone: "9876543217" },
    { id: "u-instmem", username: "instmem", name: "Manish Install-Member", role: "INSTALLATION_MEMBER", phone: "9876543218" },
    { id: "u-comp", username: "complaint", name: "Neha Complaints", role: "COMPLAINT", phone: "9876543219" },
  ];

  for (const u of seedUsers) {
    const password = u.role === "OWNER" ? "Owner@123" : `${u.role.charAt(0) + u.role.slice(1).toLowerCase().replace(/_.*$/, "")}@123`;
    db.users.set(u.id, {
      id: u.id,
      username: u.username.toLowerCase(),
      password_hash: bcrypt.hashSync(password, 10),
      name: u.name,
      role: u.role,
      team: u.role,
      phone: u.phone,
      active: true,
      created_at: now,
    });
  }

  // 2. Seed Items
  const items = [
    { id: "it-1", name: "Mono PERC Solar Panel 540W", code: "PV-540W", category: "Panels", price: 14500, unit: "Nos", active: true },
    { id: "it-2", name: "On-Grid Solar Inverter 5kW 3-Phase", code: "INV-5KW", category: "Inverters", price: 42000, unit: "Nos", active: true },
    { id: "it-3", name: "On-Grid Solar Inverter 10kW 3-Phase", code: "INV-10KW", category: "Inverters", price: 68000, unit: "Nos", active: true },
    { id: "it-4", name: "GI Elevated Structure 4-Panel", code: "STR-4P", category: "Structure", price: 6200, unit: "Set", active: true },
    { id: "it-5", name: "Solar DC Cable 4 sq mm Red/Black", code: "CAB-DC-4", category: "Wiring", price: 85, unit: "Meter", active: true },
    { id: "it-6", name: "Copper Bonded Chemical Earthing Kit", code: "EARTH-KIT", category: "Safety", price: 3800, unit: "Set", active: true },
  ];
  for (const it of items) {
    db.items.set(it.id, { ...it, created_at: now });
  }

  // 3. Seed Projects & Leads
  // Project 1: Ramesh Solar Villa (10kW, Net Metering stage)
  const l1Id = "lead-1";
  const ecp1Id = "ecp-1";
  db.leads.set(l1Id, {
    id: l1Id,
    name: "Ramesh Solar Villa",
    phone: "9800000001",
    email: "ramesh@example.com",
    address: "B-42 Civil Lines, Raipur, Chhattisgarh",
    source: "Referral",
    status: "QUALIFIED",
    financing_required: true,
    project_price: 650000,
    created_at: new Date(Date.now() - 25 * 86400000).toISOString(),
    updated_at: now,
    lead_owner_id: "u-lead",
    lead_owner_name: "Rahul Lead",
  });

  db.ecps.set(ecp1Id, {
    id: ecp1Id,
    lead_id: l1Id,
    project_name: "Ramesh Solar Villa",
    current_stage: "NET_METERING",
    status: "ACTIVE",
    financing_required: true,
    project_price: 650000,
    customer_name: "Ramesh Solar Villa",
    customer_phone: "9800000001",
    created_at: new Date(Date.now() - 25 * 86400000).toISOString(),
    updated_at: now,
    stage_entered_at: new Date(Date.now() - 2 * 86400000).toISOString(),
    lead_owner_id: "u-lead",
    responsible_user: "u-inst",
    install_status: "COMPLETED",
    derived_status: "NET_METERING",
  });

  // Seed tasks for ecp-1
  seedTasksForEcp(ecp1Id, true);
  // Mark previous stage tasks completed for ecp-1
  for (const t of db.tasks.values()) {
    if (t.ecp_id === ecp1Id && ["REGISTRATION_1", "ACCOUNTS_1", "DISPATCH", "INSTALLATION"].includes(t.stage)) {
      t.completed = true;
      t.completed_at = now;
      t.completed_by_name = "System";
    }
  }

  // Payments for ecp-1
  db.payments.set("pay-1", {
    id: "pay-1",
    ecp_id: ecp1Id,
    type: "FIRST",
    amount: 200000,
    date: "2026-08-10",
    status: "CONFIRMED",
    reference_no: "UTR98342154",
    notes: "Advance payment received via NEFT",
    created_at: now,
    created_by_name: "Vikram Accounts",
  });
  db.payments.set("pay-2", {
    id: "pay-2",
    ecp_id: ecp1Id,
    type: "ADDITIONAL",
    amount: 300000,
    date: "2026-08-25",
    status: "CONFIRMED",
    reference_no: "UTR98348821",
    notes: "Dispatch milestone payment",
    created_at: now,
    created_by_name: "Vikram Accounts",
  });

  // Project 2: Sunita Rooftop (5kW, Accounts 1 stage, advance payment pending)
  const l2Id = "lead-2";
  const ecp2Id = "ecp-2";
  db.leads.set(l2Id, {
    id: l2Id,
    name: "Sunita Rooftop",
    phone: "9800000002",
    email: "sunita@example.com",
    address: "Plot 18, Shanti Nagar, Bilaspur",
    source: "Google Search",
    status: "QUALIFIED",
    financing_required: false,
    project_price: 340000,
    created_at: new Date(Date.now() - 10 * 86400000).toISOString(),
    updated_at: now,
    lead_owner_id: "u-lead",
    lead_owner_name: "Rahul Lead",
  });

  db.ecps.set(ecp2Id, {
    id: ecp2Id,
    lead_id: l2Id,
    project_name: "Sunita Rooftop",
    current_stage: "ACCOUNTS_1",
    status: "ACTIVE",
    financing_required: false,
    project_price: 340000,
    customer_name: "Sunita Rooftop",
    customer_phone: "9800000002",
    created_at: new Date(Date.now() - 10 * 86400000).toISOString(),
    updated_at: now,
    stage_entered_at: new Date(Date.now() - 4 * 86400000).toISOString(),
    lead_owner_id: "u-lead",
    derived_status: "PAYMENT_BLOCKED",
    delayed: true,
    days_in_stage: 4,
    sla_days: 2,
  });
  seedTasksForEcp(ecp2Id, false);
  for (const t of db.tasks.values()) {
    if (t.ecp_id === ecp2Id && t.stage === "REGISTRATION_1") {
      t.completed = true;
      t.completed_at = now;
      t.completed_by_name = "Sunita Reg";
    }
  }
  db.payments.set("pay-3", {
    id: "pay-3",
    ecp_id: ecp2Id,
    type: "FIRST",
    amount: 100000,
    date: new Date().toISOString().slice(0, 10),
    status: "PENDING",
    reference_no: "CHQ-104928",
    notes: "Awaiting cheque clearance",
    created_at: now,
    created_by_name: "Vikram Accounts",
  });

  // Project 3: Verma Commercial (25kW, Installation stage)
  const l3Id = "lead-3";
  const ecp3Id = "ecp-3";
  db.leads.set(l3Id, {
    id: l3Id,
    name: "Verma Cold Storage",
    phone: "9800000003",
    email: "verma@example.com",
    address: "Industrial Area Phase 2, Durg",
    source: "Expo 2026",
    status: "QUALIFIED",
    financing_required: true,
    project_price: 1450000,
    created_at: new Date(Date.now() - 18 * 86400000).toISOString(),
    updated_at: now,
    lead_owner_id: "u-lead",
    lead_owner_name: "Rahul Lead",
  });

  db.ecps.set(ecp3Id, {
    id: ecp3Id,
    lead_id: l3Id,
    project_name: "Verma Cold Storage",
    current_stage: "INSTALLATION",
    status: "ACTIVE",
    financing_required: true,
    project_price: 1450000,
    customer_name: "Verma Cold Storage",
    customer_phone: "9800000003",
    created_at: new Date(Date.now() - 18 * 86400000).toISOString(),
    updated_at: now,
    stage_entered_at: new Date(Date.now() - 1 * 86400000).toISOString(),
    lead_owner_id: "u-lead",
    responsible_user: "u-inst",
    install_status: "IN_PROCESS",
    derived_status: "IN_PROCESS",
  });
  seedTasksForEcp(ecp3Id, true);
  for (const t of db.tasks.values()) {
    if (t.ecp_id === ecp3Id && ["REGISTRATION_1", "ACCOUNTS_1", "DISPATCH"].includes(t.stage)) {
      t.completed = true;
      t.completed_at = now;
      t.completed_by_name = "System";
    }
  }

  // Active Leads pipeline
  db.leads.set("lead-4", {
    id: "lead-4",
    name: "Sharma Green Heights",
    phone: "9800000004",
    email: "sharma@example.com",
    address: "Sector 7, Shankar Nagar, Raipur",
    source: "Website",
    status: "PENDING",
    financing_required: false,
    project_price: 240000,
    created_at: now,
    updated_at: now,
    lead_owner_id: "u-lead",
    lead_owner_name: "Rahul Lead",
    remarks: "Inquired about 3kW on-grid rooftop solar for residential bungalow.",
  });

  db.leads.set("lead-5", {
    id: "lead-5",
    name: "Patel Agro Farm 15kW",
    phone: "9800000005",
    email: "patel@example.com",
    address: "Village Dhamdha, Durg",
    source: "Newspaper Ad",
    status: "SITE_VISIT",
    financing_required: true,
    project_price: 890000,
    created_at: new Date(Date.now() - 3 * 86400000).toISOString(),
    updated_at: now,
    lead_owner_id: "u-lead",
    lead_owner_name: "Rahul Lead",
  });

  db.site_visits.set("sv-1", {
    id: "sv-1",
    lead_id: "lead-5",
    lead_name: "Patel Agro Farm 15kW",
    lead_phone: "9800000005",
    address: "Village Dhamdha, Durg",
    status: "ASSIGNED",
    requested_by_name: "Rahul Lead",
    assigned_user: "u-inst",
    assigned_user_name: "Ravi Install",
    visit_date: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
    remarks: "Roof shadow analysis and transformer distance check needed.",
    created_at: now,
  });

  db.leads.set("lead-6", {
    id: "lead-6",
    name: "Gupta Textiles",
    phone: "9800000006",
    email: "gupta@example.com",
    address: "Ring Road No 1, Raipur",
    source: "Direct Walk-in",
    status: "FOLLOW_UP",
    financing_required: false,
    project_price: 1100000,
    created_at: new Date(Date.now() - 5 * 86400000).toISOString(),
    updated_at: now,
    lead_owner_id: "u-lead",
    lead_owner_name: "Rahul Lead",
    remarks: "Reviewing commercial proposal with partners. Follow-up scheduled.",
  });

  // Seed Complaints
  db.complaints.set("comp-1", {
    id: "comp-1",
    ticket_no: "CMP-2026-001",
    customer_name: "Verma Cold Storage",
    customer_phone: "9800000003",
    category: "Technical Issue",
    priority: "HIGH",
    status: "ASSIGNED",
    assigned_team: "INSTALLATION",
    assigned_user: "u-inst",
    assigned_user_name: "Ravi Install",
    subject: "Mounting structure clearance with rooftop exhaust vent",
    description: "Customer requested 30cm extra elevation near north vent.",
    created_at: new Date(Date.now() - 1 * 86400000).toISOString(),
    updated_at: now,
  });

  logActivity("Project advanced to Net Metering stage", "Sunita Reg", "Ramesh Solar Villa", "Ramesh Solar Villa");
  logActivity("Material dispatched for Verma Cold Storage", "Amit Dispatch", "Verma Cold Storage", "Verma Cold Storage");
  logActivity("Advance payment recorded of Rs 2,00,000", "Vikram Accounts", "Ramesh Solar Villa", "Ramesh Solar Villa");
  logActivity("New lead captured: Sharma Green Heights", "Rahul Lead", "Sharma Green Heights", "");
}

export function seedTasksForEcp(ecpId: string, financing: boolean) {
  const STAGE_TASK_SPECS = {
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
      { name: "Material Dispatch Confirmation", team: "DISPATCH", financing_only: false },
      { name: "Dispatch Completed", team: "DISPATCH", financing_only: false },
    ],
    INSTALLATION: [
      { name: "Structure Installation", team: "INSTALLATION", financing_only: false },
      { name: "Module Mounting & Cabling", team: "INSTALLATION", financing_only: false },
      { name: "Inverter Commissioning", team: "INSTALLATION", financing_only: false },
    ],
    NET_METERING: [
      { name: "Upload Installation Photos to CSPDCL Portal", team: "REGISTRATION", financing_only: false },
      { name: "DCR Issuance", team: "REGISTRATION", financing_only: false },
      { name: "Consumer Approval & Submit", team: "REGISTRATION", financing_only: false },
      { name: "Request Net Metering from CSPDCL", team: "REGISTRATION", financing_only: false },
      { name: "Close Net Metering", team: "INSTALLATION_MEMBER", financing_only: false },
    ],
    REGISTRATION_2: [
      { name: "Asset Creation", team: "REGISTRATION", financing_only: false },
      { name: "Completion Certificate", team: "REGISTRATION", financing_only: false },
      { name: "Bank Submission 2nd", team: "REGISTRATION", financing_only: true },
    ],
    ACCOUNTS_2: [{ name: "Final Payment Follow-up", team: "ACCOUNTS", financing_only: false }],
  };

  for (const [stage, specs] of Object.entries(STAGE_TASK_SPECS)) {
    for (const spec of specs) {
      const id = `tsk-${ecpId}-${stage}-${spec.name.replace(/\s+/g, "_")}`;
      const applicable = !spec.financing_only || financing;
      db.tasks.set(id, {
        id,
        ecp_id: ecpId,
        stage,
        name: spec.name,
        team: spec.team,
        applicable,
        completed: false,
      });
    }
  }
}
