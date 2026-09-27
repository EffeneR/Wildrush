#!/usr/bin/env python3
"""Render log-frequency spectrogram PNGs of the essential cues to evidence/audio/ (numpy + Pillow).

* one PNG per cue (own time scale):     evidence/audio/spec_<cue>.png
* one comparison sheet (shared scale):  evidence/audio/spectrograms_essential.png

Colour: single-hue sequential blue ramp on the light chart surface (quiet = surface,
loud = dark blue), recessive muted-ink axes. A thin envelope strip above each spectrogram
shows the transient shape (level in dB over time).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUDIO = ROOT / "game" / "assets" / "audio"
EVID = ROOT / "evidence" / "audio"

CUES = ["hit_light", "hit_heavy", "guard_block", "guard_break", "parry", "knockout", "zone_contested"]
SHEET_EXTRA = ["zone_activate", "zone_reveal", "zone_ally", "zone_enemy", "score_warning_1", "score_warning_3"]

SURFACE = (0xFC, 0xFC, 0xFB)
INK = (0x0B, 0x0B, 0x0B)
INK2 = (0x52, 0x51, 0x4E)
MUTED = (0x89, 0x87, 0x81)
GRID = (0xE1, 0xE0, 0xD9)
# sequential blue ramp (steps 100..700) preceded by the surface for "near zero"
RAMP = ["#fcfcfb", "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
        "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
RAMP_RGB = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in RAMP], dtype=np.float64)
DB_FLOOR = -80.0
F_LO, F_HI = 40.0, 16000.0


def font(size):
    return ImageFont.load_default(size=size)


def cue_file(cue: str) -> Path:
    for rel in (f"sfx/{cue}_01.wav", f"ui/{cue}.wav"):
        if (AUDIO / rel).exists():
            return AUDIO / rel
    raise FileNotFoundError(cue)


def colorize(db: np.ndarray) -> np.ndarray:
    u = np.clip((db - DB_FLOOR) / -DB_FLOOR, 0.0, 1.0) * (len(RAMP) - 1)
    i0 = np.floor(u).astype(int)
    i1 = np.minimum(i0 + 1, len(RAMP) - 1)
    fr = (u - i0)[..., None]
    return (RAMP_RGB[i0] * (1 - fr) + RAMP_RGB[i1] * fr).astype(np.uint8)


def spectrogram(x, sr, width, height, t_max):
    """Multi-resolution STFT (2048 below ~350 Hz, 1024 above) resampled onto a log-frequency grid."""
    hop = 64
    out_db = None
    t_px = np.linspace(0, t_max, width)
    f_px = np.geomspace(F_HI, F_LO, height)  # top row = high frequency
    layers = []
    for nfft in (2048, 1024):
        f, t, Z = ss.stft(x, fs=sr, window="hann", nperseg=nfft, noverlap=nfft - hop, boundary="zeros")
        mag = np.abs(Z) + 1e-12
        layers.append((f, t, mag))
    ref = max(m.max() for _, _, m in layers)
    for f, t, mag in layers:
        db = 20 * np.log10(mag / ref)
        # interpolate along frequency then time
        col = np.empty((height, db.shape[1]))
        for j in range(db.shape[1]):
            col[:, j] = np.interp(f_px, f, db[:, j])
        grid = np.empty((height, width))
        for i in range(height):
            grid[i] = np.interp(t_px, t, col[i], right=DB_FLOOR)
        layers_db = grid
        if out_db is None:
            out_db = layers_db
        else:
            w = np.clip((np.log2(f_px) - np.log2(350.0)) / (np.log2(700.0) - np.log2(350.0)), 0, 1)[:, None]
            out_db = out_db * (1 - w) + layers_db * w
    return out_db, f_px


def envelope_db(x, sr, width, t_max):
    win = int(0.005 * sr)
    p = np.convolve(x ** 2, np.ones(win) / win, mode="same")
    t = np.arange(x.size) / sr
    env = 10 * np.log10(np.interp(np.linspace(0, t_max, width), t, p, right=0.0) + 1e-12)
    return np.clip(env, -60, 0)


def draw_panel(img, draw, x0, y0, w, h, sig, sr, t_max, title, subtitle, env_h=36):
    L, B = 64, 26  # left margin for freq labels, bottom margin for time labels
    pw, ph = w - L - 12, h - B - env_h - 30
    draw.text((x0 + L, y0 + 2), title, fill=INK, font=font(15))
    draw.text((x0 + L + draw.textlength(title, font=font(15)) + 10, y0 + 4), subtitle, fill=INK2, font=font(12))
    ey = y0 + 24
    # envelope strip
    env = envelope_db(sig, sr, pw, t_max)
    draw.rectangle([x0 + L, ey, x0 + L + pw, ey + env_h - 6], outline=GRID)
    pts = [(x0 + L + i, ey + (env_h - 6) * (-env[i] / 60.0)) for i in range(pw)]
    draw.line(pts, fill=RAMP[9], width=2)
    draw.text((x0 + 8, ey + 4), "level", fill=MUTED, font=font(11))
    sy = ey + env_h
    db, f_px = spectrogram(sig, sr, pw, ph, t_max)
    img.paste(Image.fromarray(colorize(db)), (x0 + L, sy))
    # frequency ticks
    for fv, lab in ((50, "50"), (100, "100"), (200, "200"), (500, "500"), (1000, "1k"), (2000, "2k"),
                    (5000, "5k"), (10000, "10k")):
        yy = sy + ph * (np.log(F_HI / fv) / np.log(F_HI / F_LO))
        draw.line([(x0 + L - 4, yy), (x0 + L, yy)], fill=MUTED)
        draw.text((x0 + L - 8 - draw.textlength(lab, font=font(11)), yy - 7), lab, fill=MUTED, font=font(11))
    draw.text((x0 + 6, sy + ph / 2 - 6), "Hz", fill=MUTED, font=font(11))
    # time ticks
    step = 0.05 if t_max <= 0.4 else 0.1 if t_max <= 1.0 else 0.25
    tv = 0.0
    while tv <= t_max + 1e-9:
        xx = x0 + L + pw * tv / t_max
        draw.line([(xx, sy + ph), (xx, sy + ph + 4)], fill=MUTED)
        lab = f"{int(round(tv * 1000))} ms"
        draw.text((xx - draw.textlength(lab, font=font(11)) / 2, sy + ph + 6), lab, fill=MUTED, font=font(11))
        tv += step
    draw.rectangle([x0 + L, sy, x0 + L + pw, sy + ph], outline=(0xC3, 0xC2, 0xB7))


def legend(draw, x, y):
    draw.text((x, y), "energy (dB re file max)", fill=INK2, font=font(11))
    n = 160
    for i in range(n):
        dbv = DB_FLOOR * (1 - i / (n - 1))
        c = tuple(int(v) for v in colorize(np.array([dbv]))[0])
        draw.line([(x + i, y + 16), (x + i, y + 26)], fill=c)
    draw.rectangle([x, y + 16, x + n, y + 26], outline=GRID)
    draw.text((x, y + 28), f"{int(DB_FLOOR)}", fill=MUTED, font=font(11))
    draw.text((x + n - 8, y + 28), "0", fill=MUTED, font=font(11))


def load(cue):
    p = cue_file(cue)
    x, sr = sf.read(str(p))
    return x, sr, p


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    written = []
    for cue in CUES:
        x, sr, p = load(cue)
        dur = x.size / sr
        W, H = 980, 400
        img = Image.new("RGB", (W, H), SURFACE)
        d = ImageDraw.Draw(img)
        draw_panel(img, d, 0, 6, W, H - 50, x, sr, max(dur, 0.1),
                   cue, f"{p.relative_to(AUDIO)}  -  {dur * 1000:.0f} ms")
        legend(d, W - 200, H - 48)
        out = EVID / f"spec_{cue}.png"
        img.save(out)
        written.append(out)
    # comparison sheet, shared time scale
    sheet_cues = CUES + SHEET_EXTRA
    data = [load(c) for c in sheet_cues]
    t_max = max(x.size / sr for x, sr, _ in data)
    t_max = float(np.ceil(t_max * 4) / 4)
    cols, pw_, ph_ = 2, 760, 250
    rows = int(np.ceil(len(sheet_cues) / cols))
    W, H = cols * pw_, rows * ph_ + 70
    img = Image.new("RGB", (W, H), SURFACE)
    d = ImageDraw.Draw(img)
    d.text((16, 10), "WILDRUSH essential cues - log-frequency spectrograms, shared time scale", fill=INK,
           font=font(18))
    legend(d, W - 200, 8)
    for k, (cue, (x, sr, p)) in enumerate(zip(sheet_cues, data)):
        r, c = divmod(k, cols)
        draw_panel(img, d, c * pw_, 60 + r * ph_, pw_, ph_, x, sr, t_max, cue, f"{x.size / sr * 1000:.0f} ms")
    out = EVID / "spectrograms_essential.png"
    img.save(out)
    written.append(out)
    for w in written:
        print(f"wrote {w.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
