"""Aggregate per-fighter checks into evidence/characters/report.json.
usage: python report.py <work_dir> <evidence_dir> <game_char_dir> id [id ...]"""
import json
import os
import sys

work, evd, gdir = sys.argv[1:4]
ids = sys.argv[4:]
out = dict(generated_by="tools/build_characters.sh", fighters={})
gc = {}
gpath = os.path.join(evd, "godot_check.json")
if os.path.exists(gpath):
    gc = json.load(open(gpath))
glog = os.path.join(evd, "godot_import.log")
gerr = []
if os.path.exists(glog):
    gerr = [l.strip() for l in open(glog, errors="replace") if "ERROR" in l or "SCRIPT ERROR" in l]
for fid in ids:
    r = {}
    cp = os.path.join(work, fid, "checks.json")
    if os.path.exists(cp):
        c = json.load(open(cp))
        r["triangles"] = c["triangles"]
        r["materials"] = c["materials"]
        r["material_count"] = len(c["materials"])
        r["deform_bones"] = c["skeleton"]["deform_bones"]
        r["skeleton"] = c["skeleton"]
        r["weights"] = c["weights"]
        r["clips"] = c["clips"]
        r["clip_count"] = len(c["clips"])
        r["required_missing"] = c["required_missing"]
        r["alignment"] = c["alignment"]
        r["max_alignment_error_m"] = max([v["max_error_m"] for v in c["alignment"].values()] or [0.0])
        r["alignment_all_ok"] = all(v["ok"] for v in c["alignment"].values())
        r["foot_contact"] = c["foot_contact"]
        r["rest_drift_idle0"] = c.get("rest_drift_idle0")
        r["extra_checks"] = c.get("extra", {})
    tp = os.path.join(work, fid, "texture_checks.json")
    if os.path.exists(tp):
        tc = json.load(open(tp))
        r["cloth_region_sides"] = tc.get("cloth_regions")
        if fid == "vex":
            sec = tc.get("cloth_regions", {}).get("secondary", {})
            r["vex_copper_panel_right_shoulder_only"] = bool(sec and sec.get("frac_left_x_pos", 1.0) == 0.0)
    gp = os.path.join(evd, f"{fid}_glbcheck.json")
    if os.path.exists(gp):
        g = json.load(open(gp))
        r["blender_reimport"] = dict(ok=g.get("ok"), bones=g.get("bones"), triangles=g.get("triangles"),
                                     animations=len(g.get("animations", {})), materials=g.get("materials"))
    if fid in gc:
        g = gc[fid]
        r["godot_import"] = dict(bones=g.get("bones"), triangles=g.get("triangles"), clips=len(g.get("clips", {})),
                                 missing_clips=g.get("missing_clips"), length_mismatch=g.get("length_mismatch"),
                                 loop_mismatch=g.get("loop_mismatch"), materials=g.get("materials"),
                                 import_errors=[e for e in gerr if fid in e])
    glb = os.path.join(gdir, fid, fid + ".glb")
    r["glb"] = dict(path=os.path.relpath(glb, os.path.join(evd, "..", "..")), bytes=os.path.getsize(glb) if os.path.exists(glb) else None)
    r["evidence"] = [f"evidence/characters/{fid}_{k}.png" for k in ("turnaround", "skills", "blender")]
    out["fighters"][fid] = r
out["godot_import_errors_total"] = len(gerr)
json.dump(out, open(os.path.join(evd, "report.json"), "w"), indent=1)
print("report written", os.path.join(evd, "report.json"))
for fid, r in out["fighters"].items():
    print(fid, "tris", r.get("triangles"), "mats", r.get("material_count"), "bones", r.get("deform_bones"),
          "clips", r.get("clip_count"), "max_align", r.get("max_alignment_error_m"), "godot", r.get("godot_import", {}).get("clips"))
