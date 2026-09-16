"""Auto-reset seed user passwords at start of every test session.
Some earlier iterations may have left seed users with modified hashes; this makes
the suite deterministic without weakening any auth/business assertion.
"""
import bcrypt
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os

SEED_PASSWORDS = {
    "anoopdube07@gmail.com": "Owner@123",
    "manager": "Manager@123",
    "lead": "Lead@123",
    "registration": "Reg@123",
    "accounts": "Acct@123",
    "dispatch": "Disp@123",
    "installation": "Install@123",
    "instmgr": "InstMgr@123",
    "instmem": "InstMem@123",
    "complaint": "Comp@123",
}


def _mongo():
    url = "mongodb://localhost:27017"
    dbn = "test_database"
    try:
        with open("/app/backend/.env") as f:
            for l in f:
                if l.startswith("MONGO_URL"):
                    url = l.split("=", 1)[1].strip().strip('"')
                elif l.startswith("DB_NAME"):
                    dbn = l.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return AsyncIOMotorClient(url)[dbn]


async def _reset():
    db = _mongo()
    for uname, pwd in SEED_PASSWORDS.items():
        u = await db.users.find_one({"username": uname})
        if not u:
            continue
        if not bcrypt.checkpw(pwd.encode(), u["password_hash"].encode()):
            newh = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt(rounds=12)).decode()
            await db.users.update_one({"username": uname}, {"$set": {"password_hash": newh, "active": True}})


@pytest.fixture(scope="session", autouse=True)
def _reset_seed_passwords():
    try:
        asyncio.get_event_loop().run_until_complete(_reset())
    except RuntimeError:
        asyncio.new_event_loop().run_until_complete(_reset())
    yield
