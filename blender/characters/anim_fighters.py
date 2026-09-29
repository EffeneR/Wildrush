"""WILDRUSH character pipeline - per-fighter attacks, skills and the clip registry.

The registry derives the required clip names + durations from CHARACTER_CONTRACT §5 and the
fighter JSON (light/heavy/skills: `clip` + `total_s`, and every `clips` map entry) and fails
if any required clip has no builder.
"""
import math
import json
import os
from mathutils import Vector, Matrix
from anim_lib import V, R3, rad, ease, smooth01, keyed, lerp_pose, add, path_at, to_obj, FPS
import anim_clips as AC

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def shared_json():
    with open(os.path.join(REPO, "game", "data", "tuning", "shared.json")) as f:
        return json.load(f)


# ----------------------------------------------------------------------------- generic JSON strike
def hit_side(limb):
    return {"hand_r": ("Right", -1), "hand_l": ("Left", 1), "foot_r": ("Right", -1), "foot_l": ("Left", 1)}.get(limb, (None, 0))


def attack(C, act, cfg, base_fn=None, t_offset=0.0, clip_len=None, windows=None):
    """Generic JSON-driven strike clip.
    cfg: style ('jab'|'swipe'|'rake'|'kick'|'slam'), twist, lean, shift, step, chamber (chest-frame),
         fing, crouch.  windows: optional list of (hit, t0, t1) in clip-local time."""
    total = clip_len if clip_len is not None else act["total_s"]
    hits = []
    if windows is None:
        for h in act.get("hits", []):
            hits.append((h, h["t0"] - t_offset, h["t1"] - t_offset, t_offset))
    else:
        hits = [w if len(w) == 4 else (w[0], w[1], w[2], 0.0) for w in windows]
    base_fn = base_fn or (lambda t: C.stance())
    st = C.st
    sched = []
    prev_end = 0.0
    for i, (h, t0, t1, off) in enumerate(hits):
        a = prev_end if i == 0 else max(prev_end, t0 - 0.16)
        nxt = hits[i + 1][1] - 0.16 if i + 1 < len(hits) else total
        b = max(min(nxt, total), t1 + 0.03)
        limb = h.get("limb", act.get("limb"))
        sched.append(dict(h=h, t0=t0, t1=t1, a=a, b=b, limb=limb, off=off))
        prev_end = b

    def drive(t, s):
        """-wind .. 1 strike curve for schedule entry s."""
        a, b, t0, t1 = s["a"], s["b"], s["t0"], s["t1"]
        if t <= a or t >= b:
            return 0.0
        tw = a + (t0 - a) * 0.65
        keys = [(a, 0.0), (tw, -0.6), (t0, -0.1), (t1, 1.0), (min(t1 + 0.07, b - 0.01), 1.0), (b, 0.0)]
        for (x0, y0), (x1, y1) in zip(keys[:-1], keys[1:]):
            if x0 <= t <= x1:
                u = (t - x0) / max(x1 - x0, 1e-6)
                return y0 + (y1 - y0) * ease(u, "smooth")
        return 0.0

    def body(t):
        p = dict(base_fn(t))
        for s in sched:
            d = drive(t, s)
            if d == 0.0:
                continue
            side, sg = hit_side(s["limb"])
            sg = -sg if sg else 0          # right-hand strikes turn the body left (+yaw)
            if s["limb"] in ("both_hands", "shoulder_r", "head", "tail_tip"):
                sg = 0
            pos, neg = max(d, 0.0), max(-d, 0.0)
            tw = cfg.get("twist", 20)
            ln = cfg.get("lean", 8)
            p = add(p, hips=(0, -cfg.get("shift", 0.08) * pos + 0.03 * neg, -cfg.get("crouch", 0.02) * abs(d)),
                    hips_rot=(ln * 0.5 * pos - cfg.get("arch", 4) * neg, 0, sg * tw * 0.55 * d),
                    spine=(ln * 0.25 * pos - cfg.get("arch", 4) * 0.5 * neg, 0, sg * tw * 0.2 * d),
                    chest=(ln * 0.25 * pos - cfg.get("arch", 4) * 0.5 * neg, 0, sg * tw * 0.25 * d),
                    head=(-ln * 0.35 * pos, 0, -sg * tw * 0.40 * d))
            step = cfg.get("step", 0.0)
            if step and "foot_L" in p and not cfg.get("air") and s["limb"] not in ("foot_l",):
                fl = dict(p["foot_L"])
                bx, by = fl["ball"]
                fl["ball"] = (bx, by - step * max(0.0, min(1.0, (d + 0.1) / 1.1)))
                fl["lift"] = fl.get("lift", 0.0) + 0.045 * math.sin(math.pi * max(0.0, min(1.0, d)))
                p["foot_L"] = fl
            if cfg.get("fing"):
                if side:
                    p["fing_" + ("L" if side == "Left" else "R")] = cfg["fing"]
                else:
                    p["fing_L"] = cfg["fing"]
                    p["fing_R"] = cfg["fing"]
        return p

    def limb_pose(p, s, t):
        ta = t + s["off"]          # JSON paths are in action time
        return AC.strike_pose(C, p, ta, s["h"], s["limb"], "punch" if cfg.get("style") == "jab" else "swipe") \
            if s["limb"] in ("hand_r", "hand_l", "both_hands") else AC.kick_pose(C, p, ta, s["h"], s["limb"])

    def f(t):
        p = body(t)
        for s in sched:
            a, b, t0, t1 = s["a"], s["b"], s["t0"], s["t1"]
            if not (a <= t <= b):
                continue
            limb = s["limb"]
            if t0 - 1e-6 <= t <= t1 + 1e-6:
                return limb_pose(p, s, min(max(t, t0), t1))
            tw = a + (t0 - a) * 0.65
            if t < t0:
                # guard -> chamber -> path start
                start = limb_pose(body(t0), s, t0)
                if limb in ("hand_r", "hand_l", "both_hands") and cfg.get("chamber") is not None:
                    ch = dict(p)
                    for side, tag in (("Left", "L"), ("Right", "R")):
                        if limb == "both_hands" or hit_side(limb)[0] == side:
                            cp = cfg["chamber"]
                            ch["hand_" + tag] = dict(frame="chest", pos=cp, fwd=cfg.get("chamber_fwd", (0.2, 0.6, 1.0)),
                                                      palm=cfg.get("chamber_palm", (-1, 0, 0)), pole=cfg.get("chamber_pole", (0.6, -0.4, -0.4)))
                    if t < tw:
                        return lerp_pose(p, ch, ease((t - a) / max(tw - a, 1e-6), "smooth"))
                    return lerp_pose(ch, start, ease((t - tw) / max(t0 - tw, 1e-6), "in"))
                if limb in ("foot_r", "foot_l") and cfg.get("chamber_foot") is not None:
                    ch = dict(p)
                    tag = "R" if limb == "foot_r" else "L"
                    cf = dict(cfg["chamber_foot"])
                    bx, by = cf["ball"]
                    if (tag == "L" and bx < 0) or (tag == "R" and bx > 0):      # chamber on the kicking side
                        cf["ball"] = (-bx, by)
                        cf["yaw"] = -cf.get("yaw", 0.0)
                    ch["foot_" + tag] = cf
                    if cfg.get("chamber_hips") is not None:
                        ch = add(ch, hips=cfg["chamber_hips"])
                    if t < tw:
                        return lerp_pose(p, ch, ease((t - a) / max(tw - a, 1e-6), "smooth"))
                    return lerp_pose(ch, start, ease((t - tw) / max(t0 - tw, 1e-6), "in"))
                return lerp_pose(p, start, ease((t - a) / max(t0 - a, 1e-6), "smooth"))
            # after the window: follow-through then settle
            end = limb_pose(body(t1), s, t1)
            tf = min(t1 + 0.07, b)
            if t <= tf:
                return end
            return lerp_pose(end, p, ease((t - tf) / max(b - tf, 1e-6), "smooth"))
        return p
    return f, dict(loop=False)


# ============================================================================= Nyx
NYX_ATTACKS = {
    "light_s": dict(style="jab", twist=22, lean=12, shift=0.14, step=0.10, chamber=(0.15, 0.13, 0.05),
                    chamber_fwd=(0.0, 0.5, 1.0), fing=(0.45, 0.3, 0.35)),
    "light_l": dict(style="swipe", twist=30, lean=6, shift=0.10, step=0.06, chamber=(0.42, 0.18, 0.02),
                    chamber_fwd=(0.6, 0.6, 0.4), fing=(0.45, 0.3, 0.4)),
    "light_r": dict(style="swipe", twist=30, lean=6, shift=0.10, step=0.06, chamber=(0.42, 0.18, 0.02),
                    chamber_fwd=(0.6, 0.6, 0.4), fing=(0.45, 0.3, 0.4)),
    "heavy": dict(style="rake", twist=0, lean=26, shift=0.32, step=0.20, chamber=(0.13, 0.60, -0.02),
                  chamber_fwd=(0.2, 1.0, -0.3), chamber_palm=(0, 0.2, 1.0), fing=(0.5, 0.3, 0.45), arch=10, crouch=0.05),
    "skill_e": dict(style="swipe", twist=30, lean=10, shift=0.12, step=0.08, chamber=(0.40, 0.44, 0.04),
                    chamber_fwd=(0.5, 1.0, 0.3), fing=(0.5, 0.3, 0.45)),
    "skill_r_counter": dict(style="swipe", twist=32, lean=8, shift=0.12, step=0.08, chamber=(0.40, 0.16, 0.0),
                            chamber_fwd=(0.6, 0.6, 0.4), fing=(0.5, 0.3, 0.45)),
}


def nyx_coil(C):
    st = C.st
    p = C.stance()
    p.update(hips=V(0, 0.03, -st["crouch"] - 0.21), hips_rot=(34, 0, -4), spine=(8, 0, 0), chest=(6, 0, 0),
             neck=(-26, 0, 0), head=(-20, 0, 0),
             hand_L=dict(frame="obj", pos=(0.16, -0.42, 0.20), fwd=(0.0, -1.0, -0.35), palm=(0, -0.2, -1), pole=(0.6, 0.4, 0.1)),
             hand_R=dict(frame="obj", pos=(-0.15, -0.36, 0.17), fwd=(0.0, -1.0, -0.35), palm=(0, -0.2, -1), pole=(-0.6, 0.4, 0.1)),
             foot_L=dict(ball=(0.15, -0.14), heel=10, yaw=-4), foot_R=dict(ball=(-0.15, 0.12), heel=42, yaw=-10),
             fing_L=(0.5, 0.3, 0.45), fing_R=(0.5, 0.3, 0.45), ear_L=(10, 0, 0), ear_R=(10, 0, 0))
    return p


def nyx_fly(C):
    p = C.stance()
    p.update(hips=V(0, -0.02, 0.02), hips_rot=(58, 0, 0), spine=(4, 0, 0), chest=(0, 0, 0), uchest=(-4, 0, 0),
             neck=(-38, 0, 0), head=(-30, 0, 0),
             hand_L=dict(frame="obj", pos=(0.12, -0.62, 1.05), fwd=(0, -1, 0.2), palm=(0, 0, -1), pole=(0.6, 0.3, -0.3)),
             hand_R=dict(frame="obj", pos=(-0.12, -0.62, 1.05), fwd=(0, -1, 0.2), palm=(0, 0, -1), pole=(-0.6, 0.3, -0.3)),
             foot_L=dict(ball=(0.14, 0.42), lift=0.42, heel=0, pitch=-70, yaw=0),
             foot_R=dict(ball=(-0.14, 0.52), lift=0.30, heel=0, pitch=-75, yaw=0),
             fing_L=(0.5, 0.3, 0.45), fing_R=(0.5, 0.3, 0.45), ear_L=(-20, 0, 0), ear_R=(-20, 0, 0))
    return p


def nyx_skills(C):
    fj = C.fj
    acts = fj["actions"]
    out = {}
    pounce = acts["nyx_pounce"]
    hit = pounce["hits"][0]
    clips = pounce["clips"]
    prep_d, air_d, land_d, miss_d = clips["prep"][1], clips["air"][1], clips["land"][1], clips["land_miss"][1]
    coil = nyx_coil(C)
    fly = nyx_fly(C)

    def prep(t):
        p = dict(keyed(t, [(0.0, C.stance()), (prep_d * 0.8, coil, "out"), (prep_d, add(coil, hips=(0, -0.02, 0.01)))]))
        p["tail"] = C.tail(t, amp=0.9, freq=6.0, lift=28, curl=6)
        return p
    out["skill_q_prep"] = (prep, prep_d, dict(loop=False))

    def air_base(t):
        p = dict(lerp_pose(coil, fly, ease(t / 0.10, "out"))) if t < 0.10 else dict(fly)
        p["tail"] = C.tail(t, amp=0.3, freq=3.0, lift=18, curl=-4)
        return p
    # hit window in air-clip local time
    w_air = [(hit, hit["t0"] - prep_d, min(hit["t1"] - prep_d, air_d), prep_d)]
    f_air, _ = attack(C, pounce, dict(style="swipe", twist=0, lean=0, shift=0.0, fing=(0.5, 0.3, 0.45), air=True),
                      base_fn=air_base, clip_len=air_d, windows=w_air)
    out["skill_q_air"] = (f_air, air_d, dict(loop=False, hits=[("both_hands", hit, prep_d)]))

    land_t0 = prep_d + air_d
    rem = max(0.0, hit["t1"] - land_t0)
    slam = dict(coil, hips=V(0, -0.05, -C.st["crouch"] - 0.24), hips_rot=(40, 0, 0),
                hand_L=dict(frame="obj", pos=(0.12, -0.55, 0.12), fwd=(0, -1, -0.6), palm=(0, 0, -1), pole=(0.6, 0.4, 0.2)),
                hand_R=dict(frame="obj", pos=(-0.12, -0.55, 0.12), fwd=(0, -1, -0.6), palm=(0, 0, -1), pole=(-0.6, 0.4, 0.2)),
                foot_L=dict(ball=(0.16, -0.18), heel=8), foot_R=dict(ball=(-0.16, 0.14), heel=40))

    def land_fn(dur, miss):
        def f(t):
            start = AC.strike_pose(C, fly, land_t0 + min(t, rem), hit, "both_hands", "swipe")
            if t <= rem:
                p = dict(start)
            elif not miss:
                p = dict(keyed(t, [(rem, start), (0.10, slam, "out"), (0.22, slam), (dur, C.stance())]))
            else:
                slide = add(slam, hips=(0, -0.10, -0.03), hips_rot=(8, 4, 6), head=(10, 0, 0))
                p = dict(keyed(t, [(rem, start), (0.10, slam, "out"), (0.30, slide), (0.48, slide), (dur, C.stance())]))
            p["tail"] = C.tail(t, amp=0.5, freq=3.0, lift=10 * (1 - t / dur))
            return p
        return f
    out["skill_q_land"] = (land_fn(land_d, False), land_d, dict(loop=False, hits=[("both_hands", hit, land_t0)]))
    out["skill_q_land_miss"] = (land_fn(miss_d, True), miss_d, dict(loop=False, hits=[("both_hands", hit, land_t0)]))

    # Crosscut (two diagonal claw strikes)
    cc = acts["nyx_crosscut"]
    out["skill_e"] = attack(C, cc, NYX_ATTACKS["skill_e"]) + (None,)
    out["skill_e"] = (out["skill_e"][0], cc["total_s"], dict(loop=False))

    # Slip left / right
    slip = acts["nyx_slip"]
    for key, sgn in (("left", 1), ("right", -1)):
        name, dur = slip["clips"][key]
        st = C.st
        low = C.stance(crouch_add=0.10)
        low = add(low, hips=(sgn * 0.10, 0.02, 0), hips_rot=(10, -sgn * 14, 0), chest=(0, -sgn * 8, 0), head=(0, sgn * 10, 0))
        low = dict(low)
        lead = "L" if sgn > 0 else "R"
        trail = "R" if sgn > 0 else "L"
        low["foot_" + lead] = dict(ball=(sgn * 0.34, -0.04), heel=6, yaw=sgn * 10)
        low["foot_" + trail] = dict(ball=(-sgn * 0.06, 0.06), heel=30, lift=0.03, yaw=sgn * 10)
        air = add(low, hips=(sgn * 0.05, 0, 0.03))
        air = dict(air)
        air["foot_" + trail] = dict(ball=(sgn * 0.10, 0.04), heel=10, lift=0.12, pitch=-15, yaw=sgn * 10)
        air["hand_L"] = C.hand("L", "Left", pos=(0.10, 0.12, 0.22))
        air["hand_R"] = C.hand("R", "Right", pos=(0.12, 0.10, 0.16))

        def fslip(t, low=low, air=air, dur=dur, sgn=sgn):
            p = dict(keyed(t, [(0.0, C.stance()), (0.07, low, "out"), (0.20, air), (0.30, low), (dur, C.stance())]))
            p["tail"] = C.tail(t, amp=0.4, freq=2.0, side=-sgn * 30 * math.sin(math.pi * min(t / dur, 1)))
            p["ear_L"] = (-14, 0, 0)
            p["ear_R"] = (-14, 0, 0)
            return p
        out[name] = (fslip, dur, dict(loop=False))
    ctr = acts["nyx_slip_counter"]
    f_ctr, _ = attack(C, ctr, NYX_ATTACKS["skill_r_counter"])
    out[ctr["clip"]] = (f_ctr, ctr["total_s"], dict(loop=False))
    return out


def nyx_perch(C):
    st = C.st
    H = 1.8
    dur = 0.45

    def edge(t):
        return H * (1 - ease(t / dur, "smooth"))
    keysp = []

    def f(t):
        e = edge(t)
        u = t / dur
        p = C.stance()
        hand_z = max(e + 0.03, 0.55 if u > 0.6 else e + 0.03)
        grip = dict(frame="obj", pos=(0.17, -0.34, min(e + 0.04, 1.85)), fwd=(0, -0.8, 0.6), palm=(0, 0.2, -1), pole=(0.6, 0.4, -0.3))
        gripR = dict(grip, pos=(-0.17, -0.34, min(e + 0.04, 1.85)), pole=(-0.6, 0.4, -0.3))
        if u < 0.72:
            p["hand_L"] = grip
            p["hand_R"] = gripR
        else:
            v = (u - 0.72) / 0.28
            p["hand_L"] = {"mix": (grip, C.hand("L", "Left"), ease(v))}
            p["hand_R"] = {"mix": (gripR, C.hand("R", "Right"), ease(v))}
        climb = 1 - abs(2 * u - 1)
        p["hips"] = V(0, -0.10 * climb, -st["crouch"] - 0.12 * climb + 0.10 * (1 - u) * (u < 0.3))
        p["hips_rot"] = (20 * climb + 6, 0, 0)
        p["head"] = (-18 * climb, 0, 0)
        # legs: kick off, tuck up the wall, land on top of the ledge (edge height relative to origin)
        fz = max(0.0, min(e, 0.55))
        p["foot_L"] = dict(ball=(0.15, -0.20 * climb - 0.02), lift=fz * (u > 0.15), heel=10, pitch=-30 * climb, yaw=0)
        p["foot_R"] = dict(ball=(-0.15, 0.05 - 0.20 * climb), lift=max(0.0, min(e, 0.50)) * (u > 0.30), heel=20, pitch=-30 * climb, yaw=-8)
        p["tail"] = C.tail(t, amp=0.6, freq=3.0, lift=20 * climb)
        p["ear_L"] = (6, 0, 0)
        p["ear_R"] = (6, 0, 0)
        return p
    return f, dur, dict(loop=False)


# ============================================================================= registry
ATTACKS = {"nyx": NYX_ATTACKS}
SKILLS = {"nyx": nyx_skills}


def movement_mults(C):
    sh = shared_json()["movement"]
    fj = C.fj
    return fj.get("strafe_mult", sh["strafe_mult"]), fj.get("backpedal_mult", sh["backpedal_mult"])


def required_clips(fj):
    """Contract §5 names + durations (JSON-derived for attacks/skills)."""
    req = {}
    common = dict(idle=2.0, walk_f=1.0, walk_b=1.0, walk_l=1.0, walk_r=1.0, turn_l=0.5, turn_r=0.5,
                  jump_start=0.12, jump_air=0.5, jump_fall=0.5, jump_land=0.2, dodge_f=0.367, dodge_b=0.367,
                  dodge_l=0.367, dodge_r=0.367, guard_enter=0.1, guard_hold=1.0, guard_exit=0.12, guard_block=0.2,
                  guard_break=0.9, hit_front=0.3, hit_back=0.3, hit_heavy=0.5, stagger=0.6, knockdown=0.8, getup=0.45,
                  grabbed=0.45, knockout=1.2, respawn=0.8, victory=2.5, defeat=2.0)
    req.update(common)
    for k in ("run_f", "run_b", "run_l", "run_r"):
        req[k] = None
    acts = fj["actions"]
    for key in ("s", "l", "r", "air"):
        a = acts[fj["light"][key]]
        req[a["clip"]] = a["total_s"]
    a = acts[fj["heavy"]]
    req[a["clip"]] = a["total_s"]
    for name, a in acts.items():
        if a.get("kind") in ("skill", "counter"):
            if "clip" in a and "total_s" in a:
                req[a["clip"]] = a["total_s"]
            for k, (cn, d) in a.get("clips", {}).items():
                if cn not in req:
                    req[cn] = d
    if fj["id"] == "nyx":
        req["perch_climb"] = 0.45
    return req


def build_clips(C):
    fj = C.fj
    st = C.st
    req = required_clips(fj)
    out = {}
    f, m = AC.clip_idle(C)
    out["idle"] = (f, 2.0, m)
    for k, dv in (("f", (0, -1, 0)), ("b", (0, 1, 0)), ("l", (1, 0, 0)), ("r", (-1, 0, 0))):
        f, m = AC.gait(C, "walk", dv, 2.0, 1.0, st.get("walk_duty", 0.45))
        out["walk_" + k] = (f, 1.0, m)
    strafe, back = movement_mults(C)
    T = st["run_T"] / FPS
    for k, dv, mult in (("f", (0, -1, 0), 1.0), ("b", (0, 1, 0), back), ("l", (1, 0, 0), strafe), ("r", (-1, 0, 0), strafe)):
        spd = fj["move_speed"] * mult
        f, m = AC.gait(C, "run", dv, spd, T, st["run_duty"])
        out["run_" + k] = (f, T, m)
    out["turn_l"] = AC.clip_turn(C, True) + (None,)
    out["turn_r"] = AC.clip_turn(C, False) + (None,)
    out["turn_l"] = (out["turn_l"][0], 0.5, out["turn_l"][1])
    out["turn_r"] = (out["turn_r"][0], 0.5, out["turn_r"][1])
    for ph, d in (("start", 0.12), ("air", 0.5), ("fall", 0.5), ("land", 0.2)):
        f, m = AC.clip_jump(C, ph)
        out["jump_" + ph] = (f, d, m)
    for k in "fblr":
        f, m = AC.clip_dodge(C, k)
        out["dodge_" + k] = (f, 0.367, m)
    for ph, d in (("enter", 0.1), ("hold", 1.0), ("exit", 0.12), ("block", 0.2), ("break", 0.9)):
        f, m = AC.clip_guard(C, ph)
        out["guard_" + ph] = (f, d, m)
    for k, d in (("front", 0.3), ("back", 0.3), ("heavy", 0.5)):
        f, m = AC.clip_hit(C, k)
        out["hit_" + k] = (f, d, m)
    f, m = AC.clip_hit(C, "stagger")
    out["stagger"] = (f, 0.6, m)
    for name, fn, d in (("knockdown", AC.clip_knockdown, 0.8), ("getup", AC.clip_getup, 0.45), ("grabbed", AC.clip_grabbed, 0.45),
                        ("knockout", AC.clip_knockout, 1.2), ("respawn", AC.clip_respawn, 0.8), ("victory", AC.clip_victory, 2.5),
                        ("defeat", AC.clip_defeat, 2.0)):
        f, m = fn(C)
        out[name] = (f, d, m)
    # light / heavy from JSON
    acts = fj["actions"]
    cfgs = ATTACKS[C.fid]
    for key in ("s", "l", "r", "air"):
        a = acts[fj["light"][key]]
        cfg = cfgs.get(a["clip"], dict(style="jab"))
        if key == "air":
            jb, _ = AC.clip_jump(C, "air")
            f, m = attack(C, a, dict(cfgs.get("light_air", dict(style="swipe")), air=True, twist=10, lean=10, shift=0.0),
                          base_fn=jb)
        else:
            f, m = attack(C, a, cfg)
        out[a["clip"]] = (f, a["total_s"], m)
    a = acts[fj["heavy"]]
    f, m = attack(C, a, cfgs["heavy"])
    out[a["clip"]] = (f, a["total_s"], m)
    # skills
    for name, v in SKILLS[C.fid](C).items():
        out[name] = v
    if C.fid == "nyx":
        f, d, m = nyx_perch(C)
        out["perch_climb"] = (f, d, m)
    missing = [k for k in req if k not in out]
    if missing:
        raise RuntimeError(f"no builder for required clips: {missing}")
    for k, d in req.items():
        if d is not None and abs(out[k][1] - d) > 1e-6:
            out[k] = (out[k][0], d, out[k][2])
    return out, req


# ============================================================================= shared skill helpers
def fist(C):
    return (1.0, 0.9, 0.0)


def body_yaw(p, deg):
    return add(p, hips_rot=(0, 0, deg))


def place_point_by_hips(C, pose, key, target, side="Right", iters=2):
    """Shift the hips so an FK point (shoulder / tail tip) lands on target."""
    for _ in range(iters):
        res = C.resolve(pose)
        cur = res["shoulder"][side] if key == "shoulder" else res["tail_tip"]
        pose = add(pose, hips=tuple(target - cur))
    return pose


# ============================================================================= Bruno
BRUNO_ATTACKS = {
    "light_s": dict(style="jab", twist=20, lean=10, shift=0.12, step=0.10, chamber=(0.10, 0.28, 0.14),
                    chamber_fwd=(0.0, 0.8, 0.6), fing=(1.0, 0.9, 0.0)),
    "light_l": dict(style="jab", twist=34, lean=6, shift=0.08, step=0.05, chamber=(0.30, 0.20, 0.06),
                    chamber_fwd=(0.4, 0.5, 0.8), fing=(1.0, 0.9, 0.0)),
    "light_r": dict(style="jab", twist=34, lean=6, shift=0.08, step=0.05, chamber=(0.30, 0.20, 0.06),
                    chamber_fwd=(0.4, 0.5, 0.8), fing=(1.0, 0.9, 0.0)),
    "light_air": dict(style="jab", chamber=(0.10, 0.55, 0.04), chamber_fwd=(0, 1, 0.2), fing=(1.0, 0.9, 0.0)),
    "heavy": dict(style="rake", twist=0, lean=28, shift=0.30, step=0.18, chamber=(0.12, 0.62, 0.0),
                  chamber_fwd=(0.1, 1.0, -0.2), chamber_palm=(-1, 0, 0), fing=(1.0, 0.9, 0.0), arch=12, crouch=0.06),
}


def bruno_skills(C):
    fj = C.fj
    acts = fj["actions"]
    st = C.st
    out = {}
    rush = acts["bruno_rush"]
    hit = rush["hits"][0]
    cl = rush["clips"]
    tgt = AL_path(hit, hit["t0"])
    # charge pose: leaning, right shoulder leading, right arm tucked, left arm pumping
    def charge_body(t, T=cl["charge"][1]):
        g, _ = AC.gait(C, "run", (0, -1, 0), fj["move_speed"] * 1.6, T, 0.30)
        p = dict(g(t))
        p = add(p, hips_rot=(24, 0, 26), spine=(8, 0, 6), chest=(6, 0, 8), neck=(-18, 0, -14), head=(-14, 0, -12))
        p["hand_R"] = dict(frame="chest", pos=(0.10, 0.02, 0.22), fwd=(-0.3, 0.3, 1.0), palm=(-1, 0, 0), pole=(0.3, -0.8, 0.2))
        p["hand_L"] = dict(frame="chest", pos=(0.18, -0.08, 0.10 + 0.10 * math.sin(2 * math.pi * t / T)), fwd=(0, 0.5, 1), palm=(-1, 0, 0), pole=(0.4, -0.6, -0.4))
        p["fing_L"] = fist(C)
        p["fing_R"] = fist(C)
        p["ear_L"] = (-25, 0, -10)
        p["ear_R"] = (-25, 0, -10)
        p["tail"] = C.tail(t, amp=0.4, freq=4.0, lift=10)
        return place_point_by_hips(C, p, "shoulder", tgt, "Right")
    wind_T = cl["windup"][1]
    crouch = add(C.stance(crouch_add=0.08), hips_rot=(18, 0, 18), chest=(4, 0, 8))
    crouch = dict(crouch, hand_R=dict(frame="chest", pos=(0.10, 0.04, 0.20), fwd=(-0.3, 0.3, 1.0), palm=(-1, 0, 0), pole=(0.3, -0.8, 0.2)))
    end_w = charge_body(0.0)

    def windup(t):
        p = dict(keyed(t, [(0.0, C.stance()), (wind_T * 0.55, crouch, "out"), (wind_T, end_w, "in")]))
        return p
    out[cl["windup"][0]] = (windup, wind_T, dict(loop=False, hits=[("shoulder_r", hit, 0.0)]))
    out[cl["charge"][0]] = (charge_body, cl["charge"][1], dict(loop=True, hits=[("shoulder_r", hit, wind_T)]))
    base = C.stance()
    bump = add(end_w, hips=(0, 0.06, 0.02), hips_rot=(-10, 0, 0), head=(-8, 0, 0))
    out[cl["hit"][0]] = (lambda t, d=cl["hit"][1]: dict(keyed(t, [(0.0, end_w), (0.06, bump, "out"), (d, base)])), cl["hit"][1], dict(loop=False))
    stumble = add(end_w, hips=(0, -0.10, -0.05), hips_rot=(12, 4, 0))
    out[cl["miss"][0]] = (lambda t, d=cl["miss"][1]: dict(keyed(t, [(0.0, end_w), (0.15, stumble, "out"), (0.32, stumble), (d, base)])), cl["miss"][1], dict(loop=False))
    wall = add(end_w, hips=(0, 0.14, 0.0), hips_rot=(-18, 0, -6), head=(-20, 0, 0))
    wall = dict(wall, jaw=10, ear_L=(-30, 0, -10), ear_R=(-30, 0, -10))
    out[cl["wall"][0]] = (lambda t, d=cl["wall"][1]: dict(keyed(t, [(0.0, end_w), (0.05, wall, "out"), (0.22, wall), (d, base)])), cl["wall"][1], dict(loop=False))
    # Warning Bark
    bark = acts["bruno_bark"]
    D = bark["total_s"]
    trig = bark["params"]["trigger_s"]
    inhale = add(C.stance(), hips=(0, 0.03, 0.01), chest=(-10, 0, 0), uchest=(-6, 0, 0), neck=(-8, 0, 0), head=(-12, 0, 0))
    inhale = dict(inhale, ear_L=(12, 0, 6), ear_R=(12, 0, 6), jaw=-1.5,
                  hand_L=C.hand("L", "Left", pos=(0.22, 0.10, 0.10)), hand_R=C.hand("R", "Right", pos=(0.24, 0.06, 0.04)))
    barkp = add(C.stance(crouch_add=0.03), hips=(0, -0.05, 0), hips_rot=(10, 0, 0), chest=(12, 0, 0), neck=(10, 0, 0), head=(4, 0, 0))
    barkp = dict(barkp, jaw=34, ear_L=(-38, 0, -18), ear_R=(-38, 0, -18),
                 hand_L=C.hand("L", "Left", pos=(0.30, 0.00, 0.12), fwd=(0.3, 0.2, 1.0)),
                 hand_R=C.hand("R", "Right", pos=(0.30, -0.02, 0.06), fwd=(0.3, 0.2, 1.0)))
    bark2 = dict(add(barkp, head=(-4, 0, 0)), jaw=28)

    def fbark(t):
        p = dict(keyed(t, [(0.0, C.stance()), (trig * 0.8, inhale, "out"), (trig, barkp, "snap"), (trig + 0.18, bark2),
                           (trig + 0.30, add(barkp, head=(2, 0, 0))), (D, C.stance())]))
        p["tail"] = C.tail(t, amp=0.6, freq=3.0, lift=18)
        return p
    out[bark["clip"]] = (fbark, D, dict(loop=False))
    # Stand Firm
    sf = acts["bruno_stand_firm"]
    cl = sf["clips"]
    firm = C.stance(crouch_add=0.07)
    firm = dict(firm, foot_L=dict(ball=(0.26, -0.10), yaw=-10, heel=4), foot_R=dict(ball=(-0.26, 0.10), yaw=-25, heel=8),
                hand_L=dict(frame="chest", pos=(0.07, 0.36, 0.28), fwd=(-0.2, 1.0, 0.15), palm=(-0.2, 0.0, -1.0), pole=(0.20, -0.7, 0.3)),
                hand_R=dict(frame="chest", pos=(0.08, 0.33, 0.24), fwd=(-0.25, 1.0, 0.15), palm=(-0.2, 0.0, -1.0), pole=(0.20, -0.7, 0.3)),
                fing_L=fist(C), fing_R=fist(C), hips_rot=(10, 0, -4), head=(6, 0, 0), ear_L=(-10, 0, 0), ear_R=(-10, 0, 0))
    out[cl["enter"][0]] = (lambda t, d=cl["enter"][1]: dict(keyed(t, [(0.0, C.stance()), (d, firm, "out")])), cl["enter"][1], dict(loop=False))

    def fhold(t, d=cl["hold"][1]):
        u = 2 * math.pi * t / d
        p = add(firm, hips=(0, 0, -0.006 * (0.5 + 0.5 * math.sin(u))), chest=(1.0 * math.sin(u), 0, 0))
        p["tail"] = C.tail(t, amp=0.3, freq=1.0 / d)
        return p
    out[cl["hold"][0]] = (fhold, cl["hold"][1], dict(loop=True))
    out[cl["exit"][0]] = (lambda t, d=cl["exit"][1]: dict(keyed(t, [(0.0, firm), (d, C.stance())])), cl["exit"][1], dict(loop=False))
    hitf = add(firm, hips=(0, 0.03, 0), chest=(-5, 0, 0), head=(-6, 0, 0))
    out[cl["block"][0]] = (lambda t, d=cl["block"][1]: dict(keyed(t, [(0.0, firm), (0.04, hitf, "out"), (d, firm)])), cl["block"][1], dict(loop=False))
    return out


def AL_path(hit, t):
    from anim_lib import path_at
    return path_at(hit["path"], t)


# ============================================================================= Vex
VEX_ATTACKS = {
    "light_s": dict(style="jab", twist=18, lean=10, shift=0.14, step=0.10, chamber=(0.14, 0.12, 0.08), fing=(0.1, 0.1, 0.0)),
    "light_l": dict(style="swipe", twist=32, lean=6, shift=0.08, step=0.05, chamber=(0.40, 0.16, 0.0),
                    chamber_fwd=(0.6, 0.5, 0.4), fing=(0.1, 0.1, 0.0)),
    "light_r": dict(style="swipe", twist=32, lean=6, shift=0.08, step=0.05, chamber=(0.40, 0.16, 0.0),
                    chamber_fwd=(0.6, 0.5, 0.4), fing=(0.05, 0.1, 0.0)),
    "light_air": dict(style="jab", chamber=(0.12, 0.50, 0.04), chamber_fwd=(0, 1, 0.2), fing=(0.1, 0.1, 0.0)),
    "heavy": dict(style="jab", twist=26, lean=22, shift=0.36, step=0.26, chamber=(0.30, 0.10, -0.12),
                  chamber_fwd=(0.3, 0.2, 1.0), fing=(0.1, 0.1, 0.0), arch=6, crouch=0.06),
    "skill_e_strike": dict(style="jab", twist=22, lean=16, shift=0.20, step=0.10, chamber=(0.22, 0.14, 0.02), fing=(0.05, 0.1, 0.0)),
}


def vex_skills(C):
    fj = C.fj
    acts = fj["actions"]
    st = C.st
    out = {}
    base = C.stance()
    # False Start sidesteps (start from the heavy wind-up pose at 0.25 s)
    fs = acts["vex_false_start"]
    heavy_f, _ = attack(C, acts[fj["heavy"]], VEX_ATTACKS["heavy"])
    start = heavy_f(fs["params"]["feint_s"])
    for key, dvec in (("step_l", (1, 0)), ("step_r", (-1, 0)), ("step_b", (0, 1))):
        name, d = fs["clips"][key]
        lean = add(C.stance(crouch_add=0.05), hips=(dvec[0] * 0.10, dvec[1] * 0.10, 0), hips_rot=(-4 * dvec[1], -12 * dvec[0], 0))
        lean = dict(lean)
        lead = "L" if dvec[0] > 0 else "R"
        if dvec[1] == 0:
            lean["foot_" + lead] = dict(ball=(dvec[0] * 0.32, -0.06), heel=6, yaw=dvec[0] * 8)
        else:
            lean["foot_R"] = dict(ball=(-0.15, 0.30), heel=30, yaw=-20)

        def fstep(t, lean=lean, d=d, dv=dvec):
            p = dict(keyed(t, [(0.0, start), (0.10, lean, "out"), (0.22, lean), (d, C.stance())]))
            p["tail"] = C.tail(t, amp=0.4, freq=2.0, side=-dv[0] * 28)
            return p
        out[name] = (fstep, d, dict(loop=False))
    # Sidewinder
    sw = acts["vex_sidewinder"]
    cl = sw["clips"]
    hit = sw["hits"][0]
    wind = add(C.stance(crouch_add=0.08), hips_rot=(14, 0, 0))
    out[cl["windup"][0]] = (lambda t, d=cl["windup"][1]: dict(keyed(t, [(0.0, base), (d, wind, "out")])), cl["windup"][1], dict(loop=False))
    for key, sgn in (("dash_l", 1), ("dash_r", -1)):
        name, d = cl[key]
        g, _ = AC.gait(C, "run", (0, -1, 0), 10.0 * 0.8, d / 1.0, 0.20)

        def fdash(t, g=g, sgn=sgn, d=d):
            p = dict(g(t))
            p = add(p, hips=(0, 0, -0.05), hips_rot=(18, sgn * 14, sgn * 22), chest=(0, sgn * 6, -sgn * 10), head=(-12, -sgn * 8, -sgn * 12))
            p["hand_L"] = C.hand("L", "Left", pos=(0.14, 0.02, 0.26))
            p["hand_R"] = C.hand("R", "Right", pos=(0.16, 0.00, 0.14))
            p["tail"] = C.tail(t, amp=0.3, freq=2.0, lift=8, side=-sgn * 35)
            return p
        out[name] = (fdash, d, dict(loop=False))
    name, d = cl["strike"]
    f, _ = attack(C, sw, VEX_ATTACKS["skill_e_strike"], clip_len=d, windows=[(hit, hit["t0"], hit["t1"], 0.0)],
                  base_fn=lambda t: add(C.stance(crouch_add=0.05), hips_rot=(12, 0, 0)))
    out[name] = (f, d, dict(loop=False, hits=[("hand_r", hit, 0.0)]))
    name, d = cl["recover"]
    out[name] = (lambda t, d=d: dict(keyed(t, [(0.0, f(cl["strike"][1])), (d, base)])), d, dict(loop=False))
    # Tail Sweep: 360 deg spin, tail extended horizontally at the JSON circle
    ts = acts["vex_tail_sweep"]
    th = ts["hits"][0]
    D = ts["total_s"]
    t0, t1 = th["t0"], th["t1"]
    low = C.stance(crouch_add=0.22)
    low = dict(low, hips_rot=(24, 0, 0), foot_L=dict(ball=(0.20, -0.10), heel=6), foot_R=dict(ball=(-0.20, 0.08), heel=16),
               hand_L=dict(frame="obj", pos=(0.30, -0.25, 0.20), fwd=(0.3, -0.6, -0.7), palm=(0, 0, -1), pole=(0.6, 0.4, 0.3)),
               hand_R=dict(frame="obj", pos=(-0.30, -0.20, 0.30), fwd=(-0.3, -0.6, -0.5), palm=(0, 0, -1), pole=(-0.6, 0.4, 0.3)))
    flat_tail = [(-14, 0, 0)] + [(-4, 0, 0)] * (C.tail_n - 1)

    def spin_pose(t):
        tip = AL_path(th, t)
        ang = math.degrees(math.atan2(-tip.x, tip.y))         # yaw that points the (rest +Y) tail at the tip
        # body faces away from the tail: tail rest points +Y (angle 0)
        p = dict(low)
        p["tail"] = flat_tail
        p = add(p, hips_rot=(0, 0, ang))
        R = Matrix.Rotation(math.radians(ang), 3, "Z")
        for tag, fx, fy in (("L", 0.20, -0.10), ("R", -0.20, 0.08)):
            v = R @ Vector((fx, fy, 0.0))
            p["foot_" + tag] = dict(ball=(v.x, v.y), heel=10, yaw=ang)
        for tag, hx, hy, hz in (("L", 0.30, -0.25, 0.20), ("R", -0.30, -0.20, 0.30)):
            v = R @ Vector((hx, hy, hz))
            hand = dict(p["hand_" + tag])
            hand["pos"] = (v.x, v.y, v.z)
            hand["fwd"] = tuple(R @ Vector(hand["fwd"]))
            hand["pole"] = tuple(R @ Vector(hand["pole"]))
            p["hand_" + tag] = hand
        return place_point_by_hips(C, p, "tail", tip, iters=3)

    def fsweep(t):
        if t0 <= t <= t1:
            p = spin_pose(t)
        elif t < t0:
            prep = add(low, hips_rot=(0, 0, 30 * smooth01(0.0, t0, t)))      # wind up against the spin
            prep = dict(prep)
            prep["tail"] = C.tail(t, amp=0.3, freq=2.0, lift=20 * smooth01(0, t0, t))
            p = lerp_pose(dict(lerp_pose(base, prep, ease(t / (t0 * 0.7)))) if t < t0 * 0.7 else prep, spin_pose(t0),
                          ease(max(0.0, (t - t0 * 0.7) / (t0 * 0.3)), "in"))
        else:
            p = lerp_pose(spin_pose(t1), base, ease((t - t1) / (D - t1)))
        return dict(p)
    out[ts["clip"]] = (fsweep, D, dict(loop=False))
    return out


# ============================================================================= Hops
HOPS_ATTACKS = {
    "light_s": dict(style="kick", twist=10, lean=-12, shift=0.0, chamber_foot=dict(ball=(-0.10, -0.25), lift=0.40, pitch=-40, heel=0),
                    fing=(1.0, 0.9, 0.0)),
    "light_l": dict(style="kick", twist=24, lean=-8, shift=0.0, chamber_foot=dict(ball=(0.35, -0.10), lift=0.45, pitch=-30, heel=0, yaw=40),
                    fing=(1.0, 0.9, 0.0)),
    "light_r": dict(style="kick", twist=24, lean=-8, shift=0.0, chamber_foot=dict(ball=(-0.35, -0.10), lift=0.45, pitch=-30, heel=0, yaw=-40),
                    fing=(1.0, 0.9, 0.0)),
    "light_air": dict(style="kick", air=True, chamber_foot=dict(ball=(-0.10, -0.20), lift=0.45, pitch=-50, heel=0), fing=(1.0, 0.9, 0.0)),
    "heavy": dict(style="kick", twist=40, lean=-18, shift=0.0, chamber_foot=dict(ball=(-0.15, 0.10), lift=0.50, pitch=-40, heel=0),
                  fing=(1.0, 0.9, 0.0), arch=4),
    "skill_e": dict(style="kick", twist=16, lean=-14, shift=0.0, chamber_foot=dict(ball=(-0.10, -0.25), lift=0.42, pitch=-40, heel=0),
                    fing=(1.0, 0.9, 0.0)),
}


def hops_skills(C):
    fj = C.fj
    acts = fj["actions"]
    out = {}
    base = C.stance()
    b = acts["hops_bound"]
    cl = b["clips"]
    crouch = dict(C.stance(crouch_add=0.16), hips_rot=(26, 0, 0), foot_L=dict(ball=(0.13, -0.05), heel=8), foot_R=dict(ball=(-0.13, 0.05), heel=12),
                  hand_L=C.hand("L", "Left", pos=(0.20, -0.10, 0.10)), hand_R=C.hand("R", "Right", pos=(0.20, -0.12, 0.04)),
                  ear_L=(-10, 0, 0), ear_R=(-10, 0, 0))
    out[cl["crouch"][0]] = (lambda t, d=cl["crouch"][1]: dict(keyed(t, [(0.0, base), (d, crouch, "out")])), cl["crouch"][1], dict(loop=False))
    fly = dict(C.stance(), hips=V(0, 0.0, 0.02), hips_rot=(20, 0, 0), chest=(-4, 0, 0),
               foot_L=dict(ball=(0.13, -0.28), lift=0.40, pitch=-15, heel=0), foot_R=dict(ball=(-0.13, 0.40), lift=0.30, pitch=-60, heel=0),
               hand_L=dict(frame="chest", pos=(0.24, 0.12, 0.26), fwd=(0.2, 0.4, 1), palm=(-1, 0, 0), pole=(0.6, -0.4, -0.3)),
               hand_R=dict(frame="chest", pos=(0.26, 0.00, -0.10), fwd=(0.2, -0.3, -1), palm=(-1, 0, 0), pole=(0.6, -0.4, 0.3)),
               ear_L=(-35, 0, -5), ear_R=(-35, 0, -5))

    def fair(t, d=cl["air"][1]):
        p = dict(keyed(t, [(0.0, crouch), (0.10, fly, "out"), (d * 0.7, fly), (d, add(fly, hips=(0, 0, 0.0)))]))
        p["tail"] = C.tail(t, amp=0.2, freq=2.0)
        return p
    out[cl["air"][0]] = (fair, cl["air"][1], dict(loop=False))
    land = dict(crouch, hips=V(0, 0.0, -0.20))
    out[cl["land"][0]] = (lambda t, d=cl["land"][1]: dict(keyed(t, [(0.0, fly), (0.06, land, "out"), (d, base)])), cl["land"][1], dict(loop=False))
    de = acts["hops_double_kick"]
    C.kick_shift = 0.60
    f, _ = attack(C, de, HOPS_ATTACKS["skill_e"])
    out[de["clip"]] = (f, de["total_s"], dict(loop=False))
    # Dropkick
    dk = acts["hops_dropkick"]
    cl = dk["clips"]
    hit = dk["hits"][0]
    hop = dict(C.stance(crouch_add=0.12), hips_rot=(16, 0, 0), ear_L=(-20, 0, 0), ear_R=(-20, 0, 0))

    def flight(t, off=cl["hop"][1]):
        tip = AL_path(hit, t + off)
        p = dict(C.stance(), hips=V(0, 0.30, 0.0), hips_rot=(-62, 0, 0), spine=(8, 0, 0), chest=(10, 0, 0), neck=(24, 0, 0), head=(26, 0, 0),
                 hand_L=dict(frame="obj", pos=(0.30, 0.45, 0.80), fwd=(0.4, 0.3, -0.8), palm=(0, 1, 0), pole=(0.5, 0.3, 0.8)),
                 hand_R=dict(frame="obj", pos=(-0.30, 0.45, 0.80), fwd=(-0.4, 0.3, -0.8), palm=(0, 1, 0), pole=(-0.5, 0.3, 0.8)),
                 ear_L=(-40, 0, 0), ear_R=(-40, 0, 0))
        p["foot_R"] = dict(ball=(tip.x, tip.y), tip=tip, pitch=-80, toe=10, pole=(0, -0.3, 1.0))
        tl = tip + Vector((0.14, 0.02, 0.0))
        p["foot_L"] = dict(ball=(tl.x, tl.y), tip=tl, pitch=-80, toe=10, pole=(0, -0.3, 1.0))
        res = C.resolve(p)
        p = C.reach_leg(p, "Right", res["ankle_des_Right"], max_shift=0.5)
        return p
    out[cl["hop"][0]] = (lambda t, d=cl["hop"][1]: dict(keyed(t, [(0.0, base), (d * 0.5, hop, "out"), (d, flight(0.0), "in")])),
                         cl["hop"][1], dict(loop=False, hits=[("foot_r", hit, 0.0)]))
    out[cl["flight"][0]] = (flight, cl["flight"][1], dict(loop=False, hits=[("foot_r", hit, cl["hop"][1])]))
    landp = dict(C.stance(crouch_add=0.14), hips_rot=(18, 0, 0))
    out[cl["land"][0]] = (lambda t, d=cl["land"][1]: dict(keyed(t, [(0.0, flight(cl["flight"][1])), (0.10, landp, "out"), (d, base)])),
                          cl["land"][1], dict(loop=False))
    from anim_clips import lying_pose
    lie = lying_pose(C)
    out[cl["crash"][0]] = (lambda t, d=cl["crash"][1]: dict(keyed(t, [(0.0, flight(cl["flight"][1])), (0.18, lie, "in"), (0.45, lie), (d, base)])),
                           cl["crash"][1], dict(loop=False))
    return out


# ============================================================================= Scrap
SCRAP_ATTACKS = {
    "light_s": dict(style="jab", twist=18, lean=12, shift=0.14, step=0.08, chamber=(0.12, 0.10, 0.10), fing=(0.6, 0.4, 0.2)),
    "light_l": dict(style="swipe", twist=30, lean=8, shift=0.08, step=0.05, chamber=(0.38, 0.12, 0.02),
                    chamber_fwd=(0.6, 0.5, 0.4), fing=(0.5, 0.3, 0.4)),
    "light_r": dict(style="jab", twist=34, lean=8, shift=0.08, step=0.05, chamber=(0.36, 0.12, 0.02),
                    chamber_fwd=(0.5, 0.5, 0.6), fing=(1.0, 0.9, 0.0)),
    "light_air": dict(style="swipe", chamber=(0.14, 0.50, 0.04), chamber_fwd=(0, 1, 0.2), fing=(0.5, 0.3, 0.4)),
    "heavy": dict(style="rake", twist=0, lean=10, shift=0.20, step=0.12, chamber=(0.14, -0.20, 0.16),
                  chamber_fwd=(0.0, -0.3, 1.0), chamber_palm=(0, 1, 0), fing=(0.6, 0.4, 0.3), arch=-6, crouch=0.10),
}


def scrap_skills(C):
    fj = C.fj
    acts = fj["actions"]
    out = {}
    base = C.stance()
    ct = acts["scrap_catch_turn"]
    cl = ct["clips"]
    parry = dict(C.stance(crouch_add=0.03), hips=V(0, 0.05, -C.st["crouch"] - 0.03), hips_rot=(4, 0, -10),
                 hand_L=dict(frame="chest", pos=(0.12, 0.16, 0.36), fwd=(-0.1, 0.5, 1.0), palm=(-0.2, 0, 1.0), pole=(0.5, -0.6, 0)),
                 hand_R=dict(frame="chest", pos=(0.10, 0.10, 0.30), fwd=(-0.1, 0.5, 1.0), palm=(-0.2, 0, 1.0), pole=(0.5, -0.6, 0)),
                 fing_L=(0.15, 0.2, 0.4), fing_R=(0.15, 0.2, 0.4), ear_L=(8, 0, 0), ear_R=(8, 0, 0))
    out[cl["stance"][0]] = (lambda t, d=cl["stance"][1]: dict(keyed(t, [(0.0, base), (0.05, parry, "snap"), (d, parry)])), cl["stance"][1], dict(loop=False))
    turn = dict(add(parry, hips_rot=(0, 0, 70), chest=(0, 0, 10)),
                hand_L=dict(frame="chest", pos=(0.30, 0.10, 0.30), fwd=(0.8, 0.2, 0.6), palm=(0, 0, 1), pole=(0.5, -0.6, 0)),
                hand_R=dict(frame="chest", pos=(0.10, 0.12, 0.34), fwd=(0.6, 0.3, 0.8), palm=(0, 0, 1), pole=(0.5, -0.6, 0)),
                fing_L=(0.9, 0.7, 0.0), fing_R=(0.9, 0.7, 0.0))
    out[cl["success"][0]] = (lambda t, d=cl["success"][1]: dict(keyed(t, [(0.0, parry), (0.12, turn, "out"), (0.22, turn), (d, base)])), cl["success"][1], dict(loop=False))
    whiff = dict(add(parry, hips=(0, -0.08, -0.03), hips_rot=(14, 0, 4), head=(8, 0, 0)), jaw=6)
    out[cl["whiff"][0]] = (lambda t, d=cl["whiff"][1]: dict(keyed(t, [(0.0, parry), (0.12, whiff, "out"), (0.28, whiff), (d, base)])), cl["whiff"][1], dict(loop=False))
    # Leg sweep: crouched pivot, right foot tip follows the low arc
    ls = acts["scrap_leg_sweep"]
    h = ls["hits"][0]
    D = ls["total_s"]
    low = dict(C.stance(crouch_add=0.30), hips_rot=(30, 0, 0),
               hand_L=dict(frame="obj", pos=(0.18, -0.30, 0.06), fwd=(0.2, -0.6, -0.8), palm=(0, 0, -1), pole=(0.6, 0.4, 0.2)),
               hand_R=dict(frame="obj", pos=(-0.12, -0.34, 0.06), fwd=(-0.2, -0.6, -0.8), palm=(0, 0, -1), pole=(-0.6, 0.4, 0.2)),
               foot_L=dict(ball=(0.16, -0.02), heel=16))
    C.kick_shift = 0.40
    C.kick_pitch = -20.0

    def sweep_pose(t):
        tip = AL_path(h, t)
        ang = math.degrees(math.atan2(tip.x, -tip.y))       # yaw facing the tip: 0 ahead, + = character's left
        p = add(low, hips_rot=(0, 0, ang * 0.55))
        p = dict(p)
        p["foot_R"] = dict(ball=(tip.x, tip.y), tip=tip, pitch=-10, toe=0, yaw=ang, pole=(0, -0.2, 1.0))
        res = C.resolve(p)
        p = C.reach_leg(p, "Right", res["ankle_des_Right"], max_shift=0.40)
        return p

    def fsweep(t):
        t0, t1 = h["t0"], h["t1"]
        if t0 <= t <= t1:
            return sweep_pose(t)
        if t < t0:
            return dict(lerp_pose(base if t < 0.08 else low, sweep_pose(t0), ease(max(0, (t - 0.08) / (t0 - 0.08)), "in")) if t >= 0.08 else lerp_pose(base, low, ease(t / 0.08)))
        return dict(lerp_pose(sweep_pose(t1), base, ease((t - t1) / (D - t1))))
    out[ls["clip"]] = (fsweep, D, dict(loop=False))
    # Turnabout
    tb = acts["scrap_turnabout"]
    cl = tb["clips"]
    hit = tb["hits"][0]
    f_reach, _ = attack(C, tb, dict(style="rake", twist=0, lean=18, shift=0.16, step=0.12, chamber=(0.18, 0.06, 0.12),
                                    chamber_fwd=(0, 0.3, 1.0), fing=(0.3, 0.3, 0.4)),
                        clip_len=cl["reach"][1], windows=[(hit, hit["t0"], hit["t1"], 0.0)])
    out[cl["reach"][0]] = (f_reach, cl["reach"][1], dict(loop=False, hits=[("both_hands", hit, 0.0)]))
    hold = dict(C.stance(crouch_add=0.06), hips_rot=(12, 0, 0),
                hand_L=dict(frame="chest", pos=(0.12, 0.05, 0.40), fwd=(-0.2, 0.2, 1.0), palm=(-1, 0, 0), pole=(0.5, -0.6, 0)),
                hand_R=dict(frame="chest", pos=(0.12, 0.02, 0.38), fwd=(-0.2, 0.2, 1.0), palm=(-1, 0, 0), pole=(0.5, -0.6, 0)),
                fing_L=(0.9, 0.7, 0.0), fing_R=(0.9, 0.7, 0.0))
    endr = f_reach(cl["reach"][1])

    def fgrap(t, d=cl["grapple"][1]):
        u = ease(t / d)
        p = dict(lerp_pose(endr, hold, ease(min(t / 0.08, 1.0)))) if t < 0.08 else dict(hold)
        p = add(p, hips_rot=(0, 0, 120 * u - 40 * math.sin(math.pi * u)))
        p["tail"] = C.tail(t, amp=0.4, freq=2.0, side=-30 * math.sin(math.pi * u))
        return p
    out[cl["grapple"][0]] = (fgrap, cl["grapple"][1], dict(loop=False))
    push = dict(add(hold, hips=(0, -0.06, 0), hips_rot=(0, 0, 120)),
                hand_L=dict(frame="chest", pos=(0.12, 0.08, 0.48), fwd=(0, 0.6, 1.0), palm=(0, 0, 1), pole=(0.5, -0.6, 0)),
                hand_R=dict(frame="chest", pos=(0.12, 0.05, 0.46), fwd=(0, 0.6, 1.0), palm=(0, 0, 1), pole=(0.5, -0.6, 0)),
                fing_L=(0.1, 0.1, 0.4), fing_R=(0.1, 0.1, 0.4))
    out[cl["release"][0]] = (lambda t, d=cl["release"][1]: dict(keyed(t, [(0.0, fgrap(cl["grapple"][1])), (0.10, push, "out"), (d, base)])),
                             cl["release"][1], dict(loop=False))
    miss = dict(add(endr, hips=(0, -0.08, -0.04), hips_rot=(10, 0, 0)))
    out[cl["whiff"][0]] = (lambda t, d=cl["whiff"][1]: dict(keyed(t, [(0.0, endr), (0.14, miss, "out"), (0.30, miss), (d, base)])),
                           cl["whiff"][1], dict(loop=False))
    return out


ATTACKS.update({"bruno": BRUNO_ATTACKS, "vex": VEX_ATTACKS, "hops": HOPS_ATTACKS, "scrap": SCRAP_ATTACKS})
SKILLS.update({"bruno": bruno_skills, "vex": vex_skills, "hops": hops_skills, "scrap": scrap_skills})
