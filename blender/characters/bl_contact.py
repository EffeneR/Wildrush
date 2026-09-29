"""Clip contact sheet (Workbench): rows = clips, columns = 5 evenly spaced frames.
blender -b <id>.blend --gpu-backend vulkan --python bl_contact.py -- <out.png> clip1,clip2,... [yaw]"""
import os
import sys
import math
import numpy as np
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bl_util import script_args
import anim_lib as AL

args = script_args()
out = args[0]
clips = args[1].split(",")
yaw = float(args[2]) if len(args) > 2 else 35.0
sc = bpy.context.scene
arm = [o for o in sc.objects if o.type == "ARMATURE"][0]
for o in sc.objects:
    if o.name.endswith("_wsrc"):
        o.hide_render = True
AL.set_constraints_enabled(arm, False)
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = os.environ.get("CS_COLOR", "TEXTURE")
sh.show_cavity = True
sh.show_shadows = True
W, Hh = int(os.environ.get("CS_W", 220)), int(os.environ.get("CS_H", 300))
sc.render.resolution_x = W
sc.render.resolution_y = Hh
cd = bpy.data.cameras.new("cc")
cam = bpy.data.objects.new("cc", cd)
sc.collection.objects.link(cam)
sc.camera = cam
cd.type = "ORTHO"
cd.ortho_scale = 2.6
bpy.ops.mesh.primitive_plane_add(size=6)
fl = bpy.context.active_object
tgt = Vector((0, -0.2, 0.95))
a = math.radians(yaw)
cam.location = tgt + Vector((math.sin(a) * 6, -math.cos(a) * 6, 1.2))
cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
rows = []
tmp = out + "_tmp.png"
for c in clips:
    act = bpy.data.actions.get(c)
    row = []
    if act is None:
        rows.append(np.zeros((Hh, W * 5, 4), dtype=np.float32))
        continue
    arm.animation_data_create()
    arm.animation_data.action = act
    n = int(round(act.frame_range[1]))
    for k in range(5):
        f = n * k / 4.0
        sc.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
        sc.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(tmp)
        px = np.array(im.pixels[:], dtype=np.float32).reshape(Hh, W, 4)
        bpy.data.images.remove(im)
        row.append(px)
    rows.append(np.concatenate(row, axis=1))
buf = np.concatenate(rows[::-1], axis=0)
img = bpy.data.images.new("sheet", buf.shape[1], buf.shape[0])
img.pixels = buf.ravel()
img.filepath_raw = out
img.file_format = "PNG"
img.save()
os.remove(tmp)
print("contact sheet", out)
