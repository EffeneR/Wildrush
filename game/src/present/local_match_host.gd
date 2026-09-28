class_name LocalMatchHost
extends MatchHost
## Offline match or training session: the authoritative MatchSim runs in-process at 60 Hz
## with server-side bots (same rules, same bot code as online). Records a replay.

const PICKS_DEFAULT: Array[String] = ["nyx", "bruno", "vex", "hops", "scrap"]

var sim: MatchSim = null
var params: Dictionary = {}
var recorder := ReplayRecorder.new()
var replay_path: String = ""
var _started: bool = false
var _local_body: FighterBody = null
var _dummy_brains: Dictionary = {}
var _finished_sent: bool = false
var _pending_events: Array = []


func setup(p: Dictionary) -> void:
	params = p
	mode = String(p.get("mode", WR.MODE_OFFLINE))
	var seed_v: int = int(p.get("seed", randi() % 1000000 + 1))
	sim = MatchSim.new()
	sim.name = "Sim"
	add_child(sim)
	sim.setup(ArenaLayout.load_file(), WR.MODE_TRAINING if mode == WR.MODE_TRAINING else WR.MODE_OFFLINE, seed_v, true)
	sim.match_id = "offline-%d" % Time.get_unix_time_from_system()
	regulation_s = float(Tuning.rules.get("regulation_s", 480))
	var me: String = String(p.get("fighter", "nyx"))
	var player_name: String = String(Settings.get_value("player", "name"))
	local_team = 0
	_local_body = sim.add_fighter(me, 0, 0, player_name, false)
	_local_body.palette = String(p.get("palette", Profile.selected_palette(me)))
	local_entity = _local_body.entity_id
	if mode == WR.MODE_TRAINING:
		_setup_training(p.get("training", {}))
	else:
		var diff: String = String(p.get("difficulty", "normal"))
		var allies: Array = p.get("allies", [])
		var enemies: Array = p.get("enemies", [])
		var rng := RandomNumberGenerator.new()
		rng.seed = seed_v
		var ally_pool: Array = PICKS_DEFAULT.filter(func(x: String) -> bool: return x != me)
		for slot in range(1, WR.TEAM_SIZE):
			var fid: String = String(allies[slot - 1]) if allies.size() >= slot else String(ally_pool[(slot - 1) % ally_pool.size()])
			_add_bot(fid, 0, slot, diff, rng)
		var enemy_pool: Array = PICKS_DEFAULT.duplicate()
		for slot2 in range(WR.TEAM_SIZE):
			var fid2: String = String(enemies[slot2]) if enemies.size() > slot2 else String(enemy_pool[(slot2 + 2) % enemy_pool.size()])
			_add_bot(fid2, 1, slot2, diff, rng)
	for f in sim.fighters:
		fighter_info[f.entity_id] = {"team": f.team, "fighter": f.def.id, "name": f.player_name, "bot": f.is_bot or f.is_dummy,
			"palette": f.palette}
	sim.sim_events.connect(_on_sim_events)
	sim.match_finished.connect(_on_finished)


func _add_bot(fid: String, team: int, slot: int, diff: String, rng: RandomNumberGenerator) -> void:
	var names: Array = ["Ash", "Birch", "Cobble", "Dune", "Ember", "Flint", "Gale", "Hazel", "Ivy", "Juniper"]
	var f: FighterBody = sim.add_fighter(fid, team, slot, "%s (Bot)" % names[(team * 5 + slot + rng.randi_range(0, 9)) % names.size()], true)
	var b := BotAI.new()
	b.difficulty = diff
	sim.bot_brains[f.entity_id] = b
	f.palette = ["default", "dusk", "ember", "frost"][rng.randi_range(0, 3)] if team == 1 else "default"


func _setup_training(t: Dictionary) -> void:
	var n: int = clampi(int(t.get("dummies", 3)), 1, 5)
	var behaviour: String = String(t.get("dummy_behaviour", "idle"))
	var fids: Array = PICKS_DEFAULT
	for i in range(n):
		var f: FighterBody = sim.add_fighter(String(fids[i % fids.size()]), 1, i, "Dummy %d" % (i + 1), false)
		f.is_dummy = true
		f.set_meta("invulnerable", bool(t.get("invulnerable", false)))
		var brain := TrainingDummy.new()
		brain.behaviour = behaviour
		sim.bot_brains[f.entity_id] = brain
	# dummies stand in a row in Market Square, facing the player's spawn side
	var c: Vector3 = sim.layout.zone_center("B")
	for i in range(sim.fighters.size()):
		var f2: FighterBody = sim.fighters[i]
		if f2.is_dummy:
			f2.global_position = c + Vector3(-4.0 + 4.0 * f2.slot, 0.002, -3.0)
			f2.st.yaw = MathX.yaw_from_dir(Vector3(0, 0, 1))   # face the player (south)
			f2.apply_yaw()
			f2.set_meta("safe_pos", f2.global_position)
			f2.set_meta("train_pos", f2.global_position)
	_local_body.global_position = c + Vector3(0, 0.002, 6.0)
	_local_body.st.yaw = 0.0
	_local_body.apply_yaw()
	_local_body.set_meta("safe_pos", _local_body.global_position)
	_local_body.set_meta("train_pos", _local_body.global_position)


func set_dummy_behaviour(b: String) -> void:
	for e in sim.bot_brains.keys():
		var brain: BotBrain = sim.bot_brains[e]
		if brain is TrainingDummy:
			(brain as TrainingDummy).behaviour = b


func reset_training() -> void:
	for f in sim.fighters:
		f.reset_vitals()
		f.st.alive = true
		f.st.respawn_at = -1
		f.collision_layer = WR.LAYER_FIGHTERS
		f.global_position = f.get_meta("train_pos", f.global_position)
		f.velocity = Vector3.ZERO


func physics_step(inp: InputFrame) -> void:
	if sim == null:
		return
	if not _started:
		if not sim.nav_ready():
			return
		_started = true
		if mode != WR.MODE_TRAINING:
			sim.begin_countdown()
			recorder.begin(sim, sim.match_id, mode, {})
	if inp != null:
		sim.set_input(local_entity, inp)
	var evs: Array[Dictionary] = sim.step_tick()
	if recorder.active:
		recorder.capture(sim)
	if mode == WR.MODE_TRAINING:
		_training_upkeep()


func _training_upkeep() -> void:
	# training never ends: KO'd dummies and the player respawn quickly in place
	for f in sim.fighters:
		if not f.st.alive and sim.tick - f.st.ko_tick > WR.secs_to_ticks(2.0):
			sim.respawn(f)
			if f.has_meta("train_pos"):
				f.global_position = f.get_meta("train_pos")
				f.set_meta("safe_pos", f.global_position)


func _on_sim_events(evs: Array) -> void:
	if recorder.active:
		recorder.add_events(evs)
	events.emit(evs)


func _on_finished(result: Dictionary) -> void:
	if _finished_sent:
		return
	_finished_sent = true
	recorder.finish(result)
	replay_path = "user://replays/%s.wrr" % sim.match_id
	var err: int = recorder.save(replay_path)
	if err != OK:
		replay_path = ""
	var awards: Dictionary = Profile.award_offline_match(result, local_entity) if mode == WR.MODE_OFFLINE else {}
	result_info = {"result": result, "my_entity": local_entity, "my_team": local_team, "mode": mode,
		"fighter": _local_body.def.id, "awards": awards, "replay_path": replay_path, "params": params}
	finished.emit(result_info)


func views(_dt: float) -> Dictionary:
	var out: Dictionary = {}
	for f in sim.fighters:
		out[f.entity_id] = MatchHost.view_from_body(f, sim.tick)
	return out


func match_state() -> Dictionary:
	var m: Dictionary = sim.snapshot_match()
	m["countdown_s"] = maxf(0.0, float(sim.countdown_until - sim.tick) / WR.TICK_RATE) if sim.phase == WR.Phase.COUNTDOWN else 0.0
	m["training"] = mode == WR.MODE_TRAINING
	m["loading"] = not _started
	return m


func local_status() -> Dictionary:
	return MatchHost.status_from_body(_local_body, sim.tick)


func local_body() -> FighterBody:
	return _local_body


func roster() -> Array:
	var rows: Array = []
	for f in sim.fighters:
		rows.append({"e": f.entity_id, "team": f.team, "fighter": f.def.id, "name": f.player_name, "bot": f.is_bot,
			"kos": f.st.kos, "kod": f.st.knocked_out, "dmg": int(round(f.st.damage_dealt)),
			"ctrl_s": int(f.st.get_meta("zone_ticks", 0)) / WR.TICK_RATE, "alive": f.st.alive,
			"respawn_s": maxf(0.0, float(f.st.respawn_at - sim.tick) / WR.TICK_RATE) if not f.st.alive else 0.0})
	return rows


func send_ping(pos: Vector3, kind: String) -> void:
	ping.emit({"from": local_entity, "pos": pos, "kind": kind})


func leave() -> void:
	if sim != null and not sim.rules.finished and mode != WR.MODE_TRAINING and not _finished_sent:
		sim.forfeit(local_team)
