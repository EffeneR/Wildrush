"""Write the Godot import sidecar <id>.glb.import next to the GLB: clips resampled at 60 fps
(Godot's default would be 30) and loop_mode = linear for every clip flagged loop in <id>_anim.json.
Godot keeps these [params] and fills in [remap]/[deps] on import (verified in the scratch project).
usage: python write_import_sidecar.py <id>_anim.json <id>.glb.import"""
import json
import sys

meta = json.load(open(sys.argv[1]))
loops = [k for k, v in meta["clips"].items() if v.get("loop")]
lines = ["[remap]", "", 'importer="scene"', "importer_version=1", "", "[params]", "",
         "animation/import=true", "animation/fps=60", "animation/trimming=false",
         "animation/remove_immutable_tracks=true", "animation/import_rest_as_RESET=false",
         "_subresources={", '"animations": {']
for i, k in enumerate(sorted(loops)):
    lines += [f'"{k}": {{', '"settings/loop_mode": 1', "}" + ("," if i < len(loops) - 1 else "")]
lines += ["}", "}", ""]
open(sys.argv[2], "w").write("\n".join(lines))
print("sidecar", sys.argv[2], "loops:", ",".join(sorted(loops)))
