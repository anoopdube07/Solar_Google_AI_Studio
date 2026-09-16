"""Business workflow constants for ECP Project Management & Lead Tracking (Phase 1 spec)."""

# ---- Roles / Teams (V1: one user = one role = one team) ----
ROLES = ["OWNER", "MANAGER", "LEAD", "REGISTRATION", "ACCOUNTS", "DISPATCH", "INSTALLATION",
         "INSTALLATION_MANAGER", "INSTALLATION_MEMBER", "COMPLAINT"]

ROLE_LABELS = {
    "OWNER": "Owner",
    "MANAGER": "Process Owner / Manager",
    "LEAD": "Lead Team",
    "REGISTRATION": "Registration Team",
    "ACCOUNTS": "Accounts Team",
    "DISPATCH": "Dispatch Team",
    "INSTALLATION": "Installation Team",
    "INSTALLATION_MANAGER": "Installation Team Manager",
    "INSTALLATION_MEMBER": "Installation Team Member",
    "COMPLAINT": "Complaint Registration Team",
}

# ---- ECP stages (ordered) ----
STAGE_ORDER = [
    "REGISTRATION_1",
    "ACCOUNTS_1",
    "DISPATCH",
    "INSTALLATION",
    "NET_METERING",
    "REGISTRATION_2",
    "ACCOUNTS_2",
]

STAGE_LABELS = {
    "PENDING_DOCUMENTS": "Pending Documents",
    "REGISTRATION_1": "Registration 1",
    "ACCOUNTS_1": "Accounts 1",
    "DISPATCH": "Dispatch",
    "INSTALLATION": "Installation",
    "NET_METERING": "Net Metering",
    "REGISTRATION_2": "Registration 2",
    "ACCOUNTS_2": "Accounts 2",
    "COMPLETED": "Successfully Completed",
    "CLOSED": "Closed / Cancelled",
}

# Team responsible for each stage
STAGE_TEAM = {
    "PENDING_DOCUMENTS": "LEAD",
    "REGISTRATION_1": "REGISTRATION",
    "ACCOUNTS_1": "ACCOUNTS",
    "DISPATCH": "DISPATCH",
    "INSTALLATION": "INSTALLATION",
    "NET_METERING": "REGISTRATION",
    "REGISTRATION_2": "REGISTRATION",
    "ACCOUNTS_2": "ACCOUNTS",
}

# Mandatory operational tasks per stage (exact spec names)
REG1_BASE_TASKS = ["Consumer Request", "CVA Print & Sign", "Feasibility Report Upload"]
REG1_FINANCING_TASKS = ["Loan Documentation", "Loan Filing", "Bank Submission"]

# Task specs per stage: (name, team, financing_only, requires_task_name)
STAGE_TASK_SPECS = {
    "REGISTRATION_1": [
        ("Consumer Request", "REGISTRATION", False, None),
        ("CVA Print & Sign", "REGISTRATION", False, None),
        ("Feasibility Report Upload", "REGISTRATION", False, None),
        ("Loan Documentation", "REGISTRATION", True, None),
        ("Loan Filing", "REGISTRATION", True, None),
        ("Bank Submission", "REGISTRATION", True, None),
    ],
    "ACCOUNTS_1": [("Advance Verification", "ACCOUNTS", False, None)],
    "DISPATCH": [
        ("Delivery Challan", "DISPATCH", False, None),
        ("Material Dispatch Confirmation", "DISPATCH", False, "Delivery Challan"),
        ("Dispatch Completed", "DISPATCH", False, "Material Dispatch Confirmation"),
    ],
    "NET_METERING": [
        ("Upload Installation Photos to CSPDCL Portal", "REGISTRATION", False, None),
        ("DCR Issuance", "REGISTRATION", False, "Upload Installation Photos to CSPDCL Portal"),
        ("Consumer Approval & Submit", "REGISTRATION", False, "DCR Issuance"),
        ("Request Net Metering from CSPDCL", "REGISTRATION", False, "Consumer Approval & Submit"),
        ("Close Net Metering", "INSTALLATION_MEMBER", False, "Request Net Metering from CSPDCL"),
    ],
    "REGISTRATION_2": [
        ("Asset Creation", "REGISTRATION", False, None),
        ("Completion Certificate", "REGISTRATION", False, "Asset Creation"),
        ("Bank Submission 2nd", "REGISTRATION", True, None),
    ],
    "ACCOUNTS_2": [("Final Payment Follow-up", "ACCOUNTS", False, None)],
}

# Installation mandatory photos
INSTALL_PHOTO_TYPES = ["INVERTER_SERIAL", "INVERTER_WITH_CUSTOMER", "PANEL_WITH_CUSTOMER",
                       "LIGHTNING_ARRESTER", "EARTHING_PIT"]
INSTALL_PHOTO_LABELS = {
    "INVERTER_SERIAL": "Inverter Serial Number",
    "INVERTER_WITH_CUSTOMER": "Inverter alongside Customer",
    "PANEL_WITH_CUSTOMER": "Solar Panel alongside Customer",
    "LIGHTNING_ARRESTER": "Lightning Arrester",
    "EARTHING_PIT": "Earthing Pit",
}
PHOTO_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

# Complaint constants
COMPLAINT_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
COMPLAINT_STATUSES = ["REGISTERED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"]
COMPLAINT_TEAMS = ["LEAD", "REGISTRATION", "ACCOUNTS", "DISPATCH", "INSTALLATION"]

INSTALL_MEMBER_ROLES = {"INSTALLATION", "INSTALLATION_MEMBER"}
INSTALL_MANAGER_ROLES = {"INSTALLATION_MANAGER", "MANAGER", "OWNER"}

LEAD_ACTIONS = ["YES", "NO", "FOLLOW_UP", "SITE_VISIT", "ESCALATION"]

# ---- Phase 3: Documents ----
# Single required document types
DOC_REQUIRED_SINGLE = ["PAN", "AADHAAR", "ELECTRICITY_BILL"]
# Bank proof group — at least one of these is required
DOC_BANK_GROUP = ["BANK_PASSBOOK", "BANK_STATEMENT", "CANCELLED_CHEQUE"]
# Finance group — at least one required ONLY when financing_required is True
DOC_FINANCE_GROUP = ["PROPERTY_PAPER", "TAX_RECEIPT"]

DOC_TYPES = DOC_REQUIRED_SINGLE + DOC_BANK_GROUP + DOC_FINANCE_GROUP

DOC_LABELS = {
    "PAN": "PAN Card",
    "AADHAAR": "Aadhaar Card",
    "ELECTRICITY_BILL": "Electricity Bill",
    "BANK_PASSBOOK": "Bank Passbook Photo",
    "BANK_STATEMENT": "3-Month Bank Statement",
    "CANCELLED_CHEQUE": "Cancelled Cheque",
    "PROPERTY_PAPER": "Property Paper",
    "TAX_RECEIPT": "Tax Receipt",
}

DOC_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}
DOC_ALLOWED_EXT = {"jpg", "jpeg", "png", "pdf"}
DOC_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def documents_complete(current_types: set, financing: bool) -> bool:
    if not all(t in current_types for t in DOC_REQUIRED_SINGLE):
        return False
    if not any(t in current_types for t in DOC_BANK_GROUP):
        return False
    if financing and not any(t in current_types for t in DOC_FINANCE_GROUP):
        return False
    return True


LOST_REASONS = ["PRICE", "COMPETITOR", "NOT_INTERESTED", "UNREACHABLE", "OTHER"]
CLOSURE_REASONS = ["CUSTOMER_CANCELLED", "DUPLICATE", "NOT_FEASIBLE", "OTHER"]


def next_stage(stage: str):
    if stage not in STAGE_ORDER:
        return None
    idx = STAGE_ORDER.index(stage)
    if idx + 1 < len(STAGE_ORDER):
        return STAGE_ORDER[idx + 1]
    return "COMPLETED"
