"""Quick Eevee look-dev render of a stage file (iteration aid).
blender -b <file.blend> --gpu-backend vulkan --python bl_quickrender.py -- <texdir> <out.png> [pose_action]
"""
import sys
import os
import math
import json
import numpy as np
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bl_util import script_args, fighter_json
import bl_mat

args = script_args()
texdir, out = args[0], args[1]
action = args[2] if len(args) > 2 else None
sc = bpy.context.scene
mesh = [o for o in sc.objects if o.type == "MESH" and o.name.endswith("_mesh")][0]
arm = [o for o in sc.objects if o.type == "ARMATURE"][0]
fid = mesh.name[:-5]
fj = fighter_json(fid)
if not bpy.data.materials[fid + "_fur"].node_tree.nodes.get("Image Texture"):
    bl_mat.setup_materials(mesh, fid, texdir, fj["palettes"]["default"])
if action:
    arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions[action]
    sc.frame_set(int(args[3]) if len(args) > 3 else 0)

sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.eevee.taa_render_samples = 32
sc.render.resolution_x = 700
sc.render.resolution_y = 1000
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.045, 0.05, 0.06, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = world


def light(name, loc, energy, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return lo


light("key", (-2.2, -3.0, 3.0), 900, 2.0, (1.0, 0.96, 0.9))
light("fill", (2.8, -2.0, 1.6), 300, 3.0, (0.85, 0.9, 1.0))
light("rim", (0.5, 3.5, 2.8), 700, 1.5, (0.9, 0.95, 1.0))
cam_d = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
cam_d.lens = 50
tiles = []
H = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "game", "data", "tuning", "fighters", fid + ".json")))["height"]
views = [("front", 0, 0.5 * H, 5.2, 50), ("q", 35, 0.5 * H, 5.2, 50), ("back", 180, 0.5 * H, 5.2, 50), ("face", 20, H - 0.10, 1.1, 85)]
for name, yaw, tz, dist, lens in views:
    cam_d.lens = lens
    a = math.radians(yaw)
    tgt = Vector((0, 0, tz))
    cam.location = tgt + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.15 * dist / 5))
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    p = out.replace(".png", f"_{name}.png")
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    tiles.append(p)
imgs = [bpy.data.images.load(p) for p in tiles]
w, h = imgs[0].size
buf = np.zeros((h, w * len(imgs), 4), dtype=np.float32)
for i, im in enumerate(imgs):
    buf[:, i * w:(i + 1) * w] = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
img = bpy.data.images.new("st", w * len(imgs), h)
img.pixels = buf.ravel()
img.filepath_raw = out
img.file_format = "PNG"
img.save()
for p in tiles:
    os.remove(p)
print("quickrender written", out)
