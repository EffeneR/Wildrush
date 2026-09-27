"""Server-signed, idempotent, transactional results; ratings, mastery, history."""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import func, select

from helpers import (
    ctx_of,
    make_account,
    make_accounts,
    online_server,
    participants_by_team,
    ready_match,
    result_body,
    running_match,
    signed,
)
from wildrush_svc.models import AccountBadge, FighterMastery, MatchPlayerResult, MatchResult, Rating


def submit(client, app, srv, match_id, body, **kw):
    return signed(client, app, srv, "POST", f"/v1/matches/{match_id}/result", body, **kw)


def ranked_setup(client, app, prefix="rs", ratings=None):
    srv = online_server(client, app)
    players = make_accounts(app, prefix, 10, ratings=ratings)
    match_id = running_match(client, app, srv, players, mode="ranked")
    teams = participants_by_team(client, players)
    return srv, players, match_id, teams


def db_snapshot(app, ids):
    with ctx_of(app).tx() as db:
        ratings = {r.account_id: (r.rating, r.deviation, r.games, r.wins, r.losses) for r in db.scalars(select(Rating).where(Rating.account_id.in_(ids)))}
        xp = {(m.account_id, m.fighter): m.xp for m in db.scalars(select(FighterMastery).where(FighterMastery.account_id.in_(ids)))}
        history = db.scalar(select(func.count()).select_from(MatchPlayerResult))
        results = db.scalar(select(func.count()).select_from(MatchResult))
    return ratings, xp, history, results


def test_ranked_result_applies_once_and_is_idempotent(client, app):
    srv, players, match_id, teams = ranked_setup(client, app)
    body = result_body(match_id, teams, winner=0)
    r = submit(client, app, srv, match_id, body)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["applied"] is True
    assert set(first["rating_changes"]) == {str(p.id) for p in players}
    for p in teams[0]:
        change = first["rating_changes"][str(p.id)]
        assert change["before"] == 1500.0 and change["after"] > 1500.0
    for p in teams[1]:
        assert first["rating_changes"][str(p.id)]["after"] < 1500.0
    before = db_snapshot(app, [p.id for p in players])

    # identical retransmission (even with different key order / int-vs-float) -> same answer
    again = copy.deepcopy(body)
    again["players"] = list(reversed(again["players"]))
    again["players"] = [dict(reversed(list(p.items()))) for p in again["players"]]
    r2 = submit(client, app, srv, match_id, body)
    assert r2.status_code == 200
    assert r2.json() == {**first, "applied": False, "idempotent": True}
    r3 = submit(client, app, srv, match_id, {**body, "duration_s": 402.5})
    assert r3.status_code == 200 and r3.json()["idempotent"] is True
    assert db_snapshot(app, [p.id for p in players]) == before  # no double rating / XP / history

    # different body -> conflict, still nothing changes
    r4 = submit(client, app, srv, match_id, {**body, "score": [250, 174]})
    assert r4.status_code == 409 and r4.json()["error"]["code"] == "result_conflict"
    assert db_snapshot(app, [p.id for p in players]) == before

    ratings, xp, history, results = before
    assert history == 10 and results == 1
    for p in teams[0]:
        assert ratings[p.id][2:] == (1, 1, 0)
    for p in teams[1]:
        assert ratings[p.id][2:] == (1, 0, 1)
    # history rows + mastery
    hist = client.get("/v1/matches/history", headers=teams[0][0].headers).json()
    assert len(hist) == 1 and hist[0]["match_id"] == match_id and hist[0]["won"] is True
    assert hist[0]["mode"] == "ranked" and hist[0]["score"] == [250, 173] and hist[0]["rating_delta"] > 0
    assert hist[0]["fighter"] == "nyx" and hist[0]["team"] == 0
    detail = client.get(f"/v1/matches/{match_id}", headers=teams[1][0].headers).json()
    assert detail["state"] == "finished" and detail["result"]["winner_team"] == 0
    assert detail["rating_changes"] == first["rating_changes"]


def test_result_requires_valid_signature_and_allocated_server(client, app):
    srv, players, match_id, teams = ranked_setup(client, app, prefix="sg")
    other = online_server(client, app, server_id="rogue-host")
    body = result_body(match_id, teams)
    r = client.post(f"/v1/matches/{match_id}/result", json=body)
    assert r.status_code == 401 and r.json()["error"]["code"] == "server_auth_required"
    r = submit(client, app, srv, match_id, body, secret="wrong-secret-value")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_signature"
    r = submit(client, app, other, match_id, body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "wrong_server"
    assert db_snapshot(app, [p.id for p in players])[3] == 0


def test_result_requires_running_match(client, app):
    srv = online_server(client, app)
    players = make_accounts(app, "nr", 10)
    match_id, _ = ready_match(client, app, srv, players)  # ready, not running
    teams = participants_by_team(client, players)
    r = submit(client, app, srv, match_id, result_body(match_id, teams))
    assert r.status_code == 409 and r.json()["error"]["code"] == "match_not_running"


def test_ranked_with_bots_rejected(client, app):
    srv, players, match_id, teams = ranked_setup(client, app, prefix="rb")
    body = result_body(match_id, teams, bots=[{"team": 1, "fighter": "hops"}])
    r = submit(client, app, srv, match_id, body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "bots_in_ranked"
    assert db_snapshot(app, [p.id for p in players])[3] == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b["players"].pop(),                                     # ranked must list all 10
        lambda b: b["players"][0].update(team=1 - b["players"][0]["team"]),  # wrong team
        lambda b: b["players"][1].update(fighter=b["players"][0]["fighter"]),  # species twice
        lambda b: b["players"][0].update(account_id="00000000-0000-4000-8000-000000000009"),
        lambda b: b.update(match_id="00000000-0000-4000-8000-000000000009"),
        lambda b: b.update(winner_team=2),
        lambda b: b.update(score=[250]),
        lambda b: b.update(ended_reason="rage_quit"),
        lambda b: b["players"][0].update(kos=-1),
        lambda b: b["players"][0].update(damage_dealt="lots"),
        lambda b: b["players"][0].update(abandoned="no"),
        lambda b: b["players"][0].update(hacked=True),
        lambda b: b.update(extra_field=1),
    ],
)
def test_invalid_results_rejected_without_side_effects(client, app, mutate):
    srv, players, match_id, teams = ranked_setup(client, app, prefix="iv")
    body = result_body(match_id, teams)
    mutate(body)
    r = submit(client, app, srv, match_id, body)
    assert r.status_code == 422, r.text
    assert db_snapshot(app, [p.id for p in players])[3] == 0
    # a valid result is still accepted afterwards
    assert submit(client, app, srv, match_id, result_body(match_id, teams)).status_code == 200


def test_abandoned_player_is_rated_as_loss_and_gets_no_xp(client, app):
    srv, players, match_id, teams = ranked_setup(client, app, prefix="ab")
    body = result_body(match_id, teams, winner=0)
    quitter = teams[0][0]
    for p in body["players"]:
        if p["account_id"] == str(quitter.id):
            p["abandoned"] = True
    r = submit(client, app, srv, match_id, body).json()
    assert r["rating_changes"][str(quitter.id)]["after"] < 1500.0
    assert r["mastery_changes"][str(quitter.id)]["xp_gained"] == 0
    with ctx_of(app).tx() as db:
        row = db.get(Rating, quitter.id)
        assert (row.games, row.wins, row.losses) == (1, 0, 1)


def test_casual_result_with_bots_awards_xp_but_no_rating(client, app, clock):
    srv = online_server(client, app)
    a, b = make_account(app, "CasOne"), make_account(app, "CasTwo")
    for p in (a, b):
        client.post("/v1/queue", json={"mode": "casual", "region": "eu", "allow_bots": True}, headers=p.headers)
    clock.advance(21)
    from helpers import heartbeat, poll, start_allocation

    heartbeat(client, app, srv)
    assert len(app.state.matchmaker.tick()) == 1
    alloc = poll(client, app, srv)[0]
    assert alloc["expected_players"] == 2 and alloc["mode"] == "casual"
    start_allocation(client, app, srv, alloc)
    match_id = alloc["match_id"]
    signed(client, app, srv, "POST", f"/v1/matches/{match_id}/started", {})
    teams = participants_by_team(client, [a, b])
    bots = [{"team": t, "fighter": f} for t in (0, 1) for f in ("bruno", "vex", "hops", "scrap")]
    body = result_body(match_id, teams, winner=1, bots=bots)
    r = submit(client, app, srv, match_id, body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["rating_changes"] == {}
    winner = teams[1][0]
    loser = teams[0][0]
    assert out["mastery_changes"][str(winner.id)]["xp_gained"] == 312  # 100 + 50 + 122 + 40
    assert out["mastery_changes"][str(loser.id)]["xp_gained"] == 262
    with ctx_of(app).tx() as db:
        assert db.get(Rating, winner.id).games == 0
        badges = set(db.scalars(select(AccountBadge.badge).where(AccountBadge.account_id == winner.id)))
    assert "pack_debut" in badges
    hist = client.get("/v1/matches/history", headers=winner.headers).json()
    assert hist[0]["rating_delta"] is None and hist[0]["mode"] == "casual"


def test_mastery_level_ups_unlock_badges_and_palettes(client, app):
    srv, players, match_id, teams = ranked_setup(client, app, prefix="lv")
    star = teams[0][0]  # plays nyx in result_body
    with ctx_of(app).tx() as db:
        row = db.get(FighterMastery, (star.id, "nyx"))
        row.xp = 1400  # level 3; +312 -> 1712 = level 4
    submit(client, app, srv, match_id, result_body(match_id, teams, winner=0))
    profile = client.get("/v1/profile", headers=star.headers).json()
    assert profile["fighters"]["nyx"]["level"] == 4
    assert profile["fighters"]["nyx"]["palettes"] == ["default", "dusk"]
    assert set(profile["badges"]) == {"nyx_adept", "pack_debut"}  # initiate (L2) was before this match
    r = client.patch("/v1/profile", json={"selected_badge": "nyx_adept", "selected_palettes": {"nyx": "dusk"}}, headers=star.headers)
    assert r.status_code == 200


def test_history_pagination_and_privacy(client, app, clock):
    srv = online_server(client, app)
    players = make_accounts(app, "hp", 10)
    match_ids = []
    for i in range(3):
        match_id = running_match(client, app, srv, players, mode="ranked")
        teams = participants_by_team(client, players)
        assert submit(client, app, srv, match_id, result_body(match_id, teams, winner=i % 2)).status_code == 200
        match_ids.append(match_id)
        clock.advance(600)
        from helpers import heartbeat

        heartbeat(client, app, srv)
    me = players[0]
    hist = client.get("/v1/matches/history", headers=me.headers).json()
    assert [h["match_id"] for h in hist] == list(reversed(match_ids))
    page = client.get("/v1/matches/history?limit=2", headers=me.headers).json()
    assert len(page) == 2
    older = client.get("/v1/matches/history", params={"limit": 20, "before": page[-1]["ended_at"]}, headers=me.headers).json()
    assert [h["match_id"] for h in older] == [match_ids[0]]
    for bad in ("limit=0", "limit=101", "before=yesterday", "before=' OR 1=1 --"):
        assert client.get(f"/v1/matches/history?{bad}", headers=me.headers).status_code == 422
    stranger = make_account(app, "Stranger")
    assert client.get(f"/v1/matches/{match_ids[0]}", headers=stranger.headers).status_code == 404
    assert client.get("/v1/matches/history", headers=stranger.headers).json() == []
