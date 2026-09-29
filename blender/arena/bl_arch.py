"""Buildings for Briarport, generated from the layout's `kind: building` solids.

Massing: each solid keeps its exact footprint (visual walls sit ON the collision faces up to
2.5 m, contract tolerance +-0.15 m). Thin perimeter solids whose back faces the outside of the
arena are deepened outward (never into playable space) so they read as real houses. Footprints
are split into parcels with individual heights, roofs and facade designs (style hint).

Facades: wall planes with rectangular/arched openings cut into the mesh (reveals <= 0.15 m
deep below 2.5 m), trims (plinth, string course, cornice, quoins), windows (atlas glass),
shutters, doors, shopfronts with awnings (>= 2.5 m), balconies (>= 3.5 m), window boxes
(foliage_*), wall lanterns (emissive_*), gutters/downpipes. Roofs: gable / gable-front with
stepped gables / hip + cupola / shed / flat with parapet or crenellations; chimneys.
Gatehouse and yard-gate gaps get arched passages springing at 2.6 m.
"""
from __future__ import annotations

import math
import random

import common as C
from bl_core import MB, M_translate, M_yaw, M_chain, v_dot
from bl_ground import side_frame, runs
from common import Rect

UP = (0.0, 1.0, 0.0)
DOWN = (0.0, -1.0, 0.0)

STYLES = {
    "townhouse": dict(walls=["plaster_cream", "plaster_ochre", "plaster_rose", "brick_red", "plaster_cream", "plaster_ochre"],
                      base="stone_ashlar", eave=(10.5, 13.5), ground=(3.9, 4.3), floor_h=(3.1, 3.4), bay=(2.6, 3.3),
                      parcel=(6.5, 9.5), roof="gable", pitch=(30.0, 36.0), shutters=0.75, balconies=0.4, shops=0.55,
                      wins=["win_sash", "win_casement", "win_sash"], doors=["door_green", "door_blue", "door_red"]),
    "canal_house": dict(walls=["brick_red", "brick_brown", "brick_red", "plaster_white", "plaster_ochre"],
                        base="stone_ashlar", eave=(10.8, 13.8), ground=(3.7, 4.0), floor_h=(3.0, 3.2), bay=(1.7, 2.3),
                        parcel=(4.6, 6.4), roof="gable_front", pitch=(48.0, 54.0), shutters=0.25, balconies=0.12, shops=0.25,
                        wins=["win_tall", "win_sash"], doors=["door_arch", "door_green", "door_plank"], stepped=True),
    "market_hall": dict(walls=["stone_ashlar"], base="stone_ashlar", eave=(12.4, 12.4), ground=(5.2, 5.2), floor_h=(5.6, 5.6),
                        bay=(3.3, 4.2), parcel=(99.0, 99.0), roof="hip", pitch=(27.0, 27.0), shutters=0.0, balconies=0.0, shops=0.0,
                        wins=["win_hall"], doors=["door_arch"]),
    "warehouse": dict(walls=["brick_brown", "brick_red", "brick_brown"], base="stone_ashlar", eave=(9.2, 11.8), ground=(4.6, 5.0),
                      floor_h=(3.4, 3.6), bay=(3.3, 4.1), parcel=(10.0, 14.0), roof="gable_front", pitch=(20.0, 24.0),
                      shutters=0.0, balconies=0.0, shops=0.0, wins=["win_industrial"], doors=["door_warehouse", "door_rollup"]),
    "warehouse_gate": dict(walls=["brick_brown"], base="stone_ashlar", eave=(8.8, 8.8), ground=(4.6, 4.6), floor_h=(3.5, 3.5),
                           bay=(3.6, 4.2), parcel=(99.0, 99.0), roof="flat", pitch=(0, 0), shutters=0.0, balconies=0.0, shops=0.0,
                           wins=["win_industrial"], doors=["door_warehouse"]),
    "gatehouse": dict(walls=["stone_ashlar"], base="stone_ashlar", eave=(9.6, 9.6), ground=(4.4, 4.4), floor_h=(3.4, 3.4),
                      bay=(2.4, 3.0), parcel=(99.0, 99.0), roof="crenel", pitch=(0, 0), shutters=0.0, balconies=0.0, shops=0.0,
                      wins=["win_small", "win_arch"], doors=["door_arch"]),
}

KEEP_OUT_PAD = 1.0


class Opening:
    __slots__ = ("s0", "s1", "y0", "y1", "arch", "depth", "through", "kind", "key", "floor")

    def __init__(self, s0, s1, y0, y1, arch=0.0, depth=0.15, through=False, kind="win", key="win_sash", floor=0):
        self.s0, self.s1, self.y0, self.y1 = s0, s1, y0, y1
        self.arch = arch
        self.depth = depth
        self.through = through
        self.kind = kind
        self.key = key
        self.floor = floor

    @property
    def spring(self):
        return self.y1 - self.arch if self.arch > 0 else self.y1


class Frame:
    """Facade frame: O origin at the face's left end (seen from outside), t along, n outward."""

    def __init__(self, sx, sz, t, n, L, y0=0.0):
        self.O = (sx, y0, sz)
        self.t = (t[0], 0.0, t[1])
        self.n = (n[0], 0.0, n[1])
        self.L = L

    def P(self, s, y, d=0.0):
        return (self.O[0] + self.t[0] * s + self.n[0] * d, self.O[1] + y, self.O[2] + self.t[2] * s + self.n[2] * d)

    def at(self, s, d=0.0):
        p = self.P(s, 0.0, d)
        return p[0], p[2]


# =============================================================================== wall with openings
def wall_with_openings(mb: MB, fr: Frame, y_lo, y_hi, openings, rows, s_lo=0.0, s_hi=None, reveal_mat=None):
    """Wall plane d=0 over s in [s_lo, s_hi], y in [y_lo, y_hi] minus openings (rect or
    semicircular-arched heads). rows: [(y_from, y_to, mat)]. Adds reveals (jambs, sill, head/arch)."""
    s_hi = fr.L if s_hi is None else s_hi
    xs = {s_lo, s_hi}
    ys = {y_lo, y_hi}
    for (a, b, _) in rows:
        if y_lo < a < y_hi:
            ys.add(a)
        if y_lo < b < y_hi:
            ys.add(b)
    ops = [o for o in openings if o.s1 > s_lo + 1e-6 and o.s0 < s_hi - 1e-6]
    for o in ops:
        xs.update((max(s_lo, o.s0), min(s_hi, o.s1)))
        ys.update((max(y_lo, o.y0), min(y_hi, o.y1)))
        if o.arch > 0:
            ys.add(o.spring)
    xs, ys = sorted(xs), sorted(ys)

    def row_mat(y):
        for a, b, m in rows:
            if a - 1e-6 <= y <= b + 1e-6:
                return m
        return rows[-1][2]

    def hole(cx, cy):
        for o in ops:
            if o.s0 < cx < o.s1 and o.y0 < cy < o.y1:
                return True
        return False
    cells = {}
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            cx, cy = 0.5 * (xs[i] + xs[i + 1]), 0.5 * (ys[j] + ys[j + 1])
            cells[(i, j)] = None if hole(cx, cy) else row_mat(cy)
    # merge runs per row, then stack identical spans
    strips = []
    for j in range(len(ys) - 1):
        i = 0
        while i < len(xs) - 1:
            m = cells[(i, j)]
            if m is None:
                i += 1
                continue
            k = i
            while k + 1 < len(xs) - 1 and cells[(k + 1, j)] == m:
                k += 1
            strips.append([xs[i], xs[k + 1], ys[j], ys[j + 1], m])
            i = k + 1
    merged = []
    for s in strips:
        for t in merged:
            if abs(t[0] - s[0]) < 1e-6 and abs(t[1] - s[1]) < 1e-6 and abs(t[3] - s[2]) < 1e-6 and t[4] == s[4]:
                t[3] = s[3]
                break
        else:
            merged.append(list(s))
    n = fr.n
    for s0, s1, y0, y1, m in merged:
        mb.poly([fr.P(s0, y0), fr.P(s1, y0), fr.P(s1, y1), fr.P(s0, y1)], m, facing=n)
    # reveals + arch spandrels
    for o in ops:
        rm = reveal_mat or row_mat(0.5 * (o.y0 + o.spring))
        d = -o.depth
        spring = o.spring
        tvec = fr.t
        mt = (-tvec[0], 0.0, -tvec[2])
        if not o.through or o.kind != "passage":
            mb.poly([fr.P(o.s0, o.y0, 0), fr.P(o.s0, o.y0, d), fr.P(o.s0, spring, d), fr.P(o.s0, spring, 0)], rm, facing=tvec)
            mb.poly([fr.P(o.s1, o.y0, d), fr.P(o.s1, o.y0, 0), fr.P(o.s1, spring, 0), fr.P(o.s1, spring, d)], rm, facing=mt)
        if o.kind != "passage" and o.y0 > y_lo + 1e-3:
            mb.poly([fr.P(o.s0, o.y0, 0), fr.P(o.s1, o.y0, 0), fr.P(o.s1, o.y0, d), fr.P(o.s0, o.y0, d)], rm, facing=UP)
        if o.arch <= 0:
            mb.poly([fr.P(o.s0, o.y1, d), fr.P(o.s1, o.y1, d), fr.P(o.s1, o.y1, 0), fr.P(o.s0, o.y1, 0)], rm, facing=DOWN)
        else:
            cs = 0.5 * (o.s0 + o.s1)
            r = 0.5 * (o.s1 - o.s0)
            nseg = max(8, int(r * 6))
            arc = [(cs - r * math.cos(math.pi * k / nseg), spring + r * math.sin(math.pi * k / nseg)) for k in range(nseg + 1)]
            ymat = row_mat(spring + r * 0.5)
            for (sa, ya), (sb, yb) in zip(arc[:-1], arc[1:]):
                # spandrel strip above the arc up to the rectangle top
                mb.poly([fr.P(sa, ya), fr.P(sb, yb), fr.P(sb, o.y1), fr.P(sa, o.y1)], ymat, facing=n)
                # intrados reveal
                mx, my = 0.5 * (sa + sb) - cs, 0.5 * (ya + yb) - spring
                inward = (-(tvec[0] * mx), -my, -(tvec[2] * mx))
                mb.poly([fr.P(sa, ya, 0), fr.P(sb, yb, 0), fr.P(sb, yb, d), fr.P(sa, ya, d)], rm, facing=inward)


# =============================================================================== small builders
def glass(mb, fr, o, atl, key, d=None, mat="detail"):
    d = -o.depth if d is None else d
    u0, v0, u1, v1 = C.atlas_uv(atl, key, inset_px=2)
    mb.poly([fr.P(o.s0, o.y0, d), fr.P(o.s1, o.y0, d), fr.P(o.s1, o.y1, d), fr.P(o.s0, o.y1, d)], mat,
            uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=fr.n)


def fbox(mb, fr, s0, s1, y0, y1, d0, d1, mat, skip=()):
    mb.fbox(fr.O, fr.t, fr.n, s0, s1, y0 + fr.O[1] * 0, y1, d0, d1, mat, skip=skip)


def atlas_quad(mb, pts, atl, key, facing, mat="detail"):
    u0, v0, u1, v1 = C.atlas_uv(atl, key, inset_px=2)
    mb.poly(pts, mat, uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=facing)


def gable_triangle(mb, fr, L, H, rise, mat):
    mb.poly([fr.P(0, H), fr.P(L, H), fr.P(L / 2, H + rise)], mat, facing=fr.n)


# =============================================================================== parcels
class Parcel:
    def __init__(self, rect, solid, style, rng, idx):
        self.r = rect
        self.solid = solid
        self.style = style
        self.S = STYLES[style]
        self.rng = rng
        self.idx = idx
        S = self.S
        self.H = rng.uniform(*S["eave"])
        self.g = rng.uniform(*S["ground"])
        self.fh = rng.uniform(*S["floor_h"])
        self.wall = rng.choice(S["walls"])
        self.pitch = math.radians(rng.uniform(*S["pitch"])) if S["pitch"][1] > 0 else 0.0
        self.roof = S["roof"]
        self.chunk = C.chunk_of(rect.cx, rect.cz)
        self.passage = False
        self.base_y = 0.0
        self.sides = {}
        self.no_roof = False


class Buildings:
    def __init__(self, lay: C.Layout, out, kit=None):
        self.L = lay
        self.out = out
        self.kit = kit
        self.atl = C.atlas("detail")
        self.iron = C.atlas("ironwork")
        self.fol = C.atlas("foliage")
        self.keep_out = []
        for d in lay.decor:
            k = d["kind"]
            x, _, z = d["pos"]
            if k == "skyline_cathedral":
                self.keep_out.append(Rect(x - 16, x + 16, z - 30, z + 30) if abs(z) > 56 else Rect(x - 16, x + 16, z - 2, z + 2))
            elif k in ("skyline_tower",):
                self.keep_out.append(Rect(x - 4, x + 4, z - 4, z + 4))
            elif k == "crane":
                self.keep_out.append(Rect(x - 3.5, x + 3.5, z - 5.0, z + 5.0))
        self.parcels = []
        self.chimney_tops = []

    # ------------------------------------------------------------------ exposure
    def classify_side(self, r: Rect, side, off=0.3, step=0.5):
        (sx, sz), (tx, tz), (nx, nz), ln = side_frame(r, side)
        n = max(1, int(round(ln / step)))
        res = []
        for i in range(n):
            s = (i + 0.5) * ln / n
            x, z = sx + tx * s + nx * off, sz + tz * s + nz * off
            c = self.L.classify(x, z)
            k = c[0]
            if k == "void" and not self.L.in_footprint(x, z):
                k = "outer"
            elif k == "void":
                k = "outer"
            lvl = c[1] if k == "floor" else 0.0
            res.append((s, k, lvl))
        return res, ln

    # ------------------------------------------------------------------ planning
    def plan(self):
        solids = [s for s in self.L.solids if s["kind"] == "building"]
        for s in solids:
            self.plan_solid(s)
        self.plan_passages(solids)

    def plan_solid(self, s):
        r = s["rect"]
        style = s.get("style", "townhouse")
        rng = random.Random(hash_str(s["id"]))
        vis = Rect(r.x0, r.x1, r.z0, r.z1)
        thin_axis = "x" if r.w <= r.d else "z"
        thick = min(r.w, r.d)
        if thick <= 2.5 and style not in ("gatehouse", "warehouse_gate"):
            # deepen outward if the back side faces the outside of the arena
            for side in (("w", "e") if thin_axis == "x" else ("n", "s")):
                cls, _ = self.classify_side(r, side)
                if all(k == "outer" for _, k, _ in cls):
                    want = 9.0 if style != "warehouse" else 8.0
                    ext = want - thick
                    vis = self.extend(vis, side, ext)
        vis_list = [vis]
        long_axis = "x" if vis.w >= vis.d else "z"
        S = STYLES[style]
        for vr in vis_list:
            L = vr.w if long_axis == "x" else vr.d
            if L <= S["parcel"][1] * 1.2:
                widths = [L]
            else:
                widths = []
                left = L
                while left > S["parcel"][1]:
                    w = rng.uniform(*S["parcel"])
                    if left - w < S["parcel"][0]:
                        w = left / 2.0
                    widths.append(w)
                    left -= w
                widths.append(left)
            a = vr.x0 if long_axis == "x" else vr.z0
            for i, w in enumerate(widths):
                if long_axis == "x":
                    pr = Rect(a, a + w, vr.z0, vr.z1)
                else:
                    pr = Rect(vr.x0, vr.x1, a, a + w)
                a += w
                p = Parcel(pr, s, style, random.Random(hash_str(s["id"]) * 31 + i), i)
                p.long_axis = long_axis
                self.parcels.append(p)

    def extend(self, r: Rect, side, ext):
        x0, x1, z0, z1 = r.x0, r.x1, r.z0, r.z1
        if side == "w":
            x0 -= ext
        elif side == "e":
            x1 += ext
        elif side == "n":
            z0 -= ext
        else:
            z1 += ext
        nr = Rect(x0, x1, z0, z1)
        for ko in self.keep_out:
            if nr.x0 < ko.x1 and nr.x1 > ko.x0 and nr.z0 < ko.z1 and nr.z1 > ko.z0:
                if side == "w":
                    nr.x0 = max(nr.x0, ko.x1 + KEEP_OUT_PAD) if ko.x1 < r.x0 else nr.x0
                elif side == "e":
                    nr.x1 = min(nr.x1, ko.x0 - KEEP_OUT_PAD) if ko.x0 > r.x1 else nr.x1
                elif side == "n":
                    nr.z0 = max(nr.z0, ko.z1 + KEEP_OUT_PAD) if ko.z1 < r.z0 else nr.z0
                else:
                    nr.z1 = min(nr.z1, ko.z0 - KEEP_OUT_PAD) if ko.z0 > r.z1 else nr.z1
        return nr

    def plan_passages(self, solids):
        for style in ("gatehouse", "warehouse_gate"):
            ss = [s for s in solids if s.get("style") == style]
            for a in ss:
                for b in ss:
                    ra, rb = a["rect"], b["rect"]
                    if ra.w < ra.d:     # thin in x, long in z: gaps along z
                        if abs(ra.x0 - rb.x0) < 1e-6 and abs(ra.x1 - rb.x1) < 1e-6 and 0.5 < rb.z0 - ra.z1 <= 7.0:
                            gap = Rect(ra.x0, ra.x1, ra.z1, rb.z0)
                        else:
                            continue
                    else:
                        if abs(ra.z0 - rb.z0) < 1e-6 and abs(ra.z1 - rb.z1) < 1e-6 and 0.5 < rb.x0 - ra.x1 <= 7.0:
                            gap = Rect(ra.x1, rb.x0, ra.z0, ra.z1)
                        else:
                            continue
                    if self.L.ground_at(gap.cx, gap.cz) is None:
                        continue
                    p = Parcel(gap, a, style, random.Random(hash_str(a["id"] + b["id"])), 99)
                    p.passage = True
                    p.long_axis = "x" if gap.w >= gap.d else "z"
                    self.parcels.append(p)

    # ------------------------------------------------------------------ harmonise heights
    def harmonise(self):
        by_solid = {}
        for p in self.parcels:
            by_solid.setdefault(p.solid["id"], []).append(p)
        for sid, ps in by_solid.items():
            st = ps[0].style
            if st in ("gatehouse", "warehouse_gate", "market_hall"):
                H = ps[0].H
                for p in ps:
                    p.H = H
                    p.g = ps[0].g
                    p.wall = ps[0].wall
        # passages match their neighbours
        for p in self.parcels:
            if p.passage:
                nb = [q for q in self.parcels if q.solid["id"] == p.solid["id"] and not q.passage]
                if nb:
                    p.H, p.g, p.wall = nb[0].H, nb[0].g, nb[0].wall
        # gatehouse centre becomes a clock tower
        for p in self.parcels:
            if p.style == "gatehouse" and not p.passage and p.r.w >= 7.0:
                p.H = 13.2
                p.roof = "tower"

    # ------------------------------------------------------------------ queries
    def roof_height_at(self, x, z):
        """Top of the roof surface at (x, z) (max over parcels containing the point), or None."""
        best = None
        for p in self.parcels:
            r = p.r
            if not r.contains(x, z) or not hasattr(p, "ridge"):
                continue
            H = p.H
            if p.roof in ("gable", "gable_front") and p.rise > 0:
                if p.ridge == "x":
                    d, half = abs(z - r.cz), r.d / 2
                else:
                    d, half = abs(x - r.cx), r.w / 2
                h = H + (half - d) * math.tan(p.pitch)
            elif p.roof in ("hip", "tower"):
                o = 0.5 if p.roof == "hip" else 0.45
                tp = math.tan(p.pitch) if p.roof == "hip" else math.tan(math.radians(52))
                dx = min(x - (r.x0 - o), (r.x1 + o) - x)
                dz = min(z - (r.z0 - o), (r.z1 + o) - z)
                h = (H - o * tp if p.roof == "hip" else H) + min(dx, dz) * tp
            else:
                h = H + 1.0
            best = h if best is None else max(best, h)
        return best

    # ------------------------------------------------------------------ build
    def build(self):
        self.plan()
        self.harmonise()
        for p in self.parcels:
            mb = self.out.mb(p.chunk, "bld_" + p.solid["id"])
            self.build_parcel(p, mb)

    def build_parcel(self, p: Parcel, mb: MB):
        r = p.r
        exp = {}
        for side in ("n", "s", "e", "w"):
            exp[side] = self.classify_side(r, side)
        p.sides = exp
        # roof orientation
        ridge = self.ridge_axis(p, exp)
        p.ridge = ridge
        rise = 0.0
        if p.roof in ("gable", "gable_front") and not p.passage:
            span = r.d if ridge == "x" else r.w
            if span < 3.2:
                p.roof = "flat"
            else:
                rise = span / 2.0 * math.tan(p.pitch)
        p.rise = rise
        for side in ("n", "s", "e", "w"):
            cls, ln = exp[side]
            self.build_face(p, mb, side, cls, ln)
        self.build_roof(p, mb, exp)

    def ridge_axis(self, p, exp):
        r = p.r
        if p.roof == "gable":
            # ridge parallel to the main exposed street side(s)
            ex = {s: sum(1 for _, k, _ in exp[s][0] if k in ("floor", "water")) for s in exp}
            ns = ex["n"] + ex["s"]
            ew = ex["e"] + ex["w"]
            if ns == ew:
                return "x" if r.w >= r.d else "z"
            return "x" if ns > ew else "z"
        if p.roof == "gable_front":
            ex = {s: sum(1 for _, k, _ in exp[s][0] if k in ("floor", "water", "outer")) for s in exp}
            # gables face the long exposed sides => ridge perpendicular to the parcel's long axis of the solid row
            if p.long_axis == "x":
                return "z"
            return "x"
        return "x" if r.w >= r.d else "z"

    # ------------------------------------------------------------------ faces
    def face_frame(self, r, side):
        (sx, sz), t, n, ln = side_frame(r, side)
        return Frame(sx, sz, t, n, ln)

    def build_face(self, p: Parcel, mb: MB, side, cls, ln):
        r = p.r
        fr = self.face_frame(r, side)
        H = p.H
        kinds = [k for _, k, _ in cls]
        exposed = [k in ("floor", "water") for k in kinds]
        outer = all(k == "outer" for k in kinds)
        party = all(k == "building" for k in kinds)
        is_gable_side = (p.roof in ("gable", "gable_front") and
                         ((p.ridge == "x" and side in ("e", "w")) or (p.ridge == "z" and side in ("n", "s"))))
        rows = self.rows_for(p)
        if p.passage:
            self.passage_face(p, mb, fr, side, cls)
            return
        if party:
            mb.poly([fr.P(0, 0), fr.P(ln, 0), fr.P(ln, H), fr.P(0, H)], p.wall, facing=fr.n)
            if is_gable_side and p.rise > 0:
                gable_triangle(mb, fr, ln, H, p.rise, p.wall)
            return
        levels = [lvl for _, k, lvl in cls if k == "floor"]
        base_lvl = min(levels) if levels else 0.0
        openings, extras = self.design_face(p, fr, side, cls, ln, is_gable_side, outer)
        wall_with_openings(mb, fr, 0.0, H, openings, rows)
        for fn in extras:
            fn(mb)
        self.trims(p, mb, fr, side, cls, ln, openings, outer)
        if is_gable_side and p.rise > 0:
            if p.S.get("stepped") and not outer:
                self.stepped_gable(p, mb, fr, ln)
            else:
                gable_triangle(mb, fr, ln, H, p.rise, p.wall)
                if not outer:
                    self.gable_details(p, mb, fr, ln)

    def rows_for(self, p):
        base = p.S["base"]
        if p.style in ("market_hall", "gatehouse"):
            return [(0.0, p.H + 20, p.wall)]
        if p.style == "townhouse" and p.wall.startswith("plaster"):
            return [(0.0, p.g, base), (p.g, p.H + 20, p.wall)]
        return [(0.0, 0.62, base), (0.62, p.H + 20, p.wall)]

    # ------------------------------------------------------------------ facade design
    def design_face(self, p, fr, side, cls, ln, is_gable, outer):
        rng = random.Random(hash_str(p.solid["id"]) + p.idx * 7 + ord(side))
        S = p.S
        H = p.H
        openings = []
        extras = []
        if ln < 2.6:
            return openings, extras
        style = p.style
        margin = 0.75 if style != "market_hall" else 1.4
        bw_target = rng.uniform(*S["bay"])
        n_bays = max(1, int(round((ln - 2 * margin) / bw_target)))
        bw = (ln - 2 * margin) / n_bays
        floors = []
        y = p.g
        while y + p.fh <= H - 0.5:
            floors.append(y)
            y += p.fh
        if style == "market_hall":
            floors = [p.g + 0.6]
        win_key = rng.choice(S["wins"])
        shutter = rng.random() < S["shutters"]
        sh_key = rng.choice(["shutter_green", "shutter_blue", "shutter_brown", "shutter_red"])
        door_key = rng.choice(S["doors"])

        def kind_at(s):
            best = None
            for ss, k, lvl in cls:
                if best is None or abs(ss - s) < abs(best[0] - s):
                    best = (ss, k, lvl)
            return best[1], best[2]
        door_bays = set()
        street_bays = [i for i in range(n_bays) if kind_at(margin + (i + 0.5) * bw)[0] == "floor"]
        if street_bays and not outer:
            door_bays.add(rng.choice(street_bays))
            if n_bays >= 5 and rng.random() < 0.5:
                door_bays.add(rng.choice(street_bays))
        shop = (not outer) and rng.random() < S["shops"] and style == "townhouse" or (style == "canal_house" and rng.random() < S["shops"])
        centre_bay = n_bays // 2
        for i in range(n_bays):
            sc = margin + (i + 0.5) * bw
            k, lvl = kind_at(sc)
            if k == "building":
                continue
            gy = lvl if k == "floor" else 0.0
            # --- ground floor
            if style == "gatehouse":
                if i % 2 == 1 or n_bays == 1:
                    ww = 0.55
                    openings.append(Opening(sc - ww / 2, sc + ww / 2, gy + 1.9, gy + 3.1, arch=ww / 2, depth=0.14, key="win_small"))
            elif style == "warehouse_gate":
                pass
            elif style == "market_hall":
                aw = min(2.6, bw * 0.62)
                if k == "floor":
                    ob = Opening(sc - aw / 2, sc + aw / 2, gy, gy + 4.3, arch=aw / 2, depth=0.14,
                                 kind="door" if i in door_bays else "shopwin", key="door_arch" if i in door_bays else "win_arch")
                else:
                    ob = Opening(sc - aw / 2, sc + aw / 2, gy + 1.0, gy + 4.3, arch=aw / 2, depth=0.14, key="win_arch")
                openings.append(ob)
            elif style == "warehouse":
                if i in door_bays or (k == "floor" and rng.random() < 0.45 and (not is_gable or i == centre_bay)):
                    dw = min(3.2, bw - 0.7)
                    openings.append(Opening(sc - dw / 2, sc + dw / 2, gy, gy + 3.9, arch=0.0, depth=0.14, kind="door",
                                            key=rng.choice(["door_warehouse", "door_rollup"])))
                else:
                    ww = min(1.4, bw * 0.45)
                    openings.append(Opening(sc - ww / 2, sc + ww / 2, gy + 1.4, gy + 3.4, arch=ww / 2, depth=0.14, key="win_industrial"))
            else:
                if i in door_bays:
                    dw = 1.3 if style == "townhouse" else 1.1
                    arch = dw / 2 if door_key == "door_arch" else 0.0
                    openings.append(Opening(sc - dw / 2, sc + dw / 2, gy, gy + 2.55 + arch * 0.3, arch=arch, depth=0.12, kind="door", key=door_key))
                elif shop and k == "floor":
                    sw = min(2.4, bw - 0.45)
                    openings.append(Opening(sc - sw / 2, sc + sw / 2, gy + 0.45, gy + 2.75, depth=0.12, kind="shop", key="win_shop"))
                else:
                    ww = min(1.15, bw * 0.55)
                    top = min(p.g - 0.55, gy + 2.95)
                    openings.append(Opening(sc - ww / 2, sc + ww / 2, gy + 0.95, top, depth=0.13, kind="win", key=win_key))
            # --- upper floors
            for fi, fy in enumerate(floors):
                if style == "gatehouse":
                    ww = 0.9 if (i % 2 == 0 or n_bays == 1) else 0.7
                    openings.append(Opening(sc - ww / 2, sc + ww / 2, fy + 0.9, fy + 2.4, arch=ww / 2, depth=0.16, key="win_arch", floor=fi + 1))
                    continue
                if style == "warehouse_gate":
                    continue
                if style == "market_hall":
                    ww = min(2.3, bw * 0.55)
                    openings.append(Opening(sc - ww / 2, sc + ww / 2, fy, min(H - 1.2, fy + 4.6), arch=ww / 2, depth=0.2, key="win_hall", floor=1))
                    continue
                if style == "warehouse":
                    if is_gable and i == centre_bay and n_bays % 2 == 1:
                        dw = 1.5
                        openings.append(Opening(sc - dw / 2, sc + dw / 2, fy + 0.15, fy + 2.5, depth=0.16, kind="loading", key="door_plank", floor=fi + 1))
                    else:
                        ww = min(1.5, bw * 0.46)
                        openings.append(Opening(sc - ww / 2, sc + ww / 2, fy + 0.8, fy + 2.7, arch=ww / 2 * 0.99, depth=0.2, key="win_industrial", floor=fi + 1))
                    continue
                ww = min(1.15, bw * 0.56) if style == "townhouse" else min(1.0, bw * 0.58)
                wh = min(p.fh - 1.05, 2.05 if fi == 0 else 1.85)
                wy = fy + 0.85
                if is_gable and style == "canal_house":
                    pass
                balcony = (not outer) and style in ("townhouse", "canal_house") and fi == 0 and rng.random() < S["balconies"]
                kind = "balcony" if balcony else "win"
                if balcony:
                    wy = fy + 0.1
                    wh = min(p.fh - 0.55, 2.55)
                    key = "door_blue" if rng.random() < 0.3 else win_key
                else:
                    key = win_key
                openings.append(Opening(sc - ww / 2, sc + ww / 2, wy, wy + wh, depth=0.18, kind=kind, key=key, floor=fi + 1))
        # inserts
        atl = self.atl
        for o in openings:
            if o.kind == "passage":
                continue
            if o.key.startswith("door"):
                extras.append(lambda m, o=o: glass(m, fr, o, atl, o.key))
            else:
                extras.append(lambda m, o=o: glass(m, fr, o, atl, o.key))
            if outer:
                continue
            extras.append(lambda m, o=o, sh=(shutter and o.kind in ("win", "balcony") and o.floor >= 1): self.surround(p, m, fr, o, sh, sh_key))
            if o.kind == "balcony":
                extras.append(lambda m, o=o: self.balcony(p, m, fr, o))
            elif o.kind == "win" and o.floor >= 1 and p.style in ("townhouse", "canal_house") and rng.random() < 0.28:
                extras.append(lambda m, o=o: self.window_box(p, m, fr, o))
            if o.kind == "shop":
                extras.append(lambda m, o=o, c=rng.choice(["canvas_red", "canvas_green", "canvas_red", "canvas_cream"]),
                              sg=rng.choice(["shop_fish", "shop_bread", "shop_key", None]): self.shopfront(p, m, fr, o, c, sg))
            if o.kind == "door" and p.style in ("townhouse", "canal_house", "market_hall"):
                extras.append(lambda m, o=o: self.door_lamp(p, m, fr, o))
        if p.style == "warehouse" and is_gable and not outer:
            extras.append(lambda m: self.hoist_beam(p, m, fr, ln))
        return openings, extras

    # ------------------------------------------------------------------ details
    def surround(self, p, mb, fr, o, shutters, sh_key):
        trim = "stone_trim"
        low = o.y0 < 2.5
        if o.kind in ("door",) and o.arch <= 0:
            # door case: pilasters + hood (hood above 2.5 may project)
            fbox(mb, fr, o.s0 - 0.16, o.s0, 0.0 if o.y0 < 0.05 else o.y0, o.y1, 0.0, 0.06, trim, skip=("back",))
            fbox(mb, fr, o.s1, o.s1 + 0.16, 0.0 if o.y0 < 0.05 else o.y0, o.y1, 0.0, 0.06, trim, skip=("back",))
            fbox(mb, fr, o.s0 - 0.28, o.s1 + 0.28, o.y1, o.y1 + 0.22, 0.0, 0.3 if o.y1 > 2.45 else 0.12, trim, skip=("back",))
            return
        if o.kind == "shop":
            fbox(mb, fr, o.s0 - 0.14, o.s0, 0.0, o.y1 + 0.55, 0.0, 0.08, "detail", skip=("back",))
            fbox(mb, fr, o.s1, o.s1 + 0.14, 0.0, o.y1 + 0.55, 0.0, 0.08, "detail", skip=("back",))
            return
        if o.kind == "loading":
            fbox(mb, fr, o.s0 - 0.1, o.s1 + 0.1, o.y0 - 0.12, o.y0, -0.05, 0.12, trim, skip=("back",))
            return
        if o.arch > 0:
            # voussoir ring (0.05 proud) + keystone
            cs = 0.5 * (o.s0 + o.s1)
            r = 0.5 * (o.s1 - o.s0)
            ring = 0.22
            n = max(8, int(r * 6))
            for k in range(n):
                a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
                pa = [(cs - r * math.cos(a0), o.spring + r * math.sin(a0)), (cs - r * math.cos(a1), o.spring + r * math.sin(a1)),
                      (cs - (r + ring) * math.cos(a1), o.spring + (r + ring) * math.sin(a1)), (cs - (r + ring) * math.cos(a0), o.spring + (r + ring) * math.sin(a0))]
                mb.poly([fr.P(s, y, 0.05) for s, y in pa], trim, facing=fr.n)
                outer_edge = [fr.P(pa[3][0], pa[3][1], 0.0), fr.P(pa[2][0], pa[2][1], 0.0), fr.P(pa[2][0], pa[2][1], 0.05), fr.P(pa[3][0], pa[3][1], 0.05)]
                mx, my = 0.5 * (pa[2][0] + pa[3][0]) - cs, 0.5 * (pa[2][1] + pa[3][1]) - o.spring
                mb.poly(outer_edge, trim, facing=(fr.t[0] * mx, my, fr.t[2] * mx))
            fbox(mb, fr, cs - 0.13, cs + 0.13, o.y1 - 0.05, o.y1 + 0.32, 0.0, 0.09, trim, skip=("back",))
            if o.y0 > 0.3:
                fbox(mb, fr, o.s0 - 0.1, o.s1 + 0.1, o.y0 - 0.1, o.y0, -0.06, 0.1, trim, skip=("back",))
            return
        # rectangular window: architrave, sill, lintel/hood
        wj = 0.13
        fbox(mb, fr, o.s0 - wj, o.s0, o.y0, o.y1, 0.0, 0.05, trim, skip=("back",))
        fbox(mb, fr, o.s1, o.s1 + wj, o.y0, o.y1, 0.0, 0.05, trim, skip=("back",))
        hood = 0.12 if o.y1 < 2.5 else 0.2
        fbox(mb, fr, o.s0 - wj - 0.06, o.s1 + wj + 0.06, o.y1, o.y1 + 0.2, 0.0, hood, trim, skip=("back",))
        if o.kind != "balcony":
            fbox(mb, fr, o.s0 - wj - 0.05, o.s1 + wj + 0.05, o.y0 - 0.09, o.y0, -0.06, 0.1 if low else 0.13, trim, skip=("back",))
        if shutters:
            w = (o.s1 - o.s0) / 2
            for s0, s1 in ((o.s0 - wj - w - 0.02, o.s0 - wj - 0.02), (o.s1 + wj + 0.02, o.s1 + wj + w + 0.02)):
                fbox(mb, fr, s0, s1, o.y0, o.y1, 0.0, 0.04, "detail", skip=("back", "front"))
                u0, v0, u1, v1 = C.atlas_uv(self.atl, sh_key, inset_px=2)
                mb.poly([fr.P(s0, o.y0, 0.04), fr.P(s1, o.y0, 0.04), fr.P(s1, o.y1, 0.04), fr.P(s0, o.y1, 0.04)], "detail",
                        uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], facing=fr.n)

    def balcony(self, p, mb, fr, o):
        y = o.y0
        s0, s1 = o.s0 - 0.45, o.s1 + 0.45
        dep = 0.75
        fbox(mb, fr, s0, s1, y - 0.16, y, 0.0, dep, "stone_trim", skip=("back",))
        for sc in (s0 + 0.2, s1 - 0.2):
            # consoles under the slab (stay above 2.4 m: balconies only on upper floors)
            fbox(mb, fr, sc - 0.08, sc + 0.08, y - 0.5, y - 0.16, 0.0, dep * 0.7, "stone_trim", skip=("back",))
        iu = self.iron
        W, Hh = iu["size"]
        x, yy, w, h = iu["rects"]["balcony"]
        v1 = 1.0 - (yy + 2) / Hh
        v0 = 1.0 - (yy + h - 2) / Hh
        rh = 1.0
        segs = [((s0, dep), (s1, dep)), ((s0, 0.0), (s0, dep)), ((s1, dep), (s1, 0.0))]
        for (sa, da), (sb, db) in segs:
            ln = math.hypot(sb - sa, db - da)
            mb.poly([fr.P(sa, y, da), fr.P(sb, y, db), fr.P(sb, y + rh, db), fr.P(sa, y + rh, da)], "ironwork",
                    uv=[(0.0, v0), (ln / 2.0, v0), (ln / 2.0, v1), (0.0, v1)])

    def window_box(self, p, mb, fr, o):
        y = o.y0 - 0.1
        fbox(mb, fr, o.s0 - 0.05, o.s1 + 0.05, y - 0.26, y, 0.0, 0.26, "wood_planks", skip=("back",))
        fm = self.out.mb(p.chunk, "foliage_flowers")
        u0, v0, u1, v1 = C.atlas_uv(self.fol, "flowers", inset_px=4)
        for d in (0.08, 0.18):
            fm.poly([fr.P(o.s0 - 0.08, y - 0.05, d), fr.P(o.s1 + 0.08, y - 0.05, d), fr.P(o.s1 + 0.08, y + 0.42, d), fr.P(o.s0 - 0.08, y + 0.42, d)],
                    "foliage", uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])

    def shopfront(self, p, mb, fr, o, canvas, sign):
        # bulkhead below the glass, fascia board above, awning (lowest edge 2.5 m)
        fbox(mb, fr, o.s0, o.s1, 0.0, o.y0, -0.12, -0.02, "detail", skip=("back",))
        top = o.y1
        fbox(mb, fr, o.s0 - 0.14, o.s1 + 0.14, top, top + 0.55, 0.0, 0.1, "detail", skip=("back",))
        if sign:
            atlas_quad(mb, [fr.P(o.s0 + 0.2, top + 0.05, 0.101), fr.P(o.s0 + 0.62, top + 0.05, 0.101), fr.P(o.s0 + 0.62, top + 0.5, 0.101),
                            fr.P(o.s0 + 0.2, top + 0.5, 0.101)], self.atl, sign, fr.n)
        ay_top = max(3.35, top + 0.6)
        ay_low = 2.55
        dep = 0.95
        a0, a1 = o.s0 - 0.2, o.s1 + 0.2
        mb.poly([fr.P(a0, ay_low, dep), fr.P(a1, ay_low, dep), fr.P(a1, ay_top, 0.0), fr.P(a0, ay_top, 0.0)], canvas)
        mb.poly([fr.P(a0, ay_low - 0.0, dep), fr.P(a1, ay_low, dep), fr.P(a1, ay_low + 0.22, dep), fr.P(a0, ay_low + 0.22, dep)], canvas)
        for s_ in (a0, a1):
            mb.poly([fr.P(s_, ay_top, 0.0), fr.P(s_, ay_low, dep), fr.P(s_, ay_low + 0.22, dep)], canvas)

    def door_lamp(self, p, mb, fr, o):
        if o.y1 > p.g - 0.3:
            return
        s = o.s1 + 0.45
        y = max(3.0, o.y1 + 0.35)            # lantern bottom >= 2.58 m (headroom rule)
        fbox(mb, fr, s - 0.04, s + 0.04, y - 0.05, y + 0.05, 0.0, 0.32, "iron", skip=("back",))
        fbox(mb, fr, s - 0.13, s + 0.13, y - 0.42, y - 0.36, 0.14, 0.4, "iron", skip=())
        fbox(mb, fr, s - 0.15, s + 0.15, y - 0.06, y + 0.02, 0.12, 0.42, "iron", skip=())
        em = self.out.mb(p.chunk, "emissive_walllamps")
        em.fbox(fr.O, fr.t, fr.n, s - 0.11, s + 0.11, y - 0.36, y - 0.06, 0.16, 0.38, "emissive_lamp", skip=("bottom",))

    def hoist_beam(self, p, mb, fr, ln):
        sc = ln / 2
        y = p.H + p.rise * 0.55
        fbox(mb, fr, sc - 0.13, sc + 0.13, y, y + 0.3, 0.0, 1.1, "wood_planks", skip=("back",))
        fbox(mb, fr, sc - 0.1, sc + 0.1, y - 0.28, y, 0.85, 1.0, "iron")
        rope = [fr.P(sc, y - 0.28, 0.93), fr.P(sc + 0.02, y - 3.2, 0.95)]
        mb.tube(rope, 0.025, 5, "iron")
        fbox(mb, fr, sc - 0.12, sc + 0.12, y - 3.5, y - 3.2, 0.83, 1.07, "iron")

    def trims(self, p, mb, fr, side, cls, ln, openings, outer):
        H = p.H
        style = p.style
        trim = "stone_trim"
        exposed_spans = [(a - 0.25, b + 0.25) for a, b, k, _ in runs([(s, k) for s, k, _ in cls], lambda v: v) if k in ("floor", "water", "outer")]
        doors = [(o.s0 - 0.2, o.s1 + 0.2) for o in openings if o.kind in ("door",) or (o.kind == "shop")]
        if outer:
            fbox(mb, fr, 0.0, ln, H - 0.35, H, 0.0, 0.25, trim, skip=("back",))
            return
        for a, b in exposed_spans:
            a, b = max(0.0, a), min(ln, b)
            # plinth, interrupted at doors (0.05 proud)
            cuts = [a]
            for d0, d1 in sorted(doors):
                if d1 > a and d0 < b:
                    cuts += [max(a, d0), min(b, d1)]
            cuts.append(b)
            for i in range(0, len(cuts) - 1, 2):
                if cuts[i + 1] - cuts[i] > 0.1:
                    fbox(mb, fr, cuts[i], cuts[i + 1], 0.0, 0.5, 0.0, 0.05, p.S["base"], skip=("back",))
            # string course at the ground floor top (above 2.5 m -> may project)
            if style not in ("market_hall",):
                fbox(mb, fr, a, b, p.g - 0.12, p.g + 0.1, 0.0, 0.1, trim, skip=("back",))
            else:
                fbox(mb, fr, a, b, p.g + 0.3, p.g + 0.55, 0.0, 0.14, trim, skip=("back",))
            # cornice (stepped profile) at the eave
            if p.roof not in ("flat", "crenel", "tower"):
                fbox(mb, fr, a, b, H - 0.42, H - 0.24, 0.0, 0.12, trim, skip=("back",))
                fbox(mb, fr, a, b, H - 0.24, H - 0.02, 0.0, 0.3, trim, skip=("back",))
            # quoins at parcel corners (brick & plaster buildings)
            if style in ("townhouse", "canal_house", "warehouse") and p.wall.startswith("brick") or style == "townhouse":
                for sq in (0.0, ln):
                    if a - 0.3 <= sq <= b + 0.3:
                        y = p.g + 0.1 if style == "townhouse" and p.wall.startswith("plaster") else 0.62
                        k = 0
                        while y + 0.3 < H - 0.45:
                            wq = 0.5 if k % 2 == 0 else 0.32
                            s0, s1 = (0.0, wq) if sq == 0.0 else (ln - wq, ln)
                            fbox(mb, fr, s0, s1, y, y + 0.3, 0.0, 0.035, trim, skip=("back",))
                            y += 0.33
                            k += 1
            # pilasters for the market hall between bays
            if style == "market_hall":
                n_p = max(2, int(round(ln / 4.0)))
                for i in range(n_p + 1):
                    sc = 0.4 + (ln - 0.8) * i / n_p
                    fbox(mb, fr, sc - 0.32, sc + 0.32, 0.5, H - 0.45, 0.0, 0.12, trim, skip=("back",))
                fbox(mb, fr, a, b, H - 0.6, H - 0.02, 0.0, 0.38, trim, skip=("back",))
                for i in range(int(ln / 0.8)):
                    sc = 0.4 + i * 0.8
                    fbox(mb, fr, sc - 0.07, sc + 0.07, H - 0.82, H - 0.6, 0.0, 0.3, trim, skip=("back",))
            # downpipes at the face ends (<= 0.14 proud) for pitched roofs
            if p.roof in ("gable", "gable_front", "hip") and style != "market_hall":
                for sq in (0.18, ln - 0.18):
                    if a <= sq <= b and not self.near_door(sq, openings):
                        P0 = fr.P(sq, 0.02, 0.08)
                        P1 = fr.P(sq, H - 0.3, 0.08)
                        mb.cylinder(M_translate(P0[0], P0[1], P0[2]), 0.055, P1[1] - P0[1], 6, "iron", cap_top=False)
        # ivy (restrained): on some canal-house / townhouse corners
        rng = random.Random(hash_str(p.solid["id"]) + ord(side) * 13 + p.idx)
        if style in ("canal_house", "townhouse", "warehouse") and rng.random() < 0.16 and ln > 4:
            w = rng.uniform(2.4, 3.6)
            sq = 0.05 if rng.random() < 0.5 else ln - w - 0.05
            base = min((lvl for _, k, lvl in cls if k == "floor"), default=0.0)
            if not any(o.kind in ("door", "shop") and o.s0 < sq + w + 0.3 and o.s1 > sq - 0.3 for o in openings):
                self.ivy(p, fr, sq, sq + w, base, base + min(2.0 * w, H - 0.8))

    @staticmethod
    def near_door(s, openings):
        return any(o.kind in ("door", "shop") and o.s0 - 0.35 < s < o.s1 + 0.35 for o in openings)

    def ivy(self, p, fr, s0, s1, y_lo, y_hi, d=0.04):
        fm = self.out.mb(p.chunk, "foliage_ivy")
        u0, v0, u1, v1 = C.atlas_uv(self.fol, "ivy", inset_px=4)
        # climbing ivy rooted at the ground, flush on the wall (0.04 m, inside the face tolerance)
        fm.poly([fr.P(s0, y_lo, d), fr.P(s1, y_lo, d), fr.P(s1, y_hi, d), fr.P(s0, y_hi, d)], "foliage",
                uv=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])

    # ------------------------------------------------------------------ gables
    def stepped_gable(self, p, mb, fr, ln):
        H, rise = p.H, p.rise
        n = 5
        sw = (ln / 2) / (n + 0.5)
        extra = 0.45
        thick = 0.35
        trim = "stone_trim"
        mat = p.wall
        strips = []
        for i in range(n):
            s0 = i * sw
            top = H + (i + 1) * sw * math.tan(p.pitch) + extra
            strips.append((s0, s0 + sw, top))
            strips.append((ln - s0 - sw, ln - s0, top))
        c0, c1 = n * sw, ln - n * sw
        strips.append((c0, c1, H + rise + extra + 0.5))
        for s0, s1, top in strips:
            mb.poly([fr.P(s0, H), fr.P(s1, H), fr.P(s1, top), fr.P(s0, top)], mat, facing=fr.n)
            fbox(mb, fr, s0 - 0.04, s1 + 0.04, top, top + 0.12, -thick - 0.04, 0.05, trim)
        # step risers (sides) + back faces above the roof
        for s0, s1, top in strips:
            for s, fc in ((s0, (-fr.t[0], 0, -fr.t[2])), (s1, fr.t)):
                mb.poly([fr.P(s, H, 0), fr.P(s, H, -thick), fr.P(s, top, -thick), fr.P(s, top, 0)], mat, facing=fc)
            mb.poly([fr.P(s1, H, -thick), fr.P(s0, H, -thick), fr.P(s0, top, -thick), fr.P(s1, top, -thick)], mat,
                    facing=(-fr.n[0], 0, -fr.n[2]))
        # finial on the top step + small gable window
        cs = ln / 2
        topc = H + rise + extra + 0.62
        mb.box(*self._ctr(fr, cs, topc, 0.16, 0.5), trim)
        o = Opening(cs - 0.4, cs + 0.4, H + rise * 0.28, H + rise * 0.28 + 1.1, arch=0.4, depth=0.1, key="win_dormer")
        glass(mb, fr, o, self.atl, "win_round", d=0.02)
        # hoist beam (canal houses)
        yb = H + rise * 0.72
        fbox(mb, fr, cs - 0.1, cs + 0.1, yb, yb + 0.22, 0.0, 0.8, "wood_planks", skip=("back",))

    def _ctr(self, fr, s, y, w, h):
        x, z = fr.at(s, -0.18)
        return (x - w / 2, y, z - w / 2, x + w / 2, y + h, z + w / 2)

    def gable_details(self, p, mb, fr, ln):
        # round window in townhouse/warehouse gables
        if p.rise < 1.4:
            return
        cs = ln / 2
        rr = min(0.45, p.rise * 0.22)
        yc = p.H + p.rise * 0.38
        o = Opening(cs - rr, cs + rr, yc - rr, yc + rr, depth=0.05, key="win_round")
        glass(mb, fr, o, self.atl, "win_round", d=0.03)
        fbox(mb, fr, cs - rr - 0.08, cs + rr + 0.08, yc - rr - 0.1, yc - rr, 0.0, 0.08, "stone_trim", skip=("back",))

    # ------------------------------------------------------------------ passages (gatehouse / yard gate)
    def passage_face(self, p, mb, fr, side, cls):
        r = p.r
        H = p.H
        across = (p.long_axis == "x" and side in ("n", "s")) or (p.long_axis == "z" and side in ("e", "w"))
        rows = self.rows_for(p)
        if not across:
            return   # side faces are the neighbours' walls
        L = fr.L
        rad = L / 2.0
        spring = 2.6
        # each face carries half of the vault so the two halves meet mid-passage (no duplicate surfaces)
        o = Opening(0.0, L, 0.0, spring + rad, arch=rad, depth=0.5 * (r.d if p.long_axis == "x" else r.w), through=True, kind="passage")
        wall_with_openings(mb, fr, 0.0, H, [o], rows)
        # voussoirs + keystone
        self.surround(p, mb, fr, Opening(0.0, L, 0.0, spring + rad, arch=rad, depth=0.0, kind="win"), False, None)
        # impost bands of the neighbouring faces stop at the voussoirs (no band across the opening)
        # sign over the gate (lane/north_row side only)
        kind0 = [k for _, k, _ in cls]
        if p.style == "warehouse_gate" and side == "w":
            atlas_quad(mb, [fr.P(L / 2 - 2.2, spring + rad + 0.5, 0.06), fr.P(L / 2 + 2.2, spring + rad + 0.5, 0.06),
                            fr.P(L / 2 + 2.2, spring + rad + 1.05, 0.06), fr.P(L / 2 - 2.2, spring + rad + 1.05, 0.06)],
                       self.atl, "sign_yard", fr.n)
        if p.style == "gatehouse":
            spawn_side = (side == "n") if r.cz < 0 else (side == "s")
            if spawn_side:
                atlas_quad(mb, [fr.P(L / 2 - 1.1, spring + rad + 0.45, 0.06), fr.P(L / 2 + 1.1, spring + rad + 0.45, 0.06),
                                fr.P(L / 2 + 1.1, spring + rad + 1.0, 0.06), fr.P(L / 2 - 1.1, spring + rad + 1.0, 0.06)],
                           self.atl, "sign_north_row", fr.n)
            else:
                atlas_quad(mb, [fr.P(L / 2 - 0.5, spring + rad + 0.4, 0.06), fr.P(L / 2 + 0.5, spring + rad + 0.4, 0.06),
                                fr.P(L / 2 + 0.5, spring + rad + 1.4, 0.06), fr.P(L / 2 - 0.5, spring + rad + 1.4, 0.06)],
                           self.atl, "sign_emblem", fr.n)
            # lanterns on both jambs (bottom above 2.5 m)
            for sj in (-0.45, L + 0.45):
                em = self.out.mb(p.chunk, "emissive_walllamps")
                em.fbox(fr.O, fr.t, fr.n, sj - 0.11, sj + 0.11, 2.75, 3.05, 0.16, 0.38, "emissive_lamp", skip=("bottom",))
                mb.fbox(fr.O, fr.t, fr.n, sj - 0.04, sj + 0.04, 3.05, 3.15, 0.0, 0.32, "iron", skip=("back",))
                mb.fbox(fr.O, fr.t, fr.n, sj - 0.15, sj + 0.15, 3.05, 3.12, 0.12, 0.42, "iron")
                mb.fbox(fr.O, fr.t, fr.n, sj - 0.13, sj + 0.13, 2.68, 2.75, 0.14, 0.4, "iron")

    # ------------------------------------------------------------------ roofs
    def build_roof(self, p, mb, exp):
        r = p.r
        H = p.H
        if p.passage:
            self.flat_top(p, mb, exp, crenel=(p.style == "gatehouse"))
            return
        roof = p.roof
        if roof == "flat":
            self.flat_top(p, mb, exp, crenel=False)
        elif roof == "crenel":
            self.flat_top(p, mb, exp, crenel=True)
        elif roof == "tower":
            self.tower_top(p, mb, exp)
        elif roof == "hip":
            self.hip_roof(p, mb, exp)
        else:
            self.gable_roof(p, mb, exp)
        self.chimneys(p, mb)

    def ovh(self, p, exp, side, eave=True):
        kinds = [k for _, k, _ in exp[side][0]]
        if all(k == "building" for k in kinds):
            return 0.0
        if p.S.get("stepped") and not eave:
            return -0.2
        return 0.42 if eave else 0.28

    def gable_roof(self, p, mb, exp):
        r = p.r
        H, rise = p.H, p.rise
        tp = math.tan(p.pitch)
        th = 0.16
        mat = "roof_terracotta"
        if p.ridge == "x":
            eo_n, eo_s = self.ovh(p, exp, "n"), self.ovh(p, exp, "s")
            go_w, go_e = self.ovh(p, exp, "w", False), self.ovh(p, exp, "e", False)
            xa, xb = r.x0 - go_w, r.x1 + go_e
            zc = r.cz
            yr = H + rise
            pS = [(xa, H - eo_s * tp, r.z1 + eo_s), (xb, H - eo_s * tp, r.z1 + eo_s), (xb, yr, zc), (xa, yr, zc)]
            pN = [(xb, H - eo_n * tp, r.z0 - eo_n), (xa, H - eo_n * tp, r.z0 - eo_n), (xa, yr, zc), (xb, yr, zc)]
            self.roof_slab(mb, pS, mat, th, (0.0, 1.0, tp))
            self.roof_slab(mb, pN, mat, th, (0.0, 1.0, -tp))
            ridge = [(xa, yr + 0.02, zc), (xb, yr + 0.02, zc)]
            self.gutter(mb, (xa, H - eo_s * tp, r.z1 + eo_s), (xb, H - eo_s * tp, r.z1 + eo_s), eo_s)
            self.gutter(mb, (xa, H - eo_n * tp, r.z0 - eo_n), (xb, H - eo_n * tp, r.z0 - eo_n), eo_n)
        else:
            eo_w, eo_e = self.ovh(p, exp, "w"), self.ovh(p, exp, "e")
            go_n, go_s = self.ovh(p, exp, "n", False), self.ovh(p, exp, "s", False)
            za, zb = r.z0 - go_n, r.z1 + go_s
            xc = r.cx
            yr = H + rise
            pE = [(r.x1 + eo_e, H - eo_e * tp, zb), (r.x1 + eo_e, H - eo_e * tp, za), (xc, yr, za), (xc, yr, zb)]
            pW = [(r.x0 - eo_w, H - eo_w * tp, za), (r.x0 - eo_w, H - eo_w * tp, zb), (xc, yr, zb), (xc, yr, za)]
            self.roof_slab(mb, pE, mat, th, (tp, 1.0, 0.0))
            self.roof_slab(mb, pW, mat, th, (-tp, 1.0, 0.0))
            ridge = [(xc, yr + 0.02, za), (xc, yr + 0.02, zb)]
            self.gutter(mb, (r.x1 + eo_e, H - eo_e * tp, za), (r.x1 + eo_e, H - eo_e * tp, zb), eo_e)
            self.gutter(mb, (r.x0 - eo_w, H - eo_w * tp, za), (r.x0 - eo_w, H - eo_w * tp, zb), eo_w)
        mb.tube(ridge, 0.13, 6, mat)

    def roof_slab(self, mb, top, mat, th, nrm):
        """top: quad (eave edge a->b, ridge edge c->d) CCW seen from above. Adds underside + edges."""
        ln = math.sqrt(nrm[0] ** 2 + nrm[1] ** 2 + nrm[2] ** 2)
        n = (nrm[0] / ln, nrm[1] / ln, nrm[2] / ln)
        mb.poly(top, mat, facing=n)
        bot = [(x - n[0] * th, y - n[1] * th, z - n[2] * th) for x, y, z in top]
        mb.poly(bot, "wood_planks", facing=(-n[0], -n[1], -n[2]))
        m = len(top)
        for i in range(m):
            a, b = top[i], top[(i + 1) % m]
            a2, b2 = bot[i], bot[(i + 1) % m]
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
            cen = (sum(p[0] for p in top) / m, sum(p[1] for p in top) / m, sum(p[2] for p in top) / m)
            outward = (mid[0] - cen[0], 0.0, mid[2] - cen[2])
            if abs(outward[0]) + abs(outward[2]) < 1e-6:
                outward = (0.0, 1.0, 0.0)
            mb.poly([a2, b2, b, a], "wood_planks", facing=outward)

    def gutter(self, mb, a, b, ovh):
        if ovh <= 0.05:
            return
        y = a[1] - 0.06
        mb.tube([(a[0], y, a[2]), (b[0], y, b[2])], 0.07, 5, "iron")

    def hip_roof(self, p, mb, exp):
        r = p.r
        H = p.H
        tp = math.tan(p.pitch)
        o = 0.5
        x0, x1, z0, z1 = r.x0 - o, r.x1 + o, r.z0 - o, r.z1 + o
        ye = H - o * tp
        w, d = x1 - x0, z1 - z0
        hd = min(w, d) / 2
        yr = ye + hd * tp
        mat = "roof_terracotta"
        if w >= d:
            ra, rb = (x0 + hd, yr, r.cz), (x1 - hd, yr, r.cz)
            self.roof_slab(mb, [(x0, ye, z1), (x1, ye, z1), rb, ra], mat, 0.16, (0.0, 1.0, tp))
            self.roof_slab(mb, [(x1, ye, z0), (x0, ye, z0), ra, rb], mat, 0.16, (0.0, 1.0, -tp))
            self.roof_slab(mb, [(x1, ye, z1), (x1, ye, z0), rb], mat, 0.16, (tp, 1.0, 0.0))
            self.roof_slab(mb, [(x0, ye, z0), (x0, ye, z1), ra], mat, 0.16, (-tp, 1.0, 0.0))
            mb.tube([(ra[0], yr + 0.02, ra[2]), (rb[0], yr + 0.02, rb[2])], 0.14, 6, mat)
            for c, rr_ in (((x0, ye, z0), ra), ((x0, ye, z1), ra), ((x1, ye, z0), rb), ((x1, ye, z1), rb)):
                mb.tube([(c[0], c[1] + 0.02, c[2]), (rr_[0], rr_[1] + 0.02, rr_[2])], 0.12, 6, mat)
        else:
            ra, rb = (r.cx, yr, z0 + hd), (r.cx, yr, z1 - hd)
            self.roof_slab(mb, [(x1, ye, z1), (x1, ye, z0), ra, rb], mat, 0.16, (tp, 1.0, 0.0))
            self.roof_slab(mb, [(x0, ye, z0), (x0, ye, z1), rb, ra], mat, 0.16, (-tp, 1.0, 0.0))
            self.roof_slab(mb, [(x0, ye, z1), (x1, ye, z1), rb], mat, 0.16, (0.0, 1.0, tp))
            self.roof_slab(mb, [(x1, ye, z0), (x0, ye, z0), ra], mat, 0.16, (0.0, 1.0, -tp))
            mb.tube([(ra[0], yr + 0.02, ra[2]), (rb[0], yr + 0.02, rb[2])], 0.14, 6, mat)
        for side, (a, b) in (("s", ((x0, ye, z1), (x1, ye, z1))), ("n", ((x0, ye, z0), (x1, ye, z0))),
                             ("e", ((x1, ye, z0), (x1, ye, z1))), ("w", ((x0, ye, z0), (x0, ye, z1)))):
            self.gutter(mb, a, b, o)
        if p.style == "market_hall":
            self.cupola(p, mb, (r.cx, yr - 0.4, r.cz))

    def cupola(self, p, mb, base):
        x, y, z = base
        M = M_translate(x, y, z)
        mb.lathe([(1.9, 0.0), (1.9, 0.5), (1.7, 0.5), (1.7, 3.0), (1.95, 3.1), (1.95, 3.35)], 8, "stone_ashlar", M=M, cap_top=False, smooth=False)
        # arched openings painted via atlas on the drum
        for k in range(8):
            a = 2 * math.pi * (k + 0.5) / 8
            cx, cz = x + math.cos(a) * 1.72, z - math.sin(a) * 1.72
            t = (-math.sin(a), 0.0, -math.cos(a))
            nrm = (math.cos(a), 0.0, -math.sin(a))
            w, h = 0.55, 1.9
            pts = [(cx - t[0] * w + nrm[0] * 0.01, y + 0.7, cz - t[2] * w + nrm[2] * 0.01),
                   (cx + t[0] * w + nrm[0] * 0.01, y + 0.7, cz + t[2] * w + nrm[2] * 0.01),
                   (cx + t[0] * w + nrm[0] * 0.01, y + 0.7 + h, cz + t[2] * w + nrm[2] * 0.01),
                   (cx - t[0] * w + nrm[0] * 0.01, y + 0.7 + h, cz - t[2] * w + nrm[2] * 0.01)]
            atlas_quad(mb, pts, self.atl, "win_arch", nrm)
        prof = [(1.95, 3.35)]
        for i in range(1, 9):
            a = (math.pi / 2) * i / 8
            prof.append((1.95 * math.cos(a) + 0.001, 3.35 + 1.9 * math.sin(a)))
        mb.lathe(prof, 16, "bronze", M=M, cap_top=False, smooth=True)
        mb.lathe([(0.12, 5.2), (0.2, 5.5), (0.06, 6.1), (0.0, 6.4)], 8, "bronze", M=M, cap_top=False, smooth=True)

    def flat_top(self, p, mb, exp, crenel=False):
        r = p.r
        H = p.H
        # roof deck slightly below the parapet top
        mb.quad((r.x0, H, r.z1), (r.x1, H, r.z1), (r.x1, H, r.z0), (r.x0, H, r.z0), "concrete", facing=UP)
        ph = 1.0
        for side in ("n", "s", "e", "w"):
            kinds = [k for _, k, _ in exp[side][0]]
            if all(k == "building" for k in kinds):
                continue
            if p.passage and not ((p.long_axis == "x" and side in ("n", "s")) or (p.long_axis == "z" and side in ("e", "w"))):
                continue
            fr = self.face_frame(r, side)
            mx, mz = fr.at(fr.L / 2, 0.3)
            if any(q.passage and q.r.inside(mx, mz) for q in self.parcels):
                continue
            L = fr.L
            mb.poly([fr.P(0, H), fr.P(L, H), fr.P(L, H + ph), fr.P(0, H + ph)], p.wall, facing=fr.n)
            mb.poly([fr.P(L, H, -0.3), fr.P(0, H, -0.3), fr.P(0, H + ph, -0.3), fr.P(L, H + ph, -0.3)], p.wall,
                    facing=(-fr.n[0], 0, -fr.n[2]))
            fbox(mb, fr, 0.0, L, H - 0.35, H - 0.05, 0.0, 0.22, "stone_trim", skip=("back",))
            if crenel:
                n = max(2, int(L / 1.3))
                for i in range(n):
                    s0 = L * i / n
                    s1 = s0 + L / n * 0.55
                    fbox(mb, fr, s0, s1, H + ph, H + ph + 0.65, -0.32, 0.02, p.wall)
                    fbox(mb, fr, s0 - 0.02, s1 + 0.02, H + ph + 0.65, H + ph + 0.75, -0.34, 0.04, "stone_trim")
                fbox(mb, fr, -0.02, L + 0.02, H + ph - 0.08, H + ph, -0.34, 0.04, "stone_trim", skip=("bottom",))
            else:
                fbox(mb, fr, -0.03, L + 0.03, H + ph, H + ph + 0.12, -0.34, 0.06, "stone_trim")

    def tower_top(self, p, mb, exp):
        r = p.r
        H = p.H
        # stone tower body continues from the gatehouse top; pyramid roof + clock faces
        o = 0.45
        tp = math.tan(math.radians(52))
        x0, x1, z0, z1 = r.x0 - o, r.x1 + o, r.z0 - o, r.z1 + o
        ye = H
        w, d = x1 - x0, z1 - z0
        hd = min(w, d) / 2
        yr = ye + hd * tp
        mat = "roof_terracotta"
        if w >= d:
            ra, rb = (x0 + hd, yr, r.cz), (x1 - hd, yr, r.cz)
            self.roof_slab(mb, [(x0, ye, z1), (x1, ye, z1), rb, ra], mat, 0.16, (0.0, 1.0, tp))
            self.roof_slab(mb, [(x1, ye, z0), (x0, ye, z0), ra, rb], mat, 0.16, (0.0, 1.0, -tp))
            self.roof_slab(mb, [(x1, ye, z1), (x1, ye, z0), rb], mat, 0.16, (tp, 1.0, 0.0))
            self.roof_slab(mb, [(x0, ye, z0), (x0, ye, z1), ra], mat, 0.16, (-tp, 1.0, 0.0))
            mb.tube([(ra[0], yr, ra[2]), (rb[0], yr, rb[2])], 0.12, 6, mat)
        for side in ("n", "s"):
            fr = self.face_frame(r, side)
            fbox(mb, fr, -0.05, fr.L + 0.05, H - 0.5, H, 0.0, 0.3, "stone_trim", skip=("back",))
            cs = fr.L / 2
            atlas_quad(mb, [fr.P(cs - 0.9, H - 2.6, 0.06), fr.P(cs + 0.9, H - 2.6, 0.06), fr.P(cs + 0.9, H - 0.8, 0.06),
                            fr.P(cs - 0.9, H - 0.8, 0.06)], self.atl, "clock", fr.n)
            fbox(mb, fr, cs - 1.05, cs + 1.05, H - 2.75, H - 0.65, 0.0, 0.05, "stone_trim", skip=("back", "front"))
        # finial
        mb.lathe([(0.1, 0.0), (0.18, 0.3), (0.05, 1.0), (0.0, 1.4)], 8, "bronze", M=M_translate(r.cx, yr, r.cz), cap_top=False)
        # banners on the tower faces (banner_* cloth, two-sided), flanking the clock
        bm = self.out.mb(p.chunk, "banner_gatehouse")
        for side in ("n", "s"):
            fr = self.face_frame(r, side)
            cs = fr.L / 2
            for off in (-2.4, 2.4):
                s0_, s1_ = cs + off - 0.7, cs + off + 0.7
                y1_, y0_ = H - 1.0, H - 1.0 - 2.8
                mb.fbox(fr.O, fr.t, fr.n, s0_ - 0.15, s1_ + 0.15, y1_, y1_ + 0.08, 0.0, 0.2, "iron")
                bm.poly([fr.P(s0_, y0_, 0.12), fr.P(s1_, y0_, 0.12), fr.P(s1_, y1_, 0.12), fr.P(s0_, y1_, 0.12)], "banner",
                        uv=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], facing=fr.n)

    def chimneys(self, p, mb):
        if p.style not in ("townhouse", "canal_house") or p.passage or p.roof not in ("gable", "gable_front"):
            return
        rng = random.Random(hash_str(p.solid["id"]) * 3 + p.idx)
        r = p.r
        n = 1 if rng.random() < 0.6 else 2
        for i in range(n):
            if p.ridge == "x":
                x = rng.uniform(r.x0 + 1.0, r.x1 - 1.0)
                z = r.cz + rng.choice((-1, 1)) * rng.uniform(0.2, 1.2)
            else:
                z = rng.uniform(r.z0 + 1.0, r.z1 - 1.0)
                x = r.cx + rng.choice((-1, 1)) * rng.uniform(0.2, 1.2)
            self.chimney(mb, x, z, p.H + p.rise + rng.uniform(0.5, 1.2), p.H)

    def chimney(self, mb, x, z, top, bottom, mat="brick_red"):
        w, d = 0.85, 0.6
        mb.box(x - w / 2, bottom, z - d / 2, x + w / 2, top, z + d / 2, mat, skip=("bottom",))
        mb.box(x - w / 2 - 0.08, top, z - d / 2 - 0.08, x + w / 2 + 0.08, top + 0.14, z + d / 2 + 0.08, "stone_trim", skip=("bottom",))
        for k in (-1, 1):
            mb.cylinder(M_translate(x + k * 0.2, top + 0.14, z), 0.1, 0.4, 8, "roof_terracotta", cap_top=True)
        self.chimney_tops.append((x, top + 0.55, z))


def hash_str(s: str) -> int:
    h = 2166136261
    for ch in s:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h
