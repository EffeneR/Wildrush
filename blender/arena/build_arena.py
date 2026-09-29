"""Briarport arena art build (Blender, background).

    blender -b --factory-startup -t 2 --python-exit-code 1 --python blender/arena/build_arena.py -- [opts]

Options:
    --no-export      skip GLB export + manifest
    --no-save        skip saving blender/arena/briarport.blend
    --skip STAGE     comma list of stages to skip (ground,buildings,props,skyline)

Reads game/data/arena/briarport_layout.json, builds kit + assembled arena in layout-driven
collections (one per chunk), saves the .blend, exports game/assets/arena/briarport_<chunk>.glb
with shared external textures, writes game/assets/arena/arena_art.json and runs the geometric
verification (verify_arena.py). Exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402

import common as C  # noqa: E402
import bl_core as B  # noqa: E402
import bl_ground as G  # noqa: E402
import bl_arch as A  # noqa: E402
import bl_export as X  # noqa: E402
import bl_props as PR  # noqa: E402
import bl_skyline as SK  # noqa: E402
import verify_arena as VF  # noqa: E402

T0 = time.time()


def log(msg):
    print(f"[arena {time.time() - T0:7.1f}s] {msg}", flush=True)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--skip", default="")
    ap.add_argument("--allow-fail", action="store_true", help="export even if verification fails")
    return ap.parse_args(argv)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 backups
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0


def flush(out: G.Out, cols):
    """Turn the Out registry into Blender objects in chunk collections."""
    made = []
    for (chunk, key), mb in sorted(out.mbs.items()):
        if mb.empty():
            continue
        name = f"{key}_{chunk}" if key.startswith(C.SPECIAL_PREFIXES) else f"{chunk}_{key}"
        ob = B.mesh_object(mb, name, cols[chunk], props={"wr_cat": key, "wr_chunk": chunk})
        made.append(ob)
    for chunk, name, mb, props in out.specials:
        p = dict(props)
        p["wr_chunk"] = chunk
        ob = B.mesh_object(mb, name, cols[chunk], props=p)
        made.append(ob)
    return made


def main():
    a = parse()
    skip = set(s for s in a.skip.split(",") if s)
    reset_scene()
    lay = C.Layout()
    root = bpy.context.scene.collection
    arena = B.get_collection("BRIARPORT", root)
    cols = {c: B.get_collection("chunk_" + c, arena) for c in C.CHUNKS}
    kit_col = B.get_collection("KIT", root)
    kit_col.hide_render = True
    kit = B.Kit(kit_col)
    out = G.Out()
    if "ground" not in skip:
        g = G.Ground(lay, out)
        g.floors(); log("floors")
        g.canal_walls(); g.canal_beds(); g.water_surfaces(); log("canals + water")
        g.balustrades(); log("balustrades")
        g.ramps(); g.bridges(); log("stairs, ramps, bridges")
        g.puddles(); g.decals(); log("puddles + decals")
    bld = None
    if "buildings" not in skip:
        bld = A.Buildings(lay, out, kit)
        bld.build(); log(f"buildings: {len(bld.parcels)} parcels")
    props = None
    if "props" not in skip:
        props = PR.Props(lay, out, kit, cols, bld)
        props.solids(); log("props: layout solids")
        props.decor(); log(f"props: decor ({len(props.moved)} decor placements adjusted)")
    if "skyline" not in skip:
        SK.Skyline(lay, out, bld).build(); log("skyline")
    objs = flush(out, cols)
    objs += [o for c in cols.values() for o in c.objects if o not in objs]
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == "MESH")
    log(f"objects={len(objs)} tris~{tris}")
    if not a.no_save:
        bpy.ops.wm.save_as_mainfile(filepath=C.BLEND_PATH, compress=True)
        bpy.ops.file.make_paths_relative()
        bpy.ops.wm.save_mainfile(filepath=C.BLEND_PATH, compress=True)
        bak = C.BLEND_PATH + "1"
        if os.path.exists(bak):
            os.remove(bak)
        log(f"saved {C.BLEND_PATH}")
    ver = VF.verify(log)
    fails = sum(v["count"] for v in ver["failures"].values())
    log(f"verification: passed={ver['passed']} failures={fails} stats={ver['stats']}")
    for k, v in ver["failures"].items():
        for line in v["first"][:10]:
            log(f"  FAIL {k}: {line}")
    rc = 0 if ver["passed"] else 3
    if not a.no_export and (ver["passed"] or a.allow_fail):
        decisions = DECISIONS + [f"decor nudged: {m}" for m in (props.moved if props else [])]
        X.export_all(log, verification=ver, decisions=decisions)
    return rc


DECISIONS = [
    "Visual walls sit exactly on the layout solid faces; thin perimeter solids are deepened outward "
    "(outside the playable area) so roofs read correctly.",
    "Spawn exits and yard gates get arched passages springing at 2.6 m (nothing below 2.4 m over walkable floor).",
    "Canal walls run from y=-3 to the adjoining walkable level and follow the terrace stairs; balustrades follow "
    "every water_edge blocker (visual only).",
    "Crane yaw -100 is read as a compass bearing so the jib points from (66,-6) toward the Loading Yard; its hook "
    "stays outside the 9 m scoring circle.",
    "Boats keep the layout yaw unless that would place a hull crosswise in a narrow canal; then the hull is aligned "
    "with the canal (decor only).",
    "Zone rings are not baked; only paving patterns well inside/outside the 9 m radius are used.",
]


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
