#!/usr/bin/env python3
"""Summarise match frame-time logs (match_scene --perf-log JSON lines, one row per 60 frames)
into evidence/perf/summary.json. Numbers are whatever the machine measured — on this
container that is Mesa llvmpipe (CPU rasteriser), NOT a GPU; they are recorded as such."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERF = ROOT / "evidence" / "perf"


def summarise(path: Path, skip_s: float = 15.0) -> dict:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if float(r.get("t", 0)) >= skip_s] or rows   # skip loading/countdown
    if not rows:
        return {"file": path.name, "rows": 0}
    fps = [float(r["fps"]) for r in rows]
    return {"file": path.name, "rows": len(rows), "fps_mean": round(statistics.mean(fps), 1),
            "fps_min_window": round(min(fps), 1), "frame_ms_p50_median": round(statistics.median(float(r["p50_ms"]) for r in rows), 2),
            "frame_ms_p99_max": round(max(float(r["p99_ms"]) for r in rows), 2),
            "physics_ms_median": round(statistics.median(float(r["physics_ms"]) for r in rows), 2),
            "draw_calls_median": int(statistics.median(float(r["draw_calls"]) for r in rows)),
            "primitives_median": int(statistics.median(float(r["prims"]) for r in rows)),
            "static_mem_mb_max": max(float(r["mem_mb"]) for r in rows)}


def main() -> int:
    files = sorted(PERF.glob("*.jsonl"))
    out = {"renderer_note": "Mesa llvmpipe/lavapipe software rendering under Xvfb, 4 CPU threads shared with other "
                            "processes; not representative of GPU hardware. 10 fighters (1 local + 9 bots), 1600x900.",
           "runs": [summarise(f) for f in files]}
    (PERF / "summary.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if files else 1


if __name__ == "__main__":
    sys.exit(main())
