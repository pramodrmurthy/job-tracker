"""Formal application email generation, grounded in the resume. Subject lines are built in code."""

import json
import re

from .llm import Ask

GENERIC_LOCALPARTS = {"careers", "career", "hr", "jobs", "job", "info", "recruiter", "recruitment", "hiring",
                      "talent", "admin", "contact", "apply", "resume", "cv", "team", "support", "sg", "india"}
BANNED = re.compile(r"passionate|dynamic|team player|results-driven|hard-working|to whom it may concern|"
                    r"esteemed|rockstar|ninja|successfully|showcas|demonstrat|proven|extensive experience|"
                    r"effectively|i am also interested|similar roles|thrilled|excited|perfect fit", re.I)


def greeting(address: str) -> str:
    """'maria@x.com' -> 'Dear Maria,'; generic or unclear addresses -> 'Dear Hiring Team,'."""
    first = re.split(r"[._\-+0-9]", address.split("@")[0].lower())[0]
    if first in GENERIC_LOCALPARTS or not first.isalpha() or len(first) < 3:
        return "Dear Hiring Team,"
    return f"Dear {first.capitalize()},"


def pretty_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    if not title.isupper():
        return title
    keep = {"AI", "ML", "LLM", "GENAI", "IOT", "SAP", "L3", "AWS", "GCP", "SME", "QA", "CRM", "ERP", "API"}
    words = [w if w.strip("/&(),–-") in keep or not w.isalpha() else w.capitalize() for w in title.split()]
    return " ".join(w.replace("Genai", "GenAI") for w in words)


def pretty_country(country: str | None) -> str:
    c = country or ""
    return c if c.upper() in {"UAE", "UK", "USA"} else c.title()


def make_subject(jobs: list[dict], sender_name: str) -> str:
    titles = [pretty_title(j["title"]) for j in jobs]
    subject = f"Application: {titles[0]}"
    if len(titles) > 1:
        subject += f" and {len(titles) - 1} other role{'s' if len(titles) > 2 else ''}"
    return f"{subject} – {sender_name}" if sender_name else subject


def numbers_in(text: str) -> set[str]:
    """Digit strings only, so '13', '13+' and '13 yrs' compare equal ('1,000' -> '1000')."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)}


def build_prompt(jobs: list[dict], resume: str, availability: str) -> str:
    briefs = [{"title": pretty_title(j["title"]), "country": j.get("country"), "yearsRequired": j.get("experience_level"),
               "skills": (j.get("skills") or [])[:20], "description": (j.get("description") or "")[:1800]} for j in jobs]
    closing_extra = (f' Include this sentence exactly once in paragraph 3: "{availability}"' if availability
                     else " Do not mention notice period, salary, visa or availability.")
    return f"""Write the BODY of a formal job-application email from the candidate to a recruiter, in the style of a
professional cover letter. Use ONLY facts from the CANDIDATE text. Never invent employers, tools, numbers, titles,
degrees, availability, notice period, salary or visa status.

CANDIDATE:
{resume}

JOB(S) (the first one is the best fit):
{json.dumps(briefs, indent=1)}

Format: exactly three paragraphs separated by one blank line. No greeting, no sign-off, no subject, no bullets,
no arrows, no markdown, 120-170 words in total, formal but plain English, no exclamation marks.
- Paragraph 1: state interest in the role (exact title and country) and who the candidate is (years of experience and
  current role, taken from the CANDIDATE text). If several jobs are listed, name the others in one clause.
- Paragraph 2: connect two or three of the job's own stated requirements to specific, quantified accomplishments from
  the CANDIDATE text, written as flowing sentences.
- Paragraph 3: say the resume is attached and invite a short call at the recruiter's convenience.{closing_extra}
HONESTY: every claim must come from the CANDIDATE text. If the candidate lacks a requirement, do not mention it and
never imply experience with it; choose other requirements the candidate really meets. With a single job, do not
mention other roles or interests.
Banned: passionate, dynamic, team player, results-driven, successfully, showcasing, demonstrating, proven, extensive
experience, effectively, excited, thrilled, perfect fit, "I am also interested", "similar roles".

Reply with ONLY JSON: {{"body": "..."}}"""


def tidy(body: str) -> str:
    body = re.sub(r"[ \t]+", " ", body.replace("\r", ""))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r" ?\n ?", "\n", body)).strip()


def check(body: str, resume_text: str, job_text: str) -> None:
    invented = numbers_in(body) - numbers_in(resume_text) - numbers_in(job_text)
    if invented:
        raise ValueError(f"numbers not in resume/job text: {sorted(invented)}")
    if BANNED.search(body):
        raise ValueError(f"banned phrase: {BANNED.search(body).group(0)!r}")
    if len(body.split("\n\n")) != 3:
        raise ValueError("need exactly three paragraphs")
    if re.search(r"(?m)^\s*([-•*]|\d+\.)\s|->|→|\*\*|!", body):
        raise ValueError("bullets, arrows, markdown or exclamation marks are not allowed")
    if not 90 <= len(body.split()) <= 220:
        raise ValueError("length out of range")


def signature(sender: dict) -> str:
    contact = " | ".join(x for x in (sender.get("phone"), sender.get("email")) if x)
    lines = ["Sincerely,", sender.get("name") or "", contact, sender.get("linkedin") or ""]
    return "\n".join(line for line in lines if line) + "\n"


def template_body(jobs: list[dict]) -> str:
    """Generic fallback when the model fails twice. Deliberately plain: it claims nothing beyond the job itself."""
    titles = [pretty_title(j["title"]) for j in jobs]
    countries = sorted({pretty_country(j.get("country")) for j in jobs if j.get("country")})
    where = f" in {' / '.join(countries)}" if countries else ""
    others = f", as well as {len(titles) - 1} other role{'s' if len(titles) > 2 else ''} ({'; '.join(titles[1:])})" if len(titles) > 1 else ""
    return (f"I am writing to express my interest in the {titles[0]} position{where}{others}.\n\n"
            "My resume is attached and sets out my experience and the work most relevant to this opening. "
            "Please edit this paragraph to add one or two accomplishments that match the role.\n\n"
            "I would welcome the opportunity to discuss the role in a short call at your convenience.")


def write_email(jobs: list[dict], address: str, resume_text: str, ask: Ask, sender: dict,
                availability: str = "") -> tuple[str, str, str]:
    """Return (subject, body, source) with source 'ai' or 'template'. One retry before falling back."""
    job_text = " ".join((j.get("description") or "") + " " + " ".join(j.get("skills") or []) + " " +
                        str(j.get("experience_level")) for j in jobs)
    subject = make_subject(jobs, sender.get("name", ""))
    last_error = ""
    for _ in range(2):
        try:
            prompt = build_prompt(jobs, resume_text, availability)
            if last_error:
                prompt += f"\n\nYour previous attempt was rejected: {last_error}. Fix that and follow every rule."
            data = json.loads(re.search(r"\{.*\}", ask(prompt), re.S).group(0))
            core = tidy(data["body"])
            check(core, resume_text, job_text)
            return subject, f"{greeting(address)}\n\n{core}\n\n{signature(sender)}", "ai"
        except Exception as e:  # model error, bad JSON, failed checks: retry once, then fall back
            last_error = str(e)
    return subject, f"{greeting(address)}\n\n{template_body(jobs)}\n\n{signature(sender)}", "template"
