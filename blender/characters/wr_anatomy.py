"""WILDRUSH character pipeline - parametric anthropomorphic anatomy (venv).

Builds, for one fighter id:
  * the bind-pose skeleton (joint positions + bone list, CHARACTER_CONTRACT §3 names),
  * the body SDF (torso, limbs, paw-hands, feet, tail, species head with eye lids,
    mouth slit + cavity, nose, ears, cheek ruffs),
  * a smoothed clothing proxy SDF,
  * detail descriptors (eyes, claws, teeth, whiskers) and texture landmarks.

Bind pose: A-pose (arms 45 deg down), legs straight with a slight knee bend,
character faces -Y, Z up, origin between the feet (D-003).
"""
import math
import numpy as np
from wr_sdf import (v3, normalize, frame_from_axis, rot_x, rot_y, rot_z, Sphere, Ellipsoid,
                    RoundCone, Capsule, RoundBox, Torus, HalfSpace, Func, Union, Subtract,
                    Intersect, Shell, Offset, Displace, perlin3, fbm3, dot_rows, smin, smax)

FWD = np.array([0.0, -1.0, 0.0])
BACK = -FWD
UP = np.array([0.0, 0.0, 1.0])
LEFT = np.array([1.0, 0.0, 0.0])


class Frame:
    def __init__(self, o, x, y, z):
        self.o = v3(o)
        self.R = np.stack([normalize(x), normalize(y), normalize(z)], axis=1)

    def p(self, x, y, z):
        return self.o + self.R @ np.array([x, y, z], dtype=np.float64)

    def v(self, x, y, z):
        return self.R @ np.array([x, y, z], dtype=np.float64)

    def local(self, P):
        return (np.asarray(P) - self.o) @ self.R


def frame_yz(y, zhint):
    """Orthonormal frame (columns x, y, z) with y exact and z close to zhint."""
    y = normalize(y)
    z = normalize(v3(zhint) - y * np.dot(v3(zhint), y))
    return np.stack([np.cross(y, z), y, z], axis=1)


def lerp(a, b, t):
    return a + (b - a) * t


def mirror(p, s):
    p = v3(p).copy()
    p[0] *= s
    return p


class Local:
    """Evaluate a child defined in a local frame: Q = ((P - o) @ R) / s."""

    def __init__(self, child, o, R, s=(1.0, 1.0, 1.0)):
        self.child = child
        self.o = v3(o)
        self.R = np.asarray(R, dtype=np.float64)
        self.s = v3(s)
        # world bbox of the child's local bbox
        c = np.array([[x, y, z] for x in (child.lo[0], child.hi[0]) for y in (child.lo[1], child.hi[1])
                      for z in (child.lo[2], child.hi[2])])
        W = self.o + (c * self.s) @ self.R.T
        self.lo = W.min(axis=0)
        self.hi = W.max(axis=0)
        self.tag = None

    def ev(self, P, blo, bhi, m):
        Q = ((P - self.o) @ self.R) / self.s
        return self.child.ev(Q, Q.min(axis=0), Q.max(axis=0), m / self.s.min()) * self.s.min()


# =============================================================================
# Fighter parameter sets (metres).  Spec §6 heights / identities.
# =============================================================================
BASE = dict(
    sex="m",
    # vertical landmarks
    hip_z=0.89, knee_z=0.49, ankle_z=0.105, ankle_y=0.035, ball_y=-0.095, ball_z=0.030, toe_len=0.075,
    hip_x=0.092, knee_x=0.098, foot_x=0.100,
    pelvis_z=0.935, waist_z=1.06, rib_z=1.235, chest_z=1.275, neck_base_z=1.435, head_joint_z=1.525,
    sh_z=1.385, sh_x=0.160, clav_x=0.022,
    ua_len=0.285, fa_len=0.255, palm_len=0.080, fing_len=(0.034, 0.027), thumb_len=(0.030, 0.024),
    arm_down_deg=45.0,
    # masses (radii)
    pelvis_r=(0.140, 0.105, 0.105), waist_r=(0.112, 0.090, 0.110), rib_r=(0.135, 0.108, 0.150),
    pec_r=(0.068, 0.040, 0.055), bust=0.0, glute_r=(0.070, 0.062, 0.078), trap_r=(0.115, 0.060, 0.060),
    lat=0.0, belly=0.0,
    neck_r=(0.058, 0.048),
    delt_r=(0.052, 0.046, 0.064), ua_r=(0.047, 0.036), bicep=(0.030, 0.050, 0.030), tricep=(0.032, 0.060, 0.030),
    fa_r=(0.040, 0.027), fa_mass=(0.034, 0.065, 0.030),
    thigh_r=(0.085, 0.053), quad=(0.058, 0.110, 0.050), hams=(0.052, 0.105, 0.050), shin_r=(0.050, 0.033),
    calf=(0.042, 0.080, 0.040), knee_r=0.042,
    hand_w=0.074, hand_t=0.030, finger_r=0.0115, thumb_r=0.012, claw_len=0.014,
    foot_w=0.105, foot_r=(0.036, 0.040), toe_r=(0.021, 0.030, 0.020),
    # tail
    tail_n=6, tail_len=0.95, tail_r=(0.042, 0.036, 0.030, 0.028), tail_shape="cat",
    tail_base=(0.0, 0.085, 0.935),
    # head
    species="cat", head_c=(0.0, -0.012, 1.605), cran_r=(0.074, 0.082, 0.075),
    eye_r=0.0205,
)

FIGHTER_PARAMS = {
    "nyx": dict(
        sex="f", H=1.70, species="cat", head_scale=1.14,
        hip_z=0.885, knee_z=0.485, ankle_z=0.125, ankle_y=0.050, ball_y=-0.080, ball_z=0.030, toe_len=0.080,
        hip_x=0.092, knee_x=0.100, foot_x=0.104, foot_w=0.118, foot_r=(0.040, 0.044), toe_r=(0.024, 0.033, 0.022),
        pelvis_r=(0.145, 0.108, 0.105), waist_r=(0.112, 0.088, 0.110), rib_r=(0.132, 0.106, 0.145),
        pec_r=(0.058, 0.032, 0.046), bust=0.5, glute_r=(0.072, 0.064, 0.078), trap_r=(0.112, 0.058, 0.062),
        sh_x=0.158, sh_z=1.392, neck_base_z=1.445, head_joint_z=1.530, neck_r=(0.060, 0.050),
        delt_r=(0.054, 0.049, 0.066), ua_r=(0.050, 0.039), bicep=(0.032, 0.052, 0.032), tricep=(0.034, 0.062, 0.032),
        fa_r=(0.044, 0.032), fa_mass=(0.036, 0.068, 0.033),
        thigh_r=(0.092, 0.055), quad=(0.060, 0.115, 0.052), hams=(0.055, 0.105, 0.052), shin_r=(0.052, 0.034),
        calf=(0.045, 0.085, 0.043), knee_r=0.043,
        hand_w=0.086, hand_t=0.034, finger_r=0.0135, thumb_r=0.0142, palm_len=0.086, fing_len=(0.036, 0.030),
        tail_n=6, tail_len=0.92, tail_r=(0.042, 0.039, 0.036, 0.034), tail_shape="cat",
        head_c=(0.0, -0.010, 0.0), cran_r=(0.071, 0.078, 0.071), eye_r=0.0215,
        ear_len=0.078, ear_w=0.062,
    ),
    "bruno": dict(
        sex="m", H=1.77, species="dog",
        hip_z=0.865, knee_z=0.470, ankle_z=0.100, hip_x=0.110, knee_x=0.112, foot_x=0.118,
        ball_y=-0.100, foot_w=0.125, foot_r=(0.043, 0.047), toe_r=(0.025, 0.033, 0.023),
        pelvis_z=0.915, waist_z=1.050, rib_z=1.255, chest_z=1.300, neck_base_z=1.480, head_joint_z=1.575,
        sh_z=1.440, sh_x=0.205, clav_x=0.030,
        ua_len=0.290, fa_len=0.270, palm_len=0.092, fing_len=(0.037, 0.030), thumb_len=(0.033, 0.027),
        pelvis_r=(0.150, 0.115, 0.110), waist_r=(0.140, 0.112, 0.120), rib_r=(0.168, 0.130, 0.165),
        pec_r=(0.085, 0.050, 0.065), glute_r=(0.078, 0.068, 0.080), trap_r=(0.150, 0.075, 0.075), lat=1.0,
        neck_r=(0.080, 0.068),
        delt_r=(0.080, 0.070, 0.086), ua_r=(0.068, 0.053), bicep=(0.052, 0.066, 0.049), tricep=(0.054, 0.076, 0.048),
        fa_r=(0.064, 0.044), fa_mass=(0.060, 0.088, 0.054),
        thigh_r=(0.104, 0.066), quad=(0.072, 0.118, 0.064), hams=(0.066, 0.112, 0.060), shin_r=(0.066, 0.045),
        calf=(0.058, 0.088, 0.055), knee_r=0.054,
        hand_w=0.096, hand_t=0.040, finger_r=0.0155, thumb_r=0.0160, claw_len=0.013,
        tail_n=3, tail_len=0.30, tail_r=(0.052, 0.046, 0.036, 0.026), tail_shape="dog", tail_base=(0.0, 0.100, 0.915),
        head_c=(0.0, -0.010, 0.0), cran_r=(0.080, 0.086, 0.078), eye_r=0.0175, head_scale=1.10,
        ear_len=0.105, ear_w=0.070,
    ),
    "vex": dict(
        sex="m", H=1.73, species="fox",
        hip_z=0.905, knee_z=0.500, ankle_z=0.112, hip_x=0.090, knee_x=0.095, foot_x=0.098,
        pelvis_z=0.950, waist_z=1.075, rib_z=1.255, chest_z=1.290, neck_base_z=1.455, head_joint_z=1.545,
        sh_z=1.405, sh_x=0.162,
        pelvis_r=(0.130, 0.100, 0.100), waist_r=(0.108, 0.086, 0.110), rib_r=(0.135, 0.108, 0.150),
        pec_r=(0.065, 0.038, 0.052), glute_r=(0.064, 0.058, 0.072), trap_r=(0.110, 0.056, 0.058),
        neck_r=(0.052, 0.044),
        delt_r=(0.048, 0.043, 0.060), ua_r=(0.042, 0.032), bicep=(0.027, 0.048, 0.027), tricep=(0.029, 0.058, 0.027),
        fa_r=(0.036, 0.025), fa_mass=(0.030, 0.062, 0.027),
        thigh_r=(0.078, 0.047), quad=(0.050, 0.110, 0.045), hams=(0.046, 0.100, 0.044), shin_r=(0.044, 0.028),
        calf=(0.036, 0.080, 0.034), knee_r=0.037,
        hand_w=0.068, hand_t=0.027, finger_r=0.0103, thumb_r=0.0108,
        tail_n=6, tail_len=1.00, tail_r=(0.050, 0.095, 0.105, 0.045), tail_shape="fox", tail_base=(0.0, 0.085, 0.950),
        head_c=(0.0, -0.012, 0.0), cran_r=(0.066, 0.078, 0.068), eye_r=0.0185, head_scale=1.12,
        ear_len=0.112, ear_w=0.074,
    ),
    "hops": dict(
        sex="f", H=1.67, species="rabbit",
        hip_z=0.860, knee_z=0.470, ankle_z=0.085, ankle_y=0.055, ball_y=-0.135, ball_z=0.026, toe_len=0.085,
        hip_x=0.095, knee_x=0.100, foot_x=0.105, foot_w=0.100, foot_r=(0.034, 0.036), toe_r=(0.020, 0.036, 0.019),
        pelvis_z=0.905, waist_z=1.035, rib_z=1.205, chest_z=1.245, neck_base_z=1.400, head_joint_z=1.490,
        sh_z=1.350, sh_x=0.145,
        pelvis_r=(0.140, 0.105, 0.105), waist_r=(0.100, 0.082, 0.105), rib_r=(0.120, 0.098, 0.138),
        pec_r=(0.052, 0.030, 0.043), bust=0.5, glute_r=(0.074, 0.066, 0.080), trap_r=(0.098, 0.050, 0.052),
        neck_r=(0.049, 0.042),
        delt_r=(0.044, 0.040, 0.055), ua_r=(0.039, 0.030), bicep=(0.025, 0.045, 0.024), tricep=(0.026, 0.055, 0.024),
        fa_r=(0.034, 0.024), fa_mass=(0.028, 0.060, 0.025), ua_len=0.275, fa_len=0.245,
        thigh_r=(0.095, 0.052), quad=(0.064, 0.120, 0.056), hams=(0.058, 0.110, 0.054), shin_r=(0.048, 0.030),
        calf=(0.042, 0.085, 0.040), knee_r=0.040,
        hand_w=0.064, hand_t=0.026, finger_r=0.0100, thumb_r=0.0105,
        tail_n=2, tail_len=0.10, tail_r=(0.050, 0.070, 0.060, 0.040), tail_shape="rabbit", tail_base=(0.0, 0.110, 0.905),
        head_c=(0.0, -0.014, 0.0), cran_r=(0.066, 0.078, 0.070), eye_r=0.0200, head_scale=1.12,
        ear_len=0.34, ear_w=0.072,
    ),
    "scrap": dict(
        sex="m", H=1.63, species="raccoon",
        hip_z=0.815, knee_z=0.445, ankle_z=0.098, hip_x=0.100, knee_x=0.104, foot_x=0.108,
        foot_w=0.112, foot_r=(0.038, 0.042), toe_r=(0.022, 0.030, 0.021),
        pelvis_z=0.865, waist_z=0.990, rib_z=1.170, chest_z=1.210, neck_base_z=1.365, head_joint_z=1.445,
        sh_z=1.325, sh_x=0.172,
        ua_len=0.265, fa_len=0.250, palm_len=0.080,
        pelvis_r=(0.150, 0.112, 0.110), waist_r=(0.135, 0.108, 0.115), rib_r=(0.148, 0.118, 0.150),
        pec_r=(0.068, 0.042, 0.055), glute_r=(0.074, 0.066, 0.076), trap_r=(0.125, 0.066, 0.066), belly=1.0,
        neck_r=(0.066, 0.058),
        delt_r=(0.056, 0.050, 0.066), ua_r=(0.050, 0.039), bicep=(0.033, 0.050, 0.032), tricep=(0.035, 0.060, 0.032),
        fa_r=(0.050, 0.033), fa_mass=(0.044, 0.070, 0.040),
        thigh_r=(0.090, 0.056), quad=(0.060, 0.105, 0.052), hams=(0.056, 0.100, 0.052), shin_r=(0.052, 0.035),
        calf=(0.046, 0.075, 0.044), knee_r=0.044,
        hand_w=0.076, hand_t=0.031, finger_r=0.0118, thumb_r=0.0122, claw_len=0.016,
        tail_n=6, tail_len=0.78, tail_r=(0.060, 0.085, 0.082, 0.055), tail_shape="raccoon", tail_base=(0.0, 0.095, 0.865),
        head_c=(0.0, -0.012, 0.0), cran_r=(0.074, 0.078, 0.070), eye_r=0.0180, head_scale=1.10,
        ear_len=0.064, ear_w=0.054,
    ),
}


def params(fid):
    p = dict(BASE)
    p.update(FIGHTER_PARAMS[fid])
    S = p.get("head_scale", 1.0)
    hc = list(p["head_c"])
    # crown of the cranium (excluding ears) exactly at H (CHARACTER_CONTRACT §2)
    hc[2] = p["H"] - (0.004 + p["cran_r"][2]) * S
    p["head_c"] = tuple(hc)
    p["head_joint_z"] = min(p["head_joint_z"], hc[2] - 0.070 * S)
    return p


# =============================================================================
class Fighter:
    def __init__(self, fid):
        self.id = fid
        self.p = params(fid)
        self.J = {}            # joint positions
        self.bones = []        # (name, head, tail, parent, zhint, deform)
        self.parts = {}        # named SDF nodes (for weights/texture regions)
        self.eyes = []         # dict(center, radius, axis, up)
        self.claws = []        # dict(base, dir, length, radius, bone)
        self.teeth = []        # dict(base, dir, length, radius, bone)
        self.whiskers = []     # dict(base, dir, length)
        self.landmarks = {}
        self.hand_frames = {}
        self.foot_frames = {}
        self.tail_pts = None
        self.tail_radii = None
        self.head_frame = None
        self.mouth = {}
        self.ear_frames = {}

    # ------------------------------------------------------------------ bones
    def add_bone(self, name, head, tail, parent, zhint, deform=True):
        self.bones.append(dict(name=name, head=v3(head).tolist(), tail=v3(tail).tolist(), parent=parent,
                               zhint=normalize(zhint).tolist(), deform=deform))


# =============================================================================
def build_skeleton(F):
    p = F.p
    J = F.J
    # legs
    for s, side in ((1, "Left"), (-1, "Right")):
        hip = np.array([s * p["hip_x"], 0.0, p["hip_z"]])
        knee = np.array([s * p["knee_x"], -0.028, p["knee_z"]])
        ankle = np.array([s * p["foot_x"], p["ankle_y"], p["ankle_z"]])
        ball = np.array([s * p["foot_x"], p["ball_y"], p["ball_z"]])
        toe = np.array([s * p["foot_x"], p["ball_y"] - p["toe_len"], 0.020])
        J[side + "Hip"], J[side + "Knee"], J[side + "Ankle"], J[side + "Ball"], J[side + "Toe"] = hip, knee, ankle, ball, toe
    # spine
    J["Pelvis"] = np.array([0.0, 0.0, p["pelvis_z"]])
    J["Spine"] = np.array([0.0, 0.004, p["waist_z"] - 0.045])
    J["Chest"] = np.array([0.0, 0.010, lerp(p["waist_z"], p["rib_z"], 0.45)])
    J["UpperChest"] = np.array([0.0, 0.012, p["rib_z"] + 0.03])
    J["Neck"] = np.array([0.0, 0.010, p["neck_base_z"]])
    J["HeadJ"] = np.array([0.0, 0.004, p["head_joint_z"]])
    J["Crown"] = np.array([0.0, p["head_c"][1] + 0.01, p["H"] - 0.004])
    # arms (A-pose)
    ad = math.radians(p["arm_down_deg"])
    for s, side in ((1, "Left"), (-1, "Right")):
        clav = np.array([s * p["clav_x"], -0.012, p["sh_z"] - 0.012])
        sh = np.array([s * p["sh_x"], 0.004, p["sh_z"]])
        adir = np.array([s * math.cos(ad), 0.0, -math.sin(ad)])
        elbow = sh + adir * p["ua_len"] + np.array([0.0, 0.012, 0.0])
        wrist = elbow + adir * p["fa_len"] + np.array([0.0, -0.022, 0.0])
        J[side + "Clav"], J[side + "Shoulder"], J[side + "Elbow"], J[side + "Wrist"] = clav, sh, elbow, wrist
        J[side + "ArmDir"] = normalize(wrist - elbow)
    return J


def build_bones(F):
    p = F.p
    J = F.J
    F.bones = []
    F.add_bone("Root", [0, 0, 0], [0, -0.25, 0], None, UP, deform=False)
    F.add_bone("Hips", J["Pelvis"], J["Spine"], "Root", FWD)
    F.add_bone("Spine", J["Spine"], J["Chest"], "Hips", FWD)
    F.add_bone("Chest", J["Chest"], J["UpperChest"], "Spine", FWD)
    F.add_bone("UpperChest", J["UpperChest"], J["Neck"], "Chest", FWD)
    F.add_bone("Neck", J["Neck"], J["HeadJ"], "UpperChest", FWD)
    F.add_bone("Head", J["HeadJ"], J["Crown"], "Neck", FWD)
    m = F.mouth
    F.add_bone("Jaw", m["pivot"], m["chin"], "Head", -UP)
    for s, side in ((1, "Left"), (-1, "Right")):
        ef = F.ear_frames[side]
        pts = ef["bone_pts"]
        prev = "Head"
        for i in range(len(pts) - 1):
            nm = f"{side}Ear{i + 1}"
            F.add_bone(nm, pts[i], pts[i + 1], prev, ef["front"])
            prev = nm
        F.add_bone(side + "Shoulder", J[side + "Clav"], J[side + "Shoulder"], "UpperChest", FWD)
        F.add_bone(side + "UpperArm", J[side + "Shoulder"], J[side + "Elbow"], side + "Shoulder", FWD)
        F.add_bone(side + "LowerArm", J[side + "Elbow"], J[side + "Wrist"], side + "UpperArm", FWD)
        hf = F.hand_frames[side]
        F.add_bone(side + "Hand", J[side + "Wrist"], hf["knuckle_mid"], side + "LowerArm", hf["n"])
        for fn in ("Thumb", "Index", "Middle", "Ring"):
            a, b, c = hf["fingers"][fn]["joints"]
            zh = hf["fingers"][fn]["curl_dir"]
            F.add_bone(f"{side}{fn}1", a, b, side + "Hand", zh)
            F.add_bone(f"{side}{fn}2", b, c, f"{side}{fn}1", zh)
    for s, side in ((1, "Left"), (-1, "Right")):
        F.add_bone(side + "UpperLeg", J[side + "Hip"], J[side + "Knee"], "Hips", FWD)
        F.add_bone(side + "LowerLeg", J[side + "Knee"], J[side + "Ankle"], side + "UpperLeg", FWD)
        F.add_bone(side + "Foot", J[side + "Ankle"], J[side + "Ball"], side + "LowerLeg", UP)
        F.add_bone(side + "Toes", J[side + "Ball"], J[side + "Toe"], side + "Foot", UP)
    # tail bones along the tail curve
    n = p["tail_n"]
    T = F.tail_pts
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(T, axis=0), axis=1))])
    marks = np.linspace(0, L[-1], n + 1)
    pts = [np.array([np.interp(mk, L, T[:, k]) for k in range(3)]) for mk in marks]
    prev = "Hips"
    for i in range(n):
        nm = f"Tail{i + 1}"
        F.add_bone(nm, pts[i], pts[i + 1], prev, UP)
        prev = nm
    F.landmarks["tail_bone_pts"] = [q.tolist() for q in pts]


# =============================================================================
# torso / limbs
# =============================================================================
def seg_frame(a, b, hint):
    y = normalize(v3(b) - v3(a))
    z = v3(hint) - y * np.dot(v3(hint), y)
    z = normalize(z)
    x = np.cross(y, z)
    return Frame(a, x, y, z)


def build_torso(F, proxy=False):
    p = F.p
    J = F.J
    parts = []
    pv = J["Pelvis"]
    pr = p["pelvis_r"]
    parts.append(Ellipsoid(pv + [0, 0.010, 0.0], pr))
    # glutes
    if not proxy:
        for s in (1, -1):
            g = p["glute_r"]
            parts.append(Ellipsoid([s * 0.062, 0.058, p["pelvis_z"] - 0.040], g,
                                   rot_y(s * 0.25) @ rot_x(0.25)))
    else:
        parts.append(Ellipsoid([0, 0.050, p["pelvis_z"] - 0.035], (0.13, 0.07, 0.085)))
    wr = p["waist_r"]
    parts.append(Ellipsoid([0, 0.004, p["waist_z"]], wr))
    rr = p["rib_r"]
    parts.append(Ellipsoid([0, 0.010, p["rib_z"]], rr, rot_x(-0.08)))
    if p["belly"] > 0:
        parts.append(Ellipsoid([0, -0.030, p["waist_z"] + 0.01], (wr[0] * 0.95, wr[1] * 1.05, wr[2] * 0.95)))
    # chest
    pc = p["pec_r"]
    if p["sex"] == "m":
        for s in (1, -1):
            parts.append(Ellipsoid([s * 0.058, -rr[1] * 0.62 + 0.010, p["chest_z"]], pc, rot_z(s * 0.25) @ rot_x(0.15)))
    else:
        for s in (1, -1):
            parts.append(Ellipsoid([s * 0.052, -rr[1] * 0.60 + 0.008, p["chest_z"] - 0.005], pc, rot_x(0.2)))
            if p["bust"] > 0 and not proxy:
                b = p["bust"]
                parts.append(Ellipsoid([s * 0.050, -rr[1] * 0.70, p["chest_z"] - 0.020],
                                       (0.042 * b + 0.018, 0.032 * b + 0.012, 0.040 * b + 0.016), rot_x(0.35)))
    # trapezius / upper back
    tr = p["trap_r"]
    parts.append(Ellipsoid([0, 0.040, p["sh_z"] - 0.030], tr, rot_x(0.25)))
    for s, side in ((1, "Left"), (-1, "Right")):
        parts.append(RoundCone(J[side + "Shoulder"] + [0, 0.012, 0.006], J["Neck"] + [s * 0.025, 0.018, 0.030],
                               p["delt_r"][0] * 0.75, p["neck_r"][0] * 0.8))
        # clavicle / shoulder girdle
        parts.append(RoundCone(J[side + "Clav"] + [0, 0.006, -0.010], J[side + "Shoulder"] + [0, -0.004, -0.008], 0.036,
                               p["delt_r"][0] * 0.78))
    if p["lat"] > 0:
        for s in (1, -1):
            parts.append(Ellipsoid([s * (rr[0] - 0.035), 0.035, p["rib_z"] + 0.02], (0.055, 0.060, 0.110), rot_z(s * 0.15)))
    # neck
    nr = p["neck_r"]
    parts.append(RoundCone(J["Neck"] + [0, 0.004, -0.030], J["HeadJ"] + [0, -0.006, 0.02], nr[0], nr[1]))
    k = 0.070 if proxy else 0.045
    return Union(parts, k=k)


def build_arm(F, side, proxy=False):
    p = F.p
    J = F.J
    s = 1 if side == "Left" else -1
    sh, el, wr = J[side + "Shoulder"], J[side + "Elbow"], J[side + "Wrist"]
    parts = []
    ua = seg_frame(sh, el, FWD)
    fa = seg_frame(el, wr, FWD)
    la = np.linalg.norm(el - sh)
    lf = np.linalg.norm(wr - el)
    if proxy:
        parts.append(RoundCone(sh, el, p["ua_r"][0] * 1.15, p["ua_r"][1] * 1.08))
        parts.append(RoundCone(el, wr, p["fa_r"][0] * 1.05, p["fa_r"][1] * 1.05))
        return Union(parts, k=0.05)
    d = p["delt_r"]
    parts.append(Ellipsoid(ua.p(0.0, 0.035, -0.004) + UP * 0.006, (d[0], d[2], d[1]), ua.R))
    parts.append(RoundCone(sh, el, p["ua_r"][0], p["ua_r"][1]))
    b = p["bicep"]
    parts.append(Ellipsoid(ua.p(0.0, la * 0.52, 0.014), (b[0], b[1], b[2]), ua.R))
    t = p["tricep"]
    parts.append(Ellipsoid(ua.p(0.0, la * 0.42, -0.014), (t[0], t[1], t[2]), ua.R))
    parts.append(Sphere(el + ua.v(0, 0, -0.012), p["ua_r"][1] * 0.82))
    parts.append(RoundCone(el, wr, p["fa_r"][0], p["fa_r"][1]))
    m = p["fa_mass"]
    # forearm mass: outer (back-of-hand) side near the elbow
    parts.append(Ellipsoid(fa.p(0.0, lf * 0.25, 0.004) + UP * 0.004, (m[0], m[1], m[2]), fa.R))
    parts.append(Ellipsoid(fa.p(0.0, lf * 0.30, -0.006), (m[0] * 0.8, m[1] * 0.9, m[2] * 0.85), fa.R))
    return Union(parts, k=0.022)


def build_hand(F, side):
    """Paw-hand: palm + thumb + 3 fingers, pads.  Returns (node, frame info)."""
    p = F.p
    J = F.J
    s = 1 if side == "Left" else -1
    wr = J[side + "Wrist"]
    a = J[side + "ArmDir"]                        # along the hand
    n = normalize(np.array([-s * 0.707, 0.0, -0.707]))  # palm normal (down/in)
    n = normalize(n - a * np.dot(n, a))
    fwd = normalize(np.cross(n, a)) * (1 if side == "Right" else -1)
    # make sure 'fwd' (thumb side) points forward (-Y)
    if fwd[1] > 0:
        fwd = -fwd
    hw, ht = p["hand_w"], p["hand_t"]
    L = p["palm_len"]
    parts = []
    palm_c = wr + a * (L * 0.50) + n * 0.002
    Rp = np.stack([fwd, a, n], axis=1)
    parts.append(Ellipsoid(palm_c, (hw * 0.52, L * 0.62, ht * 0.55), Rp))
    parts.append(Ellipsoid(wr + a * 0.012, (hw * 0.40, 0.030, ht * 0.50), Rp))
    # palm pad (large, palm side)
    parts.append(Ellipsoid(wr + a * (L * 0.55) + n * (ht * 0.35), (hw * 0.36, L * 0.30, ht * 0.28), Rp))
    knuckle_mid = wr + a * L
    fr = p["finger_r"]
    fingers = {}
    f1, f2 = p["fing_len"]
    curl0 = math.radians(14)
    spread = {"Index": 0.33, "Middle": 0.0, "Ring": -0.33}
    lens = {"Index": 0.96, "Middle": 1.04, "Ring": 0.90}
    for fn in ("Index", "Middle", "Ring"):
        off = spread[fn] * hw * 0.95
        k0 = knuckle_mid + fwd * off - a * (0.004 if fn != "Middle" else 0.0)
        fdir = normalize(a + fwd * spread[fn] * 0.22)
        # curl toward palm
        d1 = normalize(fdir * math.cos(curl0) + n * math.sin(curl0))
        k1 = k0 + d1 * f1 * lens[fn]
        d2 = normalize(fdir * math.cos(curl0 * 2.2) + n * math.sin(curl0 * 2.2))
        k2 = k1 + d2 * f2 * lens[fn]
        parts.append(RoundCone(k0 - d1 * 0.006, k1, fr * 1.08, fr * 0.98))
        parts.append(RoundCone(k1, k2 - d2 * fr * 0.35, fr * 0.98, fr * 0.86))
        # fingertip pad (palm side)
        parts.append(Sphere(k2 - d2 * fr * 0.9 + n * fr * 0.45, fr * 0.78))
        fingers[fn] = dict(joints=[k0, k1, k2], curl_dir=n, dir=d2)
        F.claws.append(dict(base=(k2 - d2 * fr * 0.55 - n * fr * 0.30).tolist(), dir=normalize(d2 * 0.75 + n * 0.65).tolist(),
                            length=p["claw_len"], radius=fr * 0.42, bone=f"{side}{fn}2", up=(-n).tolist()))
    # thumb
    t1, t2 = p["thumb_len"]
    tr = p["thumb_r"]
    tb = wr + a * (L * 0.18) + fwd * (hw * 0.42) + n * (ht * 0.10)
    tdir = normalize(a * 0.62 + fwd * 0.55 + n * 0.45)
    tk1 = tb + tdir * t1
    tdir2 = normalize(tdir * 0.8 + n * 0.35 + a * 0.2)
    tk2 = tk1 + tdir2 * t2
    parts.append(RoundCone(tb - tdir * 0.012, tk1, tr * 1.25, tr * 1.0))
    parts.append(RoundCone(tk1, tk2 - tdir2 * tr * 0.3, tr * 1.0, tr * 0.86))
    parts.append(Sphere(tk2 - tdir2 * tr * 0.9 + n * tr * 0.4, tr * 0.76))
    tcurl = normalize(np.cross(tdir, a)) if side == "Left" else normalize(np.cross(a, tdir))
    tcurl = normalize(n * 0.7 - fwd * 0.3)
    fingers["Thumb"] = dict(joints=[tb, tk1, tk2], curl_dir=tcurl, dir=tdir2)
    F.claws.append(dict(base=(tk2 - tdir2 * tr * 0.5 - n * tr * 0.3).tolist(), dir=normalize(tdir2 * 0.8 + n * 0.55).tolist(),
                        length=p["claw_len"] * 0.9, radius=tr * 0.42, bone=f"{side}Thumb2", up=(-n).tolist()))
    F.hand_frames[side] = dict(wrist=wr, a=a, n=n, fwd=fwd, knuckle_mid=knuckle_mid, fingers=fingers)
    return Union(parts, k=0.007)


def build_leg(F, side, proxy=False):
    p = F.p
    J = F.J
    s = 1 if side == "Left" else -1
    hip, knee, ankle = J[side + "Hip"], J[side + "Knee"], J[side + "Ankle"]
    th = seg_frame(hip, knee, FWD)
    sh = seg_frame(knee, ankle, FWD)
    lt = np.linalg.norm(knee - hip)
    ls = np.linalg.norm(ankle - knee)
    parts = []
    if proxy:
        parts.append(RoundCone(hip + [0, 0.0, 0.03], knee, p["thigh_r"][0] * 1.12, p["thigh_r"][1] * 1.12))
        parts.append(RoundCone(knee, ankle, p["shin_r"][0] * 1.1, p["shin_r"][1] * 1.25))
        return Union(parts, k=0.06)
    parts.append(RoundCone(hip + [0, 0.0, 0.025], knee, p["thigh_r"][0], p["thigh_r"][1]))
    q = p["quad"]
    parts.append(Ellipsoid(th.p(s * 0.004, lt * 0.42, 0.024), q, th.R))
    h = p["hams"]
    parts.append(Ellipsoid(th.p(0.0, lt * 0.40, -0.026), h, th.R))
    # outer thigh sweep
    parts.append(Ellipsoid(th.p(0.0, lt * 0.30, 0.0) + LEFT * s * 0.022, (q[0] * 0.7, q[1] * 0.9, q[2] * 0.8), th.R))
    parts.append(Sphere(knee + sh.v(0, 0.006, 0.018), p["knee_r"]))
    parts.append(RoundCone(knee, ankle, p["shin_r"][0], p["shin_r"][1]))
    c = p["calf"]
    parts.append(Ellipsoid(sh.p(0.0, ls * 0.28, -0.020), c, sh.R))
    return Union(parts, k=0.026)


def build_foot(F, side):
    p = F.p
    J = F.J
    s = 1 if side == "Left" else -1
    ankle, ball, toe = J[side + "Ankle"], J[side + "Ball"], J[side + "Toe"]
    fw = p["foot_w"]
    fr = p["foot_r"]
    parts = []
    # heel / hock
    parts.append(Sphere(ankle + BACK * 0.012 + UP * -0.004, fr[0] * 0.95))
    parts.append(RoundCone(ankle, ball + UP * 0.006, fr[0], fr[1]))
    # metatarsal pad mass (widening toward the ball)
    Rf = np.stack([LEFT, normalize(ball - ankle), normalize(np.cross(LEFT, normalize(ball - ankle)))], axis=1)
    parts.append(Ellipsoid(lerp(ankle, ball, 0.72) + UP * -0.002, (fw * 0.45, 0.05, fr[1] * 0.85), Rf))
    # toes (4 beans in an arc)
    tr = p["toe_r"]
    fdir = normalize(toe - ball)
    toe_pts = []
    for i, off in enumerate((-1.5, -0.5, 0.5, 1.5)):
        lat = off * fw * 0.235
        back = abs(off) * 0.010 + (0.006 if abs(off) > 1 else 0.0)
        c = ball + fdir * (np.linalg.norm(toe - ball) * 0.55 - back) + LEFT * lat + UP * (tr[2] * 0.55 - 0.004)
        parts.append(Ellipsoid(c, tr, frame_yz(fdir, UP)))
        toe_pts.append(c)
        F.claws.append(dict(base=(c + fdir * tr[1] * 0.75 + UP * tr[2] * 0.15).tolist(),
                            dir=normalize(fdir * 0.9 - UP * 0.35).tolist(), length=p["claw_len"] * 0.8,
                            radius=tr[0] * 0.30, bone=f"{side}Toes", up=UP.tolist()))
    foot = Union(parts, k=0.012)
    # flat sole at z = 0 (smooth)
    sole = HalfSpace([0, 0, 0.0], [0, 0, -1])
    foot = Intersect(foot, sole, k=0.006)
    F.foot_frames[side] = dict(ankle=ankle, ball=ball, toe=toe, toes=toe_pts, dir=fdir)
    return foot


def tail_curve(F):
    p = F.p
    base = v3(p["tail_base"])
    L = p["tail_len"]
    shape = p["tail_shape"]
    n = 40
    t = np.linspace(0, 1, n)
    if shape == "cat":
        # back and down, then a gentle upward hook near the tip
        ang = np.radians(-38 + 52 * t ** 1.4)          # pitch below horizontal
        yaw = np.radians(6 * np.sin(t * math.pi))
    elif shape == "fox":
        ang = np.radians(-40 + 28 * t)
        yaw = np.radians(4 * np.sin(t * math.pi))
    elif shape == "raccoon":
        ang = np.radians(-35 + 25 * t)
        yaw = np.zeros(n)
    elif shape == "dog":
        ang = np.radians(15 + 55 * t)                  # short, carried up with a gentle curl
        yaw = np.zeros(n)
    else:  # rabbit puff
        ang = np.radians(10 + 10 * t)
        yaw = np.zeros(n)
    dirs = np.stack([np.sin(yaw) * np.cos(ang), np.cos(yaw) * np.cos(ang), np.sin(ang)], axis=1)
    ds = L / (n - 1)
    pts = [base]
    for i in range(1, n):
        pts.append(pts[-1] + dirs[i - 1] * ds)
    return np.array(pts), t


def tail_radius_profile(F, t):
    r0, r1, r2, r3 = F.p["tail_r"]
    shape = F.p["tail_shape"]
    if shape == "fox":
        # narrow root, big brush, rounded tip
        r = np.interp(t, [0, 0.12, 0.45, 0.75, 0.93, 1.0], [r0, r0 * 1.25, r1, r2, r2 * 0.75, r3 * 0.5])
    elif shape == "raccoon":
        r = np.interp(t, [0, 0.15, 0.5, 0.85, 1.0], [r0, r1, r2, r2 * 0.9, r3 * 0.6])
    elif shape == "dog":
        r = np.interp(t, [0, 0.5, 1.0], [r0, r1 * 0.85, r3])
    elif shape == "rabbit":
        r = np.interp(t, [0, 0.5, 1.0], [r0, r1, r2])
    else:  # cat
        r = np.interp(t, [0, 0.1, 0.6, 0.95, 1.0], [r0, r1, r2, r3, r3 * 0.85])
    return r


class CurveParam:
    """Arc-length / rotation-minimising-frame parametrisation of a polyline (tails)."""

    def __init__(self, T):
        self.T = np.asarray(T, dtype=np.float64)
        seg = np.diff(self.T, axis=0)
        self.seglen = np.linalg.norm(seg, axis=1)
        self.tang = seg / self.seglen[:, None]
        self.s0 = np.concatenate([[0.0], np.cumsum(self.seglen)])
        self.L = self.s0[-1]
        # parallel-transport normals
        n = len(self.tang)
        N = np.zeros((n, 3))
        t0 = self.tang[0]
        ref = np.array([0.0, 0.0, 1.0]) if abs(t0[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        N[0] = normalize(ref - t0 * np.dot(ref, t0))
        for i in range(1, n):
            v = N[i - 1] - self.tang[i] * np.dot(N[i - 1], self.tang[i])
            N[i] = normalize(v)
        self.N = N
        self.B = np.cross(self.tang, N)

    def project(self, P, chunk=60000):
        """Returns s (arc length), radial distance, angle, tangent for each point."""
        if len(P) > chunk:
            outs = [self.project(P[i:i + chunk], chunk) for i in range(0, len(P), chunk)]
            return (np.concatenate([o[0] for o in outs]), np.concatenate([o[1] for o in outs]),
                    np.concatenate([o[2] for o in outs]), np.concatenate([o[3] for o in outs]))
        A = self.T[:-1][None, :, :]
        D = P[:, None, :] - A
        u = np.clip((D * self.tang[None]).sum(-1), 0.0, self.seglen[None, :])
        C = A + u[..., None] * self.tang[None]
        d2 = ((P[:, None, :] - C) ** 2).sum(-1)
        i = np.argmin(d2, axis=1)
        r = np.arange(len(P))
        ui = u[r, i]
        s = self.s0[i] + ui
        rel = P - C[r, i]
        dist = np.sqrt(d2[r, i])
        ang = np.arctan2((rel * self.B[i]).sum(1), (rel * self.N[i]).sum(1))
        return s, dist, ang, self.tang[i]


def build_tail(F):
    pts, t = tail_curve(F)
    r = tail_radius_profile(F, t)
    F.tail_pts = pts
    F.tail_radii = r
    shape = F.p["tail_shape"]
    parts = []
    if shape == "rabbit":
        parts.append(Ellipsoid(pts[0] + BACK * 0.030 + UP * 0.012, (0.056, 0.050, 0.058)))
        node = Union(parts, k=0.01)
    else:
        step = 3
        idx = list(range(0, len(pts) - 1, step)) + [len(pts) - 1]
        for i0, i1 in zip(idx[:-1], idx[1:]):
            parts.append(RoundCone(pts[i0], pts[i1], r[i0], r[i1]))
        node = Union(parts, k=0.02)
    amp = {"cat": 0.0028, "fox": 0.013, "raccoon": 0.010, "dog": 0.002, "rabbit": 0.008}[shape]
    cp = CurveParam(pts)
    F.tail_param = cp
    around = {"cat": 3.0, "fox": 4.0, "raccoon": 3.5, "dog": 2.0, "rabbit": 3.0}[shape]
    along = {"cat": 14.0, "fox": 9.0, "raccoon": 10.0, "dog": 12.0, "rabbit": 30.0}[shape]

    sawk = {"cat": 0.0, "fox": 0.25, "raccoon": 0.15, "dog": 0.0, "rabbit": 0.0}[shape]

    def clumps(P, cp=cp, amp=amp, around=around, along=along, sawk=sawk):
        s, dist, ang, tg = cp.project(P)
        # locks: periodic around the tail, elongated along it; sawtooth gives tip-ward tufts
        Q = np.stack([np.cos(ang) * around, np.sin(ang) * around, s * along], axis=1)
        nz = perlin3(Q, 1.0, 7) * 0.65 + perlin3(Q * 2.3, 1.0, 11) * 0.35
        f = np.clip(nz * 1.6, -1, 1)
        if sawk > 0:
            saw = ((s * along * 0.5 + perlin3(Q * 0.9, 1.0, 5) * 1.5) % 1.0)
            f = (1 - sawk) * f + sawk * (saw * 2.0 - 1.0)
        tipw = np.clip(s / cp.L, 0, 1)
        return amp * np.clip(f, -1, 1) * (0.6 + 0.4 * tipw)

    node = Displace(node, clumps, amp)
    F.parts["tail"] = node
    return node


# =============================================================================
# heads
# =============================================================================
def ellipse_prism(frame, cx, cy, rx, ry, depth_lo, depth_hi):
    """Elliptic cylinder along frame z (local coords), capped. Local frame: x right, y up, z forward."""
    def fn(P):
        q = frame.local(P)
        u = (q[:, 0] - cx) / rx
        v = (q[:, 1] - cy) / ry
        e = (np.sqrt(u * u + v * v) - 1.0) * min(rx, ry)
        cap = np.maximum(depth_lo - q[:, 2], q[:, 2] - depth_hi)
        return np.maximum(e, cap)
    R = max(rx, ry) + abs(cx) + abs(cy) + max(abs(depth_lo), abs(depth_hi))
    return Func(fn, frame.o - R, frame.o + R)


def eye_rig(F, Hf, s, ex, ey, ez, r, yaw_out, pitch, w_open, h_up, h_lo, tilt, lid_t=0.0034, lid_gap=0.0005):
    """Eyeball socket + lids.  Returns (lids node, socket node, eye dict).
    (ex, ey, ez) head-local eye centre (x = left, y = forward, z = up)."""
    c = Hf.p(s * ex, ey, ez)
    fwd = Hf.v(0, 1, 0)
    axis = normalize(rot_z(s * math.radians(yaw_out)) @ (rot_x(math.radians(pitch)) @ fwd))
    upv = normalize(Hf.v(0, 0, 1) - axis * np.dot(Hf.v(0, 0, 1), axis))
    rightv = np.cross(upv, axis)   # eye-local x
    # eye-local frame: x across, y up, z = axis (forward); tilt rotates the almond (outer corner up)
    ang = math.radians(tilt) * s
    xa = rightv * math.cos(ang) + upv * math.sin(ang)
    ya = -rightv * math.sin(ang) + upv * math.cos(ang)
    ef = Frame(c, xa, ya, axis)
    # almond opening = intersection of two big circles (vesica): upper arc from a circle centred below
    R1 = (w_open ** 2 + h_up ** 2) / (2 * h_up)
    R2 = (w_open ** 2 + h_lo ** 2) / (2 * h_lo)

    def opening(P):
        q = ef.local(P)
        d1 = np.sqrt(q[:, 0] ** 2 + (q[:, 1] - (h_up - R1)) ** 2) - R1
        d2 = np.sqrt(q[:, 0] ** 2 + (q[:, 1] + (h_lo - R2)) ** 2) - R2
        front = -q[:, 2] - r * 0.1
        return np.maximum(np.maximum(d1, d2), front)
    op = Func(opening, c - 0.06, c + 0.06)
    lid_shell = Shell(Sphere(c, r + lid_gap + lid_t * 0.5), 0.0, lid_t * 0.5)
    lids = Subtract(lid_shell, op, k=0.0025)
    # only keep the lids in the front half (the rest is buried in the head anyway)
    lids = Intersect(lids, HalfSpace(c - axis * r * 0.3, -axis), k=0.003)
    socket = Sphere(c, r + lid_gap)
    eye = dict(center=c.tolist(), radius=r, axis=axis.tolist(), up=ya.tolist(), side=s)
    F.eyes.append(eye)
    return lids, socket, ef


def ear_node(F, Hf, s, base_hl, length, width, thick, tilt_out, tilt_back, twist, shape, n_bones):
    """Ear in its own frame. base_hl = head-local base centre."""
    base = Hf.p(s * base_hl[0], base_hl[1], base_hl[2])
    upv = Hf.v(0, 0, 1)
    # tilt: outward (roll) and back (pitch)
    R = rot_y(s * math.radians(tilt_out)) @ rot_x(-math.radians(tilt_back))
    ey = normalize(R @ upv)
    efr = normalize(rot_z(s * math.radians(twist)) @ (R @ Hf.v(0, 1, 0)))
    efr = normalize(efr - ey * np.dot(efr, ey))
    ex = s * np.cross(ey, efr)          # mirrored frame on the right side
    Ef = Frame(base, ex, ey, efr)
    parts = []
    if shape == "pointed":      # cat / fox
        outer = RoundCone([0, 0, 0], [0, length, 0], width * 0.5, 0.0035)
        outer_s = Local(outer, [0, 0, 0], np.eye(3), (1.0, 1.0, thick / width))
        inner = RoundCone([0, 0.012, 0], [0, length * 0.93, 0], width * 0.41, 0.002)
        inner_s = Local(inner, [0, 0, thick * 0.55], np.eye(3), (1.0, 1.0, thick * 0.9 / width))
        ear_local = Subtract(outer_s, inner_s, k=0.004)
        pts_local = [np.array([0, 0.0, 0]), np.array([0, length * 0.45, 0]), np.array([0, length * 0.98, 0])]
    elif shape == "round":      # raccoon
        outer = Ellipsoid([0, length * 0.45, 0], (width * 0.5, length * 0.62, thick * 0.5))
        inner = Ellipsoid([0, length * 0.52, thick * 0.45], (width * 0.38, length * 0.50, thick * 0.45))
        ear_local = Subtract(outer, inner, k=0.004)
        ear_local = Intersect(ear_local, HalfSpace([0, -0.005, 0], [0, -1, 0]), k=0.004)
        pts_local = [np.array([0, 0.0, 0]), np.array([0, length * 0.45, 0]), np.array([0, length * 1.02, 0])]
    elif shape == "long":       # rabbit: long leaf with near-constant width and a rounded tip, 3 bones
        segs = [(0.00, 0.30), (0.18, 0.46), (0.55, 0.50), (0.82, 0.44), (0.97, 0.26)]
        o = Union([RoundCone([0, length * a0, 0], [0, length * a1, 0], width * r0, width * r1)
                   for (a0, r0), (a1, r1) in zip(segs[:-1], segs[1:])], k=0.02)
        outer_s = Local(o, [0, 0, 0], np.eye(3), (1.0, 1.0, thick / width))
        isegs = [(0.10, 0.20), (0.22, 0.34), (0.55, 0.38), (0.80, 0.33), (0.93, 0.16)]
        i2 = Union([RoundCone([0, length * a0, 0], [0, length * a1, 0], width * r0, width * r1)
                    for (a0, r0), (a1, r1) in zip(isegs[:-1], isegs[1:])], k=0.02)
        inner_s = Local(i2, [0, 0, thick * 0.62], np.eye(3), (1.0, 1.0, thick * 0.80 / width))
        ear_local = Subtract(outer_s, inner_s, k=0.005)
        pts_local = [np.array([0, 0.0, 0]), np.array([0, length * 0.33, 0]), np.array([0, length * 0.66, 0]),
                     np.array([0, length * 0.99, 0])]
    elif shape == "folded":     # dog: short rise, then a broad flap folding down beside the eye
        fold = np.array([0.030, length * 0.20, 0.0])
        up_part = RoundCone([0, 0, 0], fold, width * 0.28, width * 0.30)
        up_s = Local(up_part, [0, 0, 0], np.eye(3), (1.0, 1.0, thick * 1.4 / width))
        # flap: flattened ellipsoid hanging outward-down-forward from the fold, outside the skull
        tip = fold + np.array([0.052, -length * 0.62, length * 0.26])
        fy = normalize(tip - fold)
        fz = normalize(np.cross(fy, np.array([0.0, 0.0, 1.0])))      # flap normal ~ outward (local x)
        fz = normalize(np.array([1.0, 0.0, 0.0]) - fy * np.dot(np.array([1.0, 0.0, 0.0]), fy))
        fx = np.cross(fy, fz)
        Rf = np.stack([fx, fy, fz], axis=1)
        mid = (fold + tip) * 0.5
        flap = Local(Ellipsoid([0, 0, 0], (width * 0.50, np.linalg.norm(tip - fold) * 0.58, thick * 0.5)), mid, Rf, (1, 1, 1))
        ear_local = Union([up_s, flap], k=0.014)
        pts_local = [np.array([0, 0.0, 0]), fold, tip]
    else:
        raise ValueError(shape)
    # mirror the local x for the right side ear (Local frame handles world placement)
    node = Local(ear_local, base, Ef.R, (1.0, 1.0, 1.0))
    bone_pts = [Ef.p(*q) for q in pts_local]
    F.ear_frames["Left" if s > 0 else "Right"] = dict(frame=Ef, bone_pts=bone_pts, front=efr, length=length, shape=shape)
    return node


def mouth_parts(F, Hf, lip_y, lip_z, corner_y, half_w, gap, cavity, occl_pitch, tongue=True):
    """Occlusal plane slit + cavity. The slit plane passes through (0, lip_y, lip_z) head-local,
    tilted by occl_pitch (deg, positive = front edge lower). Returns (slit_node, cavity_node)."""
    o = Hf.p(0, lip_y, lip_z)
    pr = math.radians(occl_pitch)
    fwdv = Hf.v(0, math.cos(pr), -math.sin(pr))
    upv = Hf.v(0, math.sin(pr), math.cos(pr))
    lf = Hf.v(1, 0, 0)
    Mf = Frame(o, lf, fwdv, upv)
    front_len = 0.05
    back = corner_y - lip_y     # negative: corners behind the lip front

    def slit(P):
        q = Mf.local(P)
        taper = np.clip((q[:, 1] - back) / max(-back, 1e-4), 0.0, 1.0)
        g = gap * (0.30 + 0.70 * np.sqrt(taper))
        return np.maximum(back - q[:, 1], np.abs(q[:, 2]) - g * 0.5)
    sl = Func(slit, o - 0.09, o + 0.09)
    cav_c = Mf.p(0, -0.009 - cavity[1], -0.001)
    cav = Ellipsoid(cav_c, cavity, Mf.R)
    F.mouth.update(dict(frame_o=o.tolist(), frame_R=Mf.R.tolist(), back=back, half_w=half_w, lip_y=lip_y))
    return sl, cav, Mf


def fluff(center, radii, R, flow, amp, seed=0, f_across=58.0, f_along=14.0):
    """Fur ruff: ellipsoid with streaky outward tufts pointing along `flow`."""
    base = Ellipsoid(center, radii, R)
    fl = normalize(flow)
    c = v3(center)
    rmax = float(max(radii))

    def fn(P):
        rel = P - c
        along = rel @ fl
        across = rel - np.outer(along, fl)
        Q = across * f_across + np.outer(along * f_along, fl)
        n = perlin3(Q, 1.0, seed) * 0.7 + perlin3(Q * 2.1, 1.0, seed + 3) * 0.3
        side = np.clip(along / rmax + 0.35, 0.0, 1.0)
        return amp * 0.8 * np.clip(n * 1.5, -0.3, 1.0) * (0.3 + 0.7 * side)
    return Displace(base, fn, amp)


def clumps(base, dirs, length, r0, r1=0.0035, seed=0):
    """Fan of fat tapered fur clumps (reads as fluffy fur, not spikes)."""
    rng = np.random.RandomState(seed)
    out = []
    for i, d in enumerate(dirs):
        d = normalize(v3(d) + rng.normal(0, 0.08, 3))
        L = length * (0.8 + 0.4 * rng.rand())
        out.append(RoundCone(base, base + d * L, r0 * (0.85 + 0.3 * rng.rand()), r1))
    return out


def tufts(base, dirs, length, r0, r1=0.0012):
    """Tapered fur tufts (round cones) from base along each dir."""
    out = []
    for d in dirs:
        d = normalize(d)
        out.append(RoundCone(base, base + d * length, r0, r1))
    return out


def build_head(F):
    p = F.p
    sp = p["species"]
    hc = v3(p["head_c"])
    Hf = Frame(hc, LEFT, FWD, UP)
    F.head_frame = Hf
    S = p.get("head_scale", 1.0)
    cr = v3(p["cran_r"]) * S
    er = p["eye_r"] * S
    parts = []            # large masses (k=0.022*S)
    details = []          # muzzle features (small k)
    fur = []              # tufts
    subs = []

    def hp(x, y, z):
        return Hf.p(x * S, y * S, z * S)

    def R3(a, b, c):
        return v3(a, b, c) * S

    if sp == "cat":
        parts.append(Ellipsoid(hp(0, -0.010, 0.004), cr))
        parts.append(Ellipsoid(hp(0, 0.034, 0.016), R3(0.056, 0.046, 0.042)))           # forehead
        parts.append(Ellipsoid(hp(0, 0.028, -0.026), R3(0.050, 0.046, 0.040)))          # face mass
        for s in (1, -1):
            parts.append(Ellipsoid(hp(s * 0.046, 0.028, -0.024), R3(0.034, 0.036, 0.031)))            # cheekbones
            parts.append(Ellipsoid(hp(s * 0.030, 0.058, 0.029), R3(0.026, 0.017, 0.012), rot_z(s * -0.3)))  # brow
            fur.append(fluff(hp(s * 0.058, 0.000, -0.040), R3(0.027, 0.041, 0.035), rot_z(s * 0.45),
                             v3(s * 0.8, 0.5, -0.5), 0.007 * S, seed=21 + s))                          # cheek ruff
        parts.append(RoundCone(hp(0, 0.056, 0.012), hp(0, 0.094, -0.012), 0.022 * S, 0.0155 * S))  # bridge
        for s in (1, -1):
            details.append(Sphere(hp(s * 0.0168, 0.087, -0.031), 0.0186 * S))                    # whisker pads
            details.append(RoundCone(hp(s * 0.032, 0.016, -0.046), hp(s * 0.010, 0.064, -0.056), 0.015 * S, 0.010 * S))
        details.append(Ellipsoid(hp(0, 0.070, -0.057), R3(0.015, 0.018, 0.011)))                   # chin (recessed)
        nose_c = hp(0, 0.1075, -0.0115)
        details.append(Ellipsoid(nose_c, R3(0.0118, 0.0068, 0.0080), rot_x(0.35)))
        lip = dict(lip_y=0.099, lip_z=-0.0505, corner_y=0.062, half_w=0.030, gap=0.0036,
                   cavity=(0.020, 0.024, 0.008), pitch=10.0)
        eye_c = (0.0335, 0.0555, 0.0135)
        eye_kw = dict(yaw_out=11, pitch=-2, w_open=er * 0.97, h_up=er * 0.54, h_lo=er * 0.50, tilt=16)
        ear_kw = dict(base_hl=(0.044, -0.020, 0.054), length=p["ear_len"], width=p["ear_w"], thick=0.020,
                      tilt_out=19, tilt_back=6, twist=24, shape="pointed", n_bones=2)
        jaw_pivot = hp(0, -0.010, -0.038)
        chin = hp(0, 0.080, -0.060)
        teeth = [("upper", 0.012, 0.089, -0.045, 0.0060), ("lower", 0.0105, 0.082, -0.056, 0.0045)]
        whisk = dict(y=0.092, z=-0.030, x=0.024)
    elif sp == "fox":
        parts.append(Ellipsoid(hp(0, -0.010, 0.006), cr))
        parts.append(Ellipsoid(hp(0, 0.026, -0.014), R3(0.056, 0.052, 0.046)))                     # wedge face
        for s in (1, -1):
            parts.append(Ellipsoid(hp(s * 0.044, 0.018, -0.022), R3(0.036, 0.040, 0.032)))           # cheeks
            parts.append(Ellipsoid(hp(s * 0.027, 0.056, 0.026), R3(0.023, 0.016, 0.011), rot_z(s * -0.35)))
            fur.append(fluff(hp(s * 0.058, -0.006, -0.036), R3(0.034, 0.048, 0.038), rot_z(s * 0.55) @ rot_x(0.2),
                             v3(s * 0.8, 0.5, -0.45), 0.011 * S, seed=31 + s))
        parts.append(RoundCone(hp(0, 0.046, -0.012), hp(0, 0.124, -0.029), 0.037 * S, 0.0135 * S))  # wedge muzzle
        parts.append(RoundCone(hp(0, 0.038, 0.010), hp(0, 0.117, -0.019), 0.025 * S, 0.011 * S))    # bridge
        details.append(RoundCone(hp(0, 0.052, -0.040), hp(0, 0.110, -0.043), 0.023 * S, 0.009 * S))  # lower jaw
        nose_c = hp(0, 0.1295, -0.0275)
        details.append(Ellipsoid(nose_c, R3(0.0105, 0.0085, 0.0078), rot_x(0.25)))
        lip = dict(lip_y=0.112, lip_z=-0.037, corner_y=0.056, half_w=0.025, gap=0.0034,
                   cavity=(0.017, 0.032, 0.008), pitch=8.0)
        eye_c = (0.0315, 0.058, 0.010)
        eye_kw = dict(yaw_out=16, pitch=-4, w_open=er * 1.0, h_up=er * 0.52, h_lo=er * 0.46, tilt=18)
        ear_kw = dict(base_hl=(0.040, -0.022, 0.050), length=p["ear_len"], width=p["ear_w"], thick=0.026,
                      tilt_out=15, tilt_back=4, twist=16, shape="pointed", n_bones=2)
        jaw_pivot = hp(0, -0.012, -0.034)
        chin = hp(0, 0.106, -0.046)
        teeth = [("upper", 0.013, 0.102, -0.034, 0.0065), ("lower", 0.011, 0.095, -0.042, 0.005)]
        whisk = dict(y=0.104, z=-0.030, x=0.018)
    elif sp == "dog":
        parts.append(Ellipsoid(hp(0, -0.014, 0.012), cr))                                            # broad skull
        parts.append(Ellipsoid(hp(0, 0.036, 0.016), R3(0.058, 0.040, 0.040)))                        # forehead
        parts.append(Ellipsoid(hp(0, 0.020, -0.024), R3(0.060, 0.050, 0.048)))                        # face mass
        for s in (1, -1):
            parts.append(Ellipsoid(hp(s * 0.052, 0.016, -0.028), R3(0.036, 0.044, 0.040)))            # masseter / cheeks
            parts.append(Ellipsoid(hp(s * 0.031, 0.058, 0.031), R3(0.027, 0.017, 0.013), rot_z(s * -0.25)))  # brow ridge
        parts.append(RoundCone(hp(0, 0.052, 0.006), hp(0, 0.140, -0.012), 0.030 * S, 0.023 * S))      # bridge (after the stop)
        parts.append(Ellipsoid(hp(0, 0.104, -0.030), R3(0.037, 0.055, 0.029)))                        # muzzle mass
        for s in (1, -1):
            details.append(Ellipsoid(hp(s * 0.022, 0.114, -0.046), R3(0.019, 0.040, 0.019), rot_x(0.10)))  # flews
        details.append(Ellipsoid(hp(0, 0.100, -0.062), R3(0.023, 0.042, 0.013), rot_x(0.08)))              # lower jaw
        nose_c = hp(0, 0.1585, -0.0125)
        details.append(Ellipsoid(nose_c, R3(0.0225, 0.0140, 0.0160), rot_x(0.2)))
        lip = dict(lip_y=0.147, lip_z=-0.056, corner_y=0.054, half_w=0.038, gap=0.0040,
                   cavity=(0.028, 0.045, 0.010), pitch=4.0)
        eye_c = (0.0360, 0.060, 0.020)
        eye_kw = dict(yaw_out=12, pitch=-2, w_open=er * 0.95, h_up=er * 0.62, h_lo=er * 0.55, tilt=4)
        ear_kw = dict(base_hl=(0.054, -0.020, 0.052), length=p["ear_len"], width=p["ear_w"], thick=0.014,
                      tilt_out=30, tilt_back=0, twist=20, shape="folded", n_bones=2)
        jaw_pivot = hp(0, -0.012, -0.040)
        chin = hp(0, 0.132, -0.068)
        teeth = [("upper", 0.024, 0.144, -0.053, 0.008), ("lower", 0.021, 0.136, -0.062, 0.006)]
        whisk = dict(y=0.136, z=-0.035, x=0.030)
    elif sp == "rabbit":
        parts.append(Ellipsoid(hp(0, -0.004, 0.008), cr))
        parts.append(Ellipsoid(hp(0, 0.034, -0.018), R3(0.054, 0.050, 0.048)))
        for s in (1, -1):
            parts.append(Ellipsoid(hp(s * 0.044, 0.034, -0.030), R3(0.036, 0.036, 0.032)))            # chubby cheeks
            parts.append(Ellipsoid(hp(s * 0.030, 0.056, 0.024), R3(0.022, 0.016, 0.011), rot_z(s * -0.2)))
        parts.append(Ellipsoid(hp(0, 0.074, -0.020), R3(0.031, 0.032, 0.027)))                        # rounded muzzle
        for s in (1, -1):
            details.append(Sphere(hp(s * 0.0125, 0.093, -0.030), 0.0150 * S))                         # muzzle pads (split lip)
        details.append(Ellipsoid(hp(0, 0.080, -0.048), R3(0.015, 0.018, 0.012)))
        nose_c = hp(0, 0.1030, -0.0175)
        details.append(Ellipsoid(nose_c, R3(0.0088, 0.0058, 0.0064), rot_x(0.3)))
        lip = dict(lip_y=0.094, lip_z=-0.041, corner_y=0.066, half_w=0.021, gap=0.0034,
                   cavity=(0.016, 0.020, 0.008), pitch=10.0)
        eye_c = (0.0385, 0.056, 0.014)
        eye_kw = dict(yaw_out=24, pitch=-2, w_open=er * 0.96, h_up=er * 0.66, h_lo=er * 0.58, tilt=6)
        ear_kw = dict(base_hl=(0.036, -0.030, 0.058), length=p["ear_len"], width=p["ear_w"], thick=0.022,
                      tilt_out=14, tilt_back=12, twist=10, shape="long", n_bones=3)
        jaw_pivot = hp(0, -0.008, -0.036)
        chin = hp(0, 0.078, -0.054)
        teeth = [("incisor", 0.0042, 0.095, -0.042, 0.0085)]
        whisk = dict(y=0.092, z=-0.028, x=0.017)
    elif sp == "raccoon":
        parts.append(Ellipsoid(hp(0, -0.008, 0.006), cr))
        parts.append(Ellipsoid(hp(0, 0.026, -0.018), R3(0.060, 0.050, 0.046)))
        for s in (1, -1):
            parts.append(Ellipsoid(hp(s * 0.050, 0.016, -0.022), R3(0.038, 0.040, 0.034)))
            parts.append(Ellipsoid(hp(s * 0.030, 0.055, 0.026), R3(0.026, 0.016, 0.012), rot_z(s * -0.3)))
            fur.append(fluff(hp(s * 0.066, -0.004, -0.034), R3(0.036, 0.044, 0.040), rot_z(s * 0.30),
                             v3(s * 1.0, 0.25, -0.35), 0.012 * S, seed=41 + s))
        parts.append(RoundCone(hp(0, 0.046, -0.014), hp(0, 0.099, -0.027), 0.034 * S, 0.018 * S))    # fuller, shorter muzzle
        parts.append(RoundCone(hp(0, 0.042, 0.008), hp(0, 0.094, -0.018), 0.023 * S, 0.014 * S))
        details.append(RoundCone(hp(0, 0.056, -0.040), hp(0, 0.092, -0.043), 0.021 * S, 0.012 * S))
        nose_c = hp(0, 0.1065, -0.0255)
        details.append(Ellipsoid(nose_c, R3(0.0120, 0.0090, 0.0088), rot_x(0.25)))
        lip = dict(lip_y=0.095, lip_z=-0.039, corner_y=0.056, half_w=0.027, gap=0.0034,
                   cavity=(0.019, 0.028, 0.008), pitch=8.0)
        eye_c = (0.0345, 0.058, 0.010)
        eye_kw = dict(yaw_out=12, pitch=-3, w_open=er * 0.96, h_up=er * 0.62, h_lo=er * 0.55, tilt=6)
        ear_kw = dict(base_hl=(0.056, -0.028, 0.050), length=p["ear_len"], width=p["ear_w"], thick=0.018,
                      tilt_out=28, tilt_back=8, twist=18, shape="round", n_bones=2)
        jaw_pivot = hp(0, -0.010, -0.036)
        chin = hp(0, 0.088, -0.050)
        teeth = [("upper", 0.012, 0.088, -0.036, 0.0060), ("lower", 0.010, 0.082, -0.044, 0.0045)]
        whisk = dict(y=0.090, z=-0.030, x=0.020)
    else:
        raise ValueError(sp)

    base = Union(parts, k=0.022 * S)
    base = Union([base, Union(details, k=0.008 * S)], k=0.010 * S)
    if fur:
        base = Union([base] + fur, k=0.010 * S)
    lids = []
    sockets = []
    for s in (1, -1):
        l, sk, ef = eye_rig(F, Hf, s, eye_c[0] * S, eye_c[1] * S, eye_c[2] * S, er, **eye_kw)
        lids.append(l)
        sockets.append(sk)
    for s in (1, -1):
        subs.append(Ellipsoid(nose_c + Hf.v(s * 0.0048 * S, 0.0056 * S, -0.0016 * S), R3(0.0022, 0.0022, 0.0016)))
    ek = dict(ear_kw)
    ek["base_hl"] = tuple(v * S for v in ek["base_hl"])
    ek["length"] *= S if sp != "rabbit" else 1.0
    ek["width"] *= S
    ek["thick"] *= S
    ears = [ear_node(F, Hf, s, **ek) for s in (1, -1)]
    sl, cav, Mf = mouth_parts(F, Hf, lip["lip_y"] * S, lip["lip_z"] * S, lip["corner_y"] * S, lip["half_w"] * S,
                              lip["gap"], tuple(c * S for c in lip["cavity"]), lip["pitch"])
    head = Union([base] + lids, k=0.0045)
    head = Union([head] + ears, k=0.010 * S)
    for sb in subs:
        head = Subtract(head, sb, k=0.0015)
    head = Subtract(head, Union([sl, cav], k=0.004), k=0.0012)
    for sk in sockets:
        head = Subtract(head, sk, k=0.0012)
    cavS = [c * S for c in lip["cavity"]]
    tongue_c = Mf.p(0, -0.012 * S - cavS[1] * 0.9, -cavS[2] * 0.85)
    head = Union([head, Ellipsoid(tongue_c, (lip["half_w"] * S * 0.50, cavS[1] * 0.95, 0.0035), Mf.R)], k=0.002)
    F.mouth.update(dict(pivot=v3(jaw_pivot), chin=v3(chin), nose=nose_c.tolist(), tongue=tongue_c.tolist()))
    for kind, x, y, z, ln in teeth:
        for s in (1, -1):
            base_p = hp(s * x, y, z)
            if kind == "upper":
                F.teeth.append(dict(base=(base_p + Hf.v(0, 0, 0.004 * S)).tolist(), dir=normalize(Hf.v(0, 0.12, -1)).tolist(),
                                    length=ln * S, radius=0.0028 * S, bone="Head"))
            elif kind == "lower":
                F.teeth.append(dict(base=(base_p - Hf.v(0, 0, 0.004 * S)).tolist(), dir=normalize(Hf.v(0, 0.10, 1)).tolist(),
                                    length=ln * S, radius=0.0024 * S, bone="Jaw"))
            else:
                F.teeth.append(dict(base=(base_p + Hf.v(0, 0.0, 0.004 * S)).tolist(), dir=normalize(Hf.v(0, 0.2, -1)).tolist(),
                                    length=ln * S, radius=0.0036 * S, bone="Head", flat=True))
    for s in (1, -1):
        for i, (dz, ln) in enumerate(((0.004, 0.085), (-0.002, 0.095), (-0.008, 0.080))):
            b = hp(s * whisk["x"], whisk["y"], whisk["z"] + dz)
            d = normalize(Hf.v(s * 1.0, -0.25 + 0.02 * i, -0.10 - 0.12 * i + 0.1))
            F.whiskers.append(dict(base=b.tolist(), dir=d.tolist(), length=ln * S, side=s))
    F.parts["head"] = head
    F.head_scale = S
    F.landmarks.update(dict(nose=nose_c.tolist(), eye_c=[e["center"] for e in F.eyes], head_scale=S))
    return head


# =============================================================================
def build_body(F):
    build_skeleton(F)
    head = build_head(F)
    torso = build_torso(F)
    F.parts["torso"] = torso
    arms = []
    for side in ("Left", "Right"):
        arm = build_arm(F, side)
        hand = build_hand(F, side)
        F.parts["arm_" + side] = arm
        F.parts["hand_" + side] = hand
        arms.append(Union([arm, hand], k=0.012))
    legs = []
    for side in ("Left", "Right"):
        leg = build_leg(F, side)
        foot = build_foot(F, side)
        F.parts["leg_" + side] = leg
        F.parts["foot_" + side] = foot
        legs.append(Union([leg, foot], k=0.018))
    tail = build_tail(F)
    trunk = Union([torso] + legs, k=0.030)
    trunk = Union([trunk, tail], k=0.022)
    trunk = Union([trunk] + arms, k=0.020)
    body = Union([trunk, head], k=0.018)
    F.body = body
    build_bones(F)
    # clothing proxy: smoothed torso + limbs (no head/hands/feet/tail)
    tp = build_torso(F, proxy=True)
    ap = [build_arm(F, s, proxy=True) for s in ("Left", "Right")]
    lp = [build_leg(F, s, proxy=True) for s in ("Left", "Right")]
    # union with the real torso/limbs so the proxy always encloses the body.  Each leg blends
    # into the torso smoothly, but the two legs meet with a sharp min: no cloth web between thighs.
    ta = Union([Union([tp] + ap, k=0.055), torso, F.parts["arm_Left"], F.parts["arm_Right"]], k=0.030)
    legs = []
    F.leg_proxy = {}
    for i, side in enumerate(("Left", "Right")):
        lg = Union([lp[i], F.parts["leg_" + side]], k=0.030)
        F.leg_proxy[side] = lg
        legs.append(Union([ta, lg], k=0.050))
    F.proxy = Union(legs, k=0.0)
    F.landmarks["head_frame"] = dict(o=F.head_frame.o.tolist(), R=F.head_frame.R.tolist())
    return F


def fighter(fid):
    F = Fighter(fid)
    build_body(F)
    return F
