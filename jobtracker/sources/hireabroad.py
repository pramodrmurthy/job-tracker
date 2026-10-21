"""hireabroad.co.in adapter. Uses the JSON endpoint the site's own jobs page calls.

Note: the site's robots.txt disallows /api/*, and the endpoint is undocumented. This adapter is for personal,
low-volume use (polite delay, clear User-Agent). Do not build a public service on it.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Iterator

from .. import config
from .base import SourceError

BASE = "https://www.hireabroad.co.in/api/v1/jobs"
PAGE_SIZE = 50
MAX_ATTEMPTS = 4
MAX_PAGES = 100


class HireAbroadSource:
    name = "hireabroad"

    def __init__(self, delay: float | None = None, sleep=time.sleep):
        self.delay = config.SOURCE_DELAY_SECONDS if delay is None else delay
        self._sleep = sleep

    # ---- HTTP ----
    def _get(self, url: str) -> dict:
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": config.SOURCE_USER_AGENT})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    payload = json.load(resp)
                if not payload.get("success"):
                    raise SourceError(f"API error: {str(payload)[:200]}")
                return payload["data"]
            except urllib.error.HTTPError as e:
                last = e
                if not (e.code == 429 or e.code >= 500):
                    break
                wait = int(e.headers.get("Retry-After", 0) or 0) or 5 * attempt
            except (urllib.error.URLError, TimeoutError) as e:
                last, wait = e, 5 * attempt
            if attempt < MAX_ATTEMPTS:
                self._sleep(wait)
        raise SourceError(f"hireabroad.co.in not responding: {last}")

    # ---- filter capability mapping ----
    @staticmethod
    def server_params(profile: dict) -> dict:
        """Only filters the site supports go to the server; everything else is applied locally by the pipeline."""
        params: dict = {"limit": PAGE_SIZE}
        cats = profile.get("categories") or []
        if len(cats) == 1:
            params["category"] = cats[0]
        if (profile.get("min_years") or 0) >= 10:
            params["experience"] = "10+ years"  # the site's band is loose (includes 7-10); local filter tightens it
        include = profile.get("countries_include") or []
        if len(include) == 1:
            params["country"] = include[0].upper()
        return params

    # ---- Source interface ----
    def list_pages(self, profile: dict) -> Iterator[list[dict]]:
        params = self.server_params(profile)
        for page in range(1, MAX_PAGES + 1):
            data = self._get(f"{BASE}?{urllib.parse.urlencode({**params, 'page': page})}")
            yield [self.normalize(j) for j in data["jobs"]]
            if not data["pagination"].get("hasNextPage"):
                return
            self._sleep(self.delay)

    def fetch_detail(self, external_id: str) -> dict:
        self._sleep(self.delay)
        return self.normalize(self._get(f"{BASE}/{urllib.parse.quote(external_id)}"))

    # ---- normalization ----
    @staticmethod
    def normalize(j: dict) -> dict:
        loc = j.get("location") or {}
        salary = j.get("salaryText")
        if not salary or "[object" in str(salary):  # the site sometimes leaks "[object object]"
            salary = None
        posted = j.get("publishedAt") or j.get("createdAt")
        try:
            posted_at = datetime.fromisoformat(posted.replace("Z", "+00:00")).replace(tzinfo=None) if posted else None
        except ValueError:
            posted_at = None
        return {
            "external_id": j["jobId"], "title": (j.get("title") or "").strip(),
            "company": (j.get("companyName") or "").strip() or None,
            "country": (loc.get("country") or "").strip() or None, "city": (loc.get("city") or "").strip() or None,
            "category": j.get("category"), "sub_category": j.get("subCategory"),
            "experience_level": j.get("experienceLevel"),
            "description": j.get("description"), "skills": list(j.get("skills") or []),
            "hr_email": (j.get("hrEmail") or "").strip().lower() or None,
            "hr_name": (j.get("hrName") or "").strip() or None, "hr_phone": (j.get("hrNumber") or "").strip() or None,
            "salary_text": salary, "employment_type": j.get("employmentType"), "work_mode": j.get("workMode"),
            "visa_sponsored": j.get("isVisaSponsored"), "posted_at": posted_at,
            "source_url": None,  # the site has no documented public per-job URL; do not guess one
            "raw": j,
        }
