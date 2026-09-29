#!/usr/bin/env python3
"""G8 (game-server level): security negatives against a REAL dedicated server process.

Private server with a join password and an observer key. Real client processes:
  ok1, ok2   legitimate players (password)                          -> accepted, play normally
  probe      legitimate player that then sends forged/malformed traffic (test_client --probe
             security): forged damage + score messages, ownership field on pick, garbage,
             oversize, too many input frames, NaN/out-of-range inputs, 200-packet flood
             -> every forged message rejected (violations logged), abuser kicked, match unaffected
  badpw      wrong password                                         -> rejected (bad_password)
  obs_bad    observer with a wrong key                              -> rejected (observer_not_authorized)
  obs_ok     observer with the right key                            -> accepted as observer (no fighter)
  ticket     forged join ticket                                     -> rejected before any service call
Service-side negatives (signatures, timestamp window, result replay/conflict, ticket reuse,
player vs server endpoints) are covered by services/tests (evidence/services/pytest_latest.txt).
"""
from __future__ import annotations

import json
import sys
import time

from harness import Run, free_udp_port


def main() -> int:
    run = Run("security", "game_server")
    port = free_udp_port(24700, 24740)
    pw_file = run.dir / "pw.txt"
    pw_file.write_text("letmein-7731\n")
    server = run.server(port, ["--mode", "private", "--autostart", "3", "--allow-bots", "--observer-key", "obs-key-5519",
                               "--private-password-file", str(pw_file), "--quit-after-s", "95"])
    time.sleep(1.5)
    pw = ["--password", "letmein-7731"]
    ok1 = run.client("ok1", "127.0.0.1", port, "fight", 1, pw + ["--fighter", "nyx", "--quit-after-s", "70"])
    ok2 = run.client("ok2", "127.0.0.1", port, "fight", 2, pw + ["--fighter", "bruno", "--quit-after-s", "70"])
    probe = run.client("probe", "127.0.0.1", port, "fight", 3, pw + ["--fighter", "vex", "--probe", "security", "--quit-after-s", "70"])
    time.sleep(4.0)
    badpw = run.client("badpw", "127.0.0.1", port, "idle", 4, ["--password", "wrong", "--quit-after-s", "20"])
    obs_bad = run.client("obs_bad", "127.0.0.1", port, "idle", 5, pw + ["--observer", "--observer-key", "nope", "--quit-after-s", "20"])
    obs_ok = run.client("obs_ok", "127.0.0.1", port, "idle", 6, pw + ["--observer", "--observer-key", "obs-key-5519", "--quit-after-s", "40"])
    forged = "eyJ0aWQiOiJ4IiwibWlkIjoieCIsImFpZCI6IngiLCJzaWQiOiJ4IiwidGVhbSI6MCwicm9sZSI6InBsYXllciIsImV4cCI6OTk5OTk5OTk5OX0.AAAA"
    ticket = run.client("ticket", "127.0.0.1", port, "idle", 7, ["--ticket", forged, "--quit-after-s", "20"])
    run.wait_all([ok1, ok2, probe, badpw, obs_bad, obs_ok, ticket], 110)
    server.stop()
    sev = server.server_events()
    res: dict = {"test": "security_game_server", "ok": True, "reasons": [], "checks": {}}

    def check(name: str, cond: bool, detail: object = None) -> None:
        res["checks"][name] = {"pass": bool(cond), "detail": detail}
        if not cond:
            res["ok"] = False
            res["reasons"].append(name)

    rejects = [e for e in sev if e.get("ev") == "auth_reject"]
    reasons = sorted({str(e.get("reason")) for e in rejects})
    check("wrong_password_rejected", "password" in reasons, reasons)
    check("unauthorized_observer_rejected", "observer" in reasons, reasons)
    check("forged_ticket_rejected", any(r not in ("password", "observer", "version") for r in reasons), reasons)
    joined = [e for e in sev if e.get("ev") == "joined"]
    check("legit_players_joined", sum(1 for e in joined if not e.get("observer")) >= 3, len(joined))
    check("authorized_observer_joined", any(e.get("observer") for e in joined))
    viol = [e for e in sev if e.get("ev") == "violation"]
    kinds = sorted({str(e.get("kind")) for e in viol})
    check("forged_messages_flagged", "bad_msg" in kinds, kinds)
    check("flood_rate_limited", any(k.startswith("rate") for k in kinds), kinds)
    check("abuser_kicked", any(e.get("ev") == "kick_abuse" for e in sev))
    starts = [e for e in sev if e.get("ev") == "match_start"]
    check("match_started", bool(starts))
    ends = [e for e in sev if e.get("ev") == "match_end"]
    # a forged {"t":"score","points":250} would have ended the match instantly
    check("forged_score_had_no_effect", not any(250 in (e.get("score") or []) for e in ends), ends[:1])
    ok_stats = [x for x in ok1.json_lines() if x.get("ev") == "stats"]
    check("honest_client_kept_playing", len(ok_stats) >= 5 and int(ok_stats[-1].get("snaps", 0)) > 400,
          ok_stats[-1].get("snaps") if ok_stats else None)
    for name, proc in (("badpw", badpw), ("obs_bad", obs_bad), ("ticket", ticket)):
        st = [x for x in proc.json_lines() if x.get("ev") == "status" and x.get("status") == "failed"]
        check(f"{name}_saw_rejection", bool(st), st[:1])
    check("no_server_script_errors", not server.errors(), server.errors()[:5])
    run.write_result(res)
    run.cleanup()
    print(json.dumps({"ok": res["ok"], "reasons": res["reasons"]}))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
