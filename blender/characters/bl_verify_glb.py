"""Re-import a GLB in a clean Blender session and report its content (import check).
blender -b --factory-startup --python bl_verify_glb.py -- <file.glb> <out.json>"""
import sys, os, json
import bpy
argv = sys.argv[sys.argv.index("--") + 1:]
glb, out = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
res = dict(file=glb, ok=False)
try:
    r = bpy.ops.import_scene.gltf(filepath=glb)
    res["operator"] = list(r)
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    tris = 0
    for m in meshes:
        m.data.calc_loop_triangles()
        tris += len(m.data.loop_triangles)
    mats = sorted({s.material.name for m in meshes for s in m.material_slots if s.material})
    res.update(armatures=len(arms), bones=(len(arms[0].data.bones) if arms else 0),
               bone_names=[b.name for b in arms[0].data.bones] if arms else [],
               meshes=len(meshes), triangles=tris, materials=mats,
               animations={a.name: [round(a.frame_range[0], 2), round(a.frame_range[1], 2)] for a in bpy.data.actions},
               images=[i.name for i in bpy.data.images])
    res["ok"] = bool(arms and meshes and bpy.data.actions and len(bpy.data.images) >= 4)
except Exception as e:
    res["error"] = repr(e)
json.dump(res, open(out, "w"), indent=1)
print("GLB_CHECK", json.dumps({k: v for k, v in res.items() if k not in ("bone_names", "animations", "images")}))
print("GLB_CHECK_ANIMS", len(res.get("animations", {})))
if not res["ok"]:
    raise SystemExit("GLB check failed: " + json.dumps({k: res.get(k) for k in ("armatures", "meshes", "images", "error")}))
