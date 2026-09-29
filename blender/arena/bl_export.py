"""GLB chunk export + arena_art.json manifest for the Briarport art build.

Each chunk collection (chunk_A, chunk_B, chunk_C, chunk_north, chunk_south, chunk_skyline) is
exported to game/assets/arena/briarport_<chunk>.glb in world (= layout/Godot) coordinates with
identity root transform. Images are then rewritten to external URIs (textures/<name>.png) so all
chunks share one texture set; any image that cannot be externalised fails the build.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os

import bpy

import common as C
import glb_tools

GLB_NAME = "briarport_{}.glb"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def chunk_objects(chunk):
    col = bpy.data.collections.get("chunk_" + chunk)
    if col is None:
        return []
    return [o for o in col.all_objects if o.type in ("MESH", "EMPTY")]


def export_chunk(chunk, out_dir, log):
    objs = chunk_objects(chunk)
    if not objs:
        raise RuntimeError(f"chunk {chunk} is empty")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    path = os.path.join(out_dir, GLB_NAME.format(chunk))
    dbg = bpy.app.debug_value
    bpy.app.debug_value = 2          # glTF add-on: errors only (export_loglevel>=0 hits a KeyError in 4.5.9)
    try:
        _gltf(path)
    finally:
        bpy.app.debug_value = dbg
    return _post(path, chunk, log)


def _gltf(path):
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
        export_image_format="AUTO", export_extras=True, export_vertex_color="MATERIAL",
        export_materials="EXPORT", export_cameras=False, export_lights=False, export_animations=False,
        export_skins=False, export_morph=False, export_texcoords=True, export_normals=True,
        export_tangents=False, export_gpu_instances=False, export_def_bones=False,
    )


def _post(path, chunk, log):
    rep = glb_tools.externalize_images(path, C.TEX_DIR, "textures")
    if rep["kept_embedded"]:
        raise RuntimeError(f"{path}: images could not be externalised: {rep['kept_embedded']}")
    st = glb_tools.stats(path)
    log(f"exported {os.path.basename(path)}: {st['triangles']} tris, {st['mesh_nodes']} mesh nodes, "
        f"{st['shared_meshes']} shared meshes, {len(st['materials'])} materials, {os.path.getsize(path) // 1024} KiB")
    return path, st


def world_bounds(objs):
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for o in objs:
        if o.type != "MESH":
            pts = [o.matrix_world.translation]
        else:
            pts = [o.matrix_world @ v.co for v in o.data.vertices] if len(o.data.vertices) < 200 else \
                [o.matrix_world @ __import__("mathutils").Vector(c) for c in o.bound_box]
        for p in pts:
            x, y, z = p.x, p.z, -p.y           # Blender -> layout
            lo = [min(lo[0], x), min(lo[1], y), min(lo[2], z)]
            hi = [max(hi[0], x), max(hi[1], y), max(hi[2], z)]
    return [round(v, 3) for v in lo], [round(v, 3) for v in hi]


def material_entry(name):
    spec = C.MATERIALS[name]
    m = bpy.data.materials.get(name)
    ent = {"name": name}
    for k in ("albedo", "normal", "orm"):
        if spec.get(k):
            ent[k] = f"textures/{spec[k]}.png"
    ent["alpha"] = {"clip": "MASK", "blend": "BLEND"}.get(spec.get("alpha"), "OPAQUE")
    ent["double_sided"] = bool(spec.get("two_sided", False))
    if spec.get("emission"):
        ent["emissive"] = {"color": list(spec["emission"]), "strength": spec.get("strength", 5.0)}
    ent["texel_m_per_uv"] = list(C.TEXEL[spec["texel"]])
    ent["used"] = bool(m and m.users > 0)
    return ent


def special_nodes():
    out = {k.rstrip("_"): [] for k in C.SPECIAL_PREFIXES}
    for ch in C.CHUNKS:
        for o in chunk_objects(ch):
            for pre in C.SPECIAL_PREFIXES:
                if o.name.startswith(pre):
                    e = {"node": o.name, "chunk": ch}
                    if o.type == "EMPTY" or pre in ("emit_smoke_",):
                        t = o.matrix_world.translation
                        e["pos"] = [round(t.x, 3), round(t.z, 3), round(-t.y, 3)]
                    if "water_y" in o.keys():
                        e["y"] = float(o["water_y"])
                    if "layout_id" in o.keys():
                        e["layout_id"] = str(o["layout_id"])
                    out[pre.rstrip("_")].append(e)
    return out


def write_manifest(results, verification, decisions, log):
    lay_sha = sha256(C.LAYOUT_PATH)
    lay = C.load_json(C.LAYOUT_PATH)
    used_mats = sorted({m for r in results.values() for m in r["stats"]["materials"]})
    tex_files = sorted({im["uri"] for r in results.values() for im in r["stats"]["images"] if im.get("uri")})
    tex_bytes = sum(os.path.getsize(os.path.join(C.ASSET_DIR, t)) for t in tex_files)
    tris = sum(r["stats"]["triangles"] for r in results.values())
    chunks = []
    for ch in C.CHUNKS:
        r = results[ch]
        st = r["stats"]
        lo, hi = world_bounds(chunk_objects(ch))
        chunks.append({
            "id": ch, "path": "res://assets/arena/" + os.path.basename(r["path"]),
            "file": os.path.basename(r["path"]), "sha256": sha256(r["path"]),
            "bytes": os.path.getsize(r["path"]),
            "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            "bounds": {"min": lo, "max": hi},
            "triangles": st["triangles"], "triangles_unique_meshes": st["triangles_unique_meshes"],
            "nodes": st["nodes"], "mesh_nodes": st["mesh_nodes"], "meshes": st["meshes"],
            "shared_meshes": st["shared_meshes"], "materials": st["materials"],
            "textures": sorted({im["uri"] for im in st["images"] if im.get("uri")}),
        })
    man = {
        "name": "Briarport",
        "version": 1,
        "generated": datetime.date.today().isoformat(),
        "generator": {"entry": "tools/build_arena_art.sh", "script": "blender/arena/build_arena.py",
                      "blender": bpy.app.version_string, "source_blend": "blender/arena/briarport.blend"},
        "layout": {"path": "game/data/arena/briarport_layout.json", "sha256": lay_sha, "version": lay.get("version")},
        "coordinates": {
            "glb_space": "Godot/layout space: X east, Y up, Z south, metres. Chunks are authored in world "
                         "space; instance each GLB at the identity transform.",
            "layout_to_blender": "bx = x, by = -z, bz = y (glTF export converts back to Y up)",
        },
        "chunks": chunks,
        "totals": {"triangles": tris, "materials": len(used_mats), "textures": len(tex_files),
                   "texture_bytes": tex_bytes, "chunk_bytes": sum(c["bytes"] for c in chunks)},
        "budgets": {"triangles_max": 1200000, "materials_max": 40, "texture_size": "1K-2K",
                    "triangles_ok": tris <= 1200000, "materials_ok": len(used_mats) <= 40},
        "materials": [material_entry(m) for m in used_mats],
        "textures": tex_files,
        "special_meshes": special_nodes(),
        "special_mesh_rules": {
            "water_": "water surface quads at the layout water y (replace with the water shader)",
            "puddle_": "flat puddles at floor + 0.005 m, own material (wet decal)",
            "foliage_": "alpha-clip, two-sided leaves/ivy/flowers",
            "emissive_": "lamp glass (emissive)",
            "banner_": "cloth, two-sided (optional wind)",
            "emit_smoke_": "empties (Node3D) marking chimney smoke emitters",
        },
        "lod": {
            "authored_lods": "none (single LOD0 per mesh)",
            "strategy": "Godot importer automatic mesh LOD (glTF import option meshes/generate_lods = true, the "
                        "default) + the triangle budget below is before LOD",
            "suggested_visibility_ranges_m": {"props_small (barrels, pallets, crates < 1.5 m)": 60,
                                              "decals (grates, manholes, paint)": 45,
                                              "foliage_ivy / flowers": 70,
                                              "skyline chunk": "no limit (always visible)"},
            "occlusion": "buildings are closed shells; OccluderInstance3D can be baked from the chunk meshes",
        },
        "collision": "none in the art (the game builds collision/nav from the layout JSON)",
        "verification": verification,
        "decisions": decisions,
    }
    with open(C.MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1)
    log(f"manifest {C.MANIFEST_PATH}: {tris} tris, {len(used_mats)} materials, {len(tex_files)} textures")
    return man


def export_all(log, verification=None, decisions=None):
    os.makedirs(C.ASSET_DIR, exist_ok=True)
    results = {}
    for ch in C.CHUNKS:
        path, st = export_chunk(ch, C.ASSET_DIR, log)
        results[ch] = {"path": path, "stats": st}
    return write_manifest(results, verification or {}, decisions or [], log)
