"""Tileable procedural texture primitives (numpy/scipy) for the Briarport environment kit.

Every function is periodic on the texture tile (so outputs tile seamlessly) and deterministic
for a given seed. Arrays are float32 in [0,1] unless noted; shape (H, W) with row 0 at the top
of the image (= v = 1 in Blender UV space).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

F32 = np.float32


# ----------------------------------------------------------------------------- noise
def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def value_noise(h: int, w: int, fy: int, fx: int, seed: int, order: int = 3) -> np.ndarray:
    """Periodic value noise with fy x fx lattice cells over the tile (cubic interpolation)."""
    g = rng(seed).random((fy, fx)).astype(F32)
    out = ndimage.zoom(g, (h / fy, w / fx), order=order, mode="grid-wrap", grid_mode=True)
    out = out[:h, :w]
    lo, hi = out.min(), out.max()
    return ((out - lo) / max(hi - lo, 1e-6)).astype(F32)


def fbm(h: int, w: int, base: int, octaves: int, seed: int, gain: float = 0.5, aspect: float = 1.0) -> np.ndarray:
    """Fractal sum of periodic value noise. base = lattice cells across the width at octave 0.
    aspect scales the vertical cell count (aspect<1 => vertically stretched features)."""
    acc = np.zeros((h, w), F32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        fx = base * (2 ** o)
        fy = max(1, int(round(fx * aspect * h / w)))
        fx = min(fx, w)
        fy = min(fy, h)
        acc += amp * value_noise(h, w, fy, fx, seed + 101 * o)
        tot += amp
        amp *= gain
    acc /= tot
    lo, hi = acc.min(), acc.max()
    return ((acc - lo) / max(hi - lo, 1e-6)).astype(F32)


def spectral_noise(h: int, w: int, beta: float, seed: int, fmin: float = 1.0, fmax: float | None = None) -> np.ndarray:
    """Periodic 1/f^beta noise via FFT, normalised to [0,1]."""
    r = rng(seed)
    wn = r.standard_normal((h, w)).astype(F32)
    F = np.fft.rfft2(wn)
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.rfftfreq(w)[None, :] * w
    f = np.sqrt(fx * fx + fy * fy)
    filt = np.where(f < fmin, 0.0, 1.0 / np.maximum(f, 1e-6) ** (beta / 2.0))
    if fmax is not None:
        filt = np.where(f > fmax, 0.0, filt)
    out = np.fft.irfft2(F * filt, s=(h, w)).astype(F32)
    lo, hi = out.min(), out.max()
    return ((out - lo) / max(hi - lo, 1e-6)).astype(F32)


def streaks(h: int, w: int, seed: int, cover: float = 0.35, base: int = 10) -> np.ndarray:
    """Sparse vertical rain/dirt streaks (0..1), localised by a low-frequency mask."""
    lines = fbm(h, w, base, 3, seed, aspect=0.04)
    lines = smoothstep(0.55, 0.9, lines)
    mask = fbm(h, w, 3, 3, seed + 7)
    mask = smoothstep(1.0 - cover, 1.0 - cover + 0.25, mask)
    fade = fbm(h, w, 6, 2, seed + 9, aspect=0.3)
    return (lines * mask * (0.5 + 0.5 * fade)).astype(F32)


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    return ndimage.gaussian_filter(a, sigma, mode="wrap").astype(F32)


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(F32)


def lerp(a, b, t):
    return a + (b - a) * t


# ----------------------------------------------------------------------------- cells
def rows_of_cells(h: int, w: int, row_heights_px: list, row_widths_px: list, seed: int):
    """Rectangular cells arranged in rows (bricks, flags, setts). Periodic.

    row_heights_px: list of row heights (sum == h).
    row_widths_px: list (per row) of lists of cell widths (each sums to w); a random per-row
    horizontal offset is applied so joints do not align unless offset given as 0.
    Returns dict with cell id, local u/v in [0,1], dist to nearest edge (px), cell size.
    """
    cid = np.zeros((h, w), np.int32)
    lu = np.zeros((h, w), F32)
    lv = np.zeros((h, w), F32)
    edge = np.zeros((h, w), F32)
    cw = np.zeros((h, w), F32)
    ch = np.zeros((h, w), F32)
    xs = np.arange(w)
    y0 = 0
    next_id = 0
    for r, (rh, widths) in enumerate(zip(row_heights_px, row_widths_px)):
        widths, off = widths
        b = np.concatenate([[0], np.cumsum(widths)])
        xx = (xs - off) % w
        k = np.searchsorted(b, xx, side="right") - 1
        k = np.clip(k, 0, len(widths) - 1)
        x_in = xx - b[k]
        wk = np.asarray(widths)[k]
        rows = slice(y0, y0 + rh)
        yy = np.arange(rh)[:, None].astype(F32)
        cid[rows] = (next_id + k)[None, :]
        lu[rows] = ((x_in + 0.5) / wk)[None, :]
        lv[rows] = (yy + 0.5) / rh
        dx = np.minimum(x_in + 0.5, wk - x_in - 0.5)[None, :].astype(F32)
        dy = np.minimum(yy + 0.5, rh - yy - 0.5)
        edge[rows] = np.minimum(dx, dy)
        cw[rows] = wk[None, :]
        ch[rows] = rh
        next_id += len(widths)
        y0 += rh
    return {"id": cid, "u": lu, "v": lv, "edge": edge, "w": cw, "h": ch, "count": next_id}


def split_evenly(total: int, n: int) -> list:
    base = [total // n] * n
    for i in range(total - sum(base)):
        base[i] += 1
    return base


def random_partition(total: int, lo: int, hi: int, r: np.random.Generator) -> list:
    """Random integer widths in [lo,hi] summing exactly to total."""
    parts = []
    s = 0
    while total - s > hi:
        v = int(r.integers(lo, hi + 1))
        if total - s - v < lo and total - s - v != 0:
            v = total - s - lo if total - s - lo >= lo else total - s
        parts.append(v)
        s += v
    if total - s > 0:
        parts.append(total - s)
    # fix a too-small tail by merging
    if len(parts) > 1 and parts[-1] < lo:
        t = parts.pop()
        parts[-1] += t
    return parts


def per_cell(values: np.ndarray, cid: np.ndarray) -> np.ndarray:
    return values[cid]


def voronoi(h: int, w: int, pts01: np.ndarray):
    """Periodic Voronoi. pts01: (N,2) in [0,1)^2 as (x,y). Returns id, F1, F2 (in px)."""
    tree = cKDTree(pts01 * np.array([w, h]), boxsize=[w, h])
    yy, xx = np.mgrid[0:h, 0:w]
    q = np.stack([xx.ravel() + 0.5, yy.ravel() + 0.5], axis=1)
    d, i = tree.query(q, k=2, workers=2)
    return (i[:, 0].reshape(h, w).astype(np.int32), d[:, 0].reshape(h, w).astype(F32),
            d[:, 1].reshape(h, w).astype(F32))


# ----------------------------------------------------------------------------- maps
def height_to_normal(hgt: np.ndarray, strength: float) -> np.ndarray:
    """OpenGL (Y+) tangent-space normal map from a periodic height field (units: px heights * strength)."""
    dx = (np.roll(hgt, -1, axis=1) - np.roll(hgt, 1, axis=1)) * 0.5
    drow = (np.roll(hgt, -1, axis=0) - np.roll(hgt, 1, axis=0)) * 0.5
    nx = -dx * strength
    ny = drow * strength          # image rows go down == -v
    nz = np.ones_like(hgt)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / ln, ny / ln, nz / ln], axis=-1)
    return n


def cavity(hgt: np.ndarray, sigma: float) -> np.ndarray:
    """Positive where the surface is below its neighbourhood (crevices)."""
    return np.clip(blur(hgt, sigma) - hgt, 0.0, None)


def ao_from_height(hgt: np.ndarray, sigmas=(2.0, 6.0, 16.0), strength: float = 2.5) -> np.ndarray:
    occ = np.zeros_like(hgt)
    for s in sigmas:
        occ += cavity(hgt, s)
    occ /= len(sigmas)
    return np.clip(1.0 - occ * strength, 0.0, 1.0).astype(F32)


def colorize(t: np.ndarray, stops: list) -> np.ndarray:
    """Map scalar t in [0,1] through colour stops [(pos, (r,g,b)), ...] (sRGB 0-255)."""
    pos = np.array([s[0] for s in stops], F32)
    cols = np.array([s[1] for s in stops], F32) / 255.0
    out = np.empty(t.shape + (3,), F32)
    for c in range(3):
        out[..., c] = np.interp(t, pos, cols[:, c])
    return out


def rgb(c) -> np.ndarray:
    return np.array(c, F32) / 255.0


def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    if t.ndim == a.ndim - 1:
        t = t[..., None]
    return a + (b - a) * t


def to_u8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def normal_u8(n: np.ndarray) -> np.ndarray:
    return to_u8(n * 0.5 + 0.5)


def orm_u8(ao: np.ndarray, rough: np.ndarray, metal) -> np.ndarray:
    if np.isscalar(metal):
        metal = np.full_like(ao, metal)
    return to_u8(np.stack([ao, rough, metal], axis=-1))


def downsample(a: np.ndarray, f: int) -> np.ndarray:
    h, w = a.shape[:2]
    return a.reshape(h // f, f, w // f, f, *a.shape[2:]).mean(axis=(1, 3))


def combine_normals(n1: np.ndarray, n2: np.ndarray) -> np.ndarray:
    """Whiteout blend of two tangent normals (both unit, z up)."""
    x = n1[..., 0] + n2[..., 0]
    y = n1[..., 1] + n2[..., 1]
    z = n1[..., 2] * n2[..., 2]
    ln = np.sqrt(x * x + y * y + z * z)
    return np.stack([x / ln, y / ln, z / ln], axis=-1)


def disc_mask(h, w, cx, cy, r, soft=1.5):
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2)
    return np.clip((r - d) / soft + 0.5, 0, 1).astype(F32)


def rect_mask(h, w, x0, y0, x1, y1, soft=1.0):
    yy, xx = np.mgrid[0:h, 0:w]
    dx = np.minimum(xx + 0.5 - x0, x1 - xx - 0.5)
    dy = np.minimum(yy + 0.5 - y0, y1 - yy - 0.5)
    return np.clip(np.minimum(dx, dy) / soft + 0.5, 0, 1).astype(F32)
