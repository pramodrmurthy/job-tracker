"""Job source adapter interface. Each source maps the common profile filters onto what it supports."""

from typing import Iterator, Protocol


class SourceError(Exception):
    """A source could not be reached or returned something unusable (after retries)."""


class Source(Protocol):
    name: str

    def list_pages(self, profile: dict) -> Iterator[list[dict]]:
        """Yield pages of normalized job dicts, newest first. The caller may stop iterating early.
        Normalized keys: external_id, title, company, country, city, category, sub_category, experience_level,
        description, skills, hr_email, hr_name, hr_phone, salary_text, employment_type, work_mode,
        visa_sponsored, posted_at (datetime|None), source_url, raw."""
        ...

    def fetch_detail(self, external_id: str) -> dict:
        """Return the normalized job dict with the full description."""
        ...
