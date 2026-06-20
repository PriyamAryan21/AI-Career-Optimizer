"""
Configuration module - loads environment variables and master profile data.
All other modules import from here instead of reading files directly.
"""

import os
import time
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_DIR = BASE_DIR / "session_state"
OUTPUT_DIR = BASE_DIR / "output" / "resumes"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = BASE_DIR / "career_optimizer.db"
MASTER_PROFILE_PATH = BASE_DIR / "master_profile.yaml"
RESUME_TEMPLATE_PATH = BASE_DIR / "templates" / "resume_template.html"

# ── Supabase PostgreSQL ────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")


# Create directories if they don't exist
SESSION_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── API Keys & Auth ──────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD") # Default empty = no auth local, but required in prod

# ── Security & Encryption ──────────────────────────────
# Generates a volatile fallback key if none provided in .env
from cryptography.fernet import Fernet
FERNET_KEY = os.getenv("FERNET_KEY")
if not FERNET_KEY:
    FERNET_KEY = Fernet.generate_key().decode()
    
fernet_cipher = Fernet(FERNET_KEY.encode())

# ── Naukri ─────────────────────────────────────────────
NAUKRI_EMAIL = os.getenv("NAUKRI_EMAIL")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD")
NAUKRI_BASE_URL = "https://www.naukri.com"
NAUKRI_LOGIN_URL = "https://www.naukri.com/nlogin/login"
NAUKRI_PROFILE_URL = "https://www.naukri.com/mnjuser/profile"

# ── Email / SMTP ──────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL")

# ── Scheduling ─────────────────────────────────────────
UPDATE_FREQUENCY_DAYS = int(os.getenv("UPDATE_FREQUENCY_DAYS", "4"))
JITTER_HOURS = int(os.getenv("JITTER_HOURS", "3"))

# ── Target Roles ───────────────────────────────────────
TARGET_ROLES = [
    role.strip()
    for role in os.getenv("TARGET_ROLES", "").split(",")
    if role.strip()
]

# ── Master Profile ─────────────────────────────────────
def load_master_profile() -> dict:
    """Load and return the master profile YAML as a dictionary."""
    if not MASTER_PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"master_profile.yaml not found at {MASTER_PROFILE_PATH}. "
            "Please create it from the template."
        )
    with open(MASTER_PROFILE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_master_profile(data: dict) -> None:
    """Save updated profile data back to master_profile.yaml."""
    with open(MASTER_PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def generate_with_retry(model, prompt, max_retries=4, initial_delay=15, backoff_factor=2):
    """
    A robust wrapper for Gemini's generate_content with exponential backoff.
    It will wait 15s -> 30s -> 60s between failures before giving up.
    """
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            error_msg = str(e).lower()
            
            # If it's a permanent error (like 404 model not found), fail immediately
            if "404" in error_msg or "api_key" in error_msg:
                print(f"   ❌ Fatal API Error: {e}")
                raise e
            
            if attempt == max_retries - 1:
                print(f"   ❌ Final attempt failed after {max_retries} retries.")
                raise e
                
            print(f"   ⚠️ Gemini API limit hit. Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
            delay *= backoff_factor  # Double the wait time for the next attempt
            
    return None
