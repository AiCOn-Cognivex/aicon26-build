"""Database engine and session. Postgres when DATABASE_URL is set, otherwise SQLite."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


def _url() -> str:
    u = config.DATABASE_URL
    if not u:
        return f"sqlite:///{config.SQLITE_PATH}"
    for prefix in ("postgres://", "postgresql://"):
        if u.startswith(prefix):
            return "postgresql+psycopg://" + u[len(prefix):]
    return u


URL = _url()
IS_SQLITE = URL.startswith("sqlite")
engine = create_engine(
    URL, pool_pre_ping=True,
    **({"connect_args": {"check_same_thread": False}} if IS_SQLITE
       else {"pool_size": 5, "max_overflow": 5, "pool_recycle": 280}),
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as s:
        yield s


def utcnow() -> datetime:
    """Naive UTC timestamp (same on SQLite and Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
