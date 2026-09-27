"""WILDRUSH audio cue table: loudness categories + manifest fields for every cue.

The *file list* of each cue comes from docs/AUDIO_CONTRACT.md (see contract.py); this table adds
what the contract leaves to the audio designer: loudness category, mix trims, voice limits,
priority. Essential cues (hits, guard, parry, guard break, KO, zone changes, score warnings) are
priority 5.
"""
from __future__ import annotations

# Loudness guidance from AUDIO_CONTRACT.md ("RMS of the loud part").
# category -> (target dBFS, block_s, hop_s, relative gate dB) used by dsp.gated_rms_db.
LOUDNESS = {
    "impact": (-14.0, 0.020, 0.005, -15.0),
    "swing": (-20.0, 0.020, 0.005, -15.0),
    "footstep": (-24.0, 0.020, 0.005, -15.0),
    "ui": (-20.0, 0.020, 0.005, -15.0),
    "ambience": (-28.0, 0.400, 0.100, -10.0),
    "music": (-22.0, 0.400, 0.100, -10.0),
}
RMS_TOLERANCE_DB = 4.0          # check_audio.py acceptance window around the category target
PEAK_LIMIT_DBFS = -1.0          # contract: peak <= -1 dBFS
SFX_CEILING_DBFS = -1.2         # build target for WAV (margin for rounding)
LOOP_CEILING_DBFS = -2.0        # pre-encode ceiling for Vorbis (codec overshoot margin)

ESSENTIAL = {
    "hit_light", "hit_heavy", "guard_block", "guard_break", "parry", "knockout",
    "zone_activate", "zone_reveal", "zone_ally", "zone_enemy", "zone_contested",
    "score_warning_1", "score_warning_2", "score_warning_3",
}


def _c(cat, off=0.0, vol=0.0, pr=0.0, mv=2, prio=3):
    return {"category": cat, "rms_offset_db": off, "volume_db": vol, "pitch_rand": pr,
            "max_voices": mv, "priority": prio}


# cue -> spec. bus / positional / loop are derived from the folder (see manifest_entry).
CUES = {
    # ---- locomotion
    "foot_stone": _c("footstep", 0.0, -2.0, 0.08, 10, 1),
    "foot_wood": _c("footstep", 0.0, -2.0, 0.08, 10, 1),
    "foot_metal": _c("footstep", 0.0, -3.0, 0.07, 10, 1),
    "foot_wet": _c("footstep", 0.0, -2.0, 0.08, 10, 1),
    "land_stone": _c("footstep", 2.0, 0.0, 0.06, 4, 2),
    "land_wood": _c("footstep", 2.0, 0.0, 0.06, 4, 2),
    "land_metal": _c("footstep", 2.0, -1.0, 0.06, 4, 2),
    "land_wet": _c("footstep", 2.0, 0.0, 0.06, 4, 2),
    "jump": _c("swing", -1.0, -2.0, 0.07, 4, 2),
    "dodge": _c("swing", 0.0, -1.0, 0.07, 4, 2),
    # ---- attacks / contact
    "swing_light": _c("swing", 0.0, -1.0, 0.08, 6, 2),
    "swing_heavy": _c("swing", 1.0, 0.0, 0.06, 4, 3),
    "kick_whoosh": _c("swing", 0.0, -1.0, 0.07, 4, 2),
    "hit_light": _c("impact", -1.0, 0.0, 0.06, 6, 5),
    "hit_heavy": _c("impact", 1.0, 0.0, 0.05, 4, 5),
    "guard_block": _c("impact", -1.0, 0.0, 0.05, 4, 5),
    "guard_break": _c("impact", 1.0, 0.0, 0.03, 2, 5),
    "parry": _c("impact", -1.0, 0.0, 0.02, 2, 5),
    "knock_skid": _c("swing", -1.0, -2.0, 0.07, 3, 2),
    "body_fall": _c("impact", -2.0, -1.0, 0.06, 3, 3),
    "grab": _c("swing", 0.0, 0.0, 0.06, 2, 3),
    # ---- Nyx
    "nyx_pounce_leap": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    "nyx_pounce_land": _c("swing", 1.0, 0.0, 0.05, 2, 3),
    "nyx_crosscut": _c("swing", 1.0, 0.0, 0.05, 2, 3),
    "nyx_slip": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    # ---- Bruno
    "bruno_rush_start": _c("swing", 1.0, 0.0, 0.05, 2, 3),
    "bruno_rush_impact": _c("impact", 0.0, 0.0, 0.04, 2, 4),
    "bruno_bark": _c("impact", -2.0, 0.0, 0.04, 2, 4),
    "bruno_stand_firm": _c("swing", 0.0, 0.0, 0.04, 2, 3),
    # ---- Vex
    "vex_feint": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    "vex_sidewinder": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    "vex_tail_sweep": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    # ---- Hops
    "hops_bound_takeoff": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    "hops_bound_land": _c("footstep", 2.0, 0.0, 0.05, 2, 2),
    "hops_double_kick": _c("swing", 1.0, 0.0, 0.05, 2, 3),
    "hops_dropkick": _c("swing", 1.0, 0.0, 0.05, 2, 3),
    "hops_dropkick_crash": _c("impact", -1.0, 0.0, 0.04, 2, 4),
    # ---- Scrap
    "scrap_parry_stance": _c("swing", 0.0, 0.0, 0.03, 2, 4),
    "scrap_leg_sweep": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    "scrap_turnabout": _c("swing", 0.0, 0.0, 0.05, 2, 3),
    # ---- match flow (positional)
    "knockout": _c("impact", -2.0, 0.0, 0.0, 3, 5),
    "respawn": _c("ui", 0.0, -1.0, 0.0, 2, 3),
    "spawn_protect_end": _c("ui", -3.0, -2.0, 0.02, 2, 2),
    # ---- UI / announcer stings (2D)
    "zone_activate": _c("ui", 2.0, 0.0, 0.0, 1, 5),
    "zone_reveal": _c("ui", 0.0, 0.0, 0.0, 1, 5),
    "zone_ally": _c("ui", 1.0, 0.0, 0.0, 1, 5),
    "zone_enemy": _c("ui", 1.0, 0.0, 0.0, 1, 5),
    "zone_contested": _c("ui", 1.0, 0.0, 0.0, 1, 5),
    "score_warning_1": _c("ui", 1.0, 0.0, 0.0, 1, 5),
    "score_warning_2": _c("ui", 1.5, 0.0, 0.0, 1, 5),
    "score_warning_3": _c("ui", 2.0, 0.0, 0.0, 1, 5),
    "countdown_tick": _c("ui", 0.0, 0.0, 0.0, 1, 4),
    "countdown_go": _c("ui", 1.0, 0.0, 0.0, 1, 4),
    "rotation_tick": _c("ui", -2.0, 0.0, 0.0, 1, 4),
    "victory": _c("ui", 0.0, 0.0, 0.0, 1, 4),
    "defeat": _c("ui", 0.0, 0.0, 0.0, 1, 4),
    "sudden_death": _c("ui", 0.0, 0.0, 0.0, 1, 4),
    "ui_hover": _c("ui", -3.0, -3.0, 0.02, 2, 1),
    "ui_select": _c("ui", 0.0, 0.0, 0.0, 2, 2),
    "ui_back": _c("ui", -1.0, 0.0, 0.0, 2, 2),
    "ui_error": _c("ui", 0.0, 0.0, 0.0, 1, 2),
    "ui_lockin": _c("ui", 1.0, 0.0, 0.0, 1, 3),
    "ui_ready": _c("ui", 0.0, 0.0, 0.0, 1, 3),
    "ui_match_found": _c("ui", 1.0, 0.0, 0.0, 1, 4),
    "ui_notify": _c("ui", -1.0, 0.0, 0.0, 1, 2),
    "ui_chat": _c("ui", -3.0, -1.0, 0.0, 2, 1),
    "ui_ping": _c("ui", 0.0, 0.0, 0.0, 3, 3),
    # ---- loops
    "amb_harbor": _c("ambience", 0.0, 0.0, 0.0, 1, 3),
    "amb_market": _c("ambience", 0.0, 0.0, 0.0, 1, 3),
    "amb_yard": _c("ambience", 0.0, 0.0, 0.0, 1, 3),
    "music_menu": _c("music", 0.0, 0.0, 0.0, 1, 3),
    "music_select": _c("music", 0.0, 0.0, 0.0, 1, 3),
    "music_match": _c("music", 0.0, 0.0, 0.0, 1, 3),
    "music_results": _c("music", 0.0, 0.0, 0.0, 1, 3),
}

_BUS_BY_DIR = {"sfx": "SFX", "ui": "UI", "amb": "Ambience", "music": "Music"}


def target_db(cue: str) -> float:
    spec = CUES[cue]
    return LOUDNESS[spec["category"]][0] + spec["rms_offset_db"]


def measure_params(cue: str):
    _, block, hop, gate = LOUDNESS[CUES[cue]["category"]]
    return block, hop, gate


def manifest_entry(cue: str, files: list[str]) -> dict:
    """Manifest record (schema from AUDIO_CONTRACT.md)."""
    spec = CUES[cue]
    folder = files[0].split("/")[0]
    bus = _BUS_BY_DIR[folder]
    loop = folder in ("amb", "music")
    return {
        "files": list(files),
        "bus": bus,
        "volume_db": float(spec["volume_db"]),
        "pitch_rand": float(spec["pitch_rand"]),
        "max_voices": int(spec["max_voices"]),
        "positional": folder == "sfx",
        "priority": int(spec["priority"]),
        "loop": loop,
    }
