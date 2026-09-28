"""Queue join / leave / status and real counts."""

from __future__ import annotations

from helpers import join_queue, make_account, make_accounts, make_party, queue_body


def test_join_status_leave(client, app, clock):
    a = make_account(app, "Solo")
    r = join_queue(client, a, mode="casual", roster_prefs=["nyx", "vex"], allow_bots=True)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["state"] == "queued" and body["mode"] == "casual" and body["match"] is None
    assert body["counts"] == {"casual": 1, "ranked": 0}
    clock.advance(7)
    status = client.get("/v1/queue/status", headers=a.headers).json()
    assert status["state"] == "queued" and 7 <= status["queued_seconds"] <= 8
    r = join_queue(client, a)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_queued"
    assert client.delete("/v1/queue", headers=a.headers).status_code == 204
    status = client.get("/v1/queue/status", headers=a.headers).json()
    assert status == {"state": "idle", "mode": None, "queued_seconds": None, "counts": {"casual": 0, "ranked": 0}, "match": None}
    # leaving when not queued is a no-op
    assert client.delete("/v1/queue", headers=a.headers).status_code == 204


def test_counts_are_real_player_numbers(client, app):
    solos = make_accounts(app, "cas", 3)
    lead = make_account(app, "PartyLead")
    mates = make_accounts(app, "mate", 2)
    watcher = make_account(app, "Watcher")
    assert client.get("/v1/queue/status", headers=watcher.headers).json()["counts"] == {"casual": 0, "ranked": 0}
    for s in solos:
        join_queue(client, s, mode="casual")
    make_party(client, lead, mates)
    assert join_queue(client, lead, mode="ranked").status_code == 202
    counts = client.get("/v1/queue/status", headers=watcher.headers).json()["counts"]
    assert counts == {"casual": 3, "ranked": 3}


def test_party_queueing_rules(client, app):
    lead, member = make_account(app, "PLead"), make_account(app, "PMate")
    make_party(client, lead, [member])
    r = join_queue(client, member)
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_leader"
    assert join_queue(client, lead, mode="ranked").status_code == 202
    status = client.get("/v1/queue/status", headers=member.headers).json()
    assert status["state"] == "queued" and status["mode"] == "ranked"
    # any member may cancel the party's queue
    assert client.delete("/v1/queue", headers=member.headers).status_code == 204
    assert client.get("/v1/queue/status", headers=lead.headers).json()["state"] == "idle"


def test_queue_validation(client, app):
    a = make_account(app, "Validator")
    bad_bodies = [
        queue_body(mode="ranked", allow_bots=True),
        queue_body(mode="arcade"),
        queue_body(region="EU"),
        queue_body(region="x"),
        queue_body(roster_prefs=["nyx", "nyx"]),
        queue_body(roster_prefs=["nyx", "wolf"]),
        queue_body(roster_prefs=["nyx", "bruno", "vex", "hops", "scrap", "nyx"]),
        queue_body(latency_ms={"eu": -1}),
        queue_body(latency_ms={"eu": "20"}),
        queue_body(allow_bots="yes"),
        {**queue_body(), "party_size": 5},
    ]
    for body in bad_bodies:
        r = client.post("/v1/queue", json=body, headers=a.headers)
        assert r.status_code == 422, (body, r.text)
    r = client.post("/v1/queue", json=queue_body(mode="ranked", allow_bots=True), headers=a.headers)
    assert r.json()["error"]["code"] == "bots_in_ranked"
    assert client.get("/v1/queue/status", headers=a.headers).json()["state"] == "idle"
    # measured latencies may be fractional (rounded); strings/booleans are not numbers
    assert client.post("/v1/queue", json=queue_body(latency_ms={"eu": 42.7, "us": 131}), headers=a.headers).status_code == 202
