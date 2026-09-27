"""Rate limits (contract): 429 rate_limited with Retry-After."""

from __future__ import annotations

from helpers import PASSWORD, client_from, join_queue, make_account, make_accounts


def assert_limited(r):
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(r.headers["Retry-After"]) <= 60


def test_login_limited_per_ip(app):
    make_account(app, "Target")
    with client_from(app, "10.9.0.1") as c:
        for _ in range(10):
            assert c.post("/v1/auth/login", json={"username": "Target", "password": "wrong-pass"}).status_code == 401
        assert_limited(c.post("/v1/auth/login", json={"username": "Target", "password": PASSWORD}))
    with client_from(app, "10.9.0.2") as other_ip:  # a different IP is unaffected (username has 9 left)
        assert other_ip.post("/v1/auth/login", json={"username": "someone_else", "password": "x"}).status_code == 401


def test_login_limited_per_username_across_ips(app):
    make_account(app, "Popular")
    for i in range(10):
        with client_from(app, f"10.8.0.{i + 1}") as c:
            assert c.post("/v1/auth/login", json={"username": "popular", "password": "wrong-pass"}).status_code == 401
    with client_from(app, "10.8.1.1") as c:
        assert_limited(c.post("/v1/auth/login", json={"username": "POPULAR", "password": PASSWORD}))
        # other usernames from the same fresh IP still work
        make_account(app, "Unpopular")
        assert c.post("/v1/auth/login", json={"username": "Unpopular", "password": PASSWORD}).status_code == 200


def test_register_limited_per_ip(app):
    with client_from(app, "10.7.0.1") as c:
        for i in range(5):
            assert c.post("/v1/auth/register", json={"username": f"newbie{i}", "password": "password1"}).status_code == 201
        assert_limited(c.post("/v1/auth/register", json={"username": "newbie9", "password": "password1"}))
    with client_from(app, "10.7.0.2") as c:
        assert c.post("/v1/auth/register", json={"username": "newbie9", "password": "password1"}).status_code == 201


def test_party_invites_limited_per_account(client, app):
    lead = make_account(app, "Spammer")
    targets = make_accounts(app, "tgt", 21)
    client.post("/v1/parties", headers=lead.headers)
    codes = []
    for t in targets:
        r = client.post("/v1/parties/current/invites", json={"username": t.username}, headers=lead.headers)
        codes.append(r.status_code)
    # 10 pending invites max per party, the rest 409 until the 21st request is rate limited
    assert codes[:10] == [201] * 10 and set(codes[10:20]) == {409}
    r = client.post("/v1/parties/current/invites", json={"username": targets[0].username}, headers=lead.headers)
    assert_limited(r)


def test_queue_join_leave_limited_per_account(client, app):
    a = make_account(app, "Flapper")
    for _ in range(10):
        assert join_queue(client, a).status_code == 202
        assert client.delete("/v1/queue", headers=a.headers).status_code == 204
    assert_limited(join_queue(client, a))
    # other endpoints use the general bucket
    assert client.get("/v1/queue/status", headers=a.headers).status_code == 200


def test_general_limit_120_per_account(client, app):
    a, b = make_account(app, "Chatty"), make_account(app, "Quiet")
    for _ in range(120):
        assert client.get("/v1/me", headers=a.headers).status_code == 200
    assert_limited(client.get("/v1/profile", headers=a.headers))
    assert client.get("/v1/me", headers=b.headers).status_code == 200


def test_unauthenticated_requests_limited_per_ip(app):
    with client_from(app, "10.6.0.1") as c:
        for _ in range(120):
            assert c.get("/v1/me", headers={"Authorization": "Bearer " + "A" * 43}).status_code == 401
        assert_limited(c.get("/v1/servers"))
