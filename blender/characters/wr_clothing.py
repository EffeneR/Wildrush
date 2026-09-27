"""WILDRUSH character pipeline - clothing as SDF offset shells (venv).

Each garment = |base(P) - offset(P)| - thickness/2, minus fold displacement,
intersected (smooth) with a region mask.  base = smoothed clothing proxy that
encloses the body.  Region masks are signed fields (negative inside) built from
planes, bands along limb segments and simple solids.  The same masks drive:
  * which body faces are hidden (deleted) under clothing,
  * palette-region colouring of the cloth mask texture (wr_texture.py).
Spec §6 + REFERENCE_AUDIT B8-B11 (non-sexualised, soft pads, Vex copper on the
anatomical right shoulder only).
"""
import math
import numpy as np
from wr_sdf import (Func, Union, Subtract, Intersect, Ellipsoid, RoundCone, RoundBox, Sphere, Torus,
                    HalfSpace, Shell, v3, normalize, perlin3, fbm3, smax, smin, rot_x, rot_y, rot_z,
                    frame_from_axis, dot_rows)
from wr_anatomy import Frame, LEFT, UP, FWD, BACK, seg_frame

# ----------------------------------------------------------------------------- mask algebra
def m_and(*ms):
    def f(P):
        d = ms[0](P)
        for m in ms[1:]:
            d = np.maximum(d, m(P))
        return d
    return f


def m_or(*ms):
    def f(P):
        d = ms[0](P)
        for m in ms[1:]:
            d = np.minimum(d, m(P))
        return d
    return f


def m_not(m):
    return lambda P: -m(P)


def m_plane(p0, n):
    p0 = v3(p0)
    n = normalize(n)
    return lambda P: (P - p0) @ n


def m_zband(z0, z1):
    return lambda P: np.maximum(z0 - P[:, 2], P[:, 2] - z1)


def seg_t(P, a, b):
    ab = b - a
    L2 = ab @ ab
    return ((P - a) @ ab) / L2, math.sqrt(L2)


def m_seg(a, b, t0, t1):
    a, b = v3(a), v3(b)

    def f(P):
        t, L = seg_t(P, a, b)
        return np.maximum(t0 - t, t - t1) * L
    return f


def m_sphere(c, r):
    c = v3(c)
    return lambda P: np.sqrt(dot_rows(P - c, P - c)) - r


def m_capsule(a, b, r):
    a, b = v3(a), v3(b)

    def f(P):
        t, L = seg_t(P, a, b)
        t = np.clip(t, 0, 1)
        C = a + t[:, None] * (b - a)
        return np.sqrt(dot_rows(P - C, P - C)) - r
    return f


def m_side(sign):
    """x on the given side (sign=+1 -> +X / character left)."""
    return lambda P: -sign * P[:, 0] + 0.0


def m_all():
    return lambda P: np.full(len(P), -1.0)


# ----------------------------------------------------------------------------- garments
class Garment:
    def __init__(self, name, node, region, cover_margin=None, res=None, kind="cloth", colour=None):
        self.name = name
        self.node = node
        self.region = region
        self.cover_margin = cover_margin
        self.res = res
        self.kind = kind
        self.colour = colour    # fn(P) -> (N,3) weights (primary, secondary, accent)

    def as_dict(self):
        return dict(name=self.name, node=self.node, res=self.res, kind=self.kind)


def shell_node(base, region, offset, thick, lo, hi, folds=None, edge_k=0.0035, base_m=0.03):
    """Garment surface as a Func node."""
    half = thick * 0.5
    off_fn = offset if callable(offset) else (lambda P, o=offset: np.full(len(P), o))

    def fn(P):
        d = base.ev(P, P.min(axis=0), P.max(axis=0), base_m)
        o = off_fn(P)
        s = np.abs(d - o) - half
        if folds is not None:
            near = np.abs(s) < 0.02
            if np.any(near):
                s = s.copy()
                s[near] -= folds(P[near])
        r = region(P)
        return smax(s, r, edge_k)
    return Func(fn, lo, hi)


def solid_node(sdf, region, edge_k=0.003):
    def fn(P):
        return smax(sdf.ev(P, P.min(axis=0), P.max(axis=0), 0.02), region(P), edge_k)
    return Func(fn, sdf.lo, sdf.hi)


def body_bbox(F, zlo, zhi, pad=0.08):
    lo = np.array([F.proxy.lo[0] - pad, F.proxy.lo[1] - pad, zlo - pad])
    hi = np.array([F.proxy.hi[0] + pad, F.proxy.hi[1] + pad, zhi + pad])
    return lo, hi


# ----------------------------------------------------------------------------- shared landmarks
def landmarks(F):
    J = F.J
    p = F.p
    L = {}
    for side, s in (("Left", 1), ("Right", -1)):
        sh, el, wr = J[side + "Shoulder"], J[side + "Elbow"], J[side + "Wrist"]
        adir = normalize(el - sh)
        L[side + "_armhole"] = (sh - adir * 0.030, adir)
        L[side + "_ua"] = (sh, el)
        L[side + "_fa"] = (el, wr)
        L[side + "_th"] = (J[side + "Hip"], J[side + "Knee"])
        L[side + "_sh"] = (J[side + "Knee"], J[side + "Ankle"])
    return L


def arm_side(L, side):
    p0, n = L[side + "_armhole"]
    return m_plane(p0, -n)            # negative on the arm side


def torso_side(L):
    """negative on the torso side of both armholes."""
    return m_and(m_plane(*L["Left_armhole"]), m_plane(*L["Right_armhole"]))


def leg_region(L, side, t_hem):
    """Everything below the hip on this leg down to t_hem along the shin."""
    s = 1 if side == "Left" else -1
    a, b = L[side + "_sh"]
    return m_and(m_seg(a, b, -10.0, t_hem), lambda P, s=s: -s * P[:, 0] - 0.0)


def fold_fn(F, amp, zfreq=40.0, xyfreq=16.0, rings=(), seed=3):
    """Vertical drape + ring folds.  rings: list of (centre_z, width_z, amp_mult, wavelength)."""
    def f(P):
        Q = P * np.array([xyfreq, xyfreq, zfreq * 0.25])
        drape = perlin3(Q, 1.0, seed) * 0.7 + perlin3(Q * 2.2, 1.0, seed + 5) * 0.3
        out = drape * 0.55
        for cz, wz, am, wl in rings:
            env = np.exp(-((P[:, 2] - cz) / wz) ** 2)
            ph = perlin3(P * 9.0, 1.0, seed + 11) * 2.2
            out = out + am * env * np.sin(2 * np.pi * P[:, 2] / wl + ph)
        return amp * np.clip(out, -1.0, 1.0)
    return f


def wrap_ridges(axis_a, axis_b, pitch=0.016, amp=0.0014):
    a, b = v3(axis_a), v3(axis_b)
    ax = normalize(b - a)
    ref = np.cross(ax, UP)
    if np.linalg.norm(ref) < 1e-3:
        ref = np.cross(ax, LEFT)
    ref = normalize(ref)
    ref2 = np.cross(ax, ref)

    def f(P):
        rel = P - a
        along = rel @ ax
        ang = np.arctan2(rel @ ref2, rel @ ref)
        ph = along / pitch + ang / (2 * np.pi) * 1.0
        saw = (ph % 1.0)
        return amp * (1.0 - 2.0 * np.abs(saw - 0.5) * 2.0)
    return f


# ----------------------------------------------------------------------------- fighters
def build(F):
    L = landmarks(F)
    F.cl_landmarks = L
    fn = {"nyx": clothes_nyx, "bruno": clothes_bruno, "vex": clothes_vex, "hops": clothes_hops,
          "scrap": clothes_scrap}[F.id]
    F.garments_obj = fn(F, L)
    F.garments = [g.as_dict() for g in F.garments_obj]

    def covered(V):
        V = np.asarray(V, dtype=np.float64)
        cov = np.zeros(len(V), dtype=bool)
        for g in F.garments_obj:
            if g.cover_margin is None:
                continue
            r = g.region(V)
            cov |= r < -g.cover_margin
        return cov
    F.covered = covered
    return F


def neckline(F, front_z, back_z):
    """Plane through the neck tilted so the back is higher."""
    zc = 0.5 * (front_z + back_z)
    slope = (back_z - front_z) / 0.16
    n = normalize(np.array([0.0, -slope, 1.0]))
    return m_plane([0.0, 0.0, zc], n)


def clothes_nyx(F, L):
    """Charcoal/crimson cropped jacket (short sleeves, hood), charcoal fitted under-top (B10),
    red scarf, crimson waist sash with hanging tails, dark cargo trousers, wrist & ankle wraps."""
    J = F.J
    p = F.p
    G = []
    base = F.proxy
    z_crop = p["rib_z"] - 0.085
    z_neck = p["neck_base_z"]
    # --- under-top (trim colour): waist -> neck, sleeveless
    top_region = m_and(m_zband(0.985, 10.0), neckline(F, z_neck + 0.010, z_neck + 0.040), torso_side(L))
    lo, hi = body_bbox(F, 0.95, z_neck + 0.1)
    G.append(Garment("top", shell_node(base, top_region, 0.0035, 0.0075, lo, hi, edge_k=0.002), top_region,
                     cover_margin=0.020, colour=lambda P: np.zeros((len(P), 3))))
    # --- cropped jacket with short sleeves
    sleeve_t = 0.62
    jac_torso = m_and(m_zband(z_crop, 10.0), neckline(F, z_neck + 0.030, z_neck + 0.075), torso_side(L))
    sleeves = [m_and(arm_side(L, s), m_seg(*L[s + "_ua"], -1.0, sleeve_t)) for s in ("Left", "Right")]
    jac_region = m_or(jac_torso, *sleeves)
    folds = fold_fn(F, 0.0035, zfreq=30, xyfreq=14, seed=21)
    lo, hi = body_bbox(F, z_crop - 0.05, z_neck + 0.12)

    def jac_off(P):
        # looser around the chest/back, slightly tighter at the cuffs
        return np.full(len(P), 0.019)
    G.append(Garment("jacket", shell_node(base, jac_region, jac_off, 0.010, lo, hi, folds=folds), jac_region,
                     cover_margin=0.022, colour=nyx_jacket_colour(F, L, z_crop, sleeve_t)))
    # hem band / cuffs (thicker rim)
    hem = m_and(jac_region, m_or(m_zband(z_crop - 0.01, z_crop + 0.022),
                                 *[m_and(arm_side(L, s), m_seg(*L[s + "_ua"], sleeve_t - 0.075, 2.0)) for s in ("Left", "Right")]))
    G.append(Garment("jacket_hem", shell_node(base, hem, 0.0215, 0.0125, lo, hi), hem, cover_margin=None,
                     colour=lambda P: np.tile([0.0, 1.0, 0.0], (len(P), 1))))
    # --- hood bunched behind the neck
    nb = J["Neck"]
    hood_c = nb + np.array([0.0, 0.070, 0.035])
    hood_outer = Ellipsoid(hood_c, (0.115, 0.060, 0.085), rot_x(-0.35))
    hood_inner = Ellipsoid(hood_c + np.array([0.0, -0.028, 0.030]), (0.090, 0.040, 0.070), rot_x(-0.35))
    hood = Subtract(hood_outer, hood_inner, k=0.012)
    torus = Torus(nb + np.array([0, 0.012, 0.030]), rot_x(-0.25), 0.080, 0.026)
    hood = Union([hood, Intersect(torus, HalfSpace(nb + np.array([0, -0.005, 0]), [0, -1, 0]), k=0.02)], k=0.03)
    hood = Subtract(hood, Offset_body(F, 0.010), k=0.006)
    G.append(Garment("hood", hood, m_sphere(hood_c, 0.2), cover_margin=None,
                     colour=lambda P, c=hood_c: np.stack([np.ones(len(P)) * 0.0, (P[:, 2] > c[2] + 0.045).astype(float), np.zeros(len(P))], 1)))
    # --- scarf (accent): wrap around the neck + short front tail
    sc_c = nb + np.array([0.0, -0.004, 0.052])
    wrapn = Torus(sc_c, rot_x(0.30), p["neck_r"][0] + 0.022, 0.024)
    wrapn2 = Torus(sc_c + np.array([0, 0.004, 0.030]), rot_x(0.18), p["neck_r"][1] + 0.020, 0.020)
    tail_a = sc_c + np.array([0.030, -0.060, -0.012])
    tail = RoundBox(tail_a + np.array([0.004, -0.004, -0.070]), (0.030, 0.008, 0.070), rot_y(0.12) @ rot_x(-0.12), rnd=0.006)
    knot = Ellipsoid(tail_a + np.array([0.0, 0.004, 0.004]), (0.030, 0.024, 0.026))
    scarf = Union([wrapn, wrapn2, knot, tail], k=0.012)
    scarf = Subtract(scarf, Offset_body(F, 0.004), k=0.004)
    G.append(Garment("scarf", scarf, m_sphere(sc_c, 0.25), cover_margin=None,
                     colour=lambda P: np.tile([0.0, 0.0, 1.0], (len(P), 1))))
    # --- trousers (trim): hips -> ankles, loose cargo, tail hole
    z_top = 1.030 * (p["pelvis_z"] / 0.935)
    t_hem = 0.80
    tr_region = m_and(m_or(m_zband(-10.0, z_top) if False else m_zband(p["hip_z"] - 0.02, z_top),
                           leg_region(L, "Left", t_hem), leg_region(L, "Right", t_hem)),
                      m_plane([0, 0, z_top], [0, -0.25, 1.0]))
    tail_hole = m_capsule(F.tail_pts[0] + np.array([0, -0.05, 0]), F.tail_pts[4], F.tail_radii[0] + 0.012)
    tr_region = m_and(tr_region, m_not(tail_hole))

    def tr_off(P):
        o = np.full(len(P), 0.013)
        for side in ("Left", "Right"):
            a, b = L[side + "_sh"]
            t, Ls = seg_t(P, a, b)
            s = 1 if side == "Left" else -1
            on = (s * P[:, 0] > 0.02)
            # baggy shins, tapering into the ankle wraps
            bag = np.interp(t, [-1.0, -0.4, 0.0, 0.35, 0.62, 0.80], [0.012, 0.015, 0.020, 0.024, 0.017, 0.010])
            o = np.where(on & (P[:, 2] < p["hip_z"] - 0.05), bag, o)
        return o
    folds = fold_fn(F, 0.0045, zfreq=34, xyfreq=13, seed=5,
                    rings=[(J["LeftKnee"][2], 0.05, 0.8, 0.028), (J["LeftAnkle"][2] + 0.12, 0.05, 1.0, 0.022)])
    lo, hi = body_bbox(F, 0.0, z_top + 0.05)
    G.append(Garment("trousers", shell_node(base, tr_region, tr_off, 0.010, lo, hi, folds=folds), tr_region,
                     cover_margin=0.022, colour=lambda P: np.zeros((len(P), 3))))
    # knee patches + cargo pockets (primary)
    for side in ("Left", "Right"):
        s = 1 if side == "Left" else -1
        kn = J[side + "Knee"] + np.array([0, -0.035, 0.0])
        patch_r = m_and(m_sphere(kn + np.array([0, -0.02, 0.0]), 0.062), m_plane(J[side + "Knee"], [0, -1, 0]) if False else m_plane(J[side + "Knee"] + np.array([0, -0.01, 0]), [0, 1, 0]))
        G.append(Garment(side + "_kneepatch", shell_node(base, patch_r, tr_off_plus(tr_off, 0.009), 0.007,
                                                          kn - 0.12, kn + 0.12), patch_r, cover_margin=None,
                         colour=lambda P: np.tile([1.0, 0.0, 0.0], (len(P), 1))))
        hip, knee = J[side + "Hip"], J[side + "Knee"]
        pc = hip + (knee - hip) * 0.50 + np.array([s * 0.075, 0.010, 0.0])
        pocket = RoundBox(pc, (0.022, 0.062, 0.070), rot_z(s * 0.10) @ rot_y(-s * 0.05), rnd=0.010)
        pocket = Subtract(pocket, Offset_body(F, 0.010), k=0.004)
        flap = RoundBox(pc + np.array([s * 0.010, 0.0, 0.060]), (0.020, 0.066, 0.016), rot_z(s * 0.10), rnd=0.006)
        flap = Subtract(flap, Offset_body(F, 0.012), k=0.004)
        G.append(Garment(side + "_pocket", Union([pocket, flap], k=0.004), m_sphere(pc, 0.15), cover_margin=None,
                         colour=lambda P: np.zeros((len(P), 3))))
    # --- sash (secondary): band over the waistband + knot at the left hip + hanging tails
    zs0, zs1 = z_top - 0.050, z_top + 0.012
    sash_region = m_zband(zs0, zs1)
    lo, hi = body_bbox(F, zs0 - 0.05, zs1 + 0.05)
    sash_band = shell_node(base, sash_region, 0.030, 0.013, lo, hi, folds=fold_fn(F, 0.003, zfreq=8, xyfreq=30, seed=9))
    kn_c = np.array([0.125, -0.040, 0.5 * (zs0 + zs1)])
    knot = Ellipsoid(kn_c, (0.028, 0.030, 0.030))
    t1 = RoundBox(kn_c + np.array([0.020, -0.004, -0.120]), (0.030, 0.007, 0.115), rot_y(0.10) @ rot_x(-0.06), rnd=0.005)
    t2 = RoundBox(kn_c + np.array([0.050, 0.012, -0.090]), (0.026, 0.007, 0.085), rot_y(0.30) @ rot_x(0.05), rnd=0.005)
    sash = Union([sash_band, knot, t1, t2], k=0.010)
    sash = Subtract(sash, Offset_body(F, 0.012), k=0.004)
    G.append(Garment("sash", sash, m_or(m_zband(zs0, zs1), m_sphere(kn_c, 0.25)), cover_margin=None,
                     colour=lambda P: np.tile([0.0, 1.0, 0.0], (len(P), 1))))
    # --- wraps: wrists (trim + accent stripes) and ankles (trim)
    for side in ("Left", "Right"):
        el, wr = L[side + "_fa"]
        reg = m_and(m_seg(el, wr, 0.50, 1.10), arm_side(L, side))
        lo = np.minimum(el, wr) - 0.12
        hi = np.maximum(el, wr) + 0.12
        G.append(Garment(side + "_wristwrap", shell_node(F.body, reg, 0.0032, 0.0060, lo, hi,
                                                          folds=wrap_ridges(el, wr), edge_k=0.002, base_m=0.02),
                         reg, cover_margin=0.012,
                         colour=stripe_colour(el, wr, [(0.62, 0.68), (0.95, 1.0)])))
        kn, an = L[side + "_sh"]
        s = 1 if side == "Left" else -1
        reg = m_and(m_seg(kn, an, 0.74, 1.04), lambda P, s=s: -s * P[:, 0])
        lo = np.minimum(kn, an) - 0.12
        hi = np.maximum(kn, an) + 0.12

        def ank_off(P, kn=kn, an=an):
            t, _ = seg_t(P, kn, an)
            return np.interp(t, [0.74, 0.84, 0.96], [0.016, 0.009, 0.0035])
        G.append(Garment(side + "_anklewrap", shell_node(F.body, reg, ank_off, 0.0065, lo, hi,
                                                          folds=wrap_ridges(kn, an, pitch=0.018), edge_k=0.002, base_m=0.03),
                         reg, cover_margin=0.012, colour=lambda P: np.zeros((len(P), 3))))
    return G


def tr_off_plus(fn, add):
    return lambda P: fn(P) + add


class Offset_body:
    """Body SDF (inflated by r) used to carve garment interiors so solids never intersect the body."""

    def __init__(self, F, r):
        self.F = F
        self.r = r
        self.lo = F.body.lo - r
        self.hi = F.body.hi + r
        self.tag = None

    def ev(self, P, blo, bhi, m):
        return self.F.body.ev(P, blo, bhi, m + self.r) - self.r


def stripe_colour(a, b, bands):
    a, b = v3(a), v3(b)

    def f(P):
        t, _ = seg_t(P, a, b)
        acc = np.zeros(len(P))
        for t0, t1 in bands:
            acc = np.maximum(acc, ((t > t0) & (t < t1)).astype(float))
        return np.stack([np.zeros(len(P)), np.zeros(len(P)), acc], 1)
    return f


def nyx_jacket_colour(F, L, z_crop, sleeve_t):
    J = F.J

    def f(P):
        n = len(P)
        prim = np.ones(n)
        sec = np.zeros(n)
        # crimson shoulder yokes: top of the shoulders / upper sleeves
        for side in ("Left", "Right"):
            a, b = L[side + "_ua"]
            t, _ = seg_t(P, a, b)
            on_arm = arm_side(L, side)(P) < 0
            yoke = on_arm & (t < 0.28) & (P[:, 2] > a[2] - 0.02)
            sec = np.maximum(sec, yoke.astype(float))
        # upper-back triangle panel (points down)
        back = P[:, 1] > 0.02
        zc = J["UpperChest"][2] + 0.10
        tri = back & (P[:, 2] < zc) & (P[:, 2] > zc - 0.20) & (np.abs(P[:, 0]) < (P[:, 2] - (zc - 0.20)) * 0.55)
        sec = np.maximum(sec, tri.astype(float))
        # front zip placket and side panels stay primary
        prim = 1.0 - sec
        return np.stack([prim, sec, np.zeros(n)], 1)
    return f


# placeholders for the other fighters (filled in when their outfits are built)
def clothes_bruno(F, L):
    raise NotImplementedError


def clothes_vex(F, L):
    raise NotImplementedError


def clothes_hops(F, L):
    raise NotImplementedError


def clothes_scrap(F, L):
    raise NotImplementedError
