"""Private matches: allocation, join codes, observers, unrated results with x0.5 XP."""

from __future__ import annotations

import threading
import uuid

import pytest

from helpers import ctx_of, make_account, make_accounts, online_server, signed
from wildrush_svc.logic import allocation
from wildrush_svc.schemas import AllocationStartedReq
from wildrush_svc.security import verify_ticket


class FakeAllocator(threading.Thread):
    """Plays the allocator side through the service logic (poll -> started)."""

    def __init__(self, app, server_id: str) -> None:
        super().__init__(daemon=True)
        self.ctx = ctx_of(app)
        self.server_id = server_id
        self.stop = threading.Event()
        self.started: list[dict] = []

    def run(self) -> None:
        while not self.stop.is_set():
            with self.ctx.tx() as db:
                allocs = allocation.poll(db, self.ctx, self.server_id, list(range(24610, 24620)))["allocations"]
            for a in allocs:
                with self.ctx.tx() as db:
                    allocation.allocation_started(
                        db, self.ctx, self.server_id,
                        AllocationStartedReq(allocation_id=a["allocation_id"], match_id=a["match_id"], port=a["port"], pid=1234),
                    )
                self.started.append(a)
            self.stop.wait(0.05)


@pytest.fixture
def fake_allocator(client, app):
    srv = online_server(client, app, server_id="priv-host")
    fa = FakeAllocator(app, srv.id)
    fa.start()
    yield srv, fa
    fa.stop.set()
    fa.join(5)


def test_create_join_observe_and_unrated_result(client, app, fake_allocator):
    srv, fa = fake_allocator
    host = make_account(app, "LobbyHost")
    r = client.post("/v1/private", json={"region": "eu"}, headers=host.headers)
    assert r.status_code == 200, r.text
    created = r.json()
    code = created["join_code"]
    assert len(code) == 8 and code.isalnum() and code.upper() == code
    assert created["host"] == "127.0.0.1" and created["port"] == fa.started[0]["port"]
    assert fa.started[0]["mode"] == "private" and fa.started[0]["expected_players"] == 1
    now = int(ctx_of(app).clock.now().timestamp())
    payload = verify_ticket(srv.secret, created["ticket"], now_unix=now, expected_sid=srv.id, expected_mid=created["match_id"])
    assert payload and payload["role"] == "player" and payload["team"] == -1

    guest, spectator = make_account(app, "Guest"), make_account(app, "Spectator")
    r = client.post("/v1/private/join", json={"join_code": code.lower(), "role": "player"}, headers=guest.headers)
    assert r.status_code == 200, r.text
    assert r.json()["match_id"] == created["match_id"]
    r = client.post("/v1/private/join", json={"join_code": code, "role": "observer"}, headers=spectator.headers)
    assert r.status_code == 200
    obs = verify_ticket(srv.secret, r.json()["ticket"], now_unix=now, expected_mid=created["match_id"])
    assert obs["role"] == "observer"

    # redeem: lobby admin flag and observer role are visible to the game server
    red = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem", {"ticket_id": payload["tid"], "match_id": created["match_id"]})
    assert red.status_code == 200 and red.json()["lobby_admin"] is True and red.json()["mode"] == "private"
    red = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem", {"ticket_id": obs["tid"], "match_id": created["match_id"]})
    assert red.json()["role"] == "observer" and red.json()["lobby_admin"] is False

    assert client.post("/v1/private/join", json={"join_code": "ZZZZZZZZ"}, headers=guest.headers).status_code == 404

    match_id = created["match_id"]
    assert signed(client, app, srv, "POST", f"/v1/matches/{match_id}/started", {}).status_code == 200
    body = {
        "match_id": match_id, "winner_team": 0, "score": [250, 100], "duration_s": 300.0, "sudden_death": False,
        "ended_reason": "score_limit",
        "players": [
            {"account_id": str(host.id), "team": 0, "fighter": "nyx", "kos": 4, "knocked_out": 1, "damage_dealt": 900,
             "control_seconds": 61, "abandoned": False, "afk": False},
            {"account_id": str(guest.id), "team": 1, "fighter": "nyx", "kos": 1, "knocked_out": 4, "damage_dealt": 300,
             "control_seconds": 10, "abandoned": False, "afk": False},
        ],
        "bots": [{"team": 0, "fighter": "bruno"}, {"team": 1, "fighter": "vex"}],
    }
    # observers cannot appear as players
    bad = {**body, "players": body["players"] + [{**body["players"][1], "account_id": str(spectator.id), "fighter": "hops"}]}
    r = signed(client, app, srv, "POST", f"/v1/matches/{match_id}/result", bad)
    assert r.status_code == 422
    r = signed(client, app, srv, "POST", f"/v1/matches/{match_id}/result", body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["rating_changes"] == {}
    assert out["mastery_changes"][str(host.id)]["xp_gained"] == 156  # 312 * 0.5
    assert out["mastery_changes"][str(guest.id)]["xp_gained"] == 65  # (100 + 20 + 10) * 0.5
    me = client.get("/v1/me", headers=host.headers).json()
    assert me["rating"]["games"] == 0 and me["rating"]["rating"] == 1500.0
    hist = client.get("/v1/matches/history", headers=guest.headers).json()
    assert hist[0]["mode"] == "private" and hist[0]["rating_delta"] is None
    # observer may read the stored result
    assert client.get(f"/v1/matches/{match_id}", headers=spectator.headers).json()["result"]["winner_team"] == 0
    # finished private match can no longer be joined
    assert client.post("/v1/private/join", json={"join_code": code}, headers=make_account(app, "Latecomer").headers).status_code == 404


def test_private_capacity_and_single_hosting(client, app, fake_allocator):
    srv, fa = fake_allocator
    host = make_account(app, "OnlyOne")
    created = client.post("/v1/private", json={"region": "eu"}, headers=host.headers).json()
    r = client.post("/v1/private", json={"region": "eu"}, headers=host.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_hosting"
    players = make_accounts(app, "pj", 10)
    for p in players[:9]:  # host + 9 = 10 players
        assert client.post("/v1/private/join", json={"join_code": created["join_code"]}, headers=p.headers).status_code == 200
    r = client.post("/v1/private/join", json={"join_code": created["join_code"]}, headers=players[9].headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "match_full"
    # observers still fit
    r = client.post("/v1/private/join", json={"join_code": created["join_code"], "role": "observer"}, headers=players[9].headers)
    assert r.status_code == 200


def test_private_without_servers(client, app):
    host = make_account(app, "NoServers")
    r = client.post("/v1/private", json={"region": "eu"}, headers=host.headers)
    assert r.status_code == 503 and r.json()["error"]["code"] == "no_server_available"


def test_private_allocation_timeout(migrated_url, engine, clock):
    from fastapi.testclient import TestClient

    from conftest import make_settings
    from wildrush_svc.app import create_app

    app = create_app(make_settings(migrated_url, private_alloc_wait_s=1.0), engine=engine, clock=clock)
    with TestClient(app, client=("127.0.0.1", 40002)) as client:
        online_server(client, app, server_id="silent-host")  # online but nobody polls
        host = make_account(app, "Impatient")
        r = client.post("/v1/private", json={"region": "eu"}, headers=host.headers)
        assert r.status_code == 503 and r.json()["error"]["code"] == "allocation_timeout"
        # the attempt was cancelled (not left "hosting"), so the player may simply retry
        r = client.post("/v1/private", json={"region": "eu"}, headers=host.headers)
        assert r.json()["error"]["code"] == "allocation_timeout"


def test_private_rejects_queued_players(client, app, fake_allocator):
    host = make_account(app, "QueuedHost")
    client.post("/v1/queue", json={"mode": "casual", "region": "eu"}, headers=host.headers)
    r = client.post("/v1/private", json={"region": "eu"}, headers=host.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_queued"
    assert uuid.UUID(str(host.id))
