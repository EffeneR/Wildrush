extends Node
## Autoload "Tuning": canonical tuning data (game/data/tuning/*.json) as typed Resources.
## Pure data — safe on dedicated servers (no visuals).

const TUNING_DIR: String = "res://data/tuning/"

var shared: Dictionary = {}
var rules: Dictionary = {}
var fighters: Dictionary = {}   # id -> FighterDef
var load_errors: PackedStringArray = PackedStringArray()

# Frequently used shared values, pre-converted to ticks.
var stamina_max: float = 100.0
var stamina_regen_per_tick: float = 0.4
var stamina_regen_delay: int = 54
var hp_regen_per_tick: float = 0.3
var hp_regen_delay: int = 360
var gravity: float = 16.0
var max_fall_speed: float = 30.0
var ground_accel: float = 42.0
var ground_decel: float = 55.0
var air_accel: float = 9.0
var air_control: float = 0.35
var turn_rate_per_tick: float = deg_to_rad(720.0) / 60.0
var floor_max_angle: float = deg_to_rad(46.0)
var floor_snap_length: float = 0.4
var step_height: float = 0.36
var landing_slow_ticks: int = 7
var landing_slow_mult: float = 0.55
var coyote_ticks: int = 5
var soft_sep_speed: float = 3.0
var guard_arc_half: float = deg_to_rad(60.0)
var guard_move_mult: float = 0.45
var block_stun_light: int = 6
var block_stun_heavy: int = 12
var block_push_mult: float = 0.35
var guard_break_ticks: int = 54
var guard_exit_ticks: int = 5
var dodge_ticks: int = 22
var dodge_evade_from: int = 2
var dodge_evade_to: int = 13
var dodge_move_end: int = 16
var dodge_cancel_from: int = 18
var dodge_distance: float = 4.2
var dodge_stamina: float = 25.0
var dodge_cooldown: int = 9
var chain_max: int = 3
var chain_cancel_after_active: int = 6
var finisher_extra_recovery: int = 7
var finisher_kb_mult: float = 3.0
var chain_reset_ticks: int = 36
var cr_ticks: int = 180
var cr_flinch_ticks: int = 12
var cr_disp_mult: float = 0.5
var hard_control_min: int = 30
var getup_ticks: int = 27
var getup_evade_ticks: int = 18
var input_buffer_ticks: int = 6
var respawn_ticks: int = 600
var spawn_protect_max: int = 480
var fall_recovery_y: float = -12.0


func _init() -> void:
	reload()


func reload() -> void:
	load_errors.clear()
	shared = _load_json(TUNING_DIR + "shared.json")
	rules = _load_json(TUNING_DIR + "match_rules.json")
	_cache_shared()
	fighters.clear()
	for fid in WR.FIGHTER_IDS:
		var d: Dictionary = _load_json(TUNING_DIR + "fighters/%s.json" % fid)
		if d.is_empty():
			continue
		fighters[fid] = FighterDef.from_dict(d, shared)
	if not load_errors.is_empty():
		for e in load_errors:
			push_error("Tuning: " + e)


func fighter(id: String) -> FighterDef:
	return fighters.get(id) as FighterDef


func _load_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		load_errors.append("missing " + path)
		return {}
	var txt: String = FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(txt)
	if typeof(parsed) != TYPE_DICTIONARY:
		load_errors.append("invalid json " + path)
		return {}
	return parsed


func _cache_shared() -> void:
	if shared.is_empty():
		return
	var st: Dictionary = shared["stamina"]
	stamina_max = float(st["max"])
	stamina_regen_per_tick = float(st["regen_per_s"]) / WR.TICK_RATE
	stamina_regen_delay = WR.secs_to_ticks(float(st["regen_delay_s"]))
	var hr: Dictionary = shared["health_regen"]
	hp_regen_per_tick = float(hr["per_s"]) / WR.TICK_RATE
	hp_regen_delay = WR.secs_to_ticks(float(hr["delay_s"]))
	var mv: Dictionary = shared["movement"]
	gravity = float(mv["gravity"])
	max_fall_speed = float(mv["max_fall_speed"])
	ground_accel = float(mv["ground_accel"])
	ground_decel = float(mv["ground_decel"])
	air_accel = float(mv["air_accel"])
	air_control = float(mv["air_control"])
	turn_rate_per_tick = deg_to_rad(float(mv["turn_rate_deg"])) / WR.TICK_RATE
	floor_max_angle = deg_to_rad(float(mv["floor_max_angle_deg"]))
	floor_snap_length = float(mv["floor_snap_length"])
	step_height = float(mv["step_height"])
	landing_slow_ticks = WR.secs_to_ticks(float(mv["landing_slow_s"]))
	landing_slow_mult = float(mv["landing_slow_mult"])
	coyote_ticks = WR.secs_to_ticks(float(mv["coyote_s"]))
	soft_sep_speed = float(mv["soft_separation_speed"])
	fall_recovery_y = float(mv["fall_recovery_y"])
	var g: Dictionary = shared["guard"]
	guard_arc_half = deg_to_rad(float(g["arc_deg"]) * 0.5)
	guard_move_mult = float(g["move_mult"])
	block_stun_light = WR.secs_to_ticks(float(g["block_stun_light_s"]))
	block_stun_heavy = WR.secs_to_ticks(float(g["block_stun_heavy_s"]))
	block_push_mult = float(g["block_push_mult"])
	guard_break_ticks = WR.secs_to_ticks(float(g["break_stun_s"]))
	guard_exit_ticks = WR.secs_to_ticks(float(g["exit_s"]))
	var dg: Dictionary = shared["dodge"]
	dodge_ticks = WR.secs_to_ticks(float(dg["total_s"]))
	dodge_evade_from = WR.secs_to_ticks(float(dg["evade_from_s"]))
	dodge_evade_to = WR.secs_to_ticks(float(dg["evade_to_s"]))
	dodge_move_end = WR.secs_to_ticks(float(dg["move_end_s"]))
	dodge_cancel_from = WR.secs_to_ticks(float(dg["cancel_from_s"]))
	dodge_distance = float(dg["distance"])
	dodge_stamina = float(dg["stamina"])
	dodge_cooldown = WR.secs_to_ticks(float(dg["cooldown_s"]))
	var ch: Dictionary = shared["chain"]
	chain_max = int(ch["max_lights"])
	chain_cancel_after_active = WR.secs_to_ticks(float(ch["cancel_after_active_s"]))
	finisher_extra_recovery = WR.secs_to_ticks(float(ch["finisher_extra_recovery_s"]))
	finisher_kb_mult = float(ch["finisher_kb_mult"])
	chain_reset_ticks = WR.secs_to_ticks(float(ch["chain_reset_s"]))
	var ct: Dictionary = shared["control"]
	cr_ticks = WR.secs_to_ticks(float(ct["resistance_s"]))
	cr_flinch_ticks = WR.secs_to_ticks(float(ct["resisted_flinch_s"]))
	cr_disp_mult = float(ct["resisted_displacement_mult"])
	hard_control_min = WR.secs_to_ticks(float(ct["hard_control_min_stun_s"]))
	getup_ticks = WR.secs_to_ticks(float(ct["knockdown_getup_s"]))
	getup_evade_ticks = WR.secs_to_ticks(float(ct["getup_evade_s"]))
	input_buffer_ticks = WR.secs_to_ticks(float(shared["input_buffer_s"]))
	var ko: Dictionary = shared["knockout"]
	respawn_ticks = WR.secs_to_ticks(float(ko["respawn_s"]))
	spawn_protect_max = WR.secs_to_ticks(float(ko["spawn_protect_max_s"]))
