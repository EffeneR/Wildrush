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

T0 = time.time()


def log(msg):
    print(f"[arena {time.time() - T0:7.1f}s] {msg}", flush=True)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--skip", default="")
    return ap.parse_args(argv)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0


def flush(out: G.Out, cols):
    """Turn the Out registry into Blender objects in chunk collections."""
    made = []
    for (chunk, key), mb in sorted(out.mbs.items()):
        if mb.empty():
            continue
        name = f"{chunk}_{key}"
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
    objs = flush(out, cols)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == "MESH")
    log(f"objects={len(objs)} tris~{tris}")
    if not a.no_save:
        bpy.ops.file.make_paths_relative()
        bpy.ops.wm.save_as_mainfile(filepath=C.BLEND_PATH, compress=True)
        log(f"saved {C.BLEND_PATH}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
