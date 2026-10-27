"""Pipeline: fetch -> details -> filter -> score -> draft -> (optional) gmail.

Every stage is idempotent and driven by database state, not by what this run happened to see:
  * jobs are upserted by (source, external_id), duplicates point at a canonical job;
  * details are fetched only for jobs that lack them; scores are cached per (job content, resume, preferences);
  * drafts are created only for jobs that are not already linked to a draft;
  * Gmail drafts are created only for drafts without a gmail_draft_id.
So a retry (or a changed profile) never creates duplicate jobs, assessments or drafts.
"""

import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import config, draft_service, legacy, scoring
from .draft_service import GmailCreator, active_resume
from .llm import Ask
from .models import (Application, Assessment, ContactedRecruiter, DraftJob, EmailDraft, Job, JobObservation, Run,
                     utcnow)
from .services import (PIPELINE_OWNED, auto_advance, content_hash, dedupe_key, get_setting, parse_min_years,
                       profile_config)
from .sources.base import Source, SourceError

STAT_KEYS = ["listings_seen", "unique_jobs", "new_jobs", "known_jobs", "duplicates", "passed_filters", "scored",
             "matched", "drafts_generated", "gmail_drafts_created", "errors"]
MAX_CONSECUTIVE_FAILURES = 5


class RunCancelled(Exception):
    pass


@dataclass
class Deps:
    source: Source
    ask: Ask | None = None
    gmail_create: GmailCreator | None = None
    sleep: Callable[[float], None] = field(default=time.sleep)


# ---------- run bookkeeping ----------

def active_run(session: Session) -> Run | None:
    return session.scalars(select(Run).where(Run.status.in_(["queued", "running"]))).first()


def create_run(session: Session, profile_id: int, mode: str = "incremental", dry_run: bool = False) -> Run:
    if active_run(session):
        raise RuntimeError("A run is already queued or running.")
    from .services import get_profile
    profile = get_profile(session, profile_id)
    if profile is None:
        raise ValueError("profile not found")
    run = Run(profile_id=profile_id, mode=mode, dry_run=dry_run, status="queued",
              filters_used=profile_config(profile), stats={k: None for k in STAT_KEYS}, errors=[])
    session.add(run)
    session.commit()
    return run


def mark_interrupted_runs(session: Session) -> int:
    """After a restart, runs that were mid-flight can never finish; mark them failed (a retry resumes safely)."""
    stale = session.scalars(select(Run).where(Run.status.in_(["queued", "running"]))).all()
    for run in stale:
        run.status, run.finished_at = "failed", utcnow()
        run.errors = [*run.errors, {"stage": run.stage, "job_id": None, "message": "interrupted by restart"}]
    session.commit()
    return len(stale)


def _error(run: Run, stage: str, message: str, job_id: int | None = None) -> None:
    run.errors = [*run.errors, {"stage": stage, "job_id": job_id, "message": message[:400]}]
    run.stats = {**run.stats, "errors": (run.stats.get("errors") or 0) + 1}


def _stat(run: Run, **values) -> None:
    run.stats = {**run.stats, **values}


def _stage(session: Session, run: Run, stage: str, done: int | None = None, total: int | None = None) -> None:
    run.stage, run.progress_done, run.progress_total = stage, done, total
    session.commit()


def _check_cancel(session: Session, run: Run) -> None:
    session.refresh(run)
    if run.cancel_requested:
        raise RunCancelled()


# ---------- filters ----------

def cheap_filter(job: Job, cfg: dict) -> bool:
    """Filters that only need list data (category, years, country)."""
    cats = {c.upper() for c in cfg["categories"]}
    if cats and (job.category or "").upper() not in cats:
        return False
    years = job.min_years
    if cfg.get("min_years") is not None and (years is None or years < cfg["min_years"]):
        return False
    if cfg.get("max_years") is not None and years is not None and years > cfg["max_years"]:
        return False
    country = (job.country or "").upper()
    include = {c.upper() for c in cfg["countries_include"]}
    exclude = {c.upper() for c in cfg["countries_exclude"]}
    if include and country not in include:
        return False
    return country not in exclude


def keyword_filter(job: Job, cfg: dict) -> bool | None:
    """True/False once details are available, None when keywords are required but the description is missing."""
    include = [k.lower() for k in cfg["keywords_include"]]
    exclude = [k.lower() for k in cfg["keywords_exclude"]]
    if not include and not exclude:
        return True
    if not job.detailed:
        return None
    text = " ".join([job.title, " ".join(job.skills or []), job.description or ""]).lower()
    if include and not any(k in text for k in include):
        return False
    return not any(k in text for k in exclude)


# ---------- stages ----------

def _apply_fields(job: Job, nj: dict, with_description: bool) -> None:
    for attr in ("title", "company", "country", "city", "category", "sub_category", "experience_level", "skills",
                 "hr_email", "hr_name", "hr_phone", "salary_text", "employment_type", "work_mode", "visa_sponsored",
                 "posted_at", "source_url"):
        setattr(job, attr, nj.get(attr))
    if with_description:
        job.description = nj.get("description")
    job.min_years = parse_min_years(nj.get("experience_level"))


def stage_fetch(session: Session, run: Run, deps: Deps, cfg: dict) -> set[int]:
    """Upsert listings. Returns the ids of canonical jobs observed in this run."""
    _stage(session, run, "fetch")
    counters = dict(listings_seen=0, new_jobs=0, known_jobs=0, duplicates=0)
    seen_ext: set[str] = set()
    observed: set[int] = set()
    name = deps.source.name
    completed = False
    try:
        for page in deps.source.list_pages(cfg):
            _check_cancel(session, run)
            page_unknown = 0
            for nj in page:
                counters["listings_seen"] += 1
                ext = nj["external_id"]
                if ext in seen_ext:
                    counters["duplicates"] += 1  # same listing twice in one run
                    continue
                seen_ext.add(ext)
                job = session.scalar(select(Job).where(Job.source == name, Job.external_id == ext))
                if job is None:
                    page_unknown += 1
                    job = Job(source=name, external_id=ext, title=nj["title"], dedupe_key="", content_hash="",
                              raw=nj.get("raw"), detailed=False)
                    _apply_fields(job, nj, with_description=True)
                    job.dedupe_key = dedupe_key(job.title, job.hr_email, job.country, job.company)
                    job.content_hash = content_hash({**nj, "title": job.title})
                    job.application = Application(status="discovered", reached_rank=0)
                    twin = session.scalar(select(Job).where(Job.dedupe_key == job.dedupe_key,
                                                            Job.canonical_job_id == Job.id).order_by(Job.id))
                    session.add(job)
                    session.flush()
                    job.canonical_job_id = twin.id if twin else job.id
                    if twin:
                        counters["duplicates"] += 1  # a repost of a posting we already have
                    else:
                        counters["new_jobs"] += 1
                    was_new = True
                else:
                    merged = {**nj, "description": job.description if job.detailed else nj.get("description")}
                    new_hash = content_hash(merged)
                    if new_hash != job.content_hash:  # meaningful change: refresh fields, keep detailed text
                        _apply_fields(job, nj, with_description=not job.detailed)
                        job.content_hash, job.content_changed_at = new_hash, utcnow()
                    job.last_seen_at, job.listing_status = utcnow(), "active"
                    if job.canonical_job_id == job.id:
                        counters["known_jobs"] += 1
                    was_new = False
                session.add(JobObservation(run_id=run.id, job_id=job.id, was_new=was_new))
                if job.canonical_job_id == job.id:
                    observed.add(job.id)
            _stat(run, **counters, unique_jobs=counters["new_jobs"] + counters["known_jobs"])
            session.commit()
            if run.mode == "incremental" and page_unknown == 0:
                break  # nothing new on this page: older pages are already known
        else:
            completed = True  # the source ran out of pages (no early stop)
    except SourceError as e:
        session.rollback()
        _error(run, "fetch", str(e))
        _stat(run, **counters, unique_jobs=counters["new_jobs"] + counters["known_jobs"])
        session.commit()
        if counters["listings_seen"] == 0:
            raise
        return observed
    _stat(run, **counters, unique_jobs=counters["new_jobs"] + counters["known_jobs"])
    if run.mode == "full" and completed:
        _mark_missing(session, name, observed, cfg)
    session.commit()
    return observed


def _mark_missing(session: Session, source_name: str, observed: set[int], cfg: dict) -> None:
    """Full runs only: previously active jobs that match the filters but were not listed are 'missing'.
    Applications and history are never deleted."""
    for job in session.scalars(select(Job).where(Job.source == source_name, Job.listing_status == "active",
                                                 Job.canonical_job_id == Job.id)):
        if job.id not in observed and cheap_filter(job, cfg):
            job.listing_status = "missing"


def stage_details(session: Session, run: Run, deps: Deps, cfg: dict) -> None:
    jobs = [j for j in session.scalars(select(Job).where(Job.source == deps.source.name, Job.detailed.is_(False),
                                                         Job.listing_status == "active",
                                                         Job.canonical_job_id == Job.id).order_by(Job.id))
            if cheap_filter(j, cfg)]
    _stage(session, run, "details", 0, len(jobs))
    failures = 0
    for i, job in enumerate(jobs, 1):
        _check_cancel(session, run)
        try:
            nj = deps.source.fetch_detail(job.external_id)
            _apply_fields(job, nj, with_description=True)
            job.detailed = True
            job.content_hash = content_hash(nj)
            job.dedupe_key = dedupe_key(job.title, job.hr_email, job.country, job.company)
            failures = 0
        except SourceError as e:
            session.rollback()
            _error(run, "details", str(e), job.id)
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                _error(run, "details", "stopped after repeated failures; a retry continues from here")
                session.commit()
                return
        run.progress_done = i
        session.commit()


def stage_filter(session: Session, run: Run, cfg: dict, observed: set[int]) -> None:
    _stage(session, run, "filter")
    passed_now = 0
    for job in session.scalars(select(Job).where(Job.canonical_job_id == Job.id, Job.listing_status == "active")):
        verdict = cheap_filter(job, cfg)
        kw = keyword_filter(job, cfg) if verdict else False
        ok = bool(verdict and kw)
        job.passed_filters = ok
        if ok and job.first_passed_filters_at is None:
            job.first_passed_filters_at = utcnow()
        if ok and job.id in observed:
            passed_now += 1
    _stat(run, passed_filters=passed_now)
    session.commit()


def stage_score(session: Session, run: Run, deps: Deps, cfg: dict) -> None:
    resume = active_resume(session)
    if resume is None:
        _error(run, "score", "No resume uploaded; cannot score jobs. Upload one in Settings.")
        _stat(run, scored=0, matched=0)
        session.commit()
        return
    prefs = get_setting(session, "preferences_text") or ""
    phash, model = scoring.prefs_hash(prefs), get_setting(session, "openai_model")
    todo: list[Job] = []
    for job in session.scalars(select(Job).join(Application).where(
            Job.canonical_job_id == Job.id, Job.passed_filters.is_(True), Job.detailed.is_(True),
            Application.status.in_(PIPELINE_OWNED)).order_by(Job.id)):  # no tokens on jobs already applied/dismissed
        cached = session.scalar(select(Assessment).where(Assessment.job_id == job.id, Assessment.resume_id == resume.id,
                                                         Assessment.content_hash == job.content_hash,
                                                         Assessment.prefs_hash == phash))
        if cached is None:
            todo.append(job)
        elif job.score != cached.score:  # restore the latest view from the cache
            job.score, job.relevant, job.reason, job.scored_at = cached.score, cached.relevant, cached.reason, cached.created_at
    _stage(session, run, "score", 0, len(todo))
    scored = matched = failures = 0
    if todo and deps.ask is None:
        _error(run, "score", "Gemini is not configured (GEMINI_API_KEY missing); jobs were not scored.")
        todo = []
    for start in range(0, len(todo), config.SCORE_BATCH_SIZE):
        _check_cancel(session, run)
        batch = todo[start:start + config.SCORE_BATCH_SIZE]
        try:
            results = scoring.score_batch(deps.ask, resume.text, prefs, batch)
            failures = 0
        except Exception as e:
            _error(run, "score", f"batch failed: {e}", batch[0].id)
            failures += 1
            session.commit()
            if failures >= 3:
                _error(run, "score", "stopped after repeated failures; a retry continues from here")
                break
            continue
        for job in batch:
            res = results.get(job.id)
            if res is None:
                _error(run, "score", "model did not return a valid score for this job", job.id)
                continue
            session.add(Assessment(job_id=job.id, resume_id=resume.id, content_hash=job.content_hash, prefs_hash=phash,
                                   model=model, score=res["score"], relevant=res["relevant"], reason=res["reason"]))
            job.score, job.relevant, job.reason, job.scored_at = res["score"], res["relevant"], res["reason"], utcnow()
            scored += 1
            if res["relevant"] and res["score"] >= cfg["threshold"]:
                matched += auto_advance(session, job.application, "matched", note=f"score {res['score']}")
        run.progress_done = min(start + len(batch), len(todo))
        _stat(run, scored=scored, matched=matched)
        session.commit()
    _stat(run, scored=scored, matched=matched)
    session.commit()


def stage_draft(session: Session, run: Run, deps: Deps, cfg: dict) -> list[int]:
    """One email per recruiter, only for jobs not already in a draft. Returns the new draft ids."""
    _stage(session, run, "draft")
    cutoff = utcnow() - timedelta(days=cfg["cooldown_days"])
    linked = {jid for (jid,) in session.execute(select(DraftJob.job_id))}
    candidates = [j for j in session.scalars(select(Job).join(Application).where(
        Job.canonical_job_id == Job.id, Application.status.in_(["matched", "shortlisted"]),
        Job.hr_email.is_not(None)).order_by(Job.score.desc().nulls_last(), Job.id))
        if j.id not in linked and (j.application.status == "shortlisted" or (j.relevant and (j.score or 0) >= cfg["threshold"]))]
    groups: dict[str, list[Job]] = {}
    for job in candidates:
        groups.setdefault(job.hr_email.lower(), []).append(job)
    created: list[int] = []
    count = 0
    for recipient, jobs in groups.items():
        _check_cancel(session, run)
        if cfg["cooldown_days"] > 0 and _recipient_on_cooldown(session, recipient, cutoff):
            continue
        best = max((j.score if j.score is not None else 100) for j in jobs)
        jobs = [j for j in jobs if (j.score if j.score is not None else 100) >= best - cfg["score_gap"]]
        if deps.ask is None:
            _error(run, "draft", "Gemini is not configured; drafts were not generated.")
            break
        try:
            draft = draft_service.create_draft_for_jobs(session, jobs, recipient, deps.ask, run.id)
            created.append(draft.id)
            count += 1
            _stat(run, drafts_generated=count)
            session.commit()
        except Exception as e:
            session.rollback()
            _error(run, "draft", f"{recipient}: {e}", jobs[0].id)
            session.commit()
    _stat(run, drafts_generated=count)
    session.commit()
    return created


def _recipient_on_cooldown(session: Session, recipient: str, cutoff) -> bool:
    open_draft = session.scalar(select(EmailDraft.id).where(EmailDraft.recipient == recipient,
                                                            EmailDraft.status.in_(["generated", "approved"])))
    if open_draft:
        return True  # one open draft per recruiter at a time
    if session.scalar(select(EmailDraft.id).where(EmailDraft.recipient == recipient, EmailDraft.status == "gmail_draft",
                                                  EmailDraft.created_at >= cutoff)):
        return True
    if session.scalar(select(ContactedRecruiter.id).where(ContactedRecruiter.email == recipient,
                                                          ContactedRecruiter.contacted_at >= cutoff)):
        return True  # contacted before this app existed (imported history)
    return session.scalar(select(Application.id).join(Job).where(Job.hr_email == recipient,
                                                                 Application.applied_at >= cutoff)) is not None


def stage_gmail(session: Session, run: Run, deps: Deps, draft_ids: list[int]) -> None:
    _stage(session, run, "gmail", 0, len(draft_ids))
    if deps.gmail_create is None:
        _error(run, "gmail", "Gmail is not connected; drafts stay in the app. Connect Gmail in Settings.")
        _stat(run, gmail_drafts_created=0)
        session.commit()
        return
    result = draft_service.create_gmail_drafts(session, draft_ids, deps.gmail_create)
    for f in result["failed"]:
        _error(run, "gmail", f"draft {f['id']}: {f['message']}")
    _stat(run, gmail_drafts_created=len(result["created"]))
    session.commit()


# ---------- orchestration ----------

def _finish_early(session: Session, run: Run) -> Run:
    run.status = "partial" if run.errors else "succeeded"
    run.stage, run.progress_done, run.progress_total, run.finished_at = "done", None, None, utcnow()
    session.commit()
    return run


def execute_run(session: Session, run_id: int, deps: Deps, stop_after: str | None = None) -> Run:
    """stop_after='fetch' or 'details' ends the run early, with no scoring, drafts or LLM calls: used by the scan command."""
    run = session.get(Run, run_id)
    if run is None or run.status not in ("queued",):
        raise ValueError("run not found or not queued")
    from .services import get_profile
    cfg = profile_config(get_profile(session, run.profile_id))
    run.status, run.started_at = "running", utcnow()
    session.commit()
    try:
        observed = stage_fetch(session, run, deps, cfg)
        legacy.seed_legacy_sent(session)
        legacy.apply_legacy_sent(session)  # jobs emailed by the previous scripts become 'applied'
        session.commit()
        if stop_after == "fetch":
            return _finish_early(session, run)
        stage_details(session, run, deps, cfg)
        stage_filter(session, run, cfg, observed)
        if stop_after == "details":
            return _finish_early(session, run)
        stage_score(session, run, deps, cfg)
        if not run.dry_run:
            draft_ids = stage_draft(session, run, deps, cfg)
            if cfg.get("auto_gmail_drafts"):
                stage_gmail(session, run, deps, draft_ids)
            else:
                _stat(run, gmail_drafts_created=0)
        run.status = "partial" if run.errors else "succeeded"
    except RunCancelled:
        session.rollback()
        run.status = "cancelled"
    except SourceError as e:
        session.rollback()
        run.status = "failed"
        _error(run, run.stage or "fetch", str(e))
    except Exception as e:  # unexpected: keep what was committed, report the failure
        session.rollback()
        run.status = "failed"
        _error(run, run.stage or "unknown", f"{type(e).__name__}: {e}")
    run.stage, run.progress_done, run.progress_total, run.finished_at = "done", None, None, utcnow()
    session.commit()
    return run
