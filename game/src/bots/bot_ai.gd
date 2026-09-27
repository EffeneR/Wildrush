class_name BotAI
extends BotBrain
## Server-side bot (spec §10). Produces the same InputFrame a human sends and is bound by the
## same stamina, cooldown, collision and hit rules. Fairness:
##  * perception = own line of sight (≤ 60 m, 220° field of view) or hearing (≤ 12 m), plus
##    teammate reports through the team blackboard delayed by the coordination level;
##  * enemy actions are only known as observed animation (feints look like heavies) and are
##    read with a reaction delay; remembered positions decay — no knowledge through walls;
##  * difficulty changes reaction delay, decision quality and coordination — never damage.

const PROFILES: Dictionary = {
	"easy": {"reaction": 27, "think": 21, "aggression": 0.45, "guard": 0.30, "dodge": 0.20, "skills": 0.40,
		"punish": 0.35, "rotate_early_s": 4.0, "coordination": 0.30, "aim_error": 0.25, "report_delay": 60},
	"normal": {"reaction": 17, "think": 13, "aggression": 0.6, "guard": 0.55, "dodge": 0.45, "skills": 0.65,
		"punish": 0.6, "rotate_early_s": 9.0, "coordination": 0.6, "aim_error": 0.12, "report_delay": 30},
	"hard": {"reaction": 10, "think": 7, "aggression": 0.72, "guard": 0.8, "dodge": 0.7, "skills": 0.85,
		"punish": 0.85, "rotate_early_s": 13.0, "coordination": 0.85, "aim_error": 0.05, "report_delay": 12},
}
const SIGHT_RANGE: float = 60.0
const HEAR_RANGE: float = 12.0
const FOV_HALF: float = deg_to_rad(110.0)
const MEMORY_TICKS: int = 300

var prof: Dictionary = {}
var rng := RandomNumberGenerator.new()
var obs: Dictionary = {}          # enemy entity -> Array of observation samples (ring)
var memory: Dictionary = {}       # enemy entity -> {"pos", "tick"}
var path: PackedVector3Array = PackedVector3Array()
var path_i: int = 0
var path_goal: Vector3 = Vector3.INF
var repath_at: int = 0
var stuck_since: int = -1
var stuck_anchor: Vector3 = Vector3.ZERO
var stuck_count: int = 0
var detour_until: int = -1
var detour_point: Vector3 = Vector3.ZERO
var next_think: int = 0
var intent: Dictionary = {"mode": "objective", "target": -1}
var held: int = 0
var press_queue: Array = []       # [[tick, button]] scheduled presses
var guard_until: int = -1
var last_yaw: float = 0.0
var initialized: bool = false


func _init_profile(sim: MatchSim, f: FighterBody) -> void:
	prof = PROFILES.get(difficulty, PROFILES["normal"])
	rng.seed = sim.seed_value * 977 + f.entity_id * 131
	last_yaw = f.st.yaw
	initialized = true


func think(sim: MatchSim, f: FighterBody) -> InputFrame:
	seq += 1
	if not initialized:
		_init_profile(sim, f)
	var inp := InputFrame.new()
	inp.seq = seq
	inp.yaw = last_yaw
	if not f.st.alive or not f.present:
		held = 0
		return inp
	var tick: int = sim.tick
	_perceive(sim, f, tick)
	if tick >= next_think:
		next_think = tick + int(prof["think"]) + rng.randi_range(0, 3)
		_decide(sim, f, tick)
	var buttons: int = 0
	var move := Vector2.ZERO
	var yaw: float = last_yaw
	var want_pos: Variant = null
	var face_pos: Variant = null
	var mode: String = String(intent["mode"])
	var tgt: Dictionary = _observed(int(intent.get("target", -1)), tick, int(prof["reaction"]))
	match mode:
		"fight":
			if tgt.is_empty():
				intent = {"mode": "objective", "target": -1}
			else:
				var r: Array = _fight(sim, f, tgt, tick)
				want_pos = r[0]
				face_pos = r[1]
				buttons |= int(r[2])
		"retreat":
			want_pos = sim.layout.spawn_points(f.team)[2]["pos"]
			if not tgt.is_empty() and f.global_position.distance_to(tgt["pos"]) < 3.0:
				face_pos = tgt["pos"]
				if rng.randf() < float(prof["guard"]) * 0.3:
					buttons |= WR.BTN_GUARD
		"rotate", "objective":
			want_pos = intent.get("pos", _zone_goal(sim, f))
		"support":
			want_pos = intent.get("pos", _zone_goal(sim, f))
	# movement toward want_pos along the navmesh
	if want_pos != null:
		var arrive: float = 0.25 if mode == "fight" else 1.2
		var dir: Vector3 = _steer(sim, f, want_pos as Vector3, tick, arrive)
		if dir.length() > 0.05:
			var move_yaw: float = MathX.yaw_from_dir(dir)
			if face_pos == null:
				yaw = move_yaw
				move = Vector2(0, 1)
			else:
				var fy: Vector3 = (face_pos as Vector3) - f.global_position
				fy.y = 0.0
				yaw = MathX.yaw_from_dir(fy.normalized()) if fy.length() > 0.05 else last_yaw
				var local: Vector3 = MathX.world_dir_to_local(yaw, dir)
				move = Vector2(local.x, local.z).limit_length(1.0)
		elif face_pos != null:
			var fy2: Vector3 = (face_pos as Vector3) - f.global_position
			fy2.y = 0.0
			if fy2.length() > 0.05:
				yaw = MathX.yaw_from_dir(fy2.normalized())
	# scheduled presses (skills / attacks queued by decisions with human-like latency)
	var still: Array = []
	for pq in press_queue:
		if int(pq[0]) <= tick:
			buttons |= int(pq[1])
		else:
			still.append(pq)
	press_queue = still
	if tick < guard_until:
		buttons |= WR.BTN_GUARD
	inp.yaw = wrapf(yaw, -PI, PI)
	inp.move = move
	inp.taps = buttons & ~held & ~WR.BTN_GUARD
	inp.buttons = buttons
	held = buttons
	last_yaw = inp.yaw
	return inp


# ------------------------------------------------------------------------------------------
# perception (fair)
# ------------------------------------------------------------------------------------------
func _perceive(sim: MatchSim, f: FighterBody, tick: int) -> void:
	if tick % 3 != f.entity_id % 3:
		return
	var eye: Vector3 = f.head_position()
	var fwd: Vector3 = f.forward()
	for e: FighterBody in sim.fighters:
		if e.team == f.team or not e.present or not e.st.alive:
			continue
		var to: Vector3 = e.global_position - f.global_position
		var d: float = to.length()
		var seen: bool = d <= HEAR_RANGE
		if not seen and d <= SIGHT_RANGE:
			var th := Vector3(to.x, 0, to.z)
			if th.length() < 0.01 or fwd.angle_to(th.normalized()) <= FOV_HALF:
				seen = not sim.ctx.ray_blocked(eye, e.chest_position()) or not sim.ctx.ray_blocked(eye, e.head_position())
		if seen:
			_record(e, tick)
	# team reports (delayed by coordination): what teammates saw is shared after a delay
	var bb: Dictionary = _blackboard(sim, f.team)
	for eid in (bb.get("seen", {}) as Dictionary).keys():
		var rep: Dictionary = bb["seen"][eid]
		if tick - int(rep["tick"]) >= int(prof["report_delay"]) and not memory.has(eid) or \
				(memory.has(eid) and int(rep["tick"]) > int(memory[eid]["tick"]) + int(prof["report_delay"])):
			if tick - int(rep["tick"]) < MEMORY_TICKS:
				memory[eid] = {"pos": rep["pos"], "tick": int(rep["tick"]), "reported": true}


func _record(e: FighterBody, tick: int) -> void:
	var disp_act: String = ""
	var act_tick: int = 0
	var exposed: bool = false
	var phase: String = ""
	if e.st.act != null:
		var b: ActionBehavior = Behaviors.of(e.st.act)
		disp_act = b.display_id(e)            # feints are observed as the heavy wind-up
		act_tick = e.st.act_tick
		phase = e.st.act_phase
		exposed = b.exposed(e)
	var sample := {"tick": tick, "pos": e.global_position, "vel": e.velocity, "yaw": e.st.yaw, "act": disp_act,
		"at": act_tick, "phase": phase, "guard": e.st.guarding, "ctrl": e.st.ctrl, "hp": e.st.health / e.def.health,
		"exposed": exposed, "fighter": e.def.id, "e": e.entity_id, "grounded": e.st.grounded}
	if not obs.has(e.entity_id):
		obs[e.entity_id] = []
	var arr: Array = obs[e.entity_id]
	arr.append(sample)
	while arr.size() > 40:
		arr.pop_front()
	memory[e.entity_id] = {"pos": e.global_position, "tick": tick}


func _observed(eid: int, tick: int, delay: int) -> Dictionary:
	## Most recent observation at least `delay` ticks old (reaction time).
	if eid < 0 or not obs.has(eid):
		return {}
	var arr: Array = obs[eid]
	for i in range(arr.size() - 1, -1, -1):
		var s: Dictionary = arr[i]
		if tick - int(s["tick"]) >= delay:
			if tick - int(s["tick"]) > delay + 40:
				return {}
			return s
	return {}


func _blackboard(sim: MatchSim, team: int) -> Dictionary:
	var key: String = "bot_bb_%d" % team
	if not sim.has_meta(key):
		sim.set_meta(key, {"seen": {}, "rotators": {}, "tick": 0})
	return sim.get_meta(key)


# ------------------------------------------------------------------------------------------
# decisions
# ------------------------------------------------------------------------------------------
func _decide(sim: MatchSim, f: FighterBody, tick: int) -> void:
	var bb: Dictionary = _blackboard(sim, f.team)
	# share my current sightings with the team (read by others after a delay)
	for eid in obs.keys():
		var last: Dictionary = (obs[eid] as Array)[(obs[eid] as Array).size() - 1]
		if tick - int(last["tick"]) < 10:
			bb["seen"][eid] = {"pos": last["pos"], "tick": int(last["tick"])}
	var hp_frac: float = f.st.health / f.def.health
	# nearest threat among fresh observations
	var best: int = -1
	var best_d: float = INF
	for eid in obs.keys():
		var o: Dictionary = _observed(int(eid), tick, int(prof["reaction"]))
		if o.is_empty():
			continue
		var d: float = f.global_position.distance_to(o["pos"])
		if d < best_d:
			best_d = d
			best = int(eid)
	var zone_pos: Vector3 = _zone_goal(sim, f)
	var in_zone: bool = Vector2(f.global_position.x - zone_pos.x, f.global_position.z - zone_pos.z).length() < 8.0
	# retreat when low and threatened (health regenerates after 6 s out of combat)
	if hp_frac < 0.28 and best >= 0 and best_d < 10.0 and rng.randf() < 0.6 + 0.3 * float(prof["coordination"]):
		intent = {"mode": "retreat", "target": best}
		return
	if intent["mode"] == "retreat" and (hp_frac < 0.7 and tick - f.st.last_damage_tick < 360):
		return
	# engage: enemies near the objective or near me
	if best >= 0:
		var bo: Dictionary = _observed(best, tick, int(prof["reaction"]))
		var enemy_near_zone: bool = Vector2((bo["pos"] as Vector3).x - zone_pos.x, (bo["pos"] as Vector3).z - zone_pos.z).length() < 12.0
		var me_to_zone: float = Vector2(f.global_position.x - zone_pos.x, f.global_position.z - zone_pos.z).length()
		var close_threat: bool = best_d < 4.0 + 3.0 * float(prof["aggression"])
		if close_threat or (enemy_near_zone and me_to_zone < 25.0) or (in_zone and best_d < 14.0):
			intent = {"mode": "fight", "target": best}
			return
	# rotation planning with a team blackboard: some bots pre-rotate when the next zone is known
	var rules: TurfShiftRules = sim.rules
	var early: int = WR.secs_to_ticks(float(prof["rotate_early_s"]))
	if rules.next_revealed and rules.next_zone != "" and rules.ticks_to_rotation() <= early:
		var rot: Dictionary = bb["rotators"]
		var want: int = 1 + int(float(prof["coordination"]) * 2.0)
		if rot.get("zone", "") != rules.next_zone:
			rot.clear()
			rot["zone"] = rules.next_zone
			rot["members"] = {}
		var members: Dictionary = rot["members"]
		if members.has(f.entity_id) or members.size() < want:
			members[f.entity_id] = true
			intent = {"mode": "rotate", "pos": _spread(sim.layout.zone_center(rules.next_zone), f)}
			return
	# support an ally in trouble inside the zone (remembered enemy near the objective)
	for eid in memory.keys():
		var m: Dictionary = memory[eid]
		if tick - int(m["tick"]) < 120 and (m["pos"] as Vector3).distance_to(zone_pos) < 10.0:
			intent = {"mode": "support", "pos": m["pos"]}
			return
	intent = {"mode": "objective", "pos": _spread(zone_pos, f)}


func _zone_goal(sim: MatchSim, f: FighterBody) -> Vector3:
	return _spread(sim.layout.zone_center(sim.rules.active_zone if sim.rules.active_zone != "" else "B"), f)


func _spread(c: Vector3, f: FighterBody) -> Vector3:
	## Each bot holds a slightly different spot so the team does not stack on one point.
	var ang: float = float(f.entity_id) * 1.3
	return c + Vector3(cos(ang), 0, sin(ang)) * (3.0 + float(f.entity_id % 3))


# ------------------------------------------------------------------------------------------
# fighting
# ------------------------------------------------------------------------------------------
func _fight(sim: MatchSim, f: FighterBody, o: Dictionary, tick: int) -> Array:
	## Returns [want_pos, face_pos, buttons].
	var buttons: int = 0
	var epos: Vector3 = o["pos"]
	var d: float = Vector2(epos.x - f.global_position.x, epos.z - f.global_position.z).length()
	var ideal: float = 1.35 if f.def.id != "hops" else 1.5
	var to_e: Vector3 = (epos - f.global_position)
	to_e.y = 0.0
	var dir_e: Vector3 = to_e.normalized() if to_e.length() > 0.01 else f.forward()
	var aim_err: float = rng.randf_range(-float(prof["aim_error"]), float(prof["aim_error"]))
	var face: Vector3 = f.global_position + dir_e.rotated(Vector3.UP, aim_err) * 3.0
	var want: Vector3 = epos - dir_e * ideal
	if d > ideal + 0.2:
		want = epos - dir_e * (ideal - 0.15)   # close the distance into striking range
	var busy: bool = f.st.act != null or f.st.ctrl != WR.Ctrl.NONE
	var enemy_act: String = String(o["act"])
	var enemy_facing_me: bool = MathX.yaw_forward(float(o["yaw"])).dot(-dir_e) > 0.5
	var incoming: bool = enemy_act != "" and enemy_facing_me and d < 3.5 and _is_startup(o)
	# --- defense: guard or dodge incoming strikes (reaction-delayed observation)
	if incoming and not busy:
		var is_heavyish: bool = enemy_act.ends_with("_heavy") or enemy_act.contains("rush") or enemy_act.contains("pounce") \
			or enemy_act.contains("dropkick") or enemy_act.contains("sidewinder")
		if f.def.id == "scrap" and _skill_ready(f, "q", tick) and rng.randf() < float(prof["skills"]) * 0.8:
			_queue(tick, WR.BTN_Q)                                  # Catch & Turn the incoming strike
		elif is_heavyish and f.st.stamina >= Tuning.dodge_stamina and rng.randf() < float(prof["dodge"]):
			_queue(tick, WR.BTN_DODGE)
		elif f.def.id == "nyx" and _skill_ready(f, "r", tick) and rng.randf() < float(prof["skills"]) * 0.5:
			_queue(tick, WR.BTN_R)
			_queue(tick + 14, WR.BTN_LIGHT)                         # counter-swipe after the evade
		elif rng.randf() < float(prof["guard"]):
			guard_until = tick + 24
			return [want, face, WR.BTN_GUARD]
	if tick < guard_until:
		return [f.global_position, face, WR.BTN_GUARD]
	if busy:
		return [want, face, buttons]
	# --- punish exposed recovery
	if bool(o["exposed"]) and _in_recovery(o) and d < 2.2 and rng.randf() < float(prof["punish"]):
		if f.st.stamina >= 15.0 and rng.randf() < 0.4:
			_queue(tick, WR.BTN_HEAVY)
		else:
			_queue(tick, WR.BTN_LIGHT)
		return [want, face, buttons]
	# --- species skills
	if rng.randf() < float(prof["skills"]) * 0.35:
		var used: bool = _use_skill(sim, f, o, d, tick)
		if used:
			return [want, face, buttons]
	# --- basic offense with spacing
	if d <= 1.9:
		var r: float = rng.randf()
		if bool(o["guard"]) and enemy_facing_me:
			if f.st.stamina >= 15.0 and r < 0.25 * float(prof["aggression"]):
				_queue(tick, WR.BTN_HEAVY)                          # guard pressure
			elif r < 0.5:
				want = epos + dir_e.cross(Vector3.UP) * 1.5          # circle to the flank
		elif r < float(prof["aggression"]) * 0.55:
			var side: Vector2 = [Vector2.ZERO, Vector2(-1, 0), Vector2(1, 0)][rng.randi_range(0, 2)]
			press_queue.append([tick, WR.BTN_LIGHT])
			if side != Vector2.ZERO:
				want = f.global_position + MathX.yaw_right(MathX.yaw_from_dir(dir_e)) * side.x * 0.3
	return [want, face, buttons]


func _is_startup(o: Dictionary) -> bool:
	var act: String = String(o["act"])
	if act == "":
		return false
	var fd: FighterDef = Tuning.fighter(String(o["fighter"]))
	var a: ActionDef = fd.action(act) if fd != null else null
	if a == null:
		return false
	var first: int = a.first_active_tick()
	return int(o["at"]) < first and int(o["at"]) >= 0


func _in_recovery(o: Dictionary) -> bool:
	var act: String = String(o["act"])
	if act == "":
		return false
	var fd: FighterDef = Tuning.fighter(String(o["fighter"]))
	var a: ActionDef = fd.action(act) if fd != null else null
	if a == null:
		return String(o["phase"]) in ["land", "miss", "wall", "crash", "whiff", "recover"]
	var last_active: int = 0
	for h in a.hits:
		if h.rel == "":
			last_active = maxi(last_active, h.t1)
	return int(o["at"]) >= last_active or String(o["phase"]) in ["land", "miss", "wall", "crash", "whiff", "recover"]


func _skill_ready(f: FighterBody, slot: String, tick: int) -> bool:
	var s: ActionDef = f.def.skill(slot)
	return s != null and tick >= int(f.st.cd_ready.get(slot, 0)) and f.st.stamina >= s.stamina


func _queue(tick: int, btn: int) -> void:
	press_queue.append([tick, btn])


func _enemies_near(sim: MatchSim, f: FighterBody, radius: float, tick: int) -> int:
	var n: int = 0
	for eid in obs.keys():
		var o: Dictionary = _observed(int(eid), tick, int(prof["reaction"]))
		if not o.is_empty() and f.global_position.distance_to(o["pos"]) <= radius:
			n += 1
	return n


func _use_skill(sim: MatchSim, f: FighterBody, o: Dictionary, d: float, tick: int) -> bool:
	var epos: Vector3 = o["pos"]
	var clear: bool = not sim.ctx.ray_blocked(f.chest_position(), epos + Vector3(0, 1.0, 0))
	match f.def.id:
		"nyx":
			if d > 3.8 and d < 6.4 and clear and _skill_ready(f, "q", tick):
				_queue(tick, WR.BTN_Q)
				return true
			if d < 1.6 and _skill_ready(f, "e", tick):
				_queue(tick, WR.BTN_E)
				return true
		"bruno":
			if d > 3.0 and d < 7.0 and clear and _skill_ready(f, "q", tick):
				_queue(tick, WR.BTN_Q)
				return true
			if d < 4.5 and (bool(o["exposed"]) or _enemies_near(sim, f, 4.5, tick) >= 2) and _skill_ready(f, "e", tick):
				_queue(tick, WR.BTN_E)
				return true
			if _enemies_near(sim, f, 4.0, tick) >= 2 and f.st.health / f.def.health < 0.6 and _skill_ready(f, "r", tick):
				_queue(tick, WR.BTN_R)
				_queue(tick + 100, WR.BTN_R)
				return true
		"vex":
			if d < 2.2 and bool(o["guard"]) and _skill_ready(f, "q", tick):
				_queue(tick, WR.BTN_Q)                               # bait the guard with a feint
				_queue(tick + 32, WR.BTN_LIGHT)
				return true
			if d > 2.8 and d < 5.2 and clear and _skill_ready(f, "e", tick):
				_queue(tick, WR.BTN_E)
				return true
			if (_enemies_near(sim, f, 2.0, tick) >= 2 or bool(o["exposed"])) and d < 1.9 and _skill_ready(f, "r", tick):
				_queue(tick, WR.BTN_R)
				return true
		"hops":
			if d > 2.4 and d < 5.0 and clear and _skill_ready(f, "r", tick):
				_queue(tick, WR.BTN_R)
				return true
			if d > 1.1 and d < 1.8 and _skill_ready(f, "e", tick):
				_queue(tick, WR.BTN_E)
				return true
		"scrap":
			if d < 1.3 and _skill_ready(f, "r", tick) and rng.randf() < 0.5:
				_queue(tick, WR.BTN_R)
				return true
			if d < 1.5 and not bool(o["guard"]) and _skill_ready(f, "e", tick):
				_queue(tick, WR.BTN_E)
				return true
	return false


# ------------------------------------------------------------------------------------------
# navigation with stuck recovery
# ------------------------------------------------------------------------------------------
func _steer(sim: MatchSim, f: FighterBody, goal: Vector3, tick: int, arrive: float = 1.2) -> Vector3:
	var pos: Vector3 = f.global_position
	var flat: Vector3 = Vector3(goal.x - pos.x, 0, goal.z - pos.z)
	if flat.length() < arrive:
		return Vector3.ZERO
	# close and in plain view: go straight (no path corner-cutting artefacts)
	if flat.length() < 4.0 and not sim.ctx.ray_blocked(pos + Vector3(0, 0.6, 0), goal + Vector3(0, 0.6, 0), WR.LAYER_WORLD | WR.LAYER_BLOCKER):
		return flat.normalized()
	# Hops uses Bound to cover long open distances toward the objective (ground-only activation)
	if f.def.id == "hops" and String(intent["mode"]) in ["objective", "rotate"] and _skill_ready(f, "q", tick) \
			and pos.distance_to(goal) > 12.0 and f.st.act == null and rng.randf() < 0.02 * float(prof["skills"]):
		_queue(tick, WR.BTN_Q)
	if tick < detour_until:
		var dd: Vector3 = detour_point - pos
		dd.y = 0.0
		if dd.length() > 0.6:
			return dd.normalized()
	if not sim.nav_ready():
		var raw: Vector3 = goal - pos
		raw.y = 0.0
		return raw.normalized()
	if tick >= repath_at or path_goal.distance_to(goal) > 2.0 or path_i >= path.size():
		path = sim.nav_path(pos, goal)
		path_i = 1
		path_goal = goal
		repath_at = tick + 45 + rng.randi_range(0, 15)
	while path_i < path.size() and Vector2(path[path_i].x - pos.x, path[path_i].z - pos.z).length() < 0.7:
		path_i += 1
	var target: Vector3 = goal if path_i >= path.size() else path[path_i]
	var d: Vector3 = target - pos
	d.y = 0.0
	# stuck detection → jump / sidestep detour / repath
	if stuck_since < 0 or pos.distance_to(stuck_anchor) > 1.0:
		stuck_since = tick
		stuck_anchor = pos
		stuck_count = maxi(0, stuck_count - 1)
	elif tick - stuck_since > 90 and f.st.act == null:
		stuck_count += 1
		stuck_since = tick
		repath_at = 0
		var side: Vector3 = d.normalized().cross(Vector3.UP) * (1.0 if rng.randf() < 0.5 else -1.0)
		detour_point = pos + side * 2.5 - d.normalized() * 1.0
		var snapped: Vector3 = NavigationServer3D.map_get_closest_point(sim.nav_map, detour_point)
		detour_point = snapped
		detour_until = tick + 40
		_queue(tick, WR.BTN_JUMP)
		if stuck_count > 3:
			intent = {"mode": "objective", "pos": _spread(sim.layout.zone_center(sim.rules.active_zone), f)}
			stuck_count = 0
	return d.normalized() if d.length() > 0.01 else Vector3.ZERO
