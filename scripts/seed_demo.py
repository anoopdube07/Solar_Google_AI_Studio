import requests, sys
B = "http://localhost:8001/api"

def login(u, p):
    r = requests.post(f"{B}/auth/login", json={"username": u, "password": p})
    r.raise_for_status()
    return r.json()["token"]

def H(t): return {"Authorization": f"Bearer {t}"}

def check(r, ctx):
    if r.status_code >= 400:
        print("FAIL", ctx, r.status_code, r.text[:200]); sys.exit(1)
    return r.json()

owner = login("anoopdube07@gmail.com", "Owner@123")
lead = login("lead", "Lead@123")
manager = login("manager", "Manager@123")
reg = login("registration", "Reg@123")
acct = login("accounts", "Acct@123")
disp = login("dispatch", "Disp@123")
inst = login("installation", "Install@123")

def mk_lead(name, phone, price, fin=False):
    return check(requests.post(f"{B}/leads", headers=H(lead), json={"name": name, "phone": phone, "financing_required": fin, "project_price": price}), "create lead")

def complete_stage_tasks(ecp_id, stage, tok):
    det = check(requests.get(f"{B}/ecps/{ecp_id}", headers=H(tok)), "get ecp")
    for t in det["tasks"]:
        if t["stage"] == stage and t["applicable"] and not t["completed"]:
            check(requests.post(f"{B}/ecps/{ecp_id}/tasks/{t['id']}/complete", headers=H(tok)), f"{stage} task")

# 1) Project advanced to Net Metering via full Dispatch->Manager->Installation flow
l1 = mk_lead("Ramesh Solar Villa", "9800000001", 1000000, fin=True)
check(requests.post(f"{B}/leads/{l1['id']}/action", headers=H(lead), json={"action": "YES"}), "qualify l1")
ecp1 = check(requests.get(f"{B}/leads/{l1['id']}", headers=H(lead)), "b1")["ecp"]["id"]
complete_stage_tasks(ecp1, "REGISTRATION_1", reg)
complete_stage_tasks(ecp1, "ACCOUNTS_1", acct)
check(requests.post(f"{B}/payments", headers=H(acct), json={"ecp_id": ecp1, "type": "FIRST", "amount": 300000, "date": "2026-08-01", "status": "CONFIRMED"}), "first pay")
check(requests.post(f"{B}/payments", headers=H(acct), json={"ecp_id": ecp1, "type": "ADDITIONAL", "amount": 200000, "date": "2026-08-15", "status": "CONFIRMED"}), "sub pay")
check(requests.post(f"{B}/ecps/{ecp1}/start-dispatch", headers=H(disp)), "start dispatch")
complete_stage_tasks(ecp1, "DISPATCH", disp)
# now INSTALLATION awaiting assignment -> manager assigns
installers = check(requests.get(f"{B}/users/team/INSTALLATION", headers=H(manager)), "installers")
det = check(requests.get(f"{B}/ecps/{ecp1}", headers=H(manager)), "ecp1 await")
assert det["ecp"]["install_status"] == "AWAITING_ASSIGNMENT", det["ecp"]["install_status"]
inst_id = [u for u in installers if u["username"] == "installation"][0]["id"]
check(requests.post(f"{B}/ecps/{ecp1}/assign-installation", headers=H(manager), json={"assigned_user": inst_id}), "assign install")
check(requests.post(f"{B}/ecps/{ecp1}/installation", headers=H(inst), json={"action": "start"}), "inst start")
check(requests.post(f"{B}/ecps/{ecp1}/installation", headers=H(inst), json={"action": "complete"}), "inst complete")
print("ECP1 stage:", check(requests.get(f"{B}/ecps/{ecp1}", headers=H(reg)), "ecp1 final")["ecp"]["current_stage"])

# 2) Payment-blocked dispatch project
l2 = mk_lead("Sunita Rooftop", "9800000002", 800000)
check(requests.post(f"{B}/leads/{l2['id']}/action", headers=H(lead), json={"action": "YES"}), "qualify l2")
ecp2 = check(requests.get(f"{B}/leads/{l2['id']}", headers=H(lead)), "b2")["ecp"]["id"]
complete_stage_tasks(ecp2, "REGISTRATION_1", reg)
complete_stage_tasks(ecp2, "ACCOUNTS_1", acct)
check(requests.post(f"{B}/payments", headers=H(acct), json={"ecp_id": ecp2, "type": "FIRST", "amount": 240000, "date": "2026-08-20", "status": "PENDING"}), "first pending")

# 3) Awaiting installation assignment (manager queue) project
l3b = mk_lead("Skyline Offices", "9800000033", 1500000)
check(requests.post(f"{B}/leads/{l3b['id']}/action", headers=H(lead), json={"action": "YES"}), "qualify l3b")
ecp3 = check(requests.get(f"{B}/leads/{l3b['id']}", headers=H(lead)), "b3")["ecp"]["id"]
complete_stage_tasks(ecp3, "REGISTRATION_1", reg)
complete_stage_tasks(ecp3, "ACCOUNTS_1", acct)
check(requests.post(f"{B}/payments", headers=H(acct), json={"ecp_id": ecp3, "type": "FIRST", "amount": 450000, "date": "2026-08-22", "status": "CONFIRMED"}), "first conf")
check(requests.post(f"{B}/ecps/{ecp3}/start-dispatch", headers=H(disp)), "start dispatch3")
complete_stage_tasks(ecp3, "DISPATCH", disp)  # now awaiting install assignment

# 4) Follow-up, site visit, escalation, lost leads
l4 = mk_lead("Deepak Enterprises", "9800000003", 600000)
check(requests.post(f"{B}/leads/{l4['id']}/action", headers=H(lead), json={"action": "FOLLOW_UP", "followup_date": "2027-01-20", "remarks": "Call after quote"}), "followup")
l5 = mk_lead("Green Homes Co", "9800000004", 900000)
check(requests.post(f"{B}/leads/{l5['id']}/action", headers=H(lead), json={"action": "SITE_VISIT", "remarks": "Assess roof"}), "sitevisit")
svs = check(requests.get(f"{B}/site-visits", headers=H(manager)), "list sv")
sv = [s for s in svs if s["lead_id"] == l5["id"]][0]
check(requests.post(f"{B}/site-visits/{sv['id']}/assign", headers=H(manager), json={"assigned_user": inst_id, "visit_date": "2027-01-10"}), "assign sv")
l6 = mk_lead("Metro Mall Project", "9800000005", 2500000)
check(requests.post(f"{B}/leads/{l6['id']}/action", headers=H(lead), json={"action": "ESCALATION", "reason": "Pricing approval", "remarks": "Wants discount"}), "escalate")
l7 = mk_lead("Old Town Society", "9800000006", 700000)
check(requests.post(f"{B}/leads/{l7['id']}/action", headers=H(lead), json={"action": "NO", "lost_reason": "COMPETITOR"}), "lost")

check(requests.put(f"{B}/sla", headers=H(owner), json={"config": {"REGISTRATION_1": 5, "ACCOUNTS_1": 3, "DISPATCH": 4, "INSTALLATION": 7, "NET_METERING": 10, "REGISTRATION_2": 5, "ACCOUNTS_2": 5}}), "sla")
print("SEED DONE")
