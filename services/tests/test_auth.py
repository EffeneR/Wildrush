"""Accounts: register / login / logout / session expiry / me."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from sqlalchemy import select, update

from helpers import PASSWORD, client_from, ctx_of, make_account
from wildrush_svc.models import Account, AuthSession
from wildrush_svc.security import hash_token


def test_register_login_me_logout(client, app):
    r = client.post("/v1/auth/register", json={"username": "Nyx_Main", "password": "hunter2hunter2", "display_name": "  Night Cat  "})
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"account_id", "username", "display_name"}
    assert body["username"] == "Nyx_Main" and body["display_name"] == "Night Cat"

    r = client.post("/v1/auth/login", json={"username": "nyx_main", "password": "hunter2hunter2"})
    assert r.status_code == 200, r.text
    login = r.json()
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", login["token"])
    expires = datetime.strptime(login["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    expected = ctx_of(app).clock.now() + timedelta(hours=12)
    assert abs((expires - expected).total_seconds()) < 5
    assert login["account"]["account_id"] == body["account_id"]
    assert login["account"]["rating"] == {"rating": 1500.0, "deviation": 350.0, "games": 0, "wins": 0, "losses": 0}
    assert "Cache-Control" in r.headers and r.headers["Cache-Control"] == "no-store"

    headers = {"Authorization": f"Bearer {login['token']}"}
    me = client.get("/v1/me", headers=headers).json()
    assert set(me) == {"account_id", "username", "display_name", "created_at", "rating"}
    assert me["username"] == "Nyx_Main"

    # Token stored hashed only.
    with ctx_of(app).tx() as db:
        stored = db.scalars(select(AuthSession.token_hash)).all()
    assert hash_token(login["token"]) in stored and login["token"] not in stored

    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    r = client.get("/v1/me", headers=headers)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_register_conflicts_and_validation(client, app):
    assert client.post("/v1/auth/register", json={"username": "Bruno", "password": "password1"}).status_code == 201
    r = client.post("/v1/auth/register", json={"username": "bRUNO", "password": "password1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "username_taken"
    for i, bad in enumerate((
        {"username": "ab", "password": "password1"},                      # too short
        {"username": "a" * 17, "password": "password1"},                  # too long
        {"username": "bad name", "password": "password1"},                # space
        {"username": "okname", "password": "short"},                      # password < 8
        {"username": "okname", "password": "x" * 129},                    # password > 128
        {"username": "okname", "password": "password1", "display_name": "ab"},
        {"username": "okname", "password": "password1", "display_name": "bad\u0007bell"},
        {"username": "okname", "password": "password1", "role": "admin"},  # unknown field
    )):
        # register is limited to 5/min per IP (invalid attempts count), so vary the client IP
        with client_from(app, f"10.1.0.{i + 1}") as c:
            r = c.post("/v1/auth/register", json=bad)
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["error"]["code"] == "validation_error"


def test_login_failures_do_not_reveal_accounts(client, app):
    make_account(app, "Hops")
    for body in ({"username": "Hops", "password": "wrong-password"}, {"username": "nobody", "password": PASSWORD}):
        r = client.post("/v1/auth/login", json=body)
        assert r.status_code == 401
        assert r.json() == {"error": {"code": "invalid_credentials", "message": "Invalid username or password"}}
    assert client.post("/v1/auth/login", json={"username": "HOPS", "password": PASSWORD}).status_code == 200


def test_session_expires_after_12h(client, app, clock):
    acct = make_account(app, "Vex")
    assert client.get("/v1/me", headers=acct.headers).status_code == 200
    clock.advance(12 * 3600 - 10)
    assert client.get("/v1/me", headers=acct.headers).status_code == 200
    clock.advance(20)
    r = client.get("/v1/me", headers=acct.headers)
    assert r.status_code == 401 and r.headers.get("WWW-Authenticate") == "Bearer"


def test_bad_authorization_headers(client, app):
    make_account(app, "Scrap")
    for value in ("", "Bearer", "Bearer x", "Basic abc", "Bearer " + "A" * 43, "bearer " + "!" * 43):
        r = client.get("/v1/me", headers={"Authorization": value})
        assert r.status_code == 401, value


def test_password_rehash_on_login_when_parameters_change(client, app):
    acct = make_account(app, "Rehash")
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(PASSWORD)
    ctx = ctx_of(app)
    with ctx.tx() as db:
        db.execute(update(Account).where(Account.id == acct.id).values(password_hash=weak))
    r = client.post("/v1/auth/login", json={"username": "Rehash", "password": PASSWORD})
    assert r.status_code == 200
    with ctx.tx() as db:
        stored = db.scalar(select(Account.password_hash).where(Account.id == acct.id))
    assert stored != weak and stored.startswith("$argon2id$") and "m=65536,t=3,p=4" in stored


def test_logout_revokes_only_that_session(client, app):
    acct = make_account(app, "TwoDevices")
    r = client.post("/v1/auth/login", json={"username": "TwoDevices", "password": PASSWORD})
    other = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.post("/v1/auth/logout", headers=acct.headers).status_code == 204
    assert client.get("/v1/me", headers=acct.headers).status_code == 401
    assert client.get("/v1/me", headers=other).status_code == 200
