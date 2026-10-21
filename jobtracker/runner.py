"""Runs pipeline executions in a background thread so API requests return immediately."""

import threading
from typing import Callable

from sqlalchemy.orm import Session

from . import db, pipeline


def run_in_background(run_id: int, deps_factory: Callable[[Session], pipeline.Deps], sync: bool = False) -> None:
    def work() -> None:
        with db.session_scope() as session:
            try:
                pipeline.execute_run(session, run_id, deps_factory(session))
            except Exception as e:  # deps could not be built, or the run record vanished
                session.rollback()
                from .models import Run, utcnow
                run = session.get(Run, run_id)
                if run is not None and run.status in ("queued", "running"):
                    run.status, run.finished_at, run.stage = "failed", utcnow(), "done"
                    run.errors = [*run.errors, {"stage": None, "job_id": None, "message": f"{type(e).__name__}: {e}"[:400]}]
                    session.commit()

    if sync:
        work()
    else:
        threading.Thread(target=work, name=f"run-{run_id}", daemon=True).start()
