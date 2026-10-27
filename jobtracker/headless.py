"""Unattended run (for a schedule):   .venv/bin/python -m jobtracker.headless [--gmail-drafts] [--mode full]

Fetches new jobs, scores them and writes application drafts INSIDE the app, then shows a macOS notification.
You review and edit the drafts later in the UI. Nothing reaches Gmail unless you pass --gmail-drafts (and even then
only drafts are created; nothing is ever sent).

Exit codes: 0 finished (also when there was nothing new), 1 the run failed, 2 not set up (resume / Gemini key),
3 another run is already active (skipped).
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from typing import Callable

from sqlalchemy import select

from . import db, draft_service, pipeline
from .models import EmailDraft
from .services import ensure_default_profile

Notify = Callable[[str], None]


def notify_macos(message: str) -> None:
    """Best effort: a failed notification must never fail the run."""
    try:
        text = json.dumps(message[:220])  # a JSON string is a valid AppleScript string literal
        subprocess.run(["osascript", "-e", f'display notification {text} with title "Job Tracker"'],
                       check=False, timeout=10, capture_output=True)
    except Exception:
        pass


def build_summary(run, drafts: list[EmailDraft], gmail_created: int) -> str:
    s = run.stats
    head = (f"Job Tracker {date.today().isoformat()}: run #{run.id} {run.status}. "
            f"{s.get('new_jobs') or 0} new jobs, {s.get('matched') or 0} matched, "
            f"{s.get('drafts_generated') or 0} drafts to review"
            + (f", {gmail_created} created in Gmail" if gmail_created else "") + f". Errors: {s.get('errors') or 0}.")
    lines = [head]
    for d in drafts[:15]:
        lines.append(f"  - {', '.join(j.title for j in d.jobs)[:70]} -> {d.recipient}")
    if run.errors:
        lines += [f"  ! [{e['stage']}] {e['message'][:120]}" for e in run.errors[:5]]
    if drafts:
        lines.append("Review them: start the app and open the Drafts page.")
    return "\n".join(lines)


def run_headless(gmail_drafts: bool = False, mode: str = "incremental", deps_factory=None,
                 notify: Notify = notify_macos) -> tuple[int, str]:
    if deps_factory is None:
        from .api import default_deps as deps_factory
    with db.session_scope() as session:
        profile = ensure_default_profile(session)
        session.commit()
        if draft_service.active_resume(session) is None:
            msg = "Not set up: no resume in the app. Open Settings and upload one."
            notify(msg)
            return 2, msg
        deps = deps_factory(session)
        if deps.ask is None:
            msg = "Not set up: GEMINI_API_KEY is missing in .env."
            notify(msg)
            return 2, msg
        if pipeline.active_run(session):
            return 3, "Another run is already active; skipped."
        run = pipeline.create_run(session, profile.id, mode=mode)
        run = pipeline.execute_run(session, run.id, deps)
        gmail_created = 0
        if gmail_drafts and run.status in ("succeeded", "partial"):
            if deps.gmail_create is None:
                run.errors = [*run.errors, {"stage": "gmail", "job_id": None, "message": "Gmail is not connected; drafts stay in the app."}]
            else:
                ids = [d_id for (d_id,) in session.execute(select(EmailDraft.id).where(
                    EmailDraft.run_id == run.id, EmailDraft.gmail_draft_id.is_(None), EmailDraft.status != "discarded"))]
                result = draft_service.create_gmail_drafts(session, ids, deps.gmail_create)
                gmail_created = len(result["created"])
                run.errors = [*run.errors, *({"stage": "gmail", "job_id": None, "message": f"draft {f['id']}: {f['message']}"}
                                             for f in result["failed"])]
                run.stats = {**run.stats, "gmail_drafts_created": gmail_created}
            session.commit()
        drafts = list(session.scalars(select(EmailDraft).where(EmailDraft.run_id == run.id).order_by(EmailDraft.id)))
        summary = build_summary(run, drafts, gmail_created)
        code = 1 if run.status == "failed" else 0
        notify(f"Run {run.status}: {run.stats.get('new_jobs') or 0} new jobs, {len(drafts)} drafts to review."
               if code == 0 else f"Run FAILED: {run.errors[-1]['message'][:150] if run.errors else 'see log'}")
        return code, summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gmail-drafts", action="store_true", help="also create Gmail drafts (drafts only, never sent)")
    ap.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    args = ap.parse_args(argv)
    code, summary = run_headless(gmail_drafts=args.gmail_drafts, mode=args.mode)
    print(summary)
    sys.exit(code)


if __name__ == "__main__":
    main()
