#!/usr/bin/env python3
"""Top-down schematic of game/data/arena/briarport_layout.json (design check, not a game capture).
Usage: .venv/bin/python tools/arena/plot_layout.py [out.png]"""
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
lay = json.load(open(os.path.join(ROOT, "game/data/arena/briarport_layout.json")))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "evidence/arena/layout_schematic.png")
S = 8  # px per metre
W, H = 144 * S, 112 * S
img = Image.new("RGB", (W, H), (18, 20, 24))
d = ImageDraw.Draw(img)


def px(x, z):
    return ((x + 72) * S, (z + 56) * S)


def rect(mn, mx, fill, outline=None):
    x0, y0 = px(mn[0], mn[2] if len(mn) == 3 else mn[1])
    x1, y1 = px(mx[0], mx[2] if len(mx) == 3 else mx[1])
    d.rectangle([x0, y0, x1, y1], fill=fill, outline=outline)


for w in lay["water"]:
    rect(w["min"], w["max"], (30, 70, 110))
for f in lay["floors"]:
    if f.get("surface") == "water":
        continue
    top = f["max"][1]
    base = {"stone": (120, 112, 100), "wood": (140, 100, 60), "metal": (100, 108, 118)}.get(f.get("surface"), (110, 110, 110))
    shade = min(40, int(top * 25))
    rect(f["min"], f["max"], tuple(min(255, c + shade) for c in base))
for r in lay["ramps"]:
    (ax, ay, az), (bx, by, bz), w = r["from"], r["to"], r["width"]
    if abs(ax - bx) > abs(az - bz):
        rect([min(ax, bx), 0, az - w / 2], [max(ax, bx), 0, az + w / 2], (170, 150, 90))
    else:
        rect([ax - w / 2, 0, min(az, bz)], [ax + w / 2, 0, max(az, bz)], (170, 150, 90))
for s in lay["solids"]:
    if not s.get("collide", True):
        col = (200, 200, 200)
    else:
        col = {"building": (52, 40, 38), "wall_low": (150, 150, 140), "column": (180, 170, 150), "stall": (160, 60, 50),
               "planter": (60, 120, 60), "crate_stack": (150, 110, 60), "container": (70, 90, 130),
               "fountain": (90, 140, 170), "fountain_statue": (200, 200, 190), "balustrade": (200, 200, 200)}.get(s["kind"], (90, 90, 90))
    rect(s["min"], s["max"], col)
for b in lay["blockers"]:
    if b["kind"] == "boundary":
        continue
    rect(b["min"], b["max"], (220, 60, 60))
for z in lay["zones"]:
    cx, cy = px(z["center"][0], z["center"][2])
    r = z["radius"] * S
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(240, 200, 60), width=3)
    d.text((cx - 4, cy - 6), z["id"], fill=(255, 230, 120))
for sp in lay["spawns"]:
    col = (80, 140, 255) if sp["team"] == 0 else (255, 90, 80)
    rect(sp["protect"]["min"], sp["protect"]["max"], None, outline=col)
    for p in sp["points"]:
        cx, cy = px(p[0], p[2])
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=col)
for p in lay["perch_ledges"]:
    d.line([px(p["a"][0], p["a"][2]), px(p["b"][0], p["b"][2])], fill=(255, 0, 255), width=3)
for i in range(-70, 71, 10):
    x, _ = px(i, 0)
    d.line([x, H - 6, x, H], fill=(90, 90, 90))
os.makedirs(os.path.dirname(out), exist_ok=True)
img.save(out)
print("wrote", out)
