"""Import the recruiters the old scripts already emailed:  uv run python -m jobtracker.import_legacy [state.json ...]

Reads data/state.json and data/state.prev.json by default (the old pipeline's "emailed" records). Idempotent.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from . import config, db
from .models import ContactedRecruiter


def main() -> None:
    files = [Path(a) for a in sys.argv[1:]] or [config.ROOT / "data" / "state.json", config.ROOT / "data" / "state.prev.json"]
    found: dict[str, str] = {}
    for f in files:
        if f.exists():
            for email, info in (json.loads(f.read_text()).get("emailed") or {}).items():
                found.setdefault(email.strip().lower(), info.get("date", "2026-10-18"))
    added = 0
    with db.session_scope() as session:
        known = {e for (e,) in session.execute(select(ContactedRecruiter.email))}
        for email, day in sorted(found.items()):
            if email not in known:
                session.add(ContactedRecruiter(email=email, contacted_at=datetime.fromisoformat(day), source="legacy-import",
                                               note="emailed with the previous scripts"))
                added += 1
    print(f"{len(found)} recruiters in the old state, {added} newly imported ({len(found) - added} already present).")


if __name__ == "__main__":
    main()
