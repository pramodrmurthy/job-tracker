import json

import pytest
from sqlalchemy import select

from jobtracker import legacy, pipeline
from jobtracker.models import ContactedRecruiter, Job, LegacySent, StatusEvent, utcnow
from jobtracker.pipeline import Deps
from jobtracker.services import set_status

from .conftest import FakeSource, make_job, run_pipeline


@pytest.fixture()
def legacy_file(tmp_path, monkeypatch):
    path = tmp_path / "legacy_sent.json"
    path.write_text(json.dumps({"sent_on": "2026-10-18", "pairs": [
        {"email_start": "boss@a", "title_start": "AI Architect"},
        {"email_start": "gone@z", "title_start": "Vanished Role"},
    ]}))
    monkeypatch.setattr(legacy, "LEGACY_FILE", path)
    return path


def fetch_only(session, ask, src):
    run = pipeline.create_run(session, 1, mode="full")
    return pipeline.execute_run(session, run.id, Deps(src, ask), stop_after="details")


def test_legacy_emails_are_matched_to_jobs_by_recruiter_and_title_and_marked_applied(session, ask, legacy_file):
    session.add(ContactedRecruiter(email="boss@a.com", contacted_at=utcnow()))
    session.commit()
    src = FakeSource([make_job(1, "AI Architect Lead", email="boss@a.com"),   # sent (title starts with "AI Architect")
                      make_job(2, "AI Engineer", email="boss@a.com"),         # same recruiter, DIFFERENT job: not sent
                      make_job(3, "AI Architect", email="other@b.com")])      # same title, different recruiter: not sent
    fetch_only(session, ask, src)
    jobs = {j.external_id: j for j in session.scalars(select(Job))}
    assert jobs["HA0001"].application.status == "applied"
    assert jobs["HA0002"].application.status == "discovered" and jobs["HA0003"].application.status == "discovered"
    event = session.scalar(select(StatusEvent).where(StatusEvent.job_id == jobs["HA0001"].id, StatusEvent.to_status == "applied"))
    assert event.at.date().isoformat() == "2026-10-18" and "previous scripts" in event.note
    assert jobs["HA0001"].application.applied_at.date().isoformat() == "2026-10-18"


def test_legacy_marking_is_idempotent_and_never_overrides_a_user_status(session, ask, legacy_file):
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com")])
    fetch_only(session, ask, src)
    job = session.scalar(select(Job))
    set_status(session, job.application, "interview_scheduled", by="user")
    session.commit()
    fetch_only(session, ask, src)
    fetch_only(session, ask, src)
    session.refresh(job)
    assert job.application.status == "interview_scheduled"
    assert session.query(StatusEvent).filter_by(job_id=job.id, to_status="applied").count() == 1


def test_the_next_run_never_drafts_a_job_that_was_already_emailed(session, ask, legacy_file):
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com"), make_job(2, "AI Engineer", email="boss@a.com")])
    run = run_pipeline(session, Deps(src, ask))
    assert run.stats["drafts_generated"] == 1  # only the job that was NOT already sent
    from jobtracker.models import EmailDraft
    draft = session.scalar(select(EmailDraft))
    assert [j.title for j in draft.jobs] == ["AI Engineer"]
    assert ask.score_calls == 1  # and no tokens were spent scoring the already-sent job


def test_reconciliation_report(session, ask, legacy_file):
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com"), make_job(2, "AI Engineer", email="boss@a.com")])
    fetch_only(session, ask, src)
    rep = legacy.report(session)
    assert [m["job_id"] for m in rep["matched"]] == ["HA0001"]
    assert [u["recruiter"] for u in rep["unmatched"]] == ["gone@z"]
    assert [o["job_id"] for o in rep["other_jobs_from_same_recruiters"]] == ["HA0002"]
    assert session.scalar(select(LegacySent).where(LegacySent.email == "boss@a")) is not None


def test_fetch_only_scan_records_ids_but_needs_no_details_or_llm(session, ask, legacy_file):
    src = FakeSource([make_job(1, "AI Architect", email="boss@a.com"), make_job(2, "AI Engineer", email="boss@a.com")])
    run = pipeline.create_run(session, 1, mode="full")
    done = pipeline.execute_run(session, run.id, Deps(src), stop_after="fetch")
    assert done.status == "succeeded" and done.stats["new_jobs"] == 2
    assert src.detail_calls == 0 and ask.score_calls == 0
    assert {j.application.status for j in session.scalars(select(Job))} == {"applied", "discovered"}
