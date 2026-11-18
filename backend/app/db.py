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


def ensure_columns(eng=None) -> list[str]:
    """Non-destructive schema upgrade: ADD COLUMN for every mapped column missing in an existing table.

    `create_all` creates missing tables but never alters existing ones; this keeps an older demo DB usable without
    a reset. New columns are added as nullable (no constraints); a fresh DB (reset_demo) gets the full schema.
    Returns "table.column" for every column added.
    """
    from sqlalchemy import inspect, text

    eng = eng or engine
    insp = inspect(eng)
    added: list[str] = []
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    ddl = col.type.compile(dialect=eng.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                    added.append(f"{table.name}.{col.name}")
    return added


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
