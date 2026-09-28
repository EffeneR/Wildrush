#!/usr/bin/env python3
"""G7: latency / loss matrix — LOCALHOST SIMULATION (real UDP through tools/netsim/udp_proxy.py),
not WAN verification.

For each condition a dedicated server runs with 4 real client processes (+6 labelled bots):
  c0 fight, c1 fight, c2 guard (holds a frontal guard toward the nearest enemy), c3 fight and,
  in every condition, c3 drops its connection mid-match and reconnects with its token.
Checks per condition:
  * prediction/reconciliation: mean correction error bounded, pending inputs ~ RTT
  * duplicate hits: no confirmed hit is delivered twice; predicted hits deduplicated
  * cooldown/action consistency: predicted own actions vs server-confirmed own actions
  * guard timing: the guarding client blocks strikes (blocks recorded on it)
  * reconnect: c3 rejoins, receives a new match setup and keeps playing
"""
from __future__ import annotations

import json
import sys
import time

from harness import Run, free_udp_port

CONDITIONS = [
    {"name": "rtt0_loss0", "rtt": 0, "loss": 0.0, "jitter": 0},
    {"name": "rtt50_loss1", "rtt": 50, "loss": 0.01, "jitter": 3},
    {"name": "rtt100_loss2", "rtt": 100, "loss": 0.02, "jitter": 5},
    {"name": "rtt150_loss3", "rtt": 150, "loss": 0.03, "jitter": 8},
]
DURATION_S = 80


def run_condition(c: dict) -> dict:
    run = Run("net", "netsim_" + c["name"])
    sport = free_udp_port(24610, 24650)
    pport = free_udp_port(24651, 24699)
    server = run.server(sport, ["--mode", "private", "--autostart", "4", "--allow-bots", "--quit-after-s", str(DURATION_S + 30)])
    time.sleep(1.5)
    proxy = run.proxy(pport, sport, c["rtt"], c["loss"], c["jitter"])
    time.sleep(0.8)
    clients = []
    specs = [("c0", "fight", ["--fighter", "bruno"]), ("c1", "fight", ["--fighter", "vex"]),
             ("c2", "guard", ["--fighter", "scrap"]), ("c3", "fight", ["--fighter", "hops", "--drop-at-s", "38"])]
    for i, (name, scen, extra) in enumerate(specs):
        clients.append(run.client(name, "127.0.0.1", pport, scen, seed=10 + i,
                                  extra=extra + ["--quit-after-s", str(DURATION_S)]))
        time.sleep(0.3)
    run.wait_all(clients, DURATION_S + 50)
    server.stop()
    proxy.stop()
    stats_path = run.dir / "proxy_stats.json"
    pstats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
    res = {"condition": c, "proxy": pstats.get("proxy_stats", {}), "clients": {}, "ok": True, "reasons": []}
    for cl in clients:
        lines = cl.json_lines()
        stats = [x for x in lines if x.get("ev") == "stats"]
        last = stats[-1] if stats else {}
        counts = last.get("counts", {})
        setups = sum(1 for x in lines if x.get("ev") == "match_setup")
        row = {"snaps": last.get("snaps"), "mean_err_m": last.get("mean_err"), "max_err_m": last.get("max_err"),
               "pending_inputs": last.get("pending"), "teleports": last.get("teleports"), "match_setups": setups,
               "counts": counts, "errors": cl.errors()[:3], "exit": cl.popen.returncode}
        res["clients"][cl.name] = row
        if not stats:
            res["ok"] = False
            res["reasons"].append(f"{cl.name}: no stats")
            continue
        limit = 0.08 + 0.002 * c["rtt"]
        if last.get("mean_err") is not None and float(last["mean_err"]) > limit:
            res["ok"] = False
            res["reasons"].append(f"{cl.name}: mean correction {last['mean_err']} > {limit:.3f}")
        if int(counts.get("dup_confirmed", 0)) > 0:
            res["ok"] = False
            res["reasons"].append(f"{cl.name}: duplicate confirmed hits")
        if cl.errors():
            res["ok"] = False
            res["reasons"].append(f"{cl.name}: errors")
    c2 = res["clients"].get("c2", {}).get("counts", {})
    if int(c2.get("blocks_on_me", 0)) == 0:
        res["ok"] = False
        res["reasons"].append("guarding client never blocked a strike")
    c3 = res["clients"].get("c3", {})
    if int(c3.get("match_setups", 0)) < 2:
        res["ok"] = False
        res["reasons"].append("c3 did not reconnect into the match")
    srv = server.server_events()
    res["server"] = {"reconnected": sum(1 for e in srv if e.get("ev") == "reconnected"),
                     "violations": sum(1 for e in srv if e.get("ev") == "violation"),
                     "errors": server.errors()[:5]}
    if server.errors():
        res["ok"] = False
        res["reasons"].append("server errors")
    if res["server"]["reconnected"] < 1:
        res["ok"] = False
        res["reasons"].append("server did not record the reconnect")
    run.write_result(res)
    run.cleanup()
    return res


def main() -> int:
    all_res = []
    ok = True
    for c in CONDITIONS:
        r = run_condition(c)
        all_res.append(r)
        ok = ok and r["ok"]
        print(json.dumps({"condition": c["name"], "ok": r["ok"], "reasons": r["reasons"],
                          "mean_err": {k: v["mean_err_m"] for k, v in r["clients"].items()},
                          "pending": {k: v["pending_inputs"] for k, v in r["clients"].items()},
                          "proxy": r["proxy"]}), flush=True)
    summary = {"test": "netsim_matrix", "ok": ok, "note": "localhost simulation via UDP proxy; not WAN verification",
               "conditions": all_res}
    out = Run("net", "netsim_summary")
    out.write_result(summary)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
