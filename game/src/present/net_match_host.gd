class_name NetMatchHost
extends MatchHost
## Online match view over Game.session (ClientSession): the local fighter is predicted and
## reconciled by the session; remote fighters are interpolated 100 ms behind. Only data the
## server chose to send (visibility-filtered) is ever shown.

var session: ClientSession = null
var player_input: PlayerInput = null
var _finished_sent: bool = false
var _last_seen: Dictionary = {}          # e -> newest snapshot tick containing e


func setup_session(s: ClientSession, pi: PlayerInput) -> void:
	session = s
	player_input = pi
	mode = "online"
	spectator = s.observer or s.local_entity < 0
	local_entity = s.local_entity
	regulation_s = float(Tuning.rules.get("regulation_s", 480))
	for e in s.fighter_info.keys():
		var fi: Dictionary = s.fighter_info[e]
		fighter_info[int(e)] = {"team": int(fi["team"]), "fighter": String(fi["fighter"]), "name": String(fi.get("name", "")),
			"bot": bool(fi.get("bot", false)), "palette": String(fi.get("palette", "default"))}
	local_team = int(fighter_info.get(local_entity, {}).get("team", 0))
	s.input_source = self
	s.events_ready.connect(func(evs: Array) -> void: events.emit(evs))
	s.chat_received.connect(func(m: Dictionary) -> void: chat.emit(m))
	s.ping_received.connect(func(m: Dictionary) -> void: ping.emit(m))
	s.results_received.connect(_on_results)
	s.server_notice.connect(_on_notice)
	s.status_changed.connect(_on_status)


func sample(_s: ClientSession) -> InputFrame:
	## Called by the session once per tick (input_source contract).
	return player_input.sample() if player_input != null else InputFrame.new()


func _on_results(r: Dictionary) -> void:
	if _finished_sent:
		return
	_finished_sent = true
	result_info = {"result": r, "my_entity": local_entity, "my_team": local_team, "mode": String(r.get("mode", "online")),
		"fighter": String(fighter_info.get(local_entity, {}).get("fighter", "")), "awards": {}, "replay_path": "",
		"online": true}
	finished.emit(result_info)


func _on_notice(d: Dictionary) -> void:
	match String(d.get("t", "")):
		"error":
			notice.emit("Request refused: %s" % String(d.get("code", "")))
		"afk_warning":
			notice.emit("You will be removed for inactivity in %d s" % int(d.get("in_s", 15)))
		"cancelled":
			notice.emit("Match cancelled: %s" % String(d.get("reason", "")))
		_:
			if d.has("msg"):
				notice.emit(String(d["msg"]))


func _on_status(s: String, detail: String) -> void:
	if s == "disconnected" or s == "failed":
		notice.emit("Connection lost%s" % ((": " + detail) if detail != "" else ""))


func views(_dt: float) -> Dictionary:
	var out: Dictionary = {}
	if session == null:
		return out
	var newest: int = -1
	for sn in session.snap_buffer:
		newest = maxi(newest, int(sn["tick"]))
		for e in (sn["fighters"] as Dictionary).keys():
			_last_seen[int(e)] = maxi(int(_last_seen.get(int(e), -1)), int(sn["tick"]))
	var rt: float = session.render_tick()
	for e in fighter_info.keys():
		if e == local_entity and session.pred != null:
			var vs: Dictionary = MatchHost.view_from_body(session.pred, session.pred_tick)
			vs["pos"] = (vs["pos"] as Vector3) + session.visual_offset
			out[e] = vs
			continue
		var st: Dictionary = session.interpolated(int(e), rt)
		if st.is_empty() or int(_last_seen.get(int(e), -1)) < newest - 6:
			out[e] = {"pos": Vector3(0, -100, 0), "yaw": 0.0, "vel": Vector3.ZERO, "clip": "idle", "ct": 0.0,
				"ctrl": 0, "flags": 0, "hp": 0.0, "hidden": true}
			continue
		var v: Dictionary = st.duplicate()
		v["clip"] = Protocol.clip_name(int(st["clip"]))
		out[e] = v
	return out


func match_state() -> Dictionary:
	if session == null:
		return {}
	var m: Dictionary = session.match_state.duplicate()
	var cu: int = int(m.get("countdown_until", -1))
	m["countdown_s"] = maxf(0.0, (float(cu) - session.server_tick_est) / WR.TICK_RATE) if int(m.get("phase", 0)) == WR.Phase.COUNTDOWN else 0.0
	m["training"] = false
	m["loading"] = session.snap_buffer.is_empty()
	return m


func local_status() -> Dictionary:
	if session == null or session.pred == null:
		return {}
	var s: Dictionary = MatchHost.status_from_body(session.pred, session.pred_tick)
	var r: Dictionary = session.roster_status.get(local_entity, {})
	if not r.is_empty():
		s["alive"] = bool(r.get("alive", true))
		s["respawn_s"] = float(r.get("respawn_s", 0))
	return s


func local_body() -> FighterBody:
	return session.pred if session != null else null


func roster() -> Array:
	var rows: Array = []
	if session == null:
		return rows
	var board: Dictionary = {}
	for b in session.board:
		board[int(b["e"])] = b
	for e in fighter_info.keys():
		var fi: Dictionary = fighter_info[e]
		var rs: Dictionary = session.roster_status.get(e, {})
		var bd: Dictionary = board.get(e, {})
		rows.append({"e": e, "team": fi["team"], "fighter": fi["fighter"], "name": fi["name"], "bot": fi["bot"],
			"kos": int(bd.get("kos", 0)), "kod": int(bd.get("kod", 0)), "dmg": int(bd.get("dmg", 0)),
			"ctrl_s": int(bd.get("ctrl_s", 0)), "alive": bool(rs.get("alive", true)), "respawn_s": float(rs.get("respawn_s", 0)),
			"ping_ms": int(bd.get("ping_ms", -1)), "connected": bool(bd.get("connected", true))})
	return rows


func send_chat(text: String, team: bool) -> void:
	if session != null:
		session.request({"t": "chat", "text": text, "team": team})


func send_ping(pos: Vector3, kind: String) -> void:
	if session != null:
		session.request({"t": "ping", "pos": pos, "kind": kind})


func request_follow(e: int) -> void:
	if session != null:
		session.request({"t": "spectate", "e": e})


func leave() -> void:
	if session != null:
		session.input_source = null
	Game.end_online_session()
