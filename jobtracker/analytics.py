"""Dashboard analytics. Pure SQL/Python over the database; every number is reproducible from the tables.

Definitions
- KPI cards count ACTIVITY in the date range (e.g. applications whose first 'applied' event falls in the range).
- The funnel and the rates are COHORT based: the cohort is the unique jobs first discovered in the range, and each
  stage counts cohort jobs that ever reached it, so a rate is always <= 100% and its denominator is named.
- Duplicate listings never count: only canonical jobs are counted.
- Missing data is None; a real zero is 0.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Application, Job, JobObservation, Run, StatusEvent, iso
from .statuses import STAGE_RANK

FUNNEL = [  # (stage key, label, min rank or None for special stages, previous stage)
    ("discovered", "Discovered", None), ("passed_filters", "Passed filters", None), ("matched", "Matched", 1),
    ("drafted", "Drafted", 3), ("gmail_drafted", "Gmail drafted", 4), ("applied", "Applied", 5),
    ("replied", "Replied", 6), ("interviewed", "Interviewed", 7), ("offered", "Offered", 8),
]


def date_range(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    """Inclusive [from, to] dates -> half-open datetimes. Default: the last 90 days."""
    today = date.today()
    d_to = date.fromisoformat(end) if end else today
    d_from = date.fromisoformat(start) if start else d_to - timedelta(days=90)
    if d_from > d_to:
        raise ValueError("'from' must not be after 'to'")
    return datetime.combine(d_from, datetime.min.time()), datetime.combine(d_to + timedelta(days=1), datetime.min.time())


def _canonical(session: Session) -> list[Job]:
    return list(session.scalars(select(Job).where(Job.canonical_job_id == Job.id)))


def first_reach(session: Session, min_rank: int) -> dict[int, datetime]:
    """job_id -> time it first reached a status whose funnel rank is >= min_rank (canonical jobs only)."""
    statuses = [s for s, r in STAGE_RANK.items() if r >= min_rank]
    rows = session.execute(select(StatusEvent.job_id, func.min(StatusEvent.at)).where(StatusEvent.to_status.in_(statuses))
                           .group_by(StatusEvent.job_id)).all()
    canonical = {j.id for j in _canonical(session)}
    return {job_id: at for job_id, at in rows if job_id in canonical}


def _in(range_: tuple[datetime, datetime], when: datetime | None) -> bool:
    return when is not None and range_[0] <= when < range_[1]


def run_to_dict(run: Run | None) -> dict | None:
    if run is None:
        return None
    started, finished = run.started_at, run.finished_at
    progress = ({"done": run.progress_done, "total": run.progress_total}
                if run.progress_total is not None else None)
    return {"id": run.id, "profile_id": run.profile_id, "mode": run.mode, "dry_run": run.dry_run, "status": run.status,
            "stage": None if run.stage == "done" else run.stage, "progress": progress,
            "started_at": iso(started), "finished_at": iso(finished),
            "duration_s": int((finished - started).total_seconds()) if started and finished else None,
            "stats": {**{k: None for k in ("listings_seen", "unique_jobs", "new_jobs", "known_jobs", "duplicates",
                                           "passed_filters", "scored", "matched", "drafts_generated",
                                           "gmail_drafts_created", "errors")}, **(run.stats or {})},
            "errors": run.errors or []}


def summary(session: Session, start: str | None, end: str | None) -> dict:
    rng = date_range(start, end)
    jobs = _canonical(session)
    in_range = [j for j in jobs if _in(rng, j.first_seen_at)]

    def activity(min_rank: int) -> int:
        return sum(1 for when in first_reach(session, min_rank).values() if _in(rng, when))

    finished = session.scalars(select(Run).where(Run.status.in_(["succeeded", "partial"])).order_by(Run.id.desc())).first()
    successful = session.scalars(select(Run).where(Run.status == "succeeded").order_by(Run.id.desc())).first()
    attempted = session.scalars(select(Run).order_by(Run.id.desc())).first()
    stats = (finished.stats if finished else None) or {}
    matched_reach = first_reach(session, 1)
    return {
        "kpis": {
            "total_unique_jobs": len(in_range),
            "latest_run_discovered": stats.get("unique_jobs") if finished else None,
            "new_since_previous_run": stats.get("new_jobs") if finished else None,
            "previously_seen": stats.get("known_jobs") if finished else None,
            "passed_filters": sum(1 for j in jobs if _in(rng, j.first_passed_filters_at)),
            "matched": sum(1 for when in matched_reach.values() if _in(rng, when)),
            "shortlisted": activity(2), "drafts_generated": activity(3), "gmail_drafts_created": activity(4),
            "applied": activity(5), "employer_replied": activity(6), "interviews": activity(7), "offers": activity(8),
        },
        "latest_run": run_to_dict(finished), "last_successful_run": run_to_dict(successful),
        "last_attempted_run": run_to_dict(attempted),
    }


def _cohort(session: Session, rng) -> list[Job]:
    return [j for j in _canonical(session) if _in(rng, j.first_seen_at)]


def funnel(session: Session, start: str | None, end: str | None) -> list[dict]:
    rng = date_range(start, end)
    cohort = _cohort(session, rng)
    ids = {j.id for j in cohort}
    ranks = {a.job_id: a.reached_rank for a in session.scalars(select(Application)) if a.job_id in ids}
    counts: dict[str, int] = {}
    for key, _, min_rank in FUNNEL:
        if key == "discovered":
            counts[key] = len(cohort)
        elif key == "passed_filters":
            counts[key] = sum(1 for j in cohort if j.first_passed_filters_at is not None or ranks.get(j.id, 0) >= 1)
        else:
            counts[key] = sum(1 for j in cohort if ranks.get(j.id, 0) >= min_rank)
    out, prev = [], None
    for key, label, _ in FUNNEL:
        denominator = counts[prev] if prev else None
        out.append({"stage": key, "label": label, "count": counts[key], "of": prev,
                    "rate": round(counts[key] / denominator, 4) if denominator else None})
        prev = key
    return out


def rates(session: Session, start: str | None, end: str | None) -> dict:
    """Cohort = jobs whose first 'applied' event is in the range; numerators are cohort jobs that ever got further."""
    rng = date_range(start, end)
    applied = {jid for jid, when in first_reach(session, 5).items() if _in(rng, when)}
    ranks = {a.job_id: a.reached_rank for a in session.scalars(select(Application))}

    def rate(min_rank: int, name: str, definition: str) -> dict:
        num = sum(1 for jid in applied if ranks.get(jid, 0) >= min_rank)
        return {"value": round(num / len(applied), 4) if applied else None, "numerator": num,
                "denominator": len(applied), "definition": definition}

    return {"reply_rate": rate(6, "reply", "employer_replied / applied (jobs first applied in the range)"),
            "interview_rate": rate(7, "interview", "interview_scheduled / applied (jobs first applied in the range)"),
            "offer_rate": rate(8, "offer", "offer_received / applied (jobs first applied in the range)")}


def _bucket(d: date, bucket: str) -> date:
    return d - timedelta(days=d.weekday()) if bucket == "week" else d


def timeseries(session: Session, metric: str, bucket: str, start: str | None, end: str | None) -> list[dict]:
    rng = date_range(start, end)
    stamps: list[datetime] = []
    if metric == "discovered":  # distinct jobs seen per day (any run)
        rows = session.execute(select(JobObservation.job_id, JobObservation.seen_at)).all()
        seen: set[tuple[int, date]] = set()
        for job_id, at in rows:
            if _in(rng, at) and (job_id, at.date()) not in seen:
                seen.add((job_id, at.date()))
                stamps.append(at)
    elif metric == "new":
        stamps = [j.first_seen_at for j in _canonical(session) if _in(rng, j.first_seen_at)]
    else:
        rank = {"matched": 1, "applied": 5, "replied": 6}[metric]
        stamps = [when for when in first_reach(session, rank).values() if _in(rng, when)]
    counts = Counter(_bucket(at.date(), bucket) for at in stamps)
    day, last = _bucket(rng[0].date(), bucket), rng[1].date() - timedelta(days=1)
    step = timedelta(days=7 if bucket == "week" else 1)
    out = []
    while day <= last:
        out.append({"date": day.isoformat(), "value": counts.get(day, 0)})  # a quiet day is a real 0
        day += step
    return out


def distributions(session: Session, by: str, start: str | None, end: str | None) -> list[dict]:
    rng = date_range(start, end)
    cohort = _cohort(session, rng)
    if by == "score":
        edges = [(0, 19), (20, 39), (40, 59), (60, 79), (80, 100)]
        counts = Counter()
        for j in cohort:
            if j.score is not None:
                lo, hi = next(e for e in edges if e[0] <= j.score <= e[1])
                counts[f"{lo}-{hi}"] += 1
        return [{"label": f"{lo}-{hi}", "count": counts.get(f"{lo}-{hi}", 0)} for lo, hi in edges]
    if by == "status":
        statuses = {a.job_id: a.status for a in session.scalars(select(Application))}
        counts = Counter(statuses.get(j.id, "discovered") for j in cohort)
    else:
        attr = {"country": "country", "category": "category", "company": "company"}[by]
        counts = Counter((getattr(j, attr) or "Unknown") for j in cohort)
    return [{"label": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def runs_series(session: Session, limit: int = 30) -> list[dict]:
    runs = list(session.scalars(select(Run).order_by(Run.id.desc()).limit(limit)))[::-1]
    out = []
    for r in runs:
        s = r.stats or {}
        out.append({"run_id": r.id, "started_at": iso(r.started_at or r.created_at), "new_jobs": s.get("new_jobs"),
                    "known_jobs": s.get("known_jobs"), "matched": s.get("matched"),
                    "drafts_generated": s.get("drafts_generated"), "errors": s.get("errors")})
    return out
