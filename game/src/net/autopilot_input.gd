class_name AutopilotInput
extends RefCounted
## Scripted input source for automated protocol tests (a REAL client process with a real
## identity, driven by a repeatable seeded script — clearly a test harness, never presented
## as a player or used in real matchmaking). Scenarios: idle, zone, fight, spam, guard, dodge.

var scenario: String = "fight"
var rng := RandomNumberGenerator.new()
var nav_map: RID
var nav_region: RID
var _path: PackedVector3Array = PackedVector3Array()
var _path_i: int = 0
var _repath_at: int = 0
var _t: int = 0
var _prev_buttons: int = 0


func setup(p_scenario: String, seed_value: int, _world: Node3D, _layout: ArenaLayout) -> void:
	scenario = p_scenario
	rng.seed = seed_value
	var nm: NavigationMesh = load(ArenaBuilder.NAVMESH_PATH) if ResourceLoader.exists(ArenaBuilder.NAVMESH_PATH) else null
	if nm != null:
		nav_map = NavigationServer3D.map_create()
		NavigationServer3D.map_set_cell_size(nav_map, nm.cell_size)
		NavigationServer3D.map_set_cell_height(nav_map, nm.cell_height)
		NavigationServer3D.map_set_active(nav_map, true)
		nav_region = NavigationServer3D.region_create()
		NavigationServer3D.region_set_map(nav_region, nav_map)
		NavigationServer3D.region_set_navigation_mesh(nav_region, nm)


func cleanup() -> void:
	if nav_region.is_valid():
		NavigationServer3D.free_rid(nav_region)
	if nav_map.is_valid():
		NavigationServer3D.free_rid(nav_map)


func sample(s: ClientSession) -> InputFrame:
	_t += 1
	var f := InputFrame.new()
	if s.pred == null:
		return f
	var me: FighterBody = s.pred
	var buttons: int = 0
	match scenario:
		"idle":
			f.yaw = me.st.yaw
		"spam":
			f.yaw = rng.randf_range(-PI, PI)
			f.move = Vector2(rng.randf_range(-1, 1), rng.randf_range(-1, 1))
			buttons = rng.randi() & WR.BTN_ALL_SIM
		"guard":
			# Walk to the active zone; once an enemy is close, face it and hold a frontal guard
			# while creeping toward it (so strikes actually land on the guard).
			var gz: String = String(s.match_state.get("zone", "B"))
			var gtarget: Vector3 = s.layout.zone_center(gz) if s.layout != null else Vector3.ZERO
			var ge: Dictionary = _nearest_enemy(s, me)
			if not ge.is_empty() and me.global_position.distance_to(ge["pos"]) < 6.0:
				f.yaw = MathX.yaw_from_dir(((ge["pos"] as Vector3) - me.global_position).normalized())
				buttons = WR.BTN_GUARD
				f.move = Vector2(0, 0.25) if me.global_position.distance_to(ge["pos"]) > 1.6 else Vector2.ZERO
			else:
				var gdir: Vector3 = _steer(me.global_position, gtarget)
				if gdir.length() > 0.1:
					f.yaw = MathX.yaw_from_dir(gdir)
					f.move = Vector2(0, 1)
				else:
					f.yaw = me.st.yaw
		_:
			var zone: String = String(s.match_state.get("zone", "B"))
			var target: Vector3 = s.layout.zone_center(zone) if s.layout != null else Vector3.ZERO
			var enemy: Dictionary = _nearest_enemy(s, me)
			if scenario == "fight" and not enemy.is_empty() and me.global_position.distance_to(enemy["pos"]) < 2.2:
				f.yaw = MathX.yaw_from_dir(((enemy["pos"] as Vector3) - me.global_position).normalized())
				var r: float = rng.randf()
				if r < 0.08:
					buttons = WR.BTN_LIGHT
				elif r < 0.10:
					buttons = WR.BTN_HEAVY
				elif r < 0.13:
					buttons = [WR.BTN_Q, WR.BTN_E, WR.BTN_R][rng.randi_range(0, 2)]
				elif r < 0.16:
					buttons = WR.BTN_GUARD
				f.move = Vector2(0, 0.3)
			else:
				var dir: Vector3 = _steer(me.global_position, target)
				if dir.length() > 0.1:
					f.yaw = MathX.yaw_from_dir(dir)
					f.move = Vector2(0, 1)
				else:
					f.yaw = me.st.yaw
				if scenario == "dodge" and rng.randf() < 0.02:
					buttons = WR.BTN_DODGE
	f.taps = buttons & ~_prev_buttons
	f.buttons = buttons
	_prev_buttons = buttons
	return f


func _steer(from: Vector3, to: Vector3) -> Vector3:
	if not nav_map.is_valid():
		var d: Vector3 = to - from
		d.y = 0
		return d.normalized() if d.length() > 2.0 else Vector3.ZERO
	if _t >= _repath_at or _path_i >= _path.size():
		_path = NavigationServer3D.map_get_path(nav_map, from, to, true)
		_path_i = 1
		_repath_at = _t + 30
	while _path_i < _path.size() and Vector2(_path[_path_i].x - from.x, _path[_path_i].z - from.z).length() < 0.6:
		_path_i += 1
	if _path_i >= _path.size():
		var d2: Vector3 = to - from
		d2.y = 0
		return d2.normalized() if d2.length() > 3.0 else Vector3.ZERO
	var d3: Vector3 = _path[_path_i] - from
	d3.y = 0
	return d3.normalized()


func _nearest_enemy(s: ClientSession, me: FighterBody) -> Dictionary:
	var best: Dictionary = {}
	var bd: float = INF
	var rt: float = s.render_tick()
	for e in s.fighter_info.keys():
		if int(s.fighter_info[e]["team"]) == me.team:
			continue
		var st: Dictionary = s.interpolated(int(e), rt)
		if st.is_empty() or (int(st["flags"]) & Protocol.F_ALIVE) == 0:
			continue
		var d: float = me.global_position.distance_to(st["pos"])
		if d < bd:
			bd = d
			best = st
	return best


func _face_nearest_enemy(s: ClientSession, me: FighterBody) -> float:
	var e: Dictionary = _nearest_enemy(s, me)
	if e.is_empty():
		return me.st.yaw
	return MathX.yaw_from_dir(((e["pos"] as Vector3) - me.global_position).normalized())
