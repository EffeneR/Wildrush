class_name ClientSession
extends Node
## Online client (D-013): sends numbered input intentions, predicts the local fighter with the
## same FighterLogic as the server, reconciles on authoritative acknowledgements, and
## interpolates remote fighters 100 ms behind. Never sends positions, damage or scores.

signal status_changed(status: String, detail: String)
signal welcomed(info: Dictionary)
signal lobby_updated(lobby: Dictionary)
signal match_setup_received(info: Dictionary)
signal events_ready(events: Array)
signal chat_received(msg: Dictionary)
signal ping_received(msg: Dictionary)
signal results_received(result: Dictionary)
signal server_notice(msg: Dictionary)

var status: String = "idle"
var info: Dictionary = {}              # welcome data
var lobby: Dictionary = {}
var setup: Dictionary = {}             # match_setup
var local_entity: int = -1
var observer: bool = false
var input_source: Object = null        # has sample(session) -> InputFrame
var world: Node3D = null
var layout: ArenaLayout = null
var pred: FighterBody = null
var proxies: Dictionary = {}           # entity -> FighterBody (non-simulated positions for prediction)
var pctx := SimContext.new()
var pending: Array = []                # unacknowledged InputFrames
var sent_history: Array = []           # last frames for redundancy
var seq: int = 0
var pred_tick: int = 0
var last_ack: int = 0
var latest_snap: Dictionary = {}
var _snap_pending: bool = false
var snap_buffer: Array = []            # [{tick, recv_ms, fighters: {e: state}, match, roster}]
var server_tick_est: float = 0.0
var _last_snap_recv_ms: int = 0
var match_state: Dictionary = {}
var roster_status: Dictionary = {}     # e -> {alive, respawn_s}
var fighter_info: Dictionary = {}      # e -> {team, fighter, name, bot, palette}
var event_queue: Array = []            # server events waiting for render time
var predicted_keys: Dictionary = {}    # dedupe predicted vs confirmed hits
var visual_offset: Vector3 = Vector3.ZERO
var correction_stats: Dictionary = {"reconciles": 0, "max_error_m": 0.0, "sum_error_m": 0.0, "snaps": 0, "late_snaps": 0}
var results: Dictionary = {}
var reconnect_token: String = ""
var host: String = ""
var port: int = 0


func _ready() -> void:
	Net.client_handler = self
	Net.client_connected.connect(func() -> void: _set_status("connected", ""))
	Net.client_failed.connect(func(r: String) -> void: _set_status("failed", r))
	Net.client_disconnected.connect(func() -> void: _set_status("disconnected", ""))


func _set_status(s: String, detail: String) -> void:
	status = s
	status_changed.emit(s, detail)


func connect_to(p_host: String, p_port: int, auth: Dictionary) -> int:
	host = p_host
	port = p_port
	var a: Dictionary = auth.duplicate()
	a["proto"] = WR.PROTOCOL_VERSION
	a["build"] = WR.BUILD_ID
	if reconnect_token != "":
		a["reconnect"] = reconnect_token
	_set_status("connecting", "%s:%d" % [p_host, p_port])
	return Net.start_client(p_host, p_port, a)


func leave() -> void:
	if Net.role == "client":
		Net.send_msg({"t": "leave"})
	Net.close()
	_teardown_world()
	_set_status("idle", "")


func on_auth_reply(d: Dictionary) -> void:
	info = d
	reconnect_token = String(d.get("token", ""))


# ------------------------------------------------------------------------------------------
# server messages
# ------------------------------------------------------------------------------------------
func on_server_msg(d: Dictionary) -> void:
	match String(d.get("t", "")):
		"welcome":
			info.merge(d, true)
			observer = bool(d.get("observer", false))
			reconnect_token = String(d.get("token", reconnect_token))
			welcomed.emit(d)
		"lobby":
			lobby = d
			lobby_updated.emit(d)
		"match_setup":
			_on_match_setup(d)
		"ev":
			var lst: Array = d.get("list", [])
			for e in lst:
				event_queue.append(e)
		"chat":
			chat_received.emit(d)
		"ping":
			ping_received.emit(d)
		"results":
			results = d.get("result", {})
			results_received.emit(results)
		_:
			server_notice.emit(d)


func _on_match_setup(d: Dictionary) -> void:
	setup = d
	local_entity = int(d.get("you", -1))
	observer = bool(d.get("observer", observer)) or local_entity < 0
	fighter_info.clear()
	for f in d.get("fighters", []):
		fighter_info[int(f["e"])] = f
	_build_world()
	pending.clear()
	sent_history.clear()
	snap_buffer.clear()
	event_queue.clear()
	predicted_keys.clear()
	results = {}
	server_tick_est = float(d.get("server_tick", 0))
	pred_tick = int(d.get("server_tick", 0))
	match_setup_received.emit(d)


func _build_world() -> void:
	_teardown_world()
	world = Node3D.new()
	world.name = "ClientWorld"
	add_child(world)
	layout = ArenaLayout.load_file()
	ArenaBuilder.build_collision(world, layout)
	pctx = SimContext.new()
	pctx.predicting = true
	pctx.perch_ledges = layout.perch_ledges
	for t in range(WR.NUM_TEAMS):
		pctx.spawn_volumes[t] = layout.spawn_volume(t)
	var fighters: Array = []
	for e in fighter_info.keys():
		var fi: Dictionary = fighter_info[e]
		var body := FighterBody.new()
		body.setup(Tuning.fighter(String(fi["fighter"])), int(fi["team"]), int(e))
		body.is_bot = bool(fi.get("bot", false))
		world.add_child(body)
		if int(e) == local_entity:
			pred = body
		else:
			body.collision_layer = 0   # proxies: positions only (never simulated here)
			body.collision_mask = 0
			proxies[int(e)] = body
		fighters.append(body)
	pctx.fighters = fighters


func _teardown_world() -> void:
	if world != null:
		world.queue_free()
	world = null
	pred = null
	proxies.clear()


# ------------------------------------------------------------------------------------------
# snapshots
# ------------------------------------------------------------------------------------------
func on_snapshot(data: PackedByteArray) -> void:
	var s: Dictionary = Protocol.decode_snapshot(data)
	if s.is_empty():
		return
	correction_stats["snaps"] = int(correction_stats["snaps"]) + 1
	if not snap_buffer.is_empty() and int(s["tick"]) <= int(snap_buffer[snap_buffer.size() - 1]["tick"]):
		correction_stats["late_snaps"] = int(correction_stats["late_snaps"]) + 1
		return   # out-of-order or duplicate snapshot
	var now: int = Time.get_ticks_msec()
	var fs: Dictionary = {}
	for f in s["fighters"]:
		fs[int(f["e"])] = f
	snap_buffer.append({"tick": int(s["tick"]), "recv": now, "fighters": fs, "match": s["match"]})
	while snap_buffer.size() > 40:
		snap_buffer.pop_front()
	match_state = s["match"]
	for r in s["roster"]:
		roster_status[int(r["e"])] = r
	# server clock estimate (smoothed toward the newest snapshot)
	var est_from_snap: float = float(s["tick"])
	if server_tick_est <= 0.0 or absf(server_tick_est - est_from_snap) > 30.0:
		server_tick_est = est_from_snap
	else:
		server_tick_est = lerpf(server_tick_est, est_from_snap, 0.1)
	_last_snap_recv_ms = now
	latest_snap = s
	_snap_pending = true


func render_tick() -> float:
	return server_tick_est - float(Protocol.INTERP_DELAY_TICKS)


# ------------------------------------------------------------------------------------------
# per-tick: inputs, prediction, reconciliation
# ------------------------------------------------------------------------------------------
func _physics_process(_delta: float) -> void:
	if Net.role != "client" or setup.is_empty():
		return
	server_tick_est += 1.0
	if _snap_pending:
		_snap_pending = false
		_reconcile(latest_snap)
	_update_proxies()
	if pred == null or observer:
		_flush_events()
		return
	seq += 1
	var inp: InputFrame = InputFrame.new()
	if input_source != null:
		inp = input_source.sample(self)
	inp.seq = seq
	inp = inp.quantized()   # predict with exactly what the server will decode
	pending.append(inp)
	sent_history.append(inp)
	while sent_history.size() > Protocol.INPUT_REDUNDANCY:
		sent_history.pop_front()
	Net.send_inputs(sent_history)
	pred_tick += 1
	pctx.tick = pred_tick
	pctx.events = []
	pctx.space = world.get_world_3d().direct_space_state
	FighterLogic.step(pred, inp, pctx)
	CombatResolver.resolve(pctx)
	var predicted: Array = []
	for e in pctx.events:
		if String(e["type"]) == "predicted_hit":
			predicted_keys["%d:%d:%d:%d" % [int(e["a"]), int(e["ev"]), int(e["hi"]), int(e["t"])]] = true
		e["predicted"] = true
		predicted.append(e)
	if not predicted.is_empty():
		events_ready.emit(predicted)
	visual_offset = visual_offset.lerp(Vector3.ZERO, 0.18)
	_flush_events()


func _reconcile(s: Dictionary) -> void:
	var ack: int = int(s["ack"])
	last_ack = ack
	while not pending.is_empty() and (pending[0] as InputFrame).seq <= ack:
		pending.pop_front()
	if pred == null or not s.has("own"):
		return
	var own: Dictionary = s["own"]
	var before: Vector3 = pred.global_position
	pred.st.from_dict(own, pred.def)
	pred.global_position = own["pos"]
	pred.velocity = own["vel"]
	pred.apply_yaw()
	pred_tick = int(s["tick"])
	# replay unacknowledged inputs on top of the authoritative state
	var saved_events: Array[Dictionary] = pctx.events
	pctx.space = world.get_world_3d().direct_space_state
	for inp: InputFrame in pending:
		pred_tick += 1
		pctx.tick = pred_tick
		pctx.events = []
		FighterLogic.step(pred, inp, pctx)
	pctx.events = saved_events
	var err: float = before.distance_to(pred.global_position)
	if err < 5.0:   # teleports (respawn, fall recovery) are not prediction errors
		correction_stats["reconciles"] = int(correction_stats["reconciles"]) + 1
		correction_stats["sum_error_m"] = float(correction_stats["sum_error_m"]) + err
		correction_stats["max_error_m"] = maxf(float(correction_stats["max_error_m"]), err)
	else:
		correction_stats["teleports"] = int(correction_stats.get("teleports", 0)) + 1
	if err < 2.0:
		visual_offset += before - pred.global_position   # smooth small corrections visually
	else:
		visual_offset = Vector3.ZERO                       # snap on large corrections (teleport/respawn)


func _update_proxies() -> void:
	var rt: float = render_tick()
	for e in proxies.keys():
		var st: Dictionary = interpolated(int(e), rt)
		var b: FighterBody = proxies[e]
		if st.is_empty():
			b.present = false
			continue
		b.present = true
		b.global_position = st["pos"]
		b.st.yaw = float(st["yaw"])
		b.st.alive = (int(st["flags"]) & Protocol.F_ALIVE) != 0
		b.apply_yaw()


func interpolated(e: int, rt: float) -> Dictionary:
	## Remote fighter state at render tick `rt` (linear interpolation between snapshots).
	var n: int = snap_buffer.size()
	if n == 0:
		return {}
	var prev: Dictionary = {}
	var nxt: Dictionary = {}
	for i in range(n):
		var sn: Dictionary = snap_buffer[i]
		if float(sn["tick"]) <= rt:
			if (sn["fighters"] as Dictionary).has(e):
				prev = sn
		else:
			if (sn["fighters"] as Dictionary).has(e):
				nxt = sn
				break
	if prev.is_empty() and nxt.is_empty():
		return {}
	if prev.is_empty():
		return nxt["fighters"][e]
	if nxt.is_empty():
		# extrapolate at most 100 ms, then hold
		var a: Dictionary = (prev["fighters"][e] as Dictionary).duplicate()
		var dt: float = minf((rt - float(prev["tick"])) / WR.TICK_RATE, 0.1)
		a["pos"] = (a["pos"] as Vector3) + (a["vel"] as Vector3) * dt
		return a
	var sa: Dictionary = prev["fighters"][e]
	var sb: Dictionary = nxt["fighters"][e]
	var u: float = clampf((rt - float(prev["tick"])) / maxf(1.0, float(nxt["tick"]) - float(prev["tick"])), 0.0, 1.0)
	var out: Dictionary = sb.duplicate()
	out["pos"] = (sa["pos"] as Vector3).lerp(sb["pos"] as Vector3, u)
	out["yaw"] = lerp_angle(float(sa["yaw"]), float(sb["yaw"]), u)
	out["vel"] = (sa["vel"] as Vector3).lerp(sb["vel"] as Vector3, u)
	if int(sa["clip"]) == int(sb["clip"]):
		out["ct"] = lerpf(float(sa["ct"]), float(sb["ct"]), u)
	else:
		out = (sa if u < 0.5 else sb).duplicate()
		out["pos"] = (sa["pos"] as Vector3).lerp(sb["pos"] as Vector3, u)
		out["yaw"] = lerp_angle(float(sa["yaw"]), float(sb["yaw"]), u)
	return out


func _flush_events() -> void:
	if event_queue.is_empty():
		return
	var rt: float = render_tick()
	var ready: Array = []
	var keep: Array = []
	for e in event_queue:
		var et: int = int(e.get("tick", 0))
		var mine: bool = int(e.get("a", -1)) == local_entity or int(e.get("e", -1)) == local_entity
		if mine or float(et) <= rt + 0.5 or float(et) < server_tick_est - 30.0:
			if String(e.get("type", "")) == "hit":
				var k: String = "%d:%d:%d:%d" % [int(e["a"]), int(e["ev"]), int(e["hi"]), int(e["t"])]
				if predicted_keys.has(k):
					e["confirmed_predicted"] = true   # presentation skips duplicate feedback
					predicted_keys.erase(k)
			ready.append(e)
		else:
			keep.append(e)
	event_queue = keep
	if not ready.is_empty():
		events_ready.emit(ready)


# ------------------------------------------------------------------------------------------
# requests (lobby / match)
# ------------------------------------------------------------------------------------------
func request(d: Dictionary) -> void:
	Net.send_msg(d)


func local_view_state() -> Dictionary:
	if pred == null:
		return {}
	return {"pos": pred.global_position + visual_offset, "yaw": pred.st.yaw, "vel": pred.velocity, "st": pred.st}
