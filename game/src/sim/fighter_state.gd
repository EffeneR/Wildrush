class_name FighterState
extends RefCounted
## Mutable per-fighter simulation state. Everything the authoritative step reads or writes
## lives here (plus the body's transform/velocity) so it can be snapshotted, replayed for
## client-side prediction, and recorded for replays.

# --- vitals
var alive: bool = true
var health: float = 100.0
var stamina: float = 100.0
var last_spend_tick: int = -100000
var last_offense_tick: int = -100000
var last_damage_tick: int = -100000

# --- facing / locomotion
var yaw: float = 0.0
var grounded: bool = true
var air_ticks: int = 0
var coyote_left: int = 0
var landing_slow_until: int = -1
var air_light_used: bool = false
var jumped: bool = false
var knock_vel: Vector3 = Vector3.ZERO
var knock_left: int = 0

# --- action runtime
var act: ActionDef = null
var act_tick: int = 0
var act_event: int = 0
var act_phase: String = ""
var act_phase_tick: int = 0
var act_data: Dictionary = {}
var act_hit_done: Dictionary = {}      # "hit:target" -> true (one damage per strike per target)
var act_prev_pos: Dictionary = {}      # hit index -> Vector3 world position of the sphere last tick
var act_finisher: bool = false
var act_origin_yaw: float = 0.0

# --- guard
var guarding: bool = false
var guard_tick: int = 0
var guard_exit_until: int = -1

# --- control effects (victim side)
var ctrl: int = WR.Ctrl.NONE
var ctrl_tick: int = 0
var ctrl_len: int = 0
var ctrl_by: int = -1
var cr_until: int = -1                 # control resistance until tick (exclusive)

# --- chains / cooldowns / buffer
var chain_count: int = 0
var chain_last_tick: int = -100000
var cd_ready: Dictionary = {"q": 0, "e": 0, "r": 0, "dodge": 0}
var prev_buttons: int = 0
var buf_btn: int = 0
var buf_tick: int = -100000
var buf_move: Vector2 = Vector2.ZERO

# --- life cycle
var ko_tick: int = -1
var respawn_at: int = -1
var spawn_protected: bool = false
var protect_until: int = -1
var last_hit_by: int = -1
var last_hit_tick: int = -100000

# --- stats (authoritative, sent to results)
var kos: int = 0
var knocked_out: int = 0
var damage_dealt: float = 0.0
var control_ticks: int = 0
var last_input_seq: int = 0
var idle_ticks: int = 0


func has_cr(tick: int) -> bool:
	return tick < cr_until


func in_action() -> bool:
	return act != null


func action_id() -> String:
	return act.id if act != null else ""


func clear_action() -> void:
	act = null
	act_tick = 0
	act_phase = ""
	act_phase_tick = 0
	act_data = {}
	act_hit_done = {}
	act_prev_pos = {}
	act_finisher = false


func set_phase(name: String) -> void:
	act_phase = name
	act_phase_tick = 0


func to_dict() -> Dictionary:
	## Full state for reconciliation (local prediction) and reconnect snapshots.
	return {
		"alive": alive, "hp": health, "st": stamina, "lsp": last_spend_tick, "lof": last_offense_tick,
		"ldm": last_damage_tick, "yaw": yaw, "gr": grounded, "air": air_ticks, "coy": coyote_left,
		"lsu": landing_slow_until, "alu": air_light_used, "jmp": jumped, "kv": knock_vel, "kl": knock_left,
		"act": act.id if act != null else "", "at": act_tick, "ae": act_event, "ap": act_phase,
		"apt": act_phase_tick, "ad": act_data.duplicate(true), "ahd": act_hit_done.duplicate(),
		"app": act_prev_pos.duplicate(), "afn": act_finisher, "aoy": act_origin_yaw,
		"g": guarding, "gt": guard_tick, "geu": guard_exit_until,
		"c": ctrl, "ct": ctrl_tick, "cl": ctrl_len, "cb": ctrl_by, "cr": cr_until,
		"chc": chain_count, "chl": chain_last_tick, "cd": cd_ready.duplicate(),
		"pb": prev_buttons, "bb": buf_btn, "bt": buf_tick, "bm": buf_move,
		"ko": ko_tick, "ra": respawn_at, "sp": spawn_protected, "pu": protect_until,
		"lhb": last_hit_by, "lht": last_hit_tick, "seq": last_input_seq,
	}


const PACK_KEYS: Array[String] = ["alive", "hp", "st", "lsp", "lof", "ldm", "yaw", "gr", "air", "coy", "lsu", "alu", "jmp",
	"kv", "kl", "act", "at", "ae", "ap", "apt", "ad", "ahd", "app", "afn", "aoy", "g", "gt", "geu", "c", "ct", "cl", "cb", "cr",
	"chc", "chl", "cd", "pb", "bb", "bt", "bm", "ko", "ra", "sp", "pu", "lhb", "lht", "seq"]


func to_packed() -> PackedByteArray:
	## Compact reconciliation payload: fixed key order (no key strings) + deflate.
	var d: Dictionary = to_dict()
	var arr: Array = []
	for k in PACK_KEYS:
		arr.append(d[k])
	var raw: PackedByteArray = var_to_bytes(arr)
	var comp: PackedByteArray = raw.compress(FileAccess.COMPRESSION_DEFLATE)
	var out := PackedByteArray()
	out.resize(4)
	out.encode_u32(0, raw.size())
	out.append_array(comp)
	return out


static func unpack_dict(data: PackedByteArray) -> Dictionary:
	if data.size() < 5:
		return {}
	var raw_size: int = data.decode_u32(0)
	if raw_size <= 0 or raw_size > 65536:
		return {}
	var raw: PackedByteArray = data.slice(4).decompress(raw_size, FileAccess.COMPRESSION_DEFLATE)
	var v: Variant = bytes_to_var(raw)
	if typeof(v) != TYPE_ARRAY or (v as Array).size() != PACK_KEYS.size():
		return {}
	var d: Dictionary = {}
	for i in range(PACK_KEYS.size()):
		d[PACK_KEYS[i]] = v[i]
	return d


func from_dict(d: Dictionary, def: FighterDef) -> void:
	alive = bool(d["alive"])
	health = float(d["hp"])
	stamina = float(d["st"])
	last_spend_tick = int(d["lsp"])
	last_offense_tick = int(d["lof"])
	last_damage_tick = int(d["ldm"])
	yaw = float(d["yaw"])
	grounded = bool(d["gr"])
	air_ticks = int(d["air"])
	coyote_left = int(d["coy"])
	landing_slow_until = int(d["lsu"])
	air_light_used = bool(d["alu"])
	jumped = bool(d["jmp"])
	knock_vel = d["kv"]
	knock_left = int(d["kl"])
	var aid: String = String(d["act"])
	act = CommonActions.resolve(def, aid) if aid != "" else null
	act_tick = int(d["at"])
	act_event = int(d["ae"])
	act_phase = String(d["ap"])
	act_phase_tick = int(d["apt"])
	act_data = (d["ad"] as Dictionary).duplicate(true)
	act_hit_done = (d["ahd"] as Dictionary).duplicate()
	act_prev_pos = (d["app"] as Dictionary).duplicate()
	act_finisher = bool(d["afn"])
	act_origin_yaw = float(d["aoy"])
	guarding = bool(d["g"])
	guard_tick = int(d["gt"])
	guard_exit_until = int(d["geu"])
	ctrl = int(d["c"])
	ctrl_tick = int(d["ct"])
	ctrl_len = int(d["cl"])
	ctrl_by = int(d["cb"])
	cr_until = int(d["cr"])
	chain_count = int(d["chc"])
	chain_last_tick = int(d["chl"])
	cd_ready = (d["cd"] as Dictionary).duplicate()
	prev_buttons = int(d["pb"])
	buf_btn = int(d["bb"])
	buf_tick = int(d["bt"])
	buf_move = d["bm"]
	ko_tick = int(d["ko"])
	respawn_at = int(d["ra"])
	spawn_protected = bool(d["sp"])
	protect_until = int(d["pu"])
	last_hit_by = int(d["lhb"])
	last_hit_tick = int(d["lht"])
	last_input_seq = int(d["seq"])
