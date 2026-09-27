#!/usr/bin/env python3
"""Build every WILDRUSH audio asset listed in docs/AUDIO_CONTRACT.md plus audio_manifest.json.

Usage:  build.py [--only cue1,cue2] [--group sfx|ui|amb|music] [--no-manifest]

Deterministic: all randomness is seeded from the cue name + variation index, and Ogg streams get
a fixed serial number, so re-running produces byte-identical files. Never touches
game/assets/audio/default_bus_layout.tres (owned by the lead).
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import contract  # noqa: E402
import cue_table  # noqa: E402
from dsp import (SR, a2db, db2a, fade_edges, gated_rms_db, hp, limiter, ns, rng_for, seam_stats, sos,  # noqa: E402
                 sos_circular, write_ogg, write_wav16)

ROOT = HERE.parents[1]
OUT = ROOT / "game" / "assets" / "audio"
MANIFEST = OUT / "audio_manifest.json"
OWNED_DIRS = ("sfx", "ui", "amb", "music")
GROUP_MODULE = {"sfx": "sfx", "ui": "ui_sounds", "amb": "ambience", "music": "music"}
OGG_QUALITY = {"amb": 0.55, "music": 0.5}  # soundfile compression_level (lower = higher quality)
MAX_DUR = {"victory": 3.8, "defeat": 3.8, "sudden_death": 3.8}  # contract: stings 2-4 s


def finalize_oneshot(x: np.ndarray, cue: str) -> tuple[np.ndarray, dict]:
    """DC/subsonic removal, trim, 2 ms fade-in + short fade-out, loudness to the category target
    with a zero-overshoot limiter keeping the sample peak <= SFX_CEILING_DBFS."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError(f"{cue}: one-shots must be mono")
    if not np.all(np.isfinite(x)) or np.max(np.abs(x)) <= 0:
        raise ValueError(f"{cue}: generator returned silent/non-finite audio")
    x = hp(x, 25.0, 2)
    if cue in MAX_DUR and x.size > ns(MAX_DUR[cue]):
        x = fade_edges(x[: ns(MAX_DUR[cue])], 0.0, 0.35)
    # If the buffer ends while the sound is still ringing, give it a natural release instead of
    # a hard stop (raised-cosine over the last 30 %, max 300 ms).
    tail_db = float(a2db(np.sqrt(np.mean(x[-ns(0.02):] ** 2)) / np.max(np.abs(x))))
    if tail_db > -45.0:
        m = min(ns(0.3), int(0.3 * x.size))
        x = x.copy()
        x[-m:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(1, m + 1) / m)
    thr = np.max(np.abs(x)) * db2a(-60.0)
    above = np.nonzero(np.abs(x) > thr)[0]
    x = x[above[0]: above[-1] + 1]
    x = fade_edges(x, 0.002, min(0.02, 0.1 * x.size / SR))
    target = cue_table.target_db(cue)
    block, hop, gate = cue_table.measure_params(cue)
    ceiling = float(db2a(cue_table.SFX_CEILING_DBFS))
    lim_db = 0.0
    for _ in range(10):
        x = x * db2a(target - gated_rms_db(x, block, hop, gate))
        pk = float(np.max(np.abs(x)))
        lim_db = max(0.0, float(a2db(pk) - a2db(ceiling)))
        if pk > ceiling:
            x = limiter(x, ceiling, win_ms=1.5)
        if abs(gated_rms_db(x, block, hop, gate) - target) < 0.1:
            break
    return x, {"rms": gated_rms_db(x, block, hop, gate), "target": target, "peak": float(a2db(np.max(np.abs(x)))),
               "limited_db": lim_db, "dur": x.size / SR, "tail_db": tail_db}


def finalize_loop(x: np.ndarray, cue: str) -> tuple[np.ndarray, dict]:
    """Circular DC removal and loudness normalisation for a periodic (2, n) signal."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] != 2:
        raise ValueError(f"{cue}: loops must be stereo (2, n)")
    if not np.all(np.isfinite(x)):
        raise ValueError(f"{cue}: non-finite samples")
    x = sos_circular(sos("highpass", 22.0, 2), x)
    target = cue_table.target_db(cue)
    block, hop, gate = cue_table.measure_params(cue)
    ceiling = float(db2a(cue_table.LOOP_CEILING_DBFS))
    lim_db = 0.0
    for _ in range(10):
        x = x * db2a(target - gated_rms_db(x, block, hop, gate))
        pk = float(np.max(np.abs(x)))
        lim_db = max(0.0, float(a2db(pk) - a2db(ceiling)))
        if pk > ceiling:
            x = limiter(x, ceiling, win_ms=3.0, circular=True)
        if abs(gated_rms_db(x, block, hop, gate) - target) < 0.1:
            break
    return x, {"rms": gated_rms_db(x, block, hop, gate), "target": target, "limited_db": lim_db,
               "dur": x.shape[1] / SR}


def encode_loop(path: Path, x: np.ndarray, quality: float, title: str) -> dict:
    """Encode to Vorbis, decode, and back the gain off if codec overshoot exceeds -1.1 dBFS."""
    for attempt in range(5):
        write_ogg(path, x, quality, title=title)
        y, sr = sf.read(str(path), always_2d=True)
        if sr != SR or y.shape[0] != x.shape[1]:
            raise RuntimeError(f"{path}: decoded length/rate mismatch ({y.shape[0]} vs {x.shape[1]})")
        pk = float(a2db(np.max(np.abs(y))))
        if pk <= -1.1:
            return {"decoded_peak": pk, "attempts": attempt + 1, "seam": seam_stats(y.T)}
        x = x * db2a(-1.1 - pk - 0.15)
    raise RuntimeError(f"{path}: could not keep decoded peak under -1.1 dBFS")


def load_generators(groups):
    regs = {}
    for g in groups:
        mod = importlib.import_module(GROUP_MODULE[g])
        regs.update({k: (g, fn) for k, fn in mod.REGISTRY.items()})
    return regs


def write_manifest(spec: dict) -> None:
    cues = {cue: cue_table.manifest_entry(cue, info["files"]) for cue, info in spec.items()}
    MANIFEST.write_text(json.dumps({"cues": cues}, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {MANIFEST.relative_to(ROOT)} ({len(cues)} cues, "
          f"{sum(len(c['files']) for c in cues.values())} files)")


def clean_stale(spec: dict) -> None:
    expected = {f for info in spec.values() for f in info["files"]}
    for d in OWNED_DIRS:
        for p in sorted((OUT / d).glob("*")):
            rel = f"{d}/{p.name}"
            if p.suffix in (".wav", ".ogg") and rel not in expected:
                print(f"removing stale {rel}")
                p.unlink()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated cue ids")
    ap.add_argument("--group", default="", help="comma-separated groups: sfx,ui,amb,music")
    ap.add_argument("--no-manifest", action="store_true")
    args = ap.parse_args(argv)

    spec = contract.parse_contract()
    missing_meta = sorted(set(spec) - set(cue_table.CUES))
    if missing_meta:
        print(f"ERROR: cues without cue_table metadata: {missing_meta}")
        return 2
    groups = [g for g in (args.group.split(",") if args.group else OWNED_DIRS) if g]
    only = {c for c in args.only.split(",") if c}
    regs = load_generators(sorted({spec[c]["files"][0].split("/")[0] for c in spec}) if not args.group else groups)

    for d in OWNED_DIRS:
        (OUT / d).mkdir(parents=True, exist_ok=True)
    if not only and not args.group:
        clean_stale(spec)

    failures = 0
    t_all = time.time()
    for cue, info in spec.items():
        folder = info["files"][0].split("/")[0]
        if folder not in groups or (only and cue not in only):
            continue
        if cue not in regs:
            print(f"ERROR: no generator for cue {cue}")
            failures += 1
            continue
        _, fn = regs[cue]
        for v, rel in enumerate(info["files"]):
            t0 = time.time()
            path = OUT / rel
            try:
                x = fn(v, rng_for(folder, cue, v))
                if folder in ("amb", "music"):
                    y, st = finalize_loop(x, cue)
                    enc = encode_loop(path, y, OGG_QUALITY[folder], title=cue)
                    print(f"{rel:34s} dur={st['dur']:7.3f}s rms={st['rms']:6.2f} (tgt {st['target']:6.1f}) "
                          f"decoded_peak={enc['decoded_peak']:6.2f} lim={st['limited_db']:4.1f}dB "
                          f"seam_jump={enc['seam']['jump']:.4f} (p99.9 {enc['seam']['p999']:.4f}) "
                          f"size={path.stat().st_size / 1e6:.2f}MB  [{time.time() - t0:.1f}s]")
                else:
                    y, st = finalize_oneshot(x, cue)
                    write_wav16(path, y)
                    warn = "  WARN heavy limiting" if st["limited_db"] > 6.0 else ""
                    warn += "  (release fade)" if st["tail_db"] > -45.0 else ""
                    print(f"{rel:34s} dur={st['dur']:6.3f}s rms={st['rms']:6.2f} (tgt {st['target']:6.1f}) "
                          f"peak={st['peak']:6.2f} lim={st['limited_db']:4.1f}dB tail={st['tail_db']:6.1f}dB "
                          f"[{time.time() - t0:.2f}s]{warn}")
            except Exception as exc:  # report and continue, fail at the end
                failures += 1
                print(f"ERROR {rel}: {type(exc).__name__}: {exc}")
                import traceback
                traceback.print_exc()
    if not args.no_manifest:
        write_manifest(spec)
    print(f"build finished in {time.time() - t_all:.1f}s with {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
