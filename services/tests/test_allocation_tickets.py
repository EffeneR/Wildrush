"""Allocator flow (poll -> started -> tickets -> redeem -> ended) and join-ticket security."""

from __future__ import annotations

import json
import threading

from sqlalchemy import select

from helpers import (
    ctx_of,
    heartbeat,
    make_accounts,
    make_server,
    online_server,
    poll,
    ready_match,
    signed,
    start_allocation,
)
from wildrush_svc.models import Allocation, JoinTicket, Match
from wildrush_svc.security import b64url_decode, b64url_encode, verify_ticket


def status_of(client, acct):
    return client.get("/v1/queue/status", headers=acct.headers).json()


def test_poll_only_assigns_valid_free_ports_and_resends_unconfirmed(client, app):
    srv = online_server(client, app)
    players = make_accounts(app, "pp", 10)
    for p in players:
        client.post("/v1/queue", json={"mode": "ranked", "region": "eu"}, headers=p.headers)
    app.state.matchmaker.tick()
    assert poll(client, app, srv, free_ports=[80, 30000]) == []  # outside the heartbeat range
    allocs = poll(client, app, srv, free_ports=[24650])
    assert [a["port"] for a in allocs] == [24650]
    again = poll(client, app, srv, free_ports=[24651])
    assert again == allocs  # not yet confirmed -> handed out again with the same port


def test_poll_without_heartbeat_returns_nothing(client, app):
    srv = make_server(app, "fresh-host")
    assert poll(client, app, srv) == []


def test_tickets_verify_locally_and_redeem_once(client, app):
    srv = online_server(client, app)
    players = make_accounts(app, "tk", 10)
    match_id, alloc = ready_match(client, app, srv, players)
    st = status_of(client, players[0])
    ticket = st["match"]["ticket"]
    now_unix = int(ctx_of(app).clock.now().timestamp())
    payload = verify_ticket(srv.secret, ticket, now_unix=now_unix, expected_sid=srv.id, expected_mid=match_id)
    assert payload is not None
    assert list(payload) == ["tid", "mid", "aid", "sid", "team", "role", "exp"]
    assert payload["aid"] == str(players[0].id) and payload["role"] == "player"
    assert payload["team"] == st["match"]["team"]
    assert 55 <= payload["exp"] - now_unix <= 60

    r = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem", {"ticket_id": payload["tid"], "match_id": match_id})
    assert r.status_code == 200, r.text
    red = r.json()
    assert red["account_id"] == str(players[0].id) and red["username"] == players[0].username
    assert red["team"] == payload["team"] and red["role"] == "player" and red["roster_prefs"] == []
    assert red["palettes"] == {f: "default" for f in ("nyx", "bruno", "vex", "hops", "scrap")}
    r = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem", {"ticket_id": payload["tid"], "match_id": match_id})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ticket_used"
    # once redeemed, queue status no longer hands out a ticket (reconnect goes through rejoin)
    assert status_of(client, players[0])["match"]["ticket"] is None


def test_concurrent_redemption_has_exactly_one_winner(client, app):
    srv = online_server(client, app)
    players = make_accounts(app, "cc", 10)
    match_id, _ = ready_match(client, app, srv, players)
    ticket = status_of(client, players[1])["match"]["ticket"]
    tid = json.loads(b64url_decode(ticket.split(".")[0]))["tid"]
    results: list[int] = []
    barrier = threading.Barrier(8)

    def redeem() -> None:
        barrier.wait()
        r = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem", {"ticket_id": tid, "match_id": match_id})
        results.append(r.status_code)

    threads = [threading.Thread(target=redeem) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200] + [409] * 7


def test_forged_expired_wrong_server_and_wrong_match_tickets(client, app, clock):
    srv = online_server(client, app)
    other = online_server(client, app, server_id="other-host")
    players = make_accounts(app, "fx", 10)
    match_id, alloc = ready_match(client, app, srv, players)
    ticket = status_of(client, players[2])["match"]["ticket"]
    payload_b64, sig_b64 = ticket.split(".")
    payload = json.loads(b64url_decode(payload_b64))
    now_unix = int(ctx_of(app).clock.now().timestamp())

    # forged: modified payload keeps the old signature / attacker-chosen secret
    forged_payload = dict(payload, team=1 - payload["team"])
    forged = b64url_encode(json.dumps(forged_payload, separators=(",", ":")).encode()) + "." + sig_b64
    assert verify_ticket(srv.secret, forged, now_unix=now_unix) is None
    assert verify_ticket("not-the-secret", ticket, now_unix=now_unix) is None
    assert verify_ticket(srv.secret, ticket, now_unix=now_unix, expected_sid="other-host") is None
    assert verify_ticket(srv.secret, ticket, now_unix=now_unix, expected_mid="00000000-0000-4000-8000-000000000000") is None
    assert verify_ticket(srv.secret, "garbage", now_unix=now_unix) is None
    assert verify_ticket(srv.secret, ticket + "x", now_unix=now_unix) is None

    # wrong server cannot redeem (ticket is bound to the allocated server)
    r = signed(client, app, other, "POST", "/v1/servers/tickets/redeem", {"ticket_id": payload["tid"], "match_id": match_id})
    assert r.status_code == 404 and r.json()["error"]["code"] == "ticket_not_found"
    # wrong match id
    r = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem",
               {"ticket_id": payload["tid"], "match_id": "00000000-0000-4000-8000-000000000000"})
    assert r.status_code == 404
    # unknown ticket id
    r = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem",
               {"ticket_id": "00000000-0000-4000-8000-000000000001", "match_id": match_id})
    assert r.status_code == 404

    # expired: 60 s lifetime
    clock.advance(61)
    assert verify_ticket(srv.secret, ticket, now_unix=now_unix + 61) is None
    # keep the host fresh under the moved clock (it still reports the running process)
    running = [{"match_id": match_id, "port": alloc["port"], "players": 10, "state": "running"}]
    assert heartbeat(client, app, srv, matches=running).status_code == 200
    r = signed(client, app, srv, "POST", "/v1/servers/tickets/redeem", {"ticket_id": payload["tid"], "match_id": match_id})
    assert r.status_code == 410 and r.json()["error"]["code"] == "ticket_expired"
    # queue status re-issues a fresh ticket for players that never connected
    fresh = status_of(client, players[2])["match"]["ticket"]
    assert fresh and fresh != ticket
    assert verify_ticket(srv.secret, fresh, now_unix=now_unix + 61, expected_sid=srv.id, expected_mid=match_id)


def test_started_and_ended_lifecycle(client, app):
    srv = online_server(client, app)
    other = online_server(client, app, server_id="intruder")
    players = make_accounts(app, "lc", 10)
    for p in players:
        client.post("/v1/queue", json={"mode": "ranked", "region": "eu"}, headers=p.headers)
    app.state.matchmaker.tick()
    alloc = poll(client, app, srv)[0]
    # another server cannot report this allocation
    assert start_allocation(client, app, other, alloc).status_code == 404
    bad_port = dict(alloc, port=alloc["port"] + 1)
    assert start_allocation(client, app, srv, bad_port).json()["error"]["code"] == "port_mismatch"
    assert start_allocation(client, app, srv, alloc).status_code == 200
    assert start_allocation(client, app, srv, alloc).status_code == 200  # idempotent
    match_id = alloc["match_id"]
    # only the allocated server may mark the match running
    r = signed(client, app, other, "POST", f"/v1/matches/{match_id}/started", {})
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_server"
    r = signed(client, app, srv, "POST", f"/v1/matches/{match_id}/started", {})
    assert r.status_code == 200 and r.json()["state"] == "running"
    # rejoin for a running match
    r = client.post(f"/v1/matches/{match_id}/rejoin", headers=players[4].headers)
    assert r.status_code == 200, r.text
    assert r.json()["port"] == alloc["port"] and verify_ticket(
        srv.secret, r.json()["ticket"], now_unix=int(ctx_of(app).clock.now().timestamp()), expected_mid=match_id
    )
    outsider = make_accounts(app, "out", 1)[0]
    assert client.post(f"/v1/matches/{match_id}/rejoin", headers=outsider.headers).status_code == 404
    # process ends without a result -> match cancelled, players idle again
    r = signed(client, app, srv, "POST", "/v1/allocator/ended",
               {"allocation_id": alloc["allocation_id"], "match_id": match_id, "exit_code": 1, "reason": "crashed"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    with ctx_of(app).tx() as db:
        assert db.get(Match, match_id).state == "cancelled"
        assert db.scalar(select(Allocation.state).where(Allocation.match_id == match_id)) == "ended"
    assert status_of(client, players[0])["state"] == "idle"
    r = client.post(f"/v1/matches/{match_id}/rejoin", headers=players[4].headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "match_not_running"
    # ended again: idempotent
    r = signed(client, app, srv, "POST", "/v1/allocator/ended",
               {"allocation_id": alloc["allocation_id"], "match_id": match_id, "exit_code": 1, "reason": "crashed"})
    assert r.status_code == 200


def test_started_after_cancel_is_refused(client, app, clock):
    srv = online_server(client, app)
    players = make_accounts(app, "ac", 10)
    for p in players:
        client.post("/v1/queue", json={"mode": "ranked", "region": "eu"}, headers=p.headers)
    app.state.matchmaker.tick()
    alloc = poll(client, app, srv)[0]
    clock.advance(46)  # allocation timeout (45 s) -> janitor cancels
    heartbeat(client, app, srv)
    app.state.matchmaker.tick()
    with ctx_of(app).tx() as db:
        assert db.get(Match, alloc["match_id"]).state == "cancelled"
    r = start_allocation(client, app, srv, alloc)
    assert r.status_code == 409 and r.json()["error"]["code"] == "allocation_cancelled"
    assert status_of(client, players[0])["state"] == "idle"


def test_ticket_rows_are_bound_to_server_and_match(client, app):
    srv = online_server(client, app)
    players = make_accounts(app, "bd", 10)
    match_id, _ = ready_match(client, app, srv, players)
    with ctx_of(app).tx() as db:
        rows = db.scalars(select(JoinTicket).where(JoinTicket.match_id == match_id)).all()
    assert len(rows) == 10
    assert all(t.server_id == srv.id and t.redeemed_at is None for t in rows)
    assert all(abs((t.expires_at - t.issued_at).total_seconds() - 60) <= 1 for t in rows)
