"""WILDRUSH character pipeline - step 3 (venv): bake procedural textures in UV space.

usage: python wr_texture.py <fighter_id> <work_dir> <textures_out_dir> [--size 2048]

Every texel of the fur/cloth atlases is mapped back to its bind-pose 3D position and
normal (UV-space rasterisation of bake_*.npz).  Colours, markings, fur strands, cloth
palette regions, seams and AO are evaluated in 3D, so UV seams are invisible.
Outputs (CHARACTER_CONTRACT §4):
  <id>_fur_albedo.png, <id>_fur_normal.png,
  <id>_cloth_mask.png (R primary, G secondary, B accent, A=1; trim = none),
  <id>_cloth_detail.png (greyscale fabric detail x baked AO), <id>_cloth_normal.png,
  <id>_cloth_basecolor.png (default palette composited, used by the GLB material),
  <id>_eye.png, <id>_detail.png
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wr_sdf import perlin3, fbm3, eval_points, Union  # noqa: E402
import wr_anatomy  # noqa: E402
import wr_clothing  # noqa: E402
import wr_fur  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def log(*a):
    print("[wr_texture]", *a, flush=True)


# ----------------------------------------------------------------------------- colour utils
def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def hex_lin(h):
    h = h.lstrip("#")
    return srgb_to_lin(np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]))


def save_rgb(path, lin_rgb, is_data=False):
    a = lin_rgb if is_data else lin_to_srgb(lin_rgb)
    img = (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(img, "RGB").save(path, optimize=True)


def save_rgba(path, rgba):
    img = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(path, optimize=True)


# ----------------------------------------------------------------------------- rasteriser
def rasterize(UVt, size, chunk=4000):
    """UVt: (T,3,2) per-corner UVs.  Returns pixel index arrays (py, px), triangle id, barycentrics."""
    W = H = size
    X = UVt[..., 0] * W - 0.5
    Y = (1.0 - UVt[..., 1]) * H - 0.5
    out_py, out_px, out_t, out_b = [], [], [], []
    nT = len(UVt)
    for s in range(0, nT, chunk):
        e = min(nT, s + chunk)
        x = X[s:e]
        y = Y[s:e]
        x0 = np.clip(np.floor(x.min(1)).astype(np.int64), 0, W - 1)
        x1 = np.clip(np.ceil(x.max(1)).astype(np.int64), 0, W - 1)
        y0 = np.clip(np.floor(y.min(1)).astype(np.int64), 0, H - 1)
        y1 = np.clip(np.ceil(y.max(1)).astype(np.int64), 0, H - 1)
        nx = x1 - x0 + 1
        ny = y1 - y0 + 1
        cnt = nx * ny
        tid = np.repeat(np.arange(e - s), cnt)
        start = np.repeat(np.cumsum(cnt) - cnt, cnt)
        local = np.arange(cnt.sum()) - start
        px = x0[tid] + local % nx[tid]
        py = y0[tid] + local // nx[tid]
        ax, ay = x[tid, 0], y[tid, 0]
        bx, by = x[tid, 1], y[tid, 1]
        cx, cy = x[tid, 2], y[tid, 2]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        ok = np.abs(den) > 1e-12
        den = np.where(ok, den, 1.0)
        w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        w2 = 1.0 - w0 - w1
        eps = -0.02
        inside = ok & (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        out_py.append(py[inside])
        out_px.append(px[inside])
        out_t.append(tid[inside] + s)
        bw = np.stack([w0[inside], w1[inside], w2[inside]], 1)
        bw = np.clip(bw, 0, None)
        bw /= bw.sum(1, keepdims=True)
        out_b.append(bw)
    return np.concatenate(out_py), np.concatenate(out_px), np.concatenate(out_t), np.concatenate(out_b)


def dilate(img, valid, iters=24):
    """Push colours outward from valid texels into the gutters (mip/filter padding)."""
    img = img.copy()
    valid = valid.copy()
    H, W = valid.shape
    for _ in range(iters):
        acc = np.zeros_like(img)
        cnt = np.zeros((H, W))
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sv = np.roll(np.roll(valid, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * sv[..., None]
            cnt += sv
        new = (~valid) & (cnt > 0)
        if not new.any():
            break
        img[new] = acc[new] / cnt[new][:, None]
        valid = valid | new
    img[~valid] = img[valid].mean(axis=0)
    return img


class Bake:
    """Per-texel attributes for one atlas."""

    def __init__(self, path, size):
        d = np.load(path)
        self.V = d["V"]
        self.N = d["N"]
        self.T = d["T"]
        self.UV = d["UV"]
        self.G = d["G"] if "G" in d else None
        self.size = size
        t = time.time()
        py, px, tid, bw = rasterize(self.UV, size)
        self.py, self.px, self.tid, self.bw = py, px, tid, bw
        tri = self.T[tid]
        self.P = (self.V[tri] * bw[..., None]).sum(1)
        n = (self.N[tri] * bw[..., None]).sum(1)
        self.Nrm = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        # tangent frame per triangle (u, v derivatives)
        p0, p1, p2 = self.V[self.T[:, 0]], self.V[self.T[:, 1]], self.V[self.T[:, 2]]
        uv0, uv1, uv2 = self.UV[:, 0], self.UV[:, 1], self.UV[:, 2]
        dp1, dp2 = p1 - p0, p2 - p0
        du1, du2 = uv1 - uv0, uv2 - uv0
        r = du1[:, 0] * du2[:, 1] - du1[:, 1] * du2[:, 0]
        r = np.where(np.abs(r) < 1e-14, 1e-14, r)
        Tg = (dp1 * du2[:, 1:2] - dp2 * du1[:, 1:2]) / r[:, None]
        Bg = (dp2 * du1[:, 0:1] - dp1 * du2[:, 0:1]) / r[:, None]
        Tt = Tg[tid]
        Bt = Bg[tid]
        N = self.Nrm
        Tt = Tt - N * np.einsum("ij,ij->i", Tt, N)[:, None]
        Tt /= np.maximum(np.linalg.norm(Tt, axis=1, keepdims=True), 1e-12)
        sgn = np.sign(np.einsum("ij,ij->i", np.cross(N, Tt), Bt))
        sgn[sgn == 0] = 1.0
        self.Tan = Tt
        self.Bit = np.cross(N, Tt) * sgn[:, None]
        self.valid = np.zeros((size, size), dtype=bool)
        self.valid[py, px] = True
        self.gid = self.G[tid] if self.G is not None else None
        log(f"  rasterised {os.path.basename(path)}: {len(py)} texels, coverage {self.valid.mean():.2f} ({time.time() - t:.1f}s)")

    def image(self, values, iters=24):
        C = values.shape[1]
        img = np.zeros((self.size, self.size, C))
        img[self.py, self.px] = values
        return dilate(img, self.valid, iters)

    def vertex_interp(self, vals):
        tri = self.T[self.tid]
        return (vals[tri] * self.bw[..., None]).sum(1) if vals.ndim == 2 else (vals[tri] * self.bw).sum(1)

    def normal_from_height(self, hfn, strength, eps=0.0006):
        """Tangent-space normal from a 3D height function (continuous across seams)."""
        P, T, B = self.P, self.Tan, self.Bit
        dt = (hfn(P + T * eps) - hfn(P - T * eps)) / (2 * eps)
        db = (hfn(P + B * eps) - hfn(P - B * eps)) / (2 * eps)
        n = np.stack([-strength * dt, -strength * db, np.ones(len(P))], 1)
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        return n * 0.5 + 0.5


def vertex_ao(sdf, V, N, dists=(0.006, 0.014, 0.028, 0.05), strength=1.0):
    occ = np.zeros(len(V))
    wsum = 0.0
    for i, dd in enumerate(dists):
        w = 1.0 / (i + 1)
        d = eval_points(sdf, V + N * dd, cell=0.08, m=0.06)
        occ += w * np.clip((dd - d) / dd, 0, 1)
        wsum += w
    return np.clip(1.0 - strength * occ / wsum, 0.0, 1.0)


# ----------------------------------------------------------------------------- eye / detail
def eye_texture(spec, size=512):
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx + 0.5) / size * 2 - 1
    v = 1 - (yy + 0.5) / size * 2
    r = np.sqrt(u * u + v * v)
    iris_r = spec.get("iris_r", 0.80)
    c_out = hex_lin(spec["iris_outer"])
    c_in = hex_lin(spec["iris_inner"])
    t = np.clip(r / iris_r, 0, 1)
    P = np.stack([u * 6, v * 6, np.zeros_like(u)], -1).reshape(-1, 3)
    ang = np.arctan2(v, u)
    fib = (perlin3(np.stack([np.cos(ang) * 2, np.sin(ang) * 2, r * 14], -1).reshape(-1, 3), 1.0, 3).reshape(size, size))
    col = c_in[None, None] * (1 - t[..., None] ** 1.3) + c_out[None, None] * (t[..., None] ** 1.3)
    col = col * (1 + 0.18 * fib[..., None])
    # limbal ring
    ring = np.clip((r - iris_r * 0.86) / (iris_r * 0.14), 0, 1)
    col = col * (1 - 0.65 * ring[..., None])
    sclera = hex_lin(spec.get("sclera", "#d8d0c4"))
    outside = r > iris_r
    col[outside] = sclera * 0.8
    # pupil
    if spec["pupil"] == "slit":
        pr = np.sqrt((u / spec.get("slit_w", 0.16)) ** 2 + (v / 0.62) ** 2)
    else:
        pr = r / spec.get("pupil_r", 0.34)
    pupil = np.clip((1.0 - pr) / 0.06, 0, 1)
    col = col * (1 - pupil[..., None]) + np.array([0.004, 0.003, 0.003]) * pupil[..., None]
    return col


def detail_texture(spec, size=256):
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx + 0.5) / size
    v = 1 - (yy + 0.5) / size
    col = np.zeros((size, size, 3))
    claw_b, claw_t = hex_lin(spec["claw_base"]), hex_lin(spec["claw_tip"])
    tooth = hex_lin(spec.get("tooth", "#ece4d2"))
    wh = hex_lin(spec.get("whisker", "#f0eee8"))
    t = np.clip(v, 0, 1)[..., None]
    cl = claw_b * (1 - t ** 1.5) + claw_t * t ** 1.5
    th = tooth * (0.85 + 0.15 * t)
    ws = wh * (1 - 0.25 * t)
    col = np.where((u < 0.25)[..., None], cl, np.where((u < 0.5)[..., None], th, ws))
    return col


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fid")
    ap.add_argument("work")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--cloth-size", type=int, default=2048)
    args = ap.parse_args()
    t0 = time.time()
    wdir = os.path.join(args.work, args.fid)
    os.makedirs(args.out, exist_ok=True)
    F = wr_anatomy.fighter(args.fid)
    wr_clothing.build(F)
    fj = json.load(open(os.path.join(REPO, "game", "data", "tuning", "fighters", args.fid + ".json")))
    spec = wr_fur.SPECS[args.fid]
    garment_nodes = [g.node for g in F.garments_obj]
    occluder = Union([F.body] + garment_nodes, k=0.0)
    fid = args.fid

    # ---------------- fur
    fb = Bake(os.path.join(wdir, "bake_fur.npz"), args.size)
    t = time.time()
    ao_v = vertex_ao(occluder, fb.V + fb.N * 0.0015, fb.N)
    ao = fb.vertex_interp(ao_v)
    memb = fb.vertex_interp(wr_fur.memberships(F, fb.V))
    log(f"  AO + part memberships ({time.time() - t:.1f}s)")
    t = time.time()
    albedo, flow = wr_fur.fur_colour(F, spec, fb.P, fb.Nrm, memb)
    hfn = wr_fur.strand_height(F, spec, flow)
    strand = hfn(fb.P)
    albedo = albedo * (1.0 + spec.get("strand_contrast", 0.16) * strand[:, None])
    albedo = albedo * (0.35 + 0.65 * ao[:, None] ** 0.9)
    log(f"  fur colour ({time.time() - t:.1f}s)")
    save_rgb(os.path.join(args.out, f"{fid}_fur_albedo.png"), fb.image(albedo))
    t = time.time()
    nrm = fb.normal_from_height(hfn, strength=spec.get("normal_strength", 0.00045))
    save_rgb(os.path.join(args.out, f"{fid}_fur_normal.png"), fb.image(nrm), is_data=True)
    log(f"  fur normal ({time.time() - t:.1f}s)")

    # ---------------- cloth
    cb = Bake(os.path.join(wdir, "bake_cloth.npz"), args.cloth_size)
    ao_v = vertex_ao(occluder, cb.V + cb.N * 0.0015, cb.N, strength=0.9)
    ao = cb.vertex_interp(ao_v)
    mask = np.zeros((len(cb.P), 3))
    detail = np.ones(len(cb.P))
    hts = []
    for gi, g in enumerate(F.garments_obj):
        sel = cb.gid == gi
        if not np.any(sel):
            continue
        P = cb.P[sel]
        if g.colour is not None:
            mask[sel] = np.clip(g.colour(P), 0, 1)
        # seams / stitches near hems: region value is a distance inside the garment region
        r = g.region(P)
        stitch = wr_fur.stitch_pattern(P, r, g.kind)
        detail[sel] = detail[sel] * (1.0 - 0.28 * stitch)
    fabric = wr_fur.fabric_height(F)
    fh = fabric(cb.P)
    wear = 0.5 + 0.5 * fbm3(cb.P, 6.0, 3, 41)
    detail = detail * (0.90 + 0.10 * fh) * (0.88 + 0.12 * wear)
    detail = detail * (0.30 + 0.70 * ao ** 1.1)
    mask_img = cb.image(mask)
    det_img = cb.image(detail[:, None], iters=24)[..., 0]
    save_rgba(os.path.join(args.out, f"{fid}_cloth_mask.png"),
              np.concatenate([mask_img, np.ones(mask_img.shape[:2] + (1,))], -1))
    save_rgb(os.path.join(args.out, f"{fid}_cloth_detail.png"), np.repeat(det_img[..., None], 3, -1), is_data=True)
    nrm = cb.normal_from_height(lambda P: fabric(P) * 0.35 + wr_fur.seam_height(F, P), strength=0.0011)
    save_rgb(os.path.join(args.out, f"{fid}_cloth_normal.png"), cb.image(nrm), is_data=True)
    pal = fj["palettes"]["default"]
    cols = [hex_lin(pal["primary"]), hex_lin(pal["secondary"]), hex_lin(pal["accent"]), hex_lin(pal["trim"])]
    m = mask_img
    rest = np.clip(1 - m.sum(-1, keepdims=True), 0, 1)
    base = m[..., 0:1] * cols[0] + m[..., 1:2] * cols[1] + m[..., 2:3] * cols[2] + rest * cols[3]
    base = base * det_img[..., None] * 1.25
    save_rgb(os.path.join(args.out, f"{fid}_cloth_basecolor.png"), base)
    log(f"  cloth textures ({time.time() - t:.1f}s)")

    # ---------------- eye / detail
    save_rgb(os.path.join(args.out, f"{fid}_eye.png"), eye_texture(spec["eye"]))
    save_rgb(os.path.join(args.out, f"{fid}_detail.png"), detail_texture(spec["detail"]))
    log(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
