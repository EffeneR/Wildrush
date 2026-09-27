class_name ServerMain
extends Node
## Authoritative dedicated match server (spec §4, §9, §10; D-012..D-015).
## Launched by scenes/server.tscn when Config.is_server. Headless: no rendering or audio needed.

enum Stage { LOBBY, SELECT, MATCH, RESULTS, CLOSING }

const JOIN_TIMEOUT_S: float = 90.0
const CLOSE_DELAY_S: float = 5.0
const MAX_INPUT_QUEUE: int = 8
const MAX_VIOLATIONS: int = 50

var stage: int = Stage.LOBBY
var mode: String = WR.MODE_CASUAL
var match_id: String = ""
var sim: MatchSim = null
var layout: ArenaLayout = null
var roster := MatchRoster.new()
var vis := TeamVisibility.new()
var service: ServerService = null
var recorder := ReplayRecorder.new()
var rng := RandomNumberGenerator.new()
var conns: Dictionary = {}          # peer_id -> Dictionary (connection state)
var pid_to_peer: Dictionary = {}    # pid -> peer_id (connected)
var reconnect_tokens: Dictionary = {}  # token -> pid
var account_to_pid: Dictionary = {}
var disconnected: Dictionary = {}   # pid -> reservation expiry (server tick)
var tick: int = 0
var select_until: int = -1
var results_until: int = -1
var close_at: int = -1
var join_deadline: int = -1
var admin_pid: int = -1
var expected_players: int = 10
var observers_allowed: bool = true
var private_password: String = ""
var _next_pid: int = 1
var _pending_events: Array = []
var _afk_warned: Dictionary = {}
var _forfeit_since: Array = [-1, -1]
var result_payload: Dictionary = {}
var replay_path: String = ""
var log_lines: int = 0


func _ready() -> void:
	mode = Config.mode if Config.mode in [WR.MODE_CASUAL, WR.MODE_RANKED, WR.MODE_PRIVATE] else WR.MODE_PRIVATE
	match_id = Config.match_id if Config.match_id != "" else "local-%d" % Time.get_unix_time_from_system()
	expected_players = Config.expected_players
	private_password = Config.private_password
	rng.seed = Config.seed_value if Config.seed_value != 0 else int(Time.get_unix_time_from_system())
	roster.allow_bots = (mode == WR.MODE_CASUAL and expected_players < 10) or (mode == WR.MODE_PRIVATE and Config.allow_bots)
	if mode == WR.MODE_RANKED:
		roster.allow_bots = false   # never bots in ranked (spec §3)
	service = ServerService.new()
	service.name = "Service"
	add_child(service)
	service.configure(Config.service_url, Config.server_id, Config.read_secret())
	if mode != WR.MODE_PRIVATE and not service.enabled:
		_log("fatal", {"reason": "matchmade mode requires --service-url, --server-id and --secret-file"})
		get_tree().quit(2)
		return
	layout = ArenaLayout.load_file()
	sim = MatchSim.new()
	sim.name = "Sim"
	add_child(sim)
	sim.setup(layout, mode, rng.seed, true)
	sim.match_id = match_id
	sim.ctx.rewind_provider = _rewind_for
	sim.sim_events.connect(_on_sim_events)
	sim.match_finished.connect(_on_match_finished)
	Net.server_handler = self
	var err: int = Net.start_server(Config.port, 24, Config.bind_address)
	if err != OK:
		_log("fatal", {"reason": "bind failed", "port": Config.port})
		get_tree().quit(3)
		return
	join_deadline = WR.secs_to_ticks(JOIN_TIMEOUT_S)
	_log("server_started", {"port": Config.port, "mode": mode, "match_id": match_id, "bots_allowed": roster.allow_bots,
		"protocol": WR.PROTOCOL_VERSION, "build": WR.BUILD_ID})
	if service.enabled:
		service.post_started(match_id)


func _log(kind: String, data: Dictionary = {}) -> void:
	var d: Dictionary = data.duplicate()
	d["ev"] = kind
	d["t"] = tick
	print("[server] " + JSON.stringify(d))
	log_lines += 1


# ------------------------------------------------------------------------------------------
# authentication & connection
# ------------------------------------------------------------------------------------------
func authenticate(peer_id: int, a: Dictionary) -> void:
	if int(a.get("proto", -1)) != WR.PROTOCOL_VERSION or String(a.get("build", "")) != WR.BUILD_ID:
		Net.reject_auth(peer_id, "version_mismatch")
		_log("auth_reject", {"peer": peer_id, "reason": "version"})
		return
	var name: String = Protocol.sanitize_chat(String(a.get("name", "Player"))).substr(0, 20)
	if name == "":
		name = "Player"
	var want_observer: bool = bool(a.get("observer", false))
	if stage == Stage.CLOSING:
		Net.reject_auth(peer_id, "closing")
		return
	# reconnect by token (private) — rebinding to a reserved slot
	var token: String = String(a.get("reconnect", ""))
	if token != "" and reconnect_tokens.has(token):
		var pid: int = int(reconnect_tokens[token])
		if disconnected.has(pid):
			_bind(peer_id, pid, name, false, "")
			Net.accept_auth(peer_id, _welcome_reply(peer_id))
			return
	if service.enabled and mode != WR.MODE_PRIVATE or String(a.get("ticket", "")) != "":
		var t: Dictionary = service.verify_ticket(String(a.get("ticket", "")), match_id)
		if not bool(t["ok"]):
			Net.reject_auth(peer_id, String(t["reason"]))
			_log("auth_reject", {"peer": peer_id, "reason": t["reason"]})
			return
		service.mark_used(String(t["tid"]))   # a reused ticket fails locally before any HTTP
		service.redeem(String(t["tid"]), match_id, func(code: int, d: Dictionary) -> void:
			if code != 200:
				Net.reject_auth(peer_id, "redeem_failed_%d" % code)
				_log("auth_reject", {"peer": peer_id, "reason": "redeem", "code": code})
				return
			var role: String = String(d.get("role", t["role"]))
			var acc: String = String(d.get("account_id", t["aid"]))
			var disp: String = String(d.get("display_name", d.get("username", name)))
			if role == "observer":
				if not observers_allowed:
					Net.reject_auth(peer_id, "observers_disabled")
					return
				_bind(peer_id, -1, disp, true, acc)
			else:
				var pid2: int = int(account_to_pid.get(acc, -1))
				if pid2 < 0:
					pid2 = _new_pid()
				_bind(peer_id, pid2, disp, false, acc, int(d.get("team", t["team"])))
			Net.accept_auth(peer_id, _welcome_reply(peer_id)))
		return
	# private / direct connect
	if private_password != "" and String(a.get("password", "")) != private_password:
		Net.reject_auth(peer_id, "bad_password")
		_log("auth_reject", {"peer": peer_id, "reason": "password"})
		return
	if want_observer:
		var key: String = Config.get_arg("observer-key", "")
		if not observers_allowed or key == "" or String(a.get("observer_key", "")) != key:
			Net.reject_auth(peer_id, "observer_not_authorized")
			_log("auth_reject", {"peer": peer_id, "reason": "observer"})
			return
		_bind(peer_id, -1, name, true, "")
		Net.accept_auth(peer_id, _welcome_reply(peer_id))
		return
	if stage != Stage.LOBBY and stage != Stage.RESULTS:
		Net.reject_auth(peer_id, "match_in_progress")
		return
	_bind(peer_id, _new_pid(), name, false, "")
	Net.accept_auth(peer_id, _welcome_reply(peer_id))


func _new_pid() -> int:
	_next_pid += 1
	return _next_pid


func _bind(peer_id: int, pid: int, name: String, observer: bool, account: String, team_pref: int = -1) -> void:
	var c: Dictionary = {"peer": peer_id, "pid": pid, "name": name, "observer": observer, "account": account,
		"inputs": {}, "next_seq": -1, "last": InputFrame.new(), "acked": 0, "violations": 0, "follow": -1,
		"joined_tick": tick, "token": "", "live": false}
	conns[peer_id] = c
	if observer:
		return
	if roster.players.has(pid):
		roster.players[pid]["connected"] = true
		disconnected.erase(pid)
		if sim != null:
			var f: FighterBody = sim.fighter(_entity_of(pid))
			if f != null:
				f.present = true
				if f.st.alive:
					sim.respawn(f)   # rejoin at a safe spawn with restored resources
		_log("reconnected", {"pid": pid})
	else:
		var p: Dictionary = roster.add_player(pid, name, team_pref, account)
		if p.is_empty():
			conns[peer_id]["observer"] = true
			return
		if account != "":
			account_to_pid[account] = pid
		if admin_pid < 0 and mode == WR.MODE_PRIVATE:
			admin_pid = pid
	pid_to_peer[pid] = peer_id
	var token: String = "%d-%d-%d" % [pid, rng.randi(), Time.get_ticks_usec()]
	reconnect_tokens[token] = pid
	c["token"] = token


func _welcome_reply(peer_id: int) -> Dictionary:
	var c: Dictionary = conns.get(peer_id, {})
	return {"ok": true, "pid": c.get("pid", -1), "observer": c.get("observer", false), "token": c.get("token", ""),
		"mode": mode, "match_id": match_id, "protocol": WR.PROTOCOL_VERSION}


func on_auth_failed(peer_id: int) -> void:
	conns.erase(peer_id)


func _live_conns() -> Array:
	return conns.values().filter(func(c: Dictionary) -> bool: return bool(c["live"]))


func on_peer_connected(peer_id: int) -> void:
	var c: Dictionary = conns.get(peer_id, {})
	if c.is_empty():
		Net.disconnect_peer(peer_id)
		return
	c["live"] = true   # authentication completed on both sides: safe to send RPCs
	_log("joined", {"peer": peer_id, "pid": c["pid"], "observer": c["observer"]})
	Net.send_to(peer_id, {"t": "welcome", "pid": c["pid"], "observer": c["observer"], "admin": c["pid"] == admin_pid,
		"mode": mode, "match_id": match_id, "stage": stage, "token": c["token"]})
	_broadcast_lobby()
	if stage == Stage.MATCH:
		_send_match_setup(peer_id)


func on_peer_disconnected(peer_id: int) -> void:
	var c: Dictionary = conns.get(peer_id, {})
	conns.erase(peer_id)
	if c.is_empty():
		return
	var pid: int = int(c["pid"])
	_log("left", {"peer": peer_id, "pid": pid})
	if pid < 0:
		return
	pid_to_peer.erase(pid)
	if not roster.players.has(pid):
		return
	if stage == Stage.LOBBY or stage == Stage.RESULTS:
		if mode == WR.MODE_PRIVATE:
			roster.remove_player(pid)
			if pid == admin_pid:
				admin_pid = -1
				for p in roster.humans():
					admin_pid = int(p["pid"])
					break
		else:
			roster.players[pid]["connected"] = false
	else:
		roster.players[pid]["connected"] = false
		disconnected[pid] = tick + WR.secs_to_ticks(float(Tuning.rules.get("reconnect_reservation_s", 90)))
		var f: FighterBody = sim.fighter(_entity_of(pid))
		if f != null:
			f.present = false          # removed from the world (not hittable, not occupying)
			sim.occupancy.forget(f.entity_id)
	_broadcast_lobby()


func on_violation(peer_id: int, kind: String) -> void:
	var c: Dictionary = conns.get(peer_id, {})
	if c.is_empty():
		return
	c["violations"] = int(c["violations"]) + 1
	if int(c["violations"]) % 10 == 1:
		_log("violation", {"peer": peer_id, "kind": kind, "count": c["violations"]})
	if int(c["violations"]) > MAX_VIOLATIONS:
		_log("kick_abuse", {"peer": peer_id})
		Net.disconnect_peer(peer_id)


func _entity_of(pid: int) -> int:
	var p: Dictionary = roster.players.get(pid, {})
	if p.is_empty():
		return -1
	return int(p["team"]) * WR.TEAM_SIZE + int(p["slot"])


# ------------------------------------------------------------------------------------------
# messages
# ------------------------------------------------------------------------------------------
func on_input(peer_id: int, data: PackedByteArray) -> void:
	var c: Dictionary = conns.get(peer_id, {})
	if c.is_empty() or bool(c["observer"]) or stage != Stage.MATCH:
		return
	var frames: Array = Protocol.decode_inputs(data)
	if frames.is_empty():
		on_violation(peer_id, "bad_input")
		return
	var q: Dictionary = c["inputs"]
	for f: InputFrame in frames:
		var ns: int = int(c["next_seq"])
		if ns < 0:
			c["next_seq"] = f.seq
			ns = f.seq
		if f.seq < ns or f.seq > ns + 240 or q.has(f.seq):
			continue   # duplicate, old or absurd sequence numbers are ignored
		q[f.seq] = f


func on_msg(peer_id: int, d: Dictionary) -> void:
	var c: Dictionary = conns.get(peer_id, {})
	if c.is_empty():
		return
	var pid: int = int(c["pid"])
	var t: String = String(d["t"])
	match t:
		"chat":
			var now_ms: int = Time.get_ticks_msec()
			if now_ms - int(c.get("last_chat", 0)) < 1000:
				return
			c["last_chat"] = now_ms
			var text: String = Protocol.sanitize_chat(String(d["text"]))
			if text == "":
				return
			var team_only: bool = bool(d["team"])
			var sender_team: int = int(roster.players.get(pid, {}).get("team", -1))
			for other in _live_conns():
				var ot: int = int(roster.players.get(int(other["pid"]), {}).get("team", -2))
				if team_only and ot != sender_team:
					continue
				Net.send_to(int(other["peer"]), {"t": "chat", "from": c["name"], "team": sender_team, "team_only": team_only, "text": text})
		"ping":
			_handle_ping(pid, d)
		"leave":
			Net.disconnect_peer(peer_id)
		"spectate":
			c["follow"] = int(d["e"])
		_:
			if bool(c["observer"]) or pid < 0:
				return
			_handle_lobby_msg(peer_id, pid, d)


func _handle_ping(pid: int, d: Dictionary) -> void:
	if stage != Stage.MATCH or not roster.players.has(pid):
		return
	var team: int = int(roster.players[pid]["team"])
	var pos: Vector3 = d["pos"]
	var kind: String = String(d["kind"])
	if kind == "enemy":
		# only an enemy the team can already see may be tagged (no ping-scanning for hidden enemies)
		for f in sim.fighters:
			if f.team != team and f.st.alive and f.present and f.global_position.distance_to(pos) < 3.0 \
					and vis.visible_to(team, f.entity_id, sim.tick):
				vis.mark_pinged(team, f.entity_id, sim.tick)
	var from_e: int = _entity_of(pid)
	for c in _live_conns():
		var cp: int = int(c["pid"])
		if cp >= 0 and int(roster.players.get(cp, {}).get("team", -1)) == team:
			Net.send_to(int(c["peer"]), {"t": "ping", "from": from_e, "pos": pos, "kind": kind})


func _handle_lobby_msg(peer_id: int, pid: int, d: Dictionary) -> void:
	var t: String = String(d["t"])
	var err: String = ""
	match t:
		"pick":
			if stage != Stage.SELECT:
				err = "not_selecting"
			else:
				err = roster.pick(pid, String(d["f"]))
		"lock":
			err = roster.lock(pid) if stage == Stage.SELECT else "not_selecting"
		"swap_req":
			err = roster.request_swap(pid, int(d["slot"])) if stage == Stage.SELECT else "not_selecting"
		"swap_answer":
			err = roster.answer_swap(pid, int(d["from"]), bool(d["accept"])) if stage == Stage.SELECT else "not_selecting"
		"ready":
			if roster.players.has(pid):
				roster.players[pid]["ready"] = bool(d["v"])
		"rematch":
			if stage == Stage.RESULTS and roster.players.has(pid) and mode == WR.MODE_PRIVATE:
				roster.players[pid]["rematch"] = bool(d["v"])
				_check_rematch()
		"admin":
			err = _admin(pid, String(d["cmd"]), d["args"])
	if err != "" and err != "declined":
		Net.send_to(peer_id, {"t": "error", "for": t, "code": err})
	_broadcast_lobby()
	if stage == Stage.SELECT and roster.all_humans_locked():
		select_until = mini(select_until, tick + 60)   # everyone locked: start after 1 s


func _admin(pid: int, cmd: String, args: Dictionary) -> String:
	if mode != WR.MODE_PRIVATE or pid != admin_pid:
		return "not_admin"
	match cmd:
		"set_team":
			return roster.set_team(int(args.get("pid", -1)), int(args.get("team", -1))) if stage == Stage.LOBBY else "wrong_stage"
		"kick":
			var target: int = int(args.get("pid", -1))
			if target == admin_pid or not pid_to_peer.has(target):
				return "invalid"
			Net.disconnect_peer(int(pid_to_peer[target]))
			roster.remove_player(target)
			return ""
		"bots":
			roster.allow_bots = bool(args.get("enabled", false))
			var diff: String = String(args.get("difficulty", "normal"))
			roster.bot_difficulty = diff if diff in ["easy", "normal", "hard"] else "normal"
			return ""
		"observers":
			observers_allowed = bool(args.get("allowed", true))
			return ""
		"start":
			if stage != Stage.LOBBY:
				return "wrong_stage"
			var force: bool = bool(args.get("force", false))
			for p in roster.humans():
				if not bool(p["ready"]) and not force:
					return "not_all_ready"
			_begin_select()
			return ""
		"return_lobby":
			if stage == Stage.RESULTS:
				_return_to_lobby()
				return ""
			return "wrong_stage"
	return "unknown_cmd"


# ------------------------------------------------------------------------------------------
# lifecycle
# ------------------------------------------------------------------------------------------
func _physics_process(_delta: float) -> void:
	tick += 1
	match stage:
		Stage.LOBBY:
			_tick_lobby()
		Stage.SELECT:
			if tick >= select_until:
				_begin_match()
			elif tick % 30 == 0:
				_broadcast_lobby()
		Stage.MATCH:
			_tick_match()
		Stage.RESULTS:
			if tick >= results_until:
				if mode == WR.MODE_PRIVATE:
					_return_to_lobby()
				else:
					stage = Stage.CLOSING
					close_at = tick + WR.secs_to_ticks(CLOSE_DELAY_S)
		Stage.CLOSING:
			if tick >= close_at:
				_log("shutdown", {"reason": "match_complete"})
				Net.close()
				get_tree().quit(0)
	if Config.quit_after_s > 0.0 and tick >= WR.secs_to_ticks(Config.quit_after_s):
		_log("shutdown", {"reason": "quit_after"})
		get_tree().quit(0)


func _tick_lobby() -> void:
	if mode == WR.MODE_PRIVATE:
		# optional unattended start for LAN hosting / automated tests: --autostart N humans
		var want: int = int(Config.get_arg("autostart", "0"))
		if want > 0 and roster.humans().filter(func(p: Dictionary) -> bool: return bool(p["connected"])).size() >= want:
			_begin_select()
		return
	var connected_humans: int = roster.humans().filter(func(p: Dictionary) -> bool: return bool(p["connected"])).size()
	if connected_humans >= expected_players:
		_begin_select()
	elif tick >= join_deadline:
		if mode == WR.MODE_RANKED or connected_humans == 0:
			_log("cancelled", {"reason": "players_missing", "have": connected_humans, "expected": expected_players})
			for c in _live_conns():
				Net.send_to(int(c["peer"]), {"t": "cancelled", "reason": "players_missing"})
			stage = Stage.CLOSING
			close_at = tick + WR.secs_to_ticks(2.0)
		else:
			_begin_select()


func _begin_select() -> void:
	stage = Stage.SELECT
	select_until = tick + WR.secs_to_ticks(float(Tuning.rules.get("character_select_s", 40)))
	roster.fill_bots(rng, _new_pid)
	_log("select", {"players": roster.players.size()})
	_broadcast_lobby()


func _begin_match() -> void:
	roster.auto_assign(rng)
	if mode == WR.MODE_RANKED:
		for p in roster.players.values():
			assert(not bool(p["bot"]), "ranked never contains bots")
	# (re)build fighters
	for f in sim.fighters.duplicate():
		sim.remove_fighter(f)
	sim.rules = TurfShiftRules.new()
	sim.rules.configure(Tuning.rules)
	sim.result_emitted = false
	sim.phase = WR.Phase.WAITING
	for p in roster.players.values():
		var f: FighterBody = sim.add_fighter(String(p["fighter"]), int(p["team"]), int(p["slot"]), String(p["name"]), bool(p["bot"]))
		f.account_id = String(p["account"])
		f.palette = String(p.get("palette", "default"))
		if bool(p["bot"]):
			var brain := BotAI.new()
			brain.difficulty = roster.bot_difficulty
			sim.bot_brains[f.entity_id] = brain
		f.present = bool(p["connected"]) or bool(p["bot"])
	sim.begin_countdown()
	stage = Stage.MATCH
	for c in conns.values():
		c["inputs"] = {}
		c["next_seq"] = -1
	recorder.begin(sim, match_id, mode, roster.state())
	for c in _live_conns():
		_send_match_setup(int(c["peer"]))
	_log("match_start", {"fighters": sim.fighters.size(), "bots": sim.bot_brains.size()})


func _send_match_setup(peer_id: int) -> void:
	var c: Dictionary = conns.get(peer_id, {})
	var fs: Array = []
	for f in sim.fighters:
		fs.append({"e": f.entity_id, "team": f.team, "fighter": f.def.id, "name": f.player_name, "bot": f.is_bot, "palette": f.palette})
	var me: int = _entity_of(int(c.get("pid", -1))) if not bool(c.get("observer", true)) else -1
	Net.send_to(peer_id, {"t": "match_setup", "you": me, "fighters": fs, "server_tick": sim.tick,
		"countdown_until": sim.countdown_until, "mode": mode, "observer": c.get("observer", true)})


func _tick_match() -> void:
	# inputs: one per fighter per tick from each client's queue
	for c in conns.values():
		if bool(c["observer"]) or int(c["pid"]) < 0:
			continue
		var e: int = _entity_of(int(c["pid"]))
		var q: Dictionary = c["inputs"]
		var frame: InputFrame = null
		if q.size() > MAX_INPUT_QUEUE:
			# client ran ahead: trim oldest frames but keep their presses (taps)
			var keys: Array = q.keys()
			keys.sort()
			var taps: int = 0
			while q.size() > 3:
				var k: int = keys.pop_front()
				taps |= (q[k] as InputFrame).taps
				q.erase(k)
			(q[keys[0]] as InputFrame).taps |= taps
			c["next_seq"] = keys[0]
		var ns: int = int(c["next_seq"])
		if q.has(ns):
			frame = q[ns]
			q.erase(ns)
			c["next_seq"] = ns + 1
		elif not q.is_empty():
			var keys2: Array = q.keys()
			keys2.sort()
			if int(keys2[0]) > ns:
				frame = q[keys2[0]]
				q.erase(keys2[0])
				c["next_seq"] = int(keys2[0]) + 1
		if frame != null:
			c["last"] = frame
			c["acked"] = frame.seq
			sim.set_input(e, frame)
		else:
			var rep: InputFrame = (c["last"] as InputFrame).copy()
			rep.taps = 0
			sim.set_input(e, rep)
	var evs: Array[Dictionary] = sim.step_tick()
	recorder.capture(sim)
	if sim.tick % Protocol.SNAPSHOT_EVERY == 0:
		vis.update(sim.tick, sim.fighters, sim.ctx.space)
		_send_snapshots()
	if not _pending_events.is_empty():
		_send_events()
	if sim.tick % 60 == 0:
		_check_afk_reconnect_forfeit()


func _on_sim_events(evs: Array) -> void:
	_pending_events.append_array(evs)
	recorder.add_events(evs)


const GLOBAL_EVENTS: Array[String] = ["zone_state", "score", "score_warning", "zone_revealed", "zone_rotated",
	"zone_activated", "sudden_death", "match_end", "countdown", "ko", "respawn"]


func _send_events() -> void:
	for c in _live_conns():
		var team: int = -1 if bool(c["observer"]) else int(roster.players.get(int(c["pid"]), {}).get("team", -1))
		var out: Array = []
		for e in _pending_events:
			if GLOBAL_EVENTS.has(String(e["type"])):
				out.append(e)
				continue
			var ok: bool = true
			for key in ["e", "a", "t"]:
				if e.has(key) and typeof(e[key]) == TYPE_INT:
					var ent: FighterBody = sim.fighter(int(e[key]))
					if ent != null and team >= 0 and ent.team != team and not vis.visible_to(team, ent.entity_id, sim.tick):
						ok = false
			if ok:
				out.append(e)
		if not out.is_empty():
			Net.send_to(int(c["peer"]), {"t": "ev", "list": out})
	_pending_events.clear()


func _send_snapshots() -> void:
	var m: Dictionary = sim.snapshot_match()
	var roster_status: Array = []
	for f in sim.fighters:
		roster_status.append({"e": f.entity_id, "alive": f.st.alive and f.present,
			"respawn_s": maxi(0, int(ceil(float(f.st.respawn_at - sim.tick) / WR.TICK_RATE))) if not f.st.alive else 0})
	for c in _live_conns():
		var observer: bool = bool(c["observer"])
		var pid: int = int(c["pid"])
		var team: int = -1 if observer else int(roster.players.get(pid, {}).get("team", -1))
		var me: int = -1 if observer else _entity_of(pid)
		var fs: Array = []
		for f in sim.fighters:
			if not f.present:
				continue
			if team >= 0 and f.team != team and not vis.visible_to(team, f.entity_id, sim.tick):
				continue   # server-side visibility filtering (no omniscient data on the wire)
			fs.append(Protocol.fighter_view_state(f, team, observer, sim.tick))
		var own: Dictionary = {}
		if me >= 0:
			var mf: FighterBody = sim.fighter(me)
			if mf != null and mf.present:
				own = mf.st.to_dict()
				own["pos"] = mf.global_position
				own["vel"] = mf.velocity
				own["on_floor"] = mf.is_on_floor()
		var qd: int = (c["inputs"] as Dictionary).size()
		Net.send_snapshot(int(c["peer"]), Protocol.encode_snapshot(sim.tick, int(c["acked"]), qd, m, roster_status, fs, own))


func _rewind_for(attacker: FighterBody) -> int:
	## D-012: bounded lag compensation from SERVER-measured RTT only.
	if attacker.is_bot:
		return 0
	var pid: int = -1
	for p in roster.players.values():
		if int(p["team"]) * WR.TEAM_SIZE + int(p["slot"]) == attacker.entity_id:
			pid = int(p["pid"])
	if not pid_to_peer.has(pid):
		return 0
	var rtt: float = Net.rtt_ms(int(pid_to_peer[pid]))
	var ms: float = rtt * 0.5 + float(Protocol.INTERP_DELAY_TICKS) * 1000.0 / WR.TICK_RATE
	return clampi(int(round(ms * WR.TICK_RATE / 1000.0)), 0, 12)


func _check_afk_reconnect_forfeit() -> void:
	var afk_warn: int = WR.secs_to_ticks(float(Tuning.rules.get("afk_warning_s", 45)))
	var afk_kick: int = WR.secs_to_ticks(float(Tuning.rules.get("afk_kick_s", 60)))
	var live: bool = sim.phase == WR.Phase.LIVE or sim.phase == WR.Phase.SUDDEN_DEATH
	for p in roster.players.values():
		if bool(p["bot"]):
			continue
		var pid: int = int(p["pid"])
		var f: FighterBody = sim.fighter(_entity_of(pid))
		if f == null:
			continue
		# reconnect reservation expiry
		if disconnected.has(pid) and tick >= int(disconnected[pid]):
			disconnected.erase(pid)
			_abandon(pid, f, "disconnect")
			continue
		if not live or not bool(p["connected"]) or f.is_bot:
			continue
		if f.st.idle_ticks >= afk_kick:
			_log("afk", {"pid": pid})
			f.set_meta("afk", true)
			if pid_to_peer.has(pid):
				Net.send_to(int(pid_to_peer[pid]), {"t": "kicked", "reason": "afk"})
				Net.disconnect_peer(int(pid_to_peer[pid]))
			disconnected.erase(pid)
			_abandon(pid, f, "afk")
		elif f.st.idle_ticks >= afk_warn and not _afk_warned.has(pid):
			_afk_warned[pid] = true
			if pid_to_peer.has(pid):
				Net.send_to(int(pid_to_peer[pid]), {"t": "afk_warning", "seconds": (afk_kick - f.st.idle_ticks) / WR.TICK_RATE})
		elif f.st.idle_ticks < afk_warn:
			_afk_warned.erase(pid)
	# forfeit: a team with no connected humans (and no bots) for 30 s loses
	if live:
		for team in range(2):
			var active: int = 0
			for f2 in sim.fighters:
				if f2.team == team and f2.present:
					active += 1
			if active == 0:
				if _forfeit_since[team] < 0:
					_forfeit_since[team] = tick
				elif tick - _forfeit_since[team] >= WR.secs_to_ticks(float(Tuning.rules.get("forfeit_empty_team_s", 30))):
					_log("forfeit", {"team": team})
					sim.forfeit(team)
			else:
				_forfeit_since[team] = -1


func _abandon(pid: int, f: FighterBody, why: String) -> void:
	## Bot replacement only where the mode explicitly allows it — never in ranked.
	f.set_meta("abandoned", true)
	if roster.allow_bots and mode != WR.MODE_RANKED:
		f.is_bot = true
		f.player_name = "BOT " + f.def.display_name
		var brain := BotAI.new()
		brain.difficulty = roster.bot_difficulty
		sim.bot_brains[f.entity_id] = brain
		f.present = true
		if f.st.alive:
			sim.respawn(f)
		_log("bot_takeover", {"pid": pid, "reason": why})
	else:
		f.present = false
		sim.occupancy.forget(f.entity_id)
		_log("abandoned", {"pid": pid, "reason": why})


func _on_match_finished(result: Dictionary) -> void:
	if not result_payload.is_empty():
		return   # completion + submission happen exactly once
	stage = Stage.RESULTS
	results_until = tick + WR.secs_to_ticks(float(Tuning.rules.get("results_s", 25)))
	recorder.finish(result)
	var dir: String = Config.replay_dir if Config.replay_dir != "" else "user://replays"
	replay_path = dir.path_join("%s.wrr" % match_id.replace(":", "_"))
	var err: int = recorder.save(replay_path)
	result["replay_file"] = replay_path if err == OK else ""
	result_payload = result
	_log("match_end", {"winner": result["winner_team"], "score": result["score"], "reason": result["ended_reason"],
		"replay": result["replay_file"]})
	for c in _live_conns():
		Net.send_to(int(c["peer"]), {"t": "results", "result": result})
	if service.enabled and mode != WR.MODE_PRIVATE:
		var body: Dictionary = _service_result_body(result)
		service.post_result(match_id, body)


func _service_result_body(result: Dictionary) -> Dictionary:
	var players: Array = []
	for r in result["players"]:
		players.append({"account_id": r["account_id"], "team": r["team"], "fighter": r["fighter"], "kos": r["kos"],
			"knocked_out": r["knocked_out"], "damage_dealt": r["damage_dealt"], "control_seconds": r["control_seconds"],
			"abandoned": r["abandoned"], "afk": r["afk"]})
	var bots: Array = []
	for b in result["bots"]:
		bots.append({"team": b["team"], "fighter": b["fighter"]})
	return {"match_id": match_id, "winner_team": result["winner_team"], "score": result["score"],
		"duration_s": snappedf(float(result["duration_s"]), 0.01), "sudden_death": result["sudden_death"],
		"ended_reason": result["ended_reason"], "players": players, "bots": bots}


func _check_rematch() -> void:
	var hs: Array = roster.humans().filter(func(p: Dictionary) -> bool: return bool(p["connected"]))
	if hs.is_empty():
		return
	for p in hs:
		if not bool(p["rematch"]):
			return
	_log("rematch", {})
	roster.reset_for_rematch()
	result_payload = {}
	stage = Stage.LOBBY
	_begin_select()


func _return_to_lobby() -> void:
	result_payload = {}
	for p in roster.players.values().duplicate():
		if bool(p["bot"]):
			roster.remove_player(int(p["pid"]))
		else:
			p["locked"] = false
			p["ready"] = false
			p["fighter"] = ""
	stage = Stage.LOBBY
	for f in sim.fighters.duplicate():
		sim.remove_fighter(f)
	_broadcast_lobby()


func _broadcast_lobby() -> void:
	var st: Dictionary = roster.state()
	var msg: Dictionary = {"t": "lobby", "stage": stage, "roster": st, "admin": admin_pid, "mode": mode,
		"select_left_s": maxf(0.0, float(select_until - tick) / WR.TICK_RATE) if stage == Stage.SELECT else 0.0,
		"observers_allowed": observers_allowed, "expected": expected_players}
	for c in _live_conns():
		Net.send_to(int(c["peer"]), msg)
