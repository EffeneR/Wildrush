"""Shared fixtures: a REAL PostgreSQL 16 cluster (session scope) migrated with Alembic."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from pgcluster import free_port, start_cluster
from wildrush_svc.app import create_app
from wildrush_svc.clock import OffsetClock, SystemClock
from wildrush_svc.config import Settings
from wildrush_svc.db import create_db_engine
from wildrush_svc.models import Base

SERVICES_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    external = os.environ.get("WR_TEST_DATABASE_URL")
    if external:
        yield external
        return
    cluster = start_cluster()
    try:
        yield cluster.url
    finally:
        cluster.stop()


def alembic_config(url: str) -> Config:
    cfg = Config(str(SERVICES_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated_url(database_url: str) -> str:
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest.fixture(scope="session")
def engine(migrated_url: str) -> Iterator[Engine]:
    eng = create_db_engine(Settings(database_url=migrated_url))
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_db(request: pytest.FixtureRequest) -> None:
    if "engine" not in request.fixturenames:
        return
    eng: Engine = request.getfixturevalue("engine")
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with eng.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def make_settings(url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": url,
        "matchmaker_enabled": False,
        "private_alloc_wait_s": 5.0,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def clock() -> OffsetClock:
    return OffsetClock()


@pytest.fixture
def settings(migrated_url: str) -> Settings:
    return make_settings(migrated_url)


@pytest.fixture
def app(settings: Settings, engine: Engine, clock: OffsetClock) -> FastAPI:
    return create_app(settings, engine=engine, clock=clock)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, client=("127.0.0.1", 40000)) as c:
        yield c


class LiveServer:
    def __init__(self, app: FastAPI, port: int) -> None:
        self.app = app
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
        )
        self.thread = threading.Thread(target=self.server.run, name="live-uvicorn", daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 20
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=20)


@pytest.fixture
def live_server(migrated_url: str, engine: Engine) -> Iterator[LiveServer]:
    """A real uvicorn server (real clock, matchmaker loop enabled at 0.25 s)."""
    settings = make_settings(
        migrated_url,
        matchmaker_enabled=True,
        matchmaker_interval_s=0.25,
        private_alloc_wait_s=15.0,
    )
    live = LiveServer(create_app(settings, engine=engine, clock=SystemClock()), free_port())
    live.start()
    try:
        yield live
    finally:
        live.stop()
