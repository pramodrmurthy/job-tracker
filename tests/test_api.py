import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from jobtracker import pipeline
from jobtracker.api import create_app
from jobtracker.models import Application, EmailDraft, Job, Run
from jobtracker.pipeline import Deps

from .conftest import FakeAsk, FakeSource, RESUME, make_job

H = {"origin": "http://127.0.0.1:8000"}


@pytest.fixture()
def env(session):
    src = FakeSource([make_job(1, "AI Architect"), make_job(2, "Sales Manager"), make_job(3, "AI Engineer"),
                      make_job(4, "AI Lead", country="SINGAPORE")], page_size=2)
    ask = FakeAsk()
    gmail_calls = []

    def create(to, subject, body, attachment):
        gmail_calls.append(to)
        return f"gd{len(gmail_calls)}", f"gm{len(gmail_calls)}"

    holder = {"gmail": create}
    app = create_app(deps_factory=lambda s: Deps(src, ask, holder["gmail"]), sync_runs=True)
    client = TestClient(app)
    return type("Env", (), {"client": client, "src": src, "ask": ask, "gmail_calls": gmail_calls, "holder": holder,
                            "session": session})


def start(env, **body):
    r = env.client.post("/api/runs", json={"profile_id": 1, "mode": "full", **body}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_settings_never_expose_the_api_key(env):
    assert env.client.get("/api/health").json() == {"status": "ok"}
    r = env.client.put("/api/settings", json={"sender": {"name": "Alex", "bogus": "x"}, "openai_model": "m1"}, headers=H)
    assert r.status_code == 200
    s = r.json()
    assert s["sender"]["name"] == "Alex" and "bogus" not in s["sender"] and s["openai_model"] == "m1"
    assert s["sender"]["email"] == "t@x.com"  # partial update keeps the other fields
    assert "openai_key_set" in s and "OPENAI_API_KEY" not in str(s) and "sk-" not in str(s)
    assert s["resume"]["filename"] == "Resume.pdf"


def test_resume_upload_validation_and_versioning(env):
    good = ("Experienced engineer. " * 20).encode()
    r = env.client.post("/api/resume", files={"file": ("../../etc/My CV.txt", good, "text/plain")}, headers=H)
    assert r.status_code == 200 and "/" not in r.json()["filename"] and r.json()["chars"] > 100
    assert env.client.post("/api/resume", files={"file": ("a.exe", good, "application/octet-stream")}, headers=H).status_code == 422
    assert env.client.post("/api/resume", files={"file": ("a.pdf", b"not a pdf at all", "application/pdf")}, headers=H).status_code == 422
    assert env.client.post("/api/resume", files={"file": ("a.txt", b"too short", "text/plain")}, headers=H).status_code == 422
    big = b"x" * (5 * 1024 * 1024 + 10)
    assert env.client.post("/api/resume", files={"file": ("a.txt", big, "text/plain")}, headers=H).status_code == 422
    from jobtracker.models import Resume
    env.session.expire_all()
    assert env.session.scalar(select(func.count()).select_from(Resume)) == 2  # old version kept
    assert env.session.scalar(select(func.count()).select_from(Resume).where(Resume.is_active)) == 1


def test_profile_validation_and_roundtrip(env):
    p = env.client.get("/api/profiles/1").json()
    p.update(min_years=12, threshold=75)
    assert env.client.put("/api/profiles/1", json=p, headers=H).json()["threshold"] == 75
    p.update(min_years=20, max_years=5)
    assert env.client.put("/api/profiles/1", json=p, headers=H).status_code == 422
    p.update(min_years=5, max_years=None, threshold=300)
    assert env.client.put("/api/profiles/1", json=p, headers=H).status_code == 422
    assert env.client.get("/api/profiles/99").status_code == 404


def test_run_lifecycle_and_conflict(env):
    run = start(env)
    assert run["status"] == "succeeded" and run["stats"]["new_jobs"] == 4 and run["stats"]["drafts_generated"] == 3
    assert env.client.get(f"/api/runs/{run['id']}").json()["stats"]["scored"] == 4  # the low-scoring Sales job is scored too
    assert env.client.get("/api/runs").json()["total"] == 1
    pipeline.create_run(env.session, 1)  # an active run exists
    assert env.client.post("/api/runs", json={"profile_id": 1}, headers=H).status_code == 409
    env.session.expire_all()
    active = env.session.scalar(select(Run).where(Run.status == "queued"))
    assert env.client.post(f"/api/runs/{active.id}/cancel", headers=H).json()["status"] == "queued"
    assert env.client.post(f"/api/runs/{run['id']}/cancel", headers=H).status_code == 409  # finished
    assert env.client.get("/api/runs/999").status_code == 404
    pipeline.mark_interrupted_runs(env.session)
    retry = env.client.post(f"/api/runs/{active.id}/retry", headers=H)
    assert retry.status_code == 201 and retry.json()["status"] == "succeeded"


def test_jobs_listing_filters_detail_and_status_changes(env):
    start(env)
    items = env.client.get("/api/jobs").json()
    assert items["total"] == 4
    top = env.client.get("/api/jobs?sort=score&order=desc&page_size=2").json()
    assert len(top["items"]) == 2 and top["total"] == 4 and top["items"][0]["score"] == 90
    assert env.client.get("/api/jobs?country=singapore").json()["total"] == 1
    assert env.client.get("/api/jobs?query=sales").json()["items"][0]["title"] == "Sales Manager"
    assert env.client.get("/api/jobs?has_draft=true").json()["total"] == 3
    assert env.client.get("/api/jobs?has_draft=false").json()["total"] == 1
    assert env.client.get("/api/jobs?status=draft_generated").json()["total"] == 3
    assert env.client.get("/api/jobs?status=nonsense").status_code == 422
    assert env.client.get("/api/jobs?new_only=true").json()["total"] == 4
    job_id = top["items"][0]["id"]
    detail = env.client.get(f"/api/jobs/{job_id}").json()
    assert detail["assessment"]["score"] == 90 and detail["drafts"] and detail["description"].startswith("FULL")
    patched = env.client.patch(f"/api/jobs/{job_id}", json={"status": "applied", "notes": "emailed Anna"}, headers=H).json()
    assert patched["application"]["status"] == "applied" and patched["application"]["applied_at"]
    assert patched["history"][-1] == {**patched["history"][-1], "from": "gmail_draft_created" if False else "draft_generated", "to": "applied", "by": "user"}
    assert env.client.patch(f"/api/jobs/{job_id}", json={"status": "bogus"}, headers=H).status_code == 422
    assert env.client.post("/api/jobs/bulk", json={"ids": [job_id, 99999], "status": "applied"}, headers=H).json() == {"updated": 0}
    assert env.client.get("/api/jobs/99999").status_code == 404


def test_rescore_updates_the_job(env):
    start(env)
    sales = env.client.get("/api/jobs?query=sales").json()["items"][0]
    env.ask.scores = {"Sales Manager": 77}
    r = env.client.post(f"/api/jobs/{sales['id']}/rescore", headers=H)
    assert r.status_code == 200 and r.json()["score"] == 77 and r.json()["relevant"] is True


def test_drafts_edit_regenerate_and_gmail_flow(env):
    start(env)
    drafts = env.client.get("/api/drafts").json()
    assert drafts["total"] == 3
    d = drafts["items"][0]
    edited = env.client.patch(f"/api/drafts/{d['id']}", json={"subject": "New subject", "status": "approved"}, headers=H).json()
    assert edited["subject"] == "New subject" and edited["edited"] is True and edited["status"] == "approved"
    regen = env.client.post(f"/api/drafts/{d['id']}/regenerate", headers=H).json()
    assert regen["edited"] is False and regen["subject"].startswith("Application:")
    res = env.client.post("/api/drafts/gmail", json={"ids": [x["id"] for x in drafts["items"]]}, headers=H).json()
    assert len(res["created"]) == 3 and res["failed"] == [] and len(env.gmail_calls) == 3
    again = env.client.post("/api/drafts/gmail", json={"ids": [d["id"]]}, headers=H).json()
    assert again == {"created": [], "failed": []} and len(env.gmail_calls) == 3  # idempotent
    assert env.client.patch(f"/api/drafts/{d['id']}", json={"subject": "x"}, headers=H).status_code == 409
    assert env.client.post(f"/api/drafts/{d['id']}/regenerate", headers=H).status_code == 409
    got = env.client.get(f"/api/drafts/{d['id']}").json()
    assert got["status"] == "gmail_draft" and got["gmail_url"].endswith("compose=gm1")
    md = env.client.get(f"/api/drafts/{d['id']}/markdown")
    assert md.headers["content-type"].startswith("text/markdown") and got["subject"] in md.text  # regenerate reset the subject
    assert env.client.get("/api/jobs?status=gmail_draft_created").json()["total"] == 3
    env.holder["gmail"] = None
    assert env.client.post("/api/drafts/gmail", json={"ids": [d["id"]]}, headers=H).status_code == 400


def test_analytics_agree_with_the_database(env):
    start(env)
    jobs = env.client.get("/api/jobs").json()["items"]
    first = next(j for j in jobs if j["title"] == "AI Architect")
    second = next(j for j in jobs if j["title"] == "AI Engineer")
    for jid, status in [(first["id"], "applied"), (first["id"], "employer_replied"), (first["id"], "interview_scheduled"),
                        (second["id"], "applied")]:
        env.client.patch(f"/api/jobs/{jid}", json={"status": status}, headers=H)
    s = env.client.get("/api/analytics/summary").json()
    k = s["kpis"]
    assert k["total_unique_jobs"] == 4 and k["matched"] == 3 and k["applied"] == 2
    assert k["employer_replied"] == 1 and k["interviews"] == 1 and k["offers"] == 0
    assert s["latest_run"]["stats"]["new_jobs"] == 4 and k["new_since_previous_run"] == 4
    # cross-check against raw table counts
    env.session.expire_all()
    assert k["applied"] == env.session.scalar(select(func.count()).select_from(Application).where(Application.reached_rank >= 5))
    f = {x["stage"]: x for x in env.client.get("/api/analytics/funnel").json()}
    assert [f[x]["count"] for x in ("discovered", "passed_filters", "matched", "drafted", "gmail_drafted", "applied", "replied", "interviewed", "offered")] == [4, 4, 3, 3, 2, 2, 1, 1, 0]
    # a job counts at a stage if it reached that stage OR ANY LATER ONE, so applying implies the earlier stages
    assert f["applied"]["of"] == "gmail_drafted" and f["applied"]["rate"] == 1.0
    assert f["matched"]["rate"] == 0.75 and all((x["rate"] is None or x["rate"] <= 1) for x in f.values())
    rates = env.client.get("/api/analytics/rates").json()
    assert rates["reply_rate"] == {**rates["reply_rate"], "value": 0.5, "numerator": 1, "denominator": 2}
    assert rates["offer_rate"]["value"] == 0.0 and rates["offer_rate"]["denominator"] == 2
    ts = env.client.get("/api/analytics/timeseries?metric=applied").json()
    assert sum(p["value"] for p in ts) == 2 and len(ts) >= 90  # quiet days are real zeros
    dist = {x["label"]: x["count"] for x in env.client.get("/api/analytics/distributions?by=country").json()}
    assert dist == {"UAE": 3, "SINGAPORE": 1}
    assert sum(x["count"] for x in env.client.get("/api/analytics/distributions?by=score").json()) == 4
    assert env.client.get("/api/analytics/runs").json()[0]["new_jobs"] == 4
    assert env.client.get("/api/analytics/summary?from=2030-01-01&to=2030-02-01").json()["kpis"]["total_unique_jobs"] == 0
    assert env.client.get("/api/analytics/summary?from=2030-02-01&to=2030-01-01").status_code == 422


def test_empty_database_returns_nulls_not_zeros_for_run_metrics(env):
    k = env.client.get("/api/analytics/summary").json()["kpis"]
    assert k["latest_run_discovered"] is None and k["new_since_previous_run"] is None
    assert k["total_unique_jobs"] == 0 and k["applied"] == 0
    assert all(x["rate"] is None for x in env.client.get("/api/analytics/funnel").json())
    assert env.client.get("/api/analytics/rates").json()["reply_rate"]["value"] is None


def test_cross_site_writes_and_bad_hosts_are_refused(env):
    r = env.client.post("/api/gmail/disconnect", headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert env.client.get("/api/health", headers={"host": "evil.example"}).status_code == 400
    assert env.client.get("/api/does-not-exist").status_code == 404


def test_built_frontend_is_served_with_spa_fallback_and_no_path_traversal(session):
    from jobtracker import config
    if not (config.FRONTEND_DIST / "index.html").exists():
        pytest.skip("frontend not built (cd frontend && npm run build)")
    client = TestClient(create_app(sync_runs=True))
    index = client.get("/")
    assert index.status_code == 200 and "<div id=\"root\">" in index.text
    assert client.get("/jobs/12").text == index.text  # client-side route falls back to index.html
    asset = next((config.FRONTEND_DIST / "assets").glob("*.js")).name
    assert client.get(f"/assets/{asset}").status_code == 200
    assert client.get("/api/nope").status_code == 404 and "<div" not in client.get("/api/nope").text
    leak = client.get("/..%2f..%2f..%2f..%2fetc%2fpasswd")
    assert "root:" not in leak.text and leak.text == index.text


def test_recruiter_contacted_badge_and_filter(env):
    from datetime import timedelta
    from jobtracker.models import ContactedRecruiter, utcnow
    env.session.add(ContactedRecruiter(email="R1@corp1.com", contacted_at=utcnow() - timedelta(days=5)))  # mixed case on purpose
    env.session.commit()
    start(env)
    items = {j["title"]: j for j in env.client.get("/api/jobs").json()["items"]}
    assert items["AI Architect"]["recruiter_contacted_at"] is not None  # recruiter r1@corp1.com was contacted before
    assert items["AI Engineer"]["recruiter_contacted_at"] is None
    assert env.client.get("/api/jobs?recruiter_contacted=true").json()["total"] == 1
    assert env.client.get("/api/jobs?recruiter_contacted=false").json()["total"] == 3
    # a job still gets a draft: the badge informs, it does not block
    assert items["AI Architect"]["has_draft"] is True
    # marking a different job applied marks THAT recruiter as contacted too
    eng = items["AI Engineer"]["id"]
    env.client.patch(f"/api/jobs/{eng}", json={"status": "applied"}, headers=H)
    assert env.client.get(f"/api/jobs/{eng}").json()["recruiter_contacted_at"] is not None
    assert env.client.get("/api/jobs?recruiter_contacted=true").json()["total"] == 2
