class_name ReplayHost
extends MatchHost
## Recorded-match playback (spec §10): interpolates recorded 20 Hz authoritative frames and
## replays recorded events — never re-simulates physics. Pause, seek, speed; the match scene
## provides follow and free cameras.

var data: Dictionary = {}
var header: Dictionary = {}
var frames: Array = []
var ev_list: Array = []
var t: float = 0.0                 # playback position in ticks
var speed: float = 1.0
var paused: bool = false
var duration_ticks: int = 0
var start_tick: int = 0
var _ev_i: int = 0
var _finished_sent: bool = false
var load_error: String = ""


func load_replay(path: String) -> bool:
	data = ReplayRecorder.load_file(path)
	if data.is_empty():
		load_error = "The replay file could not be read."
		return false
	header = data.get("header", {})
	if String(header.get("build", "")) != WR.BUILD_ID:
		load_error = "This replay was recorded with a different build (%s)." % String(header.get("build", "?"))
		return false
	frames = data.get("frames", [])
	ev_list = data.get("events", [])
	if frames.is_empty():
		load_error = "The replay contains no frames."
		return false
	mode = "replay"
	spectator = true
	regulation_s = float(Tuning.rules.get("regulation_s", 480))
	start_tick = int(frames[0]["t"])
	duration_ticks = int(frames[frames.size() - 1]["t"]) - start_tick
	t = float(start_tick)
	for fi in header.get("fighters", []):
		fighter_info[int(fi["e"])] = {"team": int(fi["team"]), "fighter": String(fi["fighter"]), "name": String(fi["name"]),
			"bot": bool(fi.get("bot", false)), "palette": String(fi.get("palette", "default"))}
	local_entity = -1
	local_team = 0
	return true


func advance(dt: float) -> void:
	if paused or frames.is_empty():
		return
	var prev: float = t
	t = minf(t + dt * WR.TICK_RATE * speed, float(start_tick + duration_ticks))
	_emit_events(prev, t)
	if t >= float(start_tick + duration_ticks) and not _finished_sent:
		_finished_sent = true
		paused = true
		result_info = {"result": header.get("result", {}), "my_entity": -1, "my_team": 0, "mode": "replay"}
		finished.emit(result_info)


func seek(tick: float) -> void:
	t = clampf(tick, float(start_tick), float(start_tick + duration_ticks))
	_ev_i = 0
	while _ev_i < ev_list.size() and float(ev_list[_ev_i].get("tick", 0)) <= t:
		_ev_i += 1
	_finished_sent = t >= float(start_tick + duration_ticks)


func _emit_events(from_t: float, to_t: float) -> void:
	var out: Array = []
	while _ev_i < ev_list.size():
		var e: Dictionary = ev_list[_ev_i]
		var et: float = float(e.get("tick", 0))
		if et > to_t:
			break
		if et > from_t and String(e.get("type", "")) != "predicted_hit":
			out.append(e)
		_ev_i += 1
	if not out.is_empty():
		events.emit(out)


func _frame_pair() -> Array:
	# binary search the last frame at or before t
	var lo: int = 0
	var hi: int = frames.size() - 1
	while lo < hi:
		var mid: int = (lo + hi + 1) / 2
		if float(frames[mid]["t"]) <= t:
			lo = mid
		else:
			hi = mid - 1
	var a: Dictionary = frames[lo]
	var b: Dictionary = frames[mini(lo + 1, frames.size() - 1)]
	var span: float = maxf(1.0, float(b["t"]) - float(a["t"]))
	return [a, b, clampf((t - float(a["t"])) / span, 0.0, 1.0)]


func views(_dt: float) -> Dictionary:
	var out: Dictionary = {}
	if frames.is_empty():
		return out
	var fp: Array = _frame_pair()
	var fa: Dictionary = fp[0]
	var fb: Dictionary = fp[1]
	var u: float = fp[2]
	var bmap: Dictionary = {}
	for r in fb["f"]:
		bmap[int(r[0])] = r
	for r in fa["f"]:
		var e: int = int(r[0])
		var rb: Array = bmap.get(e, r)
		var yaw_a: float = float(r[3])
		var yaw_b: float = float(rb[3])
		out[e] = {"e": e, "flags": int(r[1]), "pos": (r[2] as Vector3).lerp(rb[2] as Vector3, u),
			"yaw": yaw_a + MathX.angle_diff(yaw_a, yaw_b) * u, "vel": (r[4] as Vector3).lerp(rb[4] as Vector3, u),
			"hp": lerpf(float(r[5]), float(rb[5]), u), "st": float(r[6]), "clip": Protocol.clip_name(int(r[7])),
			"ct": float(r[8]) + (float(rb[8]) - float(r[8])) * u if int(r[7]) == int(rb[7]) else float(r[8]) + (t - float(fa["t"])) / WR.TICK_RATE,
			"ctrl": int(r[9])}
	return out


func match_state() -> Dictionary:
	if frames.is_empty():
		return {}
	var fa: Dictionary = _frame_pair()[0]
	var m: Array = fa["m"]
	return {"phase": int(m[0]), "tick": int(m[1]), "scores": m[2], "zone": m[3], "next": m[4], "state": int(m[5]),
		"ctrl": int(m[6]), "rot": int(m[7]), "sd": bool(m[8]), "final": false, "countdown_s": 0.0, "training": false,
		"loading": false}


func roster() -> Array:
	var rows: Array = []
	var kos: Dictionary = {}
	var kod: Dictionary = {}
	for e in ev_list:
		if float(e.get("tick", 0)) > t:
			break
		if String(e.get("type", "")) == "ko":
			kod[int(e["e"])] = int(kod.get(int(e["e"]), 0)) + 1
			if int(e.get("by", -1)) >= 0:
				kos[int(e["by"])] = int(kos.get(int(e["by"]), 0)) + 1
	var vs: Dictionary = views(0.0)
	for e in fighter_info.keys():
		var fi: Dictionary = fighter_info[e]
		rows.append({"e": e, "team": fi["team"], "fighter": fi["fighter"], "name": fi["name"], "bot": fi["bot"],
			"kos": int(kos.get(e, 0)), "kod": int(kod.get(e, 0)), "dmg": -1, "ctrl_s": -1,
			"alive": (int(vs.get(e, {}).get("flags", 1)) & Protocol.F_ALIVE) != 0, "respawn_s": 0.0})
	return rows


func progress() -> float:
	return (t - float(start_tick)) / maxf(1.0, float(duration_ticks))
