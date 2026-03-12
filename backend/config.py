"""Centralised configuration — env vars, constants, model names."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Auth ─────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET", "")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET env var is required")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 72

# ── Anthropic ────────────────────────────────────────────────────────────────
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MESSAGE_BATCH_SIZE = 20

# ── CSV ──────────────────────────────────────────────────────────────────────
MAX_CSV_ROWS = 5000
ALLOWED_CSV_EXTENSIONS = {".csv"}

# ── Data paths ───────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
POLICY_CHANGES_FILE = os.path.join(DATA_DIR, "policy_changes.json")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")

# ── Singapore insurance constants ────────────────────────────────────────────
KNOWN_INSURERS = [
    "AIA", "Prudential", "Great Eastern", "NTUC Income", "Manulife",
    "AXA", "Tokio Marine", "FWD", "Aviva", "Etiqa", "HSBC Life",
    "Singlife", "China Life", "Raffles Health Insurance",
]

POLICY_TYPES = [
    "Life", "Health/Medical", "Motor", "Travel", "Home",
    "Critical Illness", "Investment-Linked (ILP)", "Personal Accident",
    "Disability Income", "Group Insurance",
]

# ── CORS ─────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
