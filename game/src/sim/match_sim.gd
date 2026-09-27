class_name MatchSim
extends Node3D
## Authoritative match simulation (spec §4–§6, D-005). Used by offline play (in-process),
## the dedicated server, and headless tests. Never touches visuals, audio or UI.

signal sim_events(events: Array)
signal match_finished(result: Dictionary)

var layout: ArenaLayout
var collision_root: Node3D
var navmesh: NavigationMesh
var nav_map: RID
var nav_region: RID
var fighters: Array[FighterBody] = []
var by_entity: Dictionary = {}
var rules := TurfShiftRules.new()
var occupancy := ZoneOccupancy.new()
var ctx := SimContext.new()
var tick: int = 0
var phase: int = WR.Phase.WAITING
var countdown_until: int = -1
var mode: String = WR.MODE_OFFLINE
var match_id: String = ""
var seed_value: int = 1
var rng := RandomNumberGenerator.new()
var auto_tick: bool = false
var inputs: Dictionary = {}            # entity_id -> InputFrame for the next tick
var last_inputs: Dictionary = {}       # entity_id -> last applied InputFrame
var bot_brains: Dictionary = {}        # entity_id -> BotBrain
var result: Dictionary = {}
var result_emitted: bool = false
var event_log_hook: Callable = Callable()
var training: bool = false
var build_nav: bool = true
var _neutral := InputFrame.new()


func setup(p_layout: ArenaLayout, p_mode: String, p_seed: int = 1, p_build_nav: bool = true) -> void:
	layout = p_layout
	mode = p_mode
	seed_value = p_seed
	rng.seed = p_seed
	training = p_mode == WR.MODE_TRAINING
	build_nav = p_build_nav
	rules.configure(Tuning.rules)
	occupancy.configure(Tuning.rules, layout.zones)
	collision_root = ArenaBuilder.build_collision(self, layout)
	ctx.perch_ledges = layout.perch_ledges
	ctx.training = training
	ctx.fall_recovery_y = float(layout.data.get("fall_recovery_y", -12.0))
	for t in range(WR.NUM_TEAMS):
		ctx.spawn_volumes[t] = layout.spawn_volume(t)
	if build_nav:
		_setup_navigation()


func _setup_navigation() -> void:
	navmesh = ArenaBuilder.load_or_bake_navmesh(collision_root, layout)
	nav_map = NavigationServer3D.map_create()
	NavigationServer3D.map_set_cell_size(nav_map, navmesh.cell_size)
	NavigationServer3D.map_set_cell_height(nav_map, navmesh.cell_height)
	NavigationServer3D.map_set_active(nav_map, true)
	nav_region = NavigationServer3D.region_create()
	NavigationServer3D.region_set_map(nav_region, nav_map)
	NavigationServer3D.region_set_navigation_mesh(nav_region, navmesh)
	NavigationServer3D.map_force_update(nav_map)


func _exit_tree() -> void:
	if nav_region.is_valid():
		NavigationServer3D.free_rid(nav_region)
	if nav_map.is_valid():
		NavigationServer3D.free_rid(nav_map)


func add_fighter(fighter_id: String, team: int, slot: int, p_name: String, is_bot: bool = false, entity_id: int = -1) -> FighterBody:
	var def: FighterDef = Tuning.fighter(fighter_id)
	assert(def != null, "unknown fighter " + fighter_id)
	var f := FighterBody.new()
	var eid: int = entity_id if entity_id >= 0 else team * WR.TEAM_SIZE + slot
	f.setup(def, team, eid)
	f.slot = slot
	f.player_name = p_name
	f.is_bot = is_bot
	add_child(f)
	fighters.append(f)
	fighters.sort_custom(func(a: FighterBody, b: FighterBody) -> bool: return a.entity_id < b.entity_id)
	by_entity[eid] = f
	ctx.fighters = fighters
	_place_at_spawn(f, slot)
	return f


func remove_fighter(f: FighterBody) -> void:
	fighters.erase(f)
	by_entity.erase(f.entity_id)
	bot_brains.erase(f.entity_id)
	ctx.fighters = fighters
	f.queue_free()


func fighter(entity_id: int) -> FighterBody:
	return by_entity.get(entity_id) as FighterBody


func _place_at_spawn(f: FighterBody, idx: int) -> void:
	var pts: Array = layout.spawn_points(f.team)
	if pts.is_empty():
		return
	var p: Dictionary = pts[idx % pts.size()]
	f.global_position = p["pos"] + Vector3(0, 0.002, 0)
	f.st.yaw = float(p["yaw"])
	f.apply_yaw()
	f.set_meta("safe_pos", p["pos"])


func begin_countdown() -> void:
	phase = WR.Phase.COUNTDOWN
	countdown_until = tick + WR.secs_to_ticks(float(Tuning.rules.get("pre_match_countdown_s", 5)))
	_emit_now([{"type": "countdown", "until": countdown_until, "tick": tick}])


func begin_live() -> void:
	phase = WR.Phase.LIVE
	var ev: Array[Dictionary] = rules.start_live()
	occupancy.set_zone(rules.active_zone)
	for e in ev:
		e["tick"] = tick
	_emit_now(ev)


func set_input(entity_id: int, frame: InputFrame) -> void:
	inputs[entity_id] = frame


func _physics_process(_delta: float) -> void:
	if auto_tick:
		step_tick()


func step_tick() -> Array[Dictionary]:
	## One authoritative 60 Hz tick. Must run inside a physics frame (fixed delta).
	tick += 1
	ctx.tick = tick
	ctx.events = []
	ctx.space = get_world_3d().direct_space_state
	# countdown -> live
	if phase == WR.Phase.COUNTDOWN and tick >= countdown_until:
		begin_live()
	# inputs are frozen only during the pre-match countdown and after completion
	var running: bool = phase != WR.Phase.COUNTDOWN and phase != WR.Phase.FINISHED
	# 1. inputs (bots think here using only fair observations)
	for eid in bot_brains.keys():
		var bf: FighterBody = by_entity.get(eid)
		if bf != null and bf.present:
			inputs[eid] = (bot_brains[eid] as BotBrain).think(self, bf)
	# 2. clock
	rules.advance_clock()
	# 3–5. fighters in entity order
	for f in fighters:
		var inp: InputFrame = _input_for(f, running)
		FighterLogic.step(f, inp, ctx)
	_soft_separation()
	for f in fighters:
		f.record_history(tick)
	# 6. hit detection & resolution
	CombatResolver.resolve(ctx)
	# 7. knockouts
	_process_knockouts()
	# 8. respawns
	_process_respawns()
	# 9–12. territory, scoring, victory, rotation
	if phase == WR.Phase.LIVE or phase == WR.Phase.SUDDEN_DEATH:
		occupancy.set_zone(rules.active_zone)
		var presence: Array[int] = occupancy.count_presence(fighters)
		var rev: Array[Dictionary] = rules.evaluate(presence)
		if rules.zone_state == WR.ZoneState.CONTROLLED:
			for f in fighters:
				if f.team == rules.controlling_team and f.is_eligible_occupant() and occupancy.is_inside(f.entity_id, f.feet_position()):
					f.st.set_meta("zone_ticks", int(f.st.get_meta("zone_ticks", 0)) + 1)
		for e in rev:
			e["tick"] = tick
			ctx.events.append(e)
			if String(e["type"]) == "sudden_death":
				phase = WR.Phase.SUDDEN_DEATH
			elif String(e["type"]) == "match_end":
				_on_match_end(e)
	# 13. emit
	var out: Array[Dictionary] = ctx.events
	if not out.is_empty():
		sim_events.emit(out)
		if event_log_hook.is_valid():
			event_log_hook.call(out)
	return out


func _input_for(f: FighterBody, running: bool) -> InputFrame:
	var inp: InputFrame = inputs.get(f.entity_id)
	if inp == null:
		# missing input: repeat held state with press-edges suppressed (D-005 step 1)
		var last: InputFrame = last_inputs.get(f.entity_id)
		inp = last.copy() if last != null else _neutral.copy()
	inputs.erase(f.entity_id)
	last_inputs[f.entity_id] = inp
	if not running or phase == WR.Phase.FINISHED:
		var frozen := InputFrame.new()
		frozen.seq = inp.seq
		frozen.yaw = inp.yaw
		frozen.pitch = inp.pitch
		return frozen
	return inp


func _soft_separation() -> void:
	## Fighters never hard-collide; overlapping bodies are pushed apart gently so nobody can
	## be trapped by teammates (spec §5) and bodies do not stack.
	var n: int = fighters.size()
	var step_max: float = Tuning.soft_sep_speed * WR.TICK_DT
	for i in range(n):
		var a: FighterBody = fighters[i]
		if not a.present or not a.st.alive or a.st.ctrl == WR.Ctrl.GRABBED:
			continue
		for j in range(i + 1, n):
			var b: FighterBody = fighters[j]
			if not b.present or not b.st.alive or b.st.ctrl == WR.Ctrl.GRABBED:
				continue
			var d := Vector3(b.global_position.x - a.global_position.x, 0, b.global_position.z - a.global_position.z)
			if absf(b.global_position.y - a.global_position.y) > 1.2:
				continue
			var need: float = a.def.hurt_radius + b.def.hurt_radius
			var dist: float = d.length()
			if dist >= need:
				continue
			var axis: Vector3 = d / dist if dist > 1e-4 else Vector3(1, 0, 0)
			var push: float = minf(need - dist, step_max) * 0.5
			a.move_and_collide(-axis * push)
			b.move_and_collide(axis * push)


func _process_knockouts() -> void:
	for f in fighters:
		if f.st.alive and f.st.health <= 0.0:
			f.st.alive = false
			f.st.ko_tick = tick
			f.st.respawn_at = tick + Tuning.respawn_ticks
			f.st.clear_action()
			f.st.ctrl = WR.Ctrl.NONE
			f.st.guarding = false
			f.st.knock_left = 0
			f.st.knocked_out += 1
			occupancy.forget(f.entity_id)
			f.collision_layer = 0
			var killer: int = -1
			if f.st.last_hit_by >= 0 and tick - f.st.last_hit_tick <= WR.secs_to_ticks(10.0):
				killer = f.st.last_hit_by
				var k: FighterBody = by_entity.get(killer)
				if k != null and k.team != f.team:
					k.st.kos += 1
			ctx.events.append({"type": "ko", "e": f.entity_id, "by": killer, "respawn_at": f.st.respawn_at, "tick": tick})
			for other in fighters:
				# a KO'd victim is released from any grapple
				if other.st.act != null and other.st.act.behavior == "grab" and int(other.st.act_data.get("victim", -1)) == f.entity_id:
					FighterLogic.end_action(other, ctx, "victim_ko")


func _process_respawns() -> void:
	for f in fighters:
		if not f.st.alive and f.present and f.st.respawn_at >= 0 and tick >= f.st.respawn_at and phase != WR.Phase.FINISHED:
			respawn(f)


func respawn(f: FighterBody) -> void:
	var pts: Array = layout.spawn_points(f.team)
	var best: Dictionary = pts[0]
	var best_score: float = -INF
	for p in pts:
		var nearest: float = INF
		for o in fighters:
			if o.team != f.team and o.st.alive and o.present:
				nearest = minf(nearest, (o.global_position - (p["pos"] as Vector3)).length())
		# prefer points far from enemies, then points not occupied by teammates
		var crowd: float = 0.0
		for o2 in fighters:
			if o2 != f and o2.team == f.team and o2.st.alive and (o2.global_position - (p["pos"] as Vector3)).length() < 1.0:
				crowd += 5.0
		var score: float = nearest - crowd
		if score > best_score:
			best_score = score
			best = p
	f.global_position = (best["pos"] as Vector3) + Vector3(0, 0.002, 0)
	f.velocity = Vector3.ZERO
	f.st.yaw = float(best["yaw"])
	f.apply_yaw()
	f.reset_vitals()
	f.st.alive = true
	f.st.respawn_at = -1
	f.st.spawn_protected = true
	f.st.protect_until = tick + Tuning.spawn_protect_max
	f.collision_layer = WR.LAYER_FIGHTERS
	f.set_meta("safe_pos", best["pos"])
	f.history.clear()
	ctx.events.append({"type": "respawn", "e": f.entity_id, "tick": tick})


func _on_match_end(e: Dictionary) -> void:
	phase = WR.Phase.FINISHED
	if result_emitted:
		return  # completion happens once
	result_emitted = true
	result = build_result(e)
	match_finished.emit(result)


func build_result(e: Dictionary) -> Dictionary:
	var players: Array = []
	var bots: Array = []
	for f in fighters:
		var row := {"entity": f.entity_id, "team": f.team, "fighter": f.def.id, "name": f.player_name,
			"account_id": f.account_id, "kos": f.st.kos, "knocked_out": f.st.knocked_out,
			"damage_dealt": int(round(f.st.damage_dealt)),
			"control_seconds": int(f.st.get_meta("zone_ticks", 0)) / WR.TICK_RATE,
			"abandoned": bool(f.get_meta("abandoned", false)), "afk": bool(f.get_meta("afk", false)),
			"bot": f.is_bot}
		if f.is_bot:
			bots.append(row)
		else:
			players.append(row)
	return {"match_id": match_id, "mode": mode, "winner_team": int(e.get("winner", -1)),
		"score": [rules.scores[0], rules.scores[1]], "duration_s": float(rules.match_tick) / WR.TICK_RATE,
		"sudden_death": rules.sudden_death, "ended_reason": String(e.get("reason", "")),
		"players": players, "bots": bots, "seed": seed_value, "build": WR.BUILD_ID}


func forfeit(losing_team: int) -> void:
	var ev: Array[Dictionary] = rules.forfeit(losing_team)
	for e in ev:
		e["tick"] = tick
		if String(e["type"]) == "match_end":
			_on_match_end(e)
	_emit_now(ev)


func _emit_now(ev: Array) -> void:
	if ev.is_empty():
		return
	sim_events.emit(ev)
	if event_log_hook.is_valid():
		event_log_hook.call(ev)


func nav_path(from: Vector3, to: Vector3) -> PackedVector3Array:
	if not nav_map.is_valid():
		return PackedVector3Array([from, to])
	return NavigationServer3D.map_get_path(nav_map, from, to, true)


func snapshot_match() -> Dictionary:
	var s: Dictionary = rules.snapshot()
	s["sim_tick"] = tick
	s["phase"] = phase
	s["countdown_until"] = countdown_until
	return s
