import express, { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";
import multer from "multer";
import {
  db,
  User,
  Lead,
  Ecp,
  Payment,
  SiteVisit,
  Complaint,
  Item,
  DocumentItem,
  logActivity,
  seedTasksForEcp,
} from "./data";
import {
  ROLES,
  STAGE_ORDER,
  STAGE_LABELS,
  documentsComplete,
} from "./workflow";

const JWT_SECRET = process.env.JWT_SECRET || "supersecretjwtkeyforlocaldevelopment12345";
const upload = multer({ storage: multer.memoryStorage() });

export const apiRouter = express.Router();

// Helper: extract auth user
function authUser(req: Request): User | null {
  const authHeader = req.headers.authorization || "";
  if (!authHeader.startsWith("Bearer ")) return null;
  const token = authHeader.slice(7);
  try {
    const payload = jwt.verify(token, JWT_SECRET) as any;
    const user = db.users.get(payload.sub);
    return user && user.active ? user : null;
  } catch {
    return null;
  }
}

function requireAuth(req: Request, res: Response, next: NextFunction) {
  const user = authUser(req);
  if (!user) return res.status(401).json({ detail: "Not authenticated" });
  (req as any).user = user;
  next();
}

function requireRoles(...roles: string[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    const user = (req as any).user as User;
    if (!user || !roles.includes(user.role)) {
      return res.status(403).json({ detail: "You do not have permission for this action" });
    }
    next();
  };
}

function cleanUser(u: User) {
  const copy = { ...u } as any;
  delete copy.password_hash;
  return copy;
}

// ------------------- AUTH -------------------
apiRouter.post("/auth/login", (req, res) => {
  const { username, password } = req.body || {};
  if (!username || !password) {
    return res.status(400).json({ detail: "Username and password required" });
  }
  const cleanUsername = String(username).trim().toLowerCase();
  let foundUser: User | null = null;
  for (const u of db.users.values()) {
    if (u.username.toLowerCase() === cleanUsername) {
      foundUser = u;
      break;
    }
  }
  if (!foundUser || !bcrypt.compareSync(password, foundUser.password_hash)) {
    return res.status(401).json({ detail: "Invalid username or password" });
  }
  if (!foundUser.active) {
    return res.status(403).json({ detail: "Account is deactivated" });
  }
  const token = jwt.sign(
    { sub: foundUser.id, username: foundUser.username, role: foundUser.role },
    JWT_SECRET,
    { expiresIn: "7d" }
  );
  res.json({ token, user: cleanUser(foundUser) });
});

apiRouter.get("/auth/me", requireAuth, (req, res) => {
  res.json(cleanUser((req as any).user));
});

// ------------------- USERS -------------------
export interface UserAssignmentItem {
  id: string;
  type: "LEAD" | "ECP_INSTALLATION" | "ECP_LEAD_OWNER" | "SITE_VISIT" | "COMPLAINT";
  type_label: string;
  record_id: string;
  record_title: string;
  current_stage: string;
  details: string;
  required_role: string;
  eligible_users: { id: string; name: string; username: string; role: string }[];
}

export function getPendingAssignmentsForUser(userId: string): UserAssignmentItem[] {
  const assignments: UserAssignmentItem[] = [];

  // 1. Leads: pending/active if status not in QUALIFIED, LOST
  for (const lead of db.leads.values()) {
    const isAssigned = lead.lead_owner_id === userId || lead.assigned_user === userId;
    const isActive = lead.status !== "QUALIFIED" && lead.status !== "LOST";
    if (isAssigned && isActive) {
      const eligibleUsers = Array.from(db.users.values())
        .filter((u) => u.active && u.role === "LEAD" && u.id !== userId)
        .map(cleanUser);
      assignments.push({
        id: `lead_${lead.id}`,
        type: "LEAD",
        type_label: "Lead",
        record_id: lead.id,
        record_title: lead.name,
        current_stage: lead.status,
        details: `Lead #${lead.id} · Status: ${lead.status} · Phone: ${lead.phone || "—"}`,
        required_role: "LEAD",
        eligible_users: eligibleUsers,
      });
    }
  }

  // 2. ECPs: pending/active only if status is ACTIVE
  for (const ecp of db.ecps.values()) {
    if (ecp.status !== "ACTIVE") continue;

    // Installation assignment: only when ECP is currently in INSTALLATION stage and installation is active/pending
    const isInstallationActive =
      ecp.current_stage === "INSTALLATION" &&
      ecp.responsible_user === userId &&
      ecp.install_status !== "COMPLETED";

    if (isInstallationActive) {
      const eligibleUsers = Array.from(db.users.values())
        .filter((u) => u.active && (u.role === "INSTALLATION" || u.role === "INSTALLATION_MEMBER") && u.id !== userId)
        .map(cleanUser);
      assignments.push({
        id: `ecp_inst_${ecp.id}`,
        type: "ECP_INSTALLATION",
        type_label: "ECP Installation",
        record_id: ecp.id,
        record_title: ecp.project_name || ecp.customer_name,
        current_stage: ecp.current_stage,
        details: `Project #${ecp.id} · Stage: ${STAGE_LABELS[ecp.current_stage] || ecp.current_stage} · Install Status: ${ecp.install_status || "ACTIVE"}`,
        required_role: "INSTALLATION",
        eligible_users: eligibleUsers,
      });
    }

    // Lead owner assignment on active project
    if (ecp.lead_owner_id === userId) {
      const eligibleUsers = Array.from(db.users.values())
        .filter((u) => u.active && u.role === "LEAD" && u.id !== userId)
        .map(cleanUser);
      assignments.push({
        id: `ecp_lead_${ecp.id}`,
        type: "ECP_LEAD_OWNER",
        type_label: "ECP Project Owner",
        record_id: ecp.id,
        record_title: ecp.project_name || ecp.customer_name,
        current_stage: ecp.current_stage,
        details: `Project #${ecp.id} · Stage: ${STAGE_LABELS[ecp.current_stage] || ecp.current_stage} · Customer: ${ecp.customer_name}`,
        required_role: "LEAD",
        eligible_users: eligibleUsers,
      });
    }
  }

  // 3. Lead-stage Site Visits: pending if status in REQUESTED, ASSIGNED
  for (const sv of db.site_visits.values()) {
    const isAssigned = sv.assigned_user === userId;
    const isActive = sv.status === "REQUESTED" || sv.status === "ASSIGNED";
    if (isAssigned && isActive) {
      const eligibleUsers = Array.from(db.users.values())
        .filter((u) => u.active && (u.role === "INSTALLATION" || u.role === "INSTALLATION_MEMBER") && u.id !== userId)
        .map(cleanUser);
      assignments.push({
        id: `sv_${sv.id}`,
        type: "SITE_VISIT",
        type_label: "Site Visit",
        record_id: sv.id,
        record_title: sv.lead_name || `Site Visit #${sv.id}`,
        current_stage: sv.status,
        details: `Site Visit #${sv.id} · Date: ${sv.visit_date || "Not scheduled"} · Status: ${sv.status}`,
        required_role: "INSTALLATION",
        eligible_users: eligibleUsers,
      });
    }
  }

  // 4. Complaints: pending if status not in RESOLVED, CLOSED
  for (const c of db.complaints.values()) {
    const isAssigned = c.assigned_user === userId;
    const isActive = c.status !== "RESOLVED" && c.status !== "CLOSED";
    if (isAssigned && isActive) {
      const team = c.assigned_team || "COMPLAINT";
      const targetRoles = team === "INSTALLATION" ? ["INSTALLATION", "INSTALLATION_MEMBER"] : [team];
      const eligibleUsers = Array.from(db.users.values())
        .filter((u) => u.active && targetRoles.includes(u.role) && u.id !== userId)
        .map(cleanUser);
      assignments.push({
        id: `complaint_${c.id}`,
        type: "COMPLAINT",
        type_label: "Complaint",
        record_id: c.id,
        record_title: c.ticket_no ? `${c.ticket_no}: ${c.subject}` : c.subject,
        current_stage: c.status,
        details: `Ticket: ${c.ticket_no || c.id} · Team: ${c.assigned_team} · Priority: ${c.priority} · Status: ${c.status}`,
        required_role: c.assigned_team,
        eligible_users: eligibleUsers,
      });
    }
  }

  return assignments;
}

apiRouter.get("/users", requireAuth, (req, res) => {
  let users = Array.from(db.users.values());
  const { status } = req.query;
  if (status === "ACTIVE") {
    users = users.filter((u) => u.active);
  } else if (status === "INACTIVE") {
    users = users.filter((u) => !u.active);
  }
  res.json(users.map(cleanUser));
});

apiRouter.get("/users/:id/assignments", requireAuth, requireRoles("OWNER"), (req, res) => {
  const user = db.users.get(req.params.id);
  if (!user) return res.status(404).json({ detail: "User not found" });
  const assignments = getPendingAssignmentsForUser(user.id);
  res.json({
    user: cleanUser(user),
    count: assignments.length,
    assignments,
  });
});

apiRouter.get("/users/team/:role", requireAuth, (req, res) => {
  const { role } = req.params;
  const targetRoles = role === "INSTALLATION" ? ["INSTALLATION", "INSTALLATION_MEMBER"] : [role];
  const list = Array.from(db.users.values())
    .filter((u) => targetRoles.includes(u.role) && u.active)
    .map((u) => ({ id: u.id, name: u.name, username: u.username, role: u.role }));
  res.json(list);
});

apiRouter.post("/users", requireAuth, requireRoles("OWNER"), (req, res) => {
  const { username, password, name, role, phone } = req.body;
  if (!username || !password || !name || !role) {
    return res.status(400).json({ detail: "Missing required fields" });
  }
  const cleanUsername = String(username).trim().toLowerCase();
  for (const u of db.users.values()) {
    if (u.username.toLowerCase() === cleanUsername) {
      return res.status(400).json({ detail: "Username already exists" });
    }
  }
  const id = `u-${Date.now()}`;
  const newUser: User = {
    id,
    username: cleanUsername,
    password_hash: bcrypt.hashSync(password, 10),
    name: String(name).trim(),
    role: String(role).toUpperCase(),
    team: String(role).toUpperCase(),
    phone: String(phone || "").trim(),
    active: true,
    created_at: new Date().toISOString(),
  };
  db.users.set(id, newUser);
  logActivity(`Created user ${newUser.name} (${newUser.role})`, (req as any).user.name);
  res.json(cleanUser(newUser));
});

apiRouter.patch("/users/:id", requireAuth, requireRoles("OWNER"), (req, res) => {
  const user = db.users.get(req.params.id);
  if (!user) return res.status(404).json({ detail: "User not found" });
  const { name, role, phone, active, password } = req.body;
  if (name !== undefined) user.name = String(name).trim();
  if (role !== undefined) {
    user.role = String(role).toUpperCase();
    user.team = user.role;
  }
  if (phone !== undefined) user.phone = String(phone).trim();
  if (password) user.password_hash = bcrypt.hashSync(password, 10);

  if (active !== undefined) {
    const shouldBeActive = Boolean(active);
    if (!shouldBeActive && user.active) {
      // Trying to deactivate: verify not current authenticated user
      const currentUserId = (req as any).user?.id;
      if (user.id === currentUserId) {
        return res.status(400).json({ detail: "Cannot deactivate your own account" });
      }

      // Authoritative check: zero active assignments required
      const pending = getPendingAssignmentsForUser(user.id);
      if (pending.length > 0) {
        return res.status(400).json({
          detail: `User has ${pending.length} active assignment(s). Every active assignment must be reassigned before deactivation.`,
          pending_count: pending.length,
          assignments: pending,
        });
      }

      user.active = false;
      logActivity(`Deactivated user ${user.name} (${user.role})`, (req as any).user.name);
    } else if (shouldBeActive && !user.active) {
      user.active = true;
      logActivity(`Activated user ${user.name} (${user.role})`, (req as any).user.name);
    }
  }

  res.json(cleanUser(user));
});

apiRouter.post("/users/:id/reassign-and-deactivate", requireAuth, requireRoles("OWNER"), (req, res) => {
  const targetUser = db.users.get(req.params.id);
  if (!targetUser) return res.status(404).json({ detail: "User not found" });

  const currentUserId = (req as any).user?.id;
  if (targetUser.id === currentUserId) {
    return res.status(400).json({ detail: "Cannot deactivate your own account" });
  }

  // Authoritatively fetch all currently pending/active assignments
  const pending = getPendingAssignmentsForUser(targetUser.id);
  if (pending.length === 0) {
    targetUser.active = false;
    logActivity(`Deactivated user ${targetUser.name} (${targetUser.role})`, (req as any).user.name);
    return res.json({ success: true, user: cleanUser(targetUser), reassigned_count: 0 });
  }

  const { reassignments } = req.body || {};
  if (!Array.isArray(reassignments)) {
    return res.status(400).json({ detail: "Reassignments array is required" });
  }

  // 1. Authoritative Validation: verify every pending assignment is explicitly provided with an eligible active replacement
  for (const a of pending) {
    const item = reassignments.find(
      (r: any) => r.id === a.id || (r.type === a.type && r.record_id === a.record_id)
    );
    if (!item || !item.new_user_id) {
      return res.status(400).json({
        detail: `Missing replacement user for ${a.type_label}: ${a.record_title}`,
      });
    }

    const replacement = db.users.get(item.new_user_id);
    if (!replacement) {
      return res.status(400).json({
        detail: `Replacement user not found for ${a.record_title}`,
      });
    }
    if (replacement.id === targetUser.id) {
      return res.status(400).json({
        detail: `Cannot reassign ${a.record_title} to the user being deactivated`,
      });
    }
    if (!replacement.active) {
      return res.status(400).json({
        detail: `Replacement user ${replacement.name} is inactive`,
      });
    }

    // Role eligibility check
    if (a.type === "LEAD" || a.type === "ECP_LEAD_OWNER") {
      if (replacement.role !== "LEAD") {
        return res.status(400).json({
          detail: `Replacement user for ${a.type_label} must have role LEAD (selected ${replacement.name} has ${replacement.role})`,
        });
      }
    } else if (a.type === "ECP_INSTALLATION" || a.type === "SITE_VISIT") {
      if (!["INSTALLATION", "INSTALLATION_MEMBER"].includes(replacement.role)) {
        return res.status(400).json({
          detail: `Replacement user for ${a.type_label} must belong to Installation team (selected ${replacement.name} has ${replacement.role})`,
        });
      }
    } else if (a.type === "COMPLAINT") {
      const allowedRoles =
        a.required_role === "INSTALLATION"
          ? ["INSTALLATION", "INSTALLATION_MEMBER"]
          : [a.required_role];
      if (!allowedRoles.includes(replacement.role)) {
        return res.status(400).json({
          detail: `Replacement user for complaint must belong to team ${a.required_role} (selected ${replacement.name} has ${replacement.role})`,
        });
      }
    }
  }

  // 2. Authoritatively execute work-by-work reassignments
  for (const a of pending) {
    const item = reassignments.find(
      (r: any) => r.id === a.id || (r.type === a.type && r.record_id === a.record_id)
    );
    const replacement = db.users.get(item.new_user_id)!;

    if (a.type === "LEAD") {
      const lead = db.leads.get(a.record_id);
      if (lead) {
        const prev = lead.lead_owner_name || "—";
        lead.lead_owner_id = replacement.id;
        lead.lead_owner_name = replacement.name;
        lead.assigned_user = replacement.id;
        lead.updated_at = new Date().toISOString();
        logActivity(
          `Lead Reassigned: ${lead.name} (${prev} → ${replacement.name})`,
          (req as any).user.name,
          lead.name
        );
      }
    } else if (a.type === "ECP_INSTALLATION") {
      const ecp = db.ecps.get(a.record_id);
      if (ecp) {
        ecp.responsible_user = replacement.id;
        ecp.updated_at = new Date().toISOString();
        logActivity(
          `Installation Reassigned: ${ecp.project_name} to ${replacement.name}`,
          (req as any).user.name,
          undefined,
          ecp.project_name
        );
      }
    } else if (a.type === "ECP_LEAD_OWNER") {
      const ecp = db.ecps.get(a.record_id);
      if (ecp) {
        ecp.lead_owner_id = replacement.id;
        ecp.updated_at = new Date().toISOString();
        logActivity(
          `Project Ownership Reassigned: ${ecp.project_name} to ${replacement.name}`,
          (req as any).user.name,
          undefined,
          ecp.project_name
        );
      }
    } else if (a.type === "SITE_VISIT") {
      const sv = db.site_visits.get(a.record_id);
      if (sv) {
        sv.assigned_user = replacement.id;
        sv.assigned_user_name = replacement.name;
        logActivity(
          `Site Visit Reassigned: ${sv.lead_name} to ${replacement.name}`,
          (req as any).user.name,
          sv.lead_name
        );
      }
    } else if (a.type === "COMPLAINT") {
      const comp = db.complaints.get(a.record_id);
      if (comp) {
        comp.assigned_user = replacement.id;
        comp.assigned_user_name = replacement.name;
        comp.updated_at = new Date().toISOString();
        logActivity(
          `Complaint Reassigned: ${comp.ticket_no || comp.id} to ${replacement.name}`,
          (req as any).user.name
        );
      }
    }
  }

  // 3. Authoritative post-reassignment check: verify ZERO active assignments remain
  const remaining = getPendingAssignmentsForUser(targetUser.id);
  if (remaining.length > 0) {
    return res.status(500).json({
      detail: `Reassignment incomplete. ${remaining.length} active assignment(s) still remain with user. Inactivation aborted.`,
    });
  }

  // 4. Safe deactivation: user record remains in database, active set to false
  targetUser.active = false;
  logActivity(
    `Deactivated user ${targetUser.name} (${targetUser.role}) after reassigning ${pending.length} operational assignment(s)`,
    (req as any).user.name
  );

  res.json({
    success: true,
    user: cleanUser(targetUser),
    reassigned_count: pending.length,
  });
});

// ------------------- SLA CONFIG -------------------
apiRouter.get("/sla", requireAuth, (req, res) => {
  res.json(db.sla_config);
});

apiRouter.put("/sla", requireAuth, requireRoles("OWNER"), (req, res) => {
  const { config } = req.body || {};
  if (config && typeof config === "object") {
    for (const [k, v] of Object.entries(config)) {
      if (STAGE_ORDER.includes(k)) {
        db.sla_config[k] = Number(v) || 0;
      }
    }
  }
  res.json(db.sla_config);
});

// ------------------- LEAD FIELDS & EMPLOYEES -------------------
apiRouter.get("/lead-field-config", requireAuth, (req, res) => {
  res.json(db.lead_field_config);
});

apiRouter.put("/lead-field-config", requireAuth, requireRoles("OWNER"), (req, res) => {
  db.lead_field_config = req.body.fields || [];
  res.json({ status: "ok" });
});

apiRouter.get("/lead-employees", requireAuth, (req, res) => {
  res.json(db.lead_employees);
});

apiRouter.post("/lead-employees", requireAuth, (req, res) => {
  const id = `emp-${Date.now()}`;
  const emp = { id, name: req.body.name, active: true };
  db.lead_employees.push(emp);
  res.json(emp);
});

apiRouter.patch("/lead-employees/:id", requireAuth, (req, res) => {
  const emp = db.lead_employees.find((e) => e.id === req.params.id);
  if (!emp) return res.status(404).json({ detail: "Employee not found" });
  if (req.body.name !== undefined) emp.name = req.body.name;
  if (req.body.active !== undefined) emp.active = req.body.active;
  res.json(emp);
});

// ------------------- ITEMS -------------------
apiRouter.get("/items", requireAuth, (req, res) => {
  let list = Array.from(db.items.values());
  if (req.query.active_only === "true") {
    list = list.filter((i) => i.active);
  }
  res.json(list);
});

apiRouter.post("/items", requireAuth, requireRoles("OWNER"), (req, res) => {
  const { name, code, category, price, unit } = req.body;
  const id = `it-${Date.now()}`;
  const item: Item = {
    id,
    name,
    code,
    category,
    price: Number(price) || 0,
    unit: unit || "Nos",
    active: true,
    created_at: new Date().toISOString(),
  };
  db.items.set(id, item);
  res.json(item);
});

apiRouter.patch("/items/:id", requireAuth, requireRoles("OWNER"), (req, res) => {
  const item = db.items.get(req.params.id);
  if (!item) return res.status(404).json({ detail: "Item not found" });
  Object.assign(item, req.body);
  res.json(item);
});

apiRouter.delete("/items/:id", requireAuth, requireRoles("OWNER"), (req, res) => {
  db.items.delete(req.params.id);
  res.json({ status: "deleted" });
});

apiRouter.post("/items/import", requireAuth, requireRoles("OWNER"), (req, res) => {
  const rows = req.body.rows || [];
  for (const r of rows) {
    const id = `it-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    db.items.set(id, {
      id,
      name: r.name || "Unnamed Item",
      code: r.code || `IT-${Date.now()}`,
      category: r.category || "General",
      price: Number(r.price) || 0,
      unit: r.unit || "Nos",
      active: true,
      created_at: new Date().toISOString(),
    });
  }
  res.json({ imported: rows.length });
});

apiRouter.get("/items/export", requireAuth, (req, res) => {
  const list = Array.from(db.items.values());
  const csv = [
    "Code,Name,Category,Price,Unit,Active",
    ...list.map((i) => `"${i.code}","${i.name}","${i.category}",${i.price},"${i.unit}",${i.active}`),
  ].join("\n");
  res.setHeader("Content-Type", "text/csv");
  res.setHeader("Content-Disposition", 'attachment; filename="item_master.csv"');
  res.send(csv);
});

// ------------------- LEADS -------------------
apiRouter.get("/leads", requireAuth, (req, res) => {
  let list = Array.from(db.leads.values());
  const { status, search, lead_owner_id } = req.query;

  if (status) {
    list = list.filter((l) => l.status === status);
  }
  if (lead_owner_id) {
    list = list.filter((l) => l.lead_owner_id === lead_owner_id);
  }
  if (search) {
    const s = String(search).toLowerCase();
    list = list.filter(
      (l) =>
        l.name.toLowerCase().includes(s) ||
        l.phone.toLowerCase().includes(s) ||
        (l.address && l.address.toLowerCase().includes(s))
    );
  }
  // sort latest first
  list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  res.json(list);
});

apiRouter.post("/leads", requireAuth, (req, res) => {
  const user = (req as any).user as User;
  const { name, phone, email, address, source, financing_required, project_price, item_id, quantity, remarks } =
    req.body;
  if (!name || !phone) {
    return res.status(400).json({ detail: "Name and phone are required" });
  }
  const id = `lead-${Date.now()}`;
  const now = new Date().toISOString();
  const lead: Lead = {
    id,
    name: String(name).trim(),
    phone: String(phone).trim(),
    email: String(email || "").trim(),
    address: String(address || "").trim(),
    source: String(source || "").trim(),
    status: "PENDING",
    financing_required: Boolean(financing_required),
    project_price: Number(project_price) || 0,
    item_id: item_id || null,
    quantity: quantity ? Number(quantity) : null,
    remarks: remarks || "",
    created_at: now,
    updated_at: now,
    lead_owner_id: user.id,
    lead_owner_name: user.name,
  };
  db.leads.set(id, lead);
  logActivity(`New lead captured: ${lead.name}`, user.name, lead.name);
  res.json(lead);
});

apiRouter.get("/leads/:id", requireAuth, (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });

  let ecp: Ecp | null = null;
  for (const e of db.ecps.values()) {
    if (e.lead_id === lead.id) {
      ecp = e;
      break;
    }
  }
  const site_visits = Array.from(db.site_visits.values()).filter((s) => s.lead_id === lead.id);
  const documents = Array.from(db.documents.values()).filter((d) => d.lead_id === lead.id);

  res.json({ lead, ecp, site_visits, documents });
});

apiRouter.patch("/leads/:id", requireAuth, (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  Object.assign(lead, req.body);
  lead.updated_at = new Date().toISOString();
  res.json(lead);
});

apiRouter.post("/leads/:id/action", requireAuth, (req, res) => {
  const user = (req as any).user as User;
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });

  const { action, lost_reason, lost_remarks, remarks, followup_date } = req.body;
  const now = new Date().toISOString();

  if (action === "YES") {
    lead.status = "QUALIFIED";
    lead.updated_at = now;

    // Check if ECP already exists, otherwise create it
    let ecp = Array.from(db.ecps.values()).find((e) => e.lead_id === lead.id);
    if (!ecp) {
      const ecpId = `ecp-${Date.now()}`;
      ecp = {
        id: ecpId,
        lead_id: lead.id,
        project_name: lead.name,
        current_stage: "REGISTRATION_1",
        status: "ACTIVE",
        financing_required: lead.financing_required,
        project_price: lead.project_price,
        customer_name: lead.name,
        customer_phone: lead.phone,
        created_at: now,
        updated_at: now,
        stage_entered_at: now,
        lead_owner_id: lead.lead_owner_id,
        derived_status: "REGISTRATION_1",
      };
      db.ecps.set(ecpId, ecp);
      seedTasksForEcp(ecpId, lead.financing_required);
      logActivity(`Lead qualified and converted to Project: ${lead.name}`, user.name, lead.name, ecp.project_name);
    }
    return res.json({ lead, ecp });
  }

  if (action === "NO") {
    lead.status = "LOST";
    lead.lost_reason = lost_reason || "OTHER";
    lead.lost_remarks = lost_remarks || remarks || "";
    lead.updated_at = now;
    logActivity(`Lead marked lost: ${lead.name} (${lead.lost_reason})`, user.name, lead.name);
    return res.json({ lead });
  }

  if (action === "FOLLOW_UP") {
    lead.status = "FOLLOW_UP";
    lead.remarks = remarks || lead.remarks;
    lead.updated_at = now;
    logActivity(`Follow-up scheduled for ${lead.name}: ${followup_date || ""}`, user.name, lead.name);
    return res.json({ lead });
  }

  if (action === "SITE_VISIT") {
    lead.status = "SITE_VISIT";
    lead.updated_at = now;
    const svId = `sv-${Date.now()}`;
    db.site_visits.set(svId, {
      id: svId,
      lead_id: lead.id,
      lead_name: lead.name,
      lead_phone: lead.phone,
      address: lead.address,
      status: "REQUESTED",
      requested_by_name: user.name,
      remarks: remarks || "",
      created_at: now,
    });
    logActivity(`Site visit requested for ${lead.name}`, user.name, lead.name);
    return res.json({ lead });
  }

  if (action === "ESCALATION") {
    lead.status = "ESCALATED";
    lead.remarks = remarks || lead.remarks;
    lead.updated_at = now;
    logActivity(`Lead escalated to Owner: ${lead.name}`, user.name, lead.name);
    return res.json({ lead });
  }

  res.status(400).json({ detail: "Invalid action" });
});

apiRouter.post("/leads/:id/reopen", requireAuth, (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  lead.status = "PENDING";
  lead.updated_at = new Date().toISOString();
  res.json(lead);
});

apiRouter.post("/leads/:id/reassign", requireAuth, (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  const assigned = db.users.get(req.body.assigned_user);
  if (assigned) {
    lead.lead_owner_id = assigned.id;
    lead.lead_owner_name = assigned.name;
    lead.assigned_user = assigned.id;
  }
  res.json(lead);
});

apiRouter.post("/leads/:id/project-price", requireAuth, (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  lead.project_price = Number(req.body.project_price) || 0;
  const ecp = Array.from(db.ecps.values()).find((e) => e.lead_id === lead.id);
  if (ecp) ecp.project_price = lead.project_price;
  res.json(lead);
});

// Commercial changes
apiRouter.post("/leads/:id/commercial-change", requireAuth, (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  lead.pending_commercial_change = {
    ...req.body,
    status: "PENDING",
    requested_by: (req as any).user.name,
    requested_at: new Date().toISOString(),
  };
  res.json(lead);
});

apiRouter.post("/leads/:id/commercial-change/:action", requireAuth, requireRoles("OWNER"), (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  const approve = req.params.action === "approve";
  if (approve && lead.pending_commercial_change) {
    if (lead.pending_commercial_change.project_price) {
      lead.project_price = Number(lead.pending_commercial_change.project_price);
      const ecp = Array.from(db.ecps.values()).find((e) => e.lead_id === lead.id);
      if (ecp) ecp.project_price = lead.project_price;
    }
  }
  lead.pending_commercial_change = null;
  res.json(lead);
});

apiRouter.get("/commercial-changes/pending", requireAuth, (req, res) => {
  const pending = Array.from(db.leads.values()).filter(
    (l) => l.pending_commercial_change && l.pending_commercial_change.status === "PENDING"
  );
  res.json(pending);
});

// Documents upload/download for leads
apiRouter.get("/leads/:id/documents", requireAuth, (req, res) => {
  const docs = Array.from(db.documents.values()).filter((d) => d.lead_id === String(req.params.id));
  res.json(docs);
});

apiRouter.post("/leads/:id/documents", requireAuth, (upload.single("file") as any), (req, res) => {
  const lead = db.leads.get(String(req.params.id));
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  if (!req.file) return res.status(400).json({ detail: "No file uploaded" });

  const id = `doc-${Date.now()}`;
  const doc: DocumentItem = {
    id,
    lead_id: lead.id,
    doc_type: req.body.doc_type || "OTHER",
    original_filename: req.file.originalname,
    content_type: req.file.mimetype,
    size: req.file.size,
    uploaded_by_name: (req as any).user.name,
    uploaded_at: new Date().toISOString(),
    buffer: req.file.buffer,
  };
  db.documents.set(id, doc);
  logActivity(`Uploaded document ${doc.doc_type} for ${lead.name}`, (req as any).user.name, lead.name);
  const resDoc = { ...doc };
  delete resDoc.buffer;
  res.json(resDoc);
});

apiRouter.get("/leads/:leadId/documents/:docId/download", requireAuth, (req, res) => {
  const doc = db.documents.get(req.params.docId);
  if (!doc) return res.status(404).json({ detail: "Document not found" });
  res.setHeader("Content-Type", doc.content_type || "application/octet-stream");
  res.setHeader("Content-Disposition", `inline; filename="${doc.original_filename}"`);
  res.send(doc.buffer || Buffer.from(""));
});

apiRouter.get("/leads/:id/quotation", requireAuth, (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  const text = `QUOTATION FOR SOLAR ROOFTOP INSTALLATION\nClient: ${lead.name}\nPhone: ${lead.phone}\nAddress: ${lead.address}\nTotal Project Price: INR ${lead.project_price.toLocaleString("en-IN")}\nDate: ${new Date().toLocaleDateString()}\nStatus: APPROVED`;
  res.setHeader("Content-Type", "text/plain");
  res.setHeader("Content-Disposition", `attachment; filename="Quotation_${lead.name.replace(/\s+/g, "_")}.txt"`);
  res.send(text);
});

// ------------------- ECPS (PROJECTS) -------------------
apiRouter.get("/ecps", requireAuth, (req, res) => {
  let list = Array.from(db.ecps.values());
  const { stage, view, search } = req.query;

  if (stage) list = list.filter((e) => e.current_stage === stage);
  if (view === "PAYMENT_BLOCKED") list = list.filter((e) => e.derived_status === "PAYMENT_BLOCKED");
  if (view === "DELAYED") list = list.filter((e) => e.delayed);
  if (view === "COMPLETED") list = list.filter((e) => e.status === "COMPLETED");

  if (search) {
    const s = String(search).toLowerCase();
    list = list.filter(
      (e) =>
        e.project_name.toLowerCase().includes(s) ||
        (e.customer_name && e.customer_name.toLowerCase().includes(s))
    );
  }
  list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  res.json(list);
});

apiRouter.get("/ecps/:id", requireAuth, (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });

  const tasks = Array.from(db.tasks.values()).filter((t) => t.ecp_id === ecp.id);
  const payments = Array.from(db.payments.values()).filter((p) => p.ecp_id === ecp.id);
  const challan = db.challans.get(ecp.id) || null;
  const site_visits = Array.from(db.site_visits.values()).filter((s) => s.lead_id === ecp.lead_id);
  const documents = Array.from(db.documents.values()).filter((d) => d.lead_id === ecp.lead_id);
  const complaints = Array.from(db.complaints.values()).filter((c) => c.lead_id === ecp.lead_id);

  res.json({ ecp, tasks, payments, challan, site_visits, documents, complaints });
});

apiRouter.post("/ecps/:id/tasks/:taskId/complete", requireAuth, (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });
  const task = db.tasks.get(req.params.taskId);
  if (!task || task.ecp_id !== ecp.id) return res.status(404).json({ detail: "Task not found" });

  const user = (req as any).user as User;
  task.completed = true;
  task.completed_at = new Date().toISOString();
  task.completed_by = user.id;
  task.completed_by_name = user.name;

  logActivity(`Completed task "${task.name}" for ${ecp.project_name}`, user.name, "", ecp.project_name);

  // Check if all applicable tasks for current stage are complete
  const stageTasks = Array.from(db.tasks.values()).filter(
    (t) => t.ecp_id === ecp.id && t.stage === ecp.current_stage && t.applicable
  );
  const allComplete = stageTasks.every((t) => t.completed);

  if (allComplete) {
    const currentIdx = STAGE_ORDER.indexOf(ecp.current_stage);
    if (currentIdx !== -1 && currentIdx < STAGE_ORDER.length - 1) {
      const nextStage = STAGE_ORDER[currentIdx + 1];
      ecp.current_stage = nextStage;
      ecp.stage_entered_at = new Date().toISOString();
      ecp.derived_status = nextStage;
      if (nextStage === "INSTALLATION") {
        ecp.install_status = "AWAITING_ASSIGNMENT";
      }
      logActivity(`Project ${ecp.project_name} transitioned to stage ${nextStage}`, "System", "", ecp.project_name);
    } else if (currentIdx === STAGE_ORDER.length - 1) {
      ecp.status = "COMPLETED";
      logActivity(`Project ${ecp.project_name} successfully completed!`, "System", "", ecp.project_name);
    }
  }

  res.json({ task, ecp });
});

apiRouter.post("/ecps/:id/start-dispatch", requireAuth, requireRoles("DISPATCH", "OWNER"), (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });
  ecp.derived_status = "DISPATCH_IN_PROCESS";
  logActivity(`Dispatch started for ${ecp.project_name}`, (req as any).user.name, "", ecp.project_name);
  res.json(ecp);
});

apiRouter.get("/ecps/:id/challan", requireAuth, (req, res) => {
  const challan = db.challans.get(req.params.id);
  if (!challan) {
    // return default draft challan
    return res.json({
      ecp_id: req.params.id,
      challan_no: `DC-${Date.now().toString().slice(-6)}`,
      items: [],
      dispatch_date: new Date().toISOString().slice(0, 10),
      status: "DRAFT",
    });
  }
  res.json(challan);
});

apiRouter.post("/ecps/:id/challan", requireAuth, (req, res) => {
  const { items, dispatch_date, vehicle_no, driver_contact } = req.body;
  const challan = {
    ecp_id: req.params.id,
    challan_no: req.body.challan_no || `DC-${Date.now().toString().slice(-6)}`,
    items: items || [],
    dispatch_date: dispatch_date || new Date().toISOString().slice(0, 10),
    status: "DRAFT" as const,
    vehicle_no,
    driver_contact,
  };
  db.challans.set(req.params.id, challan);
  res.json(challan);
});

apiRouter.post("/ecps/:id/challan/finalize", requireAuth, (req, res) => {
  const challan = db.challans.get(req.params.id);
  if (challan) {
    challan.status = "FINALIZED";
  }
  res.json(challan || { status: "FINALIZED" });
});

apiRouter.post("/ecps/:id/assign-installation", requireAuth, (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });
  const assigned = db.users.get(req.body.assigned_user);
  if (assigned) {
    ecp.responsible_user = assigned.id;
    ecp.install_status = "READY_TO_INSTALL";
    logActivity(`Assigned installation of ${ecp.project_name} to ${assigned.name}`, (req as any).user.name);
  }
  res.json(ecp);
});

apiRouter.post("/ecps/:id/installation", requireAuth, (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });
  const { action } = req.body;
  if (action === "start") {
    ecp.install_status = "IN_PROCESS";
  } else if (action === "complete") {
    ecp.install_status = "PENDING_ACCEPTANCE";
  }
  res.json(ecp);
});

apiRouter.post("/ecps/:id/installation/:action", requireAuth, (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });
  const action = req.params.action;
  if (action === "accept") {
    ecp.install_status = "COMPLETED";
    // Mark installation stage tasks complete and move to NET_METERING
    for (const t of db.tasks.values()) {
      if (t.ecp_id === ecp.id && t.stage === "INSTALLATION") {
        t.completed = true;
      }
    }
    ecp.current_stage = "NET_METERING";
    ecp.stage_entered_at = new Date().toISOString();
  } else if (action === "reject") {
    ecp.install_status = "IN_PROCESS";
  }
  res.json(ecp);
});

apiRouter.get("/ecps/:id/install-photos", requireAuth, (req, res) => {
  const photos = Array.from(db.install_photos.values()).filter((p) => p.ecp_id === String(req.params.id));
  res.json({ photos });
});

apiRouter.post("/ecps/:id/install-photos", requireAuth, (upload.single("file") as any), (req, res) => {
  const id = `iphot-${Date.now()}`;
  const photo = {
    id,
    ecp_id: String(req.params.id),
    photo_type: req.body.photo_type || "GENERAL",
    uploaded_by_name: (req as any).user.name,
    uploaded_at: new Date().toISOString(),
  };
  db.install_photos.set(id, photo);
  res.json(photo);
});

apiRouter.post("/ecps/:id/financing", requireAuth, (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });
  ecp.financing_required = Boolean(req.body.financing_required);
  // Update task applicability
  for (const t of db.tasks.values()) {
    if (t.ecp_id === ecp.id && (t.name.includes("Loan") || t.name.includes("Bank"))) {
      t.applicable = ecp.financing_required;
    }
  }
  res.json(ecp);
});

apiRouter.post("/ecps/:id/close", requireAuth, (req, res) => {
  const ecp = db.ecps.get(req.params.id);
  if (!ecp) return res.status(404).json({ detail: "ECP not found" });
  ecp.status = "CLOSED";
  ecp.closed_reason = req.body.reason;
  ecp.closed_remarks = req.body.remarks;
  res.json(ecp);
});

// ------------------- PAYMENTS -------------------
apiRouter.get("/payments", requireAuth, (req, res) => {
  const list = Array.from(db.payments.values());
  res.json(list);
});

apiRouter.get("/payments/monitor", requireAuth, (req, res) => {
  const ecps = Array.from(db.ecps.values()).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  const payments = Array.from(db.payments.values());

  const byEcp = new Map<string, Payment[]>();
  for (const p of payments) {
    const list = byEcp.get(p.ecp_id) || [];
    list.push(p);
    byEcp.set(p.ecp_id, list);
  }

  const rows = ecps.map((e) => {
    const ps = byEcp.get(e.id) || [];
    const price = Number(e.project_price) || 0;
    const firstConf = ps
      .filter((p) => p.type === "FIRST" && p.status === "CONFIRMED")
      .reduce((sum, p) => sum + p.amount, 0);
    const subConf = ps
      .filter((p) => (p.type === "ADDITIONAL" || p.type === "FINAL") && p.status === "CONFIRMED")
      .reduce((sum, p) => sum + p.amount, 0);
    const finalConf = ps
      .filter((p) => p.type === "FINAL" && p.status === "CONFIRMED")
      .reduce((sum, p) => sum + p.amount, 0);
    const totalConf = firstConf + subConf;
    const receivable = Math.max(price - totalConf, 0);
    const firstConfirmed = ps.some((p) => p.type === "FIRST" && p.status === "CONFIRMED");

    const lead = db.leads.get(e.lead_id);
    const leadCreatorName = lead?.lead_owner_name || "";

    return {
      ecp_id: e.id,
      lead_name: e.project_name || e.customer_name || "Untitled Project",
      customer_phone: e.customer_phone || lead?.phone || "",
      lead_creator_name: leadCreatorName,
      stage: e.current_stage,
      stage_label: STAGE_LABELS[e.current_stage] || e.current_stage,
      status: e.status,
      payments: ps,
      project_price: price,
      first_confirmed_amount: firstConf,
      subsequent_confirmed_amount: subConf,
      final_confirmed_amount: finalConf,
      total_received: totalConf,
      total_receivable: receivable,
      first_payment_confirmed: firstConfirmed,
    };
  });

  res.json(rows);
});

apiRouter.post("/payments", requireAuth, (req, res) => {
  const user = (req as any).user as User;
  const { ecp_id, type, amount, date, status, reference_no, notes } = req.body;
  const id = `pay-${Date.now()}`;
  const payment: Payment = {
    id,
    ecp_id,
    type: type || "FIRST",
    amount: Number(amount) || 0,
    date: date || new Date().toISOString().slice(0, 10),
    status: status || "CONFIRMED",
    reference_no: reference_no || "",
    notes: notes || "",
    created_at: new Date().toISOString(),
    created_by_name: user.name,
  };
  db.payments.set(id, payment);

  // If first payment is confirmed, unblock payment status on ECP
  const ecp = db.ecps.get(ecp_id);
  if (ecp) {
    if (payment.status === "CONFIRMED" && payment.type === "FIRST") {
      ecp.derived_status = ecp.current_stage;
      ecp.delayed = false;
    }
    logActivity(`Recorded payment of INR ${payment.amount.toLocaleString("en-IN")} (${payment.type}) for ${ecp.project_name}`, user.name, "", ecp.project_name);
  }
  res.json(payment);
});

apiRouter.patch("/payments/:id", requireAuth, (req, res) => {
  const payment = db.payments.get(req.params.id);
  if (!payment) return res.status(404).json({ detail: "Payment not found" });
  Object.assign(payment, req.body);
  res.json(payment);
});

// ------------------- SITE VISITS -------------------
apiRouter.get("/site-visits", requireAuth, (req, res) => {
  const list = Array.from(db.site_visits.values());
  res.json(list);
});

apiRouter.post("/site-visits/:id/assign", requireAuth, (req, res) => {
  const sv = db.site_visits.get(req.params.id);
  if (!sv) return res.status(404).json({ detail: "Site visit not found" });
  const assigned = db.users.get(req.body.assigned_user);
  if (assigned) {
    sv.assigned_user = assigned.id;
    sv.assigned_user_name = assigned.name;
    sv.visit_date = req.body.visit_date || sv.visit_date;
    sv.status = "ASSIGNED";
  }
  res.json(sv);
});

apiRouter.post("/site-visits/:id/complete", requireAuth, (req, res) => {
  const sv = db.site_visits.get(req.params.id);
  if (!sv) return res.status(404).json({ detail: "Site visit not found" });
  sv.status = "DONE";
  sv.completed_at = new Date().toISOString();
  sv.report = req.body.report || "";
  res.json(sv);
});

apiRouter.get("/site-visits/:id/photos", requireAuth, (req, res) => {
  const photos = Array.from(db.site_visit_photos.values()).filter((p) => p.sv_id === String(req.params.id));
  res.json({ photos });
});

apiRouter.post("/site-visits/:id/photos", requireAuth, (upload.single("file") as any), (req, res) => {
  const id = `svphot-${Date.now()}`;
  const photo = {
    id,
    sv_id: String(req.params.id),
    uploaded_by_name: (req as any).user.name,
    uploaded_at: new Date().toISOString(),
  };
  db.site_visit_photos.set(id, photo);
  res.json(photo);
});

// ------------------- COMPLAINTS -------------------
apiRouter.get("/complaints", requireAuth, (req, res) => {
  const list = Array.from(db.complaints.values());
  res.json(list);
});

apiRouter.post("/complaints", requireAuth, (req, res) => {
  const { customer_name, customer_phone, category, priority, assigned_team, subject, description, lead_id } =
    req.body;
  const id = `cmp-${Date.now()}`;
  const ticket_no = `CMP-${new Date().getFullYear()}-${String(db.complaints.size + 1).padStart(3, "0")}`;
  const comp: Complaint = {
    id,
    ticket_no,
    lead_id,
    customer_name: customer_name || "",
    customer_phone: customer_phone || "",
    category: category || "General",
    priority: priority || "MEDIUM",
    status: "REGISTERED",
    assigned_team: assigned_team || "INSTALLATION",
    subject: subject || "Customer complaint",
    description: description || "",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  db.complaints.set(id, comp);
  logActivity(`Registered new complaint: ${ticket_no}`, (req as any).user.name);
  res.json(comp);
});

apiRouter.get("/complaints/:id", requireAuth, (req, res) => {
  const complaint = db.complaints.get(req.params.id);
  if (!complaint) return res.status(404).json({ detail: "Complaint not found" });
  res.json({ complaint, attachments: [], comments: [] });
});

apiRouter.post("/complaints/:id/status", requireAuth, (req, res) => {
  const complaint = db.complaints.get(req.params.id);
  if (!complaint) return res.status(404).json({ detail: "Complaint not found" });
  complaint.status = req.body.status;
  complaint.updated_at = new Date().toISOString();
  if (req.body.status === "RESOLVED" || req.body.status === "CLOSED") {
    complaint.resolved_at = new Date().toISOString();
  }
  res.json(complaint);
});

apiRouter.post("/complaints/:id/assign", requireAuth, (req, res) => {
  const complaint = db.complaints.get(req.params.id);
  if (!complaint) return res.status(404).json({ detail: "Complaint not found" });
  const user = db.users.get(req.body.assigned_user);
  if (user) {
    complaint.assigned_user = user.id;
    complaint.assigned_user_name = user.name;
    complaint.status = "ASSIGNED";
  }
  res.json(complaint);
});

apiRouter.get("/complaint-categories", requireAuth, (req, res) => {
  res.json([
    { id: "cat-1", name: "Inverter Tripping / Generation Issue" },
    { id: "cat-2", name: "Rooftop Structure / Water Leakage" },
    { id: "cat-3", name: "Net Metering Billing Discrepancy" },
    { id: "cat-4", name: "Wiring / Earthing Voltage Warning" },
    { id: "cat-5", name: "General Inquiries" },
  ]);
});

// ------------------- ESCALATIONS -------------------
apiRouter.get("/escalations", requireAuth, (req, res) => {
  const escalatedLeads = Array.from(db.leads.values()).filter((l) => l.status === "ESCALATED");
  res.json(escalatedLeads);
});

apiRouter.post("/escalations/:id/return", requireAuth, requireRoles("OWNER"), (req, res) => {
  const lead = db.leads.get(req.params.id);
  if (!lead) return res.status(404).json({ detail: "Lead not found" });
  lead.status = "FOLLOW_UP";
  lead.remarks = `Owner returned: ${req.body.owner_remarks || ""}`;
  lead.updated_at = new Date().toISOString();
  res.json(lead);
});

// ------------------- DASHBOARD -------------------
apiRouter.get("/dashboard", requireAuth, (req, res) => {
  const user = (req as any).user as User;
  const leads = Array.from(db.leads.values());
  const ecps = Array.from(db.ecps.values());
  const payments = Array.from(db.payments.values());
  const site_visits = Array.from(db.site_visits.values());
  const complaints = Array.from(db.complaints.values());

  const activeEcps = ecps.filter((e) => e.status === "ACTIVE");

  const stageCounts: Record<string, number> = {};
  for (const s of STAGE_ORDER) {
    stageCounts[s] = activeEcps.filter((e) => e.current_stage === s).length;
  }

  const response: any = {
    role: user.role,
    role_label: user.role,
    ecp: {
      ACTIVE: activeEcps.length,
      REGISTRATION_1: stageCounts["REGISTRATION_1"] || 0,
      ACCOUNTS_1: stageCounts["ACCOUNTS_1"] || 0,
      PAYMENT_BLOCKED: activeEcps.filter((e) => e.derived_status === "PAYMENT_BLOCKED").length,
      READY_FOR_DISPATCH: activeEcps.filter((e) => e.derived_status === "READY_FOR_DISPATCH").length,
      DISPATCH_IN_PROCESS: activeEcps.filter((e) => e.derived_status === "DISPATCH_IN_PROCESS").length,
      READY_TO_INSTALL: activeEcps.filter((e) => e.install_status === "READY_TO_INSTALL").length,
      INSTALLATION_IN_PROCESS: activeEcps.filter((e) => e.install_status === "IN_PROCESS").length,
      NET_METERING: stageCounts["NET_METERING"] || 0,
      REGISTRATION_2: stageCounts["REGISTRATION_2"] || 0,
      ACCOUNTS_2: stageCounts["ACCOUNTS_2"] || 0,
      DELAYED: activeEcps.filter((e) => e.delayed).length,
      COMPLETED: ecps.filter((e) => e.status === "COMPLETED").length,
      CLOSED: ecps.filter((e) => e.status === "CLOSED").length,
      PENDING_DOCUMENTS: 0,
    },
    leads: {
      PENDING: leads.filter((l) => l.status === "PENDING").length,
      FOLLOW_UP: leads.filter((l) => l.status === "FOLLOW_UP").length,
      SITE_VISIT: leads.filter((l) => l.status === "SITE_VISIT").length,
      ESCALATED: leads.filter((l) => l.status === "ESCALATED").length,
      QUALIFIED: leads.filter((l) => l.status === "QUALIFIED").length,
      LOST: leads.filter((l) => l.status === "LOST").length,
    },
    payments: {
      FIRST_PENDING: payments.filter((p) => p.type === "FIRST" && p.status === "PENDING").length,
      FIRST_CONFIRMED: payments.filter((p) => p.type === "FIRST" && p.status === "CONFIRMED").length,
      FINAL_PENDING: payments.filter((p) => p.type === "FINAL" && p.status === "PENDING").length,
      FINAL_CONFIRMED: payments.filter((p) => p.type === "FINAL" && p.status === "CONFIRMED").length,
      ADDITIONAL: payments.filter((p) => p.type === "ADDITIONAL").length,
    },
    alerts: {
      delayed_count: activeEcps.filter((e) => e.delayed).length,
      unassigned_visits: site_visits.filter((s) => s.status === "REQUESTED").length,
      critical_complaints: complaints.filter((c) => c.priority === "CRITICAL" && c.status !== "CLOSED").length,
      pending_commercial: leads.filter((l) => l.pending_commercial_change).length,
    },
    pending_commercial: leads.filter((l) => l.pending_commercial_change).length,
    trend: [
      { date: "Day 1", qualified: 2, leads: 5 },
      { date: "Day 2", qualified: 3, leads: 8 },
      { date: "Day 3", qualified: 4, leads: 11 },
      { date: "Day 4", qualified: 6, leads: 14 },
      { date: "Day 5", qualified: 8, leads: 18 },
    ],
  };

  // Role-specific additions
  if (user.role === "MANAGER") {
    response.site_visits_to_assign = site_visits.filter((s) => s.status === "REQUESTED").length;
    response.site_visits_today = site_visits.filter((s) => s.status === "ASSIGNED").length;
    response.site_visits_upcoming = 0;
    response.awaiting_install_assignment = activeEcps.filter((e) => e.install_status === "AWAITING_ASSIGNMENT").length;
    response.delayed = activeEcps.filter((e) => e.delayed).length;
    response.active_leads = leads.filter((l) => ["PENDING", "FOLLOW_UP", "SITE_VISIT"].includes(l.status)).length;
    response.active_ecps = activeEcps.length;
  } else if (user.role === "LEAD") {
    response.action_required = leads.filter((l) => l.status === "PENDING").length;
    response.followups_today = leads.filter((l) => l.status === "FOLLOW_UP").length;
    response.waiting_site_visit = leads.filter((l) => l.status === "SITE_VISIT").length;
    response.escalated = leads.filter((l) => l.status === "ESCALATED").length;
    response.qualified = leads.filter((l) => l.status === "QUALIFIED").length;
    response.lost = leads.filter((l) => l.status === "LOST").length;
    response.pending_documents = 0;
  } else if (user.role === "ACCOUNTS") {
    response.first_payment_pending_count = payments.filter((p) => p.type === "FIRST" && p.status === "PENDING").length;
    response.subsequent_followup_count = activeEcps.length;
    response.subsequent_amount_pending = 340000;
    response.total_receivable = 790000;
  } else if (user.role === "DISPATCH") {
    response.payment_blocked = activeEcps.filter((e) => e.derived_status === "PAYMENT_BLOCKED").length;
    response.ready_for_dispatch = activeEcps.filter((e) => e.current_stage === "DISPATCH").length;
    response.dispatch_in_process = activeEcps.filter((e) => e.derived_status === "DISPATCH_IN_PROCESS").length;
    response.completed = ecps.filter((e) => ["INSTALLATION", "NET_METERING", "REGISTRATION_2", "ACCOUNTS_2", "COMPLETED"].includes(e.current_stage)).length;
  } else if (user.role === "INSTALLATION") {
    response.sv_upcoming = site_visits.filter((s) => s.assigned_user === user.id).length;
    response.sv_today = site_visits.filter((s) => s.assigned_user === user.id).length;
    response.sv_assigned = site_visits.filter((s) => s.assigned_user === user.id).length;
    response.sv_completed = site_visits.filter((s) => s.status === "DONE").length;
    response.ready_to_install = activeEcps.filter((e) => e.responsible_user === user.id && e.install_status === "READY_TO_INSTALL").length;
    response.installation_in_process = activeEcps.filter((e) => e.responsible_user === user.id && e.install_status === "IN_PROCESS").length;
    response.net_metering = activeEcps.filter((e) => e.current_stage === "NET_METERING").length;
  } else if (user.role === "REGISTRATION") {
    response.registration_1 = stageCounts["REGISTRATION_1"] || 0;
    response.registration_2 = stageCounts["REGISTRATION_2"] || 0;
    response.pending = (stageCounts["REGISTRATION_1"] || 0) + (stageCounts["REGISTRATION_2"] || 0);
    response.pending_documents = 0;
  }

  res.json(response);
});

// ------------------- ACTIVITIES -------------------
apiRouter.get("/activities", requireAuth, (req, res) => {
  res.json(db.activities.slice(0, 50));
});

// ------------------- EXPORT PROJECTS -------------------
apiRouter.get("/export/projects", requireAuth, (req, res) => {
  const ecps = Array.from(db.ecps.values());
  const inclMoney = req.query.include_money === "true";
  const header = inclMoney
    ? "ID,Project Name,Customer,Phone,Current Stage,Status,Price,Financing"
    : "ID,Project Name,Customer,Phone,Current Stage,Status,Financing";
  const rows = ecps.map((e) => {
    return inclMoney
      ? `"${e.id}","${e.project_name}","${e.customer_name}","${e.customer_phone}","${e.current_stage}","${e.status}",${e.project_price},${e.financing_required}`
      : `"${e.id}","${e.project_name}","${e.customer_name}","${e.customer_phone}","${e.current_stage}","${e.status}",${e.financing_required}`;
  });
  const csv = [header, ...rows].join("\n");
  res.setHeader("Content-Type", "text/csv");
  res.setHeader("Content-Disposition", 'attachment; filename="solar_projects.csv"');
  res.send(csv);
});
