"""Draft creation and Gmail hand-off shared by the pipeline and the API."""

from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, drafting
from .llm import Ask
from .models import Application, EmailDraft, Job, Resume, utcnow
from .services import auto_advance, get_setting

# create_gmail_draft(to, subject, body, attachment_path) -> (draft_id, message_id); injected so tests need no Gmail.
GmailCreator = Callable[[str, str, str, Path | None], tuple[str, str | None]]


def active_resume(session: Session) -> Resume | None:
    return session.scalars(select(Resume).where(Resume.is_active).order_by(Resume.id.desc())).first()


def resume_file(resume: Resume | None) -> Path | None:
    """The resume file to attach. The stored path is absolute, so if the project folder was moved, look for the
    same file name inside the current resumes folder."""
    if resume is None or not resume.stored_path:
        return None
    stored = Path(resume.stored_path)
    if stored.exists():
        return stored
    moved = config.RESUME_DIR / stored.name
    return moved if moved.exists() else None


def job_view(job: Job) -> dict:
    return {"title": job.title, "country": job.country, "description": job.description, "skills": job.skills or [],
            "experience_level": job.experience_level}


def generate_email(session: Session, jobs: list[Job], recipient: str, ask: Ask) -> tuple[str, str, str]:
    resume = active_resume(session)
    if not resume:
        raise ValueError("No resume uploaded. Upload one in Settings first.")
    return drafting.write_email([job_view(j) for j in jobs], recipient, resume.text, ask,
                                get_setting(session, "sender"), get_setting(session, "availability_line") or "")


def create_draft_for_jobs(session: Session, jobs: list[Job], recipient: str, ask: Ask, run_id: int | None = None) -> EmailDraft:
    subject, body, source = generate_email(session, jobs, recipient, ask)
    draft = EmailDraft(recipient=recipient, subject=subject, body=body, source=source, run_id=run_id, jobs=list(jobs))
    session.add(draft)
    session.flush()
    for job in jobs:
        auto_advance(session, job.application, "draft_generated", note=f"draft #{draft.id}")
    return draft


def regenerate(session: Session, draft: EmailDraft, ask: Ask) -> EmailDraft:
    draft.subject, draft.body, draft.source = generate_email(session, list(draft.jobs), draft.recipient, ask)
    draft.edited = False
    if draft.status == "discarded":
        draft.status = "generated"
    draft.updated_at = utcnow()
    return draft


def create_gmail_drafts(session: Session, draft_ids: list[int], create: GmailCreator) -> dict:
    """Create Gmail drafts (never sends). Idempotent: drafts that already have a gmail_draft_id are skipped.
    Each success is committed immediately so a later failure cannot cause a duplicate on retry."""
    resume = active_resume(session)
    attachment = resume_file(resume)
    created, failed = [], []
    for draft_id in draft_ids:
        draft = session.get(EmailDraft, draft_id)
        if draft is None:
            failed.append({"id": draft_id, "message": "draft not found"})
            continue
        if draft.gmail_draft_id:
            continue  # already in Gmail
        if draft.status == "discarded":
            failed.append({"id": draft_id, "message": "draft is discarded"})
            continue
        try:
            gmail_id, message_id = create(draft.recipient, draft.subject, draft.body, attachment)
        except Exception as e:
            failed.append({"id": draft_id, "message": str(e)[:300]})
            continue
        draft.gmail_draft_id, draft.gmail_message_id, draft.status = gmail_id, message_id, "gmail_draft"
        draft.updated_at = utcnow()
        for job in draft.jobs:
            auto_advance(session, job.application, "gmail_draft_created", note=f"gmail draft {gmail_id}")
        session.commit()
        created.append({"id": draft_id, "gmail_draft_id": gmail_id})
    return {"created": created, "failed": failed}
