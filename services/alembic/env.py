"""Alembic environment: the URL comes from WR_DATABASE_URL (or -x/config override)."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from wildrush_svc.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url():
    """Explicit sqlalchemy.url (tests / programmatic use) or the service settings."""
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        return explicit
    if not os.environ.get("WR_DATABASE_URL"):
        raise RuntimeError("WR_DATABASE_URL is not set")
    from wildrush_svc.config import Settings
    from wildrush_svc.db import effective_database_url

    return effective_database_url(Settings())  # type: ignore[call-arg]


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        _database_url(),
        poolclass=pool.NullPool,
        connect_args={"options": "-c timezone=UTC", "connect_timeout": 10},
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
