"""Dump real backend responses (seeded with fake jobs) to frontend/src/test/real_fixtures.json.

Run:  uv run python -m tests.dump_contract_fixtures
The frontend test `contract.test.ts` then checks that the shapes match what the UI (and its mock) expects.
"""

import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

tmp = tempfile.mkdtemp()
os.environ["JOBTRACKER_DATA_DIR"] = tmp

from jobtracker import db  # noqa: E402
from jobtracker.api import create_app  # noqa: E402
from jobtracker.models import Resume  # noqa: E402
from jobtracker.pipeline import Deps  # noqa: E402
from jobtracker.services import ensure_default_profile, set_setting  # noqa: E402

from tests.conftest import RESUME, FakeAsk, FakeSource, make_job  # noqa: E402

OUT = Path(__file__).parent.parent / "frontend" / "src" / "test" / "real_fixtures.json"
H = {"origin": "http://127.0.0.1:8000"}


def main() -> None:
    db.init_engine(f"sqlite:///{tmp}/fx.db")
    with db.session_scope() as s:
        ensure_default_profile(s)
        s.add(Resume(filename="Resume.pdf", text=RESUME, is_active=True))
        set_setting(s, "sender", {"name": "A", "phone": "1", "email": "a@x.com", "linkedin": "l"})
    src = FakeSource([make_job(1, "AI Architect"), make_job(2, "Sales Manager"), make_job(3, "AI Engineer", skills=["Go"])], 2)
    calls: list = []
    app = create_app(deps_factory=lambda s: Deps(src, FakeAsk(), lambda *a: ("gd", "gm")), sync_runs=True)
    c = TestClient(app)
    out: dict[str, dict] = {}

    def rec(method: str, path: str, query: dict | None = None, body=None):
        r = c.request(method, f"/api{path}", params=query, json=body, headers=H)
        assert r.status_code < 300, (method, path, r.status_code, r.text)
        out[f"{method} {path} {json.dumps(query or {}, sort_keys=True)}"] = {"method": method, "path": path, "query": query or {}, "body": body, "response": r.json()}
        return r.json()

    run = rec("POST", "/runs", body={"profile_id": 1, "mode": "full", "dry_run": False})
    rec("GET", "/runs", {"page": 1, "page_size": 20})
    rec("GET", f"/runs/{run['id']}")
    jobs = rec("GET", "/jobs", {"page_size": 50})
    job_id = jobs["items"][0]["id"]
    rec("GET", f"/jobs/{job_id}")
    rec("PATCH", f"/jobs/{job_id}", body={"status": "applied", "notes": "n"})
    rec("POST", "/jobs/bulk", body={"ids": [job_id], "status": "applied"})
    drafts = rec("GET", "/drafts", {"page_size": 50})
    rec("GET", f"/drafts/{drafts['items'][0]['id']}")
    rec("PATCH", f"/drafts/{drafts['items'][0]['id']}", body={"subject": "S"})
    rec("POST", "/drafts/gmail", body={"ids": [d["id"] for d in drafts["items"]]})
    rec("GET", "/settings")
    rec("GET", "/profiles")
    rec("GET", "/gmail/status")
    rec("GET", "/analytics/summary")
    rec("GET", "/analytics/funnel")
    rec("GET", "/analytics/rates")
    rec("GET", "/analytics/timeseries", {"metric": "applied", "bucket": "week"})
    for by in ("country", "category", "company", "score", "status"):
        rec("GET", "/analytics/distributions", {"by": by})
    rec("GET", "/analytics/runs")
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {len(out)} real responses to {OUT}")


if __name__ == "__main__":
    main()
