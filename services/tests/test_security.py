"""Server HMAC request auth (timestamp window, forgery) and hostile inputs."""

from __future__ import annotations

from sqlalchemy import func, select, text

from helpers import ctx_of, heartbeat, make_account, make_server, online_server, signed
from wildrush_svc.models import Account, GameServer
from wildrush_svc.security import sign_request


def poll_body():
    return {"free_ports": [24610]}


def test_timestamp_window_is_60_seconds(client, app):
    srv = online_server(client, app)
    assert signed(client, app, srv, "POST", "/v1/allocator/poll", poll_body(), ts_offset=-59).status_code == 200
    assert signed(client, app, srv, "POST", "/v1/allocator/poll", poll_body(), ts_offset=59).status_code == 200
    for offset in (-61, 61, -3600):
        r = signed(client, app, srv, "POST", "/v1/allocator/poll", poll_body(), ts_offset=offset)
        assert r.status_code == 401 and r.json()["error"]["code"] == "timestamp_skew", offset


def test_signature_binds_method_path_query_and_body(client, app):
    srv = online_server(client, app)
    # body tampering: signature computed over a different body
    ts = str(int(ctx_of(app).clock.now().timestamp()))
    sig = sign_request(srv.secret, "POST", "/v1/allocator/poll", ts, b'{"free_ports":[24610]}')
    r = client.post("/v1/allocator/poll", content=b'{"free_ports":[24611]}',
                    headers={"X-WR-Server": srv.id, "X-WR-Timestamp": ts, "X-WR-Signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_signature"
    # path tampering
    r = signed(client, app, srv, "POST", "/v1/allocator/poll", poll_body(), sign_path="/v1/servers/heartbeat")
    assert r.status_code == 401
    # query string is part of PATH: signing without it fails, signing with it succeeds
    r = signed(client, app, srv, "POST", "/v1/allocator/poll?x=1", poll_body(), sign_path="/v1/allocator/poll")
    assert r.status_code == 401
    r = signed(client, app, srv, "POST", "/v1/allocator/poll?x=1", poll_body())
    assert r.status_code == 200
    # method tampering
    ts = str(int(ctx_of(app).clock.now().timestamp()))
    body = b'{"free_ports":[24610]}'
    sig = sign_request(srv.secret, "GET", "/v1/allocator/poll", ts, body)
    r = client.post("/v1/allocator/poll", content=body,
                    headers={"X-WR-Server": srv.id, "X-WR-Timestamp": ts, "X-WR-Signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 401


def test_missing_or_malformed_server_headers(client, app):
    srv = online_server(client, app)
    good_ts = str(int(ctx_of(app).clock.now().timestamp()))
    cases = [
        {},
        {"X-WR-Server": srv.id, "X-WR-Timestamp": good_ts},
        {"X-WR-Server": "x' OR '1'='1", "X-WR-Timestamp": good_ts, "X-WR-Signature": "0" * 64},
        {"X-WR-Server": srv.id, "X-WR-Timestamp": "12.5", "X-WR-Signature": "0" * 64},
        {"X-WR-Server": srv.id, "X-WR-Timestamp": good_ts, "X-WR-Signature": "zz" * 32},
    ]
    for headers in cases:
        r = client.post("/v1/allocator/poll", json=poll_body(), headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "server_auth_required", headers
    # well-formed but unknown server / wrong secret / other server's secret
    other = make_server(app, "other-host")
    for kwargs in ({"server_id": "no-such-host"}, {"secret": "x" * 43}, {"secret": other.secret}):
        r = signed(client, app, srv, "POST", "/v1/allocator/poll", poll_body(), **kwargs)
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_signature", kwargs


def test_get_request_signed_with_empty_body(client, app):
    srv = online_server(client, app)
    # POST-only endpoint: GET with a valid signature is a 405, never a crash
    r = signed(client, app, srv, "GET", "/v1/allocator/poll")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


def test_player_token_cannot_call_server_endpoints_and_vice_versa(client, app):
    srv = online_server(client, app)
    a = make_account(app, "Sneaky")
    r = client.post("/v1/allocator/poll", json=poll_body(), headers=a.headers)
    assert r.status_code == 401
    r = client.get("/v1/me", headers={"X-WR-Server": srv.id})
    assert r.status_code == 401


def test_sql_injection_like_inputs_are_rejected_or_harmless(client, app):
    a = make_account(app, "Victim")
    injections = ["' OR '1'='1", "x'; DROP TABLE accounts; --", "admin'--", "\" OR \"\"=\"", "%' --"]
    for payload in injections:
        r = client.post("/v1/auth/login", json={"username": payload, "password": payload})
        assert r.status_code in (401, 422), r.text
        r = client.post("/v1/auth/register", json={"username": payload, "password": "password123"})
        assert r.status_code in (422, 429), r.text
        r = client.post("/v1/parties/current/invites", json={"username": payload}, headers=a.headers)
        assert r.status_code in (404, 422), r.text
        r = client.post("/v1/queue", json={"mode": "casual", "region": payload}, headers=a.headers)
        assert r.status_code == 422
        r = client.post("/v1/private/join", json={"join_code": payload}, headers=a.headers)
        assert r.status_code == 422
        r = client.get("/v1/matches/history", params={"before": payload}, headers=a.headers)
        assert r.status_code == 422
    r = client.get("/v1/matches/1%20OR%201=1", headers=a.headers)
    assert r.status_code == 422
    r = client.post("/v1/invites/'%3B%20DROP%20TABLE%20parties/accept", headers=a.headers)
    assert r.status_code == 422
    # display names may contain quotes; they are stored verbatim (parameterized SQL)
    r = client.patch("/v1/profile", json={"display_name": "Robert'); DROP"}, headers=a.headers)
    assert r.status_code == 200 and r.json()["display_name"] == "Robert'); DROP"
    with ctx_of(app).tx() as db:
        assert db.scalar(select(func.count()).select_from(Account)) == 1
        assert db.scalar(text("SELECT to_regclass('public.accounts') IS NOT NULL"))
        assert db.scalar(text("SELECT to_regclass('public.parties') IS NOT NULL"))
    assert client.get("/v1/me", headers=a.headers).status_code == 200


def test_body_size_limit_and_content_type(client, app):
    a = make_account(app, "BigBody")
    huge = b'{"display_name": "' + b"x" * 70_000 + b'"}'
    r = client.patch("/v1/profile", content=huge, headers={**a.headers, "Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    r = client.patch("/v1/profile", content=b'{"display_name": "Plain"}', headers={**a.headers, "Content-Type": "text/plain"})
    assert r.status_code == 422
    r = client.patch("/v1/profile", content=b'{"display_name": ', headers={**a.headers, "Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_server_secret_never_returned(client, app):
    srv = online_server(client, app)
    heartbeat(client, app, srv)
    for path in ("/v1/servers", "/v1/version", "/healthz"):
        assert srv.secret not in client.get(path).text
    with ctx_of(app).tx() as db:
        assert db.scalar(select(GameServer.secret).where(GameServer.id == srv.id)) == srv.secret


def test_unknown_routes_use_error_envelope(client):
    r = client.get("/v1/does-not-exist")
    assert r.status_code == 404 and r.json() == {"error": {"code": "not_found", "message": "Not Found"}}
    r = client.put("/v1/me")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"
