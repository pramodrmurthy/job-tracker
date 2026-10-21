"""Database models. Canonical jobs are separate from per-run observations, assessments, applications and drafts."""

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Naive UTC datetime (SQLite does not keep timezones)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)


class Resume(Base):
    __tablename__ = "resume"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SearchProfile(Base):
    __tablename__ = "search_profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Run(Base):
    __tablename__ = "run"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("search_profile.id"))
    mode: Mapped[str] = mapped_column(String(20), default="incremental")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|partial|failed|cancelled
    stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    progress_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    filters_used: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # snapshot of the profile config
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (UniqueConstraint("source", "external_id"), Index("ix_job_dedupe", "dedupe_key"))
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String(150), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    min_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    hr_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hr_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hr_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    salary_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    visa_sponsored: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detailed: Mapped[bool] = mapped_column(Boolean, default=False)  # full description fetched
    content_hash: Mapped[str] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(500))
    canonical_job_id: Mapped[int | None] = mapped_column(ForeignKey("job.id"), nullable=True)  # self when canonical
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    content_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    listing_status: Mapped[str] = mapped_column(String(20), default="active")  # active|missing
    passed_filters: Mapped[bool] = mapped_column(Boolean, default=False)
    first_passed_filters_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # latest assessment, denormalised for fast listing; history/cache lives in `assessment`
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    application: Mapped["Application"] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")


class JobObservation(Base):
    """One row per (run, job): the job was seen in that run's results."""
    __tablename__ = "job_observation"
    __table_args__ = (UniqueConstraint("run_id", "job_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"))
    was_new: Mapped[bool] = mapped_column(Boolean, default=False)
    seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Assessment(Base):
    """LLM match assessment. Also the cache: same job content + resume + preferences is never re-scored."""
    __tablename__ = "assessment"
    __table_args__ = (UniqueConstraint("job_id", "resume_id", "content_hash", "prefs_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"))
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resume.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    prefs_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    score: Mapped[int] = mapped_column(Integer)
    relevant: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Application(Base):
    __tablename__ = "application"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="discovered")
    reached_rank: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="application")
    events: Mapped[list["StatusEvent"]] = relationship(back_populates="application", order_by="StatusEvent.id",
                                                       cascade="all, delete-orphan")


class StatusEvent(Base):
    """Auditable history of every status change."""
    __tablename__ = "status_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    by: Mapped[str] = mapped_column(String(20), default="system")  # user|system
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped[Application] = relationship(back_populates="events")


class EmailDraft(Base):
    __tablename__ = "email_draft"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(200), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="ai")  # ai|template
    status: Mapped[str] = mapped_column(String(20), default="generated")  # generated|approved|gmail_draft|discarded
    gmail_draft_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("run.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    jobs: Mapped[list[Job]] = relationship(secondary="draft_job", order_by="Job.id")


class DraftJob(Base):
    __tablename__ = "draft_job"
    draft_id: Mapped[int] = mapped_column(ForeignKey("email_draft.id"), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), primary_key=True)


class ContactedRecruiter(Base):
    """Recruiters already emailed outside this app's own drafts (e.g. imported from the old scripts).
    The pipeline's cooldown treats them like a recent Gmail draft."""
    __tablename__ = "contacted_recruiter"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    contacted_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(50), default="import")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class LegacySent(Base):
    """An email sent with the previous scripts, remembered as (recruiter address, job title start).
    The old job IDs were lost, so these are matched to real jobs by recruiter + title once the jobs are fetched;
    the matched job is then marked applied. `matched_job_id` records the result for the reconciliation report."""
    __tablename__ = "legacy_sent"
    __table_args__ = (UniqueConstraint("email", "title_prefix"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    title_prefix: Mapped[str] = mapped_column(String(200))
    sent_on: Mapped[datetime] = mapped_column(DateTime)
    matched_job_id: Mapped[int | None] = mapped_column(ForeignKey("job.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
