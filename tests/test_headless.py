from jobtracker import headless, pipeline
from jobtracker.models import EmailDraft, Resume
from jobtracker.pipeline import Deps
from sqlalchemy import select

from .conftest import FakeSource, make_job


def factory(src, ask, gmail=None):
    return lambda s: Deps(src, ask, gmail)


def run(session, src, ask, gmail=None, **kw):
    seen = []
    code, summary = headless.run_headless(deps_factory=factory(src, ask, gmail), notify=seen.append, **kw)
    return code, summary, seen


def test_headless_creates_drafts_in_the_app_but_not_in_gmail_by_default(session, ask):
    src = FakeSource([make_job(1, "AI Architect"), make_job(2, "Sales Manager")])
    gmail_calls = []
    code, summary, notes = run(session, src, ask, gmail=lambda *a: gmail_calls.append(a) or ("g", "m"))
    assert code == 0 and gmail_calls == []  # nothing reaches Gmail without --gmail-drafts
    assert "1 new jobs" not in summary and "2 new jobs" in summary and "1 drafts to review" in summary
    assert "AI Architect" in summary and "Review them" in summary
    assert notes and "2 new jobs" in notes[0]
    session.expire_all()
    assert session.scalar(select(EmailDraft)).status == "generated"


def test_headless_can_create_gmail_drafts_when_asked(session, ask):
    src = FakeSource([make_job(1, "AI Architect")])
    code, summary, _ = run(session, src, ask, gmail=lambda *a: ("gd1", "gm1"), gmail_drafts=True)
    assert code == 0 and "1 created in Gmail" in summary
    session.expire_all()
    assert session.scalar(select(EmailDraft)).gmail_draft_id == "gd1"


def test_headless_gmail_requested_but_not_connected_keeps_drafts(session, ask):
    code, summary, _ = run(session, FakeSource([make_job(1, "AI Architect")]), ask, gmail=None, gmail_drafts=True)
    assert code == 0 and "Gmail is not connected" in summary
    session.expire_all()
    assert session.scalar(select(EmailDraft)).status == "generated"


def test_headless_not_set_up_exit_codes(session, ask):
    code, msg, notes = run(session, FakeSource([]), None)  # no OpenAI key -> deps.ask is None
    assert code == 2 and "OPENAI_API_KEY" in msg and notes
    session.query(Resume).delete()
    session.commit()
    code, msg, _ = run(session, FakeSource([]), ask)
    assert code == 2 and "no resume" in msg


def test_headless_skips_when_a_run_is_already_active(session, ask):
    pipeline.create_run(session, 1)
    code, msg, notes = run(session, FakeSource([make_job(1, "AI Architect")]), ask)
    assert code == 3 and "already active" in msg and notes == []


def test_headless_reports_a_failed_run_with_exit_code_1(session, ask):
    src = FakeSource([make_job(1, "AI Architect")])
    src.fail_list = True
    code, summary, notes = run(session, src, ask)
    assert code == 1 and "failed" in summary.lower() and notes and "FAILED" in notes[0]


def test_headless_nothing_new_is_a_clean_success(session, ask):
    src = FakeSource([make_job(1, "AI Architect")])
    run(session, src, ask)
    code, summary, notes = run(session, src, ask)
    assert code == 0 and "0 new jobs" in summary and "0 drafts to review" in summary
