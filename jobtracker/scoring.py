"""LLM job-vs-resume assessment. Explainable (score + reason) and cached by (job content, resume, preferences)."""

import hashlib
import json
import re

from .llm import Ask


def prefs_hash(preferences_text: str) -> str:
    return hashlib.sha256((preferences_text or "").encode()).hexdigest()


def job_brief(job) -> dict:
    return {"jobId": str(job.id), "title": job.title, "country": job.country, "yearsRequired": job.experience_level,
            "subCategory": job.sub_category, "skills": (job.skills or [])[:25],
            "description": (job.description or "")[:1800]}


def build_prompt(resume_text: str, preferences_text: str, jobs: list) -> str:
    return f"""You screen job postings for one candidate. Be strict and honest; do not flatter.

CANDIDATE:
{resume_text}

WHAT THE CANDIDATE WANTS:
{preferences_text or "(not specified)"}

For each job below, judge whether the candidate should apply, based on the REAL meaning of the role
(not keywords in the title). Penalise roles that need clearly more years of experience than the candidate has.
Calibration: 90+ only when the core of the job matches the candidate's main expertise AND what they want, and they
meet most stated requirements. 70-89 for a good fit with a notable gap. 40-69 when the match is only partial or the
seniority/domain is off. Below 40 for everything else. Most jobs should land between 20 and 70.
"relevant" is true only for scores of 70 or more.
The reason must name the specific requirement that matches or the specific gap, in max 25 words
(not generic phrases like "strong alignment").

Reply with ONLY a JSON array, one object per job, no prose, no code fences:
[{{"jobId": "...", "score": 0-100, "relevant": true/false, "reason": "..."}}]

JOBS:
{json.dumps([job_brief(j) for j in jobs], indent=1)}
"""


def parse_reply(reply: str, jobs: list) -> dict[int, dict]:
    """Return {job.id: {score, relevant, reason}} for the jobs the model answered validly."""
    m = re.search(r"\[.*\]", reply, re.S)
    if not m:
        raise ValueError(f"no JSON array in model output: {reply[:200]!r}")
    wanted = {str(j.id) for j in jobs}
    out: dict[int, dict] = {}
    for item in json.loads(m.group(0)):
        jid = str(item.get("jobId"))
        score = item.get("score")
        if jid not in wanted or not isinstance(score, (int, float)) or not 0 <= score <= 100:
            continue
        out[int(jid)] = {"score": int(round(score)), "relevant": bool(item.get("relevant")) and score >= 70,
                         "reason": str(item.get("reason") or "").strip()[:500]}
    return out


def score_batch(ask: Ask, resume_text: str, preferences_text: str, jobs: list) -> dict[int, dict]:
    return parse_reply(ask(build_prompt(resume_text, preferences_text, jobs)), jobs)
