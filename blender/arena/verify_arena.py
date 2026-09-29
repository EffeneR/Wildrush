"""Geometric verification of the built Briarport art against the layout JSON (Blender).

Run inside build_arena.py (verify(log)) or standalone:
    blender -b blender/arena/briarport.blend -t 2 --python-exit-code 1 --python blender/arena/verify_arena.py

Checks (ENVIRONMENT_CONTRACT.md):
  floor_tops   visual walkable top within +-0.03 m of every floor top (1 m grid, raycast down)
  ramps        metal ramp surface on the ramp line; stair nosings on the ramp line (+-0.03)
  headroom     nothing (non-decor) below 2.4 m over walkable floor outside solid footprints
  solid_faces  visual surface within +-0.15 m of solid box faces up to 2.5 m (horizontal rays)
  zones        no decor clutter inside the 9 m scoring circles (0.25-4 m above the floor)
  specials     water_* per layout water rect at its y, puddle_* count, emit_smoke_* at the layout points
  budgets      <= 1.2 M triangles, <= 40 materials
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import common as C  # noqa: E402

TOL_FLOOR = 0.03
TOL_FACE = 0.15
HEADROOM = 2.4

DECOR_PREFIX = ("lamp_post", "emissive_", "lantern", "banner_", "boat_", "barrel_group", "pallet_stack", "forklift",
                "crane", "water_", "KIT_")
FOLIAGE_PREFIX = ("foliage_",)


def L2B(x, y, z):
    return Vector((x, -z, y))


def B2L(v):
    return (v.x, v.z, -v.y)


def chunk_mesh_objects():
    out = []
    for ch in C.CHUNKS:
        col = bpy.data.collections.get("chunk_" + ch)
        if col is None:
            continue
        for o in col.all_objects:
            if o.type == "MESH":
                out.append((ch, o))
    return out


def is_decor(o):
    return o.name.startswith(DECOR_PREFIX)


def is_foliage(o):
    return o.name.startswith(FOLIAGE_PREFIX) or "_foliage_" in o.name


def build_bvh(objs):
    verts, polys = [], []
    owner = []
    for o in objs:
        mw = o.matrix_world
        base = len(verts)
        me = o.data
        verts.extend(mw @ v.co for v in me.vertices)
        for p in me.polygons:
            polys.append([base + i for i in p.vertices])
            owner.append(o.name)
    if not polys:
        return None, owner
    return BVHTree.FromPolygons(verts, polys, all_triangles=False), owner


class Verifier:
    def __init__(self, log=print):
        self.log = log
        self.L = C.Layout()
        objs = chunk_mesh_objects()
        self.objs = objs
        arch = [o for ch, o in objs if ch != "skyline" and not is_decor(o) and not is_foliage(o)]
        head = [o for ch, o in objs if ch != "skyline" and not is_decor(o)]
        self.bvh_arch, self.own_arch = build_bvh(arch)
        self.bvh_head, self.own_head = build_bvh(head)
        self.fail = {}
        self.stats = {}
        self.overlaps = set()

    def err(self, check, msg):
        self.fail.setdefault(check, []).append(msg)

    def ray(self, bvh, owner, o, d, dist):
        loc, nrm, idx, dd = bvh.ray_cast(L2B(*o), Vector((d[0], -d[2], d[1])), dist)
        if loc is None:
            return None, None
        return dd, owner[idx]

    def inside_solid(self, x, z, pad=0.3, y=None):
        for s in self.L.solids:
            if not s["collide"]:
                continue
            r = s["rect"]
            if y is not None and not (s["y0"] - 0.05 <= y <= s["y1"]):
                continue
            if r.x0 - pad <= x <= r.x1 + pad and r.z0 - pad <= z <= r.z1 + pad:
                return True
        return False

    def on_ramp(self, x, z, pad=0.3):
        for r in self.L.ramps:
            for dx, dz in ((0, 0), (pad, 0), (-pad, 0), (0, pad), (0, -pad)):
                if self.L.ramp_height(r, x + dx, z + dz) is not None:
                    return True
        return False

    # ------------------------------------------------------------------ floors + headroom
    def floor_samples(self, f, step=1.0, inset=0.3):
        r = f["rect"]
        nx = max(1, int((r.w - 2 * inset) / step) + 1)
        nz = max(1, int((r.d - 2 * inset) / step) + 1)
        for i in range(nx):
            for j in range(nz):
                x = r.x0 + inset + (r.w - 2 * inset) * (i / max(1, nx - 1) if nx > 1 else 0.5)
                z = r.z0 + inset + (r.d - 2 * inset) * (j / max(1, nz - 1) if nz > 1 else 0.5)
                yield x, z

    def check_floors(self):
        n = worst = 0
        worst_at = None
        n_head = 0
        for f in self.L.floors:
            if f["is_bed"]:
                continue
            top = f["top"]
            for x, z in self.floor_samples(f):
                g = self.L.ground_at(x, z)
                if g is None or abs(g - top) > 1e-6:
                    continue          # covered by a higher floor (e.g. terrace over deck)
                if self.inside_solid(x, z, y=top + 0.3) or self.on_ramp(x, z):
                    continue
                d, who = self.ray(self.bvh_arch, self.own_arch, (x, top + 2.3, z), (0, -1, 0), 3.0)
                n += 1
                if d is None:
                    self.err("floor_tops", f"{f['id']} ({x:.2f},{z:.2f}): no surface below")
                    continue
                y = top + 2.3 - d
                e = y - top
                if abs(e) > abs(worst):
                    worst, worst_at = e, (f["id"], round(x, 2), round(z, 2), who)
                if abs(e) > TOL_FLOOR:
                    self.err("floor_tops", f"{f['id']} ({x:.2f},{z:.2f}): top {y:.3f} vs {top:.3f} ({who})")
                # headroom: nothing below 2.4 m above this floor point (incl. foliage)
                d2, who2 = self.ray(self.bvh_head, self.own_head, (x, top + 0.05, z), (0, 1, 0), HEADROOM - 0.05)
                n_head += 1
                if d2 is not None:
                    self.err("headroom", f"{f['id']} ({x:.2f},{z:.2f}): {who2} at {top + 0.05 + d2:.2f} m")
        self.stats["floor_samples"] = n
        self.stats["floor_worst_err_m"] = round(worst, 4)
        self.stats["floor_worst_at"] = worst_at
        self.stats["headroom_samples"] = n_head

    def check_ramps(self):
        worst = 0.0
        for r in self.L.ramps:
            ax, ay, az = r["from"]
            bx, by, bz = r["to"]
            Ln = math.hypot(bx - ax, bz - az)
            tx, tz = (bx - ax) / Ln, (bz - az) / Ln
            nx, nz = tz, -tx
            w = r["width"] / 2
            if r["kind"] == "stairs":
                N = max(2, int(round((by - ay) / 0.17)))
                for k in range(1, N + 1):
                    t = min(Ln * k / N + 0.02, Ln - 0.01) if k < N else Ln + 0.05
                    for s in (-w + 0.4, 0.0, w - 0.4):
                        x, z = ax + tx * t + nx * s, az + tz * t + nz * s
                        line = ay + (by - ay) * min(Ln * k / N, Ln) / Ln
                        d, who = self.ray(self.bvh_arch, self.own_arch, (x, line + 2.0, z), (0, -1, 0), 3.0)
                        if d is None:
                            self.err("ramps", f"{r['id']} nosing {k}: no surface")
                            continue
                        e = (line + 2.0 - d) - line
                        worst = max(worst, abs(e))
                        if abs(e) > TOL_FLOOR:
                            self.err("ramps", f"{r['id']} nosing {k} s={s:.1f}: {e:+.3f} m off the ramp line ({who})")
            else:
                for i in range(1, 10):
                    t = Ln * i / 10
                    for s in (-w + 0.1, 0.0, w - 0.1):
                        x, z = ax + tx * t + nx * s, az + tz * t + nz * s
                        line = ay + (by - ay) * t / Ln
                        if self.inside_solid(x, z, pad=0.05, y=line + 0.2):
                            self.overlaps.add(r["id"])
                            continue
                        d, who = self.ray(self.bvh_arch, self.own_arch, (x, line + 2.0, z), (0, -1, 0), 3.0)
                        if d is None:
                            self.err("ramps", f"{r['id']} t={t:.1f}: no surface")
                            continue
                        e = (line + 2.0 - d) - line
                        worst = max(worst, abs(e))
                        if abs(e) > TOL_FLOOR:
                            self.err("ramps", f"{r['id']} t={t:.1f} s={s:.1f}: {e:+.3f} m ({who})")
        self.stats["ramp_worst_err_m"] = round(worst, 4)

    # ------------------------------------------------------------------ solid faces
    def check_solids(self):
        n = 0
        worst = 0.0
        for s in self.L.solids:
            if not s["collide"]:
                continue
            r = s["rect"]
            y0, y1 = s["y0"], s["y1"]
            kind = s["kind"]
            if s.get("shape") == "cylinder":
                R = s.get("radius", r.w / 2)
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    ox, oz = r.cx + math.cos(a) * (R + 0.5), r.cz - math.sin(a) * (R + 0.5)
                    g = self.L.ground_at(ox, oz)
                    if kind == "fountain_statue":
                        g = 0.6            # stands in the basin: players can only reach it from the basin top
                    if g is None:
                        continue
                    for h in (0.15, 0.45, 1.0, 1.8, 2.45):
                        yy = max(g, y0) + h
                        if yy > y1 - 0.02 or yy > max(g, y0) + 2.5:
                            continue
                        if kind == "fountain_statue" and yy < 0.65:
                            continue
                        start = (ox, yy, oz)
                        dd, who = self.ray(self.bvh_arch, self.own_arch, start, (-math.cos(a), 0, math.sin(a)), 1.1)
                        n += 1
                        e = (dd - 0.5) if dd is not None else 9.9
                        worst = max(worst, abs(e)) if abs(e) < 9 else worst
                        if dd is None or abs(e) > TOL_FACE:
                            self.err("solid_faces", f"{s['id']} ang={math.degrees(a):.0f} y={yy:.2f}: "
                                                    f"{'no hit' if dd is None else f'{e:+.2f} m'} ({who})")
                continue
            for side in ("n", "s", "e", "w"):
                if side == "s":
                    p0, t, nrm, ln = (r.x0, r.z1), (1, 0), (0, 1), r.w
                elif side == "n":
                    p0, t, nrm, ln = (r.x1, r.z0), (-1, 0), (0, -1), r.w
                elif side == "e":
                    p0, t, nrm, ln = (r.x1, r.z1), (0, -1), (1, 0), r.d
                else:
                    p0, t, nrm, ln = (r.x0, r.z0), (0, 1), (-1, 0), r.d
                inset = 0.35 if ln > 0.9 else ln / 2
                m = max(1, int((ln - 2 * inset) / 0.5) + 1)
                for i in range(m):
                    sl = inset + (ln - 2 * inset) * (i / (m - 1) if m > 1 else 0.5)
                    fx, fz = p0[0] + t[0] * sl, p0[1] + t[1] * sl
                    ox, oz = fx + nrm[0] * 0.5, fz + nrm[1] * 0.5
                    g = self.L.ground_at(ox, oz)
                    if g is None or self.inside_solid(ox, oz, pad=0.0, y=g + 0.3):
                        continue
                    if self.on_ramp(ox, oz, pad=0.0):
                        continue
                    # corners where another solid meets this face: neighbour details are legitimate
                    if any(self.inside_solid(fx + nrm[0] * 0.2 + t[0] * k, fz + nrm[1] * 0.2 + t[1] * k, pad=0.0, y=g + 0.3)
                           for k in (-0.4, 0.4)):
                        continue
                    base = max(g, y0)
                    for h in (0.1, 0.5, 1.0, 1.5, 2.0, 2.45):
                        yy = base + h
                        if yy > y1 - 0.02:
                            continue
                        if kind == "stall" and h > 0.95 and self.stall_front(s, side):
                            continue
                        start = (fx + nrm[0] * 0.5, yy, fz + nrm[1] * 0.5)
                        dd, who = self.ray(self.bvh_arch, self.own_arch, start, (-nrm[0], 0, -nrm[1]), 1.1)
                        n += 1
                        e = (0.5 - dd) if dd is not None else -9.9
                        if dd is not None:
                            worst = max(worst, abs(e))
                        if dd is None or abs(e) > TOL_FACE:
                            self.err("solid_faces", f"{s['id']}.{side} s={sl:.2f} y={yy:.2f}: "
                                                    f"{'no surface within 0.6 m behind the face' if dd is None else f'{e:+.2f} m'} ({who})")
        self.stats["face_samples"] = n
        self.stats["face_worst_err_m"] = round(worst, 3)

    @staticmethod
    def stall_front(s, side):
        return (side == "s") if s["rect"].cz < 0 else (side == "n")

    # ------------------------------------------------------------------ zones
    def check_zones(self):
        for ch, o in self.objs:
            if ch == "skyline" or not is_decor(o) or o.name.startswith("water_"):
                continue
            mw = o.matrix_world
            for zn in self.L.zones:
                cx, cz = zn["center"][0], zn["center"][2]
                fy = zn.get("floor_y", 0.0)
                for v in o.data.vertices:
                    p = mw @ v.co
                    if math.hypot(p.x - cx, -p.y - cz) < zn["radius"] and fy + 0.25 < p.z < fy + 4.0:
                        self.err("zones", f"{o.name} intrudes the {zn['id']} scoring circle")
                        break

    # ------------------------------------------------------------------ specials + budgets
    def check_specials(self):
        names = {o.name: o for ch, o in self.objs}
        for w in self.L.water:
            nm = "water_" + w["id"]
            o = names.get(nm)
            if o is None:
                self.err("specials", f"missing {nm}")
                continue
            zs = {round((o.matrix_world @ v.co).z, 3) for v in o.data.vertices}
            if zs != {round(w["y"], 3)}:
                self.err("specials", f"{nm} not flat at y={w['y']}: {sorted(zs)[:4]}")
            pts = [B2L(o.matrix_world @ v.co) for v in o.data.vertices]
            r = w["rect"]
            if abs(min(p[0] for p in pts) - r.x0) > 0.01 or abs(max(p[0] for p in pts) - r.x1) > 0.01 or \
               abs(min(p[2] for p in pts) - r.z0) > 0.01 or abs(max(p[2] for p in pts) - r.z1) > 0.01:
                self.err("specials", f"{nm} extent does not match the layout rect")
        puddles = [n for n in names if n.startswith("puddle_")]
        want = sum(1 for d in self.L.decor if d["kind"] == "puddle")
        if len(puddles) != want:
            self.err("specials", f"puddle_* count {len(puddles)} != layout {want}")
        smokes = [o for o in bpy.data.objects if o.name.startswith("emit_smoke_") and o.type == "EMPTY"]
        wants = [d["pos"] for d in self.L.decor if d["kind"] == "chimney_smoke"]
        if len(smokes) != len(wants):
            self.err("specials", f"emit_smoke_* count {len(smokes)} != layout {len(wants)}")
        for p in wants:
            best = min((math.hypot(B2L(o.matrix_world.translation)[0] - p[0], B2L(o.matrix_world.translation)[2] - p[2]) for o in smokes),
                       default=99)
            if best > 0.01:
                self.err("specials", f"no emit_smoke empty at layout point {p}")
        self.stats["special_counts"] = {pre.rstrip("_"): sum(1 for ch, o in self.objs if o.name.startswith(pre))
                                        for pre in C.SPECIAL_PREFIXES}
        self.stats["special_counts"]["emit_smoke"] = len(smokes)

    def check_budgets(self):
        tris = 0
        mats = set()
        for ch, o in self.objs:
            tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
            for m in o.data.materials:
                if m:
                    mats.add(m.name)
        self.stats["triangles"] = tris
        self.stats["materials"] = len(mats)
        if tris > 1_200_000:
            self.err("budgets", f"{tris} triangles > 1.2 M")
        if len(mats) > 40:
            self.err("budgets", f"{len(mats)} materials > 40")

    def run(self):
        for fn in (self.check_floors, self.check_ramps, self.check_solids, self.check_zones, self.check_specials, self.check_budgets):
            fn()
            self.log(f"verify: {fn.__name__} done ({sum(len(v) for v in self.fail.values())} failures so far)")
        self.stats["layout_overlaps_skipped"] = sorted(self.overlaps)
        res = {"passed": not self.fail, "stats": self.stats,
               "failures": {k: {"count": len(v), "first": v[:25]} for k, v in self.fail.items()},
               "tolerances": {"floor_m": TOL_FLOOR, "face_m": TOL_FACE, "headroom_m": HEADROOM}}
        return res


def verify(log=print, dump=None):
    v = Verifier(log)
    res = v.run()
    if dump:
        with open(dump, "w") as fh:
            json.dump(v.fail, fh, indent=1)
    return res


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    r = verify(dump=argv[0] if argv else None)
    print(json.dumps(r, indent=1))
    sys.exit(0 if r["passed"] else 3)
