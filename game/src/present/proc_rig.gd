class_name ProcRig
extends Node3D
## Procedural stand-in fighter (used only when game/assets/characters/<id>/<id>.glb is
## missing, see D-019): species-specific silhouette built from primitives with a pivot
## hierarchy and data-driven key poses per clip. It reads the same clip names/times as the
## GLB path, so gameplay presentation is identical; only the look is simplified.

const FUR: Dictionary = {
	"nyx": {"fur": Color(0.17, 0.17, 0.19), "light": Color(0.42, 0.41, 0.44), "eye": Color(0.85, 0.78, 0.25), "dark": Color(0.08, 0.08, 0.09)},
	"bruno": {"fur": Color(0.66, 0.47, 0.27), "light": Color(0.9, 0.8, 0.62), "eye": Color(0.3, 0.18, 0.08), "dark": Color(0.2, 0.13, 0.08)},
	"vex": {"fur": Color(0.82, 0.4, 0.14), "light": Color(0.96, 0.93, 0.88), "eye": Color(0.9, 0.62, 0.15), "dark": Color(0.16, 0.1, 0.08)},
	"hops": {"fur": Color(0.8, 0.77, 0.72), "light": Color(0.95, 0.93, 0.9), "eye": Color(0.18, 0.12, 0.1), "dark": Color(0.55, 0.45, 0.45)},
	"scrap": {"fur": Color(0.48, 0.46, 0.44), "light": Color(0.8, 0.78, 0.74), "eye": Color(0.15, 0.1, 0.08), "dark": Color(0.13, 0.12, 0.12)},
}

# joint name -> Node3D pivot
var j: Dictionary = {}
var fid: String = "nyx"
var hscale: float = 1.0
var cloth_mats: Dictionary = {}      # "primary"/"secondary"/"accent"/"trim" -> StandardMaterial3D
var fur_mat: StandardMaterial3D
var all_mats: Array[StandardMaterial3D] = []
var _cur: Dictionary = {}            # smoothed joint values
var _gait: float = 0.0
var _hips_base: float = 0.82
var _tail_n: int = 6

# Neutral combat stance (degrees; see _apply for sign conventions)
const BASE: Dictionary = {"hips_y": 0.0, "hips_pitch": 0.0, "spine": 8.0, "twist": 0.0, "roll": 0.0, "head": -4.0,
	"head_yaw": 0.0, "l_arm": 38.0, "l_abd": 12.0, "l_fore": 72.0, "r_arm": 32.0, "r_abd": 12.0, "r_fore": 78.0,
	"l_leg": 8.0, "l_knee": 14.0, "r_leg": -6.0, "r_knee": 10.0, "l_spread": 4.0, "r_spread": 4.0,
	"tail": 20.0, "tail_wag": 0.0, "ears": 0.0, "jaw": 0.0}

# Key poses: family -> [[t (0..1), {joint: value}], ...]
const POSES: Dictionary = {
	"jab_r": [[0.0, {}], [0.3, {"r_arm": 20.0, "r_fore": 110.0, "twist": 18.0, "spine": 10.0}],
		[0.42, {"r_arm": 88.0, "r_fore": 8.0, "twist": -24.0, "spine": 16.0, "l_arm": 30.0}], [0.7, {"r_arm": 70.0, "r_fore": 30.0, "twist": -12.0}], [1.0, {}]],
	"jab_l": [[0.0, {}], [0.3, {"l_arm": 20.0, "l_fore": 110.0, "twist": -18.0, "spine": 10.0}],
		[0.42, {"l_arm": 88.0, "l_fore": 8.0, "twist": 24.0, "spine": 16.0}], [0.7, {"l_arm": 70.0, "l_fore": 30.0, "twist": 12.0}], [1.0, {}]],
	"hook_r": [[0.0, {}], [0.3, {"r_arm": 40.0, "r_abd": 60.0, "r_fore": 80.0, "twist": 30.0}],
		[0.45, {"r_arm": 85.0, "r_abd": 20.0, "r_fore": 40.0, "twist": -35.0, "spine": 18.0}], [0.75, {"twist": -15.0}], [1.0, {}]],
	"air_swipe": [[0.0, {"l_knee": 60.0, "r_knee": 70.0, "l_leg": 30.0, "r_leg": 20.0}], [0.35, {"r_arm": 150.0, "r_fore": 30.0, "l_knee": 60.0, "r_knee": 70.0, "l_leg": 30.0}],
		[0.55, {"r_arm": 40.0, "r_fore": 10.0, "spine": 30.0, "l_knee": 50.0, "r_knee": 60.0, "l_leg": 25.0}], [1.0, {"l_knee": 40.0, "r_knee": 40.0}]],
	"heavy_smash": [[0.0, {}], [0.4, {"l_arm": 165.0, "r_arm": 165.0, "l_fore": 40.0, "r_fore": 40.0, "spine": -12.0, "head": -10.0, "hips_y": -0.04}],
		[0.5, {"l_arm": 60.0, "r_arm": 60.0, "l_fore": 5.0, "r_fore": 5.0, "spine": 38.0, "hips_y": -0.1, "l_leg": 30.0, "l_knee": 40.0, "r_leg": -20.0}],
		[0.75, {"l_arm": 45.0, "r_arm": 45.0, "spine": 28.0, "hips_y": -0.08, "l_leg": 25.0, "l_knee": 35.0}], [1.0, {}]],
	"heavy_kick": [[0.0, {}], [0.4, {"r_leg": -40.0, "r_knee": 80.0, "spine": -5.0, "l_knee": 20.0}], [0.5, {"r_leg": 95.0, "r_knee": 5.0, "spine": -18.0, "l_knee": 15.0, "l_arm": 60.0}],
		[0.75, {"r_leg": 40.0, "r_knee": 40.0}], [1.0, {}]],
	"crouch": [[0.0, {}], [1.0, {"hips_y": -0.2, "l_knee": 70.0, "r_knee": 70.0, "l_leg": 45.0, "r_leg": 40.0, "spine": 30.0, "l_arm": 50.0, "r_arm": 50.0}]],
	"leap": [[0.0, {"l_leg": 50.0, "r_leg": 20.0, "l_knee": 80.0, "r_knee": 40.0, "spine": 20.0, "l_arm": 120.0, "r_arm": 120.0, "l_fore": 20.0, "r_fore": 20.0}],
		[1.0, {"l_leg": 30.0, "r_leg": 10.0, "l_knee": 60.0, "r_knee": 30.0, "spine": 35.0, "l_arm": 90.0, "r_arm": 90.0, "l_fore": 10.0, "r_fore": 10.0}]],
	"land_strike": [[0.0, {"l_arm": 120.0, "r_arm": 120.0, "spine": 20.0}], [0.3, {"l_arm": 40.0, "r_arm": 40.0, "l_fore": 10.0, "r_fore": 10.0, "spine": 45.0, "hips_y": -0.22, "l_knee": 80.0, "r_knee": 80.0, "l_leg": 50.0, "r_leg": 40.0}],
		[1.0, {}]],
	"stumble": [[0.0, {"spine": 30.0, "hips_y": -0.1, "l_knee": 40.0, "r_knee": 40.0}], [0.4, {"spine": 40.0, "hips_y": -0.15, "l_knee": 60.0, "r_knee": 50.0, "l_arm": 60.0, "r_arm": 40.0, "l_abd": 40.0, "r_abd": 40.0}], [1.0, {}]],
	"crosscut": [[0.0, {}], [0.18, {"r_arm": 120.0, "r_abd": 50.0, "twist": 25.0}], [0.28, {"r_arm": 50.0, "r_abd": -10.0, "twist": -25.0, "spine": 18.0}],
		[0.46, {"l_arm": 120.0, "l_abd": 50.0, "twist": -25.0}], [0.56, {"l_arm": 50.0, "l_abd": -10.0, "twist": 25.0, "spine": 18.0}], [1.0, {}]],
	"sidestep_l": [[0.0, {}], [0.4, {"roll": -18.0, "hips_y": -0.12, "l_leg": 10.0, "l_spread": 30.0, "r_knee": 40.0, "twist": 20.0}], [1.0, {}]],
	"sidestep_r": [[0.0, {}], [0.4, {"roll": 18.0, "hips_y": -0.12, "r_leg": 10.0, "r_spread": 30.0, "l_knee": 40.0, "twist": -20.0}], [1.0, {}]],
	"sidestep_b": [[0.0, {}], [0.4, {"spine": -10.0, "hips_y": -0.1, "l_knee": 40.0, "r_knee": 40.0, "l_leg": -20.0}], [1.0, {}]],
	"spin_strike": [[0.0, {"twist": 40.0}], [0.3, {"twist": -60.0, "r_arm": 90.0, "r_abd": 40.0, "r_fore": 10.0, "spine": 20.0}], [1.0, {}]],
	"charge": [[0.0, {"spine": 42.0, "head": -30.0, "r_arm": 20.0, "r_abd": 30.0, "l_arm": 60.0, "l_fore": 90.0, "hips_y": -0.1, "twist": 20.0}],
		[1.0, {"spine": 42.0, "head": -30.0, "r_arm": 20.0, "r_abd": 30.0, "l_arm": 60.0, "l_fore": 90.0, "hips_y": -0.1, "twist": 20.0}]],
	"shoulder": [[0.0, {"spine": 45.0, "twist": 35.0, "r_abd": 40.0}], [0.4, {"spine": 20.0, "twist": -10.0}], [1.0, {}]],
	"recoil": [[0.0, {"spine": -25.0, "head": 20.0, "l_arm": 70.0, "r_arm": 70.0, "hips_y": -0.05}], [1.0, {}]],
	"bark": [[0.0, {}], [0.25, {"spine": 25.0, "head": -20.0, "jaw": 35.0, "ears": -40.0, "l_arm": 10.0, "r_arm": 10.0, "l_abd": 30.0, "r_abd": 30.0, "hips_y": -0.05}],
		[0.6, {"spine": 22.0, "head": -18.0, "jaw": 30.0, "ears": -40.0, "l_abd": 30.0, "r_abd": 30.0}], [1.0, {}]],
	"stance": [[0.0, {"hips_y": -0.14, "l_spread": 26.0, "r_spread": 26.0, "l_knee": 50.0, "r_knee": 50.0, "l_leg": 20.0, "r_leg": 20.0, "l_arm": 70.0, "r_arm": 70.0, "l_fore": 100.0, "r_fore": 100.0, "l_abd": 30.0, "r_abd": 30.0, "spine": 12.0}],
		[1.0, {"hips_y": -0.14, "l_spread": 26.0, "r_spread": 26.0, "l_knee": 50.0, "r_knee": 50.0, "l_leg": 20.0, "r_leg": 20.0, "l_arm": 70.0, "r_arm": 70.0, "l_fore": 100.0, "r_fore": 100.0, "l_abd": 30.0, "r_abd": 30.0, "spine": 12.0}]],
	"dash": [[0.0, {"spine": 35.0, "hips_y": -0.1, "l_arm": -20.0, "r_arm": -30.0, "l_leg": 40.0, "l_knee": 50.0, "r_leg": -30.0}],
		[1.0, {"spine": 35.0, "hips_y": -0.1, "l_arm": -20.0, "r_arm": -30.0, "l_leg": 40.0, "l_knee": 50.0, "r_leg": -30.0}]],
	"tail_spin": [[0.0, {}], [0.3, {"twist": 60.0, "hips_y": -0.15, "l_knee": 50.0, "r_knee": 50.0, "tail_wag": -60.0}],
		[0.5, {"twist": -80.0, "hips_y": -0.18, "l_knee": 55.0, "r_knee": 55.0, "tail_wag": 80.0, "tail": -10.0}], [1.0, {}]],
	"double_kick": [[0.0, {}], [0.17, {"r_leg": 100.0, "r_knee": 5.0, "spine": -15.0, "l_knee": 20.0}], [0.3, {"r_leg": 10.0, "r_knee": 40.0}],
		[0.5, {"l_leg": 105.0, "l_knee": 5.0, "spine": -15.0, "r_knee": 20.0}], [0.7, {"l_leg": 20.0, "l_knee": 30.0}], [1.0, {}]],
	"dropkick": [[0.0, {"spine": -50.0, "l_leg": 85.0, "r_leg": 85.0, "l_knee": 0.0, "r_knee": 0.0, "l_arm": 120.0, "r_arm": 120.0, "hips_pitch": -30.0}],
		[1.0, {"spine": -55.0, "l_leg": 90.0, "r_leg": 90.0, "l_knee": 0.0, "r_knee": 0.0, "l_arm": 130.0, "r_arm": 130.0, "hips_pitch": -35.0}]],
	"crash": [[0.0, {"hips_y": -0.6, "hips_pitch": -70.0, "spine": -10.0, "l_leg": 60.0, "r_leg": 50.0}], [0.6, {"hips_y": -0.45, "hips_pitch": -40.0, "l_knee": 60.0}], [1.0, {}]],
	"parry_stance": [[0.0, {}], [0.4, {"l_arm": 80.0, "l_fore": 60.0, "l_abd": 20.0, "r_arm": 60.0, "r_fore": 90.0, "twist": 15.0, "hips_y": -0.06, "l_knee": 30.0, "r_knee": 30.0}],
		[1.0, {"l_arm": 80.0, "l_fore": 60.0, "l_abd": 20.0, "r_arm": 60.0, "r_fore": 90.0, "twist": 15.0, "hips_y": -0.06, "l_knee": 30.0, "r_knee": 30.0}]],
	"counter": [[0.0, {"l_arm": 80.0, "twist": 15.0}], [0.35, {"twist": -50.0, "r_arm": 95.0, "r_fore": 10.0, "spine": 20.0}], [1.0, {}]],
	"leg_sweep": [[0.0, {}], [0.3, {"hips_y": -0.35, "l_knee": 100.0, "l_leg": 70.0, "r_leg": 50.0, "r_spread": 50.0, "r_knee": 5.0, "twist": 40.0, "spine": 30.0}],
		[0.45, {"hips_y": -0.35, "l_knee": 100.0, "l_leg": 70.0, "r_leg": 50.0, "r_spread": 60.0, "r_knee": 5.0, "twist": -60.0, "spine": 30.0}], [1.0, {}]],
	"grab_reach": [[0.0, {}], [0.5, {"l_arm": 85.0, "r_arm": 85.0, "l_fore": 10.0, "r_fore": 10.0, "spine": 25.0, "hips_y": -0.05}], [1.0, {"l_arm": 80.0, "r_arm": 80.0, "l_fore": 20.0, "r_fore": 20.0, "spine": 20.0}]],
	"grapple": [[0.0, {"l_arm": 80.0, "r_arm": 80.0, "l_fore": 40.0, "r_fore": 40.0, "twist": 30.0}], [1.0, {"l_arm": 80.0, "r_arm": 80.0, "l_fore": 40.0, "r_fore": 40.0, "twist": -90.0, "spine": 15.0}]],
	"throw": [[0.0, {"twist": -90.0, "l_arm": 80.0, "r_arm": 80.0}], [0.5, {"twist": -40.0, "l_arm": 40.0, "r_arm": 100.0, "r_abd": 50.0}], [1.0, {}]],
	"hit_front": [[0.0, {}], [0.25, {"spine": -20.0, "head": 25.0, "hips_y": -0.03, "l_arm": 20.0, "r_arm": 20.0, "l_abd": 30.0, "r_abd": 30.0}], [1.0, {}]],
	"hit_back": [[0.0, {}], [0.25, {"spine": 30.0, "head": -20.0, "hips_y": -0.03}], [1.0, {}]],
	"hit_heavy": [[0.0, {}], [0.25, {"spine": -35.0, "head": 35.0, "hips_y": -0.08, "l_arm": 50.0, "r_arm": 50.0, "l_abd": 50.0, "r_abd": 50.0, "l_knee": 30.0}], [1.0, {}]],
	"stagger": [[0.0, {"spine": -15.0, "roll": 10.0}], [0.3, {"spine": 20.0, "roll": -12.0, "head": 10.0, "l_arm": 20.0, "r_arm": 50.0, "l_abd": 40.0, "r_abd": 40.0}],
		[0.6, {"spine": 5.0, "roll": 8.0, "hips_y": -0.05, "l_knee": 30.0}], [1.0, {}]],
	"knockdown": [[0.0, {"spine": -20.0}], [0.4, {"hips_y": -0.55, "hips_pitch": 70.0, "spine": -5.0, "l_leg": 40.0, "r_leg": 30.0, "l_knee": 20.0, "l_arm": 100.0, "r_arm": 80.0, "l_abd": 40.0, "r_abd": 40.0}],
		[1.0, {"hips_y": -0.68, "hips_pitch": 85.0, "spine": 0.0, "l_leg": 20.0, "r_leg": 10.0, "l_knee": 30.0, "r_knee": 10.0, "l_arm": 110.0, "r_arm": 100.0, "l_abd": 60.0, "r_abd": 60.0, "tail": 0.0}]],
	"getup": [[0.0, {"hips_y": -0.68, "hips_pitch": 85.0, "l_arm": 110.0, "r_arm": 100.0}], [0.5, {"hips_y": -0.35, "hips_pitch": 20.0, "spine": 40.0, "l_knee": 90.0, "r_knee": 90.0, "l_leg": 70.0, "r_leg": 60.0}], [1.0, {}]],
	"grabbed": [[0.0, {"spine": -20.0, "l_arm": 120.0, "r_arm": 100.0, "l_abd": 40.0, "r_abd": 50.0, "l_leg": 30.0, "l_knee": 50.0, "r_knee": 40.0, "hips_y": 0.05}],
		[1.0, {"spine": -10.0, "l_arm": 80.0, "r_arm": 130.0, "l_abd": 60.0, "r_abd": 30.0, "r_leg": 30.0, "r_knee": 50.0, "l_knee": 20.0, "hips_y": 0.05}]],
	"guard_break": [[0.0, {"l_arm": 120.0, "r_arm": 120.0, "l_abd": 60.0, "r_abd": 60.0, "spine": -25.0, "head": 20.0}], [0.4, {"spine": 10.0, "head": -10.0, "hips_y": -0.1, "l_knee": 40.0, "r_knee": 40.0, "l_arm": 20.0, "r_arm": 20.0}],
		[1.0, {"spine": 20.0, "hips_y": -0.08, "l_arm": 10.0, "r_arm": 10.0, "l_fore": 20.0, "r_fore": 20.0, "head": 10.0}]],
	"guard": [[0.0, {"l_arm": 95.0, "l_abd": -5.0, "l_fore": 115.0, "r_arm": 92.0, "r_abd": -8.0, "r_fore": 118.0, "spine": 14.0, "head": 8.0, "hips_y": -0.04, "l_knee": 25.0, "r_knee": 20.0}],
		[1.0, {"l_arm": 95.0, "l_abd": -5.0, "l_fore": 115.0, "r_arm": 92.0, "r_abd": -8.0, "r_fore": 118.0, "spine": 14.0, "head": 8.0, "hips_y": -0.04, "l_knee": 25.0, "r_knee": 20.0}]],
	"guard_block": [[0.0, {"l_arm": 95.0, "l_fore": 115.0, "r_arm": 92.0, "r_fore": 118.0, "spine": -2.0, "head": 14.0, "hips_y": -0.07, "l_knee": 30.0, "r_knee": 30.0}],
		[1.0, {"l_arm": 95.0, "l_fore": 115.0, "r_arm": 92.0, "r_fore": 118.0, "spine": 14.0, "head": 8.0, "hips_y": -0.04, "l_knee": 25.0, "r_knee": 20.0}]],
	"dodge_f": [[0.0, {}], [0.3, {"spine": 45.0, "hips_y": -0.3, "l_knee": 90.0, "r_knee": 90.0, "l_leg": 70.0, "r_leg": 60.0, "l_arm": 60.0, "r_arm": 60.0}], [0.7, {"spine": 35.0, "hips_y": -0.22, "l_knee": 70.0, "r_knee": 70.0, "l_leg": 50.0, "r_leg": 40.0}], [1.0, {}]],
	"dodge_b": [[0.0, {}], [0.3, {"spine": -10.0, "hips_y": -0.2, "l_knee": 60.0, "r_knee": 60.0, "l_leg": 10.0, "r_leg": 0.0}], [1.0, {}]],
	"dodge_l": [[0.0, {}], [0.3, {"roll": -30.0, "hips_y": -0.22, "l_spread": 35.0, "r_knee": 60.0, "spine": 15.0}], [1.0, {}]],
	"dodge_r": [[0.0, {}], [0.3, {"roll": 30.0, "hips_y": -0.22, "r_spread": 35.0, "l_knee": 60.0, "spine": 15.0}], [1.0, {}]],
	"jump": [[0.0, {"l_leg": 40.0, "l_knee": 70.0, "r_leg": 10.0, "r_knee": 40.0, "l_arm": 70.0, "r_arm": 60.0, "spine": 5.0}], [1.0, {"l_leg": 40.0, "l_knee": 70.0, "r_leg": 10.0, "r_knee": 40.0, "l_arm": 70.0, "r_arm": 60.0, "spine": 5.0}]],
	"fall": [[0.0, {"l_leg": 20.0, "l_knee": 30.0, "r_leg": 5.0, "r_knee": 20.0, "l_arm": 90.0, "r_arm": 85.0, "l_abd": 30.0, "r_abd": 30.0, "spine": -5.0}], [1.0, {"l_leg": 20.0, "l_knee": 30.0, "r_leg": 5.0, "r_knee": 20.0, "l_arm": 90.0, "r_arm": 85.0, "l_abd": 30.0, "r_abd": 30.0}]],
	"land": [[0.0, {"hips_y": -0.18, "l_knee": 70.0, "r_knee": 70.0, "l_leg": 45.0, "r_leg": 40.0, "spine": 25.0}], [1.0, {}]],
	"perch_climb": [[0.0, {"l_arm": 170.0, "r_arm": 160.0, "l_fore": 30.0, "r_fore": 30.0, "l_leg": 60.0, "l_knee": 90.0, "hips_y": 0.1}],
		[0.6, {"l_arm": 60.0, "r_arm": 60.0, "l_leg": 90.0, "l_knee": 110.0, "r_leg": 30.0, "r_knee": 60.0, "spine": 40.0, "hips_y": 0.0}], [1.0, {}]],
	"knockout": [[0.0, {"spine": -25.0, "head": 20.0}], [0.5, {"hips_y": -0.5, "l_knee": 110.0, "r_knee": 100.0, "l_leg": 90.0, "r_leg": 85.0, "spine": 30.0, "head": 30.0, "l_arm": 10.0, "r_arm": 10.0, "l_fore": 20.0, "r_fore": 20.0}],
		[1.0, {"hips_y": -0.62, "hips_pitch": 20.0, "l_knee": 20.0, "r_knee": 10.0, "l_leg": 85.0, "r_leg": 80.0, "spine": 35.0, "head": 40.0, "l_arm": 0.0, "r_arm": 0.0, "l_abd": 20.0, "r_abd": 20.0, "l_fore": 10.0, "r_fore": 10.0, "tail": -10.0, "ears": -30.0}]],
	"respawn": [[0.0, {"hips_y": -0.3, "l_knee": 80.0, "r_knee": 80.0, "l_leg": 60.0, "r_leg": 55.0, "spine": 35.0, "head": 20.0}], [1.0, {}]],
	"victory": [[0.0, {"l_arm": 170.0, "r_arm": 160.0, "l_abd": 20.0, "r_abd": 25.0, "l_fore": 10.0, "r_fore": 20.0, "spine": -10.0, "head": -20.0, "tail": 50.0}],
		[0.5, {"l_arm": 160.0, "r_arm": 170.0, "l_abd": 30.0, "r_abd": 15.0, "l_fore": 20.0, "r_fore": 10.0, "spine": -12.0, "head": -25.0, "tail": 55.0, "tail_wag": 30.0, "hips_y": 0.03}],
		[1.0, {"l_arm": 170.0, "r_arm": 160.0, "l_abd": 20.0, "r_abd": 25.0, "l_fore": 10.0, "r_fore": 20.0, "spine": -10.0, "head": -20.0, "tail": 50.0, "tail_wag": -30.0}]],
	"defeat": [[0.0, {}], [1.0, {"spine": 30.0, "head": 35.0, "l_arm": 5.0, "r_arm": 5.0, "l_fore": 10.0, "r_fore": 10.0, "l_abd": 5.0, "r_abd": 5.0, "tail": -20.0, "ears": -35.0}]],
	"select": [[0.0, {"l_arm": 60.0, "l_fore": 100.0, "r_arm": 20.0, "r_fore": 40.0, "twist": 12.0, "head": -8.0, "head_yaw": -10.0, "tail": 35.0}],
		[1.0, {"l_arm": 62.0, "l_fore": 102.0, "r_arm": 22.0, "r_fore": 42.0, "twist": 14.0, "head": -10.0, "head_yaw": -12.0, "tail": 38.0, "tail_wag": 15.0}]],
}

# (fighter, clip) -> family; generic clip names fall back to CLIP_FAMILY
const FIGHTER_CLIPS: Dictionary = {
	"nyx": {"skill_q_prep": "crouch", "skill_q_air": "leap", "skill_q_land": "land_strike", "skill_q_land_miss": "stumble",
		"skill_e": "crosscut", "skill_r_left": "sidestep_l", "skill_r_right": "sidestep_r", "skill_r_counter": "spin_strike"},
	"bruno": {"skill_q_windup": "crouch", "skill_q_charge": "charge", "skill_q_hit": "shoulder", "skill_q_miss": "stumble",
		"skill_q_wall": "recoil", "skill_e": "bark", "skill_r_enter": "stance", "skill_r_hold": "stance", "skill_r_exit": "stance",
		"skill_r_block": "stance", "light_r": "hook_r"},
	"vex": {"skill_q_step_l": "sidestep_l", "skill_q_step_r": "sidestep_r", "skill_q_step_b": "sidestep_b", "skill_e_windup": "crouch",
		"skill_e_dash_l": "dash", "skill_e_dash_r": "dash", "skill_e_strike": "jab_r", "skill_e_recover": "land", "skill_r": "tail_spin"},
	"hops": {"skill_q_crouch": "crouch", "skill_q_air": "leap", "skill_q_land": "land", "skill_e": "double_kick",
		"skill_r_hop": "crouch", "skill_r_flight": "dropkick", "skill_r_land": "land", "skill_r_crash": "crash", "heavy": "heavy_kick"},
	"scrap": {"skill_q_stance": "parry_stance", "skill_q_success": "counter", "skill_q_whiff": "stumble", "skill_e": "leg_sweep",
		"skill_r_reach": "grab_reach", "skill_r_grapple": "grapple", "skill_r_release": "throw", "skill_r_whiff": "stumble"},
}
const CLIP_FAMILY: Dictionary = {
	"light_s": "jab_r", "light_l": "jab_l", "light_r": "hook_r", "light_air": "air_swipe", "heavy": "heavy_smash",
	"hit_front": "hit_front", "hit_back": "hit_back", "hit_heavy": "hit_heavy", "stagger": "stagger", "knockdown": "knockdown",
	"getup": "getup", "grabbed": "grabbed", "guard_break": "guard_break", "guard_hold": "guard", "guard_enter": "guard",
	"guard_exit": "guard", "guard_block": "guard_block", "dodge_f": "dodge_f", "dodge_b": "dodge_b", "dodge_l": "dodge_l",
	"dodge_r": "dodge_r", "jump_start": "crouch", "jump_air": "jump", "jump_fall": "fall", "jump_land": "land",
	"perch_climb": "perch_climb", "knockout": "knockout", "respawn": "respawn", "victory": "victory", "defeat": "defeat",
	"select": "select", "skill_r_counter": "spin_strike",
}


func build(p_fid: String, height: float, palette: Dictionary) -> void:
	fid = p_fid
	hscale = height / 1.7
	var col: Dictionary = FUR.get(fid, FUR["nyx"])
	fur_mat = _mat(col["fur"], 0.9)
	var light_mat: StandardMaterial3D = _mat(col["light"], 0.9)
	var dark_mat: StandardMaterial3D = _mat(col["dark"], 0.8)
	var eye_mat: StandardMaterial3D = _mat(col["eye"], 0.2)
	var pupil_mat: StandardMaterial3D = _mat(Color(0.03, 0.03, 0.03), 0.15)
	for k in ["primary", "secondary", "accent", "trim"]:
		cloth_mats[k] = _mat(Color.html(String(palette.get(k, "#444444"))), 0.75)
	var s: float = hscale
	var broad: float = 1.15 if fid == "bruno" else (0.92 if fid == "nyx" or fid == "hops" else 1.0)
	_hips_base = 0.82 * s
	# --- hierarchy -------------------------------------------------------------------------
	var hips := _pivot("hips", self, Vector3(0, _hips_base, 0))
	var spine := _pivot("spine", hips, Vector3(0, 0.02 * s, 0))
	var neck := _pivot("head", spine, Vector3(0, 0.62 * s, -0.02 * s))
	var jaw := _pivot("jaw", neck, Vector3(0, 0.08 * s, -0.1 * s))
	var l_sh := _pivot("l_arm", spine, Vector3(-0.2 * s * broad, 0.48 * s, 0))
	var r_sh := _pivot("r_arm", spine, Vector3(0.2 * s * broad, 0.48 * s, 0))
	var l_el := _pivot("l_fore", l_sh, Vector3(0, -0.28 * s, 0))
	var r_el := _pivot("r_fore", r_sh, Vector3(0, -0.28 * s, 0))
	var l_hip := _pivot("l_leg", hips, Vector3(-0.1 * s * broad, -0.02 * s, 0))
	var r_hip := _pivot("r_leg", hips, Vector3(0.1 * s * broad, -0.02 * s, 0))
	var l_kn := _pivot("l_knee", l_hip, Vector3(0, -0.4 * s, 0))
	var r_kn := _pivot("r_knee", r_hip, Vector3(0, -0.4 * s, 0))
	var ears := _pivot("ears", neck, Vector3(0, 0.12 * s, 0.01 * s))
	# --- body --------------------------------------------------------------------------------
	_capsule(hips, 0.15 * s * broad, 0.3 * s, Vector3(0, 0.02 * s, 0), fur_mat, Vector3(0, 0, 90))            # pelvis
	_capsule(spine, 0.17 * s * broad, 0.58 * s, Vector3(0, 0.3 * s, 0), fur_mat)                               # torso
	_capsule(spine, 0.13 * s * broad, 0.34 * s, Vector3(0, 0.32 * s, -0.08 * s), light_mat)                     # chest fur
	# clothing: vest / jacket (primary), belt (secondary), shorts (secondary), accents
	var vest: MeshInstance3D = _capsule(spine, 0.185 * s * broad, 0.46 * s, Vector3(0, 0.36 * s, 0.01 * s), cloth_mats["primary"])
	vest.scale = Vector3(1.0, 1.0, 0.92)
	_cylinder(spine, 0.18 * s * broad, 0.07 * s, Vector3(0, 0.1 * s, 0), cloth_mats["secondary"])             # belt
	_box(spine, Vector3(0.07, 0.05, 0.03) * s, Vector3(0, 0.1 * s, -0.17 * s * broad), cloth_mats["trim"])    # buckle
	_capsule(l_hip, 0.085 * s * broad, 0.3 * s, Vector3(0, -0.15 * s, 0), cloth_mats["secondary"])            # shorts
	_capsule(r_hip, 0.085 * s * broad, 0.3 * s, Vector3(0, -0.15 * s, 0), cloth_mats["secondary"])
	match fid:
		"nyx":
			_capsule(neck, 0.075 * s, 0.34 * s, Vector3(0, -0.06 * s, 0.02 * s), cloth_mats["accent"], Vector3(0, 0, 90))  # scarf
		"vex":
			_sphere(r_sh, 0.085 * s, Vector3(0.02 * s, 0.0, 0), cloth_mats["accent"], Vector3(1.1, 0.7, 1.1))              # copper panel (right)
		"bruno":
			_capsule(l_el, 0.058 * s, 0.16 * s, Vector3(0, -0.12 * s, 0), cloth_mats["accent"])                             # wraps
			_capsule(r_el, 0.058 * s, 0.16 * s, Vector3(0, -0.12 * s, 0), cloth_mats["accent"])
		"hops":
			_cylinder(neck, 0.1 * s, 0.03 * s, Vector3(0, 0.1 * s, 0), cloth_mats["accent"])                                # headband
		"scrap":
			_box(spine, Vector3(0.1, 0.1, 0.05) * s, Vector3(0.12 * s, 0.1 * s, -0.16 * s), cloth_mats["accent"])            # tool pouch
			_box(spine, Vector3(0.08, 0.08, 0.04) * s, Vector3(-0.1 * s, 0.4 * s, -0.17 * s), cloth_mats["trim"])            # patch
	# arms: upper (sleeve = primary), forearm fur, paw
	for side in [[l_sh, l_el], [r_sh, r_el]]:
		_capsule(side[0], 0.065 * s, 0.3 * s, Vector3(0, -0.14 * s, 0), cloth_mats["primary"])
		_capsule(side[1], 0.052 * s, 0.28 * s, Vector3(0, -0.13 * s, 0), fur_mat)
		_sphere(side[1], 0.062 * s, Vector3(0, -0.28 * s, -0.01 * s), light_mat if fid != "scrap" else dark_mat, Vector3(1.0, 0.85, 1.1))
	# legs: shin fur + foot
	for kn in [l_kn, r_kn]:
		_capsule(kn, 0.065 * s, 0.4 * s, Vector3(0, -0.19 * s, 0), fur_mat)
		_capsule(kn, 0.055 * s, 0.2 * s, Vector3(0, -0.37 * s, -0.06 * s), light_mat if fid != "scrap" else dark_mat, Vector3(90, 0, 0))
	# --- head ---------------------------------------------------------------------------------
	var head_r: float = 0.15 * s
	_sphere(neck, head_r, Vector3(0, 0.02 * s, 0), fur_mat, Vector3(1.0, 0.95, 1.0))
	_capsule(neck, 0.06 * s, 0.14 * s, Vector3(0, -0.1 * s, 0.01 * s), fur_mat)                                # neck
	var muzzle_len: float = {"nyx": 0.07, "bruno": 0.12, "vex": 0.14, "hops": 0.07, "scrap": 0.09}.get(fid, 0.08) * s
	_sphere(jaw, 0.07 * s, Vector3(0, -0.02 * s, -muzzle_len * 0.5), light_mat, Vector3(1.0, 0.7, 1.0 + muzzle_len / (0.07 * s)))
	_sphere(neck, 0.022 * s, Vector3(0, 0.06 * s, -0.1 * s - muzzle_len), dark_mat)                                     # nose
	for sx in [-1.0, 1.0]:
		var ex: float = sx * 0.062 * s
		_sphere(neck, 0.034 * s, Vector3(ex, 0.07 * s, -0.12 * s), eye_mat)
		var pupil_scale := Vector3(0.45, 1.0, 0.5) if fid == "nyx" or fid == "vex" else Vector3(0.8, 0.8, 0.5)
		_sphere(neck, 0.02 * s, Vector3(ex, 0.07 * s, -0.148 * s), pupil_mat, pupil_scale)
		if fid == "scrap":
			_sphere(neck, 0.055 * s, Vector3(ex, 0.07 * s, -0.095 * s), dark_mat, Vector3(1.3, 0.7, 0.6))          # mask
	# ears
	for sx2 in [-1.0, 1.0]:
		match fid:
			"nyx":
				_cone(ears, 0.05 * s, 0.13 * s, Vector3(sx2 * 0.08 * s, 0.03 * s, 0), fur_mat, Vector3(0, 0, -sx2 * 18.0))
			"vex":
				_cone(ears, 0.065 * s, 0.17 * s, Vector3(sx2 * 0.085 * s, 0.04 * s, 0), fur_mat, Vector3(0, 0, -sx2 * 16.0))
			"hops":
				_capsule(ears, 0.04 * s, 0.34 * s, Vector3(sx2 * 0.05 * s, 0.16 * s, 0.01 * s), fur_mat, Vector3(-8, 0, -sx2 * 8.0), Vector3(1.0, 1.0, 0.55))
			"bruno":
				_sphere(ears, 0.07 * s, Vector3(sx2 * 0.14 * s, -0.08 * s, 0.01 * s), dark_mat, Vector3(0.45, 1.3, 0.9))
			"scrap":
				_sphere(ears, 0.055 * s, Vector3(sx2 * 0.1 * s, 0.03 * s, 0.01 * s), fur_mat, Vector3(1.0, 1.0, 0.45))
	# tail
	var tail_spec: Array = {"nyx": [6, 0.028, 0.15], "vex": [6, 0.07, 0.13], "scrap": [6, 0.06, 0.12], "bruno": [3, 0.035, 0.1], "hops": [1, 0.075, 0.05]}.get(fid, [4, 0.04, 0.12])
	_tail_n = int(tail_spec[0])
	var parent: Node3D = _pivot("tail0", hips, Vector3(0, 0.02 * s, 0.13 * s))
	for i in range(_tail_n):
		var r: float = float(tail_spec[1]) * s * (1.0 - 0.08 * i if fid != "vex" else (0.8 + 0.25 * sin(float(i) / _tail_n * PI)))
		var ln: float = float(tail_spec[2]) * s
		var mat: StandardMaterial3D = fur_mat
		if fid == "scrap" and i % 2 == 1:
			mat = dark_mat
		if fid == "vex" and i == _tail_n - 1:
			mat = light_mat
		if fid == "hops":
			_sphere(parent, r, Vector3(0, 0, r * 0.6), light_mat)
		else:
			_capsule(parent, r, ln + r * 2.0, Vector3(0, 0, ln * 0.5), mat, Vector3(90, 0, 0))
		if i < _tail_n - 1:
			parent = _pivot("tail%d" % (i + 1), parent, Vector3(0, 0, ln))
	_cur = BASE.duplicate()
	_apply(_cur)


func set_palette(palette: Dictionary) -> void:
	for k in cloth_mats.keys():
		(cloth_mats[k] as StandardMaterial3D).albedo_color = Color.html(String(palette.get(k, "#444444")))


func set_flash(amount: float, color: Color) -> void:
	## Brief emissive flash (hit confirm / guard / protection). amount 0..1
	for m in all_mats:
		m.emission_enabled = amount > 0.01
		m.emission = color
		m.emission_energy_multiplier = amount * 1.6


func set_alpha(a: float) -> void:
	for m in all_mats:
		m.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED if a >= 0.99 else BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
		m.albedo_color.a = a


# ------------------------------------------------------------------------------------------
# posing
# ------------------------------------------------------------------------------------------
func family_for(clip: String) -> String:
	var fc: Dictionary = FIGHTER_CLIPS.get(fid, {})
	if fc.has(clip):
		return String(fc[clip])
	return String(CLIP_FAMILY.get(clip, ""))


func pose(clip: String, tn: float, loco: Vector3, grounded: bool, dt: float, sharp: float = 18.0) -> void:
	## clip: current clip name ("" = locomotion); tn: normalized clip time 0..1;
	## loco: local velocity (x right, z forward, y vertical) in m/s.
	var target: Dictionary = BASE.duplicate()
	var fam: String = family_for(clip) if clip != "" else ""
	if fam != "" and POSES.has(fam):
		_sample_family(fam, clamp(tn, 0.0, 1.0), target)
	else:
		_locomotion(loco, grounded, dt, target)
	# idle breathing + tail sway (always)
	var t: float = float(Time.get_ticks_msec()) / 1000.0
	target["spine"] = float(target["spine"]) + sin(t * 1.9) * 1.2
	target["tail_wag"] = float(target["tail_wag"]) + sin(t * 1.3 + float(get_instance_id() % 7)) * 12.0
	var k: float = 1.0 - exp(-sharp * dt)
	for key in target.keys():
		_cur[key] = lerpf(float(_cur.get(key, 0.0)), float(target[key]), k)
	_apply(_cur)


func _sample_family(fam: String, tn: float, out: Dictionary) -> void:
	var keys: Array = POSES[fam]
	var a: Array = keys[0]
	var b: Array = keys[keys.size() - 1]
	for i in range(keys.size() - 1):
		if tn >= float(keys[i][0]) and tn <= float(keys[i + 1][0]):
			a = keys[i]
			b = keys[i + 1]
			break
	var span: float = maxf(0.0001, float(b[0]) - float(a[0]))
	var u: float = clampf((tn - float(a[0])) / span, 0.0, 1.0)
	u = u * u * (3.0 - 2.0 * u)
	var da: Dictionary = a[1]
	var db: Dictionary = b[1]
	for key in BASE.keys():
		var va: float = float(da.get(key, BASE[key]))
		var vb: float = float(db.get(key, BASE[key]))
		out[key] = lerpf(va, vb, u)


func _locomotion(v: Vector3, grounded: bool, dt: float, out: Dictionary) -> void:
	var speed: float = Vector2(v.x, v.z).length()
	if not grounded:
		_sample_family("jump" if v.y > 0.5 else "fall", 0.5, out)
		return
	if speed < 0.25:
		return
	var run: float = clampf((speed - 1.0) / 4.0, 0.0, 1.0)
	var freq: float = lerpf(1.6, 2.6, run) * (speed / maxf(1.0, lerpf(2.0, 7.0, run)))
	_gait = fmod(_gait + dt * freq * TAU * 0.5 * clampf(speed / 2.0, 0.6, 3.2), TAU)
	var sw: float = sin(_gait)
	var fwd: float = v.z / maxf(speed, 0.01)
	var side: float = v.x / maxf(speed, 0.01)
	var amp: float = lerpf(25.0, 48.0, run)
	out["l_leg"] = sw * amp * fwd + 5.0
	out["r_leg"] = -sw * amp * fwd + 5.0
	out["l_knee"] = 15.0 + maxf(0.0, -sw) * lerpf(30.0, 75.0, run)
	out["r_knee"] = 15.0 + maxf(0.0, sw) * lerpf(30.0, 75.0, run)
	out["l_spread"] = 4.0 + maxf(0.0, -side * sw) * 20.0
	out["r_spread"] = 4.0 + maxf(0.0, side * sw) * 20.0
	out["l_arm"] = lerpf(38.0, 20.0, run) - sw * lerpf(10.0, 35.0, run) * fwd
	out["r_arm"] = lerpf(32.0, 20.0, run) + sw * lerpf(10.0, 35.0, run) * fwd
	out["l_fore"] = lerpf(72.0, 95.0, run)
	out["r_fore"] = lerpf(78.0, 95.0, run)
	out["spine"] = lerpf(8.0, 22.0, run) * fwd + 6.0
	out["roll"] = -side * lerpf(4.0, 10.0, run)
	out["hips_y"] = absf(cos(_gait)) * lerpf(0.015, 0.05, run) - lerpf(0.0, 0.04, run)
	out["twist"] = sw * lerpf(4.0, 10.0, run)
	out["tail"] = lerpf(20.0, 5.0, run)


func _apply(p: Dictionary) -> void:
	var d2r: float = PI / 180.0
	(j["hips"] as Node3D).position.y = _hips_base + float(p["hips_y"]) * hscale
	(j["hips"] as Node3D).rotation = Vector3(float(p["hips_pitch"]) * d2r, 0, float(p["roll"]) * d2r)
	(j["spine"] as Node3D).rotation = Vector3(-float(p["spine"]) * d2r, float(p["twist"]) * d2r, 0)
	(j["head"] as Node3D).rotation = Vector3(-float(p["head"]) * d2r, float(p["head_yaw"]) * d2r, 0)
	(j["jaw"] as Node3D).rotation = Vector3(float(p["jaw"]) * d2r * 0.5, 0, 0)
	(j["ears"] as Node3D).rotation = Vector3(-float(p["ears"]) * d2r, 0, 0)
	(j["l_arm"] as Node3D).rotation = Vector3(float(p["l_arm"]) * d2r, 0, -float(p["l_abd"]) * d2r)
	(j["r_arm"] as Node3D).rotation = Vector3(float(p["r_arm"]) * d2r, 0, float(p["r_abd"]) * d2r)
	(j["l_fore"] as Node3D).rotation = Vector3(float(p["l_fore"]) * d2r, 0, 0)
	(j["r_fore"] as Node3D).rotation = Vector3(float(p["r_fore"]) * d2r, 0, 0)
	(j["l_leg"] as Node3D).rotation = Vector3(float(p["l_leg"]) * d2r, 0, -float(p["l_spread"]) * d2r)
	(j["r_leg"] as Node3D).rotation = Vector3(float(p["r_leg"]) * d2r, 0, float(p["r_spread"]) * d2r)
	(j["l_knee"] as Node3D).rotation = Vector3(-float(p["l_knee"]) * d2r, 0, 0)
	(j["r_knee"] as Node3D).rotation = Vector3(-float(p["r_knee"]) * d2r, 0, 0)
	var tail_up: float = float(p["tail"]) * d2r / float(maxi(1, _tail_n))
	var wag: float = float(p["tail_wag"]) * d2r / float(maxi(1, _tail_n))
	for i in range(_tail_n):
		var tn: Node3D = j.get("tail%d" % i)
		if tn != null:
			tn.rotation = Vector3(-(tail_up * (1.4 if i == 0 else 1.0) + (0.35 if i == 0 else 0.0)), wag, 0)


# ------------------------------------------------------------------------------------------
# primitive helpers
# ------------------------------------------------------------------------------------------
func _pivot(nm: String, parent: Node3D, pos: Vector3) -> Node3D:
	var n := Node3D.new()
	n.name = nm
	n.position = pos
	parent.add_child(n)
	j[nm] = n
	return n


func _mat(c: Color, rough: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	m.rim_enabled = true
	m.rim = 0.25
	m.rim_tint = 0.4
	all_mats.append(m)
	return m


func _mi(parent: Node3D, mesh: Mesh, pos: Vector3, mat: Material, rot_deg: Vector3 = Vector3.ZERO, scl: Vector3 = Vector3.ONE) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position = pos
	mi.rotation_degrees = rot_deg
	mi.scale = scl
	mi.material_override = mat
	parent.add_child(mi)
	return mi


func _capsule(parent: Node3D, r: float, h: float, pos: Vector3, mat: Material, rot_deg: Vector3 = Vector3.ZERO, scl: Vector3 = Vector3.ONE) -> MeshInstance3D:
	var m := CapsuleMesh.new()
	m.radius = r
	m.height = maxf(h, r * 2.0 + 0.001)
	m.radial_segments = 16
	m.rings = 6
	return _mi(parent, m, pos, mat, rot_deg, scl)


func _sphere(parent: Node3D, r: float, pos: Vector3, mat: Material, scl: Vector3 = Vector3.ONE) -> MeshInstance3D:
	var m := SphereMesh.new()
	m.radius = r
	m.height = r * 2.0
	m.radial_segments = 16
	m.rings = 10
	return _mi(parent, m, pos, mat, Vector3.ZERO, scl)


func _cone(parent: Node3D, r: float, h: float, pos: Vector3, mat: Material, rot_deg: Vector3 = Vector3.ZERO) -> MeshInstance3D:
	var m := CylinderMesh.new()
	m.top_radius = 0.004
	m.bottom_radius = r
	m.height = h
	m.radial_segments = 10
	return _mi(parent, m, pos + Vector3(0, h * 0.5, 0), mat, rot_deg, Vector3(1.0, 1.0, 0.55))


func _cylinder(parent: Node3D, r: float, h: float, pos: Vector3, mat: Material) -> MeshInstance3D:
	var m := CylinderMesh.new()
	m.top_radius = r
	m.bottom_radius = r
	m.height = h
	m.radial_segments = 18
	return _mi(parent, m, pos, mat)


func _box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> MeshInstance3D:
	var m := BoxMesh.new()
	m.size = size
	return _mi(parent, m, pos, mat)
