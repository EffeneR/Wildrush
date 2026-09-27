"""WILDRUSH character pipeline - step 1 (venv): SDF -> meshes + rig spec.

usage: python wr_mesh.py <fighter_id> <work_dir> [--res 0.0025] [--cloth-res 0.0032] [--preview]

Outputs in <work_dir>/<id>/:
  body_hi.npz     body mesh (hidden-under-clothing faces removed), float32 verts, int32 faces
  cloth_hi.npz    clothing mesh + per-face garment index
  rig.json        bones, eyes, claws, teeth, whiskers, landmarks, garments
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wr_sdf import mesh_sdf, eval_points, remove_faces, keep_largest_components  # noqa: E402
import wr_anatomy  # noqa: E402


def log(*a):
    print("[wr_mesh]", *a, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fid")
    ap.add_argument("work")
    ap.add_argument("--res", type=float, default=0.0025)
    ap.add_argument("--cloth-res", type=float, default=0.0032)
    ap.add_argument("--no-cloth", action="store_true")
    ap.add_argument("--part", default=None, help="preview: mesh only this part (e.g. head)")
    args = ap.parse_args()
    out = os.path.join(args.work, args.fid)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    F = wr_anatomy.fighter(args.fid)
    have_cloth = False
    try:
        import wr_clothing
        if not args.no_cloth:
            wr_clothing.build(F)
            have_cloth = True
    except ImportError:
        pass
    log(f"built SDF for {args.fid} in {time.time() - t0:.1f}s")

    t = time.time()
    body = F.body
    if args.part:
        body = F.parts[args.part]
        have_cloth = False
    V, Fc = mesh_sdf(body, body.lo, body.hi, args.res, block=24, verbose=True)
    V, Fc = keep_largest_components(V, Fc, min_faces=400)
    log(f"body mesh: {len(V)} verts {len(Fc)} faces ({time.time() - t:.1f}s)")
    if have_cloth:
        # delete body faces fully hidden under clothing
        cov = F.covered(V)
        keep = ~(cov[Fc[:, 0]] & cov[Fc[:, 1]] & cov[Fc[:, 2]])
        V, Fc = remove_faces(V, Fc, keep)
        log(f"body visible after cover cull: {len(V)} verts {len(Fc)} faces")
    np.savez_compressed(os.path.join(out, "body_hi.npz"), V=V.astype(np.float32), F=Fc.astype(np.int32))

    garments = []
    if have_cloth:
        allV, allF, allG = [], [], []
        nv = 0
        for gi, g in enumerate(F.garments):
            t = time.time()
            gv, gf = mesh_sdf(g["node"], g["node"].lo, g["node"].hi, g.get("res", args.cloth_res), block=24)
            if len(gf) == 0:
                log(f"  garment {g['name']}: EMPTY")
                continue
            gv, gf = keep_largest_components(gv, gf, min_faces=60)
            allV.append(gv)
            allF.append(gf + nv)
            allG.append(np.full(len(gf), gi, dtype=np.int32))
            nv += len(gv)
            log(f"  garment {g['name']}: {len(gv)} verts {len(gf)} faces ({time.time() - t:.1f}s)")
            garments.append(dict(name=g["name"], index=gi))
        if allV:
            CV = np.concatenate(allV)
            CF = np.concatenate(allF)
            CG = np.concatenate(allG)
            np.savez_compressed(os.path.join(out, "cloth_hi.npz"), V=CV.astype(np.float32), F=CF.astype(np.int32),
                                G=CG)
    rig = dict(
        fighter=args.fid, H=F.p["H"], species=F.p["species"],
        bones=F.bones, eyes=F.eyes, claws=F.claws, teeth=F.teeth, whiskers=F.whiskers,
        landmarks=F.landmarks,
        joints={k: np.asarray(v).tolist() for k, v in F.J.items()},
        mouth={k: (np.asarray(v).tolist() if isinstance(v, np.ndarray) else v) for k, v in F.mouth.items()},
        garments=[dict(name=g["name"], index=i, kind=g.get("kind", "cloth")) for i, g in enumerate(getattr(F, "garments", []))],
        tail_pts=F.tail_pts.tolist(),
        res=args.res,
    )
    with open(os.path.join(out, "rig.json"), "w") as f:
        json.dump(rig, f, indent=1)
    log(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
