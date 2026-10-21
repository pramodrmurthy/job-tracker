#!/usr/bin/env python3
"""Download every job from hireabroad.co.in with full details into one CSV.

Usage:   python3 hireabroad_export.py
Output:  hireabroad_jobs.csv   (all jobs, all categories, full descriptions, recruiter contact if listed)

Needs only Python 3.8+ (no installs). Takes roughly 40-50 minutes because it asks for each job's full
details one at a time, politely (1 request per second). You can stop it with Ctrl+C and run it again:
it resumes from hireabroad_cache.jsonl, so nothing is downloaded twice.

Please be considerate: this uses the same public endpoints the website's own pages call. Run it once,
not in a loop, and do not lower the delay. The data (including recruiters' contact details) is for your
own job search; do not republish it. The site's robots.txt disallows automated access to /api/, so if
the site owner asks you to stop, stop.
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.hireabroad.co.in/api/v1/jobs"
UA = "hireabroad-personal-export/1.0 (personal job search; 1 request/second)"
DELAY_SECONDS = 1.0
PAGE_SIZE = 50
MAX_ATTEMPTS = 5
HERE = Path.cwd()
CACHE = HERE / "hireabroad_cache.jsonl"
OUTPUT = HERE / "hireabroad_jobs.csv"
DROP = {"_id", "__v"}  # internal database fields, not useful in a spreadsheet


def get_json(url):
    """GET with retries and backoff for timeouts, 429 and 5xx. Raises after MAX_ATTEMPTS."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            if not payload.get("success"):
                raise RuntimeError("API said: %s" % str(payload)[:200])
            return payload["data"]
        except urllib.error.HTTPError as e:
            retryable = e.code == 429 or e.code >= 500
            wait = int(e.headers.get("Retry-After", 0) or 0) or 5 * attempt
            if not retryable or attempt == MAX_ATTEMPTS:
                raise
        except (urllib.error.URLError, TimeoutError):
            wait = 5 * attempt
            if attempt == MAX_ATTEMPTS:
                raise
        print("  temporary problem, retrying in %ss (attempt %d/%d)" % (wait, attempt, MAX_ATTEMPTS))
        time.sleep(wait)


def list_all_job_ids():
    """Walk every list page; returns {jobId: list_record}."""
    found, page = {}, 1
    while True:
        query = urllib.parse.urlencode({"limit": PAGE_SIZE, "page": page})
        data = get_json("%s?%s" % (BASE, query))
        for job in data["jobs"]:
            found[job["jobId"]] = job
        pg = data["pagination"]
        print("list page %d/%d: %d jobs so far" % (pg["page"], pg["totalPages"], len(found)))
        if not pg.get("hasNextPage"):
            return found
        page += 1
        time.sleep(DELAY_SECONDS)


def load_cache():
    cached = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                cached[record["jobId"]] = record
    return cached


def flatten(value, prefix=""):
    """Nested dicts become dotted columns (location.country); lists are joined with '; '."""
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            if not prefix and key in DROP:
                continue
            out.update(flatten(val, "%s.%s" % (prefix, key) if prefix else key))
        return out
    if isinstance(value, list):
        return {prefix: "; ".join(str(x) for x in value)}
    return {prefix: value}


def write_csv(records):
    rows = [flatten(r) for r in records]
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel opens it correctly
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), len(columns)


def main():
    print(__doc__.split("Usage:")[0].strip())
    print("\nStarting in 5 seconds (Ctrl+C to cancel)...")
    time.sleep(5)

    listing = list_all_job_ids()
    cached = load_cache()
    todo = [job_id for job_id in listing if job_id not in cached]
    print("\n%d jobs found, %d already downloaded, %d to fetch" % (len(listing), len(cached), len(todo)))

    failed = []
    with open(CACHE, "a", encoding="utf-8") as cache_file:
        for i, job_id in enumerate(todo, 1):
            try:
                time.sleep(DELAY_SECONDS)
                detail = get_json("%s/%s" % (BASE, urllib.parse.quote(job_id)))
                record = dict(listing[job_id], **detail)  # detail wins; list fields fill any gaps
            except Exception as e:  # keep going; a rerun retries failures
                print("  could not fetch %s: %s" % (job_id, e))
                failed.append(job_id)
                continue
            cache_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            cache_file.flush()
            cached[job_id] = record
            if i % 25 == 0 or i == len(todo):
                remaining = (len(todo) - i) * (DELAY_SECONDS + 0.3) / 60
                print("details %d/%d (about %.0f min left)" % (i, len(todo), remaining))

    # jobs whose detail could not be fetched still get a row from the list data
    records = [cached.get(job_id) or listing[job_id] for job_id in listing]
    rows, cols = write_csv(records)
    print("\nDone: %d jobs, %d columns -> %s" % (rows, cols, OUTPUT))
    if failed:
        print("%d jobs have list data only (details failed). Run the script again to retry them." % len(failed))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped. Run again to resume where you left off.")
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit("\nCould not reach hireabroad.co.in (%s). Check your internet and try again later." % e)
