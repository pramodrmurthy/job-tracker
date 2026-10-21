import json
import re

import pytest

from jobtracker import db
from jobtracker.models import Resume
from jobtracker.pipeline import Deps
from jobtracker.services import DEFAULT_PROFILE_CONFIG, ensure_default_profile, set_setting
from jobtracker.sources.base import SourceError

RESUME = "Lead architect with 13+ years of experience. Built a RAG assistant over 100K+ documents."
BODY = (
    "I am writing to express my interest in the role described in your posting. I am a lead architect with 13+ years "
    "of experience, currently building production systems for a large enterprise client across several teams.\n\n"
    "Your posting asks for retrieval systems that run reliably in production, and that matches my recent work. I built "
    "a retrieval assistant over 100K+ documents that people use every day, and I owned its design, delivery and "
    "continuing improvement from the first prototype through to a stable service.\n\n"
    "My resume is attached, and it gives more detail on this work. I would welcome the opportunity to discuss the "
    "role in a short call at your convenience."
)


def make_job(i, title="AI Architect", email=None, country="UAE", years="10+", category="IT", **extra):
    return {"external_id": f"HA{i:04d}", "title": title, "company": None, "country": country, "city": country,
            "category": category, "sub_category": "x", "experience_level": years, "description": f"desc {i} truncated...",
            "skills": ["Python"], "hr_email": email or f"r{i}@corp{i}.com", "hr_name": None, "hr_phone": None,
            "salary_text": None, "employment_type": None, "work_mode": None, "visa_sponsored": True, "posted_at": None,
            "source_url": None, "raw": {"jobId": f"HA{i:04d}"}, **extra}


class FakeSource:
    name = "fake"

    def __init__(self, jobs, page_size=2):
        self.jobs, self.page_size = list(jobs), page_size
        self.list_calls = self.detail_calls = 0
        self.fail_details_for: set[str] = set()
        self.fail_list = False

    def list_pages(self, profile):
        for i in range(0, len(self.jobs), self.page_size):
            self.list_calls += 1
            if self.fail_list:
                raise SourceError("site down")
            yield [dict(j) for j in self.jobs[i:i + self.page_size]]

    def fetch_detail(self, external_id):
        self.detail_calls += 1
        if external_id in self.fail_details_for:
            raise SourceError("detail failed")
        job = next(j for j in self.jobs if j["external_id"] == external_id)
        return {**job, "description": f"FULL description of {job['title']} {external_id}"}


class FakeAsk:
    """Scores by title keyword, writes a valid email body. Records calls; can be told to fail."""

    def __init__(self):
        self.score_calls = self.draft_calls = 0
        self.fail_scoring = False
        self.scores: dict[str, int] = {}  # title -> score override

    def __call__(self, prompt):
        if "WHAT THE CANDIDATE WANTS" in prompt:
            self.score_calls += 1
            if self.fail_scoring:
                raise RuntimeError("rate limited")
            listing = json.loads(prompt.split("JOBS:\n", 1)[1])
            out = []
            for j in listing:
                score = self.scores.get(j["title"], 90 if "AI" in j["title"] else 30)
                out.append({"jobId": j["jobId"], "score": score, "relevant": score >= 70, "reason": f"reason for {j['title']}"})
            return json.dumps(out)
        self.draft_calls += 1
        return json.dumps({"body": BODY})


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setattr("jobtracker.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("jobtracker.config.RESUME_DIR", tmp_path / "resumes")
    db.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with db.session_scope() as s:
        ensure_default_profile(s)
        s.add(Resume(filename="Resume.pdf", text=RESUME, stored_path=None, is_active=True))
        set_setting(s, "sender", {"name": "Test User", "phone": "1", "email": "t@x.com", "linkedin": ""})
        set_setting(s, "preferences_text", "AI roles abroad")
        s.commit()
        yield s


@pytest.fixture()
def ask():
    return FakeAsk()


def run_pipeline(session, deps, mode="incremental", dry_run=False, **cfg_overrides):
    from jobtracker import pipeline
    from jobtracker.models import SearchProfile
    profile = session.get(SearchProfile, 1)
    if cfg_overrides:
        profile.config = {**DEFAULT_PROFILE_CONFIG, **profile.config, **cfg_overrides}
        session.commit()
    run = pipeline.create_run(session, 1, mode=mode, dry_run=dry_run)
    return pipeline.execute_run(session, run.id, deps)
