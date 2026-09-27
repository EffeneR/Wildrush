"""End-to-end over real sockets: uvicorn service + allocator agent subprocess + dummy game
server processes + UDP "clients" presenting join tickets. No mocks in the loop."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from conftest import SERVICES_DIR, LiveServer
from helpers import ctx_of, make_account, make_accounts, make_server
from wildrush_svc.models import Allocation, Match

pytestmark = pytest.mark.live
DUMMY = str(Path(__file__).resolve().parent / "fixtures" / "dummy_game_server.py")


def wait_for(cond: Callable[[], Any], timeout: float = 30.0, interval: float = 0.1) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        value = cond()
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for condition")
        time.sleep(interval)


def free_udp_range(n: int) -> int:
    """First port of n consecutive free UDP ports (outside the dev range 24610-24699)."""
    for base in range(26000, 30000, 17):
        if all(_udp_free(p) for p in range(base, base + n)):
            return base
    raise RuntimeError("no free UDP range")


def _udp_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


@contextmanager
def allocator_process(live: LiveServer, tmp_path: Path, server_id: str, secret: str, behavior: str, **extra: str) -> Iterator[subprocess.Popen]:
    secret_file = tmp_path / f"{server_id}.secret"
    secret_file.write_text(secret + "\n")
    secret_file.chmod(0o600)
    port_min = free_udp_range(4)
    env = {
        **os.environ,
        "PYTHONPATH": str(SERVICES_DIR),
        "WR_SERVICE_URL": live.url,
        "WR_SERVER_ID": server_id,
        "WR_SERVER_SECRET_FILE": str(secret_file),
        "WR_SERVER_BINARY": sys.executable,
        "WR_SERVER_EXTRA_ARGS_JSON": json.dumps([DUMMY]),
        "WR_PORT_MIN": str(port_min),
        "WR_PORT_MAX": str(port_min + 3),
        "WR_PUBLIC_HOST": "127.0.0.1",
        "WR_REGION": "eu",
        "WR_MAX_MATCHES": "2",
        "WR_POLL_INTERVAL_S": "0.2",
        "WR_HEARTBEAT_INTERVAL_S": "0.5",
        "WR_ALLOCATOR_LOG_DIR": str(tmp_path / "match-logs"),
        "DUMMY_BEHAVIOR": behavior,
        "DUMMY_REPORT_DIR": str(tmp_path),
        **extra,
    }
    log = open(tmp_path / "allocator.log", "wb")  # noqa: SIM115
    proc = subprocess.Popen([sys.executable, "-m", "allocator"], cwd=SERVICES_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        log.close()


def udp_exchange(port: int, message: str, timeout: float = 5.0) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(message.encode(), ("127.0.0.1", port))
        data, _ = s.recvfrom(4096)
        return data.decode()


def match_row(live: LiveServer, match_id: str) -> tuple[Match, Allocation]:
    with ctx_of(live.app).tx() as db:
        match = db.get(Match, match_id)
        alloc = db.scalar(select(Allocation).where(Allocation.match_id == match_id))
        db.expunge_all()
    return match, alloc


def test_ranked_end_to_end_with_real_processes(live_server: LiveServer, tmp_path: Path):
    srv = make_server(live_server.app, "e2e-host", "eu")
    players = make_accounts(live_server.app, "e2e", 10, ratings=[1400 + 20 * i for i in range(10)])
    with allocator_process(live_server, tmp_path, srv.id, srv.secret, "play") as agent, httpx.Client(base_url=live_server.url, timeout=10) as http:
        wait_for(lambda: http.get("/v1/servers").json(), timeout=15)
        for p in players:
            r = http.post("/v1/queue", json={"mode": "ranked", "region": "eu", "latency_ms": {"eu": 25}}, headers=p.headers)
            assert r.status_code == 202, r.text

        def all_tickets() -> dict[str, Any] | None:
            out = {}
            for p in players:
                st = http.get("/v1/queue/status", headers=p.headers).json()
                if st["state"] != "matched" or not st["match"]["ticket"]:
                    return None
                out[p.username] = st["match"]
            return out

        tickets = wait_for(all_tickets, timeout=30, interval=0.3)
        match_id = next(iter(tickets.values()))["match_id"]
        port = next(iter(tickets.values()))["port"]
        assert {t["match_id"] for t in tickets.values()} == {match_id}
        assert sorted(t["team"] for t in tickets.values()) == [0] * 5 + [1] * 5
        wait_for(lambda: match_row(live_server, match_id)[0].state == "running", timeout=15)

        # a forged ticket (tampered signature) is refused locally by the game server
        first = players[0]
        forged_parts = tickets[first.username]["ticket"].split(".")
        assert udp_exchange(port, f"TICKET {forged_parts[0]}.{forged_parts[1][::-1]}") == "ERR invalid_ticket"
        for i, p in enumerate(players):
            reply = udp_exchange(port, f"TICKET {tickets[p.username]['ticket']}")
            assert reply == f"OK {p.id} {tickets[p.username]['team']}", reply
            if i == 0:  # replaying a used ticket is refused by the service
                assert udp_exchange(port, f"TICKET {tickets[p.username]['ticket']}") == "ERR ticket_used"

        # dummy server submits the result (and a retransmission), exits 0 -> agent reports "ended"
        wait_for(lambda: match_row(live_server, match_id)[1].state == "ended", timeout=20)
        match, alloc = match_row(live_server, match_id)
        assert match.state == "finished" and alloc.exit_code == 0 and alloc.end_reason == "exited"

        winners = [p for p in players if tickets[p.username]["team"] == 0]
        hist = http.get("/v1/matches/history", headers=winners[0].headers).json()
        assert hist[0]["match_id"] == match_id and hist[0]["won"] is True and hist[0]["rating_delta"] > 0
        me = http.get("/v1/me", headers=winners[0].headers).json()
        assert me["rating"]["games"] == 1 and me["rating"]["wins"] == 1
        match_log = (tmp_path / "match-logs" / f"{match_id}.log").read_text()
        assert "result -> 200" in match_log and '"idempotent": true' in match_log
        report = json.loads((tmp_path / f"{match_id}.json").read_text())
        assert report["argv"][report["argv"].index("--port") + 1] == str(port)
        assert report["env_wr"] == []

        agent.send_signal(signal.SIGTERM)
        assert agent.wait(timeout=30) == 0


def test_private_match_and_agent_shutdown_cleans_up(live_server: LiveServer, tmp_path: Path):
    srv = make_server(live_server.app, "priv-e2e", "eu")
    host = make_account(live_server.app, "PrivHost")
    guest = make_account(live_server.app, "PrivGuest")
    with allocator_process(live_server, tmp_path, srv.id, srv.secret, "sleep") as agent, httpx.Client(base_url=live_server.url, timeout=30) as http:
        wait_for(lambda: http.get("/v1/servers").json(), timeout=15)
        r = http.post("/v1/private", json={"region": "eu"}, headers=host.headers)
        assert r.status_code == 200, r.text
        created = r.json()
        r = http.post("/v1/private/join", json={"join_code": created["join_code"], "role": "observer"}, headers=guest.headers)
        assert r.status_code == 200 and r.json()["port"] == created["port"]
        report = json.loads(wait_for(lambda: (tmp_path / f"{created['match_id']}.json").exists() and (tmp_path / f"{created['match_id']}.json").read_text()))
        child_pid = report["pid"]
        os.kill(child_pid, 0)  # the real child process is alive

        agent.send_signal(signal.SIGTERM)
        assert agent.wait(timeout=30) == 0
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
        match, alloc = match_row(live_server, created["match_id"])
        assert match.state == "cancelled" and alloc.state == "ended" and alloc.end_reason == "allocator_shutdown"


def test_real_agent_kills_hung_server_after_timeout(live_server: LiveServer, tmp_path: Path):
    srv = make_server(live_server.app, "hung-e2e", "eu")
    host = make_account(live_server.app, "HungHost")
    with allocator_process(
        live_server, tmp_path, srv.id, srv.secret, "ignore_term", WR_MATCH_TIMEOUT_S="2", WR_KILL_GRACE_S="1"
    ), httpx.Client(base_url=live_server.url, timeout=30) as http:
        wait_for(lambda: http.get("/v1/servers").json(), timeout=15)
        created = http.post("/v1/private", json={"region": "eu"}, headers=host.headers).json()
        wait_for(lambda: match_row(live_server, created["match_id"])[1].state == "ended", timeout=20)
        match, alloc = match_row(live_server, created["match_id"])
        assert alloc.end_reason == "timeout" and alloc.exit_code == -signal.SIGKILL
        assert match.state == "cancelled"
        pid = json.loads((tmp_path / f"{created['match_id']}.json").read_text())["pid"]
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
