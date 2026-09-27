"""Quick Workbench preview of raw SDF meshes (iteration aid, not part of the final evidence).

blender -b --factory-startup --python bl_preview.py -- <work_dir>/<id> <out.png> [head]
"""
import sys
import os
import math
import json
import numpy as np
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
wdir, outp = argv[0], argv[1]
mode = argv[2] if len(argv) > 2 else "body"

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def load(name, path, color):
    d = np.load(path)
    V = d["V"].astype(np.float64)
    F = d["F"].astype(np.int64)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    me.loops.add(F.size)
    me.loops.foreach_set("vertex_index", F.ravel())
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", np.arange(0, F.size, 3))
    me.polygons.foreach_set("loop_total", np.full(len(F), 3))
    me.update()
    me.validate()
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(name + "_m")
    mat.diffuse_color = color
    me.materials.append(mat)
    return ob


load("body", os.path.join(wdir, "body_hi.npz"), (0.72, 0.70, 0.66, 1))
if os.path.exists(os.path.join(wdir, "cloth_hi.npz")):
    load("cloth", os.path.join(wdir, "cloth_hi.npz"), (0.25, 0.30, 0.42, 1))
rig = json.load(open(os.path.join(wdir, "rig.json")))
for i, e in enumerate(rig["eyes"]):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=e["radius"], location=e["center"], segments=24, ring_count=16)
    ob = bpy.context.active_object
    m = bpy.data.materials.new("eye%d" % i)
    m.diffuse_color = (0.85, 0.55, 0.1, 1)
    ob.data.materials.append(m)

scene.render.engine = "BLENDER_WORKBENCH"
sh = scene.display.shading
sh.light = "STUDIO"
sh.color_type = "MATERIAL"
sh.show_cavity = True
sh.cavity_type = "BOTH"
sh.show_shadows = False
scene.render.resolution_x = 640
scene.render.resolution_y = 900 if mode == "body" else 640
scene.render.film_transparent = False
scene.world = bpy.data.worlds.new("w")
scene.display.shading.background_type = "VIEWPORT"

cam_d = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_d)
scene.collection.objects.link(cam)
scene.camera = cam
H = rig["H"]
if mode == "body":
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = H * 1.12 + 0.3
    target = Vector((0, 0.15, H * 0.5 + 0.05))
    dist = 6.0
    views = [("front", 0), ("side", 90), ("back", 180), ("q", 35)]
else:
    cam_d.type = "PERSP"
    cam_d.lens = 85
    hf = rig["landmarks"]["head_frame"]["o"]
    target = Vector((hf[0], hf[1] - 0.02, hf[2] + 0.02 + (0.09 if rig["species"] == "rabbit" else 0.0)))
    dist = 1.25 if rig["species"] != "rabbit" else 1.6
    views = [("front", 0), ("q", 35), ("side", 90), ("low", -20)]

tiles = []
for name, yaw in views:
    a = math.radians(yaw)
    pitch = 0.0 if name != "low" else 0.0
    loc = target + Vector((math.sin(a) * dist * (-1 if name == "low" else 1), -math.cos(a) * dist, 0.0))
    if name == "low":
        loc = target + Vector((0.35 * dist, -0.9 * dist, -0.25 * dist))
    cam.location = loc
    d = (target - loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    p = outp.replace(".png", f"_{name}.png")
    scene.render.filepath = p
    bpy.ops.render.render(write_still=True)
    tiles.append(p)

# stitch
imgs = [bpy.data.images.load(p) for p in tiles]
w, h = imgs[0].size
out = bpy.data.images.new("stitch", w * len(imgs), h, alpha=False)
buf = np.zeros((h, w * len(imgs), 4), dtype=np.float32)
for i, im in enumerate(imgs):
    px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
    buf[:, i * w:(i + 1) * w] = px
out.pixels = buf.ravel()
out.filepath_raw = outp
out.file_format = "PNG"
out.save()
for p in tiles:
    os.remove(p)
print("preview written", outp)
