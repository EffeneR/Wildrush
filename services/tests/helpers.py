"""Test helpers: fast account/session creation, server provisioning, signed requests."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update

from wildrush_svc.context import AppContext
from wildrush_svc.logic import accounts, servers
from wildrush_svc.models import Rating
from wildrush_svc.security import hash_password, sign_request

PASSWORD = "correct-horse-1"
_HASH: str | None = None


def password_hash() -> str:
    global _HASH
    if _HASH is None:
        _HASH = hash_password(PASSWORD)
    return _HASH


def ctx_of(app: FastAPI) -> AppContext:
    return app.state.ctx


def client_from(app: FastAPI, ip: str) -> TestClient:
    """A TestClient whose requests come from ``ip`` (per-IP rate limit buckets)."""
    return TestClient(app, client=(ip, 40001))


@dataclass
class Acct:
    id: uuid.UUID
    username: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def make_account(app: FastAPI, username: str, *, rating: float | None = None) -> Acct:
    """Create an account + session directly (argon2 hashing once per test run)."""
    assert re.fullmatch(r"[A-Za-z0-9_]{3,16}", username), username
    ctx = ctx_of(app)
    now = ctx.clock.now()
    with ctx.tx() as db:
        account = accounts.create_account(
            db, username=username, password_hash=password_hash(), display_name=None, now=now
        )
        token, _ = accounts.create_session(db, account.id, now=now, ttl=timedelta(hours=12))
        if rating is not None:
            db.execute(update(Rating).where(Rating.account_id == account.id).values(rating=rating))
    return Acct(id=account.id, username=username, token=token)


def make_accounts(app: FastAPI, prefix: str, n: int, *, ratings: list[float] | None = None) -> list[Acct]:
    return [
        make_account(app, f"{prefix}{i}", rating=(ratings[i] if ratings else None)) for i in range(n)
    ]


@dataclass
class Srv:
    id: str
    secret: str
    region: str


def make_server(app: FastAPI, server_id: str = "test-srv-1", region: str = "eu", name: str | None = None) -> Srv:
    ctx = ctx_of(app)
    with ctx.tx() as db:
        secret = servers.add_server(db, server_id=server_id, name=name or server_id, region=region, now=ctx.clock.now())
    return Srv(id=server_id, secret=secret, region=region)


def signed(
    client: TestClient,
    app: FastAPI,
    srv: Srv,
    method: str,
    path: str,
    payload: Any = None,
    *,
    ts_offset: int = 0,
    body: bytes | None = None,
    secret: str | None = None,
    sign_path: str | None = None,
    server_id: str | None = None,
) -> Any:
    raw = body if body is not None else (b"" if payload is None else json.dumps(payload).encode())
    ts = str(int(ctx_of(app).clock.now().timestamp()) + ts_offset)
    sig = sign_request(secret or srv.secret, method, sign_path or path, ts, raw)
    headers = {"X-WR-Server": server_id or srv.id, "X-WR-Timestamp": ts, "X-WR-Signature": sig}
    if raw:
        headers["Content-Type"] = "application/json"
    return client.request(method, path, content=raw, headers=headers)


def heartbeat(
    client: TestClient, app: FastAPI, srv: Srv, *, capacity: int = 4, status: str = "online",
    host: str = "127.0.0.1", port_min: int = 24610, port_max: int = 24699, matches: list | None = None,
    region: str | None = None,
) -> Any:
    body = {
        "name": f"{srv.id} name",
        "region": region or srv.region,
        "host": host,
        "port_min": port_min,
        "port_max": port_max,
        "capacity": capacity,
        "build_id": "test-build",
        "protocol": 1,
        "status": status,
        "matches": matches or [],
    }
    return signed(client, app, srv, "POST", "/v1/servers/heartbeat", body)


def online_server(client: TestClient, app: FastAPI, server_id: str = "test-srv-1", region: str = "eu", capacity: int = 4) -> Srv:
    srv = make_server(app, server_id, region)
    r = heartbeat(client, app, srv, capacity=capacity)
    assert r.status_code == 200, r.text
    return srv


def queue_body(mode: str = "casual", region: str = "eu", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"mode": mode, "region": region, "roster_prefs": [], "latency_ms": {region: 30}, "allow_bots": False}
    body.update(extra)
    return body


def join_queue(client: TestClient, acct: Acct, **kw: Any) -> Any:
    return client.post("/v1/queue", json=queue_body(**kw), headers=acct.headers)


def tick(app: FastAPI) -> list[uuid.UUID]:
    return app.state.matchmaker.tick()


def poll(client: TestClient, app: FastAPI, srv: Srv, free_ports: list[int] | None = None) -> list[dict[str, Any]]:
    r = signed(client, app, srv, "POST", "/v1/allocator/poll", {"free_ports": free_ports or list(range(24610, 24620))})
    assert r.status_code == 200, r.text
    return r.json()["allocations"]


def start_allocation(client: TestClient, app: FastAPI, srv: Srv, alloc: dict[str, Any], pid: int = 4242) -> Any:
    return signed(
        client, app, srv, "POST", "/v1/allocator/started",
        {"allocation_id": alloc["allocation_id"], "match_id": alloc["match_id"], "port": alloc["port"], "pid": pid},
    )


def make_party(client: TestClient, leader: Acct, members: list[Acct]) -> str:
    r = client.post("/v1/parties", headers=leader.headers)
    assert r.status_code == 201, r.text
    for m in members:
        r = client.post("/v1/parties/current/invites", json={"username": m.username}, headers=leader.headers)
        assert r.status_code == 201, r.text
        r = client.post(f"/v1/invites/{r.json()['invite_id']}/accept", headers=m.headers)
        assert r.status_code == 200, r.text
    return client.get("/v1/parties/current", headers=leader.headers).json()["party_id"]


def ready_match(
    client: TestClient, app: FastAPI, srv: Srv, players: list[Acct], mode: str = "ranked", **queue_kw: Any
) -> tuple[str, dict[str, Any]]:
    """Queue solo players, form a match, allocate + start it. Returns (match_id, allocation)."""
    for p in players:
        r = join_queue(client, p, mode=mode, region=srv.region, **queue_kw)
        assert r.status_code == 202, r.text
    formed = tick(app)
    assert len(formed) == 1, formed
    allocs = poll(client, app, srv)
    assert len(allocs) == 1
    r = start_allocation(client, app, srv, allocs[0])
    assert r.status_code == 200, r.text
    return allocs[0]["match_id"], allocs[0]


def running_match(client: TestClient, app: FastAPI, srv: Srv, players: list[Acct], mode: str = "ranked", **kw: Any) -> str:
    match_id, _ = ready_match(client, app, srv, players, mode=mode, **kw)
    r = signed(client, app, srv, "POST", f"/v1/matches/{match_id}/started", {})
    assert r.status_code == 200, r.text
    return match_id


def participants_by_team(client: TestClient, players: list[Acct]) -> dict[int, list[Acct]]:
    teams: dict[int, list[Acct]] = {0: [], 1: []}
    for p in players:
        status = client.get("/v1/queue/status", headers=p.headers).json()
        teams[status["match"]["team"]].append(p)
    return teams


FIGHTERS = ["nyx", "bruno", "vex", "hops", "scrap"]


def result_body(match_id: str, teams: dict[int, list[Acct]], *, winner: int = 0, bots: list[dict] | None = None, **overrides: Any) -> dict[str, Any]:
    players = []
    for team, members in teams.items():
        for i, p in enumerate(members):
            players.append({
                "account_id": str(p.id), "team": team, "fighter": FIGHTERS[i], "kos": 4, "knocked_out": 2,
                "damage_dealt": 1830, "control_seconds": 61, "abandoned": False, "afk": False,
            })
    body = {
        "match_id": match_id, "winner_team": winner, "score": [250, 173], "duration_s": 402.5,
        "sudden_death": False, "ended_reason": "score_limit", "players": players, "bots": bots or [],
    }
    body.update(overrides)
    return body
