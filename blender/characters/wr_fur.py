"""WILDRUSH character pipeline - species coat colours, markings, fur strands, fabric (venv).

Colour fields are evaluated at bind-pose 3D positions (see wr_texture.py).  Fur is
natural colour only (never palette driven, CHARACTER_CONTRACT §4).
"""
import math
import numpy as np
from wr_sdf import perlin3, fbm3, eval_points

# ----------------------------------------------------------------------------- helpers


def srgb(h):
    h = h.lstrip("#")
    c = np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = np.asarray(t)
    if t.ndim == 1:
        t = t[:, None]
    return a * (1 - t) + b * t


def seg_param(P, a, b):
    ab = b - a
    L2 = ab @ ab
    t = ((P - a) @ ab) / L2
    C = a + np.clip(t, 0, 1)[:, None] * ab
    return t, np.linalg.norm(P - C, axis=1), math.sqrt(L2)


def polyline_dist(P, pts):
    pts = np.asarray(pts, dtype=np.float64)
    best = np.full(len(P), 1e9)
    for a, b in zip(pts[:-1], pts[1:]):
        _, d, _ = seg_param(P, a, b)
        best = np.minimum(best, d)
    return best


PARTS = ["head", "torso", "arm_Left", "arm_Right", "hand_Left", "hand_Right", "leg_Left", "leg_Right",
         "foot_Left", "foot_Right", "tail"]


def memberships(F, P, sigma=0.006):
    D = np.stack([eval_points(F.parts[p], P, cell=0.08, m=0.05) for p in PARTS], 1)
    D = np.maximum(D, 0.0)
    D = D - D.min(axis=1, keepdims=True)
    W = np.exp(-D / sigma)
    return W / W.sum(axis=1, keepdims=True)


class Ctx:
    """Everything a colour function needs about the texels."""

    def __init__(self, F, P, N, memb):
        self.F = F
        self.P = P
        self.N = N
        self.m = {p: memb[:, i] for i, p in enumerate(PARTS)}
        self.S = F.head_scale
        self.hl = F.head_frame.local(P) / self.S      # head-local, unscaled design units
        self.n = len(P)

    def arm(self, side):
        return self.m["arm_" + side] + self.m["hand_" + side]

    def leg(self, side):
        return self.m["leg_" + side] + self.m["foot_" + side]


def flow_field(F, C):
    """Fur direction per texel (unit, tangent to the surface)."""
    P, N = C.P, C.N
    fl = np.zeros_like(P)
    # head: from the nose backwards and a little down
    fl += C.m["head"][:, None] * np.array([0.0, 0.85, -0.45])
    fl += C.m["torso"][:, None] * np.array([0.0, 0.0, -1.0])
    for side in ("Left", "Right"):
        J = F.J
        a = (J[side + "Wrist"] - J[side + "Shoulder"])
        a /= np.linalg.norm(a)
        fl += (C.m["arm_" + side] + C.m["hand_" + side])[:, None] * a
        fl += C.m["leg_" + side][:, None] * np.array([0.0, 0.0, -1.0])
        fd = F.foot_frames[side]["dir"]
        fl += C.m["foot_" + side][:, None] * fd
    if hasattr(F, "tail_param"):
        s, dist, ang, tg = F.tail_param.project(P)
        fl += C.m["tail"][:, None] * tg
    fl = fl - N * np.einsum("ij,ij->i", fl, N)[:, None]
    n = np.linalg.norm(fl, axis=1, keepdims=True)
    fallback = np.cross(N, np.array([1.0, 0.0, 0.0]))
    fl = np.where(n > 1e-6, fl / np.maximum(n, 1e-9), fallback)
    return fl


def strand_height(F, spec, flow):
    k_across = spec.get("strand_across", 1.0 / 0.0019)
    k_along = spec.get("strand_along", 1.0 / 0.014)

    def h(P):
        along = np.einsum("ij,ij->i", P, flow)
        across = P - flow * along[:, None]
        Q = across * k_across + flow * (along * k_along)[:, None]
        n1 = perlin3(Q, 1.0, 101)
        n2 = perlin3(Q * np.array([0.5, 0.5, 0.5]), 1.0, 202)
        return np.clip(0.65 * n1 + 0.35 * n2, -1, 1)
    return h


# ----------------------------------------------------------------------------- common features
def eye_features(F, C):
    """(liner, halo): dark lid rim and pale ring around the eyes."""
    liner = np.zeros(C.n)
    halo = np.zeros(C.n)
    for e in F.eyes:
        d = np.linalg.norm(C.P - np.array(e["center"]), axis=1) - e["radius"]
        liner = np.maximum(liner, ss(0.0034 * C.S, 0.0022 * C.S, d))
        halo = np.maximum(halo, ss(0.0105 * C.S, 0.0060 * C.S, d) * (1 - ss(0.0040 * C.S, 0.0028 * C.S, d)))
    return liner, halo


def mouth_features(F, C):
    """(lipline, cavity, tongue) masks from the mouth frame."""
    m = F.mouth
    o = np.array(m["frame_o"])
    R = np.array(m["frame_R"])
    q = (C.P - o) @ R
    back = m["back"]
    inside_front = q[:, 1] > back - 0.002
    lip = ss(0.0031, 0.0021, np.abs(q[:, 2])) * inside_front * C.m["head"]
    nz = C.N @ R[:, 2]
    facing = np.where(q[:, 2] >= 0, -nz, nz)          # normal points toward the slit plane
    cav = ss(0.1, 0.5, facing) * ss(-0.001, -0.004, q[:, 1]) * ss(0.016, 0.010, np.abs(q[:, 2]))
    cav *= ss(m["half_w"] * 1.1, m["half_w"] * 0.8, np.abs(q[:, 0])) * C.m["head"]
    cav = np.maximum(cav, lip * ss(-0.0005, -0.003, q[:, 1]))
    tng = np.linalg.norm(C.P - np.array(m["tongue"]), axis=1)
    tongue = ss(0.012 * C.S, 0.006 * C.S, tng) * cav
    return lip, cav, tongue


def nose_mask(F, C, r=0.012):
    d = np.linalg.norm(C.P - np.array(F.mouth["nose"]), axis=1)
    return ss(r * C.S, r * 0.75 * C.S, d) * C.m["head"]


def ear_masks(F, C):
    """(inner, back, tip_t) for both ears."""
    inner = np.zeros(C.n)
    back = np.zeros(C.n)
    tip = np.zeros(C.n)
    for side in ("Left", "Right"):
        ef = F.ear_frames[side]
        Ef = ef["frame"]
        q = Ef.local(C.P)
        L = ef["length"]
        t = np.clip(q[:, 1] / L, 0, 1.2)
        onear = (q[:, 1] > 0.004) & (np.abs(q[:, 2]) < 0.03) & C.m["head"].astype(bool)
        front = np.einsum("ij,j->i", C.N, Ef.R[:, 2])
        inner = np.maximum(inner, onear * ss(0.05, 0.4, front) * ss(0.0, 0.08, t))
        back = np.maximum(back, onear * ss(0.1, -0.3, front) * ss(0.02, 0.2, t))
        tip = np.maximum(tip, onear * t)
    return inner, back, tip


def pad_masks(F, C):
    """Paw pads: palm + fingertips (hands), toe beans + sole (feet)."""
    pads = np.zeros(C.n)
    for side in ("Left", "Right"):
        hf = F.hand_frames[side]
        n = hf["n"]
        facing = ss(0.35, 0.75, np.einsum("ij,j->i", C.N, n))
        wr = hf["wrist"]
        a = hf["a"]
        L = F.p["palm_len"]
        pc = wr + a * (L * 0.55) + n * (F.p["hand_t"] * 0.35)
        d = np.linalg.norm((C.P - pc) - np.outer((C.P - pc) @ a, a) * 0.55, axis=1)
        palm = ss(F.p["hand_w"] * 0.40, F.p["hand_w"] * 0.30, d)
        tips = np.zeros(C.n)
        for fn, fd in hf["fingers"].items():
            k2 = fd["joints"][2]
            dd = np.linalg.norm(C.P - k2, axis=1)
            tips = np.maximum(tips, ss(F.p["finger_r"] * 1.35, F.p["finger_r"] * 0.9, dd))
        hand = C.m["hand_" + side]
        pads = np.maximum(pads, hand * facing * np.maximum(palm, tips))
        foot = C.m["foot_" + side]
        sole = ss(0.012, 0.004, C.P[:, 2]) * ss(-0.2, -0.6, C.N[:, 2])
        pads = np.maximum(pads, foot * sole)
    return pads


def tail_coords(F, P):
    s, dist, ang, tg = F.tail_param.project(P)
    return s, ang


def limb_t(F, side, P):
    J = F.J
    t1, d1, L1 = seg_param(P, J[side + "Shoulder"], J[side + "Elbow"])
    t2, d2, L2 = seg_param(P, J[side + "Elbow"], J[side + "Wrist"])
    # arc length from the shoulder
    s = np.where(t1 < 1.0, t1 * L1, L1 + t2 * L2)
    return s


def leg_s(F, side, P):
    J = F.J
    t1, d1, L1 = seg_param(P, J[side + "Hip"], J[side + "Knee"])
    t2, d2, L2 = seg_param(P, J[side + "Knee"], J[side + "Ankle"])
    return np.where(t1 < 1.0, t1 * L1, L1 + t2 * L2)


def bands(s, period, duty, P, warp=0.35, seed=0, freq=25.0):
    """Irregular stripes across a 1D coordinate s (metres)."""
    w = perlin3(P * freq, 1.0, seed) * warp
    ph = (s / period + w) % 1.0
    edge = 0.08
    return ss(duty * 0.5 + edge * 0.5, duty * 0.5 - edge * 0.5, np.abs(ph - 0.5))


# ----------------------------------------------------------------------------- species colour functions
def colour_cat(F, spec, C):
    P, hl = C.P, C.hl
    base = mix(srgb(spec["base_dark"]), srgb(spec["base"]), 0.5 + 0.5 * fbm3(P, 9.0, 3, 5))
    dark = srgb(spec["stripe"])
    pale = srgb(spec["pale"])
    col = base.copy()
    head = C.m["head"]
    # --- pale areas: muzzle / chin / throat / chest / paws
    pads_c = [np.array([s * 0.0168, 0.087, -0.031]) for s in (1, -1)]
    dmuz = np.min([np.linalg.norm(hl - c, axis=1) for c in pads_c], axis=0) - 0.0186
    muz = ss(0.006, 0.000, dmuz)
    chin = ss(-0.040, -0.050, hl[:, 2]) * ss(0.015, 0.045, hl[:, 1])
    throat = ss(-0.058, -0.080, hl[:, 2]) * ss(0.040, 0.016, np.abs(hl[:, 0])) * ss(-0.02, 0.03, hl[:, 1])
    brow_pale = ss(0.02, 0.0, np.abs(hl[:, 2] - 0.005)) * ss(0.06, 0.07, hl[:, 1]) * 0
    paleness = np.maximum.reduce([muz, chin, throat]) * head
    neckfront = C.m["torso"] * ss(-0.02, -0.08, P[:, 1] - F.J["Neck"][1]) * ss(F.J["Neck"][2] - 0.10, F.J["Neck"][2], P[:, 2])
    paleness = np.maximum(paleness, neckfront)
    # paws: fingers and toes pale, wrists grey
    for side in ("Left", "Right"):
        hf = F.hand_frames[side]
        s_hand = (P - hf["wrist"]) @ hf["a"]
        paleness = np.maximum(paleness, C.m["hand_" + side] * ss(0.02, 0.06, s_hand) * 0.85)
        ff = F.foot_frames[side]
        s_ft = (P - ff["ankle"]) @ ff["dir"]
        paleness = np.maximum(paleness, C.m["foot_" + side] * ss(0.02, 0.08, s_ft) * 0.85)
    edge_noise = 0.15 * fbm3(P, 60.0, 2, 13)
    col = mix(col, pale, np.clip(paleness + edge_noise * (paleness > 0.05), 0, 1))
    # --- tabby stripes on the head: forehead "M" + lines over the skull
    top = ss(0.020, 0.040, hl[:, 2] + 0.25 * np.clip(0.07 - hl[:, 1], 0, None)) * head
    xw = hl[:, 0] + 0.004 * perlin3(P * 40, 1.0, 17)
    lines = np.zeros(C.n)
    for x0, w in ((0.0, 0.0036), (0.0110, 0.0032), (-0.0110, 0.0032), (0.0225, 0.0028), (-0.0225, 0.0028)):
        lines = np.maximum(lines, ss(w, w * 0.4, np.abs(xw - x0)))
    forehead_fade = ss(0.080, 0.060, hl[:, 1])
    head_str = lines * top * forehead_fade
    # cheek stripes from the outer eye corner sweeping back
    cheek = np.zeros(C.n)
    for s in (1, -1):
        for dz, dd in ((0.0, 0.0), (-0.016, 0.004)):
            pts = [np.array([s * 0.052, 0.050, 0.004 + dz]), np.array([s * 0.066, 0.025, -0.006 + dz]),
                   np.array([s * 0.076, -0.005, -0.020 + dz])]
            d = polyline_dist(hl, pts)
            cheek = np.maximum(cheek, ss(0.0034, 0.0014, d))
    cheek *= head * (1 - muz)
    # arms: bands around the forearm / upper arm, lighter on the inside
    arm_str = np.zeros(C.n)
    for side in ("Left", "Right"):
        s = limb_t(F, side, P)
        b = bands(s, 0.040, 0.30, P, warp=0.45, seed=31) * ss(-0.35, 0.15, perlin3(P * 18, 1.0, 32))
        inner = ss(0.2, 0.7, np.einsum("ij,j->i", C.N, np.array([-1.0 if side == "Left" else 1.0, 0, 0])))
        arm_str = np.maximum(arm_str, C.m["arm_" + side] * b * (1 - 0.7 * inner))
        # a couple of faint bands on the back of the hand
        hf = F.hand_frames[side]
        sh = (P - hf["wrist"]) @ hf["a"]
        arm_str = np.maximum(arm_str, C.m["hand_" + side] * bands(sh + 0.01, 0.028, 0.30, P, seed=33) * ss(0.045, 0.010, sh) * 0.8)
        # legs / ankles
        sl = leg_s(F, side, P)
        arm_str = np.maximum(arm_str, C.leg(side) * bands(sl, 0.048, 0.30, P, warp=0.45, seed=35) * ss(-0.35, 0.15, perlin3(P * 18, 1.0, 36)) * (1 - C.m["foot_" + side] * 0.7))
    # torso: mackerel stripes around the body (mostly hidden by clothes)
    ang = np.arctan2(P[:, 0], P[:, 1] - 0.02)
    tor = C.m["torso"] * ss(0.18, 0.08, np.abs(np.sin(ang * 3.5 + 2.5 * perlin3(P * 12, 1.0, 41))))
    # tail rings + dark tip
    s, tang = tail_coords(F, P)
    L = F.tail_param.L
    rings = bands(s, spec.get("tail_period", 0.085), 0.42, P, warp=0.18, seed=51, freq=14)
    tip = ss(L - 0.090, L - 0.060, s)
    tail_str = C.m["tail"] * np.maximum(rings * ss(0.03, 0.08, s), tip)
    stripes = np.clip(np.maximum.reduce([head_str, cheek, arm_str, tor, tail_str]), 0, 1)
    col = mix(col, dark, stripes * 0.92)
    # --- eyes, nose, mouth, ears, pads
    liner, halo = eye_features(F, C)
    col = mix(col, pale, halo * 0.8 * head)
    col = mix(col, srgb(spec["liner"]), liner * head)
    nose = nose_mask(F, C)
    col = mix(col, srgb(spec["nose"]), nose)
    lip, cav, tongue = mouth_features(F, C)
    col = mix(col, srgb(spec["lip"]), lip * 0.9)
    col = mix(col, srgb(spec["mouth"]), cav)
    col = mix(col, srgb(spec["tongue"]), tongue)
    inner, earback, tip_t = ear_masks(F, C)
    col = mix(col, srgb(spec["ear_back"]), earback * 0.75)
    inner_col = mix(srgb(spec["inner_ear"]), pale, ss(0.45, 0.15, tip_t) * 0.6)
    col = mix(col, inner_col, inner)
    col = mix(col, srgb(spec["pad"]), pad_masks(F, C))
    return col


COLOUR_FUNCS = {"cat": colour_cat}


def fur_colour(F, spec, P, N, memb):
    C = Ctx(F, P, N, memb)
    fn = COLOUR_FUNCS[F.p["species"]]
    col = fn(F, spec, C)
    flow = flow_field(F, C)
    return col, flow


# ----------------------------------------------------------------------------- cloth
def stitch_pattern(P, r, kind):
    line = ss(0.0014, 0.0004, np.abs(r + 0.0075))
    dash = (np.sin(2 * np.pi * (P[:, 0] * 0.8 + P[:, 1] * 1.1 + P[:, 2] * 1.3) / 0.0055) > -0.1).astype(float)
    return line * dash


def fabric_height(F):
    def f(P):
        k = 2 * np.pi / 0.0048
        weave = np.sin(P[:, 0] * k + P[:, 2] * k * 0.3) * np.sin(P[:, 2] * k - P[:, 1] * k * 0.3)
        grain = perlin3(P * 260.0, 1.0, 77)
        return 0.35 * weave + 0.65 * grain
    return f


def seam_height(F, P):
    return np.zeros(len(P))


# ----------------------------------------------------------------------------- specs
SPECS = {
    "nyx": dict(
        base="#77726b", base_dark="#5c5752", stripe="#2c2825", pale="#e6e0d5", liner="#221d1b",
        nose="#c48882", lip="#3a2b28", mouth="#4a1b1d", tongue="#c46a6e", inner_ear="#d2aca4",
        ear_back="#4a4541", pad="#5b4a49", tail_period=0.082,
        eye=dict(iris_outer="#c9832a", iris_inner="#f0c04a", pupil="slit", slit_w=0.15, iris_r=0.86),
        detail=dict(claw_base="#6a5f58", claw_tip="#ece6da", tooth="#efe7d6", whisker="#f3f1ec"),
    ),
}
