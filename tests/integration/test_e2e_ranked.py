#!/usr/bin/env python3
"""G9: end-to-end online flow with TEN real client identities through the control service.

  account register/login -> ranked queue (solo, region "local") -> matchmaker forms a 10-human
  match -> allocator starts the EXPORTED Linux dedicated server -> 10 client processes (exported
  Linux client, headless autopilot) join with their HMAC tickets -> server redeems tickets,
  runs character select and a full regulation match -> server submits the signed result ->
  ratings, mastery and history are updated for all 10 accounts.

Everything runs locally on loopback (dev stack: PostgreSQL + service + allocator). This proves
the protocol and service flow end to end; it is not a WAN deployment test.
Requires: builds/linux_server + builds/linux_client (tools/verify_export.sh).
Evidence: evidence/e2e/ranked/ (result.json, service/allocator/server/client logs).
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVI = ROOT / "evidence" / "e2e" / "ranked"
BASE = "http://127.0.0.1:8080"
SERVER_BIN = ROOT / "builds" / "linux_server" / "wildrush_server.x86_64"
CLIENT_BIN = ROOT / "builds" / "linux_client" / "wildrush.x86_64"
FIGHTERS = ["nyx", "bruno", "vex", "hops", "scrap"]
MATCH_TIMEOUT_S = 16 * 60


def api(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict | list]:
    """HTTP call that honours the service's rate limits (429 + Retry-After) instead of bypassing them:
    all ten test identities share one loopback IP, and registration is limited to 5/min per IP."""
    for _ in range(6):
        code, d, retry = _api_once(method, path, token, body)
        if code != 429:
            return code, d
        time.sleep(min(90, max(1, retry)))
    return code, d


def _api_once(method: str, path: str, token: str | None, body: dict | None) -> tuple[int, dict | list, int]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {}), 0
    except urllib.error.HTTPError as e:
        raw = e.read()
        retry = int(e.headers.get("Retry-After", "60") or 60)
        try:
            return e.code, json.loads(raw), retry
        except json.JSONDecodeError:
            return e.code, {"raw": raw.decode(errors="replace")}, retry


def sh(*args: str, env: dict | None = None) -> int:
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.call(list(args), cwd=str(ROOT), env=e)


def main() -> int:
    shutil.rmtree(EVI, ignore_errors=True)   # one run's evidence only (older runs: git history)
    EVI.mkdir(parents=True, exist_ok=True)
    result: dict = {"test": "e2e_ranked", "ok": False, "reasons": [], "note": "loopback dev stack; not WAN"}
    for b in (SERVER_BIN, CLIENT_BIN):
        if not b.exists():
            result["reasons"].append(f"missing export {b} (run tools/verify_export.sh)")
            (EVI / "result.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
            return 1
    clients: list[subprocess.Popen] = []
    t0 = time.time()
    try:
        if sh("services/scripts/dev_up.sh") != 0:
            raise RuntimeError("dev_up failed")
        if sh("services/scripts/dev_allocator.sh", "start", env={"WR_SERVER_BINARY": str(SERVER_BIN)}) != 0:
            raise RuntimeError("allocator start failed")
        run = secrets.token_hex(2)
        accounts = []
        for i in range(10):
            user = f"e2e{run}p{i}"
            pw = secrets.token_urlsafe(12)
            code, d = api("POST", "/v1/auth/register", body={"username": user, "password": pw, "display_name": f"E2E Player {i}"})
            if code != 201:
                raise RuntimeError(f"register {user}: {code} {d}")
            code, d = api("POST", "/v1/auth/login", body={"username": user, "password": pw})
            if code != 200:
                raise RuntimeError(f"login {user}: {code} {d}")
            accounts.append({"user": user, "token": d["token"], "id": d["account"]["account_id"], "fighter": FIGHTERS[i % 5]})
        before = {}
        for a in accounts:
            code, me = api("GET", "/v1/me", a["token"])
            before[a["id"]] = me.get("rating", {})
        for a in accounts:
            code, d = api("POST", "/v1/queue", a["token"], {"mode": "ranked", "roster_prefs": [a["fighter"]], "region": "local",
                                                            "latency_ms": {"local": 5}, "allow_bots": False})
            if code != 202:
                raise RuntimeError(f"queue {a['user']}: {code} {d}")
        # poll until every account has a match assignment; launch each client as soon as its ticket appears
        launched: set[str] = set()
        match_id = ""
        deadline = time.time() + 120
        while len(launched) < 10 and time.time() < deadline:
            for a in accounts:
                if a["user"] in launched:
                    continue
                code, st = api("GET", "/v1/queue/status", a["token"])
                m = st.get("match") if isinstance(st, dict) else None
                if code == 200 and st.get("state") == "matched" and m and m.get("ticket"):
                    match_id = m["match_id"]
                    log = open(EVI / f"client_{a['user']}.log", "w")
                    args = [str(CLIENT_BIN), "--headless", "--", "--autopilot", "fight", "--connect", f"{m['host']}:{m['port']}",
                            "--ticket", m["ticket"], "--name", a["user"], "--fighter", a["fighter"],
                            "--log-json", str(EVI / f"client_{a['user']}.jsonl"), "--quit-after-s", str(MATCH_TIMEOUT_S)]
                    clients.append(subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, cwd="/tmp"))
                    launched.add(a["user"])
            time.sleep(0.5)
        result["match_id"] = match_id
        result["clients_launched"] = len(launched)
        if len(launched) < 10:
            raise RuntimeError(f"only {len(launched)} clients got tickets")
        # wait for the result to be applied (history row for the first account)
        deadline = time.time() + MATCH_TIMEOUT_S
        hist0: list = []
        while time.time() < deadline:
            code, hist0 = api("GET", "/v1/matches/history?limit=5", accounts[0]["token"])
            if code == 200 and any(h.get("match_id") == match_id for h in hist0):
                break
            if all(c.poll() is not None for c in clients):
                break
            time.sleep(5)
        code, full = api("GET", f"/v1/matches/{match_id}", accounts[0]["token"])
        result["match"] = {k: full.get(k) for k in ("mode", "state", "started_at", "ended_at")} if isinstance(full, dict) else full
        stored = full.get("result") if isinstance(full, dict) else None
        result["stored_result"] = {k: stored.get(k) for k in ("winner_team", "score", "duration_s", "ended_reason")} if stored else None
        rows = []
        ok_all = True
        for a in accounts:
            code, hist = api("GET", "/v1/matches/history?limit=5", a["token"])
            row = next((h for h in hist if isinstance(h, dict) and h.get("match_id") == match_id), None) if code == 200 else None
            code2, me = api("GET", "/v1/me", a["token"])
            rating = me.get("rating", {}) if code2 == 200 else {}
            rows.append({"user": a["user"], "history": row, "rating_before": before[a["id"]], "rating_after": rating})
            if row is None or row.get("rating_delta") is None or int(rating.get("games", 0)) != 1:
                ok_all = False
        result["accounts"] = rows
        if not stored:
            result["reasons"].append("no stored result for the match")
        if not ok_all:
            result["reasons"].append("not every account has a rated history row / games == 1")
        if isinstance(full, dict) and full.get("mode") != "ranked":
            result["reasons"].append("match mode is not ranked")
        result["ok"] = not result["reasons"]
    except Exception as e:  # noqa: BLE001 - report every failure in the evidence file
        result["reasons"].append(f"exception: {e}")
    finally:
        for c in clients:
            if c.poll() is None:
                c.terminate()
        for c in clients:
            try:
                c.wait(10)
            except subprocess.TimeoutExpired:
                c.kill()
        # keep the service-side logs as evidence
        for src, dst in ((ROOT / ".run" / "service.log", "service.log"), (ROOT / ".run" / "allocator" / "allocator.log", "allocator.log")):
            if src.exists():
                shutil.copy(src, EVI / dst)
        mlog = ROOT / ".run" / "allocator" / "match-logs" / f"{result.get('match_id', '')}.log"
        if result.get("match_id") and mlog.exists():
            shutil.copy(mlog, EVI / "server.log")
        sh("services/scripts/dev_allocator.sh", "stop")
        sh("services/scripts/dev_down.sh")
    result["wall_s"] = round(time.time() - t0, 1)
    (EVI / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({k: result[k] for k in ("ok", "reasons", "match_id", "wall_s") if k in result}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
