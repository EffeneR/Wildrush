"""Matchmaker tick against the real database (queue -> match -> allocation)."""

from __future__ import annotations

from sqlalchemy import func, select

from helpers import (
    ctx_of,
    join_queue,
    make_account,
    make_accounts,
    make_party,
    online_server,
    participants_by_team,
    poll,
    start_allocation,
    tick,
)
from wildrush_svc.models import Allocation, Match, MatchParticipant, QueueEntry


def test_ranked_match_forms_with_exactly_ten(client, app):
    srv = online_server(client, app)
    players = make_accounts(app, "rk", 10)
    for p in players[:9]:
        assert join_queue(client, p, mode="ranked").status_code == 202
    assert tick(app) == []
    assert client.get("/v1/queue/status", headers=players[0].headers).json()["counts"]["ranked"] == 9
    assert join_queue(client, players[9], mode="ranked").status_code == 202
    formed = tick(app)
    assert len(formed) == 1
    with ctx_of(app).tx() as db:
        match = db.get(Match, formed[0])
        assert match.mode == "ranked" and match.state == "allocating" and match.bot_slots == 0
        assert match.expected_players == 10 and match.server_id == srv.id
        assert db.scalar(select(func.count()).select_from(QueueEntry)) == 0
        teams = db.execute(
            select(MatchParticipant.team, func.count()).where(MatchParticipant.match_id == match.id).group_by(MatchParticipant.team)
        ).all()
        assert dict(teams) == {0: 5, 1: 5}
        assert db.scalar(select(Allocation.state).where(Allocation.match_id == match.id)) == "pending"
    status = client.get("/v1/queue/status", headers=players[3].headers).json()
    assert status["state"] == "matched" and status["match"]["state"] == "allocating"
    assert status["match"]["ticket"] is None and status["counts"] == {"casual": 0, "ranked": 0}
    # a matched player can no longer leave or re-queue
    assert client.delete("/v1/queue", headers=players[3].headers).status_code == 409
    assert join_queue(client, players[3], mode="ranked").json()["error"]["code"] == "already_in_match"


def test_no_server_capacity_means_no_match(client, app):
    players = make_accounts(app, "nc", 10)
    for p in players:
        join_queue(client, p, mode="ranked")
    assert tick(app) == []  # no allocator host online: players keep waiting (real state)
    srv = online_server(client, app, capacity=1)
    assert len(tick(app)) == 1
    more = make_accounts(app, "nd", 10)
    for p in more:
        join_queue(client, p, mode="ranked")
    assert tick(app) == []  # capacity 1 already used
    assert srv.id


def test_stale_or_draining_servers_get_no_matches(client, app, clock):
    from helpers import heartbeat

    srv = online_server(client, app)
    players = make_accounts(app, "st", 10)
    for p in players:
        join_queue(client, p, mode="ranked")
    clock.advance(31)  # heartbeat older than 30 s
    assert tick(app) == []
    assert heartbeat(client, app, srv, status="draining").status_code == 200
    assert tick(app) == []
    assert heartbeat(client, app, srv, status="online").status_code == 200
    assert len(tick(app)) == 1


def test_party_members_share_a_team(client, app):
    online_server(client, app)
    lead = make_account(app, "PartyBoss")
    mates = make_accounts(app, "pm", 3)
    make_party(client, lead, mates)
    solos = make_accounts(app, "so", 6)
    assert join_queue(client, lead, mode="ranked", roster_prefs=["scrap", "nyx"]).status_code == 202
    for s in solos:
        join_queue(client, s, mode="ranked")
    formed = tick(app)
    assert len(formed) == 1
    with ctx_of(app).tx() as db:
        rows = db.execute(select(MatchParticipant).where(MatchParticipant.match_id == formed[0])).scalars().all()
        team_of = {r.account_id: r.team for r in rows}
        prefs = {r.account_id: r.roster_prefs for r in rows}
    party_ids = [lead.id, *(m.id for m in mates)]
    assert len({team_of[i] for i in party_ids}) == 1
    assert prefs[lead.id] == ["scrap", "nyx"] and prefs[mates[0].id] == []


def test_casual_bot_fill_after_20s_only_with_opt_in(client, app, clock):
    online_server(client, app)
    a, b, c = make_account(app, "BotFan"), make_account(app, "BotFan2"), make_account(app, "NoBots")
    join_queue(client, a, mode="casual", allow_bots=True)
    join_queue(client, b, mode="casual", allow_bots=True)
    join_queue(client, c, mode="casual", allow_bots=False)
    assert tick(app) == []  # nobody waited 20 s yet
    clock.advance(19)
    assert tick(app) == []
    clock.advance(2)
    formed = tick(app)
    assert len(formed) == 1
    with ctx_of(app).tx() as db:
        match = db.get(Match, formed[0])
        assert match.mode == "casual" and match.expected_players == 2 and match.bot_slots == 8
        ids = set(db.scalars(select(MatchParticipant.account_id).where(MatchParticipant.match_id == match.id)))
    assert ids == {a.id, b.id}
    assert client.get("/v1/queue/status", headers=c.headers).json()["state"] == "queued"


def test_casual_full_human_match_preferred(client, app, clock):
    online_server(client, app)
    players = make_accounts(app, "hu", 10)
    for p in players:
        join_queue(client, p, mode="casual", allow_bots=True)
    clock.advance(25)
    formed = tick(app)
    assert len(formed) == 1
    with ctx_of(app).tx() as db:
        assert db.get(Match, formed[0]).bot_slots == 0


def test_region_latency_rules(client, app, clock):
    online_server(client, app, server_id="us-host", region="us")
    online_server(client, app, server_id="eu-host", region="eu")
    players = make_accounts(app, "lat", 10)
    for p in players:
        join_queue(client, p, mode="ranked", region="eu", latency_ms={"eu": 180, "us": 90})
    formed = tick(app)
    assert len(formed) == 1
    with ctx_of(app).tx() as db:
        m = db.get(Match, formed[0])
        assert m.region == "us" and m.server_id == "us-host"


def test_full_allocation_flow_issues_one_ticket_per_player(client, app):
    srv = online_server(client, app)
    players = make_accounts(app, "fl", 10)
    for p in players:
        join_queue(client, p, mode="ranked")
    tick(app)
    allocs = poll(client, app, srv, free_ports=[24615, 24616])
    assert len(allocs) == 1 and allocs[0]["port"] == 24615 and allocs[0]["mode"] == "ranked"
    assert allocs[0]["expected_players"] == 10
    assert start_allocation(client, app, srv, allocs[0]).status_code == 200
    teams = participants_by_team(client, players)
    assert len(teams[0]) == 5 and len(teams[1]) == 5
    tickets = set()
    for p in players:
        st = client.get("/v1/queue/status", headers=p.headers).json()
        assert st["state"] == "matched"
        m = st["match"]
        assert m["state"] == "ready" and m["host"] == "127.0.0.1" and m["port"] == 24615
        assert m["ticket"] and m["expires_at"].endswith("Z")
        tickets.add(m["ticket"])
    assert len(tickets) == 10
