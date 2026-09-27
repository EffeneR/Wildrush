"""Ground-level art from the layout JSON: walkable floor tops (flush, exact heights), exposed
floor sides / retaining walls, canal walls + copings, balustrades along canal-edge blockers,
stairs (nosings on the ramp line), the metal ramp, arched bridges, water surfaces, canal beds,
puddles and flush floor decals.

Everything is written into an Out registry (per chunk + category MeshBuilders); special-named
meshes (water_*, puddle_*) become their own objects.
"""
from __future__ import annotations

import math

import common as C
from bl_core import MB, M_apply, M_chain, M_translate, M_yaw, M_scale, v_add, v_mul, v_sub
from common import Rect

FLOOR_EPS = 0.0          # floor tops are exact
DECAL_Y = 0.004          # flush decals above floor
PUDDLE_Y = 0.005         # contract: puddles at y + 0.005
CANAL_BOTTOM = -3.0
LIP_FLOOR = 0.30         # canal wall protrudes into the water under balustrades
LIP_BUILDING = 0.12


def floor_material(f):
    s, d = f["surface"], f["district"]
    if s == "wood":
        return "wood_planks"
    if s == "metal":
        return "metal_deck"
    return {"spawn": "paving_flag", "north_row": "paving_cobble", "A": "paving_flag", "quay": "paving_flag",
            "B": "paving_flag", "lane": "paving_cobble", "C": "paving_concrete", "alley": "paving_cobble"}.get(d, "paving_flag")


def side_frame(r: Rect, side: str):
    """(start point (x,z), unit tangent (tx,tz), outward normal (nx,nz), length) for a rect side,
    tangent running left->right as seen from outside."""
    if side == "s":
        return (r.x0, r.z1), (1.0, 0.0), (0.0, 1.0), r.w
    if side == "n":
        return (r.x1, r.z0), (-1.0, 0.0), (0.0, -1.0), r.w
    if side == "e":
        return (r.x1, r.z1), (0.0, -1.0), (1.0, 0.0), r.d
    return (r.x0, r.z0), (0.0, 1.0), (-1.0, 0.0), r.d


def runs(samples, key):
    """Group consecutive samples [(s, value)] by key(value) -> [(s0, s1, value0)]."""
    out = []
    cur = None
    for s, v in samples:
        k = key(v)
        if cur is None or cur[2] != k:
            if cur is not None:
                out.append(cur)
            cur = [s, s, k, v]
        else:
            cur[1] = s
    if cur is not None:
        out.append(cur)
    return [(a, b, k, v) for a, b, k, v in out]


class Out:
    def __init__(self):
        self.mbs = {}
        self.specials = []   # (chunk, name, MB, props)

    def mb(self, chunk, key):
        k = (chunk, key)
        if k not in self.mbs:
            self.mbs[k] = MB()
        return self.mbs[k]

    def special(self, chunk, name, mb, props=None):
        self.specials.append((chunk, name, mb, props or {}))


# =============================================================================== floors
def partition_rect(rect: Rect, base_mat, bands):
    """bands: list of (Rect, mat) in increasing priority. Returns list of (Rect, mat) covering rect."""
    xs = {rect.x0, rect.x1}
    zs = {rect.z0, rect.z1}
    clipped = []
    for b, m in bands:
        x0, x1 = max(rect.x0, b.x0), min(rect.x1, b.x1)
        z0, z1 = max(rect.z0, b.z0), min(rect.z1, b.z1)
        if x1 - x0 < 1e-4 or z1 - z0 < 1e-4:
            continue
        clipped.append((Rect(x0, x1, z0, z1), m))
        xs.update((x0, x1))
        zs.update((z0, z1))
    xs, zs = sorted(xs), sorted(zs)
    grid = {}
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            cx, cz = 0.5 * (xs[i] + xs[i + 1]), 0.5 * (zs[j] + zs[j + 1])
            m = base_mat
            for b, bm in clipped:
                if b.contains(cx, cz):
                    m = bm
            grid[(i, j)] = m
    # merge along x per row, then identical spans along z
    strips = []
    for j in range(len(zs) - 1):
        i = 0
        while i < len(xs) - 1:
            m = grid[(i, j)]
            k = i
            while k + 1 < len(xs) - 1 and grid[(k + 1, j)] == m:
                k += 1
            strips.append([xs[i], xs[k + 1], zs[j], zs[j + 1], m])
            i = k + 1
    merged = []
    for s in strips:
        for t in merged:
            if abs(t[0] - s[0]) < 1e-6 and abs(t[1] - s[1]) < 1e-6 and abs(t[3] - s[2]) < 1e-6 and t[4] == s[4]:
                t[3] = s[3]
                break
        else:
            merged.append(list(s))
    return [(Rect(a, b, c, d), m) for a, b, c, d, m in merged]


class Ground:
    def __init__(self, lay: C.Layout, out: Out):
        self.L = lay
        self.out = out

    # ------------------------------------------------------------------ helpers
    def neighbour(self, x, z):
        return self.L.classify(x, z)

    def side_samples(self, r: Rect, side, off=0.06, step=0.25):
        (sx, sz), (tx, tz), (nx, nz), ln = side_frame(r, side)
        n = max(1, int(round(ln / step)))
        res = []
        for i in range(n):
            s = (i + 0.5) * ln / n
            x = sx + tx * s + nx * off
            z = sz + tz * s + nz * off
            res.append((s, (x, z)))
        return res, ln

    # ------------------------------------------------------------------ floor tops
    def floors(self):
        L = self.L
        for f in L.floors:
            if f["is_bed"]:
                continue
            r = f["rect"]
            top = f["top"]
            ch = C.chunk_of(r.cx, r.cz)
            base = floor_material(f)
            bands = []
            bridge = f["surface"] == "wood"
            if not bridge:
                bands += self.edge_bands(f, base)
            bands += self.pattern_bands(f)
            mb = self.out.mb(ch, "floor")
            for rr, m in partition_rect(r, base, bands):
                rot = False
                if bridge:
                    # planks across the walking direction (span axis = longer extent of the water crossing)
                    rot = self.bridge_axis(f) == "x"
                mb.quad((rr.x0, top, rr.z1), (rr.x1, top, rr.z1), (rr.x1, top, rr.z0), (rr.x0, top, rr.z0), m,
                        uv_rot=rot)
            if not bridge:
                self.floor_sides(f)

    def bridge_axis(self, f):
        w = self.L.water_at(f["rect"].cx, f["rect"].cz)
        if w is None:
            return "z"
        wr = w["rect"]
        # span direction: across the canal (the canal's narrow axis)
        return "x" if wr.w < wr.d else "z"

    def edge_bands(self, f, base):
        r = f["rect"]
        top = f["top"]
        bands = []
        for side in ("n", "s", "e", "w"):
            samples, ln = self.side_samples(r, side)
            cls = []
            for s, (x, z) in samples:
                c = self.neighbour(x, z)
                if c[0] == "floor" and c[1] < top - 0.05:
                    k = "lower"
                elif c[0] == "floor":
                    k = "floor"
                else:
                    k = c[0]
                cls.append((s, k))
            for s0, s1, k, _ in runs(cls, lambda v: v):
                if k in ("floor", "void"):
                    continue
                s0 -= ln / len(samples) / 2
                s1 += ln / len(samples) / 2
                if k == "building":
                    if base == "paving_cobble":
                        wdt, m = min(1.2, 0.2 * min(r.w, r.d)), "paving_flag"
                    else:
                        wdt, m = 0.32, "paving_cobble"
                elif k == "water":
                    wdt, m = 0.45, "stone_trim"
                elif k == "lower":
                    wdt, m = (0.25, "hazard") if f["surface"] == "metal" else (0.35, "stone_trim")
                else:
                    continue
                bands.append((self.band_rect(r, side, s0, s1, wdt), m))
        return bands

    @staticmethod
    def band_rect(r, side, s0, s1, w):
        (sx, sz), (tx, tz), (nx, nz), ln = side_frame(r, side)
        s0, s1 = max(0.0, s0), min(ln, s1)
        xa, za = sx + tx * s0, sz + tz * s0
        xb, zb = sx + tx * s1, sz + tz * s1
        xc, zc = xb - nx * w, zb - nz * w
        return Rect(min(xa, xb, xc), max(xa, xb, xc), min(za, zb, zc), max(za, zb, zc))

    def pattern_bands(self, f):
        """Designed paving patterns (never rings at the 9 m scoring radius)."""
        out = []
        fid = f["id"]
        if fid == "plaza_b":
            for a in (-13.0, 13.0):
                out.append((Rect(a - 0.2, a + 0.2, -13.2, 13.2), "stone_trim"))
                out.append((Rect(-13.2, 13.2, a - 0.2, a + 0.2), "stone_trim"))
            for a in (-19.0, 19.0):
                out.append((Rect(a - 0.2, a + 0.2, -19.5, 19.5), "stone_trim"))
            out.append((Rect(-0.2, 0.2, -20.0, -13.2), "stone_trim"))
            out.append((Rect(-0.2, 0.2, 13.2, 20.0), "stone_trim"))
        elif fid == "deck_a":
            for z in (-12.5, 12.5):
                out.append((Rect(-50.5, -34.5, z - 0.2, z + 0.2), "stone_trim"))
            for x in (-50.5, -34.5):
                out.append((Rect(x - 0.2, x + 0.2, -12.5, 12.5), "stone_trim"))
            out.append((Rect(-50.3, -34.7, -0.2, 0.2), "stone_trim"))
        elif fid == "spawn_plaza" or fid == "spawn_plaza_s":
            zc = -49.0 if fid == "spawn_plaza" else 49.0
            out.append((Rect(-10.0, 10.0, zc - 0.2, zc + 0.2), "stone_trim"))
            out.append((Rect(-0.2, 0.2, min(zc, zc * 0.86), max(zc, zc * 0.86)), "stone_trim"))
        elif fid in ("north_row", "north_row_s"):
            # central drainage channel of setts running along the street
            zc = -37.0 if fid == "north_row" else 37.0
            out.append((Rect(-60.0, 60.0, zc - 0.25, zc + 0.25), "paving_flag"))
        return out

    # ------------------------------------------------------------------ floor sides
    def floor_sides(self, f):
        r = f["rect"]
        top, bottom = f["top"], f["bottom"]
        ch = C.chunk_of(r.cx, r.cz)
        side_mat = "concrete" if f["surface"] == "metal" else "stone_ashlar"
        for side in ("n", "s", "e", "w"):
            samples, ln = self.side_samples(r, side)
            vals = []
            for s, (x, z) in samples:
                c = self.neighbour(x, z)
                if c[0] == "floor":
                    lvl = c[1]
                    vals.append((s, round(lvl, 3) if lvl < top - 0.02 else None))
                elif c[0] == "void":
                    vals.append((s, round(bottom, 3)))
                else:
                    vals.append((s, None))
            (sx, sz), (tx, tz), (nx, nz), _ = side_frame(r, side)
            ds = ln / len(samples)
            # ramps give varying levels -> emit per-sample strips, merged when constant
            for s0, s1, k, lvl in runs(vals, lambda v: v):
                if lvl is None:
                    continue
                a, b = s0 - ds / 2, s1 + ds / 2
                pa = (sx + tx * a, sz + tz * a)
                pb = (sx + tx * b, sz + tz * b)
                mb = self.out.mb(ch, "floor_side")
                mb.quad((pa[0], lvl, pa[1]), (pb[0], lvl, pb[1]), (pb[0], top, pb[1]), (pa[0], top, pa[1]), side_mat)
                if f["surface"] == "metal":
                    # steel edge angle + rubber dock bumpers along loading-dock faces
                    self.dock_edge(mb, pa, pb, (nx, nz), lvl, top)

    def dock_edge(self, mb, pa, pb, n, y0, y1):
        (ax, az), (bx, bz) = pa, pb
        nx, nz = n
        L = math.hypot(bx - ax, bz - az)
        t = ((bx - ax) / L, 0.0, (bz - az) / L)
        nv = (nx, 0.0, nz)
        O = (ax, 0.0, az)
        # steel angle on the top edge (flush on top, 0.02 proud of the face)
        mb.fbox(O, t, nv, 0.0, L, y1 - 0.12, y1, 0.0, 0.02, "iron", skip=("back", "top"))
        k = int(L // 2.5)
        for i in range(k):
            sc = (i + 0.5) * L / k
            # rubber bumper 0.25 wide, 0.12 proud, 0.35 tall (within +-0.15 of the face)
            mb.fbox(O, t, nv, sc - 0.125, sc + 0.125, y1 - 0.55, y1 - 0.2, 0.0, 0.12, "iron", skip=("back",))

    # ------------------------------------------------------------------ canal walls
    def land_level(self, x, z):
        c = self.L.classify(x, z)
        if c[0] == "floor":
            return ("floor", c[1])
        if c[0] == "building":
            return ("building", 0.0)
        if c[0] == "water":
            return ("water", None)
        return ("void", 0.0)

    def canal_walls(self):
        L = self.L
        for w in L.water:
            r = w["rect"]
            for side in ("n", "s", "e", "w"):
                samples, ln = self.side_samples(r, side, off=0.06, step=0.2)
                vals = [(s, self.land_level(x, z)) for s, (x, z) in samples]
                (sx, sz), (tx, tz), (nx, nz), _ = side_frame(r, side)
                ds = ln / len(samples)
                for s0, s1, k, v in runs(vals, lambda v: v[0]):
                    if k == "water":
                        continue
                    lip = LIP_FLOOR if k == "floor" else LIP_BUILDING
                    a, b = s0 - ds / 2 - lip, s1 + ds / 2 + lip
                    seg = [(s, lv) for s, lv in vals if s0 - 1e-6 <= s <= s1 + 1e-6]
                    # level profile (floor tops incl. ramps); buildings -> 0
                    prof = []
                    for s, lv in seg:
                        prof.append((s, lv[1] if lv[1] is not None else 0.0))
                    prof = [(a, prof[0][1])] + prof + [(b, prof[-1][1])]
                    prof = simplify_profile(prof)
                    self.canal_wall_strip(r, side, prof, lip, k)

    def canal_wall_strip(self, r, side, prof, lip, kind):
        (sx, sz), (tx, tz), (nx, nz), _ = side_frame(r, side)
        # wall face is inside the water rect: water side normal = -outward
        wx, wz = -nx, -nz

        def P(s, y, d):
            # d: distance from the rect edge into the water (positive = into water)
            return (sx + tx * s + wx * d, y, sz + tz * s + wz * d)
        cx = sx + tx * prof[len(prof) // 2][0]
        cz = sz + tz * prof[len(prof) // 2][0]
        ch = C.chunk_of(cx, cz)
        mb = self.out.mb(ch, "canal_wall")
        cap = 0.2
        for (s0, y0), (s1, y1) in zip(prof[:-1], prof[1:]):
            # face as seen from the water: tangent must run left->right for a viewer in the water
            top0, top1 = y0 - cap, y1 - cap
            lo = CANAL_BOTTOM
            mid0, mid1 = min(0.0, top0), min(0.0, top1)
            # stone_canal below y=0, ashlar above (terrace sections)
            mb.quad(P(s1, lo, lip), P(s0, lo, lip), P(s0, mid0, lip), P(s1, mid1, lip), "stone_canal")
            if top0 > 0.0 or top1 > 0.0:
                mb.quad(P(s1, mid1, lip), P(s0, mid0, lip), P(s0, max(top0, 0.0), lip), P(s1, max(top1, 0.0), lip), "stone_ashlar")
            # coping: top face from the wall face (+0.06 overhang) back to the land edge
            o = lip + 0.06
            mb.quad(P(s0, y0, 0.0), P(s1, y1, 0.0), P(s1, y1, o), P(s0, y0, o), "stone_trim")
            mb.quad(P(s1, top1, o), P(s0, top0, o), P(s0, y0, o), P(s1, y1, o), "stone_trim")
            mb.quad(P(s0, top0, o), P(s1, top1, o), P(s1, top1, lip), P(s0, top0, lip), "stone_trim")

    def canal_beds(self):
        for w in self.L.water:
            r = w["rect"]
            ch = C.chunk_of(r.cx, r.cz)
            mb = self.out.mb(ch, "canal_bed")
            y = -2.0
            uv = [(0.0, 0.05), (r.w / 4.0, 0.05), (r.w / 4.0, 0.12), (0.0, 0.12)]
            mb.quad((r.x0, y, r.z1), (r.x1, y, r.z1), (r.x1, y, r.z0), (r.x0, y, r.z0), "stone_canal", uv=uv)

    def water_surfaces(self):
        for w in self.L.water:
            r = w["rect"]
            ch = C.chunk_of(r.cx, r.cz)
            mb = MB()
            nx = max(1, int(math.ceil(r.w / 4.0)))
            nz = max(1, int(math.ceil(r.d / 4.0)))
            y = w["y"]
            for i in range(nx):
                for j in range(nz):
                    x0 = r.x0 + r.w * i / nx
                    x1 = r.x0 + r.w * (i + 1) / nx
                    z0 = r.z0 + r.d * j / nz
                    z1 = r.z0 + r.d * (j + 1) / nz
                    mb.quad((x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0), "water")
            self.out.special(ch, "water_" + w["id"], mb, {"wr_cat": "water", "layout_id": w["id"], "water_y": y})

    # ------------------------------------------------------------------ balustrades
    def balustrades(self):
        L = self.L
        for b in L.blockers:
            if b["kind"] != "water_edge":
                continue
            r = b["rect"]
            along_x = r.w >= r.d
            ln = r.w if along_x else r.d
            n = max(1, int(round(ln / 0.1)))
            cl = (r.cz if along_x else r.cx)
            for sign in (-1.0, 1.0):
                pts = []
                for i in range(n + 1):
                    s = i * ln / n
                    if along_x:
                        x, z = r.x0 + s, cl + sign * (r.d / 2 + 0.2)
                    else:
                        x, z = cl + sign * (r.w / 2 + 0.2), r.z0 + s
                    g = L.ground_at(x, z)
                    if g is not None and L.building_at(x, z) is None:
                        pts.append((s, g))
                    else:
                        pts.append((s, None))
                for s0, s1, k, _ in runs(pts, lambda v: v is not None):
                    if not k or s1 - s0 < 0.5:
                        continue
                    prof = simplify_profile([(s, g) for s, g in pts if s0 - 1e-6 <= s <= s1 + 1e-6 and g is not None])
                    if along_x:
                        a, bpt = (r.x0 + s0, cl), (r.x0 + s1, cl)
                    else:
                        a, bpt = (cl, r.z0 + s0), (cl, r.z0 + s1)
                    prof = [(s - s0, g) for s, g in prof]
                    self.balustrade_run(a, bpt, prof, land_sign=sign, along_x=along_x, bid=b["id"])

    def balustrade_run(self, a, b, prof, land_sign, along_x, bid):
        """Stone balustrade from a to b (layout x,z); base follows prof [(s, y)] (s from a)."""
        ax, az = a
        bx, bz = b
        Ltot = math.hypot(bx - ax, bz - az)
        tx, tz = (bx - ax) / Ltot, (bz - az) / Ltot
        nx, nz = tz, -tx
        ch = C.chunk_of(0.5 * (ax + bx), 0.5 * (az + bz))
        mb = self.out.mb(ch, "balustrade")

        def base(s):
            return interp_profile(prof, s)

        def P(s, y, d):
            return (ax + tx * s + nx * d, base(s) + y, az + tz * s + nz * d)

        # posts at ends, at profile breaks and every <= 2.6 m
        cuts = sorted(set([0.0, Ltot] + [p[0] for p in prof if 0.1 < p[0] < Ltot - 0.1]))
        posts = []
        for c0, c1 in zip(cuts[:-1], cuts[1:]):
            k = max(1, int(math.ceil((c1 - c0) / 2.6)))
            for i in range(k):
                posts.append(c0 + (c1 - c0) * i / k)
        posts.append(Ltot)
        posts = sorted(set(round(p, 4) for p in posts))
        hw = 0.15
        pw = 0.17
        H = 0.9

        f0 = (nx * -1.0, 0.0, nz * -1.0)
        f1 = (nx, 0.0, nz)

        def sheared_box(s0, s1, y0, y1, d0, d1, mat, top=True, bottom=False):
            mb.quad(P(s0, y0, d0), P(s1, y0, d0), P(s1, y1, d0), P(s0, y1, d0), mat, facing=f0)
            mb.quad(P(s1, y0, d1), P(s0, y0, d1), P(s0, y1, d1), P(s1, y1, d1), mat, facing=f1)
            if top:
                mb.quad(P(s0, y1, d0), P(s1, y1, d0), P(s1, y1, d1), P(s0, y1, d1), mat, facing=(0, 1, 0))
            if bottom:
                mb.quad(P(s0, y0, d1), P(s1, y0, d1), P(s1, y0, d0), P(s0, y0, d0), mat, facing=(0, -1, 0))

        # orientation: d from -hw..hw; faces are two-sided visually since both sides are drawn
        # plinth + handrail along the whole run (sheared along the profile)
        segs = cuts
        for s0, s1 in zip(segs[:-1], segs[1:]):
            sheared_box(s0, s1, 0.0, 0.16, -hw, hw, "stone_trim")
            sheared_box(s0, s1, H - 0.13, H, -hw - 0.02, hw + 0.02, "stone_trim")
            mb.quad(P(s0, H - 0.13, -hw - 0.02), P(s1, H - 0.13, -hw - 0.02), P(s1, H - 0.13, hw + 0.02), P(s0, H - 0.13, hw + 0.02), "stone_trim", facing=(0, -1, 0))
        # balusters between posts
        bal = baluster_template()
        for p0, p1 in zip(posts[:-1], posts[1:]):
            span = p1 - p0 - 2 * pw
            if span <= 0.1:
                continue
            k = max(1, int(round(span / 0.23)))
            for i in range(k):
                s = p0 + pw + span * (i + 0.5) / k
                x, y, z = P(s, 0.16, 0.0)
                yaw = math.atan2(tx, tz)
                mb.append(bal, M_chain(M_translate(x, y, z), M_yaw(yaw)), reuv=False)
        for s in posts:
            s0, s1 = max(0.0, s - pw), min(Ltot, s + pw)
            y0 = min(base(s0), base(s1))
            yb = max(base(s0), base(s1))
            x0, z0 = ax + tx * s0, az + tz * s0
            x1, z1 = ax + tx * s1, az + tz * s1
            xa, xb = min(x0, x1) - (abs(nx) * (hw + 0.03)), max(x0, x1) + (abs(nx) * (hw + 0.03))
            za, zb = min(z0, z1) - (abs(nz) * (hw + 0.03)), max(z0, z1) + (abs(nz) * (hw + 0.03))
            mb.box(xa, y0, za, xb, yb + H + 0.06, zb, "stone_trim", skip=("bottom",))
            mb.box(xa - 0.03, yb + H + 0.06, za - 0.03, xb + 0.03, yb + H + 0.13, zb + 0.03, "stone_trim", skip=("bottom",))

    # ------------------------------------------------------------------ stairs & ramps
    def ramps(self):
        for r in self.L.ramps:
            if r["kind"] == "stairs":
                self.stairs(r)
            else:
                self.metal_ramp(r)

    def stairs(self, r):
        ax, ay, az = r["from"]
        bx, by, bz = r["to"]
        L = math.hypot(bx - ax, bz - az)
        tx, tz = (bx - ax) / L, (bz - az) / L
        nx, nz = tz, -tx
        w = r["width"] / 2
        rise = by - ay
        N = max(2, int(round(rise / 0.17)))
        back = (-tx, 0.0, -tz)
        ch = C.chunk_of(ax, az)
        mb = self.out.mb(ch, "stairs")

        def P(t, y, s):
            return (ax + tx * t + nx * s, y, az + tz * t + nz * s)
        nose = 0.03
        for k in range(1, N + 1):
            t0 = L * k / N                     # nosing position (on the ramp line)
            t1 = L * (k + 1) / N if k < N else L
            y0 = ay + rise * (k - 1) / N
            y1 = ay + rise * k / N
            # riser (slightly recessed under the nosing)
            mb.quad(P(t0 + nose, y0, w), P(t0 + nose, y0, -w), P(t0 + nose, y1 - 0.04, -w), P(t0 + nose, y1 - 0.04, w), "stone_trim", facing=back)
            # nosing front (bullnose approximated by a thin vertical band)
            mb.quad(P(t0, y1 - 0.04, w), P(t0, y1 - 0.04, -w), P(t0, y1, -w), P(t0, y1, w), "stone_trim", facing=back)
            mb.quad(P(t0 + nose, y1 - 0.04, w), P(t0 + nose, y1 - 0.04, -w), P(t0, y1 - 0.04, -w), P(t0, y1 - 0.04, w), "stone_trim", facing=(0, -1, 0))
            if k < N:
                mb.quad(P(t0, y1, w), P(t0, y1, -w), P(t1, y1, -w), P(t1, y1, w), "stone_trim", facing=(0, 1, 0))
            # cheek (side) faces: visible where no wall/solid is beside the stair
            for side in (w, -w):
                sx_, sz_ = ax + tx * 0.5 * (t0 + t1) + nx * side * 1.05, az + tz * 0.5 * (t0 + t1) + nz * side * 1.05
                c = self.L.classify(sx_, sz_)
                if c[0] == "floor" and c[1] < y1 - 0.02:
                    lo = c[1]
                    sg = 1.0 if side > 0 else -1.0
                    mb.quad(P(t1, lo, side), P(t0, lo, side), P(t0, y1, side), P(t1, y1, side), "stone_ashlar",
                            facing=(nx * sg, 0.0, nz * sg))

    def metal_ramp(self, r):
        ax, ay, az = r["from"]
        bx, by, bz = r["to"]
        L = math.hypot(bx - ax, bz - az)
        tx, tz = (bx - ax) / L, (bz - az) / L
        nx, nz = tz, -tx
        w = r["width"] / 2
        ch = C.chunk_of(ax, az)
        mb = self.out.mb(ch, "ramp")
        UP = (0.0, 1.0, 0.0)

        def P(t, s, dy=0.0):
            return (ax + tx * t + nx * s, ay + (by - ay) * t / L + dy, az + tz * t + nz * s)

        def G(t, s):
            return (ax + tx * t + nx * s, ay, az + tz * t + nz * s)
        edge = 0.22
        # deck (metal) with hazard striped edges, all exactly on the ramp plane
        mb.quad(P(0, w - edge), P(0, -w + edge), P(L, -w + edge), P(L, w - edge), "metal_deck", facing=UP)
        mb.quad(P(0, w), P(0, w - edge), P(L, w - edge), P(L, w), "hazard", facing=UP)
        mb.quad(P(0, -w + edge), P(0, -w), P(L, -w), P(L, -w + edge), "hazard", facing=UP)
        # side skirts (triangles) down to the yard floor
        mb.poly([G(0, w), G(L, w), P(L, w)], "concrete", facing=(nx, 0.0, nz))
        mb.poly([G(L, -w), G(0, -w), P(L, -w)], "concrete", facing=(-nx, 0.0, -nz))
        # riser at the high end is the platform itself; steel edge channel on the skirts' top edge
        for s in (w, -w):
            d = 1 if s > 0 else -1
            a0, a1 = P(0, s), P(L, s)
            mb.quad((a0[0] + nx * 0.02 * d, a0[1] - 0.1, a0[2] + nz * 0.02 * d), (a1[0] + nx * 0.02 * d, a1[1] - 0.1, a1[2] + nz * 0.02 * d),
                    (a1[0] + nx * 0.02 * d, a1[1], a1[2] + nz * 0.02 * d), (a0[0] + nx * 0.02 * d, a0[1], a0[2] + nz * 0.02 * d), "iron",
                    facing=(nx * d, 0.0, nz * d))

    # ------------------------------------------------------------------ bridges
    def bridges(self):
        for f in self.L.floors:
            if f["surface"] != "wood":
                continue
            w = self.L.water_at(f["rect"].cx, f["rect"].cz)
            if w is None:
                continue
            self.bridge(f, w)

    def bridge(self, f, w):
        """Stone segmental arch under a flat wooden deck (deck top = JSON floor top, drawn by floors())."""
        r = f["rect"]
        wr = w["rect"]
        axis = "x" if wr.w < wr.d else "z"      # span axis (across the canal)
        ch = C.chunk_of(r.cx, r.cz)
        mb = self.out.mb(ch, "bridge")
        if axis == "z":
            s_a, s_b = wr.z0, wr.z1
            c_a, c_b = r.x0 - 0.4, r.x1 + 0.4
        else:
            s_a, s_b = wr.x0, wr.x1
            c_a, c_b = r.z0 - 0.4, r.z1 + 0.4
        s_a2, s_b2 = s_a + 0.2, s_b - 0.2
        span = s_b2 - s_a2
        crown, spring_y = -0.32, -1.45
        rise = crown - spring_y
        R = ((span / 2) ** 2 + rise ** 2) / (2 * rise)
        yc = crown - R
        mid = 0.5 * (s_a2 + s_b2)
        nseg = 16
        half = math.asin(min(1.0, (span / 2) / R))
        arch = [(mid + R * math.sin(-half + 2 * half * i / nseg), yc + R * math.cos(-half + 2 * half * i / nseg)) for i in range(nseg + 1)]
        k = 1.0 + 0.32 / R
        ring = [(mid + (s_ - mid) * k, yc + (y_ - yc) * k) for s_, y_ in arch]

        def P(s_, y_, c_):
            return (c_, y_, s_) if axis == "z" else (s_, y_, c_)

        def cdir(sg):
            return (sg, 0.0, 0.0) if axis == "z" else (0.0, 0.0, sg)
        top = 0.0
        for c, sg in ((c_a, -1.0), (c_b, 1.0)):
            out = cdir(sg)
            c2 = c + sg * 0.05
            for (s0, y0), (s1, y1), (o0, p0), (o1, p1) in zip(arch[:-1], arch[1:], ring[:-1], ring[1:]):
                # spandrel wall above the voussoir ring
                mb.poly([P(o0, p0, c), P(o1, p1, c), P(o1, top, c), P(o0, top, c)], "stone_ashlar", facing=out)
                # voussoir ring face (proud by 0.05) + its outer and inner edges
                mb.poly([P(s0, y0, c2), P(s1, y1, c2), P(o1, p1, c2), P(o0, p0, c2)], "stone_trim", facing=out)
                mx, my = 0.5 * (o0 + o1) - mid, 0.5 * (p0 + p1) - yc
                radial = (mx, my, 0.0) if axis == "x" else (0.0, my, mx)
                mb.poly([P(o0, p0, c), P(o1, p1, c), P(o1, p1, c2), P(o0, p0, c2)], "stone_trim", facing=radial)
                inward = (-radial[0], -radial[1], -radial[2])
                mb.poly([P(s0, y0, c), P(s1, y1, c), P(s1, y1, c2), P(s0, y0, c2)], "stone_trim", facing=inward)
        # intrados (arch barrel underside), facing the arch centre
        for (s0, y0), (s1, y1) in zip(arch[:-1], arch[1:]):
            mx, my = 0.5 * (s0 + s1) - mid, 0.5 * (y0 + y1) - yc
            inward = (-mx, -my, 0.0) if axis == "x" else (0.0, -my, -mx)
            mb.poly([P(s0, y0, c_a), P(s0, y0, c_b), P(s1, y1, c_b), P(s1, y1, c_a)], "stone_ashlar", facing=inward)
        # parapet bases (tops of the spandrel walls beside the deck), flush at y=0
        if axis == "z":
            for x0, x1 in ((c_a, r.x0), (r.x1, c_b)):
                mb.quad((x0, top, s_b2), (x1, top, s_b2), (x1, top, s_a2), (x0, top, s_a2), "stone_trim", facing=(0, 1, 0))
        else:
            for z0, z1 in ((c_a, r.z0), (r.z1, c_b)):
                mb.quad((s_a2, top, z1), (s_b2, top, z1), (s_b2, top, z0), (s_a2, top, z0), "stone_trim", facing=(0, 1, 0))
        # end faces of the spandrel walls toward the canal walls are hidden (inside the copings)

    # ------------------------------------------------------------------ puddles & decals
    def puddles(self):
        import random
        n = 0
        for d in self.L.decor:
            if d["kind"] != "puddle":
                continue
            x, _, z = d["pos"]
            rad = d.get("scale", 1.0)
            g = self.L.ground_at(x, z)
            if g is None:
                continue
            rnd = random.Random(int(x * 1000 + z * 7))
            seg = 28
            mb = MB()
            y = g + PUDDLE_Y
            centre = (x, y, z)
            ring = []
            ph = [rnd.uniform(0, 6.28) for _ in range(3)]
            for k in range(seg):
                a = 2 * math.pi * k / seg
                rr = rad * (1.0 + 0.16 * math.sin(2 * a + ph[0]) + 0.1 * math.sin(3 * a + ph[1]) + 0.06 * math.sin(5 * a + ph[2]))
                sx = 1.25 if n % 2 == 0 else 0.85
                ring.append((x + math.cos(a) * rr * sx, y, z - math.sin(a) * rr / sx))
            rmax = rad * 1.45
            for k in range(seg):
                p0, p1 = ring[k], ring[(k + 1) % seg]
                uv = [(0.5, 0.5)] + [(0.5 + (p[0] - x) / (2 * rmax), 0.5 - (p[2] - z) / (2 * rmax)) for p in (p0, p1)]
                mb.poly([centre, p0, p1], "puddle", uv=uv)
            n += 1
            ch = C.chunk_of(x, z)
            self.out.special(ch, f"puddle_{n:02d}", mb, {"wr_cat": "puddle", "radius": rad})

    def decal_quad(self, ch, x, z, sx, sz, key, yaw=0.0, mat="detail", atl=None, uv=None):
        g = self.L.ground_at(x, z)
        if g is None:
            return
        y = g + DECAL_Y
        c, s = math.cos(yaw), math.sin(yaw)
        pts = []
        for (u, v) in ((-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, -0.5)):
            lx, lz = u * sx, v * sz
            pts.append((x + lx * c + lz * s, y, z - lx * s + lz * c))
        if uv is None:
            u0, v0, u1, v1 = C.atlas_uv(atl, key, inset_px=2)
            uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        self.out.mb(ch, "decal").poly(pts, mat, uv=uv, facing=(0, 1, 0))

    def decals(self):
        atl = C.atlas("detail")
        L = self.L
        # drain grates along the yard walls and near the platform
        for zz in (-18.6, -6.8, 6.8, 18.6):
            self.decal_quad("C", 31.2, zz, 0.7, 0.7, "grate", atl=atl)
        for xx in (36.0, 44.0, 50.5):
            self.decal_quad("C", xx, -19.3, 0.9, 0.5, "grate", atl=atl)
            self.decal_quad("C", xx, 19.3, 0.9, 0.5, "grate", atl=atl)
        for zz in (-7.0, 7.0):
            self.decal_quad("C", 51.2, zz, 0.6, 0.9, "grate", atl=atl)
        # manholes in streets and lanes
        for (x, z) in ((-30.0, -37.0), (22.0, -37.0), (-50.0, 37.0), (40.0, 37.0), (0.0, -30.5), (0.0, 30.5),
                       (-42.0, -27.0), (42.0, 27.0), (25.0, -10.0), (-25.0, 5.0), (0.0, 51.5), (0.0, -51.5)):
            self.decal_quad(C.chunk_of(x, z), x, z, 0.85, 0.85, "manhole", atl=atl)
        # painted walkway lines in the yard (solid yellow), outside the objective radius where long
        for z0 in (-19.0, 19.0):
            self.paint_line("C", (31.0, z0 * 0.84), (51.5, z0 * 0.84), 0.12)
        self.paint_line("C", (30.6, -15.5), (30.6, -10.8), 0.12)
        self.paint_line("C", (30.6, 10.8), (30.6, 15.5), 0.12)
        # hazard band on the platform edge (perch ledge) is part of the floor partition (metal edge band)
        # fountain surround: ring of setts around the basin (radius 2.9..3.6, far inside the 9 m circle)
        self.ring_decal("B", 0.0, 0.0, 2.95, 3.55, "paving_cobble")

    def paint_line(self, ch, a, b, w):
        ax, az = a
        bx, bz = b
        L = math.hypot(bx - ax, bz - az)
        tx, tz = (bx - ax) / L, (bz - az) / L
        nx, nz = -tz * w / 2, tx * w / 2
        g = self.L.ground_at(ax, az) or 0.0
        y = g + DECAL_Y
        pts = [(ax - nx, y, az - nz), (bx - nx, y, bz - nz), (bx + nx, y, bz + nz), (ax + nx, y, az + nz)]
        from bl_core import poly_normal
        self.out.mb(ch, "decal").poly(pts, "paint_yellow", facing=(0, 1, 0))

    def ring_decal(self, ch, cx, cz, r0, r1, mat, seg=48):
        y = (self.L.ground_at(cx + r0 + 0.1, cz) or 0.0) + DECAL_Y * 0.75
        mb = self.out.mb(ch, "decal")
        for k in range(seg):
            a0 = 2 * math.pi * k / seg
            a1 = 2 * math.pi * (k + 1) / seg
            p = [(cx + math.cos(a0) * r0, y, cz - math.sin(a0) * r0), (cx + math.cos(a0) * r1, y, cz - math.sin(a0) * r1),
                 (cx + math.cos(a1) * r1, y, cz - math.sin(a1) * r1), (cx + math.cos(a1) * r0, y, cz - math.sin(a1) * r0)]
            mb.poly(p, mat, facing=(0, 1, 0))


# ----------------------------------------------------------------------------- profile helpers
def simplify_profile(prof, tol=0.004):
    """Remove collinear interior points from [(s, y)]."""
    if len(prof) <= 2:
        return prof
    out = [prof[0]]
    for i in range(1, len(prof) - 1):
        s0, y0 = out[-1]
        s1, y1 = prof[i]
        s2, y2 = prof[i + 1]
        if abs(s2 - s0) < 1e-9:
            continue
        yi = y0 + (y2 - y0) * (s1 - s0) / (s2 - s0)
        if abs(yi - y1) > tol:
            out.append(prof[i])
    out.append(prof[-1])
    return out


def interp_profile(prof, s):
    if s <= prof[0][0]:
        return prof[0][1]
    for (s0, y0), (s1, y1) in zip(prof[:-1], prof[1:]):
        if s0 <= s <= s1:
            if s1 - s0 < 1e-9:
                return y1
            return y0 + (y1 - y0) * (s - s0) / (s1 - s0)
    return prof[-1][1]


_BAL = None


def baluster_template():
    """Vase baluster (6 sides) from y=0 (plinth top) to 0.61 (handrail underside)."""
    global _BAL
    if _BAL is None:
        mb = MB()
        prof = [(0.055, 0.0), (0.055, 0.05), (0.035, 0.08), (0.062, 0.22), (0.068, 0.3), (0.045, 0.42),
                (0.03, 0.5), (0.045, 0.55), (0.055, 0.58), (0.055, 0.61)]
        mb.lathe(prof, 6, "stone_trim", cap_top=False, smooth=True)
        _BAL = mb
    return _BAL
