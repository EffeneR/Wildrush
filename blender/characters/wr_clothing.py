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
    def __init__(self, name, node, region, cover_margin=None, res=None, kind="cloth", colour=None,
                 base=None, inner=None):
        self.base = base          # SDF whose iso-surface the garment follows (for cover tests)
        self.inner = inner        # inner offset of the garment (cover only if base(P) < inner)
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


def arm_val(L, side):
    """Signed distance past the armhole plane (positive on the arm side), bounded to the
    neighbourhood of the arm (elsewhere -1 = torso side)."""
    p0, n = L[side + "_armhole"]
    a = L[side + "_ua"][0]
    b = L[side + "_fa"][1] + n * 0.14

    def f(P):
        t, Lg = seg_t(P, a, b)
        t = np.clip(t, 0, 1)
        C = a + t[:, None] * (b - a)
        near = np.sqrt(dot_rows(P - C, P - C)) < 0.17
        return np.where(near, (P - p0) @ n, -1.0)
    return f


def arm_side(L, side):
    """negative on the arm side."""
    v = arm_val(L, side)
    return lambda P: -v(P)


def torso_side(L):
    """negative on the torso side of both armholes."""
    return m_and(arm_val(L, "Left"), arm_val(L, "Right"))


def leg_hem(F, L, t_hem):
    """Piecewise term: for leg points (below the hips) (t_shin - t_hem) * L_shin, else -1."""
    hz = F.p["hip_z"]

    def f(P):
        out = np.full(len(P), -1.0)
        for side, s in (("Left", 1), ("Right", -1)):
            a, b = L[side + "_sh"]
            t, Ls = seg_t(P, a, b)
            on = (s * P[:, 0] > 0.0) & (P[:, 2] < hz)
            out = np.where(on, (t - t_hem) * Ls, out)
        return out
    return f


def sleeve_cut(L, t_end, t_start=-10.0, other=-1.0):
    """For arm-side points: band along the upper arm/forearm chain; torso points -> `other`."""
    def f(P):
        out = np.full(len(P), other)
        for side in ("Left", "Right"):
            av = arm_val(L, side)(P)
            sh, el = L[side + "_ua"]
            wr = L[side + "_fa"][1]
            # chain parameter: 0..1 upper arm, 1..2 forearm
            t1, L1 = seg_t(P, sh, el)
            t2, L2 = seg_t(P, el, wr)
            tc = np.where(t1 < 1.0, t1, 1.0 + np.clip(t2, 0, None))
            val = np.maximum(t_start - tc, tc - t_end) * np.where(tc < 1.0, L1, L2)
            out = np.where(av > 0, val, out)
        return out
    return f


def fold_fn(F, amp, zfreq=40.0, xyfreq=16.0, rings=(), seed=3):
    """Vertical drape folds + irregular bunching bands.
    rings: list of (centre_z, width_z, amp_mult, wavelength)."""
    def f(P):
        Q = P * np.array([xyfreq, xyfreq, zfreq * 0.25])
        drape = perlin3(Q, 1.0, seed) * 0.7 + perlin3(Q * 2.2, 1.0, seed + 5) * 0.3
        out = drape * 0.6
        for cz, wz, am, wl in rings:
            env = np.exp(-((P[:, 2] - cz) / wz) ** 2)
            ph = perlin3(P * np.array([14.0, 14.0, 6.0]), 1.0, seed + 11) * 3.0
            patch = np.clip(perlin3(P * 11.0, 1.0, seed + 23) * 1.4 + 0.3, 0.0, 1.0)
            out = out + am * env * patch * np.sin(2 * np.pi * P[:, 2] / wl + ph)
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
            c = r < -g.cover_margin
            if g.base is not None and np.any(c):
                idx = np.flatnonzero(c)
                from wr_sdf import eval_points
                d = eval_points(g.base, V[idx], cell=0.08, m=0.05)
                c[idx] = d < (g.inner + 0.006)
            cov |= c
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
                     cover_margin=0.020, colour=lambda P: np.zeros((len(P), 3)), base=base, inner=0.0035))
    # --- cropped jacket with short sleeves
    sleeve_t = 0.62
    jac_region = m_and(m_zband(z_crop, 10.0), neckline(F, z_neck + 0.030, z_neck + 0.075), sleeve_cut(L, sleeve_t))
    folds = fold_fn(F, 0.0035, zfreq=30, xyfreq=14, seed=21)
    lo, hi = body_bbox(F, z_crop - 0.05, z_neck + 0.12)

    def jac_off(P):
        # looser around the chest/back, slightly tighter at the cuffs
        return np.full(len(P), 0.019)
    G.append(Garment("jacket", shell_node(base, jac_region, jac_off, 0.010, lo, hi, folds=folds), jac_region,
                     cover_margin=0.022, colour=nyx_jacket_colour(F, L, z_crop, sleeve_t), base=base, inner=0.014))
    # hem band / cuffs (thicker rim)
    hem = m_and(jac_region, m_or(m_and(m_zband(z_crop - 0.01, z_crop + 0.022), torso_side(L)),
                                 sleeve_cut(L, 10.0, sleeve_t - 0.07, other=1.0)))
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
    tr_region = m_and(m_plane([0, 0, z_top], [0, -0.25, 1.0]), leg_hem(F, L, t_hem), torso_side(L))
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
    folds = fold_fn(F, 0.0040, zfreq=34, xyfreq=13, seed=5,
                    rings=[(J["LeftKnee"][2] + 0.01, 0.035, 0.45, 0.034), (J["LeftAnkle"][2] + 0.10, 0.04, 0.7, 0.026)])
    lo, hi = body_bbox(F, 0.0, z_top + 0.05)
    G.append(Garment("trousers", shell_node(base, tr_region, tr_off, 0.010, lo, hi, folds=folds), tr_region,
                     cover_margin=0.022, colour=lambda P: np.zeros((len(P), 3)), base=base, inner=0.008))
    # knee patches + cargo pockets (primary)
    for side in ("Left", "Right"):
        s = 1 if side == "Left" else -1
        kn = J[side + "Knee"] + np.array([0, -0.035, 0.0])
        kz = J[side + "Knee"][2]
        patch_r = m_and(m_zband(kz - 0.060, kz + 0.070), lambda P, c=kn[0]: np.abs(P[:, 0] - c) - 0.050,
                        m_plane(J[side + "Knee"] + np.array([0, -0.005, 0]), [0, 1, 0]))
        G.append(Garment(side + "_kneepatch", shell_node(base, patch_r, tr_off_plus(tr_off, 0.0075), 0.0065,
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
    sash_region = m_and(m_zband(zs0, zs1), torso_side(L))
    lo, hi = body_bbox(F, zs0 - 0.05, zs1 + 0.05)
    sash_band = shell_node(base, sash_region, 0.030, 0.013, lo, hi, folds=fold_fn(F, 0.003, zfreq=8, xyfreq=30, seed=9))
    kn_c = np.array([0.125, -0.040, 0.5 * (zs0 + zs1)])
    knot = Ellipsoid(kn_c, (0.028, 0.030, 0.030))
    t1 = RoundBox(kn_c + np.array([0.020, -0.004, -0.120]), (0.030, 0.007, 0.115), rot_y(0.10) @ rot_x(-0.06), rnd=0.005)
    t2 = RoundBox(kn_c + np.array([0.050, 0.012, -0.090]), (0.026, 0.007, 0.085), rot_y(0.30) @ rot_x(0.05), rnd=0.005)
    sash = Union([sash_band, knot, t1, t2], k=0.010)
    sash = Subtract(sash, Offset_body(F, 0.012), k=0.004)
    G.append(Garment("sash", sash, m_or(sash_region, m_sphere(kn_c, 0.25)), cover_margin=None,
                     colour=lambda P: np.tile([0.0, 1.0, 0.0], (len(P), 1))))
    # --- wraps: wrists (trim + accent stripes) and ankles (trim)
    for side in ("Left", "Right"):
        el, wr = L[side + "_fa"]
        reg = m_and(m_seg(el, wr, 0.52, 0.99), arm_side(L, side))
        lo = np.minimum(el, wr) - 0.12
        hi = np.maximum(el, wr) + 0.12
        G.append(Garment(side + "_wristwrap", shell_node(F.body, reg, 0.0032, 0.0060, lo, hi,
                                                          folds=wrap_ridges(el, wr, pitch=0.017, amp=0.0010), edge_k=0.002, base_m=0.02),
                         reg, cover_margin=0.012, base=F.body, inner=0.0003,
                         colour=stripe_colour(el, wr, [(0.62, 0.68), (0.93, 0.99)])))
        kn, an = L[side + "_sh"]
        s = 1 if side == "Left" else -1
        reg = m_and(m_seg(kn, an, 0.74, 1.04), lambda P, s=s: -s * P[:, 0], m_zband(-1.0, F.p["hip_z"] - 0.1))
        lo = np.minimum(kn, an) - 0.12
        hi = np.maximum(kn, an) + 0.12

        def ank_off(P, kn=kn, an=an):
            t, _ = seg_t(P, kn, an)
            return np.interp(t, [0.74, 0.84, 0.96], [0.016, 0.009, 0.0035])
        G.append(Garment(side + "_anklewrap", shell_node(F.body, reg, ank_off, 0.0065, lo, hi,
                                                          folds=wrap_ridges(kn, an, pitch=0.019, amp=0.0010), edge_k=0.002, base_m=0.03),
                         reg, cover_margin=0.012, colour=lambda P: np.zeros((len(P), 3)), base=F.body, inner=0.0003))
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


# ============================================================================= shared garment builders
def pal(p=0.0, s=0.0, a=0.0):
    return lambda P: np.tile([p, s, a], (len(P), 1))


def g_top(F, L, z_bottom, neck_front, neck_back, off=0.0035, thick=0.0075, colour=None, sleeve=None, name="top"):
    """Fitted under-top / athletic top: z_bottom -> neckline, sleeveless or short sleeves (t_end on arm chain)."""
    z_neck = F.p["neck_base_z"]
    reg = m_and(m_zband(z_bottom, 10.0), neckline(F, z_neck + neck_front, z_neck + neck_back),
                torso_side(L) if sleeve is None else sleeve_cut(L, sleeve))
    lo, hi = body_bbox(F, z_bottom - 0.05, z_neck + 0.12)
    return Garment(name, shell_node(F.proxy, reg, off, thick, lo, hi, edge_k=0.002), reg, cover_margin=0.020,
                   colour=colour or pal(), base=F.proxy, inner=off)


def g_upper(F, L, name, z_bottom, sleeve_t, neck_front, neck_back, off=0.019, thick=0.010, colour=None,
            open_front=0.0, folds_amp=0.0035, cover=True, armhole_in=0.0):
    """Jacket / vest.  sleeve_t None = sleeveless; open_front = half-width (m) of the front opening."""
    z_neck = F.p["neck_base_z"]
    parts = [m_zband(z_bottom, 10.0), neckline(F, z_neck + neck_front, z_neck + neck_back)]
    if sleeve_t is None:
        # sleeveless: vertical armhole planes just inside the shoulder joints (no flaps over the deltoids)
        xcut = F.p["sh_x"] - armhole_in
        z_arm = F.p["sh_z"] - 0.13            # armpit: below it the allowance widens (armhole bottom)

        def vcut(P, xc=xcut, za=z_arm):
            return np.abs(P[:, 0]) - (xc + 1.6 * np.maximum(0.0, za - P[:, 2]))
        parts.append(torso_side(L))
        parts.append(vcut)
    else:
        parts.append(sleeve_cut(L, sleeve_t))
    if open_front > 0:
        zc = F.p["rib_z"]

        def opening(P, w=open_front, zc=zc):
            front = P[:, 1] < -0.02
            wz = w * (0.55 + 0.45 * np.clip((P[:, 2] - (zc - 0.10)) / 0.25, 0, 1))
            return np.where(front, wz - np.abs(P[:, 0]), -1.0)
        parts.append(opening)
    reg = m_and(*parts)
    folds = fold_fn(F, folds_amp, zfreq=30, xyfreq=14, seed=21) if folds_amp > 0 else None
    lo, hi = body_bbox(F, z_bottom - 0.05, z_neck + 0.14)
    return Garment(name, shell_node(F.proxy, reg, off, thick, lo, hi, folds=folds), reg,
                   cover_margin=0.022 if cover else None, colour=colour or pal(1.0), base=F.proxy, inner=off - thick / 2)


def g_hem(F, L, upper_region, z_bottom, sleeve_t, off, thick, colour, name, front_band=None):
    parts = [m_and(m_zband(z_bottom - 0.01, z_bottom + 0.022), torso_side(L))]
    if sleeve_t is not None:
        parts.append(sleeve_cut(L, 10.0, sleeve_t - 0.07, other=1.0))
    if front_band is not None:
        w = front_band

        def band(P, w=w):
            return np.where(P[:, 1] < -0.02, np.abs(np.abs(P[:, 0]) - w) - 0.014, 1.0)
        parts.append(band)
    reg = m_and(upper_region, m_or(*parts))
    lo, hi = body_bbox(F, z_bottom - 0.05, F.p["neck_base_z"] + 0.14)
    return Garment(name, shell_node(F.proxy, reg, off, thick, lo, hi), reg, colour=colour)


def g_lower(F, L, name, t_hem, z_top, off_hips=0.013, bag=(0.012, 0.015, 0.020, 0.024, 0.017, 0.010),
            thigh_hem=None, colour=None, folds_amp=0.004):
    """Trousers (t_hem along the shin) or shorts (thigh_hem along the thigh)."""
    J = F.J
    p = F.p
    if thigh_hem is not None:
        def hem_term(P, t_th=thigh_hem):
            out = np.full(len(P), -1.0)
            for side, s in (("Left", 1), ("Right", -1)):
                a, b = L[side + "_th"]
                t, Ls = seg_t(P, a, b)
                on = (s * P[:, 0] > 0.0) & (P[:, 2] < p["hip_z"])
                out = np.where(on, (t - t_th) * Ls, out)
            return out
    else:
        hem_term = leg_hem(F, L, t_hem)
    reg = m_and(m_plane([0, 0, z_top], [0, -0.25, 1.0]), hem_term, torso_side(L))
    tail_hole = m_capsule(F.tail_pts[0] + np.array([0, -0.05, 0]), F.tail_pts[min(4, len(F.tail_pts) - 1)],
                          F.tail_radii[0] + 0.012)
    reg = m_and(reg, m_not(tail_hole))

    def off_fn(P):
        o = np.full(len(P), off_hips)
        for side in ("Left", "Right"):
            a, b = L[side + "_sh"]
            t, Ls = seg_t(P, a, b)
            s = 1 if side == "Left" else -1
            on = (s * P[:, 0] > 0.02)
            bg = np.interp(t, [-1.0, -0.4, 0.0, 0.35, 0.62, 0.80], list(bag))
            o = np.where(on & (P[:, 2] < p["hip_z"] - 0.05), bg, o)
        return o
    folds = fold_fn(F, folds_amp, zfreq=34, xyfreq=13, seed=5,
                    rings=[(J["LeftKnee"][2] + 0.01, 0.035, 0.45, 0.034), (J["LeftAnkle"][2] + 0.10, 0.04, 0.7, 0.026)])
    lo, hi = body_bbox(F, 0.0, z_top + 0.05)
    node = trouser_node(F, reg, off_fn, 0.010, lo, hi, folds)
    g = Garment(name, node, reg, cover_margin=0.022, colour=colour or pal(), base=F.proxy, inner=off_hips - 0.005)
    g.off_fn = off_fn
    return g


def trouser_node(F, region, off_fn, thick, lo, hi, folds, crotch_drop=0.055):
    """Hips part follows the whole proxy; below the crotch each leg gets its own tube from its own
    leg proxy, clipped to its side, so baggy legs never fill the gap between the thighs."""
    zc = F.p["hip_z"] - crotch_drop
    half = thick * 0.5

    def fn(P):
        blo, bhi = P.min(axis=0), P.max(axis=0)
        o = off_fn(P)
        d = F.proxy.ev(P, blo, bhi, 0.05)
        s_all = np.abs(d - o) - half
        s_all = np.maximum(s_all, zc - 0.015 - P[:, 2])
        out = s_all
        for side, sg in (("Left", 1.0), ("Right", -1.0)):
            dl = F.leg_proxy[side].ev(P, blo, bhi, 0.05)
            s_leg = np.abs(dl - o) - half
            s_leg = np.maximum(s_leg, P[:, 2] - (zc + 0.015))
            s_leg = np.maximum(s_leg, -sg * P[:, 0] - 0.002)
            out = smin(out, s_leg, 0.004)
        if folds is not None:
            near = np.abs(out) < 0.02
            if np.any(near):
                out = out.copy()
                out[near] -= folds(P[near])
        return smax(out, region(P), 0.0035)
    return Func(fn, lo, hi)


def g_band(F, L, name, z0, z1, off, thick, colour, folds=None):
    reg = m_and(m_zband(z0, z1), torso_side(L))
    lo, hi = body_bbox(F, z0 - 0.05, z1 + 0.05)
    return Garment(name, shell_node(F.proxy, reg, off, thick, lo, hi, folds=folds), reg, colour=colour)


def g_buckle(F, name, c, size, colour):
    b = RoundBox(c, size, None, rnd=0.004)
    b = Subtract(b, Offset_body(F, 0.020), k=0.003)
    return Garment(name, b, m_sphere(c, 0.1), colour=colour)


def g_hood(F, name, colour, scale=1.0, lift=0.0):
    J = F.J
    nb = J["Neck"]
    s = scale
    hood_c = nb + np.array([0.0, 0.070 * s, 0.035 + lift])
    outer = Ellipsoid(hood_c, (0.118 * s, 0.062 * s, 0.086 * s), rot_x(-0.35))
    inner = Ellipsoid(hood_c + np.array([0.0, -0.028, 0.030]), (0.092 * s, 0.042 * s, 0.070 * s), rot_x(-0.35))
    hood = Subtract(outer, inner, k=0.012)
    torus = Torus(nb + np.array([0, 0.012, 0.030 + lift]), rot_x(-0.25), 0.080 * s + (F.p["neck_r"][0] - 0.05), 0.026)
    hood = Union([hood, Intersect(torus, HalfSpace(nb + np.array([0, -0.005, 0]), [0, -1, 0]), k=0.02)], k=0.03)
    hood = Subtract(hood, Offset_body(F, 0.010), k=0.006)
    return Garment(name, hood, m_sphere(hood_c, 0.25), colour=colour)


def g_wrist(F, L, side, name, t0, t1, colour, off=0.0032, thick=0.0060):
    el, wr = L[side + "_fa"]
    reg = m_and(m_seg(el, wr, t0, t1), arm_side(L, side))
    lo = np.minimum(el, wr) - 0.12
    hi = np.maximum(el, wr) + 0.12
    return Garment(name, shell_node(F.body, reg, off, thick, lo, hi, folds=wrap_ridges(el, wr, pitch=0.017, amp=0.0010),
                                    edge_k=0.002, base_m=0.02), reg, cover_margin=0.012, base=F.body, inner=0.0003,
                   colour=colour)


def g_ankle(F, L, side, name, t0, t1, colour, off_profile=((0.74, 0.016), (0.84, 0.009), (0.96, 0.0035))):
    kn, an = L[side + "_sh"]
    s = 1 if side == "Left" else -1
    reg = m_and(m_seg(kn, an, t0, t1), lambda P, s=s: -s * P[:, 0], m_zband(-1.0, F.p["hip_z"] - 0.1))
    lo = np.minimum(kn, an) - 0.12
    hi = np.maximum(kn, an) + 0.12
    ts = [a for a, _ in off_profile]
    os_ = [b for _, b in off_profile]

    def off(P, kn=kn, an=an):
        t, _ = seg_t(P, kn, an)
        return np.interp(t, ts, os_)
    return Garment(name, shell_node(F.body, reg, off, 0.0065, lo, hi, folds=wrap_ridges(kn, an, pitch=0.019, amp=0.0010),
                                    edge_k=0.002, base_m=0.03), reg, cover_margin=0.012, base=F.body, inner=0.0003,
                   colour=colour)


def g_pad(F, L, side, which, name, colour, base_off, size=(0.055, 0.065), thick=0.014):
    """Soft fabric pad (knee / elbow): thick quilted cap on the joint front/back (B11: no hard armour)."""
    J = F.J
    s = 1 if side == "Left" else -1
    if which == "knee":
        c = J[side + "Knee"] + np.array([0, -0.045, 0.0])
        half = m_and(m_zband(c[2] - size[1], c[2] + size[1] * 0.9), lambda P, cx=c[0], w=size[0]: np.abs(P[:, 0] - cx) - w,
                     m_plane(J[side + "Knee"] + np.array([0, -0.004, 0]), [0, 1, 0]))
        lo, hi = c - 0.15, c + 0.15
        base = F.proxy
    else:  # elbow (back of the elbow)
        el = J[side + "Elbow"]
        sh = J[side + "Shoulder"]
        wr = J[side + "Wrist"]
        ua = normalize(el - sh)
        fa = normalize(wr - el)
        back = normalize(np.cross(ua, np.array([0.0, 0.0, 1.0])) * 0 + np.array([0.0, 1.0, 0.0]))
        c = el + back * 0.03

        def half(P, el=el, ua=ua, fa=fa, w=size[0], h=size[1]):
            rel = P - el
            along = np.where(rel @ ua < 0, rel @ ua, rel @ fa)
            d_side = np.abs(rel @ normalize(np.cross(ua, fa) + 1e-9)) if False else np.zeros(len(P))
            behind = -(rel @ np.array([0.0, 1.0, 0.0])) + 0.004
            return np.maximum.reduce([np.abs(along) - h, behind, np.linalg.norm(rel, axis=1) - (w + 0.05)])
        lo, hi = el - 0.18, el + 0.18
        base = F.body
    quilt = lambda P: 0.0022 * np.clip(np.sin(P[:, 0] * 180) * np.sin(P[:, 2] * 180) * 2.0, -1, 1)
    node = shell_node(base, half, base_off, thick, lo, hi, folds=quilt, edge_k=0.006, base_m=0.03)
    return Garment(name, node, half, colour=colour)


def g_pocket(F, side, name, frac=0.50, out=0.075, size=(0.022, 0.062, 0.070), colour=None):
    J = F.J
    s = 1 if side == "Left" else -1
    hip, knee = J[side + "Hip"], J[side + "Knee"]
    pc = hip + (knee - hip) * frac + np.array([s * out, 0.010, 0.0])
    pocket = RoundBox(pc, size, rot_z(s * 0.10) @ rot_y(-s * 0.05), rnd=0.010)
    pocket = Subtract(pocket, Offset_body(F, 0.010), k=0.004)
    flap = RoundBox(pc + np.array([s * 0.010, 0.0, size[2] - 0.010]), (size[0] - 0.002, size[1] + 0.004, 0.016), rot_z(s * 0.10), rnd=0.006)
    flap = Subtract(flap, Offset_body(F, 0.012), k=0.004)
    return Garment(name, Union([pocket, flap], k=0.004), m_sphere(pc, 0.15), colour=colour or pal())


def g_zip(F, name, z0, z1, off, colour):
    """Raised zipper placket down the front centre."""
    def reg(P, z0=z0, z1=z1):
        return np.maximum.reduce([np.abs(P[:, 0]) - 0.008, z0 - P[:, 2], P[:, 2] - z1, P[:, 1] + 0.0])
    lo, hi = body_bbox(F, z0 - 0.05, z1 + 0.05)
    return Garment(name, shell_node(F.proxy, reg, off, 0.012, lo, hi, edge_k=0.002), reg, colour=colour)


# ============================================================================= Bruno
def clothes_bruno(F, L):
    """Navy sleeveless vest with cobalt upper-back panel + hood, charcoal shorts with belt,
    blue wrist/hand wraps, soft padded knee pads (B11), short tail through the shorts."""
    p = F.p
    J = F.J
    G = []
    z_vest = p["waist_z"] - 0.035
    zc = J["UpperChest"][2]

    def vest_colour(P, zc=zc):
        n = len(P)
        back = P[:, 1] > 0.03
        panel = back & (P[:, 2] > zc - 0.06)                      # cobalt upper-back panel
        piping = (np.abs(np.abs(P[:, 0]) - 0.075) < 0.010) & (P[:, 1] < -0.03) & (P[:, 2] > zc - 0.10)
        sec = panel.astype(float)
        acc = piping.astype(float) * (1 - sec)
        return np.stack([1 - sec - acc, sec, acc], 1)
    vest = g_upper(F, L, "vest", z_vest, None, 0.030, 0.070, off=0.018, thick=0.011, colour=vest_colour, armhole_in=0.030)
    G.append(vest)
    G.append(g_hem(F, L, vest.region, z_vest, None, 0.0205, 0.0135, pal(0, 1, 0), "vest_hem"))
    G.append(g_zip(F, "vest_zip", z_vest + 0.01, p["neck_base_z"] + 0.03, 0.022, pal(0, 0, 1)))
    G.append(g_hood(F, "hood", lambda P: np.stack([np.ones(len(P)) * 0.0 + 1.0, np.zeros(len(P)), np.zeros(len(P))], 1), scale=1.12))
    z_top = p["waist_z"] - 0.015
    shorts = g_lower(F, L, "shorts", None, z_top, off_hips=0.012, thigh_hem=0.78,
                     bag=(0.014, 0.018, 0.022, 0.024, 0.020, 0.012), colour=pal())
    G.append(shorts)
    G.append(g_band(F, L, "belt", z_top - 0.040, z_top - 0.004, 0.025, 0.012, pal()))
    G.append(g_buckle(F, "buckle", np.array([0.0, -0.13, z_top - 0.022]), (0.028, 0.008, 0.020), pal(0, 0, 1)))
    for side in ("Left", "Right"):
        G.append(g_pocket(F, side, side + "_pocket", frac=0.42, out=0.085, size=(0.022, 0.060, 0.062)))
        G.append(g_wrist(F, L, side, side + "_wrap", 0.52, 0.99, lambda P: np.tile([0, 1, 0], (len(P), 1)),
                         off=0.0035, thick=0.0068))
        G.append(g_pad(F, L, side, "knee", side + "_kneepad", pal(), base_off=0.016, size=(0.058, 0.070), thick=0.018))
    return G


# ============================================================================= Vex
def clothes_vex(F, L):
    """Dark-plum cropped open jacket with a copper panel on the anatomical RIGHT shoulder only
    (B8), dark under-shirt, charcoal rolled trousers, belt, fingerless wraps, hood. No scarf."""
    p = F.p
    J = F.J
    G = []
    z_crop = p["rib_z"] - 0.075
    G.append(g_top(F, L, p["waist_z"] - 0.06, 0.012, 0.040, colour=pal()))
    right_sh = J["RightShoulder"]

    def jacket_colour(P, rs=right_sh, zc=J["UpperChest"][2]):
        n = len(P)
        # copper panel: anatomical right shoulder = -X side, top of the shoulder / upper sleeve
        d = P - (rs + np.array([-0.02, 0.0, 0.03]))
        panel = (P[:, 0] < -0.06) & (np.linalg.norm(d, axis=1) < 0.13) & (P[:, 2] > rs[2] - 0.07)
        sec = panel.astype(float)
        collar = (P[:, 2] > p["neck_base_z"] + 0.02).astype(float) * (1 - sec)
        return np.stack([1 - sec - collar * 0.0, sec, collar * 0.0], 1)
    jacket = g_upper(F, L, "jacket", z_crop, 1.45, 0.045, 0.085, off=0.020, thick=0.010, colour=jacket_colour,
                     open_front=0.060)
    G.append(jacket)
    G.append(g_hem(F, L, jacket.region, z_crop, 1.45, 0.0215, 0.0130, pal(1.0), "jacket_hem"))
    G.append(g_hood(F, "hood", pal(1.0), scale=1.02, lift=0.012))
    z_top = p["waist_z"] - 0.02
    tr = g_lower(F, L, "trousers", 0.66, z_top, off_hips=0.013, bag=(0.013, 0.016, 0.021, 0.024, 0.019, 0.016), colour=pal())
    G.append(tr)
    # rolled cuffs at the shin hem
    for side in ("Left", "Right"):
        kn, an = L[side + "_sh"]
        s = 1 if side == "Left" else -1
        reg = m_and(m_seg(kn, an, 0.58, 0.68), lambda P, s=s: -s * P[:, 0], m_zband(-1, p["hip_z"] - 0.1))
        lo, hi = np.minimum(kn, an) - 0.15, np.maximum(kn, an) + 0.15
        G.append(Garment(side + "_cuff", shell_node(F.proxy, reg, 0.026, 0.014, lo, hi, edge_k=0.004), reg, colour=pal()))
        G.append(g_wrist(F, L, side, side + "_glove", 0.70, 1.02, pal(), off=0.0035, thick=0.0065))
        G.append(g_pocket(F, side, side + "_pocket", frac=0.45, out=0.080, size=(0.020, 0.055, 0.060)))
    G.append(g_band(F, L, "belt", z_top - 0.042, z_top - 0.006, 0.024, 0.012, pal()))
    G.append(g_buckle(F, "buckle", np.array([0.0, -0.118, z_top - 0.024]), (0.024, 0.007, 0.018), pal(0, 0, 1)))
    return G


# ============================================================================= Hops
def clothes_hops(F, L):
    """Teal cropped jacket (short sleeves, hood), full-coverage charcoal athletic top reaching the
    waistband, mid-thigh charcoal shorts with mint waistband (B9), ankle wraps, fingerless gloves."""
    p = F.p
    J = F.J
    G = []
    z_crop = p["rib_z"] - 0.070
    z_top = p["waist_z"] - 0.010
    G.append(g_top(F, L, z_top - 0.035, 0.016, 0.045, colour=pal(0, 1, 0), name="athletic_top"))
    jacket = g_upper(F, L, "jacket", z_crop, 0.55, 0.045, 0.085, off=0.019, thick=0.010, colour=pal(1.0),
                     open_front=0.050)
    G.append(jacket)
    G.append(g_hem(F, L, jacket.region, z_crop, 0.55, 0.0212, 0.0128, pal(0, 0, 1), "jacket_trim"))
    G.append(g_hood(F, "hood", pal(1.0), scale=0.98, lift=0.010))
    shorts = g_lower(F, L, "shorts", None, z_top, off_hips=0.010, thigh_hem=0.55,
                     bag=(0.010, 0.012, 0.014, 0.014, 0.012, 0.010), colour=pal(0, 1, 0), folds_amp=0.003)
    G.append(shorts)
    G.append(g_band(F, L, "waistband", z_top - 0.040, z_top - 0.004, 0.018, 0.012, pal(0, 0, 1)))
    for side in ("Left", "Right"):
        G.append(g_ankle(F, L, side, side + "_anklewrap", 0.80, 1.05, pal(),
                         off_profile=((0.80, 0.006), (0.92, 0.004), (1.0, 0.0035))))
        G.append(g_wrist(F, L, side, side + "_glove", 0.72, 1.02, pal(1.0), off=0.0035, thick=0.0065))
    # thigh strap (left)
    hip, knee = J["LeftHip"], J["LeftKnee"]
    reg = m_and(m_seg(hip, knee, 0.60, 0.68), lambda P: -P[:, 0], m_zband(-1, p["hip_z"] - 0.05))
    G.append(Garment("thigh_strap", shell_node(F.proxy, reg, 0.006, 0.008, hip - 0.25, hip + 0.25, edge_k=0.002), reg, colour=pal()))
    return G


# ============================================================================= Scrap
def clothes_scrap(F, L):
    """Slate sleeveless vest (hood, amber accents), cropped charcoal trousers, belt, wrist wraps
    with amber stripes, soft elbow and knee pads (B11). No gadgets."""
    p = F.p
    J = F.J
    G = []
    z_vest = p["waist_z"] - 0.030
    zc = J["UpperChest"][2]

    def vest_colour(P, zc=zc):
        yoke = (P[:, 2] > zc + 0.05) & (np.abs(P[:, 0]) > 0.07)          # amber shoulder yokes
        stripe = (np.abs(np.abs(P[:, 0]) - 0.060) < 0.008) & (P[:, 1] < -0.03) & (P[:, 2] < zc + 0.05)
        sec = yoke.astype(float)
        acc = stripe.astype(float) * (1 - sec)
        return np.stack([1 - sec - acc, sec, acc], 1)
    vest = g_upper(F, L, "vest", z_vest, None, 0.030, 0.070, off=0.018, thick=0.011, colour=vest_colour, armhole_in=0.028)
    G.append(vest)
    G.append(g_hem(F, L, vest.region, z_vest, None, 0.0205, 0.0135, pal(), "vest_hem"))
    G.append(g_zip(F, "vest_zip", z_vest + 0.01, p["neck_base_z"] + 0.03, 0.022, pal(0, 0, 1)))
    G.append(g_hood(F, "hood", pal(1.0), scale=1.08))
    z_top = p["waist_z"] - 0.015
    tr = g_lower(F, L, "trousers", 0.62, z_top, off_hips=0.013, bag=(0.013, 0.017, 0.022, 0.025, 0.020, 0.016), colour=pal())
    G.append(tr)
    G.append(g_band(F, L, "belt", z_top - 0.040, z_top - 0.004, 0.025, 0.012, pal()))
    G.append(g_buckle(F, "buckle", np.array([0.0, -0.140, z_top - 0.022]), (0.026, 0.008, 0.019), pal(0, 1, 0)))
    for side in ("Left", "Right"):
        el, wr = L[side + "_fa"]
        G.append(g_wrist(F, L, side, side + "_wrap", 0.55, 1.0, stripe_colour(el, wr, [(0.60, 0.66), (0.90, 0.95)])))
        G.append(g_pad(F, L, side, "knee", side + "_kneepad", pal(), base_off=0.018, size=(0.056, 0.062), thick=0.016))
        G.append(g_pad(F, L, side, "elbow", side + "_elbowpad", pal(), base_off=0.004, size=(0.045, 0.050), thick=0.013))
        G.append(g_pocket(F, side, side + "_pocket", frac=0.50, out=0.090, size=(0.022, 0.060, 0.066)))
    return G
