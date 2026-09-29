"""WILDRUSH character pipeline - animation library (runs inside Blender).

Control rig: IK chains (arms/legs) with pole targets on non-deform control bones,
FK for spine/neck/head/jaw/ears/tail/fingers/toes.  Clips are procedural functions of
time returning a *pose* (dict); `Solver` resolves a pose into control-bone matrices and
FK rotations (object space, character faces -Y, +X = character's left), the keyer writes
one key per frame (60 fps), and `bake_clip` bakes the visual result to deform bones.

Pose fields (all optional; missing -> neutral):
  hips      Vector offset of the pelvis from its rest position (object space)
  hips_rot  (pitch, roll, yaw) deg: pitch>0 bends forward, roll>0 leans left, yaw>0 turns left
  spine/chest/uchest/neck/head  (pitch, roll, yaw) deg relative rotations
  clav_L/clav_R  (pitch, roll, yaw) deg (shrug: roll)
  hand_L/hand_R  HandSpec dict: frame 'chest'|'obj', pos (wrist, or tip if tip=True), fwd, palm,
                 pole (object-space offset direction from the shoulder, or chest-frame if frame='chest')
  foot_L/foot_R  FootSpec dict: ball (x, y) + lift, yaw, heel, pitch, toe (deg), pole (optional)
  fing_L/fing_R  (curl, thumb, spread)  curl 0 open .. 1 fist
  jaw       deg (open > 0)
  ear_L/ear_R  (pitch, roll, yaw) deg (pitch<0 = pinned back)
  tail      list of (pitch, roll, yaw) per tail bone
"""
import math
import numpy as np
import bpy
from mathutils import Vector, Matrix, Quaternion, Euler

FPS = 60
UPV = Vector((0, 0, 1))
FWDV = Vector((0, -1, 0))
LEFTV = Vector((1, 0, 0))


def rad(d):
    return d * math.pi / 180.0


def R3(p=0.0, r=0.0, y=0.0):
    """Object-space rotation from (pitch, roll, yaw) degrees."""
    return (Matrix.Rotation(rad(y), 3, "Z") @ Matrix.Rotation(rad(r), 3, "Y") @ Matrix.Rotation(rad(p), 3, "X"))


def V(*a):
    return Vector(a if len(a) == 3 else a[0])


def ease(u, kind="smooth"):
    u = min(max(u, 0.0), 1.0)
    if kind == "linear":
        return u
    if kind == "in":
        return u * u
    if kind == "out":
        return 1 - (1 - u) * (1 - u)
    if kind == "in3":
        return u * u * u
    if kind == "out3":
        return 1 - (1 - u) ** 3
    if kind == "snap":        # fast attack, soft settle
        return 1 - (1 - u) ** 4
    if kind == "hold":
        return 0.0
    return u * u * (3 - 2 * u)


def smooth01(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------- pose interpolation
def _lerp(a, b, u):
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        if a.get("frame") is not None or b.get("frame") is not None or "ball" in a or "ball" in b:
            if ("ball" in a) and ("ball" in b):
                out = {}
                for k in set(a) | set(b):
                    out[k] = _lerp(a.get(k), b.get(k), u)
                return out
            return {"mix": (a, b, u)}
        out = {}
        for k in set(a) | set(b):
            out[k] = _lerp(a.get(k), b.get(k), u)
        return out
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * u
    if isinstance(a, Vector):
        return a.lerp(b, u)
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return b if u >= 0.5 else a
        return type(a)(_lerp(x, y, u) for x, y in zip(a, b)) if isinstance(a, tuple) else [_lerp(x, y, u) for x, y in zip(a, b)]
    if isinstance(a, str) or isinstance(a, bool):
        return b if u >= 0.5 else a
    return b if u >= 0.5 else a


def lerp_pose(a, b, u):
    return _lerp(a, b, u)


def keyed(t, keys):
    """keys: [(time, pose, ease_kind_to_next), ...] sorted by time."""
    if t <= keys[0][0]:
        return keys[0][1]
    for i in range(len(keys) - 1):
        t0, p0, e = keys[i][0], keys[i][1], keys[i][2] if len(keys[i]) > 2 else "smooth"
        t1, p1 = keys[i + 1][0], keys[i + 1][1]
        if t <= t1:
            u = (t - t0) / max(t1 - t0, 1e-9)
            return lerp_pose(p0, p1, ease(u, e))
    return keys[-1][1]


def add(pose, **kw):
    """Return a copy of pose with additive offsets for tuple/Vector/number fields."""
    out = dict(pose)
    for k, v in kw.items():
        cur = out.get(k)
        if cur is None:
            out[k] = v
        elif isinstance(cur, Vector):
            out[k] = cur + Vector(v)
        elif isinstance(cur, tuple):
            out[k] = tuple(x + y for x, y in zip(cur, v))
        elif isinstance(cur, (int, float)):
            out[k] = cur + v
        else:
            out[k] = v
    return out


# ----------------------------------------------------------------------------- rig info / control rig
class RigInfo:
    def __init__(self, arm, rig_json):
        self.arm = arm
        self.rj = rig_json
        bones = arm.data.bones
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.rest3 = {n: m.to_3x3() for n, m in self.rest.items()}
        self.head = {b.name: b.head_local.copy() for b in bones}
        self.tail = {b.name: b.tail_local.copy() for b in bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.length = {b.name: b.length for b in bones}
        self.deform = [b.name for b in bones if b.use_deform]
        self.tail_bones = sorted([n for n in self.head if n.startswith("Tail")], key=lambda s: int(s[4:]))
        self.ear_bones = {s: sorted([n for n in self.head if n.startswith(s + "Ear")]) for s in ("Left", "Right")}
        self.fingers = ("Thumb", "Index", "Middle", "Ring")
        L = self.length
        self.arm_len = {s: L[s + "UpperArm"] + L[s + "LowerArm"] for s in ("Left", "Right")}
        self.leg_len = {s: L[s + "UpperLeg"] + L[s + "LowerLeg"] for s in ("Left", "Right")}
        # foot geometry (rest)
        self.ball_rest = {s: self.head[s + "Toes"].copy() for s in ("Left", "Right")}
        self.ankle_rest = {s: self.head[s + "Foot"].copy() for s in ("Left", "Right")}
        self.toe_rest = {s: self.tail[s + "Toes"].copy() for s in ("Left", "Right")}
        self.wrist_rest = {s: self.head[s + "Hand"].copy() for s in ("Left", "Right")}

    def rel(self, name):
        p = self.parent[name]
        if p is None:
            return self.rest[name].copy()
        return self.rest[p].inverted() @ self.rest[name]


CTRL = ["IK_Hand.L", "IK_Hand.R", "IK_Foot.L", "IK_Foot.R", "Pole_Elbow.L", "Pole_Elbow.R", "Pole_Knee.L", "Pole_Knee.R"]


def side_tag(side):
    return "L" if side == "Left" else "R"


def build_control_rig(arm):
    """Adds IK controls + constraints. Returns nothing; pole angles calibrated separately."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for side in ("Left", "Right"):
        t = side_tag(side)
        h = eb[side + "Hand"]
        c = eb.new("IK_Hand." + t)
        c.head, c.tail, c.roll = h.head.copy(), h.tail.copy(), h.roll
        c.parent = eb["Root"]
        c.use_deform = False
        f = eb[side + "Foot"]
        c = eb.new("IK_Foot." + t)
        c.head, c.tail, c.roll = f.head.copy(), f.tail.copy(), f.roll
        c.parent = eb["Root"]
        c.use_deform = False
        el = eb[side + "LowerArm"].head.copy()
        c = eb.new("Pole_Elbow." + t)
        c.head = el + Vector((0, 0.35, -0.10))
        c.tail = c.head + Vector((0, 0.05, 0))
        c.parent = eb["Root"]
        c.use_deform = False
        kn = eb[side + "LowerLeg"].head.copy()
        c = eb.new("Pole_Knee." + t)
        c.head = kn + Vector((0, -0.45, 0))
        c.tail = c.head + Vector((0, -0.05, 0))
        c.parent = eb["Root"]
        c.use_deform = False
    bpy.ops.object.mode_set(mode="POSE")
    pbs = arm.pose.bones
    for pb in pbs:
        pb.rotation_mode = "QUATERNION"
    for side in ("Left", "Right"):
        t = side_tag(side)
        for chain, tgt, pole in (("LowerArm", "IK_Hand." + t, "Pole_Elbow." + t), ("LowerLeg", "IK_Foot." + t, "Pole_Knee." + t)):
            ik = pbs[side + chain].constraints.new("IK")
            ik.name = "IK"
            ik.target = arm
            ik.subtarget = tgt
            ik.pole_target = arm
            ik.pole_subtarget = pole
            ik.chain_count = 2
            ik.use_stretch = False
            ik.use_tail = True
            ik.iterations = 200
        for bone, tgt in ((side + "Hand", "IK_Hand." + t), (side + "Foot", "IK_Foot." + t)):
            cr = pbs[bone].constraints.new("COPY_ROTATION")
            cr.name = "CopyRot"
            cr.target = arm
            cr.subtarget = tgt
            cr.target_space = "WORLD"
            cr.owner_space = "WORLD"
            cr.mix_mode = "REPLACE"
    bpy.ops.object.mode_set(mode="OBJECT")


def set_constraints_enabled(arm, enabled):
    for pb in arm.pose.bones:
        for c in pb.constraints:
            c.enabled = enabled
            c.mute = not enabled


def calibrate_poles(arm, info):
    """Pick pole_angle per chain so the rest pose is reproduced exactly."""
    pbs = arm.pose.bones
    res = {}
    for pb in pbs:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for side in ("Left", "Right"):
        for chain, mid in (("LowerArm", side + "LowerArm"), ("LowerLeg", side + "LowerLeg")):
            ik = pbs[side + chain].constraints["IK"]
            rest_mid = info.head[mid]
            best = (1e9, 0.0)
            for ang in range(-180, 181, 5):
                ik.pole_angle = rad(ang)
                bpy.context.view_layer.update()
                d = (pbs[mid].head - rest_mid).length
                if d < best[0]:
                    best = (d, float(ang))
            a0 = best[1]
            for k in range(-10, 11):
                ang = a0 + k * 0.5
                ik.pole_angle = rad(ang)
                bpy.context.view_layer.update()
                d = (pbs[mid].head - rest_mid).length
                if d < best[0]:
                    best = (d, ang)
            ik.pole_angle = rad(best[1])
            res[side + chain] = best
    bpy.context.view_layer.update()
    return res


# ----------------------------------------------------------------------------- solver
class Solver:
    def __init__(self, info):
        self.I = info

    def fk_matrix(self, name, local_rots, hips_M, cache):
        if name in cache:
            return cache[name]
        I = self.I
        if name == "Hips":
            M = hips_M
        else:
            p = I.parent[name]
            Mp = self.fk_matrix(p, local_rots, hips_M, cache) if p is not None else I.rest[p if p else name]
            if p is None:
                Mp = Matrix.Identity(4)
                M = I.rest[name] @ local_rots.get(name, Matrix.Identity(3)).to_4x4()
            else:
                M = Mp @ I.rel(name) @ local_rots.get(name, Matrix.Identity(3)).to_4x4()
        cache[name] = M
        return M

    def local_from_obj(self, name, rot3):
        """Local rotation for bone `name` equivalent to rotating it by object-space rot3 (in rest frame)."""
        r = self.I.rest3[name]
        return r.transposed() @ rot3 @ r

    def resolve(self, pose):
        I = self.I
        out = {}
        # ---- hips
        hoff = V(pose.get("hips", (0, 0, 0)))
        hr = pose.get("hips_rot", (0, 0, 0))
        Rh = R3(*hr)
        hips_M = Matrix.Translation(I.head["Hips"] + hoff) @ (Rh @ I.rest3["Hips"]).to_4x4()
        out["Hips"] = hips_M
        local = {}
        for key, bone in (("spine", "Spine"), ("chest", "Chest"), ("uchest", "UpperChest"), ("neck", "Neck"), ("head", "Head")):
            if key in pose:
                local[bone] = self.local_from_obj(bone, R3(*pose[key]))
        for side in ("Left", "Right"):
            k = "clav_" + side_tag(side)
            if k in pose:
                local[side + "Shoulder"] = self.local_from_obj(side + "Shoulder", R3(*pose[k]))
        # jaw / ears / tail / fingers / toes: local rotations in bone frame helpers
        if "jaw" in pose:
            local["Jaw"] = self.local_from_obj("Jaw", R3(pose["jaw"], 0, 0))
        for side in ("Left", "Right"):
            e = pose.get("ear_" + side_tag(side))
            if e is not None:
                bones = I.ear_bones[side]
                for i, b in enumerate(bones):
                    w = 1.0 if i == 0 else 0.6
                    p, r, y = e
                    s = 1 if side == "Left" else -1
                    local[b] = self.local_from_obj(b, R3(p * w, r * w * s, y * w * s))
        if "tail" in pose and I.tail_bones:
            for b, rot in zip(I.tail_bones, pose["tail"]):
                local[b] = self.local_from_obj(b, R3(*rot))
        for side in ("Left", "Right"):
            f = pose.get("fing_" + side_tag(side))
            if f is not None:
                curl, thumb, spread = (tuple(f) + (0.0, 0.0, 0.0))[:3]
                for fn in ("Index", "Middle", "Ring"):
                    sp = {"Index": 1, "Middle": 0, "Ring": -1}[fn] * spread
                    local[f"{side}{fn}1"] = Matrix.Rotation(rad(curl * 75), 3, "X") @ Matrix.Rotation(rad(sp * 12), 3, "Z")
                    local[f"{side}{fn}2"] = Matrix.Rotation(rad(curl * 85), 3, "X")
                local[f"{side}Thumb1"] = Matrix.Rotation(rad(thumb * 35), 3, "X")
                local[f"{side}Thumb2"] = Matrix.Rotation(rad(thumb * 55), 3, "X")
        out["local"] = local
        cache = {}
        self.cache = cache
        uc = self.fk_matrix("UpperChest", local, hips_M, cache)
        out["chest_M"] = uc
        out["head_M"] = self.fk_matrix("Head", local, hips_M, cache)
        sh = {}
        for side in ("Left", "Right"):
            Ms = self.fk_matrix(side + "Shoulder", local, hips_M, cache)
            sh[side] = Ms @ Vector((0, I.length[side + "Shoulder"], 0))
        out["shoulder"] = sh
        hipj = {}
        for side in ("Left", "Right"):
            hipj[side] = (hips_M @ I.rel(side + "UpperLeg")).translation
        out["hipj"] = hipj
        # ---- hands
        for side in ("Left", "Right"):
            spec = pose.get("hand_" + side_tag(side))
            wrist, Rw, pole = self.resolve_hand(side, spec, out)
            out["IK_Hand." + side_tag(side)] = Matrix.Translation(wrist) @ (Rw @ I.rest3[side + "Hand"]).to_4x4()
            out["Pole_Elbow." + side_tag(side)] = pole
            out["wrist_" + side] = wrist
            out["handR_" + side] = Rw
        # ---- feet
        for side in ("Left", "Right"):
            spec = pose.get("foot_" + side_tag(side))
            ankle, Rf, toes_local, pole = self.resolve_foot(side, spec, out)
            out["IK_Foot." + side_tag(side)] = Matrix.Translation(ankle) @ (Rf @ I.rest3[side + "Foot"]).to_4x4()
            out["Pole_Knee." + side_tag(side)] = pole
            local[side + "Toes"] = toes_local
            out["ankle_" + side] = ankle
        # tail tip (FK) for checks / solvers
        if I.tail_bones:
            Mt = self.fk_matrix(I.tail_bones[-1], local, hips_M, cache)
            out["tail_tip"] = Mt @ Vector((0, I.length[I.tail_bones[-1]], 0))
        return out

    # ---- hands
    def chest_frame(self, out):
        M = out["chest_M"]
        R = M.to_3x3().normalized()
        # bone axes: X left, Y up (spine), Z forward
        return M.translation, R

    def resolve_hand(self, side, spec, out):
        I = self.I
        s = 1 if side == "Left" else -1
        if spec is None:
            spec = {"frame": "rest"}
        if "mix" in spec:
            a, b, u = spec["mix"]
            wa, Ra, pa = self.resolve_hand(side, a, out)
            wb, Rb, pb = self.resolve_hand(side, b, out)
            qa, qb = Ra.to_quaternion(), Rb.to_quaternion()
            if qa.dot(qb) < 0:
                qb.negate()
            return wa.lerp(wb, u), qa.slerp(qb, u).to_matrix(), pa.lerp(pb, u)
        shoulder = out["shoulder"][side]
        o, Rc = self.chest_frame(out)
        fr = spec.get("frame", "chest")
        if fr == "rest":
            return I.wrist_rest[side].copy(), Matrix.Identity(3), I.head[side + "LowerArm"] + Vector((s * 0.1, 0.35, -0.1))

        def vec(v, frame):
            v = Vector(v)
            if frame == "chest":
                # chest-frame coords: (left, up, forward); mirrored for the right side via x sign
                return Rc @ Vector((v.x * s, v.y, v.z))
            return Vector((v.x, v.y, v.z))
        fwd = vec(spec.get("fwd", (0, 0, 1) if fr == "chest" else (0, -1, 0)), fr).normalized()
        palm = vec(spec.get("palm", (-1, 0, 0) if fr == "chest" else (-s, 0, 0)), fr)
        palm = (palm - fwd * palm.dot(fwd)).normalized()
        X = fwd.cross(palm)
        Rw = Matrix((X, fwd, palm)).transposed()       # columns X, Y(fwd), Z(palm)
        # convert "hand-relative" rotation: rest hand axes are (x, a, n); we want hand Y=fwd, Z=palm
        Rrest = I.rest3[side + "Hand"]
        Rdelta = Rw @ Rrest.transposed()
        if fr == "chest":
            pos = o + vec(spec["pos"], "chest")
        else:
            pos = Vector(spec["pos"])
        if spec.get("tip"):
            pos = pos - fwd * I.length[side + "Hand"]
        out["wrist_des_" + side] = pos.copy()
        # reach clamp (keep a hair of bend so the pole stays meaningful)
        d = pos - shoulder
        maxr = I.arm_len[side] * 0.992
        if d.length > maxr:
            pos = shoulder + d.normalized() * maxr
        pole_dir = spec.get("pole")
        if pole_dir is None:
            pole_dir = (0.35, -0.55, -0.35) if fr == "chest" else (s * 0.35, 0.35, -0.5)
        pd = vec(pole_dir, fr if fr != "obj" else "obj")
        elbow_guess = (shoulder + pos) * 0.5
        pole = elbow_guess + pd.normalized() * 0.45
        return pos, Rdelta, pole

    # ---- feet
    def resolve_foot(self, side, spec, out):
        I = self.I
        s = 1 if side == "Left" else -1
        ball_r = I.ball_rest[side]
        ankle_r = I.ankle_rest[side]
        if spec is None:
            spec = {"ball": (ball_r.x, ball_r.y), "lift": 0.0}
        if "mix" in spec:
            a, b, u = spec["mix"]
            spec = lerp_pose(dict(a), dict(b), u)
        bx, by = spec.get("ball", (ball_r.x, ball_r.y))
        lift = spec.get("lift", 0.0)
        yaw = spec.get("yaw", 0.0)
        heel = spec.get("heel", 0.0)
        pitch = spec.get("pitch", 0.0)
        toe = spec.get("toe", 0.0)
        roll = spec.get("roll", 0.0)
        Ry = Matrix.Rotation(rad(yaw), 3, "Z")
        Rfoot = Ry @ Matrix.Rotation(rad(roll), 3, "Y") @ Matrix.Rotation(rad(heel + pitch), 3, "X")
        B = Vector((bx, by, ball_r.z + lift))
        if spec.get("tip") is not None:
            # place the toe tip exactly (kicks): solve ball from tip
            Rt = Ry @ Matrix.Rotation(rad(roll), 3, "Y") @ Matrix.Rotation(rad(pitch + toe), 3, "X")
            B = Vector(spec["tip"]) - Rt @ (I.toe_rest[side] - ball_r)
        ankle = B - Rfoot @ (ball_r - ankle_r)
        out["ankle_des_" + side] = ankle.copy()
        # reach clamp
        hj = out["hipj"][side]
        d = ankle - hj
        maxr = I.leg_len[side] * 0.995
        if d.length > maxr:
            ankle = hj + d.normalized() * maxr
        # toes: world rotation should be Ry*R(pitch+toe) (flat unless pitched), local = inv(parent)*that
        Rparent_world = Rfoot @ I.rest3[side + "Foot"]
        Rtoes_world = Ry @ Matrix.Rotation(rad(roll), 3, "Y") @ Matrix.Rotation(rad(pitch + toe), 3, "X") @ I.rest3[side + "Toes"]
        rel3 = (I.rest3[side + "Foot"].transposed() @ I.rest3[side + "Toes"])
        toes_local = (Rparent_world @ rel3).transposed() @ Rtoes_world
        pole_dir = spec.get("pole")
        knee_mid = (hj + ankle) * 0.5
        if pole_dir is None:
            fdir = Ry @ Vector((s * 0.75, -1.0, 0.0))
            pole = knee_mid + fdir.normalized() * 0.5
        else:
            pole = knee_mid + Vector(pole_dir).normalized() * 0.5
        return ankle, Rfoot, toes_local, pole


# ----------------------------------------------------------------------------- keying / baking
KEY_FK = None


def key_pose(arm, info, res, frame):
    pbs = arm.pose.bones
    pbs["Hips"].matrix = res["Hips"]
    pbs["Hips"].keyframe_insert("location", frame=frame, group="Hips")
    pbs["Hips"].keyframe_insert("rotation_quaternion", frame=frame, group="Hips")
    for name in CTRL:
        M = res[name]
        pb = pbs[name]
        if isinstance(M, Vector):
            M = Matrix.Translation(M) @ info.rest3[name].to_4x4()
        pb.matrix = M
        pb.keyframe_insert("location", frame=frame, group=name)
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)
    local = res["local"]
    for name in KEY_FK:
        pb = pbs[name]
        R = local.get(name, Matrix.Identity(3))
        q = R.to_quaternion()
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)


def fk_bone_list(info):
    names = ["Spine", "Chest", "UpperChest", "Neck", "Head", "Jaw", "LeftShoulder", "RightShoulder",
             "LeftToes", "RightToes"] + info.tail_bones + info.ear_bones["Left"] + info.ear_bones["Right"]
    for side in ("Left", "Right"):
        for fn in info.fingers:
            names += [f"{side}{fn}1", f"{side}{fn}2"]
    return names


def fix_quat_continuity(action):
    """Make consecutive quaternion keys take the short path (avoid flips)."""
    groups = {}
    for fc in action.fcurves:
        if fc.data_path.endswith("rotation_quaternion"):
            groups.setdefault(fc.data_path, [None] * 4)[fc.array_index] = fc
    for dp, fcs in groups.items():
        if any(f is None for f in fcs):
            continue
        n = len(fcs[0].keyframe_points)
        vals = np.zeros((4, n))
        for i, f in enumerate(fcs):
            co = np.zeros(n * 2)
            f.keyframe_points.foreach_get("co", co)
            vals[i] = co[1::2]
        for k in range(1, n):
            if np.dot(vals[:, k], vals[:, k - 1]) < 0:
                vals[:, k] *= -1
        for i, f in enumerate(fcs):
            co = np.zeros(n * 2)
            f.keyframe_points.foreach_get("co", co)
            co[1::2] = vals[i]
            f.keyframe_points.foreach_set("co", co)
            f.update()


def author_clip(arm, info, solver, name, pose_fn, duration, loop):
    """Create ctrl action with one key per frame. Returns (action, nframes, resolved list)."""
    global KEY_FK
    if KEY_FK is None:
        KEY_FK = fk_bone_list(info)
    n = max(1, int(round(duration * FPS)))
    act = bpy.data.actions.new("ctrl_" + name)
    act.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = act
    resolved = []
    for f in range(n + 1):
        t = f / FPS
        if loop and f == n:
            t = 0.0
        pose = pose_fn(t)
        res = solver.resolve(pose)
        key_pose(arm, info, res, f)
        resolved.append(res)
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    fix_quat_continuity(act)
    return act, n, resolved


def bake_clip(arm, info, name, n):
    """Visual-bake the current (ctrl) action onto deform bones -> new action `name`."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for pb in arm.pose.bones:
        pb.bone.select = pb.bone.use_deform
    ctrl = arm.animation_data.action
    bpy.ops.nla.bake(frame_start=0, frame_end=n, step=1, only_selected=True, visual_keying=True,
                     clear_constraints=False, clear_parents=False, use_current_action=False,
                     clean_curves=False, bake_types={"POSE"}, channel_types={"LOCATION", "ROTATION"})
    baked = arm.animation_data.action
    baked.name = name
    baked.use_fake_user = True
    for fc in baked.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    fix_quat_continuity(baked)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.animation_data.action = ctrl
    return baked


# ----------------------------------------------------------------------------- evaluation helpers
def eval_points(arm, info, action, frames):
    """Evaluate deform-bone world points for a baked action at given frames (constraints off)."""
    set_constraints_enabled(arm, False)
    arm.animation_data.action = action
    sc = bpy.context.scene
    pts = []
    pbs = arm.pose.bones
    for f in frames:
        sc.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
        d = {}
        for n in ("RightHand", "LeftHand", "RightToes", "LeftToes", "RightUpperArm", "LeftUpperArm", "Head",
                  "LeftFoot", "RightFoot"):
            d[n + ".head"] = pbs[n].head.copy()
            d[n + ".tail"] = pbs[n].tail.copy()
        if info.tail_bones:
            d["tail_tip"] = pbs[info.tail_bones[-1]].tail.copy()
        # foot sole points (rest offsets of sole below ankle/ball, transformed)
        for side in ("Left", "Right"):
            Mf = pbs[side + "Foot"].matrix
            Mt = pbs[side + "Toes"].matrix
            ankle_r = info.ankle_rest[side]
            ball_r = info.ball_rest[side]
            heel_local = info.rest[side + "Foot"].inverted() @ Vector((ankle_r.x, ankle_r.y + 0.01, 0.0))
            ball_local = info.rest[side + "Toes"].inverted() @ Vector((ball_r.x, ball_r.y, 0.0))
            tip_local = info.rest[side + "Toes"].inverted() @ Vector((info.toe_rest[side].x, info.toe_rest[side].y - 0.01, 0.0))
            d[side + "_heel"] = Mf @ heel_local
            d[side + "_ballsole"] = Mt @ ball_local
            d[side + "_tipsole"] = Mt @ tip_local
        pts.append(d)
    set_constraints_enabled(arm, True)
    return pts


def path_at(path, t):
    """Linear interpolation of JSON path [[t, x, y, z], ...] -> Blender object space."""
    P = path
    if t <= P[0][0]:
        q = P[0]
    elif t >= P[-1][0]:
        q = P[-1]
    else:
        for a, b in zip(P[:-1], P[1:]):
            if a[0] <= t <= b[0]:
                u = (t - a[0]) / max(b[0] - a[0], 1e-9)
                q = [a[0], a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u, a[3] + (b[3] - a[3]) * u]
                break
    x, y, z = q[1], q[2], q[3]
    return Vector((-x, -z, y))


def to_obj(x, y, z):
    """action-local (x right, y up, z forward) -> Blender object space."""
    return Vector((-x, -z, y))
