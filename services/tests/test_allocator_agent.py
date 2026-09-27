"""Allocator agent: config validation, exact argv, real child processes (dummy game server)."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

import pytest

from allocator.agent import (
    Agent,
    AgentConfig,
    Allocation,
    AllocationRejected,
    ConfigError,
    build_server_argv,
    canonical_uuid,
    udp_port_free,
    validate_allocation,
)
from pgcluster import free_port

DUMMY = str(Path(__file__).resolve().parent / "fixtures" / "dummy_game_server.py")


def base_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    secret = tmp_path / "server.secret"
    if not secret.exists():
        secret.write_text("s3cr3t-value-for-tests-only-0123456789abcdef\n")
        secret.chmod(0o600)
    env = {
        "WR_SERVICE_URL": "http://127.0.0.1:8080",
        "WR_SERVER_ID": "test-host",
        "WR_SERVER_SECRET_FILE": str(secret),
        "WR_SERVER_BINARY": sys.executable,
        "WR_SERVER_EXTRA_ARGS_JSON": json.dumps([DUMMY]),
        "WR_PUBLIC_HOST": "127.0.0.1",
        "WR_REGION": "eu",
        "WR_ALLOCATOR_LOG_DIR": str(tmp_path / "logs"),
    }
    env.update(overrides)
    return env


def test_config_defaults_and_validation(tmp_path):
    cfg = AgentConfig.from_env(base_env(tmp_path))
    assert (cfg.port_min, cfg.port_max, cfg.max_matches, cfg.match_timeout_s) == (24610, 24699, 4, 1500.0)
    assert cfg.extra_args == (DUMMY,) and cfg.kill_grace_s == 10.0
    not_exec = tmp_path / "server.x86_64"
    not_exec.write_text("#!/bin/sh\n")
    bad = [
        {"WR_SERVICE_URL": ""},
        {"WR_SERVICE_URL": "http://example.org"},             # http only for loopback
        {"WR_SERVICE_URL": "https://example.org/prefix"},     # no path
        {"WR_SERVICE_URL": "ftp://127.0.0.1"},
        {"WR_SERVER_ID": "Bad_Id"},
        {"WR_SERVER_BINARY": "relative/server"},
        {"WR_SERVER_BINARY": str(not_exec)},
        {"WR_SERVER_BINARY": str(tmp_path / "missing")},
        {"WR_SERVER_EXTRA_ARGS_JSON": "--main-pack x"},
        {"WR_SERVER_EXTRA_ARGS_JSON": json.dumps(["--", "--server"])},
        {"WR_SERVER_EXTRA_ARGS_JSON": json.dumps([1, 2])},
        {"WR_PORT_MIN": "24700", "WR_PORT_MAX": "24610"},
        {"WR_PORT_MIN": "80"},
        {"WR_MAX_MATCHES": "500"},
        {"WR_PORT_MIN": "24610", "WR_PORT_MAX": "24611", "WR_MAX_MATCHES": "3"},
        {"WR_REGION": "EU West"},
        {"WR_PUBLIC_HOST": "bad host"},
        {"WR_SERVER_SECRET_FILE": str(tmp_path / "nope")},
        {"WR_MATCH_TIMEOUT_S": "soon"},
    ]
    for override in bad:
        with pytest.raises(ConfigError):
            AgentConfig.from_env(base_env(tmp_path, **override))
    ok = AgentConfig.from_env(base_env(tmp_path, WR_SERVICE_URL="http://example.org", WR_DEV_ALLOW_HTTP="1"))
    assert ok.service_url == "http://example.org"
    assert AgentConfig.from_env(base_env(tmp_path, WR_SERVICE_URL="https://svc.example.org/")).service_url == "https://svc.example.org"


def test_exact_argv(tmp_path):
    cfg = AgentConfig.from_env(base_env(tmp_path, WR_SERVER_EXTRA_ARGS_JSON=json.dumps(["--main-pack", "/opt/wr/server.pck"])))
    mid = str(uuid.uuid4())
    argv = build_server_argv(cfg, Allocation(str(uuid.uuid4()), mid, "ranked", 24612, 10))
    assert argv == [
        sys.executable, "--main-pack", "/opt/wr/server.pck", "--headless", "--", "--server", "--port", "24612",
        "--match-id", mid, "--mode", "ranked", "--service-url", "http://127.0.0.1:8080", "--server-id", "test-host",
        "--secret-file", str(tmp_path / "server.secret"), "--expected-players", "10",
    ]


def test_allocation_validation(tmp_path):
    cfg = AgentConfig.from_env(base_env(tmp_path))
    good = {"allocation_id": str(uuid.uuid4()), "match_id": str(uuid.uuid4()), "mode": "casual", "port": 24610, "expected_players": 3}
    always_free = lambda p: True  # noqa: E731
    assert validate_allocation(good, cfg, set(), always_free).port == 24610
    bad = [
        {**good, "match_id": "not-a-uuid"},
        {**good, "match_id": good["match_id"].upper()},
        {**good, "match_id": "../../etc/passwd"},
        {**good, "match_id": good["match_id"] + " --evil"},
        {**good, "allocation_id": 5},
        {**good, "mode": "deathmatch"},
        {**good, "mode": "casual; rm -rf /"},
        {**good, "port": 24700},
        {**good, "port": "24610"},
        {**good, "port": True},
        {**good, "expected_players": 0},
        {**good, "expected_players": 11},
    ]
    for raw in bad:
        with pytest.raises(AllocationRejected):
            validate_allocation(raw, cfg, set(), always_free)
    with pytest.raises(AllocationRejected):
        validate_allocation(good, cfg, {24610}, always_free)  # used by another child
    with pytest.raises(AllocationRejected):
        validate_allocation(good, cfg, set(), lambda p: False)  # bound by some other process
    assert canonical_uuid("00000000-0000-4000-8000-000000000000")
    assert canonical_uuid("{00000000-0000-4000-8000-000000000000}") is None


def test_udp_port_check():
    port = free_port()
    assert udp_port_free(port, "127.0.0.1")
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("0.0.0.0", port))
        assert not udp_port_free(port, "0.0.0.0")


class FakeClient:
    """Records service calls; poll hands out queued allocations once."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.to_allocate: list[dict] = []
        self.started_code = 200

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "/v1/allocator/poll":
            out, self.to_allocate = self.to_allocate, []
            return 200, {"allocations": out}
        if path == "/v1/allocator/started":
            return self.started_code, ({"ok": True} if self.started_code == 200 else {"error": {"code": "allocation_cancelled"}})
        return 200, {"ok": True}

    def paths(self, path):
        return [p for (_, pth, p) in self.calls if pth == path]


def alloc_dict(port: int, mode: str = "casual") -> dict:
    return {"allocation_id": str(uuid.uuid4()), "match_id": str(uuid.uuid4()), "mode": mode, "port": port, "expected_players": 2}


def make_agent(tmp_path, monkeypatch, behavior: str, **env_overrides: str) -> tuple[Agent, FakeClient]:
    port = free_port()
    env = base_env(tmp_path, WR_PORT_MIN=str(port), WR_PORT_MAX=str(port + 5), WR_MAX_MATCHES="2",
                   WR_KILL_GRACE_S="0.5", WR_POLL_INTERVAL_S="0.05", WR_HEARTBEAT_INTERVAL_S="0.2", **env_overrides)
    monkeypatch.setenv("DUMMY_BEHAVIOR", behavior)
    monkeypatch.setenv("DUMMY_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("WR_SHOULD_NOT_LEAK", "1")
    client = FakeClient()
    return Agent(cfg=AgentConfig.from_env(env), client=client), client  # type: ignore[arg-type]


def run_until(agent: Agent, cond, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached")
        agent.step()
        time.sleep(0.02)


def test_spawn_report_and_reap(tmp_path, monkeypatch):
    agent, client = make_agent(tmp_path, monkeypatch, "exit")
    monkeypatch.setenv("DUMMY_EXIT_CODE", "7")
    a = alloc_dict(agent.cfg.port_min)
    client.to_allocate = [a]
    run_until(agent, lambda: client.paths("/v1/allocator/ended"))
    started = client.paths("/v1/allocator/started")
    assert started and started[0]["match_id"] == a["match_id"] and started[0]["port"] == a["port"]
    ended = client.paths("/v1/allocator/ended")[0]
    assert ended == {"allocation_id": a["allocation_id"], "match_id": a["match_id"], "exit_code": 7, "reason": "crashed"}
    report = json.loads((tmp_path / f"{a['match_id']}.json").read_text())
    assert report["argv"][1:] == ["--headless", "--", "--server", "--port", str(a["port"]), "--match-id", a["match_id"],
                                  "--mode", "casual", "--service-url", "http://127.0.0.1:8080", "--server-id", "test-host",
                                  "--secret-file", str(tmp_path / "server.secret"), "--expected-players", "2"]
    assert report["env_wr"] == []  # WR_* variables are not passed to game servers
    hb = client.paths("/v1/servers/heartbeat")[0]
    assert hb["region"] == "eu" and hb["capacity"] == 2 and hb["status"] == "online"
    assert not agent.children


def test_timeout_sigterm_then_sigkill(tmp_path, monkeypatch):
    agent, client = make_agent(tmp_path, monkeypatch, "ignore_term", WR_MATCH_TIMEOUT_S="1")
    a = alloc_dict(agent.cfg.port_min)
    client.to_allocate = [a]
    run_until(agent, lambda: agent.children)
    pid = next(iter(agent.children.values())).proc.pid
    t0 = time.monotonic()
    run_until(agent, lambda: client.paths("/v1/allocator/ended"), timeout=15)
    elapsed = time.monotonic() - t0
    ended = client.paths("/v1/allocator/ended")[0]
    assert ended["reason"] == "timeout" and ended["exit_code"] == -signal.SIGKILL
    assert 1.0 <= elapsed < 10
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_graceful_timeout_and_heartbeat_lists_children(tmp_path, monkeypatch):
    agent, client = make_agent(tmp_path, monkeypatch, "sleep", WR_MATCH_TIMEOUT_S="1.5")
    allocs = [alloc_dict(agent.cfg.port_min), alloc_dict(agent.cfg.port_min + 1, mode="ranked")]
    client.to_allocate = list(allocs)
    run_until(agent, lambda: len(agent.children) == 2)
    agent.heartbeat("online")
    hb = client.paths("/v1/servers/heartbeat")[-1]
    assert sorted(m["match_id"] for m in hb["matches"]) == sorted(a["match_id"] for a in allocs)
    run_until(agent, lambda: len(client.paths("/v1/allocator/ended")) == 2, timeout=15)
    assert {e["reason"] for e in client.paths("/v1/allocator/ended")} == {"timeout"}
    assert {e["exit_code"] for e in client.paths("/v1/allocator/ended")} == {0}  # handled SIGTERM


def test_refused_start_stops_child_and_resent_allocation_is_deduplicated(tmp_path, monkeypatch):
    agent, client = make_agent(tmp_path, monkeypatch, "sleep")
    a = alloc_dict(agent.cfg.port_min)
    client.to_allocate = [a]
    run_until(agent, lambda: client.paths("/v1/allocator/started"))
    client.to_allocate = [a]  # service re-sends (e.g. lost response)
    run_until(agent, lambda: len(client.paths("/v1/allocator/started")) >= 2)
    assert len(agent.children) == 1  # not started twice
    b = alloc_dict(agent.cfg.port_min + 1)
    client.started_code = 409
    client.to_allocate = [b]
    run_until(agent, lambda: any(e["match_id"] == b["match_id"] for e in client.paths("/v1/allocator/ended")))
    ended_b = [e for e in client.paths("/v1/allocator/ended") if e["match_id"] == b["match_id"]][0]
    assert ended_b["reason"].startswith("refused_by_service")
    agent.shutdown()
    assert not agent.children


def test_invalid_allocation_is_reported_not_started(tmp_path, monkeypatch):
    agent, client = make_agent(tmp_path, monkeypatch, "sleep")
    bad = {**alloc_dict(agent.cfg.port_min), "mode": "evil"}
    client.to_allocate = [bad]
    run_until(agent, lambda: client.paths("/v1/allocator/ended"))
    assert not agent.children and not client.paths("/v1/allocator/started")
    assert client.paths("/v1/allocator/ended")[0]["reason"].startswith("rejected:")


def test_shutdown_terminates_all_children(tmp_path, monkeypatch):
    agent, client = make_agent(tmp_path, monkeypatch, "ignore_term")
    client.to_allocate = [alloc_dict(agent.cfg.port_min), alloc_dict(agent.cfg.port_min + 1)]
    run_until(agent, lambda: len(agent.children) == 2)
    pids = [c.proc.pid for c in agent.children.values()]
    agent.stopping = True
    agent.shutdown()
    assert not agent.children
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    reasons = {e["reason"] for e in client.paths("/v1/allocator/ended")}
    assert reasons == {"allocator_shutdown"}
    assert client.paths("/v1/servers/heartbeat")[-1]["status"] == "draining"
