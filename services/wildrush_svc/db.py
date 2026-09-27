"""Engine / session factory. All access goes through SQLAlchemy with bound parameters."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings


def effective_database_url(settings: Settings) -> URL:
    url = make_url(settings.database_url)
    if settings.database_password_file:
        password = Path(settings.database_password_file).read_text(encoding="utf-8").strip()
        if not password:
            raise ValueError("WR_DATABASE_PASSWORD_FILE is empty")
        url = url.set(password=password)
    return url


def safe_url_for_logs(settings: Settings) -> str:
    try:
        return make_url(settings.database_url).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover - defensive
        return "<unparseable database url>"


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        effective_database_url(settings),
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=10,
        pool_recycle=1800,
        # All timestamps are timezone-aware UTC; make the session time zone UTC as well.
        connect_args={"options": "-c timezone=UTC", "connect_timeout": 10},
    )


def create_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, autoflush=True)
