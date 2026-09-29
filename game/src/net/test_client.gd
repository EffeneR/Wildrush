extends Node
## Headless client process for automated network tests (gate G6–G9).
## <godot> --headless --path game -- --autopilot fight --connect 127.0.0.1:24610 --name P1
##        [--ticket T] [--fighter nyx] [--seed 3] [--log-json out.jsonl] [--quit-after-s 600]
##        [--probe security] [--observer --observer-key K] [--password PW]

var session: ClientSession
var autopilot := AutopilotInput.new()
var log_file: FileAccess = null
var _t0: int = 0
var _picked: bool = false
var _stats_every: int = 300
var _ticks: int = 0
var _probed: bool = false
var _prefs: Array = []
var _last_req_ms: int = -100000
var _hit_keys: Dictionary = {}
var _counts: Dictionary = {"confirmed_hits": 0, "dup_confirmed": 0, "predicted_hits": 0, "predicted_confirmed": 0,
	"pred_actions": 0, "conf_actions": 0, "blocks_on_me": 0, "hits_on_me": 0, "reconnects": 0}
var _dropped: bool = false
var _drop_done: bool = false
var _auth: Dictionary = {}
var _host: String = ""
var _port: int = 0


func _ready() -> void:
	_t0 = Time.get_ticks_msec()
	if Config.log_json != "":
		log_file = FileAccess.open(Config.log_json, FileAccess.WRITE)
	session = ClientSession.new()
	session.name = "Session"
	add_child(session)
	session.status_changed.connect(func(s: String, d: String) -> void:
		_log({"ev": "status", "status": s, "detail": d})
		if (s == "failed" or s == "disconnected") and not _dropped:
			_finish(3 if s == "failed" else 0))
	session.welcomed.connect(func(d: Dictionary) -> void: _log({"ev": "welcome", "pid": d.get("pid"), "observer": d.get("observer")}))
	session.lobby_updated.connect(_on_lobby)
	session.match_setup_received.connect(func(d: Dictionary) -> void:
		_log({"ev": "match_setup", "you": d.get("you"), "fighters": (d.get("fighters", []) as Array).size()})
		autopilot.setup(Config.autopilot, Config.seed_value, session.world, session.layout))
	session.results_received.connect(func(r: Dictionary) -> void:
		_log({"ev": "results", "winner": r.get("winner_team"), "score": r.get("score"), "reason": r.get("ended_reason"),
			"duration_s": r.get("duration_s")})
		_log_stats()
		if not Config.has("stay"):   # --stay: remain for back-to-back matches (soak)
			get_tree().create_timer(1.0).timeout.connect(func() -> void: _finish(0)))
	session.events_ready.connect(_on_events)
	session.server_notice.connect(func(d: Dictionary) -> void: _log({"ev": "notice", "msg": d}))
	session.input_source = autopilot
	for f in Config.get_arg("fighter", "").split(",", false):
		_prefs.append(f)
	for fid in WR.FIGHTER_IDS:
		if not _prefs.has(fid):
			_prefs.append(fid)
	var hp: PackedStringArray = Config.connect_to.split(":")
	var auth := {"name": Config.player_name if Config.player_name != "" else "Tester"}
	_auth = auth
	if Config.ticket != "":
		auth["ticket"] = Config.ticket
	if Config.has("password"):
		auth["password"] = Config.get_arg("password")
	if Config.observer:
		auth["observer"] = true
		auth["observer_key"] = Config.get_arg("observer-key", "")
	_host = hp[0]
	_port = int(hp[1]) if hp.size() > 1 else 24610
	var err: int = session.connect_to(_host, _port, auth)
	if err != OK:
		_log({"ev": "error", "reason": "connect", "code": err})
		_finish(4)


func _log(d: Dictionary) -> void:
	d["ms"] = Time.get_ticks_msec() - _t0
	var line: String = JSON.stringify(d)
	print("[client] " + line)
	if log_file != null:
		log_file.store_line(line)
		log_file.flush()


func _on_lobby(l: Dictionary) -> void:
	var stage: int = int(l.get("stage", 0))
	if stage != 1:   # ServerMain.Stage.SELECT
		return
	var me: int = int(session.info.get("pid", -1))
	var mine: Dictionary = {}
	var taken: Dictionary = {}
	for team in l["roster"]["teams"]:
		for p in team:
			if int(p["pid"]) == me:
				mine = p
	if mine.is_empty() or bool(mine["locked"]):
		return
	for p in l["roster"]["teams"][int(_team_of(l, me))]:
		if int(p["pid"]) != me and String(p["fighter"]) != "":
			taken[String(p["fighter"])] = true
	var now: int = Time.get_ticks_msec()
	if now - _last_req_ms < 700:
		return   # one request per state change, like a human clicking — never spam
	if String(mine["fighter"]) == "" or taken.has(String(mine["fighter"])):
		for f in _prefs:
			if not taken.has(f):
				_last_req_ms = now
				session.request({"t": "pick", "f": f})
				_log({"ev": "pick", "f": f})
				break
	else:
		_last_req_ms = now
		session.request({"t": "lock"})
		_log({"ev": "lock", "f": mine["fighter"]})


func _team_of(l: Dictionary, pid: int) -> int:
	for t in range(2):
		for p in l["roster"]["teams"][t]:
			if int(p["pid"]) == pid:
				return t
	return 0


func _on_events(evs: Array) -> void:
	var me: int = session.local_entity
	for e in evs:
		var t: String = String(e.get("type", ""))
		var predicted: bool = bool(e.get("predicted", false))
		if t == "predicted_hit":
			_counts["predicted_hits"] = int(_counts["predicted_hits"]) + 1
		elif t == "hit":
			var key: String = "%d:%d:%d:%d" % [int(e.get("a", -1)), int(e.get("ev", -1)), int(e.get("hi", -1)), int(e.get("t", -1))]
			if _hit_keys.has(key):
				_counts["dup_confirmed"] = int(_counts["dup_confirmed"]) + 1
			_hit_keys[key] = true
			_counts["confirmed_hits"] = int(_counts["confirmed_hits"]) + 1
			if bool(e.get("confirmed_predicted", false)):
				_counts["predicted_confirmed"] = int(_counts["predicted_confirmed"]) + 1
			if int(e.get("t", -1)) == me:
				_counts["hits_on_me"] = int(_counts["hits_on_me"]) + 1
		elif t == "block" and int(e.get("t", -1)) == me:
			_counts["blocks_on_me"] = int(_counts["blocks_on_me"]) + 1
		elif t == "action" and int(e.get("e", -1)) == me:
			var a: String = String(e.get("a", ""))
			if a.ends_with("_q") or a.contains("pounce") or a.contains("rush") or a.contains("false_start") or a.contains("bound") or a.contains("catch"):
				pass
			if predicted:
				_counts["pred_actions"] = int(_counts["pred_actions"]) + 1
			else:
				_counts["conf_actions"] = int(_counts["conf_actions"]) + 1
		if t in ["ko", "match_end", "sudden_death", "zone_rotated", "hit", "block", "parry", "guard_break", "respawn"]:
			_log({"ev": "game", "type": t, "tick": e.get("tick"), "a": e.get("a", e.get("e", -1)), "t": e.get("t", -1),
				"predicted": e.get("predicted", false), "dup": e.get("confirmed_predicted", false)})


func _physics_process(_d: float) -> void:
	_ticks += 1
	if _ticks % _stats_every == 0:
		_log_stats()
	var drop_at: float = float(Config.get_arg("drop-at-s", "0"))
	if drop_at > 0.0 and not _drop_done and float(Time.get_ticks_msec() - _t0) / 1000.0 > drop_at:
		_drop_done = true   # one deliberate drop per run
		_dropped = true
		_log({"ev": "drop", "token_set": session.reconnect_token != ""})
		Net.close()
		get_tree().create_timer(3.0).timeout.connect(func() -> void:
			_counts["reconnects"] = int(_counts["reconnects"]) + 1
			var err: int = session.connect_to(_host, _port, _auth)
			_log({"ev": "reconnect_attempt", "err": err})
			await get_tree().create_timer(4.0).timeout
			_dropped = false)
	if Config.get_arg("probe", "") == "security" and not _probed and session.status == "connected" and _ticks > 120:
		_probed = true
		_security_probe()
	if Config.quit_after_s > 0.0 and float(Time.get_ticks_msec() - _t0) / 1000.0 > Config.quit_after_s:
		_log_stats()
		_finish(0)


func _log_stats() -> void:
	var p: FighterBody = session.pred
	_log({"ev": "stats", "snaps": session.correction_stats["snaps"], "late": session.correction_stats["late_snaps"],
		"reconciles": session.correction_stats["reconciles"], "max_err": snappedf(float(session.correction_stats["max_error_m"]), 0.001),
		"mean_err": snappedf(float(session.correction_stats["sum_error_m"]) / maxf(1.0, float(session.correction_stats["reconciles"])), 0.0001),
		"pending": session.pending.size(), "in_bytes": Net.stats["in_bytes"], "out_bytes": Net.stats["out_bytes"],
		"hp": p.st.health if p != null else -1, "pos": [snappedf(p.global_position.x, 0.01), snappedf(p.global_position.z, 0.01)] if p != null else [],
		"server_tick": int(session.server_tick_est), "match": session.match_state, "counts": _counts,
		"teleports": session.correction_stats.get("teleports", 0), "local_entity": session.local_entity})


func _security_probe() -> void:
	## Forged/malformed traffic. The server must ignore all of it (verified from its log/state).
	_log({"ev": "probe_start"})
	Net.send_raw_msg(Protocol.pack({"t": "damage", "target": 0, "amount": 999}))       # forged outcome type
	Net.send_raw_msg(Protocol.pack({"t": "score", "team": 0, "points": 250}))          # forged score
	Net.send_raw_msg(Protocol.pack({"t": "pick", "f": "nyx", "entity": 3}))            # schema violation
	Net.send_raw_msg(PackedByteArray([1, 2, 3, 4, 5, 6, 7]))                            # garbage
	var big := PackedByteArray()
	big.resize(4096)
	Net.send_raw_msg(big)                                                               # oversize
	var b := StreamPeerBuffer.new()
	b.put_u8(5)                                                                         # too many frames
	for i in range(5):
		InputFrame.new().encode(b)
	Net.send_raw_input(b.data_array)
	var nan := StreamPeerBuffer.new()                                                   # malformed values
	nan.put_u8(1)
	nan.put_u32(session.seq + 5)
	nan.put_8(127)
	nan.put_8(-128)
	nan.put_u16(65535)
	nan.put_8(-128)
	nan.put_u16(0xFFFF)
	nan.put_u8(0xFF)
	Net.send_raw_input(nan.data_array)
	for i in range(200):
		Net.send_raw_input(PackedByteArray([1]))                                          # input flood (ENet may throttle)
	for i in range(100):
		Net.send_raw_msg(Protocol.pack({"t": "ready", "v": i % 2 == 0}))                 # reliable flood > 25 msg/s
	var bad_utf8 := PackedByteArray([27, 0, 0, 0, 1, 0, 0, 0, 4, 0, 0, 0, 1, 0, 0, 0, 116, 0, 0, 0, 4, 0, 0, 0, 2, 0, 0, 0, 0xC3, 0x28, 0, 0])
	Net.send_raw_msg(bad_utf8)                                                          # invalid UTF-8 string
	_log({"ev": "probe_sent"})


func _finish(code: int) -> void:
	autopilot.cleanup()
	if log_file != null:
		log_file.close()
		log_file = null
	Net.close()
	get_tree().quit(code)
