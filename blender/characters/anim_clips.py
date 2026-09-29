"""WILDRUSH character pipeline - clip definitions (runs inside Blender).

Every clip is a function of time returning a pose dict (see anim_lib).  Timings of attacks
and skills come from game/data/tuning/fighters/<id>.json (total_s, hit windows, paths,
clips maps); hit windows are authored so the limb tip follows the JSON path exactly
(object space: X = -x, Y = -z, Z = y).  Locomotion plants feet at the reference speed so
nothing slides once the sim moves the character.
"""
import math
from mathutils import Vector, Matrix
from anim_lib import (V, R3, rad, ease, smooth01, keyed, lerp_pose, add, path_at, to_obj, FPS)

STYLE = {
    "nyx": dict(crouch=0.095, width=0.185, lead=0.130, rear=0.110, yaw=16, lean=10, guard="claws_high",
                fing=(0.55, 0.35, 0.25), run="light_springy", idle_rate=1.1, walk_crouch=0.035,
                run_T=40, run_duty=0.18, run_bounce=0.045, run_lean=13, knee_lift=0.10, walk_duty=0.42),
    "bruno": dict(crouch=0.075, width=0.215, lead=0.110, rear=0.120, yaw=12, lean=8, guard="forearms_high",
                  fing=(1.0, 0.9, 0.0), run="heavy_driving", idle_rate=0.85, walk_crouch=0.03,
                  run_T=42, run_duty=0.22, run_bounce=0.030, run_lean=16, knee_lift=0.07, walk_duty=0.45),
    "vex": dict(crouch=0.070, width=0.170, lead=0.150, rear=0.110, yaw=28, lean=4, guard="open_hands",
                fing=(0.25, 0.15, 0.3), run="smooth_glide", idle_rate=1.0, walk_crouch=0.025,
                run_T=41, run_duty=0.20, run_bounce=0.020, run_lean=10, knee_lift=0.08, walk_duty=0.42),
    "hops": dict(crouch=0.075, width=0.170, lead=0.110, rear=0.110, yaw=14, lean=6, guard="forearms_mid",
                 fing=(1.0, 0.9, 0.0), run="bounding", idle_rate=1.25, walk_crouch=0.025,
                 run_T=42, run_duty=0.17, run_bounce=0.060, run_lean=8, knee_lift=0.14, walk_duty=0.42),
    "scrap": dict(crouch=0.110, width=0.200, lead=0.120, rear=0.110, yaw=20, lean=16, guard="paws_mid",
                  fing=(0.6, 0.4, 0.2), run="low_scurry", idle_rate=1.05, walk_crouch=0.05,
                  run_T=38, run_duty=0.22, run_bounce=0.025, run_lean=18, knee_lift=0.06, walk_duty=0.45),
}

GUARDS = {
    # chest-frame (left, up, forward); x mirrored for the right hand.  L = lead (left), R = rear.
    "claws_high": dict(L=dict(pos=(0.14, 0.19, 0.42), fwd=(0.2, 0.8, 0.6), palm=(-0.35, -0.2, 1.0)),
                       R=dict(pos=(0.17, 0.12, 0.27), fwd=(0.2, 0.85, 0.5), palm=(-0.4, -0.2, 1.0)),
                       pole=(0.55, -0.60, -0.10)),
    "forearms_high": dict(L=dict(pos=(0.10, 0.31, 0.26), fwd=(0.0, 0.8, 0.6), palm=(-1.0, 0.0, 0.1)),
                          R=dict(pos=(0.09, 0.29, 0.16), fwd=(0.0, 0.85, 0.5), palm=(-1.0, 0.0, 0.1)),
                          pole=(0.25, -0.60, 0.0)),
    "open_hands": dict(L=dict(pos=(0.05, 0.08, 0.40), fwd=(-0.25, 0.15, 1.0), palm=(-0.6, -0.8, 0.0)),
                       R=dict(pos=(0.13, 0.02, 0.20), fwd=(-0.1, 0.35, 1.0), palm=(-0.8, -0.5, 0.0)),
                       pole=(0.45, -0.55, -0.2)),
    "forearms_mid": dict(L=dict(pos=(0.10, 0.17, 0.31), fwd=(0.0, 0.65, 0.75), palm=(-1.0, 0.0, 0.1)),
                         R=dict(pos=(0.10, 0.13, 0.19), fwd=(0.0, 0.7, 0.7), palm=(-1.0, 0.0, 0.1)),
                         pole=(0.35, -0.60, -0.05)),
    "paws_mid": dict(L=dict(pos=(0.15, 0.05, 0.32), fwd=(-0.1, 0.25, 1.0), palm=(-0.45, -0.9, 0.0)),
                     R=dict(pos=(0.14, 0.02, 0.24), fwd=(-0.1, 0.25, 1.0), palm=(-0.45, -0.9, 0.0)),
                     pole=(0.55, -0.45, -0.1)),
}

TAIL_BASE = {
    "cat": [(-6, 0, 0), (4, 0, 0), (6, 0, 0), (8, 0, 0), (10, 0, 0), (12, 0, 0)],
    "fox": [(4, 0, 0), (2, 0, 0), (0, 0, 0), (0, 0, 0), (-2, 0, 0), (-2, 0, 0)],
    "raccoon": [(2, 0, 0), (2, 0, 0), (0, 0, 0), (0, 0, 0), (-2, 0, 0), (-2, 0, 0)],
    "dog": [(8, 0, 0), (10, 0, 0), (10, 0, 0)],
    "rabbit": [(0, 0, 0), (0, 0, 0)],
}


class Ctx:
    def __init__(self, fid, info, solver, fj):
        self.fid = fid
        self.I = info
        self.solver = solver
        self.fj = fj
        self.st = STYLE[fid]
        self.species = info.rj["species"]
        self.tail_n = len(info.tail_bones)

    # ------------------------------------------------------------------ building blocks
    def tail(self, t=0.0, amp=1.0, freq=0.5, lift=0.0, curl=0.0, side=0.0, phase=0.0):
        base = TAIL_BASE[self.species]
        n = self.tail_n
        out = []
        for i in range(n):
            p, r, y = base[i] if i < len(base) else (0, 0, 0)
            w = (i + 1) / n
            sway = amp * (4 + 6 * w) * math.sin(2 * math.pi * freq * t - i * 0.55 + phase)
            bob = amp * 2.0 * math.sin(2 * math.pi * freq * 2 * t - i * 0.6 + phase)
            out.append((p + lift * (1.0 if i == 0 else 0.25) + curl * w + bob, r, y + sway + side * (1.0 if i < 2 else 0.4)))
        return out

    def hand(self, which, side, guard=None, **over):
        g = GUARDS[guard or self.st["guard"]]
        h = dict(g[which])
        spec = dict(frame="chest", pos=h["pos"], fwd=h["fwd"], palm=h["palm"], pole=g["pole"])
        spec.update(over)
        return spec

    def stance(self, crouch_add=0.0, **over):
        st = self.st
        w = st["width"]
        p = dict(
            hips=V(0, 0.01, -st["crouch"] - crouch_add),
            hips_rot=(st["lean"] * 0.5, 0.0, -st["yaw"] * 0.6),
            spine=(st["lean"] * 0.3, 0.0, st["yaw"] * 0.18),
            chest=(st["lean"] * 0.25, 0.0, st["yaw"] * 0.18),
            uchest=(0.0, 0.0, st["yaw"] * 0.08),
            neck=(-st["lean"] * 0.35, 0.0, st["yaw"] * 0.08),
            head=(-st["lean"] * 0.35, 0.0, st["yaw"] * 0.10),
            hand_L=self.hand("L", "Left"), hand_R=self.hand("R", "Right"),
            foot_L=dict(ball=(w, -st["lead"]), yaw=-st["yaw"] * 0.4, heel=4.0),
            foot_R=dict(ball=(-w, st["rear"]), yaw=-st["yaw"] * 1.4, heel=14.0),
            fing_L=st["fing"], fing_R=st["fing"],
            jaw=-2.6, ear_L=(0.0, 0.0, 0.0), ear_R=(0.0, 0.0, 0.0),
            tail=self.tail(0.0, amp=0.0),
        )
        p.update(over)
        return p

    def neutral(self, **over):
        """Relaxed upright pose (victory/defeat/respawn bases)."""
        p = dict(
            hips=V(0, 0, -0.01), hips_rot=(0, 0, 0), spine=(0, 0, 0), chest=(0, 0, 0), uchest=(0, 0, 0),
            neck=(0, 0, 0), head=(0, 0, 0),
            hand_L=dict(frame="chest", pos=(0.20, -0.36, 0.04), fwd=(0.05, -1, 0.1), palm=(-1, 0, 0.1), pole=(0.3, 0.0, -1.0)),
            hand_R=dict(frame="chest", pos=(0.20, -0.36, 0.04), fwd=(0.05, -1, 0.1), palm=(-1, 0, 0.1), pole=(0.3, 0.0, -1.0)),
            foot_L=dict(ball=(0.11, -0.02), yaw=4), foot_R=dict(ball=(-0.11, 0.02), yaw=-4),
            fing_L=(0.3, 0.2, 0.1), fing_R=(0.3, 0.2, 0.1), jaw=-2.6, ear_L=(0, 0, 0), ear_R=(0, 0, 0),
            tail=self.tail(0.0, amp=0.0))
        p.update(over)
        return p

    # ------------------------------------------------------------------ reach helpers
    def resolve(self, pose):
        return self.solver.resolve(pose)

    def reach_hips(self, pose, side, target, frac=0.93, max_shift=0.45, up=False):
        """Shift the hips (and lean) so the wrist target is reachable by the arm."""
        res = self.resolve(pose)
        sh = res["shoulder"][side]
        target = Vector(target)
        d = target - sh
        L = self.I.arm_len[side] * frac
        if d.length <= L:
            return pose
        excess = d.length - L
        dirv = d.normalized()
        if not up:
            dirv = Vector((dirv.x, dirv.y, dirv.z * 0.5))
        shift = dirv * min(excess, max_shift)
        p = dict(pose)
        p["hips"] = V(pose.get("hips", (0, 0, 0))) + shift
        return p

    def reach_leg(self, pose, side, ankle_target, frac=0.985, max_shift=0.35):
        res = self.resolve(pose)
        hj = res["hipj"][side]
        d = ankle_target - hj
        L = self.I.leg_len[side] * frac
        if d.length <= L:
            return pose
        excess = d.length - L
        p = dict(pose)
        p["hips"] = V(pose.get("hips", (0, 0, 0))) + d.normalized() * min(excess, max_shift)
        return p


# ============================================================================= common clips
def clip_idle(C):
    st = C.st
    base = C.stance()
    T = 2.0
    k = 2 if st["idle_rate"] >= 1.0 else 1

    def f(t):
        u = 2 * math.pi * t / T
        br = math.sin(u * k)
        p = add(base, hips=(0.004 * math.sin(u), 0.0, -0.008 * (0.5 + 0.5 * math.sin(u * k))),
                chest=(1.5 * br, 0, 0), uchest=(1.0 * br, 0, 0), head=(-1.0 * br, 0.8 * math.sin(u), 2.0 * math.sin(u)),
                hips_rot=(0, 1.2 * math.sin(u), 0))
        p["tail"] = C.tail(t, amp=0.8, freq=1.0 / T * k)
        tw = max(0.0, math.sin(u * 2 + 1.0)) ** 8
        p["ear_L"] = (-6 * tw, 0, 4 * tw)
        p["ear_R"] = (0, 0, 2 * tw)
        return p
    return f, dict(loop=True)


def gait(C, kind, dirn, speed, T, duty, stride_scale=1.0):
    """Walk/run cycle. dirn: object-space unit vector of travel. Feet planted at `speed`."""
    st = C.st
    run = kind == "run"
    d = Vector(dirn).normalized()
    lateral = abs(d.x) > 0.5
    back = d.y > 0.5
    # hips turn toward lateral travel, upper body counter-rotates
    hy = 0.0
    if lateral:
        hy = (55.0 if run else 35.0) * (1 if d.x > 0 else -1)
    Rh = Matrix.Rotation(rad(hy), 3, "Z")
    w = 0.095 if run else 0.105
    centers = {"Left": Rh @ Vector((w, 0.0, 0.0)), "Right": Rh @ Vector((-w, 0.0, 0.0))}
    travel = speed * T * duty
    h_swing = (0.16 + st["knee_lift"]) if run else 0.075
    crouch = (st["crouch"] * 0.5 + 0.02) if run else (st["walk_crouch"] + 0.045)
    lean = (st["run_lean"] if run else 5.0) * (-0.5 if back else 1.0) * (0.4 if lateral else 1.0)
    bounce = st["run_bounce"] if run else 0.022
    guard = C.stance()

    def foot(side, t):
        off = 0.0 if side == "Left" else 0.5
        ph = (t / T + off) % 1.0
        c = centers[side]
        if ph < duty:
            u = ph / duty
            pos = c + d * (travel * (0.5 - u))
            lift = 0.0
            # heel rises whenever the planted foot is behind the hips (toe-off forward, toe-strike backward)
            behind = (Rh.transposed() @ (pos - c)).y
            heel = (8.0 if run else 0.0) + (24.0 if run else 28.0) * smooth01(0.10, 0.45, behind / max(travel, 1e-3) * 1.0 + 0.0)
            pitch = 0.0
        else:
            u = (ph - duty) / (1.0 - duty)
            pos = c + d * (travel * 0.5 * -math.cos(math.pi * u))
            if run:
                # heel kick toward the rear early in swing, knee drive forward late
                pos = pos - d * (0.16 * math.sin(math.pi * min(u * 1.6, 1.0)) * (1 - u))
            lift = h_swing * math.sin(math.pi * u) ** (0.8 if run else 1.0)
            heel = (30.0 if run else 24.0) * (1 - u) ** 2
            pitch = (-18.0 if run else -10.0) * math.sin(math.pi * u) * (1 - u) + (6.0 if not run else 0.0) * u ** 3
        fyaw = hy + (-4 if side == "Left" else 4) * 0.5
        return dict(ball=(pos.x, pos.y), lift=lift, heel=heel, pitch=pitch, yaw=fyaw)

    def f(t):
        ph = t / T
        s2 = math.cos(4 * math.pi * (ph - duty * 0.5))           # two bobs per cycle
        if run:
            hz = -crouch + bounce * (0.5 - 0.5 * s2) - bounce * 0.5
        else:
            hz = -crouch + bounce * (0.5 + 0.5 * s2) - bounce
        sw = math.sin(2 * math.pi * ph)                          # + when left foot forward (left swing mid)
        p = dict(
            hips=V(0, 0.015 * (1 if not back else -1) * (0 if lateral else 1), hz),
            hips_rot=(lean * 0.6, (2.5 if not run else 1.5) * math.sin(2 * math.pi * ph) * (0 if lateral else 1),
                      hy + (5.0 if not run else 7.0) * sw * (0 if lateral else 1)),
            spine=(lean * 0.3, 0, -hy * 0.35 - 3.0 * sw),
            chest=(lean * 0.2, 0, -hy * 0.35 - 3.0 * sw),
            uchest=(0, 0, -hy * 0.1),
            neck=(-lean * 0.45, 0, -hy * 0.1),
            head=(-lean * 0.35, 0, -hy * 0.1 + 1.5 * sw),
            foot_L=foot("Left", t), foot_R=foot("Right", t),
            jaw=-2.6, ear_L=(-4.0 if run else 0.0, 0, 0), ear_R=(-4.0 if run else 0.0, 0, 0),
            fing_L=(0.6 if run else 0.35, 0.4, 0.1), fing_R=(0.6 if run else 0.35, 0.4, 0.1),
        )
        # arms: counter-swing (left arm forward when right leg forward)
        for side, s in (("Left", 1), ("Right", -1)):
            a = -sw * s
            if run:
                spec = dict(frame="chest", pos=(0.15, -0.14 + 0.06 * max(a, 0), 0.06 + 0.22 * a),
                            fwd=(-0.2, 0.25 + 0.4 * a, 1.0), palm=(-1.0, 0, 0), pole=(0.25, -0.5, -0.8))
            elif back or lateral:
                g = guard["hand_" + ("L" if side == "Left" else "R")]
                spec = dict(g)
                spec["pos"] = (g["pos"][0], g["pos"][1] - 0.05, g["pos"][2] - 0.04 + 0.03 * a)
            else:
                spec = dict(frame="chest", pos=(0.19, -0.33, 0.02 + 0.16 * a), fwd=(0.0, -1.0, 0.25 + 0.3 * a),
                            palm=(-1.0, 0, 0.0), pole=(0.3, 0.0, -1.0))
            p["hand_" + ("L" if side == "Left" else "R")] = spec
        p["tail"] = C.tail(t, amp=0.7 if not run else 0.5, freq=1.0 / T, lift=(10 if run else 3))
        if run and C.species in ("fox", "cat", "raccoon"):
            p["tail"] = [(pp + (6 if i > 0 else 10), rr, yy) for i, (pp, rr, yy) in enumerate(p["tail"])]
        return p
    contacts = {}
    n = int(round(T * FPS))
    for side, off in (("Left", 0.0), ("Right", 0.5)):
        fr = []
        for fi in range(n):
            ph = (fi / n + off) % 1.0
            if 0.08 * duty < ph < 0.55 * duty:
                fr.append(fi)
        contacts[side] = fr
    return f, dict(loop=True, ref_speed=speed, contacts=contacts)


def clip_turn(C, left=True):
    base = C.stance()
    s = 1 if left else -1
    st = C.st

    def f(t):
        u = t / 0.5
        p = dict(base)
        lead = math.sin(math.pi * min(u * 1.3, 1.0))
        p = add(p, hips_rot=(0, 0, 10 * s * lead), chest=(0, 0, 8 * s * lead), head=(0, 0, 14 * s * lead))
        # two quick steps: pivot foot (inside of the turn) then the other
        for side, t0, t1 in ((("Left" if left else "Right"), 0.05, 0.25), (("Right" if left else "Left"), 0.22, 0.45)):
            key = "foot_" + ("L" if side == "Left" else "R")
            spec = dict(base[key])
            if t0 < t < t1:
                v = (t - t0) / (t1 - t0)
                spec["lift"] = 0.06 * math.sin(math.pi * v)
                spec["yaw"] = spec.get("yaw", 0) + 25 * s * math.sin(math.pi * v)
                spec["heel"] = spec.get("heel", 0) + 10 * math.sin(math.pi * v)
            p[key] = spec
        p["tail"] = C.tail(t, amp=0.4, freq=2.0, side=-18 * s * lead)
        return p
    return f, dict(loop=False)


def clip_jump(C, phase):
    st = C.st
    base = C.stance()
    crouch = dict(base, hips=V(0, 0.0, -st["crouch"] - 0.10), hips_rot=(18, 0, -st["yaw"] * 0.3),
                  hand_L=C.hand("L", "Left", pos=(0.14, -0.10, 0.20)), hand_R=C.hand("R", "Right", pos=(0.15, -0.12, 0.10)))
    crouch["foot_L"] = dict(ball=(0.13, -0.06), yaw=-4, heel=6)
    crouch["foot_R"] = dict(ball=(-0.13, 0.06), yaw=-10, heel=10)
    ext = dict(base, hips=V(0, 0.0, 0.02), hips_rot=(4, 0, 0), spine=(0, 0, 0), chest=(-4, 0, 0), head=(-6, 0, 0),
               hand_L=dict(frame="chest", pos=(0.22, 0.28, 0.12), fwd=(0.2, 1, 0.2), palm=(-1, 0, 0), pole=(0.6, -0.3, -0.4)),
               hand_R=dict(frame="chest", pos=(0.22, 0.24, 0.10), fwd=(0.2, 1, 0.2), palm=(-1, 0, 0), pole=(0.6, -0.3, -0.4)),
               foot_L=dict(ball=(0.12, -0.03), lift=0.02, heel=40, pitch=10, yaw=0),
               foot_R=dict(ball=(-0.12, 0.02), lift=0.02, heel=40, pitch=10, yaw=0))
    tuck = dict(ext, hips=V(0, 0.0, 0.0), hips_rot=(10, 0, 0),
                foot_L=dict(ball=(0.13, -0.16), lift=0.34, heel=0, pitch=-20, yaw=0),
                foot_R=dict(ball=(-0.12, 0.08), lift=0.24, heel=10, pitch=-35, yaw=0),
                hand_L=dict(frame="chest", pos=(0.24, 0.10, 0.22), fwd=(0.3, 0.5, 1), palm=(-1, -0.5, 0), pole=(0.6, -0.5, -0.2)),
                hand_R=dict(frame="chest", pos=(0.26, 0.06, 0.10), fwd=(0.3, 0.3, 1), palm=(-1, -0.5, 0), pole=(0.6, -0.5, -0.2)))
    fall = dict(tuck, hips_rot=(4, 0, 0),
                foot_L=dict(ball=(0.13, -0.10), lift=0.10, heel=8, pitch=-12, yaw=-4),
                foot_R=dict(ball=(-0.13, 0.08), lift=0.06, heel=16, pitch=-18, yaw=-8),
                hand_L=dict(frame="chest", pos=(0.30, 0.16, 0.12), fwd=(0.6, 0.3, 0.6), palm=(0, -1, 0), pole=(0.6, -0.4, -0.4)),
                hand_R=dict(frame="chest", pos=(0.30, 0.14, 0.08), fwd=(0.6, 0.3, 0.6), palm=(0, -1, 0), pole=(0.6, -0.4, -0.4)))
    if phase == "start":
        keys = [(0.0, base), (0.05, crouch, "out"), (0.12, ext)]
        loop = False
    elif phase == "air":
        def f(t):
            u = 2 * math.pi * t / 0.5
            p = add(tuck, hips=(0, 0, 0.006 * math.sin(u)), chest=(1.5 * math.sin(u), 0, 0))
            p["tail"] = C.tail(t, amp=0.6, freq=2.0, lift=12)
            p["ear_L"] = (-8, 0, 0)
            p["ear_R"] = (-8, 0, 0)
            return p
        return f, dict(loop=True)
    elif phase == "fall":
        def f(t):
            u = 2 * math.pi * t / 0.5
            p = add(fall, hand_L={}, chest=(-1.5 * math.sin(u), 0, 0))
            p["hand_L"] = fall["hand_L"]
            p["tail"] = C.tail(t, amp=0.6, freq=2.0, lift=20)
            p["ear_L"] = (10, 0, 0)
            p["ear_R"] = (10, 0, 0)
            return p
        return f, dict(loop=True)
    else:  # land
        impact = dict(crouch, hips=V(0, 0.0, -st["crouch"] - 0.13), hips_rot=(20, 0, -st["yaw"] * 0.4))
        keys = [(0.0, fall), (0.035, impact, "out"), (0.2, base)]
        loop = False

    def f(t):
        p = keyed(t, keys)
        p = dict(p)
        p["tail"] = C.tail(t, amp=0.3, freq=2.0, lift=8 if phase == "start" else -6)
        return p
    return f, dict(loop=loop)


def clip_dodge(C, dirn):
    st = C.st
    base = C.stance()
    d = {"f": Vector((0, -1, 0)), "b": Vector((0, 1, 0)), "l": Vector((1, 0, 0)), "r": Vector((-1, 0, 0))}[dirn]
    lean_p = -d.y * 28 if dirn in "fb" else 6
    lean_r = d.x * 22
    low = dict(base, hips=V(d.x * 0.10, d.y * 0.10, -st["crouch"] - 0.14), hips_rot=(lean_p, lean_r, -st["yaw"] * 0.3),
               chest=(8, lean_r * 0.4, 0), head=(-10, -lean_r * 0.5, 0),
               hand_L=C.hand("L", "Left", pos=(0.12, 0.10, 0.18)), hand_R=C.hand("R", "Right", pos=(0.12, 0.06, 0.10)))
    # stride in the dodge direction
    ahead, behind = (0.28, 0.24)
    if dirn in "fb":
        fL = dict(ball=(0.14, d.y * ahead), lift=0.0, yaw=0, heel=6)
        fR = dict(ball=(-0.14, -d.y * behind), lift=0.0, yaw=-8, heel=38)
    else:
        lead_side = "Left" if dirn == "l" else "Right"
        s = 1 if dirn == "l" else -1
        fL = dict(ball=(0.14 + (0.26 if lead_side == "Left" else -0.02), -0.04), lift=0.0, yaw=8 * s, heel=6)
        fR = dict(ball=(-0.14 + (0.02 if lead_side == "Left" else -0.26), 0.04), lift=0.0, yaw=8 * s, heel=6)
        if lead_side == "Left":
            fR["heel"] = 34
        else:
            fL["heel"] = 34
    low["foot_L"] = fL
    low["foot_R"] = fR
    push = dict(low)
    fL2 = dict(fL)
    fR2 = dict(fR)
    if dirn in "fb":
        fR2["lift"] = 0.10
        fR2["heel"] = 20
    else:
        (fR2 if dirn == "l" else fL2)["lift"] = 0.08
    push["foot_L"] = fL2
    push["foot_R"] = fR2
    keys = [(0.0, base), (0.05, low, "out"), (0.20, push), (0.30, low), (0.367, base)]

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.3, freq=2.0, lift=14, side=-d.x * 25)
        p["ear_L"] = (-12, 0, 0)
        p["ear_R"] = (-12, 0, 0)
        return p
    return f, dict(loop=False)


def guard_pose(C):
    st = C.st
    base = C.stance(crouch_add=0.02)
    if st["guard"] in ("forearms_high", "forearms_mid", "claws_high"):
        hl = dict(frame="chest", pos=(0.07, 0.36, 0.25), fwd=(-0.25, 1.0, 0.15), palm=(-0.2, 0.0, -1.0), pole=(0.20, -0.7, 0.30))
        hr = dict(frame="chest", pos=(0.08, 0.34, 0.20), fwd=(-0.30, 1.0, 0.15), palm=(-0.2, 0.0, -1.0), pole=(0.20, -0.7, 0.30))
    else:
        hl = dict(frame="chest", pos=(0.06, 0.30, 0.27), fwd=(-0.35, 1.0, 0.1), palm=(-0.2, 0.0, -1.0), pole=(0.25, -0.7, 0.25))
        hr = dict(frame="chest", pos=(0.07, 0.27, 0.22), fwd=(-0.35, 1.0, 0.1), palm=(-0.2, 0.0, -1.0), pole=(0.25, -0.7, 0.25))
    g = dict(base, hand_L=hl, hand_R=hr, fing_L=(1.0, 0.9, 0.0), fing_R=(1.0, 0.9, 0.0),
             head=(6, 0, 0), neck=(4, 0, st["yaw"] * 0.1), chest=(6, 0, st["yaw"] * 0.15), ear_L=(-10, 0, 0), ear_R=(-10, 0, 0))
    return g


def clip_guard(C, phase):
    base = C.stance()
    g = guard_pose(C)
    if phase == "enter":
        keys = [(0.0, base), (0.1, g, "out")]
    elif phase == "exit":
        keys = [(0.0, g), (0.12, base)]
    elif phase == "block":
        hit = add(g, hips=(0, 0.05, -0.01), hips_rot=(-6, 0, 0), chest=(-6, 0, 0), head=(-8, 0, 0))
        keys = [(0.0, g), (0.04, hit, "out"), (0.2, g)]
    elif phase == "hold":
        def f(t):
            u = 2 * math.pi * t / 1.0
            p = add(g, hips=(0, 0, -0.006 * (0.5 + 0.5 * math.sin(u))), chest=(1.0 * math.sin(u), 0, 0))
            p["tail"] = C.tail(t, amp=0.5, freq=1.0)
            return p
        return f, dict(loop=True)
    else:  # break
        st = C.st
        broke = dict(C.stance(crouch_add=-0.02), hips=V(0, 0.10, -st["crouch"]), hips_rot=(-14, 4, -st["yaw"] * 0.6),
                     chest=(-12, -4, 6), head=(-16, 6, -8), jaw=12, ear_L=(-25, 0, -10), ear_R=(-25, 0, -10),
                     hand_L=dict(frame="chest", pos=(0.34, 0.30, 0.06), fwd=(0.5, 1, -0.2), palm=(0, 0, 1), pole=(0.6, -0.4, -0.4)),
                     hand_R=dict(frame="chest", pos=(0.33, 0.26, 0.02), fwd=(0.5, 1, -0.2), palm=(0, 0, 1), pole=(0.6, -0.4, -0.4)),
                     fing_L=(0.1, 0.1, 0.4), fing_R=(0.1, 0.1, 0.4))
        broke["foot_L"] = dict(ball=(0.15, -0.02), yaw=-4, heel=10)
        broke["foot_R"] = dict(ball=(-0.15, 0.22), yaw=-20, heel=22)
        wobble = add(broke, hips=(0.01, 0.04, -0.02), hips_rot=(4, -3, 4), head=(8, -6, 6))
        keys = [(0.0, g), (0.08, broke, "out"), (0.35, wobble), (0.6, broke), (0.9, base)]

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.4, freq=1.5, lift=(-10 if phase == "break" else 0))
        return p
    return f, dict(loop=False)


def react_pose(C, back=False, heavy=False):
    st = C.st
    base = C.stance()
    k = 1.8 if heavy else 1.0
    if not back:
        p = add(base, hips=(0, 0.06 * k, 0.0), hips_rot=(-10 * k, 0, 0), chest=(-10 * k, 0, 0), head=(-14 * k, 0, 4 * k))
    else:
        p = add(base, hips=(0, -0.05 * k, -0.02), hips_rot=(10 * k, 0, 0), chest=(10 * k, 0, 0), head=(12 * k, 0, 0))
    p = dict(p)
    p["jaw"] = 10 if not back else 6
    p["ear_L"] = (-28, 0, -8)
    p["ear_R"] = (-28, 0, -8)
    p["hand_L"] = C.hand("L", "Left", pos=(0.20, 0.20, 0.18))
    p["hand_R"] = C.hand("R", "Right", pos=(0.22, 0.16, 0.10))
    p["fing_L"] = (0.2, 0.2, 0.4)
    p["fing_R"] = (0.2, 0.2, 0.4)
    if heavy:
        p["foot_R"] = dict(ball=(-st["width"], st["rear"] + (0.12 if not back else -0.02)), yaw=-st["yaw"] * 1.4, heel=18)
    return p


def clip_hit(C, kind):
    base = C.stance()
    if kind == "front":
        r = react_pose(C)
        keys = [(0.0, base), (0.05, r, "out"), (0.3, base)]
        T = 0.3
    elif kind == "back":
        r = react_pose(C, back=True)
        keys = [(0.0, base), (0.05, r, "out"), (0.3, base)]
        T = 0.3
    elif kind == "heavy":
        r = react_pose(C, heavy=True)
        r2 = add(r, hips=(0, 0.04, -0.02), hips_rot=(4, 3, 0))
        keys = [(0.0, base), (0.06, r, "out"), (0.22, r2), (0.5, base)]
        T = 0.5
    else:  # stagger
        r = react_pose(C, heavy=True)
        s1 = add(r, hips=(0.03, 0.08, -0.03), hips_rot=(-4, -6, 8), head=(6, 8, -8))
        s1 = dict(s1)
        s1["foot_L"] = dict(ball=(0.20, 0.06), lift=0.0, yaw=10, heel=12)
        s2 = add(r, hips=(-0.02, 0.10, -0.02), hips_rot=(0, 5, -6))
        keys = [(0.0, base), (0.07, r, "out"), (0.25, s1), (0.42, s2), (0.6, base)]
        T = 0.6

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.6, freq=3.0, lift=-8, side=6 * math.sin(20 * t))
        return p
    return f, dict(loop=False)


def lying_pose(C, t=0.0):
    """On the back, knees up, arms loose."""
    I = C.I
    hz = I.head["Hips"].z
    p = dict(
        hips=V(0, 0.06, -hz + 0.16), hips_rot=(-80, 0, 0), spine=(4, 0, 0), chest=(4, 0, 0), uchest=(2, 0, 0),
        neck=(18, 0, 10), head=(14, 0, 12),
        hand_L=dict(frame="obj", pos=(0.36, 0.30, 0.07), fwd=(0.4, 0.8, 0.0), palm=(0, 0, -1), pole=(0.3, 0, 1)),
        hand_R=dict(frame="obj", pos=(-0.38, 0.22, 0.07), fwd=(-0.4, 0.8, 0.0), palm=(0, 0, -1), pole=(-0.3, 0, 1)),
        foot_L=dict(ball=(0.16, -0.46), lift=0.0, yaw=10, heel=30),
        foot_R=dict(ball=(-0.20, -0.62), lift=0.0, yaw=-14, heel=10, pitch=-10),
        fing_L=(0.25, 0.2, 0.2), fing_R=(0.25, 0.2, 0.2), jaw=-1.0, ear_L=(-20, 0, 0), ear_R=(-20, 0, 0),
        tail=[(0, 0, 30 if i == 0 else 8) for i in range(C.tail_n)],
    )
    return p


def clip_knockdown(C):
    base = C.stance()
    st = C.st
    r = react_pose(C, heavy=True)
    mid = dict(r, hips=V(0, 0.18, -0.45), hips_rot=(-45, 0, 0), chest=(-8, 0, 0), head=(10, 0, 0),
               foot_L=dict(ball=(0.15, -0.20), lift=0.05, heel=0, pitch=-20), foot_R=dict(ball=(-0.18, -0.10), heel=10),
               hand_L=dict(frame="obj", pos=(0.30, 0.32, 0.35), fwd=(0.3, 0.3, -1), palm=(0, -1, 0), pole=(0.4, 0, 1)),
               hand_R=dict(frame="obj", pos=(-0.30, 0.30, 0.35), fwd=(-0.3, 0.3, -1), palm=(0, -1, 0), pole=(-0.4, 0, 1)))
    lie = lying_pose(C)
    bounce = add(lie, hips=(0, 0, 0.03), hips_rot=(4, 0, 0), head=(8, 0, 0))
    keys = [(0.0, base), (0.08, r, "out"), (0.32, mid, "in"), (0.55, bounce, "out"), (0.8, lie)]

    def f(t):
        p = dict(keyed(t, keys))
        return p
    return f, dict(loop=False)


def clip_getup(C):
    base = C.stance()
    lie = lying_pose(C)
    sit = dict(lie, hips=V(0, 0.10, -C.I.head["Hips"].z + 0.22), hips_rot=(-15, 0, 0), spine=(20, 0, 0), chest=(14, 0, 0),
               neck=(0, 0, 0), head=(-4, 0, 0),
               hand_L=dict(frame="obj", pos=(0.28, 0.22, 0.10), fwd=(0.1, 0.4, -1), palm=(0, 1, 0), pole=(0.4, 0.6, 0.5)),
               hand_R=dict(frame="obj", pos=(-0.28, 0.24, 0.10), fwd=(-0.1, 0.4, -1), palm=(0, 1, 0), pole=(-0.4, 0.6, 0.5)),
               foot_L=dict(ball=(0.16, -0.30), heel=10), foot_R=dict(ball=(-0.16, -0.18), heel=25))
    crouch = dict(base, hips=V(0, 0.02, -C.st["crouch"] - 0.20), hips_rot=(30, 0, -C.st["yaw"] * 0.4),
                  foot_L=dict(ball=(0.15, -0.10), heel=8), foot_R=dict(ball=(-0.15, 0.06), heel=25))
    keys = [(0.0, lie), (0.14, sit, "out"), (0.30, crouch), (0.45, base)]

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.3, freq=2.0)
        return p
    return f, dict(loop=False)


def clip_grabbed(C):
    base = C.stance()
    r = react_pose(C)
    pulled = dict(r, hips=V(0, -0.10, -0.02), hips_rot=(12, 0, 0), chest=(8, 0, 0), head=(-6, 0, 0),
                  hand_L=dict(frame="chest", pos=(0.26, 0.16, 0.30), fwd=(0, 0.3, 1), palm=(-0.5, -1, 0), pole=(0.6, -0.4, -0.3)),
                  hand_R=dict(frame="chest", pos=(0.26, 0.12, 0.30), fwd=(0, 0.3, 1), palm=(-0.5, -1, 0), pole=(0.6, -0.4, -0.3)),
                  foot_L=dict(ball=(0.14, -0.20), lift=0.04, heel=30, pitch=-10), foot_R=dict(ball=(-0.12, -0.02), heel=35),
                  jaw=14, ear_L=(-30, 0, -10), ear_R=(-30, 0, -10))
    keys = [(0.0, base), (0.08, pulled, "out"), (0.30, add(pulled, hips_rot=(0, 0, 20), hips=(0.04, -0.04, 0))), (0.45, add(pulled, hips_rot=(0, 0, 35)))]

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.8, freq=3.0, lift=-5)
        return p
    return f, dict(loop=False)


def clip_knockout(C):
    base = C.stance()
    r = react_pose(C, heavy=True)
    kneel = dict(base, hips=V(0, 0.06, -0.42), hips_rot=(14, 0, 0), spine=(10, 0, 0), chest=(8, 0, 0), head=(20, 0, 0),
                 hand_L=dict(frame="obj", pos=(0.26, -0.20, 0.36), fwd=(0.2, -0.2, -1), palm=(-1, 0, 0), pole=(0.6, 0.5, 0)),
                 hand_R=dict(frame="obj", pos=(-0.26, -0.20, 0.36), fwd=(-0.2, -0.2, -1), palm=(1, 0, 0), pole=(-0.6, 0.5, 0)),
                 foot_L=dict(ball=(0.15, -0.16), heel=5), foot_R=dict(ball=(-0.15, 0.10), heel=50),
                 fing_L=(0.2, 0.2, 0.3), fing_R=(0.2, 0.2, 0.3), jaw=4, ear_L=(-25, 0, -20), ear_R=(-25, 0, -20))
    sit = dict(kneel, hips=V(0, 0.18, -C.I.head["Hips"].z + 0.17), hips_rot=(-10, 6, 8), spine=(18, 0, 0), chest=(12, 4, 0),
               neck=(16, 0, 0), head=(24, 8, 12),
               hand_L=dict(frame="obj", pos=(0.30, 0.34, 0.07), fwd=(0.3, 0.4, -0.9), palm=(0, 1, 0), pole=(0.5, 0.6, 0.3)),
               hand_R=dict(frame="obj", pos=(-0.30, 0.10, 0.20), fwd=(-0.1, -0.5, -0.8), palm=(1, 0, 0), pole=(-0.5, 0.3, 0.3)),
               foot_L=dict(ball=(0.20, -0.44), heel=0, yaw=18), foot_R=dict(ball=(-0.16, -0.30), heel=20, yaw=-30))
    keys = [(0.0, base), (0.10, r, "out"), (0.45, kneel, "in"), (0.85, sit, "smooth"), (1.2, sit)]

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.2 * max(0.0, 1 - t), freq=2.0, lift=-12, side=25 * smooth01(0.4, 1.0, t))
        return p
    return f, dict(loop=False)


def clip_respawn(C):
    base = C.stance()
    low = dict(base, hips=V(0, 0.02, -C.st["crouch"] - 0.26), hips_rot=(34, 0, -C.st["yaw"] * 0.3), head=(-20, 0, 0),
               hand_L=dict(frame="obj", pos=(0.16, -0.30, 0.05), fwd=(0, -1, -0.3), palm=(0, 0, -1), pole=(0.5, 0.5, 0.3)),
               hand_R=C.hand("R", "Right", pos=(0.18, 0.02, 0.12)),
               foot_L=dict(ball=(0.16, -0.14), heel=6), foot_R=dict(ball=(-0.16, 0.10), heel=45))
    rise = add(base, hips=(0, 0, 0.03), chest=(-6, 0, 0), head=(-6, 0, 0))
    keys = [(0.0, low), (0.35, low), (0.62, rise, "out"), (0.8, base)]

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.6, freq=2.5, lift=10 * smooth01(0.3, 0.7, t))
        p["ear_L"] = (10 * smooth01(0.4, 0.6, t) * (1 - smooth01(0.6, 0.8, t)), 0, 0)
        p["ear_R"] = p["ear_L"]
        return p
    return f, dict(loop=False)


def clip_victory(C):
    st = C.st
    n = C.neutral()
    up = dict(n, hips=V(0, 0, 0.0), chest=(-8, 0, 0), head=(-12, 0, 0),
              hand_R=dict(frame="chest", pos=(0.16, 0.58, 0.10), fwd=(0.1, 1, 0.1), palm=(-1, 0, 0.3), pole=(0.8, -0.2, -0.2)),
              hand_L=dict(frame="chest", pos=(0.14, 0.02, 0.22), fwd=(0, 0.4, 1), palm=(-1, 0, 0), pole=(0.5, -0.5, -0.3)),
              fing_R=(1.0, 0.9, 0.0), fing_L=(1.0, 0.9, 0.0), jaw=16, ear_L=(10, 0, 0), ear_R=(10, 0, 0))
    down = dict(up, hand_R=dict(up["hand_R"], pos=(0.18, 0.42, 0.14)), hips=V(0, 0, -0.03), jaw=4)

    def f(t):
        u = (t % 1.25) / 1.25
        p = dict(lerp_pose(up, down, 0.5 - 0.5 * math.cos(2 * math.pi * u)))
        p["tail"] = C.tail(t, amp=1.3, freq=0.8, lift=16)
        p["hips_rot"] = (0, 0, 6 * math.sin(2 * math.pi * t / 2.5))
        return p
    return f, dict(loop=True)


def clip_defeat(C):
    n = C.neutral()
    slump = dict(n, hips=V(0, 0.03, -0.05), hips_rot=(10, 0, 0), spine=(12, 0, 0), chest=(10, 0, 0), neck=(12, 0, 0), head=(18, 0, -6),
                 hand_L=dict(frame="chest", pos=(0.20, -0.40, 0.10), fwd=(0, -1, 0.2), palm=(-1, 0, 0), pole=(0.3, 0, -1)),
                 hand_R=dict(frame="chest", pos=(0.20, -0.40, 0.10), fwd=(0, -1, 0.2), palm=(-1, 0, 0), pole=(0.3, 0, -1)),
                 ear_L=(-30, 0, -20), ear_R=(-30, 0, -20), jaw=-1.0)
    keys = [(0.0, C.stance()), (0.5, slump), (1.2, add(slump, head=(6, 0, 0), hips=(0, 0, -0.01))), (2.0, slump)]

    def f(t):
        p = dict(keyed(t, keys))
        p["tail"] = C.tail(t, amp=0.2, freq=0.5, lift=-18)
        return p
    return f, dict(loop=False)


# ============================================================================= strikes (JSON driven)
def hand_dir_from_path(path, t, dt=0.012):
    a = path_at(path, t - dt)
    b = path_at(path, t + dt)
    v = b - a
    if v.length < 1e-6:
        v = Vector((0, -1, 0))
    return v.normalized()


def strike_pose(C, base, t, hit, limb, style="punch"):
    """Pose at time t inside [t0, t1]: the limb tip sits exactly on the path."""
    path = hit["path"]
    tgt = path_at(path, t)
    p = dict(base)
    if limb in ("hand_r", "hand_l"):
        side = "Right" if limb == "hand_r" else "Left"
        tag = "R" if side == "Right" else "L"
        vdir = hand_dir_from_path(path, t)
        s = 1 if side == "Left" else -1
        if style == "punch":
            fwd = (vdir + Vector((0, -1.0, 0))).normalized()
            palm = Vector((-s * 0.6, 0, -1.0))
        else:  # swipe / claw: fingers lead the sweep, palm faces the sweep direction
            fwd = (Vector((0, -0.8, 0.5)) + vdir * 0.3).normalized()
            palm = vdir
        pole = Vector((s * 0.6, 0.3, -0.5))
        p["hand_" + tag] = dict(frame="obj", pos=tgt, tip=True, fwd=fwd, palm=palm, pole=pole)
        wrist = tgt - fwd * C.I.length[side + "Hand"]
        p = C.reach_hips(p, side, wrist)
    elif limb == "both_hands":
        vdir = hand_dir_from_path(path, t)
        fwd = (Vector((0, -1.0, 0.25)) + vdir * 0.4).normalized()
        for side, s in (("Left", 1), ("Right", -1)):
            tip = tgt + Vector((s * 0.09, 0, 0))
            p["hand_" + ("L" if s > 0 else "R")] = dict(frame="obj", pos=tip, tip=True, fwd=fwd,
                                                         palm=(vdir + Vector((-s * 0.3, 0, 0))), pole=Vector((s * 0.6, 0.3, -0.4)))
        for side, s in (("Left", 1), ("Right", -1)):
            wrist = tgt + Vector((s * 0.09, 0, 0)) - fwd * C.I.length[side + "Hand"]
            p = C.reach_hips(p, side, wrist)
    return p


def strike_clip(C, act, style="punch", windup=None, follow=None, recover_pose=None, extra=None):
    """Generic hand strike: base -> windup -> path-following active window(s) -> recovery."""
    total = act["total_s"]
    hits = act.get("hits", [])
    base = C.stance()
    rec = recover_pose or base

    def f(t):
        # find the active hit or the phase between hits
        cur = base
        for i, h in enumerate(hits):
            limb = h.get("limb", act.get("limb"))
            t0, t1 = h["t0"], h["t1"]
            if t0 - 1e-6 <= t <= t1 + 1e-6:
                p = strike_pose(C, windup(t, i) if windup else base, t, h, limb, style)
                return extra(p, t) if extra else p
        # outside active windows: interpolate between neighbouring anchor poses
        anchors = [(0.0, base)]
        for i, h in enumerate(hits):
            limb = h.get("limb", act.get("limb"))
            t0, t1 = h["t0"], h["t1"]
            wu = windup(t0 * 0.7, i) if windup else base
            anchors.append((max(0.02, t0 - max(0.06, t0 * 0.45)), wu))
            anchors.append((t0, strike_pose(C, windup(t0, i) if windup else base, t0, h, limb, style)))
            anchors.append((t1, strike_pose(C, windup(t1, i) if windup else base, t1, h, limb, style)))
            if follow:
                anchors.append((min(t1 + 0.06, total - 0.02), follow(i, strike_pose(C, windup(t1, i) if windup else base, t1, h, limb, style))))
        anchors.append((total, rec))
        anchors.sort(key=lambda a: a[0])
        p = keyed(t, [(a[0], a[1], "smooth") for a in anchors])
        return extra(dict(p), t) if extra else dict(p)
    return f, dict(loop=False)


def kick_pose(C, base, t, hit, limb):
    path = hit["path"]
    tip = path_at(path, t)
    side = "Right" if limb == "foot_r" else "Left"
    tag = "R" if side == "Right" else "L"
    s = 1 if side == "Left" else -1
    vdir = hand_dir_from_path(path, t)
    p = dict(base)
    yaw = math.degrees(math.atan2(-tip.x, -tip.y)) * -1.0
    pitch = getattr(C, "kick_pitch", -55.0)
    p["foot_" + tag] = dict(ball=(tip.x, tip.y), tip=tip, lift=0.0, yaw=yaw, pitch=pitch, toe=10.0,
                            pole=(Vector((0, -0.4, 1.0)) + Vector((s * 0.5, 0, 0))))
    # stance leg planted, torso leans back as the kick extends
    res = C.resolve(p)
    ank = res["ankle_des_" + side]
    p = C.reach_leg(p, side, ank, max_shift=getattr(C, "kick_shift", 0.35))
    res = C.resolve(p)
    ank = res["ankle_des_" + side]
    p = C.reach_leg(p, side, ank, max_shift=getattr(C, "kick_shift", 0.35))
    return p
