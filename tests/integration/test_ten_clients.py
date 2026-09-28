#!/usr/bin/env python3
"""G6: real dedicated server + TEN separate client processes (protocol test, not bots-in-process).

Private direct-connect server with autostart after 10 humans, no bots. Every client is its own
Godot process with its own ENet connection and identity, driven by a seeded autopilot script.
Pass criteria: all 10 authenticate, receive match setup and a steady snapshot stream, the server
reports 10 human fighters and 0 bots, gameplay hits occur, prediction error stays small, and no
script errors are logged.
"""
from __future__ import annotations

import json
import sys
import time

from harness import Run, free_udp_port

DURATION_S = 150


def main() -> int:
    run = Run("net", "ten_clients")
    port = free_udp_port()
    t0 = time.time()
    server = run.server(port, ["--mode", "private", "--autostart", "10", "--quit-after-s", str(DURATION_S + 40)])
    time.sleep(2.0)
    prefs = ["nyx", "bruno", "vex", "hops", "scrap"]
    clients = []
    for i in range(10):
        clients.append(run.client(f"c{i:02d}", "127.0.0.1", port, "fight", seed=100 + i,
                                  extra=["--fighter", prefs[i % 5], "--quit-after-s", str(DURATION_S)]))
        time.sleep(0.3)
    run.wait_all(clients, DURATION_S + 60)
    server.stop()
    sev = server.server_events()
    joined = [e for e in sev if e.get("ev") == "joined"]
    starts = [e for e in sev if e.get("ev") == "match_start"]
    violations = [e for e in sev if e.get("ev") == "violation"]
    per_client = {}
    ok = True
    reasons = []
    total_in = 0
    for c in clients:
        lines = c.json_lines()
        welcome = any(x.get("ev") == "welcome" for x in lines)
        setup = any(x.get("ev") == "match_setup" for x in lines)
        stats = [x for x in lines if x.get("ev") == "stats"]
        last = stats[-1] if stats else {}
        hits = [x for x in lines if x.get("ev") == "game" and x.get("type") == "hit"]
        errs = c.errors()
        per_client[c.name] = {"welcome": welcome, "match_setup": setup, "snapshots": last.get("snaps", 0),
                              "late_snaps": last.get("late", 0), "mean_pred_err_m": last.get("mean_err"),
                              "max_pred_err_m": last.get("max_err"), "in_bytes": last.get("in_bytes"),
                              "out_bytes": last.get("out_bytes"), "hits_seen": len(hits), "errors": errs[:5],
                              "exit": c.popen.returncode}
        total_in += int(last.get("in_bytes", 0) or 0)
        if not (welcome and setup):
            ok = False
            reasons.append(f"{c.name} did not join the match")
        if int(last.get("snaps", 0) or 0) < 1000:
            ok = False
            reasons.append(f"{c.name} received too few snapshots ({last.get('snaps')})")
        if last.get("mean_err") is not None and float(last["mean_err"]) > 0.25:
            ok = False
            reasons.append(f"{c.name} mean prediction error too high ({last['mean_err']})")
        if errs:
            ok = False
            reasons.append(f"{c.name} logged errors")
    if len(joined) < 10:
        ok = False
        reasons.append(f"server saw {len(joined)} joins")
    if not starts or starts[0].get("fighters") != 10 or starts[0].get("bots") != 0:
        ok = False
        reasons.append(f"match_start not 10 humans / 0 bots: {starts}")
    all_hits = sum(v["hits_seen"] for v in per_client.values())
    if all_hits < 5:
        ok = False
        reasons.append("no combat observed")
    srv_errs = server.errors()
    if srv_errs:
        ok = False
        reasons.append("server logged errors")
    result = {"test": "ten_clients", "ok": ok, "reasons": reasons, "duration_s": round(time.time() - t0, 1),
              "server_joins": len(joined), "match_start": starts[:1], "violations": len(violations),
              "clients": per_client, "avg_client_down_kbps": round(total_in * 8 / 1000 / 10 / DURATION_S, 1),
              "server_errors": srv_errs[:10], "network": "localhost (no netsim)"}
    path = run.write_result(result)
    print(json.dumps({"ok": ok, "reasons": reasons, "result": str(path)}, indent=1))
    run.cleanup()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
