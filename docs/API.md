# Job Tracker: API contract (single user, local, no auth)

Backend: FastAPI + SQLite, package `jobtracker/`, served at http://127.0.0.1:8000. All routes are under `/api`.
Frontend: Vite + React + TypeScript + Tailwind in `frontend/`; dev server proxies `/api` to :8000; the built
`frontend/dist` is served by FastAPI at `/` so one command runs everything.

Conventions
- JSON. Timestamps are ISO-8601 UTC strings. Missing data is `null` (never 0): the UI shows "-" for null and "0" for a real zero.
- Lists: `?page=1&page_size=50` -> `{ "items": [...], "total": N }`.
- Errors: HTTP 4xx/5xx with `{ "detail": "message" }`. 409 = conflict (e.g. a run is already active).

## Status values (application lifecycle)
`discovered, matched, shortlisted, draft_generated, gmail_draft_created, applied, employer_replied,
interview_scheduled, interview_completed, offer_received, rejected, withdrawn, closed, not_interested`
Stage rank used for the funnel (a job counts at a stage if it EVER reached it):
discovered 0, matched 1, shortlisted 2, draft_generated 3, gmail_draft_created 4, applied 5, employer_replied 6,
interview_scheduled 7, interview_completed 7, offer_received 8. rejected / withdrawn / closed / not_interested do not lower the reached rank.

## Settings
GET  /api/settings ->
```json
{ "sender": {"name": "", "phone": "", "email": "", "linkedin": ""},
  "preferences_text": "", "availability_line": "", "openai_model": "gpt-4o-mini",
  "openai_key_set": true,
  "resume": {"id": 1, "filename": "Resume.pdf", "uploaded_at": "...", "chars": 4300} | null,
  "gmail": {"client_secret_present": true, "connected": false, "account": null} }
```
PUT  /api/settings   body: any subset of {sender, preferences_text, availability_line, openai_model}. Never accepts or returns the API key.
POST /api/resume     multipart `file` (pdf, docx or txt, max 5 MB) -> the `resume` object above. Replaces the active resume (old versions are kept).

## Search profiles (one default profile, id 1, but the API is list-shaped)
GET /api/profiles -> `[Profile]`;  GET /api/profiles/{id};  PUT /api/profiles/{id} (full Profile body)
```json
Profile = { "id": 1, "name": "Default",
  "categories": ["IT"], "min_years": 10, "max_years": null,
  "countries_include": [], "countries_exclude": ["INDIA"],
  "keywords_include": [], "keywords_exclude": [],
  "threshold": 60, "score_gap": 10, "cooldown_days": 30, "auto_gmail_drafts": false }
```

## Runs
POST /api/runs  body `{"profile_id": 1, "mode": "incremental" | "full", "dry_run": false}` -> `Run` (status `queued`). 409 if one is already queued/running.
GET  /api/runs?page&page_size -> `{items:[Run], total}` (newest first);  GET /api/runs/{id} -> `Run`
POST /api/runs/{id}/cancel -> `Run`;  POST /api/runs/{id}/retry -> new `Run` (continues from stored state; never duplicates)
```json
Run = { "id": 7, "profile_id": 1, "mode": "incremental", "dry_run": false,
  "status": "queued|running|succeeded|partial|failed|cancelled",
  "stage": "fetch|details|filter|score|draft|gmail|done|null",
  "progress": {"done": 120, "total": 340} | null,
  "started_at": "...", "finished_at": "..." | null, "duration_s": 512 | null,
  "stats": { "listings_seen": 0, "unique_jobs": 0, "new_jobs": 0, "known_jobs": 0, "duplicates": 0,
             "passed_filters": 0, "scored": 0, "matched": 0, "drafts_generated": 0, "gmail_drafts_created": 0, "errors": 0 },
  "errors": [{"stage": "score", "job_id": 12 | null, "message": "..."}] }
```
`stats` values are null for stages that have not run yet.

## Jobs
GET /api/jobs ?query &recruiter_contacted(bool) &status &min_score &max_score &country &category &run_id &new_only(bool) &has_draft(bool) &sort(score|first_seen|title) &order(asc|desc) &page &page_size -> `{items:[JobSummary], total}`
```json
JobSummary = { "id": 1, "external_id": "HA171026098", "title": "", "company": null, "country": "UAE", "city": "",
  "category": "IT", "sub_category": "", "experience_level": "10+", "hr_email": "x@y.com" | null,
  "score": 85 | null, "relevant": true | null, "reason": "" | null,
  "status": "matched", "first_seen_at": "...", "last_seen_at": "...", "listing_status": "active|missing",
  "has_draft": false,
  "recruiter_contacted_at": "2026-10-18T00:00:00Z" | null }
```
GET /api/jobs/{id} -> `JobDetail` = JobSummary +
`{ "description": "", "skills": [], "salary_text": null, "employment_type": null, "work_mode": null, "visa_sponsored": null,
   "hr_name": null, "hr_phone": null, "posted_at": null, "source": "hireabroad",
   "assessment": {"score": 85, "relevant": true, "reason": "", "model": "gpt-4o-mini", "created_at": "..."} | null,
   "application": {"status": "matched", "notes": "", "applied_at": null, "last_follow_up_at": null},
   "drafts": [DraftSummary], "history": [{"from": "matched", "to": "applied", "at": "...", "by": "user|system", "note": null}] }`
PATCH /api/jobs/{id}  body `{ "status"?: Status, "notes"?: string }` -> JobDetail (status change appends to history, by "user")
POST  /api/jobs/bulk  body `{ "ids": [1,2], "status": "shortlisted" }` -> `{ "updated": 2 }`
POST  /api/jobs/{id}/rescore -> JobDetail (re-runs the LLM assessment now)

## Drafts (application emails)
GET /api/drafts ?status &page &page_size -> `{items:[Draft], total}`;  GET /api/drafts/{id} -> Draft
```json
Draft = { "id": 3, "recipient": "x@y.com", "job_ids": [1, 2], "job_titles": ["AI Architect"], "countries": ["UAE"],
  "subject": "", "body": "", "source": "ai|template", "status": "generated|approved|gmail_draft|discarded",
  "gmail_draft_id": null, "gmail_url": null, "edited": false, "created_at": "...", "updated_at": "..." }
DraftSummary = { "id", "recipient", "subject", "status", "gmail_draft_id" }
```
PATCH /api/drafts/{id} body `{subject?, body?, status?: "generated|approved|discarded"}` -> Draft (editing sets `edited: true`; a draft already in Gmail is read-only: 409)
POST  /api/drafts/{id}/regenerate -> Draft (409 if already in Gmail)
POST  /api/drafts/gmail body `{ "ids": [3, 4] }` -> `{ "created": [{"id": 3, "gmail_draft_id": "r123"}], "failed": [{"id": 4, "message": ""}] }`
      Creates Gmail DRAFTS only (never sends). Idempotent: a draft that already has a gmail_draft_id is skipped, not duplicated.
GET   /api/drafts/{id}/markdown -> text/markdown download (subject, recipient, job links, body)

## Gmail
GET  /api/gmail/status -> `{ "client_secret_present": true, "connected": false, "account": null }`
POST /api/gmail/connect -> status (starts the Google OAuth consent in the user's browser; blocks until done). 400 if client_secret.json is missing.
POST /api/gmail/disconnect -> status (deletes the stored token)

## Analytics (all accept optional `from` and `to` as YYYY-MM-DD, default last 90 days)
GET /api/analytics/summary ->
```json
{ "kpis": { "total_unique_jobs": 0, "latest_run_discovered": null, "new_since_previous_run": null,
    "previously_seen": null, "passed_filters": 0, "matched": 0, "shortlisted": 0, "drafts_generated": 0,
    "gmail_drafts_created": 0, "applied": 0, "employer_replied": 0, "interviews": 0, "offers": 0 },
  "latest_run": Run | null, "last_successful_run": Run | null, "last_attempted_run": Run | null }
```
GET /api/analytics/funnel -> (cohort = unique jobs first discovered in the range; a job counts at a stage if it reached that stage OR ANY LATER ONE, so the funnel is monotonic and every rate is <= 100%) `[{ "stage": "matched", "label": "Matched", "count": 40, "of": "discovered", "rate": 0.12 | null }]`
   Stages in order: discovered, passed_filters, matched, drafted, gmail_drafted, applied, replied, interviewed, offered.
   `rate` = count / count of the PREVIOUS stage, null when that denominator is 0. `reply_rate_applied` is separate (see below).
GET /api/analytics/rates -> `{ "reply_rate": {"value": 0.2 | null, "numerator": 3, "denominator": 15, "definition": "employer_replied / applied"}, ... }` (also interview_rate, offer_rate with the same shape)
GET /api/analytics/timeseries?metric=discovered|new|matched|applied|replied&bucket=day|week -> `[{ "date": "2026-10-18", "value": 12 }]`
GET /api/analytics/distributions?by=country|category|company|score|status -> `[{ "label": "UAE", "count": 31 }]` (score buckets: "0-19" ... "80-100")
GET /api/analytics/runs -> per-run series for charts: `[{ "run_id": 7, "started_at": "...", "new_jobs": 0, "known_jobs": 0, "matched": 0, "drafts_generated": 0, "errors": 0 }]`

`recruiter_contacted_at`: the most recent time this job's recruiter (hr_email) was emailed about ANY job: imported history,
a Gmail draft created in the app, or a job marked applied. It never blocks drafting (protection is per job); it is shown as a badge.
Filter with `?recruiter_contacted=true|false`.
