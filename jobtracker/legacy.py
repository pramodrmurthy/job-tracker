"""Bridge from the previous scripts: mark the jobs that were already emailed, matched by recruiter + job title.

The old pipeline recorded which jobs each email covered, but only the recruiter addresses survived. The role titles
in appdata/legacy_sent.json come from that run's printed output (truncated to ~40 characters), so jobs are matched on the START of the title.
"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import ContactedRecruiter, Job, LegacySent
from .services import normalize_text, set_status

LEGACY_FILE = config.DATA_DIR / "legacy_sent.json"  # {"sent_on": "YYYY-MM-DD", "pairs": [{"email_start", "title_start"}]}


def load_pairs() -> tuple[datetime, list[tuple[str, str]]]:
    """(sent date, [(start of recruiter address, start of job title)]) from appdata/legacy_sent.json, or nothing."""
    if not LEGACY_FILE.exists():
        return datetime(2026, 10, 18), []
    data = json.loads(LEGACY_FILE.read_text())
    return datetime.fromisoformat(data["sent_on"]), [(p["email_start"], p["title_start"]) for p in data["pairs"]]


def seed_legacy_sent(session: Session) -> int:
    """Insert PAIRS, resolving each address prefix against the full addresses imported earlier. Idempotent."""
    sent_on, pairs = load_pairs()
    full = [e for (e,) in session.execute(select(ContactedRecruiter.email))]
    existing = {(r.email, r.title_prefix) for r in session.scalars(select(LegacySent))}
    added = 0
    for email_start, title_start in pairs:
        email = next((e for e in full if e.startswith(email_start)), None)
        if email is None:
            email = email_start  # not imported yet: keep the prefix; it still matches by prefix below
        key = (email, normalize_text(title_start))
        if key not in existing:
            session.add(LegacySent(email=email, title_prefix=normalize_text(title_start), sent_on=sent_on,
                                   note="emailed with the previous scripts"))
            existing.add(key)
            added += 1
    session.flush()
    return added


def apply_legacy_sent(session: Session) -> int:
    """Mark matching jobs as applied (once). Never touches a job whose status is past the pipeline's own stages."""
    from .services import PIPELINE_OWNED
    marked = 0
    for entry in session.scalars(select(LegacySent).where(LegacySent.matched_job_id.is_(None))):
        jobs = session.scalars(select(Job).where(Job.canonical_job_id == Job.id, Job.hr_email.is_not(None))).all()
        for job in jobs:
            if not (job.hr_email.lower().startswith(entry.email) and normalize_text(job.title).startswith(entry.title_prefix)):
                continue
            entry.matched_job_id = job.id
            if job.application.status in PIPELINE_OWNED:
                set_status(session, job.application, "applied", by="system", when=entry.sent_on,
                           note="imported: emailed with the previous scripts")
                marked += 1
            break
    session.flush()
    return marked


def report(session: Session) -> dict:
    """Reconciliation: legacy emails matched to jobs, those that were not found, and other jobs from the same recruiters."""
    entries = session.scalars(select(LegacySent).order_by(LegacySent.id)).all()
    matched, unmatched = [], []
    for e in entries:
        job = session.get(Job, e.matched_job_id) if e.matched_job_id else None
        (matched if job else unmatched).append({"recruiter": e.email, "title_start": e.title_prefix,
                                                "job_id": job.external_id if job else None,
                                                "job_title": job.title if job else None,
                                                "status": job.application.status if job else None})
    emails = {e.email for e in entries}
    sent_ids = {e.matched_job_id for e in entries if e.matched_job_id}
    others = [{"recruiter": j.hr_email, "job_id": j.external_id, "title": j.title, "status": j.application.status}
              for j in session.scalars(select(Job).where(Job.canonical_job_id == Job.id, Job.hr_email.is_not(None)))
              if j.id not in sent_ids and any(j.hr_email.lower().startswith(m) for m in emails)]
    return {"matched": matched, "unmatched": unmatched, "other_jobs_from_same_recruiters": others}
