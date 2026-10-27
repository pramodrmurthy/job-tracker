"""Core domain helpers shared by the pipeline and the API."""

import hashlib
import json
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Application, Job, SearchProfile, Setting, StatusEvent, utcnow
from .statuses import STAGE_RANK, STATUSES

DEFAULT_PROFILE_CONFIG = {
    "categories": ["IT"], "min_years": 10, "max_years": None,
    "countries_include": [], "countries_exclude": ["INDIA"],
    "keywords_include": [], "keywords_exclude": [],
    "threshold": 60, "score_gap": 10, "cooldown_days": 0, "auto_gmail_drafts": False,
}
DEFAULT_SETTINGS = {
    "sender": {"name": "", "phone": "", "email": "", "linkedin": ""},
    "preferences_text": "",
    "availability_line": "",
    "openai_model": config.load_env().get("GEMINI_MODEL", config.DEFAULT_MODEL),
}


# ---------- settings ----------

def get_setting(session: Session, key: str):
    row = session.get(Setting, key)
    return row.value if row else json.loads(json.dumps(DEFAULT_SETTINGS.get(key)))


def set_setting(session: Session, key: str, value) -> None:
    row = session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))


def get_profile(session: Session, profile_id: int) -> SearchProfile | None:
    return session.get(SearchProfile, profile_id)


def ensure_default_profile(session: Session) -> SearchProfile:
    profile = session.scalars(select(SearchProfile).order_by(SearchProfile.id)).first()
    if not profile:
        profile = SearchProfile(name="Default", config=dict(DEFAULT_PROFILE_CONFIG))
        session.add(profile)
        session.flush()
    return profile


def profile_config(profile: SearchProfile) -> dict:
    """Profile config with defaults filled in, so older saved profiles keep working."""
    return {**DEFAULT_PROFILE_CONFIG, **(profile.config or {})}


# ---------- job identity ----------

def normalize_text(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def dedupe_key(title: str, recruiter_email: str | None, country: str | None, company: str | None = None) -> str:
    """Fallback identity for the same posting listed twice: title + recruiter (or company) + country."""
    who = (recruiter_email or "").strip().lower() or normalize_text(company)
    return f"{normalize_text(title)}|{who}|{(country or '').strip().upper()}"


def content_hash(job: dict) -> str:
    """Hash of the parts of a job whose change warrants a fresh look."""
    material = json.dumps([normalize_text(job.get("title")), (job.get("description") or "").strip(),
                           sorted(job.get("skills") or []), job.get("experience_level"),
                           (job.get("hr_email") or "").lower(), job.get("country")], sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


def parse_min_years(level: str | None) -> int | None:
    """'10+' -> 10, '7-10' -> 7, '15+' -> 15, 'Fresher' -> None."""
    m = re.match(r"\s*(\d+)", level or "")
    return int(m.group(1)) if m else None


# ---------- application lifecycle ----------

def set_status(session: Session, application: Application, to_status: str, by: str = "system",
               note: str | None = None, when: datetime | None = None) -> bool:
    """Change an application's status, append history, track the highest funnel rank reached.
    Returns False (and changes nothing) when the status is already `to_status`."""
    if to_status not in STATUSES:
        raise ValueError(f"unknown status: {to_status}")
    if application.status == to_status:
        return False
    when = when or utcnow()
    session.add(StatusEvent(application_id=application.id, job_id=application.job_id,
                            from_status=application.status, to_status=to_status, at=when, by=by, note=note))
    application.status = to_status
    rank = STAGE_RANK.get(to_status)
    if rank is not None:
        application.reached_rank = max(application.reached_rank, rank)
    if to_status == "applied" and application.applied_at is None:
        application.applied_at = when
    application.updated_at = when
    return True


PIPELINE_OWNED = {"discovered", "matched", "shortlisted", "draft_generated"}


def auto_advance(session: Session, application: Application, to_status: str, note: str | None = None) -> bool:
    """Pipeline-driven move forward. Only moves jobs sitting in a pipeline-owned status to a later stage, so a
    status the user chose (applied, rejected, not_interested, ...) is never overridden."""
    if application.status not in PIPELINE_OWNED:
        return False
    if STAGE_RANK[application.status] >= STAGE_RANK[to_status]:
        return False
    return set_status(session, application, to_status, by="system", note=note)


def new_job_application(job: Job) -> Application:
    return Application(job=job, status="discovered", reached_rank=0)
