"""Scan the site and reconcile it with what you already emailed. No OpenAI, no drafts, no Gmail.

    uv run python -m jobtracker.scan             # list pages only (~20 seconds)
    uv run python -m jobtracker.scan --details   # also fetch every candidate's full description (~7 minutes)

It records every job ID in the database (so later runs know what is old), marks the jobs you already emailed as
'applied' (matched by recruiter + title), and writes appdata/reconciliation.csv.
"""

import argparse
import csv

from . import config, db, legacy, pipeline
from .services import ensure_default_profile
from .sources.hireabroad import HireAbroadSource


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true", help="also fetch full job details")
    args = ap.parse_args()
    with db.session_scope() as session:
        profile = ensure_default_profile(session)
        session.commit()
        run = pipeline.create_run(session, profile.id, mode="full")
        print(f"Scanning (run #{run.id}, full)...")
        run = pipeline.execute_run(session, run.id, pipeline.Deps(source=HireAbroadSource()),
                                   stop_after="details" if args.details else "fetch")
        s = run.stats
        print(f"\nRun {run.status}: {s['listings_seen']} listings, {s['unique_jobs']} unique jobs "
              f"({s['new_jobs']} new, {s['known_jobs']} already known), {s['duplicates']} duplicate listings.")
        for e in run.errors:
            print(f"  error [{e['stage']}]: {e['message']}")
        rep = legacy.report(session)
        path = config.DATA_DIR / "reconciliation.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["section", "recruiter", "job_id", "job_title", "status", "note"])
            for m in rep["matched"]:
                w.writerow(["already_emailed", m["recruiter"], m["job_id"], m["job_title"], m["status"], ""])
            for u in rep["unmatched"]:
                w.writerow(["not_found", u["recruiter"], "", "", "", f"no job with title starting '{u['title_start']}'"])
            for o in rep["other_jobs_from_same_recruiters"]:
                w.writerow(["same_recruiter_other_job", o["recruiter"], o["job_id"], o["title"], o["status"], "not emailed"])
        print(f"\nAlready emailed and now recorded by job ID: {len(rep['matched'])}")
        for m in rep["matched"]:
            print(f"  {m['job_id']}  {m['recruiter']:42} {m['job_title'][:60]}")
        print(f"\nNot found on the site any more (job closed or title differs): {len(rep['unmatched'])}")
        for u in rep["unmatched"]:
            print(f"  {u['recruiter']:42} title starts '{u['title_start']}'")
        print(f"\nOther jobs from the same recruiters, NOT emailed (these can still be drafted): "
              f"{len(rep['other_jobs_from_same_recruiters'])}")
        for o in rep["other_jobs_from_same_recruiters"][:40]:
            print(f"  {o['job_id']}  {o['recruiter']:42} {o['title'][:60]}")
        print(f"\nFull report: {path}")


if __name__ == "__main__":
    main()
