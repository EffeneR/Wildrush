#!/usr/bin/env python3
"""Stand-in for the exported Godot dedicated server (tests only; standard library only).

Invoked by the allocator exactly like the real binary (see allocator/agent.py). It checks
the fixed argument layout, records it to ``$DUMMY_REPORT_DIR/<match_id>.json`` and then
behaves according to ``$DUMMY_BEHAVIOR``:

* ``sleep`` (default): bind the UDP port and wait for SIGTERM (exit 0).
* ``ignore_term``: ignore SIGTERM (the allocator must SIGKILL it).
* ``exit``: exit immediately with ``$DUMMY_EXIT_CODE`` (default 3).
* ``play``: a miniature server-side protocol, useful as a Python reference for the real
  server: report ``/v1/matches/{id}/started``, accept UDP datagrams ``TICKET <ticket>``,
  verify each ticket locally (HMAC, sid, mid, exp), redeem it with the service, answer
  ``OK <account_id> <team>`` / ``ERR <reason>``, and once ``--expected-players`` tickets were
  redeemed submit a signed result and exit 0.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import signal
import socket
import sys
import time
import urllib.error
import urllib.request

FIGHTERS = ["nyx", "bruno", "vex", "hops", "scrap"]


def parse_args(argv: list[str]) -> dict[str, str]:
    expected_flags = [
        "--server", "--port", None, "--match-id", None, "--mode", None, "--service-url", None,
        "--server-id", None, "--secret-file", None, "--expected-players", None,
    ]
    if argv[:2] != ["--headless", "--"]:
        raise SystemExit(f"dummy: unexpected engine args {argv[:2]!r}")
    user = argv[2:]
    if len(user) != len(expected_flags):
        raise SystemExit(f"dummy: unexpected user args {user!r}")
    values: dict[str, str] = {}
    for i, flag in enumerate(expected_flags):
        if flag is None:
            values[expected_flags[i - 1].lstrip("-")] = user[i]
        elif user[i] != flag:
            raise SystemExit(f"dummy: expected {flag} at position {i}, got {user[i]!r}")
    return values


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def verify_ticket(secret: str, ticket: str, sid: str, mid: str) -> dict | None:
    try:
        payload_b64, sig_b64 = ticket.split(".")
        expected = hmac.new(secret.encode(), payload_b64.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, b64url_decode(sig_b64)):
            return None
        payload = json.loads(b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError):
        return None
    if payload.get("sid") != sid or payload.get("mid") != mid or int(payload.get("exp", 0)) <= time.time():
        return None
    return payload


class Service:
    def __init__(self, base_url: str, server_id: str, secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.server_id = server_id
        self.secret = secret
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method: str, path: str, payload: object | None) -> tuple[int, object]:
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        ts = str(int(time.time()))
        msg = f"{method}\n{path}\n{ts}\n{hashlib.sha256(body).hexdigest()}".encode()
        sig = hmac.new(self.secret.encode(), msg, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            self.base_url + path,
            data=body if payload is not None else None,
            method=method,
            headers={
                "X-WR-Server": self.server_id,
                "X-WR-Timestamp": ts,
                "X-WR-Signature": sig,
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"null")


def play(args: dict[str, str], secret: str, sock: socket.socket) -> int:
    svc = Service(args["service-url"], args["server-id"], secret)
    mid = args["match-id"]
    code, data = svc.call("POST", f"/v1/matches/{mid}/started", {})
    print(f"dummy: started -> {code} {data}", flush=True)
    if code != 200:
        return 5
    expected = int(args["expected-players"])
    redeemed: dict[str, int] = {}
    sock.settimeout(0.5)
    deadline = time.time() + float(os.environ.get("DUMMY_PLAY_TIMEOUT_S", "60"))
    while len(redeemed) < expected and time.time() < deadline:
        try:
            datagram, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        text = datagram.decode("ascii", "replace").strip()
        if not text.startswith("TICKET "):
            sock.sendto(b"ERR bad_request", addr)
            continue
        ticket = text[len("TICKET "):]
        payload = verify_ticket(secret, ticket, args["server-id"], mid)
        if payload is None:
            sock.sendto(b"ERR invalid_ticket", addr)
            continue
        code, data = svc.call("POST", "/v1/servers/tickets/redeem", {"ticket_id": payload["tid"], "match_id": mid})
        if code != 200 or not isinstance(data, dict):
            reason = data.get("error", {}).get("code", "error") if isinstance(data, dict) else "error"
            sock.sendto(f"ERR {reason}".encode(), addr)
            continue
        redeemed[data["account_id"]] = int(data["team"])
        sock.sendto(f"OK {data['account_id']} {data['team']}".encode(), addr)
    if len(redeemed) < expected:
        print("dummy: timed out waiting for players", flush=True)
        return 4
    players = []
    used = {0: 0, 1: 0}
    for account_id, team in sorted(redeemed.items()):
        team = team if team in (0, 1) else (0 if used[0] <= used[1] else 1)
        players.append({
            "account_id": account_id, "team": team, "fighter": FIGHTERS[used[team]],
            "kos": 3 + used[team], "knocked_out": 2, "damage_dealt": 1500.0, "control_seconds": 40.0,
            "abandoned": False, "afk": False,
        })
        used[team] += 1
    bots = []
    if args["mode"] == "casual":
        for team in (0, 1):
            for i in range(used[team], 5):
                bots.append({"team": team, "fighter": FIGHTERS[i]})
    result = {
        "match_id": mid, "winner_team": 0, "score": [250, 173], "duration_s": 402.5,
        "sudden_death": False, "ended_reason": "score_limit", "players": players, "bots": bots,
        "replay_id": None,
    }
    code, data = svc.call("POST", f"/v1/matches/{mid}/result", result)
    print(f"dummy: result -> {code} {json.dumps(data)}", flush=True)
    # Retransmit once (idempotency is exercised end-to-end as well).
    code2, data2 = svc.call("POST", f"/v1/matches/{mid}/result", result)
    print(f"dummy: result retransmit -> {code2} {json.dumps(data2)}", flush=True)
    return 0 if code == 200 and code2 == 200 else 6


def main() -> int:
    args = parse_args(sys.argv[1:])
    report_dir = os.environ.get("DUMMY_REPORT_DIR")
    if report_dir:
        with open(os.path.join(report_dir, f"{args['match-id']}.json"), "w", encoding="utf-8") as fh:
            json.dump({"argv": sys.argv, "pid": os.getpid(), "env_wr": sorted(k for k in os.environ if k.startswith("WR_"))}, fh)
    behavior = os.environ.get("DUMMY_BEHAVIOR", "sleep")
    print(f"dummy: match {args['match-id']} mode {args['mode']} port {args['port']} behavior {behavior}", flush=True)
    if behavior == "exit":
        return int(os.environ.get("DUMMY_EXIT_CODE", "3"))
    with open(args["secret-file"], encoding="utf-8") as fh:
        secret = fh.read().strip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", int(args["port"])))
    if behavior == "play":
        return play(args, secret, sock)
    stop = {"flag": False}
    if behavior == "ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))
    while not stop["flag"]:
        time.sleep(0.05)
    return 0


if __name__ == "__main__":
    sys.exit(main())
