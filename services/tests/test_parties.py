"""Parties: invite / accept / decline / kick / promote / leave, max 5, one party per account."""

from __future__ import annotations

from helpers import join_queue, make_account, make_accounts, make_party


def test_create_and_view_party(client, app):
    a = make_account(app, "Leader")
    r = client.post("/v1/parties", headers=a.headers)
    assert r.status_code == 201
    party = r.json()
    assert party["leader_id"] == str(a.id)
    assert party["members"] == [{"account_id": str(a.id), "username": "Leader", "display_name": "Leader"}]
    assert party["invites"] == [] and party["queue"] is None
    r = client.post("/v1/parties", headers=a.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_in_party"
    other = make_account(app, "Loner")
    r = client.get("/v1/parties/current", headers=other.headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_party"


def test_invite_accept_decline_flow(client, app):
    lead, b, c = make_account(app, "Lead"), make_account(app, "Bee"), make_account(app, "Cee")
    client.post("/v1/parties", headers=lead.headers)
    r = client.post("/v1/parties/current/invites", json={"username": "bee"}, headers=lead.headers)
    assert r.status_code == 201
    inv = r.json()
    assert inv["to_username"] == "Bee" and inv["expires_at"].endswith("Z")
    r = client.post("/v1/parties/current/invites", json={"username": "Bee"}, headers=lead.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_invited"
    r = client.post("/v1/parties/current/invites", json={"username": "ghost_user"}, headers=lead.headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_such_user"
    r = client.post("/v1/parties/current/invites", json={"username": "Lead"}, headers=lead.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_in_party"

    mine = client.get("/v1/invites", headers=b.headers).json()
    assert [(i["invite_id"], i["from_username"]) for i in mine] == [(inv["invite_id"], "Lead")]
    assert client.get("/v1/invites", headers=c.headers).json() == []
    # someone else cannot accept my invite
    assert client.post(f"/v1/invites/{inv['invite_id']}/accept", headers=c.headers).status_code == 404

    party = client.post(f"/v1/invites/{inv['invite_id']}/accept", headers=b.headers)
    assert party.status_code == 200
    assert [m["username"] for m in party.json()["members"]] == ["Lead", "Bee"]
    # accepted invites are no longer pending
    assert client.get("/v1/invites", headers=b.headers).json() == []

    inv_c = client.post("/v1/parties/current/invites", json={"username": "Cee"}, headers=lead.headers).json()
    assert [i["to_username"] for i in client.get("/v1/parties/current", headers=lead.headers).json()["invites"]] == ["Cee"]
    assert client.post(f"/v1/invites/{inv_c['invite_id']}/decline", headers=c.headers).status_code == 204
    assert client.get("/v1/parties/current", headers=lead.headers).json()["invites"] == []
    r = client.post(f"/v1/invites/{inv_c['invite_id']}/accept", headers=c.headers)
    assert r.status_code == 404


def test_only_leader_invites_kicks_promotes(client, app):
    lead, b, c = make_account(app, "Boss"), make_account(app, "Member"), make_account(app, "Outsider")
    make_party(client, lead, [b])
    r = client.post("/v1/parties/current/invites", json={"username": "Outsider"}, headers=b.headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_leader"
    r = client.post("/v1/parties/current/kick", json={"account_id": str(lead.id)}, headers=b.headers)
    assert r.status_code == 403
    r = client.post("/v1/parties/current/promote", json={"account_id": str(b.id)}, headers=b.headers)
    assert r.status_code == 403
    r = client.post("/v1/parties/current/kick", json={"account_id": str(c.id)}, headers=lead.headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_in_party"


def test_kick_and_promote(client, app):
    lead, b, c = make_account(app, "Chief"), make_account(app, "Second"), make_account(app, "Third")
    make_party(client, lead, [b, c])
    assert client.post("/v1/parties/current/kick", json={"account_id": str(c.id)}, headers=lead.headers).status_code == 204
    assert client.get("/v1/parties/current", headers=c.headers).status_code == 404
    assert client.post("/v1/parties/current/promote", json={"account_id": str(b.id)}, headers=lead.headers).status_code == 204
    party = client.get("/v1/parties/current", headers=b.headers).json()
    assert party["leader_id"] == str(b.id)
    # the old leader can no longer invite
    assert client.post("/v1/parties/current/invites", json={"username": "Third"}, headers=lead.headers).status_code == 403


def test_leader_leave_promotes_longest_standing_member_and_empty_party_is_deleted(client, app, clock):
    lead, b, c = make_account(app, "First"), make_account(app, "Early"), make_account(app, "Late")
    client.post("/v1/parties", headers=lead.headers)
    for m in (b, c):
        inv = client.post("/v1/parties/current/invites", json={"username": m.username}, headers=lead.headers).json()
        clock.advance(2)
        assert client.post(f"/v1/invites/{inv['invite_id']}/accept", headers=m.headers).status_code == 200
    assert client.post("/v1/parties/current/leave", headers=lead.headers).status_code == 204
    party = client.get("/v1/parties/current", headers=c.headers).json()
    assert party["leader_id"] == str(b.id)
    assert [m["username"] for m in party["members"]] == ["Early", "Late"]
    assert client.post("/v1/parties/current/leave", headers=b.headers).status_code == 204
    assert client.post("/v1/parties/current/leave", headers=c.headers).status_code == 204
    assert client.get("/v1/parties/current", headers=c.headers).status_code == 404
    assert client.post("/v1/parties/current/leave", headers=c.headers).status_code == 404


def test_max_five_members(client, app):
    lead = make_account(app, "Big")
    members = make_accounts(app, "mem", 5)
    make_party(client, lead, members[:4])
    r = client.post("/v1/parties/current/invites", json={"username": members[4].username}, headers=lead.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "party_full"


def test_party_full_on_accept(client, app):
    lead = make_account(app, "Host")
    members = make_accounts(app, "ply", 5)
    client.post("/v1/parties", headers=lead.headers)
    invites = [
        client.post("/v1/parties/current/invites", json={"username": m.username}, headers=lead.headers).json()
        for m in members
    ]
    for m, inv in zip(members[:4], invites[:4]):
        assert client.post(f"/v1/invites/{inv['invite_id']}/accept", headers=m.headers).status_code == 200
    r = client.post(f"/v1/invites/{invites[4]['invite_id']}/accept", headers=members[4].headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "party_full"
    assert len(client.get("/v1/parties/current", headers=lead.headers).json()["members"]) == 5


def test_one_party_per_account(client, app):
    a, b, x = make_account(app, "Alpha"), make_account(app, "Beta"), make_account(app, "Xeno")
    client.post("/v1/parties", headers=a.headers)
    client.post("/v1/parties", headers=b.headers)
    inv_a = client.post("/v1/parties/current/invites", json={"username": "Xeno"}, headers=a.headers).json()
    inv_b = client.post("/v1/parties/current/invites", json={"username": "Xeno"}, headers=b.headers).json()
    assert client.post(f"/v1/invites/{inv_a['invite_id']}/accept", headers=x.headers).status_code == 200
    r = client.post(f"/v1/invites/{inv_b['invite_id']}/accept", headers=x.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_in_party"
    # inviting someone who is already in a party is refused up front
    r = client.post("/v1/parties/current/invites", json={"username": "Alpha"}, headers=b.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_in_party"


def test_invites_expire_after_5_minutes(client, app, clock):
    lead, b = make_account(app, "Timer"), make_account(app, "Slow")
    client.post("/v1/parties", headers=lead.headers)
    inv = client.post("/v1/parties/current/invites", json={"username": "Slow"}, headers=lead.headers).json()
    clock.advance(5 * 60 + 1)
    assert client.get("/v1/invites", headers=b.headers).json() == []
    assert client.get("/v1/parties/current", headers=lead.headers).json()["invites"] == []
    r = client.post(f"/v1/invites/{inv['invite_id']}/accept", headers=b.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "expired"
    # a fresh invite works again after expiry
    r = client.post("/v1/parties/current/invites", json={"username": "Slow"}, headers=lead.headers)
    assert r.status_code == 201


def test_joining_or_leaving_removes_party_from_queue(client, app):
    lead, b, c = make_account(app, "Qlead"), make_account(app, "Qbee"), make_account(app, "Qcee")
    make_party(client, lead, [b])
    assert join_queue(client, lead).status_code == 202
    assert client.get("/v1/queue/status", headers=b.headers).json()["state"] == "queued"
    assert client.get("/v1/parties/current", headers=b.headers).json()["queue"]["state"] == "queued"
    inv = client.post("/v1/parties/current/invites", json={"username": "Qcee"}, headers=lead.headers).json()
    assert client.post(f"/v1/invites/{inv['invite_id']}/accept", headers=c.headers).status_code == 200
    for acct in (lead, b, c):
        assert client.get("/v1/queue/status", headers=acct.headers).json()["state"] == "idle"
    assert join_queue(client, lead).status_code == 202
    assert client.post("/v1/parties/current/leave", headers=c.headers).status_code == 204
    assert client.get("/v1/queue/status", headers=lead.headers).json()["state"] == "idle"
