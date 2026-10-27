# Job Tracker

Find jobs on hireabroad.co.in, score them against your resume, draft tailored application emails, create
Gmail drafts (never sends), and track everything on a dashboard. Single user, runs locally, state in SQLite.

## Run it

```bash
uv sync
uv run python -m jobtracker.seed                 # once: imports your resume, preferences and sender details
cd frontend && npm install && npm run build      # once, and after UI changes
cd .. && uv run uvicorn jobtracker.main:app --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000. Always bind to 127.0.0.1; the app can create Gmail drafts.

### Restarting later (production command)
Setup is already done once `appdata/jobtracker.db` exists. From the project root (not `jobtracker/`):
```bash
uv run uvicorn jobtracker.main:app --host 127.0.0.1 --port 8000
```
Start a run from the UI, or from the terminal without the UI:
```bash
uv run python -m jobtracker.headless                  # fetch, score, draft inside the app; nothing goes to Gmail
uv run python -m jobtracker.headless --gmail-drafts   # also create Gmail drafts (never sends)
```
You never run `jobtracker/pipeline.py` directly; it is a library used by the UI, `headless` and `scan`.
If Gmail fails, the token has probably expired (7 days in Testing mode): Settings → Connect Gmail again.

### Updating your resume
Settings → Resume card → upload the new PDF/DOCX (5 MB max). It replaces the active resume; new runs use it.
Existing jobs, drafts, statuses and past scores are kept (unchanged jobs are not re-scored automatically).
`resume.txt` and `linkedin_profile.md` are only read by the one-time `seed` step; editing them later has no effect.

Development: `uv run uvicorn jobtracker.main:app --reload` plus `cd frontend && npm run dev` (proxies /api to :8000).
UI without a backend: `cd frontend && npm run dev:mock`.

## Configure
- `.env` in this folder: `GEMINI_API_KEY=...` and optionally `GEMINI_MODEL=...` (default `gemini-2.5-flash`).
- Gmail: put Google's OAuth `client_secret.json` in this folder, then Settings → Connect Gmail.
- Everything else (resume, preferences, filters, sender details) is in the app's Settings page.

## Scan and reconcile (do this before the first real run)
```bash
uv run python -m jobtracker.scan             # list pages only, about 20 seconds; add --details for full descriptions
```
Records every current job ID in the database, marks the jobs you already emailed as `applied` (matched by recruiter
address + start of the job title, from `appdata/legacy_sent.json`), and writes `appdata/reconciliation.csv`
(already emailed / not found / other jobs from the same recruiters). No OpenAI, no drafts, no Gmail.

## Run it automatically every week (macOS)
`uv run python -m jobtracker.headless` fetches new jobs, scores them, writes drafts INSIDE the app and shows a macOS
notification. Nothing reaches Gmail unless you add `--gmail-drafts`, and nothing is ever sent. Review the drafts later in the UI.

1. Move the project out of Downloads (macOS blocks background jobs there):
   `mv <this folder> ~/Projects/jobtracker && cd ~/Projects/jobtracker && uv sync`
2. `scripts/schedule.sh install` (Mondays 09:00; `WEEKDAY=3 HOUR=18 scripts/schedule.sh install` to change), then
   `scripts/schedule.sh run-now` to test, `status` to check, `uninstall` to remove. Log: `appdata/logs/headless.log`.
The Mac must be awake (a missed run starts when it wakes). Exit codes: 0 ok, 1 run failed, 2 not set up, 3 another run active.

## Notes for hosting on GitHub
Keep the repo PRIVATE. Never commit `.env`, `client_secret.json`, `token.json`, `appdata/` (database, resume, recruiter data)
or `resume.txt`; they are in `.gitignore`. Do not run the full pipeline on GitHub Actions: the Gmail login expires every 7 days
while the Google app is in Testing mode, the SQLite state does not persist between runs, and drafts need your review.

## How state works
Each run is stored with its stats and errors. Jobs are unique per (source, external id); reposts point at one
canonical job. Protection is per JOB ID: a job is never drafted twice. A recruiter you already emailed is highlighted in the Jobs list, but a
different job from them can still be drafted (the optional recruiter cooldown is 0 days by default). A second run only fetches what is new, never re-scores unchanged jobs, never duplicates drafts, and
never overrides a status you set. Retrying a failed run is always safe.

## Tests
`uv run pytest` (pipeline, deduplication, state, lifecycle, analytics, Gmail idempotency, API).

## Share with friends
`share/hireabroad_export.py` is a single stdlib-only script that downloads every job into one CSV.
It uses an undocumented endpoint that robots.txt disallows; read the notice at the top of the file first.
