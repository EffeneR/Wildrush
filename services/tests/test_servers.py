"""Heartbeats, server browser staleness, reconciliation, admin CLI, health/version."""

from __future__ import annotations

import os
import stat
import subprocess
import sys

from sqlalchemy import select

from conftest import SERVICES_DIR
from helpers import ctx_of, heartbeat, make_accounts, make_server, online_server, ready_match
from wildrush_svc.models import Allocation, GameServer, Match


def test_heartbeat_and_browser_staleness(client, app, clock):
    srv = make_server(app, "eu-alpha", "eu", name="EU Alpha")
    make_server(app, "never-seen", "eu")
    assert client.get("/v1/servers").json() == []
    assert heartbeat(client, app, srv, capacity=6).status_code == 200
    listing = client.get("/v1/servers").json()
    assert len(listing) == 1
    entry = listing[0]
    assert entry["server_id"] == "eu-alpha" and entry["region"] == "eu" and entry["capacity"] == 6
    assert entry["status"] == "online" and entry["host"] == "127.0.0.1" and entry["active_matches"] == 0
    assert entry["last_seen"].endswith("Z")
    assert "secret" not in str(listing)
    clock.advance(29)
    assert len(client.get("/v1/servers").json()) == 1
    clock.advance(2)
    assert client.get("/v1/servers").json() == []  # heartbeat older than 30 s
    assert heartbeat(client, app, srv, status="draining").status_code == 200
    assert client.get("/v1/servers").json()[0]["status"] == "draining"


def test_heartbeat_validation(client, app):
    srv = make_server(app, "val-host", "eu")
    r = heartbeat(client, app, srv, region="us")
    assert r.status_code == 409 and r.json()["error"]["code"] == "region_mismatch"
    for kwargs in ({"port_min": 30000, "port_max": 20000}, {"port_min": 80}, {"capacity": -1}, {"host": "bad host!"},
                   {"port_min": 20000, "port_max": 29000}, {"status": "exploded"}):
        assert heartbeat(client, app, srv, **kwargs).status_code == 422, kwargs


def test_disabled_server_is_rejected_and_hidden(client, app):
    srv = online_server(client, app, server_id="to-disable")
    from wildrush_svc.logic import servers as server_logic

    with ctx_of(app).tx() as db:
        server_logic.set_enabled(db, "to-disable", False)
    r = heartbeat(client, app, srv)
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_signature"
    assert client.get("/v1/servers").json() == []


def test_heartbeat_reconciles_processes_the_host_no_longer_runs(client, app, clock):
    srv = online_server(client, app)
    players = make_accounts(app, "rc", 10)
    match_id, alloc = ready_match(client, app, srv, players)
    running = [{"match_id": match_id, "port": alloc["port"], "players": 10, "state": "running"}]
    clock.advance(25)
    assert heartbeat(client, app, srv, matches=running).status_code == 200
    with ctx_of(app).tx() as db:
        assert db.get(Match, match_id).state == "ready"
    # e.g. the allocator restarted and lost the process
    assert heartbeat(client, app, srv, matches=[]).status_code == 200
    with ctx_of(app).tx() as db:
        assert db.get(Match, match_id).state == "cancelled"
        assert db.scalar(select(Allocation.state).where(Allocation.match_id == match_id)) == "ended"


def test_lost_host_matches_are_cancelled_by_janitor(client, app, clock):
    srv = online_server(client, app)
    players = make_accounts(app, "lh", 10)
    match_id, _ = ready_match(client, app, srv, players)
    clock.advance(121)
    app.state.matchmaker.tick()
    with ctx_of(app).tx() as db:
        assert db.get(Match, match_id).state == "cancelled"
    assert client.get("/v1/queue/status", headers=players[0].headers).json()["state"] == "idle"


def test_health_and_version(client, app):
    assert client.get("/healthz").json() == {"ok": True, "db": "ok"}
    v = client.get("/v1/version").json()
    assert v["api"] == 1 and isinstance(v["protocol"], int) and v["service_build"].startswith("1.0.0")


def test_healthz_reports_db_down(migrated_url):
    from fastapi.testclient import TestClient

    from conftest import make_settings
    from wildrush_svc.app import create_app

    bad = make_settings(migrated_url.rsplit(":", 1)[0] + ":1/nowhere")
    with TestClient(create_app(bad)) as c:
        r = c.get("/healthz")
    assert r.status_code == 503
    assert r.json()["ok"] is False and r.json()["db"] == "unavailable"


def test_admin_cli(migrated_url, tmp_path, engine):
    env = {**os.environ, "WR_DATABASE_URL": migrated_url, "PYTHONPATH": str(SERVICES_DIR)}
    run = lambda *args: subprocess.run(  # noqa: E731
        [sys.executable, "-m", "wildrush_svc.admin", *args], cwd=SERVICES_DIR, env=env, capture_output=True, text=True, timeout=60
    )
    r = run("add-server", "--id", "cli-host-1", "--name", "CLI Host", "--region", "eu")
    assert r.returncode == 0, r.stderr
    printed = r.stdout.strip().splitlines()[-1]
    with engine.begin() as conn:
        stored = conn.execute(select(GameServer.secret).where(GameServer.id == "cli-host-1")).scalar_one()
    assert printed == stored and len(printed) >= 40
    assert stored not in r.stderr

    r = run("add-server", "--id", "cli-host-1", "--name", "dup", "--region", "eu")
    assert r.returncode == 1 and "already exists" in r.stderr
    r = run("add-server", "--id", "BAD ID", "--name", "x", "--region", "eu")
    assert r.returncode == 1

    secret_file = tmp_path / "secrets" / "cli-host-2.secret"
    r = run("add-server", "--id", "cli-host-2", "--name", "Two", "--region", "us", "--write-secret-file", str(secret_file))
    assert r.returncode == 0, r.stderr
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600
    with engine.begin() as conn:
        stored2 = conn.execute(select(GameServer.secret).where(GameServer.id == "cli-host-2")).scalar_one()
    assert secret_file.read_text().strip() == stored2 and stored2 not in r.stdout

    r = run("list-servers")
    assert r.returncode == 0 and "cli-host-1" in r.stdout and "cli-host-2" in r.stdout
    assert stored not in r.stdout and stored2 not in r.stdout

    r = run("disable-server", "--id", "cli-host-1")
    assert r.returncode == 0
    with engine.begin() as conn:
        assert conn.execute(select(GameServer.enabled).where(GameServer.id == "cli-host-1")).scalar_one() is False
    r = run("rotate-secret", "--id", "cli-host-2")
    assert r.returncode == 0
    with engine.begin() as conn:
        rotated = conn.execute(select(GameServer.secret).where(GameServer.id == "cli-host-2")).scalar_one()
    assert rotated != stored2 and rotated == r.stdout.strip().splitlines()[-1]
    r = run("disable-server", "--id", "no-such-host")
    assert r.returncode == 1
