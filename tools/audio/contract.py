"""Parse the cue table of docs/AUDIO_CONTRACT.md into {cue_id: {"files": [...], "notes": str,
"duration": (min_s, max_s) | None}} so the builder and the checker validate against the binding
contract itself rather than against a hand-copied list."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "AUDIO_CONTRACT.md"


def _cue_names(cell: str) -> list[str]:
    names: list[str] = []
    for tok in (t.strip() for t in cell.split("/")):
        if not tok:
            continue
        if tok.isdigit() and names:  # "score_warning_1/2/3"
            tok = re.sub(r"\d+$", tok, names[-1])
        names.append(tok)
    return names


def _expand(pattern: str, cues: list[str]) -> list[str]:
    pats = [pattern]
    m = re.search(r"<(\w+)>", pattern)
    if m:
        prefix = os.path.basename(pattern[: m.start()])
        subs = [c[len(prefix):] for c in cues if c.startswith(prefix)]
        pats = [pattern[: m.start()] + s + pattern[m.end():] for s in subs]
    out: list[str] = []
    for p in pats:
        r = re.search(r"(\d+)\.\.(\d+)", p)
        if r:
            width = len(r.group(1))
            for k in range(int(r.group(1)), int(r.group(2)) + 1):
                out.append(p[: r.start()] + str(k).zfill(width) + p[r.end():])
        else:
            out.append(p)
    return out


def _duration(notes: str, files: list[str]):
    if not ("loop" in notes or "sting" in notes or any(f.endswith(".ogg") for f in files)):
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*s\b", notes)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*s\b", notes)
    if m:
        v = float(m.group(1))
        return v * 0.99, v * 1.01
    return None


def parse_contract(path: Path = CONTRACT_PATH) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    cues: dict = {}
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("| Cue |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not s.startswith("|"):
            if cues:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        names = _cue_names(cells[0])
        notes = cells[2] if len(cells) > 2 else ""
        files: list[str] = []
        for pat in re.findall(r"`([^`]+)`", cells[1]):
            files.extend(_expand(pat, names))
        assigned = set()
        for cue in names:
            mine = [f for f in files
                    if (stem := Path(f).stem) == cue or re.fullmatch(re.escape(cue) + r"_\d{2}", stem)]
            if not mine:
                raise ValueError(f"contract parse: no files for cue {cue!r} in row {cells[0]!r}")
            if cue in cues:
                raise ValueError(f"contract parse: duplicate cue {cue!r}")
            cues[cue] = {"files": mine, "notes": notes, "duration": _duration(notes, mine)}
            assigned.update(mine)
        if assigned != set(files):
            raise ValueError(f"contract parse: unassigned files {sorted(set(files) - assigned)}")
    if not cues:
        raise ValueError("contract parse: cue table not found")
    return cues


if __name__ == "__main__":
    c = parse_contract()
    n = sum(len(v["files"]) for v in c.values())
    for k, v in c.items():
        print(f"{k:22s} {len(v['files']):2d}  {v['files'][0]:32s} {v['duration']}")
    print(f"{len(c)} cues, {n} files")
