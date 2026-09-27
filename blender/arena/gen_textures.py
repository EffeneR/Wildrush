#!/usr/bin/env python3
"""Generate the Briarport environment texture set (tileable PBR, 1K-2K PNG).

Run with the project venv:  .venv/bin/python blender/arena/gen_textures.py [--only name,...]
Outputs game/assets/arena/textures/<set>_{albedo,normal,orm}.png (+ a few single maps) and
blender/arena/textures.json (list + sha256). Fixed seeds => byte-identical re-runs.

Conventions: albedo sRGB; normal OpenGL (+Y); ORM = R ambient occlusion, G roughness, B metallic
(glTF metallicRoughness + occlusion packing). World-space texel densities are listed in
TEXEL (metres per UV tile) and used by the Blender builder for UV scaling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texlib as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "game", "assets", "arena", "textures")
F32 = np.float32

# metres covered by one UV tile (u, v) for each tileable set -- consumed by the Blender builder
TEXEL = {
    "brick": (2.0, 2.0), "plaster": (3.0, 3.0), "stone_ashlar": (3.0, 3.0), "stone_trim": (2.0, 2.0),
    "stone_canal": (4.0, 3.0), "roof_terracotta": (2.0, 2.0), "paving_flag": (5.0, 5.0),
    "paving_cobble": (4.0, 4.0), "paving_concrete": (8.0, 8.0), "wood_planks": (2.0, 2.0),
    "metal_deck": (1.5, 1.5), "iron": (1.0, 1.0), "paint_yellow": (2.0, 2.0), "container": (2.6, 2.6),
    "hazard": (1.0, 1.0), "canvas": (2.0, 2.0), "concrete": (2.0, 2.0), "soil": (1.0, 1.0),
    "bronze": (1.0, 1.0), "bark": (1.0, 2.0), "water": (6.0, 6.0), "skyline": (24.0, 12.0),
    "roof_metal": (2.0, 2.0),
}

WRITTEN: list = []


def save(name: str, arr: np.ndarray, mode: str | None = None) -> None:
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name + ".png")
    img = Image.fromarray(arr, mode) if mode else Image.fromarray(arr)
    img.save(p, optimize=False, compress_level=6)
    WRITTEN.append(p)


def save_set(name: str, albedo, normal=None, orm=None, orm_half: bool = True, normal_half: bool = False):
    save(name + "_albedo", T.to_u8(albedo) if albedo.dtype != np.uint8 else albedo)
    if normal is not None:
        if normal_half:
            normal = T.downsample(normal, 2)
            normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
        save(name + "_normal", T.normal_u8(normal))
    if orm is not None:
        if orm_half:
            orm = T.downsample(orm.astype(F32), 2).round().astype(np.uint8)
        save(name + "_orm", orm)


def pick(r, palette, weights, n):
    w = np.asarray(weights, F32)
    idx = r.choice(len(palette), size=n, p=w / w.sum())
    return np.asarray(palette, F32)[idx] / 255.0


# =============================================================================== BRICK
def gen_brick():
    S = 1024
    r = T.rng(11)
    rows = T.split_evenly(S, 24)
    layout = []
    for i, rh in enumerate(rows):
        widths = [128] * 8
        off = (64 if i % 2 else 0) + int(r.integers(-6, 7))
        layout.append((widths, off))
    c = T.rows_of_cells(S, S, rows, layout, seed=11)
    n = c["count"]
    grain = T.fbm(S, S, 16, 5, 12)
    fine = T.spectral_noise(S, S, 1.0, 13)
    mort_noise = T.fbm(S, S, 64, 3, 14)
    mortar = T.smoothstep(2.2, 3.6, c["edge"] + (mort_noise - 0.5) * 2.0)
    # chipped edges
    chip = T.fbm(S, S, 48, 4, 15)
    bevel = T.smoothstep(2.0, 7.0, c["edge"] + (chip - 0.5) * 5.0)
    per_h = T.rng(16).random(n).astype(F32)
    tilt = (T.per_cell(per_h, c["id"]) - 0.5) * 0.15
    hgt = mortar * (0.55 + 0.45 * bevel) + (grain - 0.5) * 0.08 + (fine - 0.5) * 0.05 + tilt * mortar
    hgt += (1 - mortar) * (mort_noise - 0.5) * 0.1
    nrm = T.height_to_normal(hgt, 3.2)
    ao = T.ao_from_height(hgt, strength=2.2)
    face = mortar
    grime = T.fbm(S, S, 3, 5, 17)
    streak = T.streaks(S, S, 18, cover=0.3)
    rough = np.clip(0.80 + (grain - 0.5) * 0.12 + (1 - face) * 0.12, 0, 1)
    orm = T.orm_u8(ao, rough, 0.0)
    for variant, pal, wts, mcol, seed in (
        ("brick_red",
         [(152, 66, 48), (166, 76, 54), (141, 60, 45), (176, 90, 62), (128, 54, 42), (186, 104, 72),
          (98, 46, 38), (112, 54, 43), (178, 124, 98)],
         [5, 5, 4, 3, 3, 2, 1.2, 1.2, 0.6], (184, 174, 158), 21),
        ("brick_brown",
         [(124, 68, 52), (110, 60, 50), (138, 80, 60), (96, 54, 46), (150, 94, 70), (84, 50, 44),
          (130, 100, 80)],
         [5, 5, 3, 3, 2, 1.5, 0.6], (150, 142, 128), 22),
    ):
        rr = T.rng(seed)
        cols = pick(rr, pal, wts, n) * rr.uniform(0.9, 1.08, (n, 1)).astype(F32)
        base = cols[c["id"]]
        # brick face mottling + darker burnt edges
        base = base * (0.86 + 0.22 * grain[..., None]) * (0.94 + 0.1 * fine[..., None])
        base *= (0.85 + 0.15 * bevel)[..., None]
        mort = T.rgb(mcol) * (0.85 + 0.25 * mort_noise[..., None])
        alb = T.mix(mort, base, face)
        alb *= (0.88 + 0.14 * grime[..., None])
        alb *= (1.0 - 0.12 * streak)[..., None]
        # efflorescence specks (fine, sparse)
        eff = T.smoothstep(0.82, 0.95, T.fbm(S, S, 40, 3, seed + 5)) * 0.18 * T.smoothstep(0.5, 0.8, grime)
        alb = T.mix(alb, np.ones_like(alb) * T.rgb((205, 200, 190)), eff)
        alb *= (0.55 + 0.45 * ao[..., None])
        save(variant + "_albedo", T.to_u8(alb))
    save("brick_normal", T.normal_u8(nrm))
    save("brick_orm", T.downsample(orm.astype(F32), 2).round().astype(np.uint8))


# =============================================================================== PLASTER
def gen_plaster():
    S = 1024
    trowel = T.fbm(S, S, 6, 6, 31, gain=0.55)
    grain = T.spectral_noise(S, S, 0.6, 32)
    patches = T.fbm(S, S, 4, 4, 33)
    # small spalled patch revealing brick (subtle, one per tile)
    spall = T.smoothstep(0.86, 0.89, T.fbm(S, S, 2, 5, 34) * 0.7 + T.fbm(S, S, 16, 3, 35) * 0.3)
    hgt = trowel * 0.5 + grain * 0.15 - spall * 0.6
    nrm = T.height_to_normal(hgt, 2.0)
    ao = T.ao_from_height(hgt, strength=1.5)
    streak = T.streaks(S, S, 36, cover=0.35)
    rough = np.clip(0.86 + (grain - 0.5) * 0.1, 0, 1)
    save("plaster_normal", T.normal_u8(nrm))
    save("plaster_orm", T.downsample(T.orm_u8(ao, rough, 0.0).astype(F32), 2).round().astype(np.uint8))
    # brick pattern for spall area
    yy, xx = np.mgrid[0:S, 0:S]
    course = (yy // 28) % 2
    bx = ((xx + course * 42) % 84) < 80
    by = (yy % 28) < 25
    brick = (bx & by).astype(F32)
    for name, col, seed in (("plaster_cream", (228, 214, 186), 41), ("plaster_ochre", (214, 172, 110), 42),
                            ("plaster_rose", (206, 146, 118), 43), ("plaster_white", (222, 222, 214), 44)):
        base = T.rgb(col)[None, None, :] * np.ones((S, S, 1), F32)
        tint = T.fbm(S, S, 3, 4, seed)
        base = base * (0.9 + 0.14 * tint[..., None]) * (0.95 + 0.07 * trowel[..., None])
        base *= (1.0 - 0.10 * streak)[..., None]
        base *= (0.92 + 0.08 * patches[..., None])
        bcol = T.mix(np.ones_like(base) * T.rgb((150, 78, 58)), np.ones_like(base) * T.rgb((170, 160, 145)), 1 - brick)
        alb = T.mix(base, bcol, spall)
        alb *= ao[..., None] ** 0.6
        save(name + "_albedo", T.to_u8(alb))


# =============================================================================== STONE ASHLAR
def gen_stone_ashlar():
    S = 1024
    r = T.rng(51)
    rows = T.split_evenly(S, 8)                       # 0.375 m courses
    layout = [(T.random_partition(S, 200, 400, r), int(r.integers(0, S))) for _ in rows]
    c = T.rows_of_cells(S, S, rows, layout, 51)
    n = c["count"]
    chisel = T.fbm(S, S, 32, 4, 52)
    scratch = T.fbm(S, S, 64, 3, 53, aspect=0.2)
    big = T.fbm(S, S, 3, 5, 54)
    joint_n = T.fbm(S, S, 40, 3, 55)
    joint = T.smoothstep(1.5, 3.5, c["edge"] + (joint_n - 0.5) * 2)
    bevel = T.smoothstep(2.0, 9.0, c["edge"] + (chisel - 0.5) * 4)
    ptilt = T.rng(56).random((n, 2)).astype(F32) - 0.5
    tilt = ptilt[c["id"], 0] * (c["u"] - 0.5) * 0.3 + ptilt[c["id"], 1] * (c["v"] - 0.5) * 0.3
    hgt = joint * (0.6 + 0.4 * bevel) + (chisel - 0.5) * 0.12 + (scratch - 0.5) * 0.05 + tilt * joint
    nrm = T.height_to_normal(hgt, 3.0)
    ao = T.ao_from_height(hgt, strength=2.0)
    pal = [(206, 194, 170), (196, 184, 160), (214, 204, 182), (186, 176, 156), (200, 186, 158), (176, 168, 152)]
    cols = pick(T.rng(57), pal, [4, 4, 3, 2, 2, 1], n) * T.rng(58).uniform(0.94, 1.05, (n, 1)).astype(F32)
    base = cols[c["id"]] * (0.9 + 0.12 * chisel[..., None]) * (0.9 + 0.14 * big[..., None])
    streak = T.streaks(S, S, 59, cover=0.3)
    base *= (1.0 - 0.12 * streak)[..., None]
    jcol = np.ones_like(base) * T.rgb((168, 158, 140))
    alb = T.mix(jcol, base, joint) * ao[..., None] ** 0.6
    rough = np.clip(0.78 + (chisel - 0.5) * 0.14, 0, 1)
    save_set("stone_ashlar", alb, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== STONE TRIM
def gen_stone_trim():
    S = 1024
    fine = T.fbm(S, S, 24, 5, 61)
    big = T.fbm(S, S, 3, 4, 62)
    pits = T.smoothstep(0.82, 0.9, T.spectral_noise(S, S, 0.3, 63))
    hgt = fine * 0.3 - pits * 0.3
    nrm = T.height_to_normal(hgt, 1.6)
    ao = T.ao_from_height(hgt, strength=1.2)
    base = T.rgb((216, 206, 186)) * np.ones((S, S, 1), F32)
    base = base * (0.9 + 0.1 * fine[..., None]) * (0.9 + 0.12 * big[..., None])
    streak = T.streaks(S, S, 64, cover=0.25)
    base *= (1.0 - 0.06 * streak)[..., None]
    base *= (1.0 - 0.25 * pits)[..., None]
    rough = np.clip(0.7 + (fine - 0.5) * 0.1, 0, 1)
    save_set("stone_trim", base * ao[..., None] ** 0.5, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== CANAL STONE
def gen_stone_canal():
    W, H = 1024, 768                                  # 4 m x 3 m, v=0 at y=-3, v=1 at y=0
    r = T.rng(71)
    rows = T.split_evenly(H, 6)
    layout = [(T.random_partition(W, 180, 400, r), int(r.integers(0, W))) for _ in rows]
    c = T.rows_of_cells(H, W, rows, layout, 71)
    n = c["count"]
    rough_s = T.fbm(H, W, 16, 5, 72)
    joint = T.smoothstep(1.5, 3.0, c["edge"] + (T.fbm(H, W, 32, 3, 73) - 0.5) * 2)
    bevel = T.smoothstep(2.0, 10.0, c["edge"] + (rough_s - 0.5) * 6)
    hgt = joint * (0.55 + 0.45 * bevel) + (rough_s - 0.5) * 0.2
    nrm = T.height_to_normal(hgt, 3.0)
    ao = T.ao_from_height(hgt, strength=2.0)
    pal = [(132, 124, 110), (118, 112, 102), (140, 130, 114), (110, 104, 96), (126, 116, 100)]
    cols = pick(T.rng(74), pal, [3, 3, 2, 2, 2], n)
    base = cols[c["id"]] * (0.85 + 0.2 * rough_s[..., None])
    yy = (np.arange(H)[:, None] / H).astype(F32) * np.ones((1, W), F32)   # 0 top (y=0) .. 1 bottom (y=-3)
    wl = 1.0 / 3.0                                     # waterline row fraction (y=-1)
    drip = T.fbm(H, W, 24, 4, 75, aspect=0.05)
    wet = T.smoothstep(wl - 0.06, wl + 0.02, yy + (drip - 0.5) * 0.08)
    algae = np.exp(-((yy - (wl + 0.03)) / 0.06) ** 2) * (0.6 + 0.4 * T.fbm(H, W, 20, 4, 76))
    base = base * (1.0 - 0.45 * wet[..., None])
    base = T.mix(base, np.ones_like(base) * T.rgb((64, 78, 44)), np.clip(algae * 0.85, 0, 1))
    base = T.mix(base, np.ones_like(base) * T.rgb((56, 60, 44)), np.clip(wet * 0.35 * T.fbm(H, W, 8, 4, 77), 0, 1))
    streaks = T.streaks(H, W, 78, cover=0.4) * (1 - wet) * 0.22
    base *= (1.0 - streaks)[..., None]
    jcol = np.ones_like(base) * T.rgb((92, 88, 78))
    alb = T.mix(jcol * (1 - 0.4 * wet[..., None]), base, joint) * ao[..., None] ** 0.6
    rough = np.clip(0.85 - 0.45 * wet - 0.2 * algae + (rough_s - 0.5) * 0.1, 0.2, 1)
    save_set("stone_canal", alb, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== ROOF TILES
def gen_roof_terracotta():
    S = 1024
    cols_n, rows_n = 8, 8
    tw, th = S // cols_n, S // rows_n
    yy, xx = np.mgrid[0:S, 0:S].astype(F32)
    r = T.rng(81)
    jit = T.fbm(S, S, 16, 3, 82)
    row = (yy // th).astype(np.int32)
    vloc = (yy % th) / th                               # 0 top of course .. 1 lower edge
    xoff = r.integers(-5, 6, rows_n)[row]
    xl = (xx + xoff) % S
    col = (xl // tw).astype(np.int32)
    uloc = (xl % tw) / tw
    tid = row * cols_n + col
    # pantile-like wave: convex caps alternate with channels
    prof = 0.5 - 0.5 * np.cos(2 * np.pi * uloc)
    lower = T.smoothstep(0.86, 0.99, vloc + (jit - 0.5) * 0.04)
    hgt = 0.55 * prof + 0.35 * vloc - 0.6 * lower + (jit - 0.5) * 0.05
    hgt += (T.fbm(S, S, 48, 3, 83) - 0.5) * 0.05
    nrm = T.height_to_normal(hgt, 3.5)
    ao = T.ao_from_height(hgt, strength=2.2)
    pal = [(186, 94, 60), (172, 84, 54), (198, 108, 70), (158, 76, 50), (146, 68, 46), (206, 124, 84), (176, 100, 70)]
    tc = pick(T.rng(84), pal, [5, 4, 3, 3, 2, 1.5, 2], rows_n * cols_n) * T.rng(85).uniform(0.9, 1.08, (rows_n * cols_n, 1)).astype(F32)
    base = tc[tid] * (0.86 + 0.2 * T.fbm(S, S, 24, 4, 86)[..., None])
    base *= (0.78 + 0.22 * prof)[..., None]           # darker channels (dirt)
    lichen = T.smoothstep(0.8, 0.88, T.fbm(S, S, 20, 4, 87)) * 0.6
    base = T.mix(base, np.ones_like(base) * T.rgb((170, 168, 130)), lichen)
    moss = T.smoothstep(0.7, 0.85, T.fbm(S, S, 12, 4, 88)) * lower * 0.7
    base = T.mix(base, np.ones_like(base) * T.rgb((78, 84, 46)), moss)
    alb = base * ao[..., None] ** 0.7
    rough = np.clip(0.74 + (jit - 0.5) * 0.1 + lichen * 0.15, 0, 1)
    save_set("roof_terracotta", alb, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== FLAGSTONES
def gen_paving_flag():
    S = 2048                                          # 5 m -> 410 px/m
    r = T.rng(91)
    rows = T.random_partition(S, 205, 330, r)
    layout = [(T.random_partition(S, 240, 540, r), int(r.integers(0, S))) for _ in rows]
    c = T.rows_of_cells(S, S, rows, layout, 91)
    n = c["count"]
    grain = T.fbm(S, S, 24, 6, 92)
    big = T.fbm(S, S, 3, 5, 93)
    jn = T.fbm(S, S, 64, 3, 94)
    joint = T.smoothstep(2.0, 4.0, c["edge"] + (jn - 0.5) * 3.0)
    chip = T.fbm(S, S, 40, 4, 95)
    bevel = T.smoothstep(2.0, 12.0, c["edge"] + (chip - 0.5) * 8.0)
    pt = T.rng(96).random((n, 3)).astype(F32) - 0.5
    tilt = pt[c["id"], 0] * (c["u"] - 0.5) * 0.35 + pt[c["id"], 1] * (c["v"] - 0.5) * 0.35 + pt[c["id"], 2] * 0.1
    pits = T.smoothstep(0.84, 0.92, T.spectral_noise(S, S, 0.4, 97))
    # cracks in a few slabs: Voronoi edge lines masked per slab
    vp = T.rng(98).random((60, 2))
    _, f1, f2 = T.voronoi(S, S, vp)
    crack_line = 1.0 - T.smoothstep(0.0, 1.8, f2 - f1)
    crack_sel = (T.rng(99).random(n) < 0.18).astype(F32)[c["id"]]
    crack = crack_line * crack_sel * T.smoothstep(0.35, 0.6, T.fbm(S, S, 6, 3, 100))
    hgt = joint * (0.55 + 0.45 * bevel) + tilt * joint + (grain - 0.5) * 0.10 - pits * 0.12 - crack * 0.25
    nrm = T.height_to_normal(hgt, 3.0)
    ao = T.ao_from_height(hgt, sigmas=(2, 6, 18), strength=2.4)
    pal = [(182, 172, 154), (170, 162, 148), (192, 181, 160), (156, 150, 140), (176, 164, 142), (164, 154, 136),
           (196, 188, 170), (150, 142, 128)]
    cols = pick(T.rng(101), pal, [5, 5, 4, 3, 3, 3, 2, 2], n) * T.rng(102).uniform(0.92, 1.06, (n, 1)).astype(F32)
    base = cols[c["id"]] * (0.86 + 0.18 * grain[..., None]) * (0.9 + 0.12 * big[..., None])
    wear = T.smoothstep(0.1, 0.45, np.minimum(np.minimum(c["u"], 1 - c["u"]), np.minimum(c["v"], 1 - c["v"])))
    base *= (0.94 + 0.08 * wear)[..., None]
    base *= (1.0 - 0.3 * pits - 0.5 * crack)[..., None]
    jcol = T.rgb((78, 72, 62)) * (0.8 + 0.4 * jn[..., None])
    moss = T.smoothstep(0.62, 0.8, T.fbm(S, S, 10, 4, 103)) * (1 - joint)
    jcol = T.mix(jcol, np.ones_like(jcol) * T.rgb((74, 88, 50)), moss * 0.8)
    alb = T.mix(jcol, base, joint)
    dirt = T.smoothstep(0.55, 0.8, T.fbm(S, S, 5, 5, 104))
    alb *= (1.0 - 0.12 * dirt)[..., None]
    alb *= ao[..., None] ** 0.55
    rough = np.clip(0.72 + (grain - 0.5) * 0.14 - 0.08 * wear + (1 - joint) * 0.2, 0, 1)
    save_set("paving_flag", alb, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== COBBLE SETTS
def gen_paving_cobble():
    S = 2048                                          # 4 m -> 512 px/m
    r = T.rng(111)
    rows = T.split_evenly(S, 40)                      # 0.1 m courses
    layout = [(T.random_partition(S, 66, 118, r), int(r.integers(0, S))) for _ in rows]
    c = T.rows_of_cells(S, S, rows, layout, 111)
    n = c["count"]
    grain = T.fbm(S, S, 48, 5, 112)
    jn = T.fbm(S, S, 96, 3, 113)
    gap = T.smoothstep(2.5, 5.5, c["edge"] + (jn - 0.5) * 3.0)
    uu, vv = c["u"] * 2 - 1, c["v"] * 2 - 1
    dome = np.sqrt(np.clip(1 - np.abs(uu) ** 4, 0, 1)) * np.sqrt(np.clip(1 - np.abs(vv) ** 4, 0, 1))
    ph = T.rng(114).random((n, 3)).astype(F32) - 0.5
    hgt = gap * (0.45 + 0.45 * dome + ph[c["id"], 0] * 0.15 + ph[c["id"], 1] * uu * 0.08) + (grain - 0.5) * 0.08
    nrm = T.height_to_normal(hgt, 3.4)
    ao = T.ao_from_height(hgt, sigmas=(2, 5, 12), strength=2.6)
    pal = [(132, 128, 124), (114, 112, 110), (146, 140, 132), (124, 114, 110), (104, 108, 114), (88, 88, 88),
           (156, 146, 134)]
    cols = pick(T.rng(115), pal, [5, 5, 3, 3, 2, 2, 1.5], n) * T.rng(116).uniform(0.9, 1.08, (n, 1)).astype(F32)
    speck = T.smoothstep(0.7, 0.9, T.spectral_noise(S, S, 0.0, 117))
    base = cols[c["id"]] * (0.88 + 0.18 * grain[..., None]) * (1 - 0.15 * speck[..., None] + 0.1 * dome[..., None])
    jcol = T.rgb((96, 86, 72)) * (0.75 + 0.45 * jn[..., None])
    alb = T.mix(jcol, base, gap)
    alb *= (0.9 + 0.12 * T.fbm(S, S, 4, 5, 118))[..., None]
    alb *= ao[..., None] ** 0.55
    rough = np.clip(0.62 - 0.12 * dome + (grain - 0.5) * 0.1 + (1 - gap) * 0.35, 0, 1)
    save_set("paving_cobble", alb, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== CONCRETE PAVING (yard)
def gen_paving_concrete():
    S = 2048                                          # 8 m -> 256 px/m ; 2 m slabs
    k = 4
    rows = T.split_evenly(S, k)
    layout = [([S // k] * k, 0) for _ in rows]
    c = T.rows_of_cells(S, S, rows, layout, 121)
    n = c["count"]
    grain = T.fbm(S, S, 32, 6, 122)
    agg = T.smoothstep(0.75, 0.9, T.spectral_noise(S, S, 0.0, 123))
    joint = T.smoothstep(1.5, 3.0, c["edge"])
    vp = T.rng(124).random((24, 2))
    _, f1, f2 = T.voronoi(S, S, vp)
    crack = (1.0 - T.smoothstep(0.0, 1.6, f2 - f1)) * T.smoothstep(0.55, 0.7, T.fbm(S, S, 4, 4, 125))
    pt = T.rng(126).random((n, 2)).astype(F32) - 0.5
    tilt = pt[c["id"], 0] * (c["u"] - 0.5) * 0.2 + pt[c["id"], 1] * (c["v"] - 0.5) * 0.2
    hgt = joint * (0.7 + tilt) + (grain - 0.5) * 0.08 - agg * 0.03 - crack * 0.3
    nrm = T.height_to_normal(hgt, 2.5)
    ao = T.ao_from_height(hgt, strength=1.8)
    tone = T.rng(127).uniform(0.9, 1.08, n).astype(F32)[c["id"]]
    base = T.rgb((156, 154, 148)) * np.ones((S, S, 1), F32) * tone[..., None]
    base *= (0.86 + 0.18 * grain[..., None])
    base = T.mix(base, np.ones_like(base) * T.rgb((120, 118, 114)), agg * 0.5)
    oil = T.smoothstep(0.74, 0.86, T.fbm(S, S, 6, 5, 128))
    base = T.mix(base, np.ones_like(base) * T.rgb((64, 62, 60)), oil * 0.7)
    rust = T.smoothstep(0.8, 0.9, T.fbm(S, S, 8, 4, 129))
    base = T.mix(base, np.ones_like(base) * T.rgb((136, 92, 62)), rust * 0.4)
    tyre = T.smoothstep(0.62, 0.8, T.fbm(S, S, 40, 3, 130, aspect=0.03)) * T.smoothstep(0.4, 0.7, T.fbm(S, S, 3, 3, 131))
    base *= (1 - 0.18 * tyre)[..., None]
    base *= (1 - 0.5 * crack)[..., None]
    alb = T.mix(T.rgb((70, 68, 64)) * np.ones_like(base), base, joint) * ao[..., None] ** 0.5
    rough = np.clip(0.86 + (grain - 0.5) * 0.1 - oil * 0.45, 0, 1)
    save_set("paving_concrete", alb, nrm, T.orm_u8(ao, rough, 0.0))


# =============================================================================== WOOD PLANKS
def gen_wood_planks():
    S = 1024                                          # 2 m ; planks run along u, 0.2 m wide
    r = T.rng(141)
    rows = T.split_evenly(S, 10)
    layout = [(T.random_partition(S, 380, 1024, r), int(r.integers(0, S))) for _ in rows]
    c = T.rows_of_cells(S, S, rows, layout, 141)
    n = c["count"]
    fib = T.fbm(S, S, 96, 4, 142, aspect=0.02)
    ring = 0.5 + 0.5 * np.sin((c["v"] * 6.0 + T.fbm(S, S, 8, 3, 143, aspect=0.1) * 9.0 + T.per_cell(T.rng(144).random(n).astype(F32) * 10, c["id"])) * np.pi)
    gap = T.smoothstep(1.2, 3.2, c["edge"])
    # knots
    kn = np.zeros((S, S), F32)
    kr = T.rng(145)
    for _ in range(9):
        kx, ky, rad = kr.random() * S, kr.random() * S, kr.uniform(6, 14)
        for dx in (-S, 0, S):
            for dy in (-S, 0, S):
                kn = np.maximum(kn, T.disc_mask(S, S, kx + dx, ky + dy, rad, soft=4.0))
    # nail heads near butt ends
    nails = np.zeros((S, S), F32)
    endd = np.minimum(c["u"] * c["w"], (1 - c["u"]) * c["w"])
    nail_band = (endd > 10) & (endd < 16)
    vv = c["v"]
    nails = (nail_band & ((np.abs(vv - 0.25) < 0.05) | (np.abs(vv - 0.75) < 0.05))).astype(F32)
    nails = T.blur(nails, 0.8)
    pt = T.rng(146).random(n).astype(F32) - 0.5
    hgt = gap * (0.7 + pt[c["id"]] * 0.1) + (fib - 0.5) * 0.12 + ring * 0.03 - kn * 0.05 + nails * 0.05
    nrm = T.height_to_normal(hgt, 3.0)
    ao = T.ao_from_height(hgt, strength=2.2)
    pal = [(134, 106, 78), (118, 94, 70), (148, 120, 88), (108, 86, 66), (126, 112, 96), (140, 128, 110)]
    cols = pick(T.rng(147), pal, [4, 4, 3, 3, 2, 2], n) * T.rng(148).uniform(0.9, 1.08, (n, 1)).astype(F32)
    base = cols[c["id"]] * (0.8 + 0.3 * fib[..., None]) * (0.92 + 0.1 * ring[..., None])
    base = T.mix(base, np.ones_like(base) * T.rgb((70, 50, 36)), kn * 0.7)
    base = T.mix(base, np.ones_like(base) * T.rgb((50, 48, 46)), nails * 0.9)
    weather = T.fbm(S, S, 4, 4, 149)
    base = T.mix(base, np.ones_like(base) * T.rgb((142, 136, 126)), weather * 0.25)
    alb = T.mix(T.rgb((34, 28, 24)) * np.ones_like(base), base, gap) * ao[..., None] ** 0.5
    rough = np.clip(0.8 + (fib - 0.5) * 0.12 - nails * 0.3, 0, 1)
    save_set("wood_planks", alb, nrm, T.orm_u8(ao, rough, np.clip(nails, 0, 1) * 0.8))


GENERATORS = {
    "brick": gen_brick, "plaster": gen_plaster, "stone_ashlar": gen_stone_ashlar, "stone_trim": gen_stone_trim,
    "stone_canal": gen_stone_canal, "roof_terracotta": gen_roof_terracotta, "paving_flag": gen_paving_flag,
    "paving_cobble": gen_paving_cobble, "paving_concrete": gen_paving_concrete, "wood_planks": gen_wood_planks,
}

try:  # second half of the generators (props, cloth, foliage, atlas)
    import gen_textures_b as _B  # noqa: E402
    _B.register(GENERATORS, save, save_set, pick)
except ImportError as _e:  # pragma: no cover
    if "gen_textures_b" not in str(_e):
        raise


def sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated generator names")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(GENERATORS))
        return 0
    names = [s for s in a.only.split(",") if s] or list(GENERATORS)
    for nm in names:
        if nm not in GENERATORS:
            print("unknown generator", nm)
            return 2
    for nm in names:
        t0 = time.time()
        GENERATORS[nm]()
        print(f"[tex] {nm:18s} {time.time() - t0:6.1f}s", flush=True)
    if not a.only:
        # full run: write the manifest of every texture file present
        files = sorted(f for f in os.listdir(OUT) if f.endswith(".png"))
        man = {"generator": "blender/arena/gen_textures.py", "texel_m_per_tile": TEXEL, "files": []}
        for f in files:
            p = os.path.join(OUT, f)
            with Image.open(p) as im:
                size = im.size
                mode = im.mode
            man["files"].append({"file": f, "size": list(size), "mode": mode, "sha256": sha256(p)})
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures.json"), "w") as fh:
            json.dump(man, fh, indent=1)
        print(f"[tex] wrote {len(files)} textures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
