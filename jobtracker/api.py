"""FastAPI application. Contract: docs/API.md. Local single-user app: bind to 127.0.0.1 only."""

from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from . import analytics, config, db, draft_service, gmail, llm, pipeline, runner, scoring
from .models import (Application, Assessment, ContactedRecruiter, DraftJob, EmailDraft, Job, JobObservation, Resume, Run,
                     SearchProfile, iso, utcnow)
from .resume_parser import ResumeError, extract_text, store_file
from .services import (DEFAULT_SETTINGS, ensure_default_profile, get_setting, profile_config, set_status, set_setting)
from .sources.hireabroad import HireAbroadSource
from .statuses import STATUSES

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
ALLOWED_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "testserver"}


# ---------- request models ----------

class SettingsUpdate(BaseModel):
    sender: dict | None = None
    preferences_text: str | None = None
    availability_line: str | None = None
    openai_model: str | None = Field(default=None, max_length=100)


class ProfileBody(BaseModel):
    name: str = Field(max_length=100)
    categories: list[str] = []
    min_years: int | None = Field(default=None, ge=0, le=60)
    max_years: int | None = Field(default=None, ge=0, le=60)
    countries_include: list[str] = []
    countries_exclude: list[str] = []
    keywords_include: list[str] = []
    keywords_exclude: list[str] = []
    threshold: int = Field(default=60, ge=0, le=100)
    score_gap: int = Field(default=10, ge=0, le=100)
    cooldown_days: int = Field(default=30, ge=0, le=365)
    auto_gmail_drafts: bool = False


class RunBody(BaseModel):
    profile_id: int = 1
    mode: Literal["incremental", "full"] = "incremental"
    dry_run: bool = False


class JobPatch(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=5000)


class BulkBody(BaseModel):
    ids: list[int] = Field(max_length=2000)
    status: str


class DraftPatch(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20000)
    status: Literal["generated", "approved", "discarded"] | None = None


class GmailBody(BaseModel):
    ids: list[int] = Field(max_length=500)


# ---------- serializers ----------

def contacted_map(session: Session) -> dict[str, "datetime"]:
    """recruiter address -> the most recent time that recruiter was emailed, from every source we know:
    imported history, Gmail drafts created here, and jobs marked applied."""
    out: dict[str, datetime] = {}

    def note(email: str | None, when: datetime | None) -> None:
        if email and when and (email.lower() not in out or when > out[email.lower()]):
            out[email.lower()] = when

    for email, when in session.execute(select(ContactedRecruiter.email, ContactedRecruiter.contacted_at)):
        note(email, when)
    for email, when in session.execute(select(EmailDraft.recipient, EmailDraft.created_at).where(EmailDraft.status == "gmail_draft")):
        note(email, when)
    for email, when in session.execute(select(Job.hr_email, Application.applied_at).join(Application)
                                       .where(Application.applied_at.is_not(None), Job.hr_email.is_not(None))):
        note(email, when)
    return out


def job_summary(job: Job, has_draft: bool, contacted: dict | None = None) -> dict:
    return {"id": job.id, "external_id": job.external_id, "title": job.title, "company": job.company,
            "country": job.country, "city": job.city, "category": job.category, "sub_category": job.sub_category,
            "experience_level": job.experience_level, "hr_email": job.hr_email, "score": job.score,
            "relevant": job.relevant, "reason": job.reason, "status": job.application.status,
            "first_seen_at": iso(job.first_seen_at), "last_seen_at": iso(job.last_seen_at),
            "listing_status": job.listing_status, "has_draft": has_draft,
            "recruiter_contacted_at": iso((contacted or {}).get((job.hr_email or "").lower()))}


def draft_summary(d: EmailDraft) -> dict:
    return {"id": d.id, "recipient": d.recipient, "subject": d.subject, "status": d.status,
            "gmail_draft_id": d.gmail_draft_id}


def draft_dict(d: EmailDraft) -> dict:
    return {"id": d.id, "recipient": d.recipient, "job_ids": [j.id for j in d.jobs], "job_titles": [j.title for j in d.jobs],
            "countries": sorted({j.country for j in d.jobs if j.country}), "subject": d.subject, "body": d.body,
            "source": d.source, "status": d.status, "gmail_draft_id": d.gmail_draft_id,
            "gmail_url": gmail.draft_url(d.gmail_message_id), "edited": d.edited,
            "created_at": iso(d.created_at), "updated_at": iso(d.updated_at)}


def linked_job_ids(session: Session) -> set[int]:
    rows = session.execute(select(DraftJob.job_id).join(EmailDraft).where(EmailDraft.status != "discarded"))
    return {job_id for (job_id,) in rows}


def job_detail(session: Session, job: Job) -> dict:
    app_, assessment = job.application, session.scalar(select(Assessment).where(Assessment.job_id == job.id)
                                                       .order_by(Assessment.id.desc()))
    drafts = session.scalars(select(EmailDraft).join(DraftJob).where(DraftJob.job_id == job.id)
                             .order_by(EmailDraft.id)).all()
    return {**job_summary(job, any(d.status != "discarded" for d in drafts), contacted_map(session)),
            "description": job.description, "skills": job.skills or [], "salary_text": job.salary_text,
            "employment_type": job.employment_type, "work_mode": job.work_mode, "visa_sponsored": job.visa_sponsored,
            "hr_name": job.hr_name, "hr_phone": job.hr_phone, "posted_at": iso(job.posted_at), "source": job.source,
            "assessment": ({"score": assessment.score, "relevant": assessment.relevant, "reason": assessment.reason,
                            "model": assessment.model, "created_at": iso(assessment.created_at)} if assessment else None),
            "application": {"status": app_.status, "notes": app_.notes, "applied_at": iso(app_.applied_at),
                            "last_follow_up_at": iso(app_.last_follow_up_at)},
            "drafts": [draft_summary(d) for d in drafts],
            "history": [{"from": e.from_status, "to": e.to_status, "at": iso(e.at), "by": e.by, "note": e.note}
                        for e in app_.events]}


def settings_dict(session: Session) -> dict:
    resume = draft_service.active_resume(session)
    return {"sender": {**DEFAULT_SETTINGS["sender"], **(get_setting(session, "sender") or {})},
            "preferences_text": get_setting(session, "preferences_text") or "",
            "availability_line": get_setting(session, "availability_line") or "",
            "openai_model": get_setting(session, "openai_model") or "gpt-4o-mini",
            "openai_key_set": llm.key_is_set(),
            "resume": resume_dict(resume), "gmail": gmail_status(session)}


def resume_dict(r: Resume | None) -> dict | None:
    return ({"id": r.id, "filename": r.filename, "uploaded_at": iso(r.uploaded_at), "chars": len(r.text)}
            if r else None)


def gmail_status(session: Session) -> dict:
    connected = gmail.token_present()
    return {"client_secret_present": gmail.client_secret_present(), "connected": connected,
            "account": get_setting(session, "gmail_account") if connected else None}


def profile_dict(p: SearchProfile) -> dict:
    return {"id": p.id, "name": p.name, **profile_config(p)}


# ---------- default dependencies (real source, OpenAI, Gmail); tests override via app.state ----------

def default_deps(session: Session) -> pipeline.Deps:
    ask = None
    if llm.key_is_set():
        ask = llm.make_ask(get_setting(session, "openai_model") or "gpt-4o-mini")
    return pipeline.Deps(source=HireAbroadSource(), ask=ask, gmail_create=gmail_creator())


def gmail_creator() -> Callable | None:
    if not gmail.token_present():
        return None
    try:
        service = gmail.get_service(interactive=False)
    except gmail.GmailError:
        return None
    return lambda to, subject, body, attachment: gmail.create_draft(service, to, subject, body, attachment)


def create_app(deps_factory: Callable[[Session], pipeline.Deps] | None = None, sync_runs: bool = False,
               init: bool = True) -> FastAPI:
    app = FastAPI(title="Job Tracker API", version="1.0")
    app.state.deps_factory = deps_factory or default_deps
    app.state.sync_runs = sync_runs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)  # blocks DNS-rebinding

    @app.middleware("http")
    async def block_cross_site_writes(request: Request, call_next):
        """This app can create Gmail drafts, so a web page you visit must not be able to POST to it."""
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and (origin.split("://", 1)[-1].split(":")[0] not in ALLOWED_ORIGIN_HOSTS):
                return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
        return await call_next(request)

    if init:
        db.get_engine()
        with db.session_scope() as s:
            ensure_default_profile(s)
            pipeline.mark_interrupted_runs(s)

    api = app

    # ----- health & settings -----
    @api.get("/api/health")
    def health(session: Session = Depends(db.get_session)):
        session.execute(select(1))
        return {"status": "ok"}

    @api.get("/api/settings")
    def get_settings(session: Session = Depends(db.get_session)):
        return settings_dict(session)

    @api.put("/api/settings")
    def put_settings(body: SettingsUpdate, session: Session = Depends(db.get_session)):
        data = body.model_dump(exclude_unset=True)
        if "sender" in data and data["sender"] is not None:
            allowed = {"name", "phone", "email", "linkedin"}
            data["sender"] = {**get_setting(session, "sender"), **{k: str(v)[:200] for k, v in data["sender"].items() if k in allowed}}
        for key, value in data.items():
            if value is not None:
                set_setting(session, key, value)
        session.commit()
        return settings_dict(session)

    @api.post("/api/resume")
    async def upload_resume(file: UploadFile = File(...), session: Session = Depends(db.get_session)):
        data = await file.read(config.MAX_RESUME_BYTES + 1)
        try:
            text = extract_text(file.filename or "resume", data)
        except ResumeError as e:
            raise HTTPException(422, str(e))
        path = store_file(file.filename or "resume", data)
        for old in session.scalars(select(Resume).where(Resume.is_active)):
            old.is_active = False  # old versions stay on record
        resume = Resume(filename=Path(path).name.split("_", 1)[1], stored_path=str(path), mime=file.content_type, text=text)
        session.add(resume)
        session.commit()
        return resume_dict(resume)

    # ----- profiles -----
    @api.get("/api/profiles")
    def list_profiles(session: Session = Depends(db.get_session)):
        return [profile_dict(p) for p in session.scalars(select(SearchProfile).order_by(SearchProfile.id))]

    @api.get("/api/profiles/{profile_id}")
    def get_profile(profile_id: int, session: Session = Depends(db.get_session)):
        p = session.get(SearchProfile, profile_id)
        if not p:
            raise HTTPException(404, "profile not found")
        return profile_dict(p)

    @api.put("/api/profiles/{profile_id}")
    def put_profile(profile_id: int, body: ProfileBody, session: Session = Depends(db.get_session)):
        p = session.get(SearchProfile, profile_id)
        if not p:
            raise HTTPException(404, "profile not found")
        cfg = body.model_dump(exclude={"name"})
        if cfg["min_years"] is not None and cfg["max_years"] is not None and cfg["min_years"] > cfg["max_years"]:
            raise HTTPException(422, "min_years must not exceed max_years")
        p.name, p.config = body.name, cfg
        session.commit()
        return profile_dict(p)

    # ----- runs -----
    @api.post("/api/runs", status_code=201)
    def start_run(body: RunBody, session: Session = Depends(db.get_session)):
        try:
            run = pipeline.create_run(session, body.profile_id, body.mode, body.dry_run)
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))
        runner.run_in_background(run.id, app.state.deps_factory, sync=app.state.sync_runs)
        session.refresh(run)
        return analytics.run_to_dict(run)

    @api.get("/api/runs")
    def list_runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                  session: Session = Depends(db.get_session)):
        total = session.scalar(select(func.count()).select_from(Run))
        rows = session.scalars(select(Run).order_by(Run.id.desc()).limit(page_size).offset((page - 1) * page_size))
        return {"items": [analytics.run_to_dict(r) for r in rows], "total": total}

    def get_run_or_404(session: Session, run_id: int) -> Run:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(404, "run not found")
        return run

    @api.get("/api/runs/{run_id}")
    def get_run(run_id: int, session: Session = Depends(db.get_session)):
        return analytics.run_to_dict(get_run_or_404(session, run_id))

    @api.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: int, session: Session = Depends(db.get_session)):
        run = get_run_or_404(session, run_id)
        if run.status not in ("queued", "running"):
            raise HTTPException(409, "run already finished")
        run.cancel_requested = True
        session.commit()
        return analytics.run_to_dict(run)

    @api.post("/api/runs/{run_id}/retry", status_code=201)
    def retry_run(run_id: int, session: Session = Depends(db.get_session)):
        old = get_run_or_404(session, run_id)
        return start_run(RunBody(profile_id=old.profile_id, mode=old.mode, dry_run=old.dry_run), session)

    # ----- jobs -----
    @api.get("/api/jobs")
    def list_jobs(query: str | None = None, status: str | None = None, min_score: int | None = None,
                  max_score: int | None = None, country: str | None = None, category: str | None = None,
                  run_id: int | None = None, new_only: bool = False, has_draft: bool | None = None,
                  recruiter_contacted: bool | None = None,
                  sort: Literal["score", "first_seen", "title"] = "first_seen", order: Literal["asc", "desc"] = "desc",
                  page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                  session: Session = Depends(db.get_session)):
        stmt = select(Job).join(Application).where(Job.canonical_job_id == Job.id)
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.hr_email.ilike(like),
                                  Job.country.ilike(like), Job.sub_category.ilike(like)))
        if status:
            if status not in STATUSES:
                raise HTTPException(422, "unknown status")
            stmt = stmt.where(Application.status == status)
        if min_score is not None:
            stmt = stmt.where(Job.score >= min_score)
        if max_score is not None:
            stmt = stmt.where(Job.score <= max_score)
        if country:
            stmt = stmt.where(func.upper(Job.country) == country.upper())
        if category:
            stmt = stmt.where(func.upper(Job.category) == category.upper())
        if run_id is not None:
            stmt = stmt.where(Job.id.in_(select(JobObservation.job_id).where(JobObservation.run_id == run_id)))
        if new_only:
            latest = session.scalar(select(func.max(JobObservation.run_id)))
            stmt = stmt.where(Job.id.in_(select(JobObservation.job_id).where(
                and_(JobObservation.run_id == latest, JobObservation.was_new.is_(True)))))
        contacted = contacted_map(session)
        if recruiter_contacted is not None:
            clause = func.lower(Job.hr_email).in_(set(contacted)) if contacted else (Job.id < 0)
            stmt = stmt.where(clause if recruiter_contacted else ~clause)
        linked = linked_job_ids(session)
        if has_draft is not None:
            clause = Job.id.in_(linked) if linked else (Job.id < 0)
            stmt = stmt.where(clause if has_draft else ~clause)
        total = session.scalar(select(func.count()).select_from(stmt.subquery()))
        column = {"score": Job.score, "first_seen": Job.first_seen_at, "title": Job.title}[sort]
        ordering = column.asc() if order == "asc" else column.desc()
        rows = session.scalars(stmt.order_by(ordering.nulls_last() if sort == "score" else ordering, Job.id.desc())
                               .limit(page_size).offset((page - 1) * page_size))
        return {"items": [job_summary(j, j.id in linked, contacted) for j in rows], "total": total}

    def get_job_or_404(session: Session, job_id: int) -> Job:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        return job

    @api.get("/api/jobs/{job_id}")
    def get_job(job_id: int, session: Session = Depends(db.get_session)):
        return job_detail(session, get_job_or_404(session, job_id))

    @api.patch("/api/jobs/{job_id}")
    def patch_job(job_id: int, body: JobPatch, session: Session = Depends(db.get_session)):
        job = get_job_or_404(session, job_id)
        if body.status is not None:
            if body.status not in STATUSES:
                raise HTTPException(422, f"unknown status: {body.status}")
            set_status(session, job.application, body.status, by="user")
        if body.notes is not None:
            job.application.notes = body.notes
        session.commit()
        return job_detail(session, job)

    @api.post("/api/jobs/bulk")
    def bulk_jobs(body: BulkBody, session: Session = Depends(db.get_session)):
        if body.status not in STATUSES:
            raise HTTPException(422, f"unknown status: {body.status}")
        updated = 0
        for job in session.scalars(select(Job).where(Job.id.in_(body.ids))):
            updated += set_status(session, job.application, body.status, by="user")
        session.commit()
        return {"updated": updated}

    @api.post("/api/jobs/{job_id}/rescore")
    def rescore(job_id: int, session: Session = Depends(db.get_session)):
        job = get_job_or_404(session, job_id)
        resume = draft_service.active_resume(session)
        if not resume:
            raise HTTPException(409, "Upload a resume first.")
        deps = app.state.deps_factory(session)
        if deps.ask is None:
            raise HTTPException(409, "OpenAI is not configured (OPENAI_API_KEY missing).")
        prefs = get_setting(session, "preferences_text") or ""
        try:
            result = scoring.score_batch(deps.ask, resume.text, prefs, [job]).get(job.id)
        except Exception as e:
            raise HTTPException(502, f"Scoring failed: {e}")
        if result is None:
            raise HTTPException(502, "The model did not return a valid score.")
        phash = scoring.prefs_hash(prefs)
        existing = session.scalar(select(Assessment).where(Assessment.job_id == job.id, Assessment.resume_id == resume.id,
                                                           Assessment.content_hash == job.content_hash,
                                                           Assessment.prefs_hash == phash))
        values = dict(score=result["score"], relevant=result["relevant"], reason=result["reason"],
                      model=get_setting(session, "openai_model"), created_at=utcnow())
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
        else:
            session.add(Assessment(job_id=job.id, resume_id=resume.id, content_hash=job.content_hash, prefs_hash=phash, **values))
        job.score, job.relevant, job.reason, job.scored_at = result["score"], result["relevant"], result["reason"], utcnow()
        session.commit()
        return job_detail(session, job)

    # ----- drafts -----
    @api.get("/api/drafts")
    def list_drafts(status: Literal["generated", "approved", "gmail_draft", "discarded"] | None = None,
                    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                    session: Session = Depends(db.get_session)):
        stmt = select(EmailDraft)
        if status:
            stmt = stmt.where(EmailDraft.status == status)
        total = session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = session.scalars(stmt.order_by(EmailDraft.id.desc()).limit(page_size).offset((page - 1) * page_size))
        return {"items": [draft_dict(d) for d in rows], "total": total}

    def get_draft_or_404(session: Session, draft_id: int) -> EmailDraft:
        d = session.get(EmailDraft, draft_id)
        if not d:
            raise HTTPException(404, "draft not found")
        return d

    @api.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: int, session: Session = Depends(db.get_session)):
        return draft_dict(get_draft_or_404(session, draft_id))

    @api.patch("/api/drafts/{draft_id}")
    def patch_draft(draft_id: int, body: DraftPatch, session: Session = Depends(db.get_session)):
        d = get_draft_or_404(session, draft_id)
        if d.gmail_draft_id:
            raise HTTPException(409, "This draft is already in Gmail; edit it there.")
        if body.subject is not None and body.subject != d.subject:
            d.subject, d.edited = body.subject, True
        if body.body is not None and body.body != d.body:
            d.body, d.edited = body.body, True
        if body.status is not None:
            d.status = body.status
        d.updated_at = utcnow()
        session.commit()
        return draft_dict(d)

    @api.post("/api/drafts/{draft_id}/regenerate")
    def regenerate_draft(draft_id: int, session: Session = Depends(db.get_session)):
        d = get_draft_or_404(session, draft_id)
        if d.gmail_draft_id:
            raise HTTPException(409, "This draft is already in Gmail.")
        ask = app.state.deps_factory(session).ask
        if ask is None:
            raise HTTPException(409, "OpenAI is not configured (OPENAI_API_KEY missing).")
        try:
            draft_service.regenerate(session, d, ask)
        except ValueError as e:
            raise HTTPException(409, str(e))
        session.commit()
        return draft_dict(d)

    @api.post("/api/drafts/gmail")
    def drafts_to_gmail(body: GmailBody, session: Session = Depends(db.get_session)):
        deps = app.state.deps_factory(session)
        if deps.gmail_create is None:
            raise HTTPException(400, "Gmail is not connected. Connect it in Settings first.")
        return draft_service.create_gmail_drafts(session, body.ids, deps.gmail_create)

    @api.get("/api/drafts/{draft_id}/markdown")
    def draft_markdown(draft_id: int, session: Session = Depends(db.get_session)):
        d = get_draft_or_404(session, draft_id)
        jobs = "\n".join(f"- {j.title} ({j.country or 'n/a'}), job {j.external_id}" for j in d.jobs)
        text = (f"# {d.subject}\n\n**To:** {d.recipient}\n\n**Roles:**\n{jobs}\n\n**Status:** {d.status}\n\n---\n\n{d.body}\n")
        return PlainTextResponse(text, media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="draft_{d.id}.md"'})

    # ----- gmail -----
    @api.get("/api/gmail/status")
    def gmail_status_route(session: Session = Depends(db.get_session)):
        return gmail_status(session)

    @api.post("/api/gmail/connect")
    def gmail_connect(session: Session = Depends(db.get_session)):
        if not gmail.client_secret_present():
            raise HTTPException(400, f"{config.GMAIL_CLIENT_SECRET.name} not found in the project folder.")
        try:
            service = gmail.get_service(interactive=True)
        except gmail.GmailError as e:
            raise HTTPException(400, str(e))
        set_setting(session, "gmail_account", gmail.account_email(service))
        session.commit()
        return gmail_status(session)

    @api.post("/api/gmail/disconnect")
    def gmail_disconnect(session: Session = Depends(db.get_session)):
        gmail.disconnect()
        set_setting(session, "gmail_account", None)
        session.commit()
        return gmail_status(session)

    # ----- analytics -----
    def guarded(fn, *args):
        try:
            return fn(*args)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @api.get("/api/analytics/summary")
    def a_summary(from_: str | None = Query(None, alias="from"), to: str | None = None,
                  session: Session = Depends(db.get_session)):
        return guarded(analytics.summary, session, from_, to)

    @api.get("/api/analytics/funnel")
    def a_funnel(from_: str | None = Query(None, alias="from"), to: str | None = None,
                 session: Session = Depends(db.get_session)):
        return guarded(analytics.funnel, session, from_, to)

    @api.get("/api/analytics/rates")
    def a_rates(from_: str | None = Query(None, alias="from"), to: str | None = None,
                session: Session = Depends(db.get_session)):
        return guarded(analytics.rates, session, from_, to)

    @api.get("/api/analytics/timeseries")
    def a_timeseries(metric: Literal["discovered", "new", "matched", "applied", "replied"],
                     bucket: Literal["day", "week"] = "day", from_: str | None = Query(None, alias="from"),
                     to: str | None = None, session: Session = Depends(db.get_session)):
        return guarded(analytics.timeseries, session, metric, bucket, from_, to)

    @api.get("/api/analytics/distributions")
    def a_distributions(by: Literal["country", "category", "company", "score", "status"],
                        from_: str | None = Query(None, alias="from"), to: str | None = None,
                        session: Session = Depends(db.get_session)):
        return guarded(analytics.distributions, session, by, from_, to)

    @api.get("/api/analytics/runs")
    def a_runs(session: Session = Depends(db.get_session)):
        return analytics.runs_series(session)

    # ----- built frontend (single command runs everything) -----
    if config.FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/") or path == "api":
                raise HTTPException(404, "not found")
            candidate = (config.FRONTEND_DIST / path).resolve()
            if path and config.FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(config.FRONTEND_DIST / "index.html")

    return app

