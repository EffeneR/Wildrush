"""Password hashing, session tokens, server request signing and join tickets.

Wire formats (see docs/API_CONTRACT.md and services/CONTRACT_NOTES.md):

* base64url is RFC 4648 §5 **without** ``=`` padding.
* Session token: base64url(32 random bytes) -> 43 chars. Stored as hex(SHA-256(token ASCII)).
* Server secret: ``secrets.token_urlsafe(32)`` (43 chars). The HMAC key is the ASCII bytes of
  the secret string exactly as printed by the admin CLI (it is *not* base64-decoded).
* Request signature: hex(HMAC-SHA256(secret, METHOD "\n" PATH "\n" TIMESTAMP "\n" hex(SHA256(body)))).
* Join ticket: base64url(payload_json) "." base64url(HMAC-SHA256(secret, payload_b64 ASCII)).
  payload_json is compact JSON with keys in the order tid, mid, aid, sid, team, role, exp.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import threading
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id with argon2-cffi defaults (contract)
_dummy_lock = threading.Lock()
_dummy_hash: str | None = None

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")
SERVER_ID_RE = re.compile(r"[a-z0-9-]{3,40}")
TIMESTAMP_RE = re.compile(r"[0-9]{1,12}")
SIGNATURE_RE = re.compile(r"[0-9a-f]{64}")
TICKET_KEYS = ("tid", "mid", "aid", "sid", "team", "role", "exp")
MAX_TICKET_LEN = 1024


# --- passwords -----------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> tuple[bool, bool]:
    """Return ``(ok, needs_rehash)``."""
    try:
        _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, False
    return True, _hasher.check_needs_rehash(stored_hash)


def burn_password_check(password: str) -> None:
    """Spend the same time as a real verification (unknown usernames)."""
    global _dummy_hash
    with _dummy_lock:
        if _dummy_hash is None:
            _dummy_hash = _hasher.hash(secrets.token_urlsafe(16))
        dummy = _dummy_hash
    verify_password(dummy, password)


# --- base64url -----------------------------------------------------------------------------

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]*", text):
        raise ValueError("not base64url")
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("not base64url") from exc


# --- session tokens ----------------------------------------------------------------------

def new_session_token() -> str:
    return b64url_encode(secrets.token_bytes(32))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def is_token_shaped(token: str) -> bool:
    return bool(TOKEN_RE.fullmatch(token))


# --- server secrets and request signing ------------------------------------------------------

def new_server_secret() -> str:
    return secrets.token_urlsafe(32)


def body_sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def signing_string(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    return f"{method.upper()}\n{path}\n{timestamp}\n{body_sha256_hex(body)}".encode("utf-8")


def sign_request(secret: str, method: str, path: str, timestamp: str, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"), signing_string(method, path, timestamp, body), hashlib.sha256
    ).hexdigest()


def verify_request_signature(
    secret: str, method: str, path: str, timestamp: str, body: bytes, signature: str
) -> bool:
    expected = sign_request(secret, method, path, timestamp, body)
    return hmac.compare_digest(expected, signature.lower())


# --- join tickets ------------------------------------------------------------------------------

def ticket_payload(
    *, tid: str, mid: str, aid: str, sid: str, team: int, role: str, exp: int
) -> dict[str, Any]:
    # Insertion order is the canonical key order.
    return {"tid": tid, "mid": mid, "aid": aid, "sid": sid, "team": team, "role": role, "exp": exp}


def encode_ticket(secret: str, payload: dict[str, Any]) -> str:
    ordered = {k: payload[k] for k in TICKET_KEYS}
    payload_b64 = b64url_encode(
        json.dumps(ordered, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )
    mac = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return payload_b64 + "." + b64url_encode(mac)


def verify_ticket(
    secret: str,
    ticket: str,
    *,
    now_unix: int,
    expected_sid: str | None = None,
    expected_mid: str | None = None,
) -> dict[str, Any] | None:
    """Reference verifier (the game server does the same checks locally before redeeming).

    Returns the payload when the signature is valid, the ticket is unexpired and it is bound
    to ``expected_sid``/``expected_mid`` (when given); otherwise ``None``.
    """
    if not isinstance(ticket, str) or len(ticket) > MAX_TICKET_LEN or ticket.count(".") != 1:
        return None
    payload_b64, sig_b64 = ticket.split(".")
    try:
        sig = b64url_decode(sig_b64)
        raw = b64url_decode(payload_b64)
    except ValueError:
        return None
    expected = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or set(payload) != set(TICKET_KEYS):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or isinstance(exp, bool) or exp <= now_unix:
        return None
    if expected_sid is not None and payload.get("sid") != expected_sid:
        return None
    if expected_mid is not None and payload.get("mid") != expected_mid:
        return None
    return payload
