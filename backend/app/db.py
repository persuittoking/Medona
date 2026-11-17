"""SQLAlchemy engine and session factory."""
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BACKEND_DIR, get_settings


class Base(DeclarativeBase):
    pass


def _resolve_url(url: str) -> str:
    # Make relative SQLite paths relative to backend/, regardless of the cwd.
    if url.startswith("sqlite:///./"):
        return f"sqlite:///{(BACKEND_DIR / url[len('sqlite:///./'):]).as_posix()}"
    return url


def make_engine(url: str | None = None):
    url = _resolve_url(url or get_settings().database_url)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
