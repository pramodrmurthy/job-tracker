"""SQLAlchemy engine and session helpers (SQLite with WAL and foreign keys)."""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from . import config

_engine = None
_SessionLocal: sessionmaker | None = None


def init_engine(url: str | None = None):
    """(Re)create the engine. Tests pass an in-memory or temp-file URL."""
    global _engine, _SessionLocal
    url = url or config.DB_URL
    if url.startswith("sqlite:///") and ":memory:" not in url:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(_engine, "connect")
    def _pragmas(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    from .models import Base
    Base.metadata.create_all(_engine)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit on success, roll back on error."""
    get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session
