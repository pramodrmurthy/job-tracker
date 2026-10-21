"""One-time import of your existing details into the app:  uv run python -m jobtracker.seed

Idempotent: does nothing if a resume already exists. Reads ~/Downloads/Resume.pdf (or the path given as the
first argument), preferences.txt and your sender details from appdata/sender.json.
"""

import json
import sys
from pathlib import Path

from . import config, db
from .models import Resume
from .resume_parser import ResumeError, extract_text, store_file
from .services import ensure_default_profile, set_setting
from sqlalchemy import select

SENDER_FILE = config.DATA_DIR / "sender.json"  # {"name", "phone", "email", "linkedin"}; stays local (appdata/ is gitignored)


def main() -> None:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads" / "Resume.pdf"
    with db.session_scope() as session:
        ensure_default_profile(session)
        if session.scalar(select(Resume.id)):
            print("A resume already exists; nothing to seed.")
            return
        sender = json.loads(SENDER_FILE.read_text()) if SENDER_FILE.exists() else {}
        if sender:
            set_setting(session, "sender", sender)
        else:
            print(f"No {SENDER_FILE.name}; fill in your sender details in the app (Settings).")
        prefs = config.ROOT / "preferences.txt"
        if prefs.exists():
            set_setting(session, "preferences_text", prefs.read_text().strip())
        text, stored, name = None, None, "Resume.pdf"
        if pdf.exists():
            try:
                data = pdf.read_bytes()
                text, stored, name = extract_text(pdf.name, data), str(store_file(pdf.name, data)), pdf.name
            except ResumeError as e:
                print(f"Could not read {pdf}: {e}")
        if text is None and (config.ROOT / "resume.txt").exists():
            text, name = (config.ROOT / "resume.txt").read_text(), "resume.txt"
        if text is None:
            print("No resume found. Upload one in the app (Settings).")
            return
        session.add(Resume(filename=name, stored_path=stored, text=text))
        print(f"Seeded resume '{name}' ({len(text)} characters), sender details and preferences.")


if __name__ == "__main__":
    main()
