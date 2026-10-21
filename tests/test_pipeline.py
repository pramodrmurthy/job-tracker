from sqlalchemy import func, select

from jobtracker import draft_service, pipeline
from jobtracker.models import (Application, Assessment, DraftJob, EmailDraft, Job, JobObservation, StatusEvent)
from jobtracker.pipeline import Deps
from jobtracker.services import set_status
from jobtracker.sources.base import SourceError

from .conftest import FakeSource, make_job, run_pipeline


def jobs():
    return [make_job(1, "AI Architect"), make_job(2, "Sales Manager"), make_job(3, "AI Engineer"),
            make_job(4, "Junior AI", years="3-5"), make_job(5, "AI Lead", country="INDIA")]


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_first_run_discovers_filters_scores_and_drafts(session, ask):
    src = FakeSource(jobs())
    run = run_pipeline(session, Deps(src, ask))
    assert run.status == "succeeded", run.errors
    s = run.stats
    assert (s["listings_seen"], s["new_jobs"], s["known_jobs"], s["duplicates"]) == (5, 5, 0, 0)
    # Junior AI (3-5 yrs) and the India job fail hard filters; the Sales Manager passes filters but scores low
    assert s["passed_filters"] == 3 and s["scored"] == 3 and s["matched"] == 2
    assert s["drafts_generated"] == 2 and s["gmail_drafts_created"] == 0
    statuses = {j.title: j.application.status for j in session.scalars(select(Job))}
    assert statuses["AI Architect"] == statuses["AI Engineer"] == "draft_generated"
    assert statuses["Sales Manager"] == "discovered"
    assert src.detail_calls == 3  # details only for jobs passing the cheap filters
    assert count(session, JobObservation) == 5
    assert all(d.source == "ai" for d in session.scalars(select(EmailDraft)))


def test_second_run_recognises_known_jobs_and_never_duplicates(session, ask):
    src = FakeSource(jobs())
    run_pipeline(session, Deps(src, ask))
    calls_after_first = (ask.score_calls, ask.draft_calls, src.detail_calls)
    run2 = run_pipeline(session, Deps(src, ask))
    assert run2.status == "succeeded"
    # incremental stops at the first page with nothing new (page size 2), so only that page is re-seen
    assert (run2.stats["new_jobs"], run2.stats["known_jobs"]) == (0, 2)
    assert run2.stats["drafts_generated"] == 0 and run2.stats["scored"] == 0
    run_full = run_pipeline(session, Deps(src, ask), mode="full")  # a full run re-sees everything, still no rework
    assert (run_full.stats["new_jobs"], run_full.stats["known_jobs"]) == (0, 5)
    assert (ask.score_calls, ask.draft_calls, src.detail_calls) == calls_after_first  # nothing re-done
    assert count(session, Job) == 5 and count(session, EmailDraft) == 2 and count(session, Assessment) == 3


def test_incremental_stops_at_first_fully_known_page_and_full_does_not(session, ask):
    src = FakeSource([make_job(i, "AI Architect") for i in range(1, 9)])  # 4 pages of 2
    run_pipeline(session, Deps(src, ask))
    src.list_calls = 0
    run_pipeline(session, Deps(src, ask))  # nothing new -> stops after page 1
    assert src.list_calls == 1
    src.list_calls = 0
    run_pipeline(session, Deps(src, ask), mode="full")
    assert src.list_calls == 4


def test_new_jobs_are_found_on_later_runs_and_statuses_are_preserved(session, ask):
    src = FakeSource([make_job(1, "AI Architect"), make_job(2, "AI Engineer")])
    run_pipeline(session, Deps(src, ask))
    job1 = session.scalar(select(Job).where(Job.external_id == "HA0001"))
    set_status(session, job1.application, "applied", by="user")
    session.commit()
    src.jobs.insert(0, make_job(3, "AI Principal"))  # newest first
    run3 = run_pipeline(session, Deps(src, ask))
    assert run3.stats["new_jobs"] == 1 and run3.stats["known_jobs"] >= 1
    session.refresh(job1)
    assert job1.application.status == "applied"  # pipeline never overrides a user-set status
    new = session.scalar(select(Job).where(Job.external_id == "HA0003"))
    assert new.application.status == "draft_generated"
    history = [e.to_status for e in session.scalars(select(StatusEvent).where(StatusEvent.job_id == job1.id).order_by(StatusEvent.id))]
    assert history == ["matched", "draft_generated", "applied"]


def test_duplicate_listings_share_one_canonical_job_and_one_draft(session, ask):
    same = dict(email="same@agency.com")
    src = FakeSource([make_job(1, "AI Architect", **same), make_job(2, "AI Architect", **same), make_job(3, "AI  architect!", **same)])
    run = run_pipeline(session, Deps(src, ask))
    assert (run.stats["new_jobs"], run.stats["duplicates"]) == (1, 2)
    assert run.stats["unique_jobs"] == 1 and count(session, Job) == 3  # rows kept, one canonical
    canon = {j.canonical_job_id for j in session.scalars(select(Job))}
    assert len(canon) == 1 and count(session, EmailDraft) == 1


def test_retry_after_scoring_failure_completes_without_duplicates(session, ask):
    src = FakeSource([make_job(i, "AI Architect") for i in range(1, 4)])
    ask.fail_scoring = True
    run1 = run_pipeline(session, Deps(src, ask))
    assert run1.status == "partial" and any(e["stage"] == "score" for e in run1.errors)
    assert count(session, Assessment) == 0 and count(session, EmailDraft) == 0
    ask.fail_scoring = False
    run2 = run_pipeline(session, Deps(src, ask))  # the "retry": same state, picks up where it stopped
    assert run2.status == "succeeded"
    assert count(session, Job) == 3 and count(session, Assessment) == 3 and count(session, EmailDraft) == 3
    run3 = run_pipeline(session, Deps(src, ask))
    assert count(session, Assessment) == 3 and count(session, EmailDraft) == 3 and run3.stats["drafts_generated"] == 0


def test_detail_failure_is_recorded_and_retried_next_run(session, ask):
    src = FakeSource([make_job(1, "AI Architect"), make_job(2, "AI Engineer")])
    src.fail_details_for = {"HA0002"}
    run1 = run_pipeline(session, Deps(src, ask))
    assert run1.status == "partial" and run1.stats["scored"] == 1
    src.fail_details_for = set()
    run2 = run_pipeline(session, Deps(src, ask))
    assert run2.status == "succeeded" and count(session, Assessment) == 2 and count(session, EmailDraft) == 2


def test_source_down_on_first_page_fails_the_run_cleanly(session, ask):
    src = FakeSource(jobs())
    src.fail_list = True
    run = run_pipeline(session, Deps(src, ask))
    assert run.status == "failed" and count(session, Job) == 0 and run.errors


def test_full_run_marks_missing_jobs_but_keeps_history(session, ask):
    src = FakeSource([make_job(1, "AI Architect"), make_job(2, "AI Engineer")])
    run_pipeline(session, Deps(src, ask))
    src.jobs = [make_job(1, "AI Architect")]  # job 2 disappears from the source
    run_pipeline(session, Deps(src, ask), mode="full")
    j2 = session.scalar(select(Job).where(Job.external_id == "HA0002"))
    assert j2.listing_status == "missing" and j2.application.status == "draft_generated"
    assert count(session, StatusEvent) >= 2  # history untouched


def test_one_draft_per_recruiter_lists_close_scores_together(session, ask):
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com"), make_job(2, "AI Engineer", email="boss@a.com")])
    run = run_pipeline(session, Deps(src, ask))
    assert run.stats["drafts_generated"] == 1
    d = session.scalar(select(EmailDraft))
    assert d.recipient == "boss@a.com" and len(d.jobs) == 2  # both 90: within the gap, so one email lists both


def test_score_gap_keeps_a_clearly_weaker_role_out_of_the_email(session, ask):
    ask.scores = {"AI Architect": 95, "AI Helper": 70}  # 25 points apart; the default gap is 10
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com"), make_job(2, "AI Helper", email="boss@a.com")])
    run_pipeline(session, Deps(src, ask))
    d = session.scalar(select(EmailDraft))
    assert [j.title for j in d.jobs] == ["AI Architect"]
    helper = session.scalar(select(Job).where(Job.title == "AI Helper"))
    assert helper.application.status == "matched"  # matched, but not pitched in this email


def test_changed_posting_is_rescored_and_keeps_its_status(session, ask):
    src = FakeSource([make_job(1, "AI Architect")])
    run_pipeline(session, Deps(src, ask))
    job = session.scalar(select(Job))
    assert job.application.status == "draft_generated"
    src.jobs[0]["skills"] = ["Python", "Rust"]  # the posting changed
    run_pipeline(session, Deps(src, ask), mode="full")
    session.refresh(job)
    assert job.content_changed_at is not None
    assert count(session, Assessment) == 2  # new content -> a fresh assessment, the old one is kept as history
    assert job.application.status == "draft_generated" and count(session, EmailDraft) == 1


def test_jobs_already_applied_or_dismissed_are_not_scored_again(session, ask):
    src = FakeSource([make_job(1, "AI Architect"), make_job(2, "AI Engineer")])
    run_pipeline(session, Deps(src, ask))
    first = session.scalar(select(Job).where(Job.external_id == "HA0001"))
    set_status(session, first.application, "applied", by="user")
    session.commit()
    src.jobs[0]["skills"] = ["Python", "Rust"]
    src.jobs[1]["skills"] = ["Python", "Rust"]
    run_pipeline(session, Deps(src, ask), mode="full")
    scored_for = {a.job_id for a in session.scalars(select(Assessment)) if a.content_hash != first.content_hash}
    assert count(session, Assessment) == 3  # the applied job kept its single assessment; the other was re-scored


def test_cooldown_blocks_a_second_draft_for_a_recently_contacted_recruiter(session, ask):
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com")])
    run_pipeline(session, Deps(src, ask))
    draft = session.scalar(select(EmailDraft))
    draft_service.create_gmail_drafts(session, [draft.id], lambda *a: ("g1", "m1"))
    src.jobs.insert(0, make_job(2, "AI Engineer", email="boss@a.com"))
    run = run_pipeline(session, Deps(src, ask), cooldown_days=30)  # recruiter-wide cooldown is opt-in
    assert run.stats["drafts_generated"] == 0 and count(session, EmailDraft) == 1


def test_gmail_draft_creation_is_idempotent(session, ask):
    src = FakeSource([make_job(1, "AI Architect")])
    run_pipeline(session, Deps(src, ask))
    draft = session.scalar(select(EmailDraft))
    calls = []

    def create(to, subject, body, attachment):
        calls.append(to)
        return f"gd{len(calls)}", f"gm{len(calls)}"

    first = draft_service.create_gmail_drafts(session, [draft.id], create)
    second = draft_service.create_gmail_drafts(session, [draft.id], create)
    assert len(first["created"]) == 1 and second == {"created": [], "failed": []} and len(calls) == 1
    session.refresh(draft)
    assert draft.status == "gmail_draft" and draft.gmail_draft_id == "gd1"
    assert draft.jobs[0].application.status == "gmail_draft_created"


def test_gmail_failure_is_reported_and_not_marked_created(session, ask):
    run_pipeline(session, Deps(FakeSource([make_job(1, "AI Architect")]), ask))
    draft = session.scalar(select(EmailDraft))

    def boom(*a):
        raise RuntimeError("quota")

    res = draft_service.create_gmail_drafts(session, [draft.id], boom)
    assert res["created"] == [] and res["failed"][0]["id"] == draft.id
    session.refresh(draft)
    assert draft.gmail_draft_id is None and draft.status == "generated"


def test_auto_gmail_and_dry_run_flags(session, ask):
    src = FakeSource([make_job(1, "AI Architect")])
    dry = run_pipeline(session, Deps(src, ask, gmail_create=lambda *a: ("g", "m")), dry_run=True)
    assert dry.stats["scored"] == 1 and count(session, EmailDraft) == 0  # dry run: scored, no drafts
    real = run_pipeline(session, Deps(src, ask, gmail_create=lambda *a: ("g", "m")), auto_gmail_drafts=True)
    assert real.stats["gmail_drafts_created"] == 1
    assert session.scalar(select(EmailDraft)).status == "gmail_draft"


def test_auto_gmail_without_connection_reports_error_but_keeps_drafts(session, ask):
    run = run_pipeline(session, Deps(FakeSource([make_job(1, "AI Architect")]), ask), auto_gmail_drafts=True)
    assert run.status == "partial" and count(session, EmailDraft) == 1
    assert any(e["stage"] == "gmail" for e in run.errors)


def test_missing_resume_is_reported_not_crashed(session, ask):
    from jobtracker.models import Resume
    session.query(Resume).delete()
    session.commit()
    run = run_pipeline(session, Deps(FakeSource([make_job(1, "AI Architect")]), ask))
    assert run.status == "partial" and any("resume" in e["message"].lower() for e in run.errors)


def test_only_one_active_run_and_cancel(session, ask):
    run = pipeline.create_run(session, 1)
    try:
        pipeline.create_run(session, 1)
        assert False, "second active run must be refused"
    except RuntimeError:
        pass
    run.cancel_requested = True
    session.commit()
    done = pipeline.execute_run(session, run.id, Deps(FakeSource(jobs()), ask))
    assert done.status == "cancelled"


def test_interrupted_runs_are_marked_failed_on_restart(session):
    run = pipeline.create_run(session, 1)
    assert pipeline.mark_interrupted_runs(session) == 1
    session.refresh(run)
    assert run.status == "failed" and pipeline.active_run(session) is None


def test_imported_contacted_recruiters_are_on_cooldown(session, ask):
    from datetime import timedelta
    from jobtracker.models import ContactedRecruiter, utcnow
    session.add(ContactedRecruiter(email="boss@a.com", contacted_at=utcnow() - timedelta(days=3)))
    session.add(ContactedRecruiter(email="old@b.com", contacted_at=utcnow() - timedelta(days=90)))  # cooldown is 30 days
    session.commit()
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com"), make_job(2, "AI Engineer", email="old@b.com")])
    run = run_pipeline(session, Deps(src, ask), cooldown_days=30)
    assert run.stats["drafts_generated"] == 1
    assert session.scalar(select(EmailDraft)).recipient == "old@b.com"  # the recently contacted one is skipped


def test_same_recruiter_different_job_is_drafted_when_the_cooldown_is_off(session, ask):
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com")])
    run_pipeline(session, Deps(src, ask))
    src.jobs.insert(0, make_job(2, "AI Engineer", email="boss@a.com"))  # a different job, same recruiter
    run = run_pipeline(session, Deps(src, ask))  # default cooldown_days is 0: protection is per job, not per recruiter
    assert run.stats["drafts_generated"] == 1 and count(session, EmailDraft) == 2
    again = run_pipeline(session, Deps(src, ask))
    assert again.stats["drafts_generated"] == 0 and count(session, EmailDraft) == 2  # the same job is never redone


def test_scan_only_mode_fetches_and_compares_without_scoring_or_drafting(session, ask):
    src = FakeSource(jobs())
    run = pipeline.create_run(session, 1, mode="full")
    done = pipeline.execute_run(session, run.id, Deps(src, ask), stop_after="details")
    assert done.status == "succeeded" and done.stats["new_jobs"] == 5 and src.detail_calls == 3
    assert ask.score_calls == 0 and ask.draft_calls == 0 and count(session, Assessment) == 0 and count(session, EmailDraft) == 0


def test_resume_attachment_is_found_after_the_project_folder_moves(session, tmp_path, monkeypatch):
    from jobtracker import config
    from jobtracker.models import Resume
    folder = tmp_path / "new_home" / "resumes"
    folder.mkdir(parents=True)
    (folder / "abc_Resume.pdf").write_bytes(b"%PDF-1.4 test")
    monkeypatch.setattr(config, "RESUME_DIR", folder)
    moved = Resume(filename="Resume.pdf", text="x", stored_path="/old/location/that/no/longer/exists/abc_Resume.pdf")
    assert draft_service.resume_file(moved) == folder / "abc_Resume.pdf"
    assert draft_service.resume_file(Resume(filename="r", text="x", stored_path="/nowhere/gone.pdf")) is None
    assert draft_service.resume_file(Resume(filename="r", text="x", stored_path=None)) is None
