"""Second half of the Briarport texture generators: metals, containers, cloth, banner emblem,
foliage atlas, water/puddle, skyline facades, ironwork (alpha) and the facade detail atlas.

Imported by gen_textures.py (register()). Atlas layouts are written to
blender/arena/atlas_layout.json for the Blender builder (UV rects, pixel space, top-left origin).
"""
from __future__ import annotations

import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import texlib as T

F32 = np.float32
HERE = os.path.dirname(os.path.abspath(__file__))
_save = _save_set = _pick = None


def register(gens, save, save_set, pick):
    global _save, _save_set, _pick
    _save, _save_set, _pick = save, save_set, pick
    gens.update({
        "metal_deck": gen_metal_deck, "iron": gen_iron, "paint_yellow": gen_paint_yellow,
        "container": gen_container, "hazard": gen_hazard, "canvas": gen_canvas, "banner": gen_banner,
        "foliage": gen_foliage, "bark": gen_bark, "water": gen_water, "puddle": gen_puddle,
        "concrete": gen_concrete, "soil": gen_soil, "bronze": gen_bronze, "skyline": gen_skyline,
        "ironwork": gen_ironwork, "detail_atlas": gen_detail_atlas, "roof_metal": gen_roof_metal,
    })


def font(size: int):
    return ImageFont.load_default(size=size)


# =============================================================================== METAL DECK (checker plate)
def gen_metal_deck():
    S = 1024
    n = 32
    cell = S / n
    yy, xx = np.mgrid[0:S, 0:S].astype(F32) + 0.5
    cx = np.floor(xx / cell)
    cy = np.floor(yy / cell)
    lx = (xx - (cx + 0.5) * cell) / cell
    ly = (yy - (cy + 0.5) * cell) / cell
    sgn = np.where(((cx + cy) % 2) == 0, 1.0, -1.0).astype(F32)
    a = np.pi / 4
    u = lx * np.cos(a) + sgn * ly * np.sin(a)
    v = -lx * np.sin(a) * sgn + ly * np.cos(a)
    e = (u / 0.40) ** 2 + (v / 0.11) ** 2
    bump = np.clip(1 - e, 0, 1) ** 0.5
    dirt_n = T.fbm(S, S, 14, 5, 201)
    scuff = T.fbm(S, S, 48, 3, 202, aspect=0.3)
    hgt = bump * 0.6 + (T.fbm(S, S, 64, 3, 203) - 0.5) * 0.05
    nrm = T.height_to_normal(hgt, 4.0)
    ao = T.ao_from_height(hgt, sigmas=(1.5, 4, 10), strength=1.6)
    steel = T.rgb((132, 134, 136)) * (0.85 + 0.25 * scuff[..., None])
    steel = steel * (1 + 0.15 * bump[..., None])
    rust = T.smoothstep(0.8, 0.93, T.fbm(S, S, 18, 5, 204)) * (1 - bump * 0.7)
    grime = T.smoothstep(0.45, 0.9, dirt_n) * (1 - bump) * 0.45
    alb = T.mix(steel, np.ones_like(steel) * T.rgb((112, 72, 46)), rust * 0.8)
    alb = T.mix(alb, np.ones_like(alb) * T.rgb((60, 58, 54)), grime * 0.6)
    alb *= ao[..., None] ** 0.5
    metal = np.clip(0.9 - rust - grime * 0.6, 0, 1)
    rough = np.clip(0.5 - 0.15 * bump + rust * 0.4 + grime * 0.3 + (scuff - 0.5) * 0.1, 0, 1)
    _save_set("metal_deck", alb, nrm, T.orm_u8(ao, rough, metal))


# =============================================================================== IRON (painted, dark)
def gen_iron():
    S = 512
    n1 = T.fbm(S, S, 8, 5, 211)
    chips = T.smoothstep(0.8, 0.9, T.fbm(S, S, 24, 4, 212))
    rust = T.smoothstep(0.72, 0.9, T.fbm(S, S, 6, 5, 213))
    hgt = -chips * 0.3 + (n1 - 0.5) * 0.05
    nrm = T.height_to_normal(hgt, 2.0)
    base = T.rgb((42, 46, 44)) * (0.85 + 0.3 * n1[..., None])
    base = T.mix(base, np.ones_like(base) * T.rgb((96, 64, 44)), rust * 0.6)
    base = T.mix(base, np.ones_like(base) * T.rgb((110, 110, 112)), chips * 0.7)
    rough = np.clip(0.52 + rust * 0.35 + (n1 - 0.5) * 0.1, 0, 1)
    metal = np.clip(chips * 0.9, 0, 1)
    ao = np.ones_like(n1)
    _save_set("iron", base, nrm, T.orm_u8(ao, rough, metal), orm_half=False)


# =============================================================================== YELLOW PAINT (crane, forklift)
def gen_paint_yellow():
    S = 1024
    n1 = T.fbm(S, S, 6, 5, 221)
    chips = T.smoothstep(0.78, 0.86, T.fbm(S, S, 20, 5, 222))
    streak = T.streaks(S, S, 223, cover=0.45, base=16)
    hgt = -chips * 0.4 + (n1 - 0.5) * 0.04
    nrm = T.height_to_normal(hgt, 2.5)
    base = T.rgb((222, 170, 36)) * (0.9 + 0.14 * n1[..., None])
    base *= (1 - 0.25 * streak)[..., None]
    under = T.mix(np.ones_like(base) * T.rgb((70, 66, 62)), np.ones_like(base) * T.rgb((116, 70, 40)), T.fbm(S, S, 16, 3, 224))
    alb = T.mix(base, under, chips)
    rough = np.clip(0.45 + chips * 0.4 + streak * 0.2, 0, 1)
    metal = chips * 0.6
    _save_set("paint_yellow", alb, nrm, T.orm_u8(np.ones_like(n1), rough, metal))


# =============================================================================== CONTAINER (corrugated)
def gen_container():
    S = 1024
    ribs = 10
    xx = (np.arange(S, dtype=F32) + 0.5) / S * ribs
    f = xx % 1.0
    # trapezoid profile: flat 0.35 / ramp 0.15 / flat 0.35 / ramp 0.15
    prof = np.interp(f, [0, 0.35, 0.5, 0.85, 1.0], [0, 0, 1, 1, 0]).astype(F32)
    hgt = np.tile(prof[None, :], (S, 1)) * 0.8
    dents = T.fbm(S, S, 3, 3, 231)
    hgt = hgt + (dents - 0.5) * 0.6
    nrm = T.height_to_normal(hgt, 4.0)
    ao = T.ao_from_height(hgt, sigmas=(3, 8), strength=1.2)
    streak = T.streaks(S, S, 232, cover=0.55, base=14)
    rust = T.smoothstep(0.74, 0.88, T.fbm(S, S, 10, 5, 233))
    top_rust = np.clip(1.0 - (np.arange(S, dtype=F32)[:, None] / S) * 6, 0, 1) * T.fbm(S, S, 24, 3, 234, aspect=0.1)
    n1 = T.fbm(S, S, 8, 4, 235)
    rough = np.clip(0.55 + rust * 0.35 + (n1 - 0.5) * 0.1, 0, 1)
    metal = np.clip(0.25 - rust * 0.25, 0, 1)
    _save("container_normal", T.normal_u8(nrm))
    _save("container_orm", T.downsample(T.orm_u8(ao, rough, metal).astype(F32), 2).round().astype(np.uint8))
    for name, col in (("container_blue", (44, 86, 128)), ("container_red", (150, 52, 40)), ("container_green", (58, 96, 70))):
        base = T.rgb(col) * (0.9 + 0.16 * n1[..., None]) * (0.9 + 0.1 * np.tile(prof[None, :], (S, 1))[..., None])
        base *= (1 - 0.3 * streak)[..., None]
        base = T.mix(base, np.ones_like(base) * T.rgb((118, 70, 42)), np.clip(rust * 0.8 + top_rust * 0.5, 0, 1))
        _save(name + "_albedo", T.to_u8(base * ao[..., None] ** 0.5))


# =============================================================================== HAZARD STRIPES
def gen_hazard():
    S = 512
    yy, xx = np.mgrid[0:S, 0:S].astype(F32) + 0.5
    P = S / 5.0
    s = ((xx + yy) % P) / P
    stripe = T.smoothstep(0.48, 0.52, s) * (1 - T.smoothstep(0.98, 1.0, s)) + (1 - T.smoothstep(0.0, 0.02, s)) * 0
    wear = T.smoothstep(0.62, 0.8, T.fbm(S, S, 12, 5, 241))
    n1 = T.fbm(S, S, 16, 4, 242)
    yel = T.rgb((226, 178, 38)) * (0.9 + 0.14 * n1[..., None])
    blk = T.rgb((34, 34, 34)) * (0.9 + 0.2 * n1[..., None])
    base = T.mix(yel, blk, stripe)
    base = T.mix(base, np.ones_like(base) * T.rgb((128, 124, 118)), wear * 0.75)
    hgt = -wear * 0.2 + (n1 - 0.5) * 0.03
    nrm = T.height_to_normal(hgt, 2.0)
    rough = np.clip(0.55 + wear * 0.35, 0, 1)
    _save_set("hazard", base, nrm, T.orm_u8(np.ones_like(n1), rough, 0.0), orm_half=False)


# =============================================================================== CANVAS (awnings, stall canopies, tarps)
def gen_canvas():
    S = 1024
    yy, xx = np.mgrid[0:S, 0:S].astype(F32)
    weave = (np.sin(xx * np.pi / 2.0) * np.sin(yy * np.pi / 2.0)) * 0.5 + 0.5
    folds = T.fbm(S, S, 4, 3, 251, aspect=0.5) * 0.5
    wr = T.fbm(S, S, 12, 4, 252)
    hgt = weave * 0.08 + folds * 0.6 + (wr - 0.5) * 0.1
    nrm = T.height_to_normal(hgt, 2.0)
    ao = T.ao_from_height(hgt, sigmas=(8, 20), strength=1.0)
    dirt = T.smoothstep(0.55, 0.85, T.fbm(S, S, 5, 5, 253))
    fade = T.fbm(S, S, 2, 4, 254)
    rough = np.clip(0.9 + (wr - 0.5) * 0.06, 0, 1)
    _save("canvas_normal", T.normal_u8(nrm))
    _save("canvas_orm", T.downsample(T.orm_u8(ao, rough, 0.0).astype(F32), 2).round().astype(np.uint8))
    for name, col in (("canvas_red", (156, 42, 36)), ("canvas_green", (52, 84, 56)), ("canvas_cream", (206, 192, 162))):
        base = T.rgb(col) * (0.9 + 0.1 * weave[..., None]) * (0.95 + 0.08 * fade[..., None])
        base = T.mix(base, np.ones_like(base) * T.rgb((70, 62, 50)), dirt * 0.12)
        _save(name + "_albedo", T.to_u8(base * ao[..., None] ** 0.6))


# =============================================================================== BANNER (crimson, three-claw emblem)
def claw_emblem(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, fill, sc: float = 1.0):
    """Original WILDRUSH-Briarport three-claw emblem: three tapered, curved claw marks fanning
    upward from a shared base arc. Coordinates relative to (cx, cy) centre, size = height."""
    def stroke(p0, p1, p2, w0):
        pts_l, pts_r = [], []
        N = 40
        for i in range(N + 1):
            t = i / N
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
            dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln, dx / ln
            w = w0 * (1 - t) ** 0.85 * (0.6 + 0.4 * math.sin(min(1.0, t * 3.0) * math.pi / 2))
            pts_l.append((x + nx * w / 2, y + ny * w / 2))
            pts_r.append((x - nx * w / 2, y - ny * w / 2))
        return pts_l + pts_r[::-1]

    def P(u, v):
        return (cx + (u - 0.5) * size, cy + (v - 0.5) * size)
    w = 0.16 * size
    draw.polygon(stroke(P(0.40, 0.80), P(0.20, 0.52), P(0.10, 0.08), w), fill=fill)
    draw.polygon(stroke(P(0.50, 0.84), P(0.53, 0.45), P(0.50, 0.00), w * 1.1), fill=fill)
    draw.polygon(stroke(P(0.60, 0.80), P(0.80, 0.52), P(0.90, 0.08), w), fill=fill)
    # base arc (paw pad) joining the claws
    bb = [P(0.26, 0.74), P(0.74, 1.02)]
    draw.chord([bb[0], bb[1]], start=180, end=360, fill=fill)
    draw.ellipse([P(0.40, 0.86), P(0.60, 1.00)], fill=fill)


def gen_banner():
    W, H = 1024, 2048
    SS = 2
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    crimson = (142, 24, 32, 255)
    dark = (96, 14, 22, 255)
    cream = (232, 214, 184, 255)
    gold = (196, 152, 70, 255)
    # banner body with swallowtail bottom
    body = [(0, 0), (W * SS, 0), (W * SS, int(H * SS * 0.90)), (W * SS // 2, int(H * SS * 0.80)), (0, int(H * SS * 0.90))]
    d.polygon(body, fill=crimson)
    m = 36 * SS
    d.line([(m, 0), (m, int(H * SS * 0.88))], fill=dark, width=18 * SS)
    d.line([(W * SS - m, 0), (W * SS - m, int(H * SS * 0.88))], fill=dark, width=18 * SS)
    d.line([(m + 22 * SS, 0), (m + 22 * SS, int(H * SS * 0.875))], fill=gold, width=5 * SS)
    d.line([(W * SS - m - 22 * SS, 0), (W * SS - m - 22 * SS, int(H * SS * 0.875))], fill=gold, width=5 * SS)
    d.rectangle([0, 0, W * SS, 70 * SS], fill=dark)
    d.rectangle([0, 70 * SS, W * SS, 78 * SS], fill=gold)
    claw_emblem(d, W * SS / 2, H * SS * 0.33, W * SS * 0.62, cream)
    # neutral slogan (set dressing only)
    f = font(78 * SS)
    for i, line in enumerate(("BRIARPORT",)):
        tw = d.textlength(line, font=f)
        d.text(((W * SS - tw) / 2, H * SS * 0.585), line, font=f, fill=cream)
    f2 = font(40 * SS)
    for i, line in enumerate(("STRENGTH BUILDS", "A BRIGHTER TOMORROW")):
        tw = d.textlength(line, font=f2)
        d.text(((W * SS - tw) / 2, H * SS * 0.64 + i * 54 * SS), line, font=f2, fill=gold)
    img = img.resize((W, H), Image.LANCZOS)
    a = np.asarray(img).astype(F32) / 255.0
    rgbc = a[..., :3]
    alpha = a[..., 3]
    weave = T.fbm(H, W, 64, 2, 261)
    folds = np.tile(T.fbm(1, W, 6, 3, 262)[0][None, :], (H, 1))
    shade = 0.82 + 0.18 * folds
    rgbc = rgbc * (0.93 + 0.07 * weave[..., None]) * shade[..., None]
    fade = T.fbm(H, W, 3, 3, 263)
    rgbc = rgbc * (0.92 + 0.1 * fade[..., None])
    out = np.concatenate([rgbc, alpha[..., None]], axis=-1)
    _save("banner_albedo", T.to_u8(out))
    hgt = np.tile((folds * 1.5)[None, :] if folds.ndim == 1 else folds * 1.5, (1, 1)) + weave * 0.05
    nrm = T.height_to_normal(hgt, 3.0)
    _save("banner_normal", T.normal_u8(T.downsample(nrm, 2)))


# =============================================================================== FOLIAGE ATLAS (alpha)
FOLIAGE_LAYOUT = {
    "canopy_a": (0, 0, 1024, 1024),
    "canopy_b": (1024, 0, 1024, 1024),
    "ivy": (0, 1024, 1024, 512),
    "weeds": (0, 1536, 1024, 512),
    "flowers": (1024, 1024, 1024, 512),
    "shrub": (1024, 1536, 1024, 512),
}


def _leaf(d, x, y, L, Wd, ang, col):
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(13):
        t = i / 12.0
        w = Wd * math.sin(math.pi * t) ** 0.8
        pts.append((t * L, w))
    for i in range(12, -1, -1):
        t = i / 12.0
        w = Wd * math.sin(math.pi * t) ** 0.8
        pts.append((t * L, -w))
    d.polygon([(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in pts], fill=col)


def _cluster(d, r, x0, y0, w, h, n, Lr, greens, shape="round", hang=False):
    for i in range(n):
        if shape == "round":
            rr = math.sqrt(r.random()) * 0.48
            a = r.random() * 2 * math.pi
            x = x0 + w / 2 + math.cos(a) * rr * w
            y = y0 + h / 2 + math.sin(a) * rr * h
            depth = 1.0 - rr / 0.48
        else:
            x = x0 + r.random() * w
            y = y0 + (r.random() ** (1.6 if hang else 1.0)) * h
            depth = r.random()
        L = r.uniform(*Lr)
        ang = r.uniform(0, 2 * math.pi) if not hang else r.uniform(0.9, 2.2)
        g = greens[int(r.integers(len(greens)))]
        k = 0.55 + 0.45 * depth + r.uniform(-0.08, 0.08)
        col = tuple(int(max(0, min(255, c * k))) for c in g) + (255,)
        _leaf(d, x, y, L, L * r.uniform(0.28, 0.4), ang, col)


def gen_foliage():
    S = 2048
    SS = 2
    img = Image.new("RGBA", (S * SS, S * SS), (60, 80, 40, 0))
    d = ImageDraw.Draw(img)
    r = T.rng(271)
    greens = [(62, 96, 40), (78, 112, 46), (54, 84, 36), (92, 124, 56), (70, 104, 44), (100, 130, 60)]
    ivyg = [(46, 78, 34), (60, 92, 40), (38, 66, 30), (72, 104, 48)]
    # canopy clusters (several blobs per card)
    for key, seed in (("canopy_a", 1), ("canopy_b", 2)):
        x0, y0, w, h = [v * SS for v in FOLIAGE_LAYOUT[key]]
        rr = T.rng(280 + seed)
        blobs = [(0.5, 0.5, 0.9)] + [(rr.uniform(0.25, 0.75), rr.uniform(0.25, 0.75), rr.uniform(0.4, 0.6)) for _ in range(6)]
        for bx, by, bs in blobs:
            bw, bh = w * bs, h * bs
            _cluster(d, rr, x0 + bx * w - bw / 2, y0 + by * h - bh / 2, bw, bh, int(900 * bs), (22 * SS, 40 * SS), greens)
    # ivy: hanging strands from the top edge
    x0, y0, w, h = [v * SS for v in FOLIAGE_LAYOUT["ivy"]]
    for s in range(60):
        sx = x0 + r.random() * w
        length = h * r.uniform(0.3, 0.98)
        y = y0
        x = sx
        while y < y0 + length:
            ang = r.uniform(0, 2 * math.pi)
            L = r.uniform(14, 26) * SS
            _leaf(d, x + r.uniform(-12, 12) * SS, y, L, L * 0.45, ang, ivyg[int(r.integers(len(ivyg)))] + (255,))
            y += r.uniform(6, 14) * SS
            x += r.uniform(-4, 4) * SS
    # weeds / grass tufts along the bottom
    x0, y0, w, h = [v * SS for v in FOLIAGE_LAYOUT["weeds"]]
    for i in range(700):
        bx = x0 + r.random() * w
        base_y = y0 + h
        L = r.uniform(0.2, 0.95) * h
        ang = -math.pi / 2 + r.uniform(-0.5, 0.5)
        col = [(96, 118, 52), (80, 104, 44), (120, 128, 64), (70, 92, 40)][int(r.integers(4))] + (255,)
        _leaf(d, bx, base_y, L, r.uniform(3, 7) * SS, ang, col)
    # flowers (geranium-like): leaves + red/pink blossoms
    x0, y0, w, h = [v * SS for v in FOLIAGE_LAYOUT["flowers"]]
    _cluster(d, r, x0, y0 + h * 0.25, w, h * 0.75, 1600, (18 * SS, 30 * SS), greens, shape="box")
    for i in range(420):
        fx = x0 + r.random() * w
        fy = y0 + r.random() ** 1.5 * h * 0.75
        rad = r.uniform(7, 14) * SS
        col = [(200, 40, 44), (220, 70, 90), (236, 110, 140), (230, 200, 90), (240, 240, 230)][int(r.integers(5))]
        for k in range(5):
            a = k * 2 * math.pi / 5 + r.random()
            d.ellipse([fx + math.cos(a) * rad * 0.6 - rad * 0.5, fy + math.sin(a) * rad * 0.6 - rad * 0.5,
                       fx + math.cos(a) * rad * 0.6 + rad * 0.5, fy + math.sin(a) * rad * 0.6 + rad * 0.5], fill=col + (255,))
    # shrub (box-shaped hedge card)
    x0, y0, w, h = [v * SS for v in FOLIAGE_LAYOUT["shrub"]]
    _cluster(d, r, x0 + w * 0.02, y0 + h * 0.08, w * 0.96, h * 0.9, 3200, (16 * SS, 28 * SS), greens, shape="box")
    img = img.resize((S, S), Image.LANCZOS)
    a = np.asarray(img).astype(F32) / 255.0
    alpha = a[..., 3]
    rgbc = a[..., :3] / np.maximum(alpha[..., None], 1e-3)
    # dilate colour into transparent texels (avoid dark fringes with mip-mapping)
    mask = alpha > 0.02
    col_bg = rgbc.copy()
    for _ in range(6):
        blurred = np.stack([T.blur(col_bg[..., c] * mask, 3.0) for c in range(3)], -1)
        wsum = T.blur(mask.astype(F32), 3.0)[..., None]
        fill = blurred / np.maximum(wsum, 1e-4)
        col_bg = np.where(mask[..., None], col_bg, fill)
        mask = mask | (wsum[..., 0] > 0.01)
    alpha = np.where(alpha > 0.5, 1.0, alpha)
    out = np.concatenate([np.clip(col_bg, 0, 1), alpha[..., None]], axis=-1)
    _save("foliage_albedo", T.to_u8(out))
    lum = col_bg.mean(-1)
    nrm = T.height_to_normal(T.blur(lum, 1.0), 4.0)
    _save("foliage_normal", T.normal_u8(T.downsample(nrm, 2)))
    with open(os.path.join(HERE, "atlas_foliage.json"), "w") as fh:
        json.dump({"size": [S, S], "rects": FOLIAGE_LAYOUT}, fh, indent=1)


# =============================================================================== BARK
def gen_bark():
    W, H = 512, 1024
    ridges = T.fbm(H, W, 12, 5, 291, aspect=0.12)
    cracks = T.smoothstep(0.35, 0.5, ridges)
    fine = T.fbm(H, W, 32, 3, 292)
    hgt = cracks * 0.8 + fine * 0.2
    nrm = T.height_to_normal(hgt, 4.0)
    ao = T.ao_from_height(hgt, strength=2.0)
    base = T.mix(T.rgb((46, 38, 30)) * np.ones((H, W, 1), F32), T.rgb((112, 100, 86)) * np.ones((H, W, 1), F32), cracks)
    base *= (0.85 + 0.25 * fine[..., None])
    moss = T.smoothstep(0.7, 0.85, T.fbm(H, W, 6, 4, 293)) * 0.5
    base = T.mix(base, np.ones_like(base) * T.rgb((80, 96, 50)), moss)
    _save_set("bark", base * ao[..., None] ** 0.5, nrm, T.orm_u8(ao, np.full_like(fine, 0.9), 0.0))


# =============================================================================== WATER
def gen_water():
    S = 1024
    yy, xx = np.mgrid[0:S, 0:S].astype(F32) / S
    hgt = np.zeros((S, S), F32)
    r = T.rng(301)
    for i in range(14):
        kx, ky = int(r.integers(-9, 10)), int(r.integers(1, 12))
        amp = 1.0 / math.hypot(kx, ky)
        ph = r.random() * 2 * math.pi
        hgt += amp * np.sin(2 * np.pi * (kx * xx + ky * yy) + ph)
    hgt += (T.spectral_noise(S, S, 2.4, 302) - 0.5) * 1.2
    nrm = T.height_to_normal(hgt, 1.2)
    base = T.rgb((34, 62, 60)) * (0.9 + 0.2 * T.fbm(S, S, 3, 3, 303)[..., None])
    rough = np.full((S, S), 0.06, F32)
    _save_set("water", base, nrm, T.orm_u8(np.ones_like(rough), rough, 0.0))


# =============================================================================== PUDDLE
def gen_puddle():
    S = 512
    yy, xx = np.mgrid[0:S, 0:S].astype(F32) + 0.5
    d = np.sqrt((xx - S / 2) ** 2 + (yy - S / 2) ** 2) / (S / 2)
    edge_n = T.fbm(S, S, 6, 4, 311)
    alpha = 1.0 - T.smoothstep(0.55, 0.98, d + (edge_n - 0.5) * 0.3)
    base = T.rgb((46, 46, 44)) * np.ones((S, S, 1), F32) * (0.9 + 0.2 * T.fbm(S, S, 8, 3, 312)[..., None])
    out = np.concatenate([base, alpha[..., None]], -1)
    _save("puddle_albedo", T.to_u8(out))
    rip = T.fbm(S, S, 16, 3, 313)
    nrm = T.height_to_normal(rip, 0.6)
    _save("puddle_normal", T.normal_u8(nrm))
    rough = np.clip(0.04 + (1 - alpha) * 0.5, 0, 1)
    _save("puddle_orm", T.orm_u8(np.ones_like(rough), rough, 0.0))


# =============================================================================== CONCRETE (cast)
def gen_concrete():
    S = 1024
    n1 = T.fbm(S, S, 6, 6, 321)
    pits = T.smoothstep(0.86, 0.93, T.spectral_noise(S, S, 0.2, 322))
    boards = (np.sin((np.arange(S, dtype=F32)[:, None] / S) * 2 * np.pi * 10) * 0.5 + 0.5) * np.ones((1, S), F32)
    streak = T.streaks(S, S, 323, cover=0.4)
    hgt = n1 * 0.2 - pits * 0.4 + boards * 0.03
    nrm = T.height_to_normal(hgt, 2.0)
    ao = T.ao_from_height(hgt, strength=1.2)
    base = T.rgb((172, 170, 162)) * (0.86 + 0.2 * n1[..., None]) * (1 - 0.15 * streak[..., None])
    base *= (1 - 0.4 * pits)[..., None]
    base *= (0.97 + 0.03 * boards[..., None])
    rough = np.clip(0.88 + (n1 - 0.5) * 0.08, 0, 1)
    _save_set("concrete", base * ao[..., None] ** 0.5, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== SOIL
def gen_soil():
    S = 512
    n1 = T.fbm(S, S, 10, 5, 331)
    peb_pts = T.rng(332).random((260, 2))
    pid, f1, f2 = T.voronoi(S, S, peb_pts)
    peb = T.smoothstep(4.0, 1.5, f1) * (T.rng(333).random(260) < 0.5)[pid]
    hgt = n1 * 0.3 + peb * 0.6
    nrm = T.height_to_normal(hgt, 3.0)
    ao = T.ao_from_height(hgt, strength=2.0)
    base = T.rgb((62, 48, 36)) * (0.8 + 0.4 * n1[..., None])
    base = T.mix(base, np.ones_like(base) * T.rgb((128, 118, 104)), peb * 0.8)
    leaves = T.smoothstep(0.8, 0.9, T.fbm(S, S, 20, 3, 334)) * 0.6
    base = T.mix(base, np.ones_like(base) * T.rgb((120, 90, 40)), leaves)
    _save_set("soil", base * ao[..., None] ** 0.5, nrm, T.orm_u8(ao, np.full_like(n1, 0.95), 0.0), orm_half=False)


# =============================================================================== BRONZE (patina)
def gen_bronze():
    S = 512
    n1 = T.fbm(S, S, 14, 5, 341)
    streak = T.streaks(S, S, 342, cover=0.6, base=12)
    pat = np.clip(T.smoothstep(0.55, 0.85, n1) * 0.45 + streak * 0.55, 0, 1)
    base = T.mix(T.rgb((116, 80, 46)) * np.ones((S, S, 1), F32), T.rgb((86, 138, 118)) * np.ones((S, S, 1), F32), pat)
    base *= (0.85 + 0.2 * T.fbm(S, S, 24, 3, 343)[..., None])
    rough = np.clip(0.35 + pat * 0.5, 0, 1)
    metal = np.clip(0.95 - pat, 0, 1)
    nrm = T.height_to_normal(n1 * 0.2, 1.0)
    _save_set("bronze", base, nrm, T.orm_u8(np.ones_like(n1), rough, metal), orm_half=False)


# =============================================================================== SKYLINE FACADES (distant, painted windows)
def gen_skyline():
    W, H = 2048, 2048                                  # 24 m x 4 bands of 12 m
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    bands = [((222, 206, 176), "plaster"), ((206, 160, 104), "plaster"), ((150, 72, 54), "brick"), ((176, 168, 152), "stone")]
    ppm = W / 24.0
    for bi, (col, kind) in enumerate(bands):
        y0 = bi * 512
        d.rectangle([0, y0, W, y0 + 512], fill=col)
        # string course & cornice
        d.rectangle([0, y0 + 0, W, y0 + 14], fill=tuple(int(c * 0.8) for c in col))
        d.rectangle([0, y0 + int(512 - 4.2 * 512 / 12), W, y0 + int(512 - 4.0 * 512 / 12)], fill=(200, 192, 176))
        for k in range(8):                              # 8 bays of 3 m
            cx = int((k + 0.5) * 3 * ppm)
            for fl in range(2):                          # upper floors
                top = y0 + int((1.0 + fl * 3.3) * 512 / 12)
                ww, wh = int(1.1 * ppm), int(1.8 * 512 / 12)
                d.rectangle([cx - ww // 2 - 4, top - 4, cx + ww // 2 + 4, top + wh + 6], fill=(214, 206, 190))
                d.rectangle([cx - ww // 2, top, cx + ww // 2, top + wh], fill=(40, 52, 62))
                d.line([cx, top, cx, top + wh], fill=(200, 196, 188), width=3)
                d.line([cx - ww // 2, top + wh // 2, cx + ww // 2, top + wh // 2], fill=(200, 196, 188), width=3)
                shc = [(60, 92, 70), (70, 90, 120), (120, 80, 50)][(k + bi) % 3]
                d.rectangle([cx - ww // 2 - 30, top, cx - ww // 2 - 6, top + wh], fill=shc)
                d.rectangle([cx + ww // 2 + 6, top, cx + ww // 2 + 30, top + wh], fill=shc)
            # ground floor: doors / shop windows
            gtop = y0 + int((12 - 3.6) * 512 / 12)
            if k % 3 == 1:
                d.rectangle([cx - int(0.7 * ppm), gtop, cx + int(0.7 * ppm), y0 + 512], fill=(70, 50, 36))
            else:
                d.rectangle([cx - int(1.0 * ppm), gtop + 10, cx + int(1.0 * ppm), y0 + 512 - 30], fill=(46, 56, 62))
    a = np.asarray(img).astype(F32) / 255.0
    n1 = T.fbm(H, W, 8, 4, 351)
    a *= (0.85 + 0.2 * n1[..., None])
    a *= (1 - 0.15 * T.streaks(H, W, 352, cover=0.5))[..., None]
    _save("skyline_albedo", T.to_u8(a))
    orm = T.orm_u8(np.ones((H // 2, W // 2), F32), np.full((H // 2, W // 2), 0.85, F32), 0.0)
    _save("skyline_orm", orm)


# =============================================================================== IRONWORK (alpha railings)
IRON_LAYOUT = {
    "balcony": (0, 0, 1024, 256),      # 2 m wide x 1 m tall railing, tileable in u
    "fence": (0, 256, 1024, 256),      # plain bar fence
    "grille": (0, 512, 512, 512),      # window grille
    "gate": (512, 512, 512, 512),      # ornamental gate panel
}


def gen_ironwork():
    S = 1024
    SS = 2
    img = Image.new("RGBA", (S * SS, S * SS), (40, 42, 40, 0))
    d = ImageDraw.Draw(img)
    c = (40, 43, 41, 255)
    # balcony railing: rails + balusters + scrolls, period 128 px (0.25 m) over 1024 px (2 m)
    x0, y0, w, h = [v * SS for v in IRON_LAYOUT["balcony"]]
    d.rectangle([x0, y0 + 6 * SS, x0 + w, y0 + 22 * SS], fill=c)
    d.rectangle([x0, y0 + h - 22 * SS, x0 + w, y0 + h - 8 * SS], fill=c)
    d.rectangle([x0, y0 + 48 * SS, x0 + w, y0 + 56 * SS], fill=c)
    for i in range(0, w, 32 * SS):
        d.rectangle([x0 + i + 13 * SS, y0 + 20 * SS, x0 + i + 19 * SS, y0 + h - 20 * SS], fill=c)
    for i in range(0, w, 128 * SS):
        cx = x0 + i + 64 * SS
        for sgn in (-1, 1):
            d.arc([cx - 30 * SS + sgn * 22 * SS, y0 + 60 * SS, cx + 30 * SS + sgn * 22 * SS, y0 + 120 * SS], 0, 360, fill=c, width=5 * SS)
        d.ellipse([cx - 9 * SS, y0 + 140 * SS, cx + 9 * SS, y0 + 158 * SS], outline=c, width=5 * SS)
    # fence
    x0, y0, w, h = [v * SS for v in IRON_LAYOUT["fence"]]
    d.rectangle([x0, y0 + 20 * SS, x0 + w, y0 + 32 * SS], fill=c)
    d.rectangle([x0, y0 + h - 40 * SS, x0 + w, y0 + h - 28 * SS], fill=c)
    for i in range(0, w, 32 * SS):
        d.rectangle([x0 + i + 12 * SS, y0 + 8 * SS, x0 + i + 20 * SS, y0 + h - 10 * SS], fill=c)
        d.polygon([(x0 + i + 8 * SS, y0 + 12 * SS), (x0 + i + 16 * SS, y0), (x0 + i + 24 * SS, y0 + 12 * SS)], fill=c)
    # grille
    x0, y0, w, h = [v * SS for v in IRON_LAYOUT["grille"]]
    d.rectangle([x0 + 8 * SS, y0 + 8 * SS, x0 + w - 8 * SS, y0 + h - 8 * SS], outline=c, width=14 * SS)
    for i in range(1, 6):
        xx = x0 + i * w // 6
        d.rectangle([xx - 5 * SS, y0, xx + 5 * SS, y0 + h], fill=c)
    for j in range(1, 4):
        yy = y0 + j * h // 4
        d.rectangle([x0, yy - 5 * SS, x0 + w, yy + 5 * SS], fill=c)
    # gate panel
    x0, y0, w, h = [v * SS for v in IRON_LAYOUT["gate"]]
    d.rectangle([x0 + 6 * SS, y0 + 6 * SS, x0 + w - 6 * SS, y0 + h - 6 * SS], outline=c, width=16 * SS)
    for i in range(1, 8):
        xx = x0 + i * w // 8
        d.rectangle([xx - 5 * SS, y0, xx + 5 * SS, y0 + h], fill=c)
    d.arc([x0 + 40 * SS, y0 + 40 * SS, x0 + w - 40 * SS, y0 + h - 40 * SS], 180, 360, fill=c, width=10 * SS)
    img = img.resize((S, S), Image.LANCZOS)
    a = np.asarray(img).astype(F32) / 255.0
    alpha = np.where(a[..., 3] > 0.5, 1.0, a[..., 3])
    base = np.ones((S, S, 3), F32) * T.rgb((40, 43, 41)) * (0.85 + 0.3 * T.fbm(S, S, 16, 3, 361)[..., None])
    _save("ironwork_albedo", T.to_u8(np.concatenate([base, alpha[..., None]], -1)))
    with open(os.path.join(HERE, "atlas_ironwork.json"), "w") as fh:
        json.dump({"size": [S, S], "rects": IRON_LAYOUT}, fh, indent=1)


# =============================================================================== ROOF METAL (corrugated sheets)
def gen_roof_metal():
    S = 1024
    yy = (np.arange(S, dtype=F32)[:, None] + 0.5) / S
    xx = (np.arange(S, dtype=F32)[None, :] + 0.5) / S
    prof = 0.5 + 0.5 * np.sin(2 * np.pi * xx * 24)
    hgt = np.tile(prof, (S, 1)) * 0.5 + (T.fbm(S, S, 3, 3, 371) - 0.5) * 0.3
    laps = T.smoothstep(0.96, 0.995, (yy * 2) % 1.0) * np.ones((1, S), F32)
    hgt = hgt - laps * 0.3
    nrm = T.height_to_normal(hgt, 3.0)
    ao = T.ao_from_height(hgt, sigmas=(3, 8), strength=1.2)
    rust = T.smoothstep(0.72, 0.92, T.fbm(S, S, 14, 5, 372)) * 0.55
    streak = T.streaks(S, S, 373, cover=0.5) * 0.6
    base = T.rgb((128, 132, 134)) * (0.85 + 0.2 * np.tile(prof, (S, 1))[..., None])
    base = T.mix(base, np.ones_like(base) * T.rgb((122, 76, 46)), np.clip(rust + streak * 0.4, 0, 1))
    rough = np.clip(0.5 + rust * 0.4, 0, 1)
    metal = np.clip(0.8 - rust, 0, 1)
    _save_set("roof_metal", base * ao[..., None] ** 0.5, nrm, T.orm_u8(ao, rough, metal))


# =============================================================================== DETAIL ATLAS
ATLAS = {
    # name: (x, y, w, h) in px, 2048 atlas, top-left origin
    "win_sash": (0, 0, 128, 256),
    "win_casement": (128, 0, 128, 256),
    "win_arch": (256, 0, 128, 256),
    "win_tall": (384, 0, 128, 256),
    "win_shop": (512, 0, 256, 256),
    "win_industrial": (768, 0, 256, 256),
    "win_round": (1024, 0, 128, 128),
    "win_small": (1024, 128, 128, 128),
    "win_lit": (1152, 0, 128, 256),
    "win_dormer": (1280, 0, 128, 128),
    "win_hall": (1408, 0, 128, 256),
    "door_green": (0, 256, 128, 256),
    "door_plank": (128, 256, 128, 256),
    "door_blue": (256, 256, 128, 256),
    "door_arch": (384, 256, 128, 256),
    "door_red": (512, 256, 128, 256),
    "door_warehouse": (640, 256, 256, 256),
    "door_rollup": (896, 256, 256, 256),
    "shutter_green": (1152, 256, 64, 256),
    "shutter_blue": (1216, 256, 64, 256),
    "shutter_brown": (1280, 256, 64, 256),
    "shutter_red": (1344, 256, 64, 256),
    "sign_emblem": (1536, 0, 256, 256),
    "clock": (1792, 0, 256, 256),
    "sign_north_row": (0, 512, 512, 128),
    "sign_canal": (512, 512, 512, 128),
    "sign_market": (1024, 512, 512, 128),
    "sign_yard": (1536, 512, 512, 128),
    "sign_briarport": (0, 640, 1024, 256),
    "sign_trade": (1024, 640, 1024, 256),
    "grate": (0, 896, 256, 256),
    "manhole": (256, 896, 256, 256),
    "vent": (512, 896, 256, 256),
    "shop_fish": (768, 896, 256, 256),
    "shop_bread": (1024, 896, 256, 256),
    "shop_key": (1280, 896, 256, 256),
    "poster_a": (1536, 896, 256, 512),
    "poster_b": (1792, 896, 256, 512),
    "goods_fruit": (0, 1152, 512, 256),
    "goods_crates": (512, 1152, 512, 256),
    "wood_frame": (1024, 1152, 256, 256),
    "stencil_logo": (1280, 1152, 256, 256),
    "plank_panel": (0, 1408, 512, 512),
    "dark": (512, 1408, 64, 64),
    "glass_plain": (576, 1408, 64, 64),
    "white_paint": (640, 1408, 64, 64),
    "green_paint": (704, 1408, 64, 64),
    "cushion": (768, 1408, 256, 256),
    "tarp_fold": (1024, 1408, 512, 512),
    "rope": (1536, 1408, 512, 128),
    "fishnet": (1536, 1536, 512, 384),
}


def _glass(d, x, y, w, h, cols, rows, frame=(222, 218, 208), glass_top=(92, 120, 140), glass_bot=(34, 44, 52), bar=6, lit=False, arch=False):
    # vertical gradient glass (sky reflection on top)
    for i in range(h):
        t = i / max(h - 1, 1)
        g = tuple(int(glass_top[k] * (1 - t) + glass_bot[k] * t) for k in range(3))
        if lit:
            g = tuple(int(min(255, g[k] * 0.3 + (230, 180, 110)[k] * 0.7)) for k in range(3))
        d.line([(x, y + i), (x + w, y + i)], fill=g)
    # faint curtain on one side
    d.rectangle([x + 2, y + 2, x + w * 0.28, y + h - 2], fill=(150, 140, 124) if not lit else (220, 180, 120))
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=frame, width=bar + 2)
    for c in range(1, cols):
        xx = x + c * w // cols
        d.rectangle([xx - bar // 2, y, xx + bar // 2, y + h], fill=frame)
    for r in range(1, rows):
        yy = y + r * h // rows
        d.rectangle([x, yy - bar // 2, x + w, yy + bar // 2], fill=frame)


def _door_panels(d, x, y, w, h, col, dark, leaves=2, glass=False):
    d.rectangle([x, y, x + w, y + h], fill=col)
    lw = w // leaves
    for L in range(leaves):
        lx = x + L * lw
        d.rectangle([lx + 2, y + 2, lx + lw - 3, y + h - 2], outline=dark, width=4)
        for k in range(3):
            py0 = y + 14 + k * (h - 20) // 3
            if glass and k == 0:
                _glass(d, lx + 12, py0, lw - 24, (h - 20) // 3 - 14, 1, 2, frame=dark, bar=4)
            else:
                d.rectangle([lx + 12, py0, lx + lw - 12, py0 + (h - 20) // 3 - 14], outline=dark, width=3)
                d.rectangle([lx + 16, py0 + 4, lx + lw - 16, py0 + (h - 20) // 3 - 18],
                            fill=tuple(min(255, int(c * 1.08)) for c in col))
    d.ellipse([x + w // 2 - 10, y + h // 2, x + w // 2 - 2, y + h // 2 + 8], fill=(180, 150, 70))


def gen_detail_atlas():
    S = 2048
    img = Image.new("RGB", (S, S), (90, 90, 90))
    rough = Image.new("L", (S, S), 200)
    d = ImageDraw.Draw(img)
    dr = ImageDraw.Draw(rough)
    A = ATLAS

    def R(name):
        return A[name]

    def mark_rough(name, val):
        x, y, w, h = R(name)
        dr.rectangle([x, y, x + w - 1, y + h - 1], fill=val)

    x, y, w, h = R("win_sash"); _glass(d, x, y, w, h, 2, 3); mark_rough("win_sash", 40)
    x, y, w, h = R("win_casement"); _glass(d, x, y, w, h, 2, 4, frame=(44, 70, 52)); mark_rough("win_casement", 40)
    x, y, w, h = R("win_arch"); _glass(d, x, y, w, h, 2, 5, frame=(226, 222, 212)); d.arc([x + 6, y + 6, x + w - 6, y + w - 6], 180, 360, fill=(226, 222, 212), width=5); mark_rough("win_arch", 40)
    x, y, w, h = R("win_tall"); _glass(d, x, y, w, h, 2, 6, frame=(60, 60, 58)); mark_rough("win_tall", 40)
    x, y, w, h = R("win_shop"); _glass(d, x, y, w, h, 3, 2, frame=(52, 64, 54), bar=8, glass_top=(120, 140, 150), glass_bot=(60, 56, 50))
    for k in range(9):  # goods silhouettes behind glass
        gx = x + 20 + k * 25
        d.ellipse([gx, y + h - 70, gx + 20, y + h - 50], fill=[(170, 60, 40), (190, 150, 50), (90, 120, 50)][k % 3])
    mark_rough("win_shop", 50)
    x, y, w, h = R("win_industrial"); _glass(d, x, y, w, h, 6, 6, frame=(52, 56, 58), bar=5, glass_top=(110, 130, 140), glass_bot=(50, 60, 64)); mark_rough("win_industrial", 60)
    x, y, w, h = R("win_round"); d.rectangle([x, y, x + w, y + h], fill=(120, 110, 96)); d.ellipse([x + 4, y + 4, x + w - 4, y + h - 4], fill=(40, 52, 60), outline=(220, 214, 200), width=8)
    d.line([x + w // 2, y + 8, x + w // 2, y + h - 8], fill=(220, 214, 200), width=5); d.line([x + 8, y + h // 2, x + w - 8, y + h // 2], fill=(220, 214, 200), width=5); mark_rough("win_round", 50)
    x, y, w, h = R("win_small"); _glass(d, x, y, w, h, 2, 2); mark_rough("win_small", 40)
    x, y, w, h = R("win_lit"); _glass(d, x, y, w, h, 2, 3, lit=True); mark_rough("win_lit", 40)
    x, y, w, h = R("win_dormer"); _glass(d, x, y, w, h, 2, 2, frame=(230, 226, 214)); mark_rough("win_dormer", 40)
    x, y, w, h = R("win_hall"); _glass(d, x, y, w, h, 3, 7, frame=(70, 70, 66), bar=4); mark_rough("win_hall", 40)
    x, y, w, h = R("door_green"); _door_panels(d, x, y, w, h, (46, 82, 58), (28, 50, 36)); mark_rough("door_green", 150)
    x, y, w, h = R("door_plank"); d.rectangle([x, y, x + w, y + h], fill=(112, 80, 54))
    for k in range(6):
        d.line([x + k * w // 6, y, x + k * w // 6, y + h], fill=(70, 50, 34), width=3)
    for yy in (y + 40, y + h - 40):
        d.rectangle([x + 6, yy - 6, x + w - 6, yy + 6], fill=(50, 50, 50))
        for k in range(5):
            d.ellipse([x + 16 + k * 24 - 3, yy - 3, x + 16 + k * 24 + 3, yy + 3], fill=(120, 120, 120))
    mark_rough("door_plank", 190)
    x, y, w, h = R("door_blue"); _door_panels(d, x, y, w, h, (48, 74, 110), (28, 44, 70), leaves=1, glass=True); mark_rough("door_blue", 150)
    x, y, w, h = R("door_arch"); d.rectangle([x, y, x + w, y + h], fill=(96, 64, 44))
    for k in range(5):
        d.line([x + k * w // 5, y, x + k * w // 5, y + h], fill=(62, 42, 30), width=4)
    d.rectangle([x + 10, y + h // 2 - 40, x + w - 10, y + h // 2 - 30], fill=(40, 40, 40)); mark_rough("door_arch", 190)
    x, y, w, h = R("door_red"); _door_panels(d, x, y, w, h, (128, 36, 34), (80, 20, 22), leaves=2); mark_rough("door_red", 150)
    x, y, w, h = R("door_warehouse"); d.rectangle([x, y, x + w, y + h], fill=(92, 70, 52))
    for k in range(10):
        d.line([x + k * w // 10, y, x + k * w // 10, y + h], fill=(62, 46, 34), width=3)
    for (a, b) in ((0, 1), (1, 2)):
        d.rectangle([x, y + a * h // 2 + 6, x + w, y + a * h // 2 + 18], fill=(70, 54, 40))
        d.line([x + 6, y + a * h // 2 + 18, x + w // 2 - 6, y + b * h // 2 - 6], fill=(70, 54, 40), width=12)
        d.line([x + w // 2 + 6, y + b * h // 2 - 6, x + w - 6, y + a * h // 2 + 18], fill=(70, 54, 40), width=12)
    d.line([x + w // 2, y, x + w // 2, y + h], fill=(40, 30, 22), width=6); mark_rough("door_warehouse", 200)
    x, y, w, h = R("door_rollup"); d.rectangle([x, y, x + w, y + h], fill=(118, 122, 124))
    for k in range(0, h, 12):
        d.line([x, y + k, x + w, y + k], fill=(88, 92, 94), width=3)
    d.rectangle([x, y + h - 20, x + w, y + h], fill=(70, 70, 70)); mark_rough("door_rollup", 120)
    for nm, col in (("shutter_green", (52, 96, 66)), ("shutter_blue", (60, 96, 132)), ("shutter_brown", (110, 76, 50)), ("shutter_red", (136, 50, 44))):
        x, y, w, h = R(nm); d.rectangle([x, y, x + w, y + h], fill=col)
        dk = tuple(int(c * 0.65) for c in col)
        d.rectangle([x, y, x + w - 1, y + h - 1], outline=dk, width=5)
        for k in range(y + 12, y + h - 10, 9):
            d.line([x + 7, k, x + w - 8, k + 3], fill=dk, width=3)
        mark_rough(nm, 160)
    # emblem plaque
    x, y, w, h = R("sign_emblem"); d.rectangle([x, y, x + w, y + h], fill=(120, 110, 96))
    d.ellipse([x + 6, y + 6, x + w - 6, y + h - 6], fill=(142, 24, 32), outline=(196, 152, 70), width=8)
    img_e = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    claw_emblem(ImageDraw.Draw(img_e), w * 2, h * 2.05, w * 2.4, (232, 214, 184, 255))
    img_e = img_e.resize((w, h), Image.LANCZOS)
    img.paste(img_e, (x, y), img_e)
    mark_rough("sign_emblem", 120)
    # clock
    x, y, w, h = R("clock"); d.rectangle([x, y, x + w, y + h], fill=(160, 150, 130))
    d.ellipse([x + 8, y + 8, x + w - 8, y + h - 8], fill=(236, 230, 214), outline=(40, 40, 40), width=10)
    cx, cy = x + w / 2, y + h / 2
    for k in range(12):
        a = k * math.pi / 6
        d.line([cx + math.cos(a) * 95, cy + math.sin(a) * 95, cx + math.cos(a) * 110, cy + math.sin(a) * 110], fill=(30, 30, 30), width=8)
    d.line([cx, cy, cx + 0, cy - 80], fill=(30, 30, 30), width=8); d.line([cx, cy, cx + 55, cy + 20], fill=(30, 30, 30), width=10)
    mark_rough("clock", 90)
    # stencil direction signs (set dressing)
    for nm, text, arrow in (("sign_north_row", "NORTH ROW", ">"), ("sign_canal", "CANAL COURT", "<"),
                            ("sign_market", "MARKET SQUARE", "^"), ("sign_yard", "LOADING YARD", ">")):
        x, y, w, h = R(nm); d.rectangle([x, y, x + w, y + h], fill=(58, 62, 66))
        d.rectangle([x + 4, y + 4, x + w - 5, y + h - 5], outline=(214, 206, 188), width=4)
        f = font(50)
        d.text((x + 24, y + 34), text, font=f, fill=(226, 218, 200))
        ax = x + w - 60
        if arrow == ">":
            d.polygon([(ax, y + 40), (ax + 36, y + 64), (ax, y + 88)], fill=(226, 218, 200))
        elif arrow == "<":
            d.polygon([(ax + 36, y + 40), (ax, y + 64), (ax + 36, y + 88)], fill=(226, 218, 200))
        else:
            d.polygon([(ax, y + 88), (ax + 18, y + 40), (ax + 36, y + 88)], fill=(226, 218, 200))
        mark_rough(nm, 140)
    for nm, lines in (("sign_briarport", ("BRIARPORT", "TRADING CO.")), ("sign_trade", ("TRADE FUELS", "A STRONGER TOMORROW"))):
        x, y, w, h = R(nm); d.rectangle([x, y, x + w, y + h], fill=(64, 58, 52))
        d.rectangle([x + 8, y + 8, x + w - 9, y + h - 9], outline=(200, 170, 110), width=6)
        f1 = font(96); f2 = font(56)
        tw = d.textlength(lines[0], font=f1); d.text((x + (w - tw) / 2, y + 30), lines[0], font=f1, fill=(236, 226, 200))
        tw = d.textlength(lines[1], font=f2); d.text((x + (w - tw) / 2, y + 150), lines[1], font=f2, fill=(200, 170, 110))
        mark_rough(nm, 150)
    # grate / manhole / vent
    x, y, w, h = R("grate"); d.rectangle([x, y, x + w, y + h], fill=(52, 52, 50))
    for k in range(10, w - 10, 20):
        d.rectangle([x + k, y + 16, x + k + 9, y + h - 16], fill=(14, 14, 14))
    d.rectangle([x + 2, y + 2, x + w - 3, y + h - 3], outline=(80, 80, 76), width=6); mark_rough("grate", 110)
    x, y, w, h = R("manhole"); d.rectangle([x, y, x + w, y + h], fill=(120, 116, 110))
    d.ellipse([x + 8, y + 8, x + w - 8, y + h - 8], fill=(62, 60, 58), outline=(40, 40, 40), width=6)
    for k in range(-5, 6):
        d.line([x + w // 2 + k * 18 - 60, y + 40, x + w // 2 + k * 18 + 60, y + h - 40], fill=(48, 46, 44), width=5)
    mark_rough("manhole", 120)
    x, y, w, h = R("vent"); d.rectangle([x, y, x + w, y + h], fill=(90, 92, 90))
    for k in range(y + 20, y + h - 16, 18):
        d.rectangle([x + 16, k, x + w - 16, k + 8], fill=(30, 30, 30))
    mark_rough("vent", 120)
    # shop signs (icons on painted boards)
    for nm, col, icon in (("shop_fish", (46, 82, 110), "fish"), ("shop_bread", (128, 70, 36), "bread"), ("shop_key", (60, 90, 60), "key")):
        x, y, w, h = R(nm); d.rectangle([x, y, x + w, y + h], fill=col)
        d.rectangle([x + 8, y + 8, x + w - 9, y + h - 9], outline=(210, 180, 110), width=6)
        c2 = (232, 214, 184)
        if icon == "fish":
            d.ellipse([x + 50, y + 90, x + 180, y + 166], fill=c2); d.polygon([(x + 170, y + 128), (x + 215, y + 92), (x + 215, y + 164)], fill=c2)
        elif icon == "bread":
            d.ellipse([x + 40, y + 90, x + 216, y + 170], fill=c2)
            for k in range(4):
                d.line([x + 80 + k * 30, y + 100, x + 70 + k * 30, y + 160], fill=col, width=6)
        else:
            d.ellipse([x + 50, y + 90, x + 110, y + 150], outline=c2, width=12); d.rectangle([x + 105, y + 114, x + 210, y + 126], fill=c2)
            d.rectangle([x + 180, y + 126, x + 192, y + 150], fill=c2)
        mark_rough(nm, 150)
    for nm, col, text in (("poster_a", (190, 176, 150), ("FIGHT", "HIGHER", "TOGETHER")), ("poster_b", (140, 40, 36), ("WILD", "HEARTS", "OPEN", "DOORS"))):
        x, y, w, h = R(nm); d.rectangle([x, y, x + w, y + h], fill=col)
        img_e = Image.new("RGBA", (w * 4, w * 4), (0, 0, 0, 0))
        claw_emblem(ImageDraw.Draw(img_e), w * 2, w * 2, w * 2.6, (40, 30, 28, 255) if nm == "poster_a" else (232, 214, 184, 255))
        img_e = img_e.resize((w, w), Image.LANCZOS)
        img.paste(img_e, (x, y + 20), img_e)
        f = font(44)
        for i, t in enumerate(text):
            tw = d.textlength(t, font=f)
            d.text((x + (w - tw) / 2, y + w + 20 + i * 52), t, font=f, fill=(40, 30, 28) if nm == "poster_a" else (232, 214, 184))
        mark_rough(nm, 200)
    # goods (stall counters)
    x, y, w, h = R("goods_fruit"); d.rectangle([x, y, x + w, y + h], fill=(110, 84, 58))
    rr = T.rng(381)
    for k in range(260):
        gx, gy = x + rr.random() * w, y + rr.random() * h
        rad = rr.uniform(9, 16)
        col = [(196, 48, 36), (220, 150, 40), (120, 160, 50), (230, 200, 70), (150, 30, 60)][int(rr.integers(5))]
        d.ellipse([gx - rad, gy - rad, gx + rad, gy + rad], fill=col)
        d.ellipse([gx - rad * 0.4, gy - rad * 0.6, gx, gy - rad * 0.2], fill=tuple(min(255, c + 50) for c in col))
    mark_rough("goods_fruit", 110)
    x, y, w, h = R("goods_crates"); d.rectangle([x, y, x + w, y + h], fill=(120, 94, 64))
    for k in range(0, w, 64):
        d.rectangle([x + k + 2, y + 4, x + k + 60, y + h - 4], outline=(70, 52, 36), width=4)
        d.line([x + k + 2, y + 4, x + k + 60, y + h - 4], fill=(90, 68, 46), width=4)
    mark_rough("goods_crates", 190)
    x, y, w, h = R("wood_frame"); d.rectangle([x, y, x + w, y + h], fill=(120, 96, 70))
    for k in range(0, h, 8):
        d.line([x, y + k, x + w, y + k + 2], fill=(104, 82, 60), width=2)
    mark_rough("wood_frame", 180)
    x, y, w, h = R("stencil_logo"); d.rectangle([x, y, x + w, y + h], fill=(168, 164, 156))
    img_e = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    claw_emblem(ImageDraw.Draw(img_e), w * 2, h * 2, w * 3.0, (52, 50, 48, 235))
    img_e = img_e.resize((w, h), Image.LANCZOS)
    img.paste(img_e, (x, y), img_e)
    mark_rough("stencil_logo", 220)
    x, y, w, h = R("plank_panel"); d.rectangle([x, y, x + w, y + h], fill=(118, 90, 64))
    for k in range(0, h, 51):
        d.line([x, y + k, x + w, y + k], fill=(60, 44, 32), width=4)
    mark_rough("plank_panel", 200)
    for nm, col, rv in (("dark", (22, 22, 22), 230), ("glass_plain", (52, 66, 76), 30), ("white_paint", (226, 222, 212), 150), ("green_paint", (46, 82, 58), 150)):
        x, y, w, h = R(nm); d.rectangle([x, y, x + w - 1, y + h - 1], fill=col); mark_rough(nm, rv)
    x, y, w, h = R("cushion"); d.rectangle([x, y, x + w, y + h], fill=(150, 46, 40))
    for k in range(0, w, 32):
        d.line([x + k, y, x + k, y + h], fill=(120, 34, 30), width=3)
    mark_rough("cushion", 220)
    x, y, w, h = R("tarp_fold"); d.rectangle([x, y, x + w, y + h], fill=(60, 80, 58))
    for k in range(0, w, 40):
        d.line([x + k, y, x + k + 30, y + h], fill=(46, 64, 44), width=6)
    mark_rough("tarp_fold", 220)
    x, y, w, h = R("rope"); d.rectangle([x, y, x + w, y + h], fill=(170, 146, 104))
    for k in range(-h, w, 14):
        d.line([x + k, y + h, x + k + h, y], fill=(130, 108, 74), width=5)
    mark_rough("rope", 230)
    x, y, w, h = R("fishnet"); d.rectangle([x, y, x + w, y + h], fill=(80, 76, 66))
    for k in range(-h, w, 24):
        d.line([x + k, y + h, x + k + h, y], fill=(150, 140, 110), width=2)
        d.line([x + k, y, x + k + h, y + h], fill=(150, 140, 110), width=2)
    mark_rough("fishnet", 230)
    a = np.asarray(img).astype(F32) / 255.0
    n1 = T.fbm(S, S, 16, 4, 391)
    a *= (0.92 + 0.1 * n1[..., None])
    _save("detail_albedo", T.to_u8(a))
    lum = T.blur(a.mean(-1), 1.2)
    nrm = T.height_to_normal(lum, 2.5)
    _save("detail_normal", T.normal_u8(nrm))
    rr_ = np.asarray(rough).astype(F32) / 255.0
    rr_ = np.clip(rr_ + (n1 - 0.5) * 0.08, 0, 1)
    orm = T.orm_u8(np.ones_like(rr_), rr_, 0.0)
    _save("detail_orm", T.downsample(orm.astype(F32), 2).round().astype(np.uint8))
    with open(os.path.join(HERE, "atlas_detail.json"), "w") as fh:
        json.dump({"size": [S, S], "rects": ATLAS}, fh, indent=1)
