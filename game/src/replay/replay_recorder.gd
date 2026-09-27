class_name ReplayRecorder
extends RefCounted
## Records authoritative match state (20 Hz full-state frames) and events with version
## metadata (spec §10). Playback interpolates recorded states — it never re-simulates physics.
## File: zstd-compressed var_to_bytes of {"header", "frames", "events"} with a magic prefix.

const MAGIC: String = "WRREPLAY1"
const FRAME_EVERY: int = 3

var header: Dictionary = {}
var frames: Array = []
var events: Array = []
var active: bool = false


func begin(sim: MatchSim, match_id: String, mode: String, roster_state: Dictionary) -> void:
	active = true
	frames.clear()
	events.clear()
	var fighters: Array = []
	for f in sim.fighters:
		fighters.append({"e": f.entity_id, "team": f.team, "fighter": f.def.id, "name": f.player_name, "bot": f.is_bot,
			"palette": f.palette})
	header = {"magic": MAGIC, "version": 1, "build": WR.BUILD_ID, "protocol": WR.PROTOCOL_VERSION,
		"godot": Engine.get_version_info()["string"], "match_id": match_id, "mode": mode, "arena": "Briarport",
		"recorded_at": Time.get_datetime_string_from_system(true), "tick_rate": WR.TICK_RATE,
		"frame_every": FRAME_EVERY, "fighters": fighters, "roster": roster_state, "seed": sim.seed_value}


func capture(sim: MatchSim) -> void:
	if not active or sim.tick % FRAME_EVERY != 0:
		return
	var fs: Array = []
	for f in sim.fighters:
		var v: Dictionary = Protocol.fighter_view_state(f, -1, true, sim.tick)
		fs.append([v["e"], v["flags"], v["pos"], v["yaw"], v["vel"], v["hp"], v["st"], v["clip"], v["ct"], v["ctrl"]])
	var m: Dictionary = sim.snapshot_match()
	frames.append({"t": sim.tick, "m": [m["phase"], m["tick"], m["scores"], m["zone"], m["next"], m["state"], m["ctrl"], m["rot"], m["sd"]], "f": fs})


func add_events(evs: Array) -> void:
	if not active:
		return
	for e in evs:
		events.append(e)


func finish(result: Dictionary) -> void:
	header["result"] = result
	header["duration_ticks"] = frames[frames.size() - 1]["t"] if not frames.is_empty() else 0
	active = false


func save(path: String) -> int:
	var raw: PackedByteArray = var_to_bytes({"header": header, "frames": frames, "events": events})
	var comp: PackedByteArray = raw.compress(FileAccess.COMPRESSION_ZSTD)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_buffer(MAGIC.to_utf8_buffer())
	f.store_32(raw.size())
	f.store_buffer(comp)
	f.close()
	return OK


static func load_file(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var magic: String = f.get_buffer(MAGIC.length()).get_string_from_utf8()
	if magic != MAGIC:
		return {}
	var raw_size: int = f.get_32()
	if raw_size <= 0 or raw_size > 256 * 1024 * 1024:
		return {}
	var comp: PackedByteArray = f.get_buffer(f.get_length() - f.get_position())
	f.close()
	var raw: PackedByteArray = comp.decompress(raw_size, FileAccess.COMPRESSION_ZSTD)
	var v: Variant = bytes_to_var(raw)
	if typeof(v) != TYPE_DICTIONARY:
		return {}
	return v


static func read_header(path: String) -> Dictionary:
	var d: Dictionary = load_file(path)
	return d.get("header", {})
