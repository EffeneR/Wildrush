#!/usr/bin/env python3
"""Validate game/assets/audio against docs/AUDIO_CONTRACT.md.

Checks (each result is PASS / FAIL / WARN; any FAIL -> exit code 1):
  contract   every contract file exists (file list parsed from the contract table itself)
  format     WAV = 44.1 kHz 16-bit PCM mono; OGG = 44.1 kHz Vorbis stereo
  peak       sample peak <= -1 dBFS (4x-oversampled true peak reported as info)
  loudness   gated "loud part" RMS within +/-4 dB of the category target (impact -14, swing -20,
             footstep -24, ui -20, ambience -28, music -22 dBFS)
  shape      one-shots: start/end at zero (fades), trimmed (<= 10 ms lead-in, <= 30 ms tail
             below -60 dB), no DC offset; no isolated clicks (HF spike detector)
  duration   loops/stings inside the contract's duration window
  seam       loops: the step across the loop point is no larger than the steps in its own
             +/-50 ms neighbourhood, no HF click at the seam, level continuity across the seam
  variation  variations of a cue are audibly different (max normalised cross-correlation < 0.95)
  essential  essential cues are mutually distinct (spectral profile / centroid / duration)
  manifest   schema, every contract cue + file listed, every file on disk listed, bus/loop/
             positional/priority consistency (essential cues priority 5)
  size       total audio size < 60 MB
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import contract  # noqa: E402
import cue_table  # noqa: E402
from dsp import SR, a2db, gated_rms_db  # noqa: E402

ROOT = HERE.parents[1]
AUDIO = ROOT / "game" / "assets" / "audio"
MANIFEST = AUDIO / "audio_manifest.json"
EVID = ROOT / "evidence" / "audio"
SIZE_LIMIT_MB = 60.0
BUSES = {"sfx": "SFX", "ui": "UI", "amb": "Ambience", "music": "Music"}
MANIFEST_KEYS = {"files": list, "bus": str, "volume_db": (int, float), "pitch_rand": (int, float),
                 "max_voices": int, "positional": bool, "priority": int, "loop": bool}


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, check, subject, detail=""):
        self.rows.append({"status": status, "check": check, "subject": subject, "detail": detail})

    def ok(self, cond, check, subject, detail="", warn_only=False):
        self.add("PASS" if cond else ("WARN" if warn_only else "FAIL"), check, subject, detail)
        return cond

    def counts(self):
        c = {"PASS": 0, "FAIL": 0, "WARN": 0}
        for r in self.rows:
            c[r["status"]] += 1
        return c


# --------------------------------------------------------------------------- signal helpers
def hf_click_frames(x, skip_s=0.04):
    """Indices (1 ms frames) of isolated high-frequency spikes: > +18 dB over the local median
    that collapse again in the next frame (a click, not a decaying transient)."""
    h = ss.sosfilt(ss.butter(4, 7000, "highpass", fs=SR, output="sos"), x)
    fr = int(0.001 * SR)
    m = h.size // fr
    if m < 3:
        return []
    e = 10 * np.log10(np.mean(h[: m * fr].reshape(m, fr) ** 2, axis=1) + 1e-14)
    loc = np.array([np.median(e[max(0, i - 20): i + 20]) for i in range(m)])
    start = int(skip_s * SR / fr)
    return [int(round(i * fr / SR * 1000)) for i in range(start, m - 1)
            if e[i] - loc[i] > 18 and e[i] > -70 and e[i + 1] - loc[i] < 12]


def seam_check(x):
    """x: (n, ch). Returns dict with the seam step vs its neighbourhood, seam HF spike, level delta."""
    out = {"jump": 0.0, "local_max": 0.0, "hf_excess_db": -99.0, "hf_click": False, "level_delta_db": 0.0}
    w = int(0.05 * SR)
    for c in range(x.shape[1]):
        ch = x[:, c]
        ring = np.concatenate([ch[-w:], ch[:w]])  # seam between index w-1 and w
        d = np.abs(np.diff(ring))
        seam = d[w - 1]
        local = np.delete(d, w - 1).max()
        out["jump"] = max(out["jump"], float(seam))
        out["local_max"] = max(out["local_max"], float(local))
        # HF energy in 1 ms frames around the seam (circular context)
        ctx = np.concatenate([ch[-4 * w:], ch[: 4 * w]])
        h = ss.sosfilt(ss.butter(4, 7000, "highpass", fs=SR, output="sos"), ctx)
        fr = int(0.001 * SR)
        m = h.size // fr
        e = 10 * np.log10(np.mean(h[: m * fr].reshape(m, fr) ** 2, axis=1) + 1e-14)
        k = (4 * w) // fr
        med = float(np.median(e[max(0, k - 40): k + 40]))
        for kk in (k - 1, k):  # the frames touching the loop point
            exc = float(e[kk] - med)
            out["hf_excess_db"] = max(out["hf_excess_db"], exc)
            # a click is an isolated spike that collapses in the next frame (an onset keeps ringing)
            if exc > 18 and e[kk + 1] - med < 12:
                out["hf_click"] = True
    r = int(0.25 * SR)
    lvl = lambda seg: 10 * np.log10(np.mean(seg ** 2) + 1e-20)
    out["level_delta_db"] = float(abs(lvl(x[-r:]) - lvl(x[:r])))
    return out


def max_xcorr(a, b):
    n = a.size + b.size
    nfft = 1 << (n - 1).bit_length()
    A = np.fft.rfft(a, nfft)
    B = np.fft.rfft(b, nfft)
    xc = np.fft.irfft(A * np.conj(B), nfft)
    return float(np.max(np.abs(xc)) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


OCT = [(45, 90), (90, 180), (180, 355), (355, 710), (710, 1400), (1400, 2800), (2800, 5600), (5600, 11200),
       (11200, 20000)]


def features(x):
    f, P = ss.welch(x, SR, nperseg=min(4096, max(256, x.size)))
    tot = P.sum() + 1e-20
    prof = np.array([10 * np.log10(P[(f >= a) & (f < b)].sum() / tot + 1e-9) for a, b in OCT])
    centroid = float((f * P).sum() / tot)
    env = np.sqrt(np.convolve(x ** 2, np.ones(441) / 441, mode="same"))
    pk = env.max()
    above = np.nonzero(env > pk * 10 ** (-30 / 20))[0]
    dur = (above[-1] - above[0]) / SR if above.size else 0.0
    return prof, centroid, dur


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(EVID / "check_audio.txt"))
    ap.add_argument("--json", default=str(EVID / "check_audio.json"))
    args = ap.parse_args(argv)
    R = Report()
    spec = contract.parse_contract()
    info_lines = []

    # ---------------------------------------------------------------- per-file checks
    data = {}
    for cue, cinfo in spec.items():
        meta = cue_table.CUES.get(cue)
        if not R.ok(meta is not None, "cue_table", cue, "loudness category defined"):
            continue
        cat = meta["category"]
        target = cue_table.LOUDNESS[cat][0]
        block, hop, gate = cue_table.LOUDNESS[cat][1:]
        for rel in cinfo["files"]:
            p = AUDIO / rel
            if not R.ok(p.exists(), "contract", rel, "file exists"):
                continue
            inf = sf.info(str(p))
            x, sr = sf.read(str(p), always_2d=True)
            data[rel] = x
            is_ogg = rel.endswith(".ogg")
            want = ("OGG", "VORBIS", 2) if is_ogg else ("WAV", "PCM_16", 1)
            got = (inf.format, inf.subtype, inf.channels)
            R.ok(sr == SR and got == want, "format", rel,
                 f"{inf.format}/{inf.subtype} {inf.samplerate} Hz {inf.channels} ch (want {want[0]}/{want[1]} 44100 Hz {want[2]} ch)")
            if not np.all(np.isfinite(x)) or np.max(np.abs(x)) == 0:
                R.add("FAIL", "signal", rel, "silent or non-finite")
                continue
            pk = float(a2db(np.max(np.abs(x))))
            tp = float(a2db(np.max(np.abs(ss.resample_poly(x, 4, 1, axis=0)))))
            R.ok(pk <= cue_table.PEAK_LIMIT_DBFS, "peak", rel, f"sample peak {pk:.2f} dBFS (true peak {tp:.2f})")
            sig = x.T if x.shape[1] > 1 else x[:, 0]
            rms = gated_rms_db(sig, block, hop, gate)
            R.ok(abs(rms - target) <= cue_table.RMS_TOLERANCE_DB, "loudness", rel,
                 f"{cat}: loud-part RMS {rms:.2f} dBFS vs target {target:.0f} +/-{cue_table.RMS_TOLERANCE_DB:.0f}")
            dur = x.shape[0] / SR
            if cinfo["duration"]:
                lo, hi = cinfo["duration"]
                R.ok(lo <= dur <= hi, "duration", rel, f"{dur:.3f} s within [{lo:g}, {hi:g}] s")
            mono = x.mean(axis=1)
            if not is_ogg:
                pkl = np.max(np.abs(mono))
                lead = np.nonzero(np.abs(mono) > pkl * 10 ** (-50 / 20))[0]
                tail = np.nonzero(np.abs(mono) > pkl * 10 ** (-60 / 20))[0]
                lead_ms = lead[0] / SR * 1000
                tail_ms = (mono.size - 1 - tail[-1]) / SR * 1000
                R.ok(abs(mono[0]) <= 0.001 and abs(mono[-1]) <= 0.001 and lead_ms <= 10 and tail_ms <= 30,
                     "shape", rel, f"x[0]={mono[0]:.5f} x[-1]={mono[-1]:.5f} lead-in {lead_ms:.1f} ms, "
                                   f"tail below -60 dB {tail_ms:.1f} ms")
                dc = float(np.mean(mono))
                R.ok(abs(dc) < 0.005, "dc", rel, f"mean {dc:+.5f}")
                clicks = hf_click_frames(mono)
                R.ok(not clicks, "clicks", rel, f"isolated HF spikes at ms {clicks[:5]}" if clicks else "none")
            else:
                st = seam_check(x)
                ok_jump = st["jump"] <= max(st["local_max"], 1e-4)
                ok_hf = not st["hf_click"]
                lvl_lim = 6.0 if rel.startswith("amb/") else 10.0
                ok_lvl = st["level_delta_db"] <= lvl_lim
                R.ok(ok_jump and ok_hf and ok_lvl, "seam", rel,
                     f"step at loop point {st['jump']:.4f} vs max local step {st['local_max']:.4f}; "
                     f"HF at seam {st['hf_excess_db']:+.1f} dB vs local median, isolated click: {st['hf_click']}; "
                     f"level delta {st['level_delta_db']:.1f} dB (<= {lvl_lim:g})")
                # circular scan: prepend the loop's own last 100 ms so the filter start-up at t=0
                # is not mistaken for a click (the seam itself is covered by the seam check)
                pre = int(0.1 * SR)
                clicks = [t - 100 for t in hf_click_frames(np.concatenate([mono[-pre:], mono]), skip_s=0.1)]
                R.ok(not clicks, "clicks", rel, f"isolated HF spikes at ms {clicks[:5]}" if clicks else "none",
                     warn_only=rel.startswith("music/"))
                width = 10 * np.log10(np.mean((x[:, 0] - x[:, 1]) ** 2) / (np.mean((x[:, 0] + x[:, 1]) ** 2) + 1e-20) + 1e-20)
                info_lines.append(f"  {rel:28s} {dur:8.3f} s  loud-part RMS {rms:6.2f}  peak {pk:6.2f}  "
                                  f"side/mid {width:5.1f} dB  {p.stat().st_size / 1e6:5.2f} MB")

    # ---------------------------------------------------------------- variations
    for cue, cinfo in spec.items():
        files = [f for f in cinfo["files"] if f in data]
        if len(files) < 2:
            continue
        worst = 0.0
        pair = ("", "")
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                c = max_xcorr(data[files[i]].mean(axis=1), data[files[j]].mean(axis=1))
                if c > worst:
                    worst, pair = c, (files[i], files[j])
        R.ok(worst < 0.95, "variation", cue,
             f"{len(files)} variations, max normalised xcorr {worst:.3f} ({Path(pair[0]).stem} vs {Path(pair[1]).stem})")

    # ---------------------------------------------------------------- essential distinctness
    ess = sorted(cue_table.ESSENTIAL)
    feats = {}
    for cue in ess:
        rel = spec[cue]["files"][0]
        if rel in data:
            feats[cue] = features(data[rel].mean(axis=1))
    too_close = []
    nearest = {}
    for i, a in enumerate(ess):
        for b in ess[i + 1:]:
            if a not in feats or b not in feats:
                continue
            pa, ca, da = feats[a]
            pb, cb, db_ = feats[b]
            corr = float(np.corrcoef(pa, pb)[0, 1])
            cr = max(ca, cb) / max(min(ca, cb), 1.0)
            dr = max(da, db_) / max(min(da, db_), 1e-3)
            score = corr - 0.5 * np.log2(cr) - 0.5 * np.log2(dr)  # higher = more alike
            for s_, o in ((a, b), (b, a)):
                if s_ not in nearest or score > nearest[s_][1]:
                    nearest[s_] = (o, score, corr, cr, dr)
            if corr > 0.97 and cr < 1.25 and dr < 1.3:
                too_close.append(f"{a}~{b}")
    R.ok(not too_close, "essential", "distinct signatures",
         "too similar: " + ", ".join(too_close) if too_close else f"{len(feats)} essential cues mutually distinct")
    ess_lines = []
    for cue in ess:
        if cue in feats:
            prof, cen, dur = feats[cue]
            o, score, corr, cr, dr = nearest[cue]
            band = OCT[int(np.argmax(prof))]
            ess_lines.append(f"  {cue:16s} centroid {cen:7.0f} Hz  dominant band {band[0]}-{band[1]} Hz  "
                             f"dur(-30dB) {dur:5.2f} s  nearest: {o} (profile corr {corr:.2f}, "
                             f"centroid x{cr:.2f}, duration x{dr:.2f})")

    # ---------------------------------------------------------------- manifest
    man = None
    if R.ok(MANIFEST.exists(), "manifest", "audio_manifest.json", "exists"):
        try:
            man = json.loads(MANIFEST.read_text(encoding="utf-8"))
            R.ok(isinstance(man.get("cues"), dict), "manifest", "schema", 'top-level {"cues": {...}}')
        except Exception as exc:  # noqa: BLE001
            R.add("FAIL", "manifest", "parse", str(exc))
    if man and isinstance(man.get("cues"), dict):
        cues = man["cues"]
        listed = set()
        for cue, cinfo in spec.items():
            ent = cues.get(cue)
            if not R.ok(ent is not None, "manifest", cue, "cue present"):
                continue
            errs = []
            for k, typ in MANIFEST_KEYS.items():
                if k not in ent:
                    errs.append(f"missing {k}")
                elif not isinstance(ent[k], typ) or (typ is int and isinstance(ent[k], bool)):
                    errs.append(f"{k} has type {type(ent[k]).__name__}")
            extra = set(ent) - set(MANIFEST_KEYS)
            if extra:
                errs.append(f"unexpected keys {sorted(extra)}")
            if not errs:
                folder = cinfo["files"][0].split("/")[0]
                if ent["files"] != cinfo["files"]:
                    errs.append("files differ from contract")
                if ent["bus"] != BUSES[folder]:
                    errs.append(f"bus {ent['bus']} (want {BUSES[folder]})")
                if ent["loop"] != (folder in ("amb", "music")):
                    errs.append("loop flag inconsistent with folder")
                if not 1 <= ent["priority"] <= 5:
                    errs.append("priority out of 1..5")
                if cue in cue_table.ESSENTIAL and ent["priority"] != 5:
                    errs.append("essential cue must be priority 5")
                if ent["max_voices"] < 1:
                    errs.append("max_voices < 1")
                if not 0.0 <= ent["pitch_rand"] <= 0.25:
                    errs.append("pitch_rand out of [0, 0.25]")
                if not -24.0 <= ent["volume_db"] <= 6.0:
                    errs.append("volume_db out of [-24, 6]")
                if ent["positional"] and any(f in data and data[f].shape[1] != 1 for f in ent["files"]):
                    errs.append("positional cue must be mono")
            R.ok(not errs, "manifest", cue, "; ".join(errs) if errs else
                 f"bus={ent['bus']} vol={ent['volume_db']:+.1f} pitch_rand={ent['pitch_rand']} voices={ent['max_voices']} "
                 f"pos={ent['positional']} prio={ent['priority']} loop={ent['loop']}")
            listed.update(ent.get("files", []))
        extra_cues = sorted(set(cues) - set(spec))
        R.ok(not extra_cues, "manifest", "no unknown cues", ", ".join(extra_cues) if extra_cues else "none")
        missing_on_disk = sorted(f for f in listed if not (AUDIO / f).exists())
        R.ok(not missing_on_disk, "manifest", "every listed file exists",
             ", ".join(missing_on_disk[:10]) if missing_on_disk else f"{len(listed)} files")
        on_disk = sorted(str(p.relative_to(AUDIO)).replace("\\", "/") for p in AUDIO.rglob("*")
                         if p.suffix.lower() in (".wav", ".ogg"))
        unlisted = [f for f in on_disk if f not in listed]
        R.ok(not unlisted, "manifest", "every file on disk is listed",
             ", ".join(unlisted[:10]) if unlisted else f"{len(on_disk)} audio files on disk, all listed")

    # ---------------------------------------------------------------- size + counts
    files = [p for p in AUDIO.rglob("*") if p.suffix.lower() in (".wav", ".ogg")]
    total_mb = sum(p.stat().st_size for p in files) / 1e6
    R.ok(total_mb < SIZE_LIMIT_MB, "size", "total", f"{total_mb:.2f} MB (< {SIZE_LIMIT_MB:g} MB)")
    per_dir = {}
    for p in files:
        d = p.parent.name
        per_dir.setdefault(d, [0, 0])
        per_dir[d][0] += 1
        per_dir[d][1] += p.stat().st_size

    # ---------------------------------------------------------------- report
    c = R.counts()
    lines = ["WILDRUSH audio check (tools/audio/check_audio.py)",
             f"contract: {contract.CONTRACT_PATH.relative_to(ROOT)} -> {len(spec)} cues, "
             f"{sum(len(v['files']) for v in spec.values())} files",
             "loudness: gated 'loud part' RMS (SFX/UI: 20 ms blocks, blocks within 15 dB of the loudest; "
             "loops: 400 ms blocks within 10 dB)", ""]
    lines.append("files per folder:")
    for d in sorted(per_dir):
        lines.append(f"  {d:6s} {per_dir[d][0]:4d} files  {per_dir[d][1] / 1e6:7.2f} MB")
    lines.append(f"  total  {len(files):4d} files  {total_mb:7.2f} MB")
    lines += ["", "loops:"] + info_lines + ["", "essential cue signatures:"] + ess_lines + [""]
    width = max(len(r["check"]) for r in R.rows)
    for r in R.rows:
        lines.append(f"{r['status']:4s}  {r['check']:{width}s}  {r['subject']:36s} {r['detail']}")
    lines += ["", f"SUMMARY: {c['PASS']} PASS, {c['FAIL']} FAIL, {c['WARN']} WARN",
              "RESULT: " + ("PASS" if c["FAIL"] == 0 else "FAIL")]
    text = "\n".join(lines) + "\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    Path(args.json).write_text(json.dumps({"summary": c, "result": "PASS" if c["FAIL"] == 0 else "FAIL",
                                           "total_mb": round(total_mb, 3), "checks": R.rows}, indent=1) + "\n",
                               encoding="utf-8")
    fails = [r for r in R.rows if r["status"] != "PASS"]
    for r in fails:
        print(f"{r['status']}  {r['check']}  {r['subject']}  {r['detail']}")
    print(f"SUMMARY: {c['PASS']} PASS, {c['FAIL']} FAIL, {c['WARN']} WARN  -> {Path(args.out).relative_to(ROOT)}")
    return 0 if c["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
