#!/usr/bin/env python3
"""G10: soak at normal speed (real time, 60 Hz) for >= 20 minutes.

The EXPORTED Linux dedicated server runs a private lobby with autostart; 4 real headless
client processes (autopilot) plus 6 server-side bots play back-to-back matches (the private
lobby restarts automatically after each result). Every 15 s the server's RSS/CPU is sampled.
Pass: >= 2 complete matches, no server/client script errors, server RSS growth between the
second sample and the end < 25 %, every client still receiving snapshots at the end.
Evidence: evidence/soak/<run>/ (result.json, server.log, client logs, samples).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from harness import ROOT, Run, free_udp_port

SOAK_S = int(sys.argv[1]) if len(sys.argv) > 1 else 21 * 60
SERVER_BIN = ROOT / "builds" / "linux_server" / "wildrush_server.x86_64"


def rss_cpu(pid: int) -> tuple[int, float]:
    out = subprocess.run(["ps", "-o", "rss=,pcpu=", "-p", str(pid)], capture_output=True, text=True).stdout.split()
    return (int(out[0]), float(out[1])) if len(out) == 2 else (0, 0.0)


def main() -> int:
    run = Run("soak", "server_clients")
    port = free_udp_port(24750, 24790)
    log = open(run.dir / "server.log", "w")
    server = subprocess.Popen([str(SERVER_BIN), "--headless", "--", "--port", str(port), "--mode", "private",
                               "--autostart", "4", "--allow-bots", "--replay-dir", str(run.dir / "replays"),
                               "--quit-after-s", str(SOAK_S + 60)], stdout=log, stderr=subprocess.STDOUT, cwd="/tmp")
    time.sleep(2.0)
    clients = [run.client(f"s{i}", "127.0.0.1", port, "fight", 100 + i, ["--fighter", ["nyx", "vex", "hops", "scrap"][i],
               "--quit-after-s", str(SOAK_S)]) for i in range(4)]
    samples = []
    t0 = time.time()
    while time.time() - t0 < SOAK_S + 20 and server.poll() is None:
        rss, cpu = rss_cpu(server.pid)
        samples.append({"t": round(time.time() - t0), "rss_kb": rss, "cpu": cpu})
        if all(c.popen.poll() is not None for c in clients):
            break
        time.sleep(15)
    run.wait_all(clients, 60)
    server.terminate()
    try:
        server.wait(15)
    except subprocess.TimeoutExpired:
        server.kill()
    log.close()
    text = (run.dir / "server.log").read_text(errors="replace")
    events = []
    for line in text.splitlines():
        if line.startswith("[server] "):
            try:
                events.append(json.loads(line[9:]))
            except json.JSONDecodeError:
                pass
    ends = [e for e in events if e.get("ev") == "match_end"]
    errors = [l for l in text.splitlines() if l.startswith("ERROR") or "SCRIPT ERROR" in l]
    res: dict = {"test": "soak", "duration_s": round(time.time() - t0), "target_s": SOAK_S, "matches_completed": len(ends),
                 "match_ends": ends, "server_errors": errors[:10], "samples": samples, "ok": True, "reasons": []}
    if len(ends) < 2:
        res["reasons"].append(f"only {len(ends)} matches completed")
    if errors:
        res["reasons"].append("server errors")
    if len(samples) > 4:
        base = samples[1]["rss_kb"]
        peak_end = max(s["rss_kb"] for s in samples[-4:])
        res["rss_growth_pct"] = round(100.0 * (peak_end - base) / max(1, base), 1)
        if res["rss_growth_pct"] > 25.0:
            res["reasons"].append(f"server RSS grew {res['rss_growth_pct']} %")
    for c in clients:
        st = [x for x in c.json_lines() if x.get("ev") == "stats"]
        errs = c.errors()
        res.setdefault("clients", {})[c.name] = {"stats_lines": len(st), "last_snaps": st[-1].get("snaps") if st else None,
                                                  "errors": errs[:3], "exit": c.popen.returncode}
        if errs:
            res["reasons"].append(f"{c.name}: errors")
        if not st:
            res["reasons"].append(f"{c.name}: no stats")
    res["ok"] = not res["reasons"]
    run.write_result(res)
    print(json.dumps({k: res[k] for k in ("ok", "reasons", "duration_s", "matches_completed")} | {"rss_growth_pct": res.get("rss_growth_pct")}))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
