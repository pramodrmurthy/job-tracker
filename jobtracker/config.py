"""Paths and environment-based configuration."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JOBTRACKER_DATA_DIR", ROOT / "appdata"))
RESUME_DIR = DATA_DIR / "resumes"
DB_URL = os.environ.get("JOBTRACKER_DB_URL", f"sqlite:///{DATA_DIR / 'jobtracker.db'}")
FRONTEND_DIST = ROOT / "frontend" / "dist"

# Gmail OAuth files keep their existing location so a previous login keeps working.
GMAIL_CLIENT_SECRET = Path(os.environ.get("GMAIL_CLIENT_SECRET", ROOT / "client_secret.json"))
GMAIL_TOKEN = Path(os.environ.get("GMAIL_TOKEN", ROOT / "token.json"))
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]  # narrowest scope that can create drafts

SOURCE_DELAY_SECONDS = float(os.environ.get("JOBTRACKER_SOURCE_DELAY", "1.0"))
SOURCE_USER_AGENT = "hireabroad-personal-scraper/0.1 (personal job search; low volume)"
MAX_RESUME_BYTES = 5 * 1024 * 1024
SCORE_BATCH_SIZE = 8
DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def load_env() -> dict[str, str]:
    """Read .env in the project root (KEY=VALUE lines); real environment variables win."""
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip("'\"")
    env.update({k: v for k, v in os.environ.items() if k.startswith(("GEMINI_", "TELEGRAM_"))})
    return env
