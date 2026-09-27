class_name WRTest
extends Node3D
## Base class for WILDRUSH GDScript tests. Methods named test_* are run by tests/test_runner.gd.
## Simulation ticks are executed inside physics frames (fixed 1/60 s delta) — run the suite
## with `--headless --fixed-fps 60` so it proceeds faster than real time.

var failures: Array[String] = []
var checks: int = 0


func before_each() -> void:
	pass


func after_each() -> void:
	for c in get_children():
		c.queue_free()
	await get_tree().physics_frame


# ------------------------------------------------------------------------------------------
# assertions
# ------------------------------------------------------------------------------------------
func fail(msg: String) -> void:
	failures.append(msg)


func assert_true(c: bool, msg: String = "") -> void:
	checks += 1
	if not c:
		fail("expected true: " + msg)


func assert_false(c: bool, msg: String = "") -> void:
	checks += 1
	if c:
		fail("expected false: " + msg)


func assert_eq(a: Variant, b: Variant, msg: String = "") -> void:
	checks += 1
	if not (typeof(a) == typeof(b) and a == b) and not (_is_num(a) and _is_num(b) and float(a) == float(b)):
		fail("expected %s == %s: %s" % [str(a), str(b), msg])


func assert_ne(a: Variant, b: Variant, msg: String = "") -> void:
	checks += 1
	if a == b:
		fail("expected %s != %s: %s" % [str(a), str(b), msg])


func assert_near(a: float, b: float, eps: float, msg: String = "") -> void:
	checks += 1
	if absf(a - b) > eps:
		fail("expected %.4f ≈ %.4f (±%.4f): %s" % [a, b, eps, msg])


func assert_gt(a: float, b: float, msg: String = "") -> void:
	checks += 1
	if not (a > b):
		fail("expected %.4f > %.4f: %s" % [a, b, msg])


func assert_lt(a: float, b: float, msg: String = "") -> void:
	checks += 1
	if not (a < b):
		fail("expected %.4f < %.4f: %s" % [a, b, msg])


func _is_num(v: Variant) -> bool:
	return typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT


# ------------------------------------------------------------------------------------------
# simulation helpers
# ------------------------------------------------------------------------------------------
static func flat_layout() -> Dictionary:
	## Small deterministic test arena: open floor, a wall, a perch ledge, zones, spawns,
	## and a slab 4 m above zone A to test that fighters above cannot capture.
	return {
		"name": "TestFlat", "footprint": {"x": [-60, 60], "z": [-60, 60]},
		"zones": [
			{"id": "A", "name": "A", "center": [-35.0, 0.0, 0.0], "floor_y": 0.0, "radius": 9.0},
			{"id": "B", "name": "B", "center": [0.0, 0.0, 0.0], "floor_y": 0.0, "radius": 9.0},
			{"id": "C", "name": "C", "center": [35.0, 0.0, 0.0], "floor_y": 0.0, "radius": 9.0},
		],
		"spawns": [
			{"team": 0, "points": [[-6, 0, -40, PI], [-3, 0, -40, PI], [0, 0, -40, PI], [3, 0, -40, PI], [6, 0, -40, PI]],
			 "protect": {"min": [-10, -1, -48], "max": [10, 8, -36]}, "barriers": [{"min": [-10, -1, -36.4], "max": [10, 8, -36]}],
			 "exits": [[0, 0, -35]]},
			{"team": 1, "points": [[-6, 0, 40, 0], [-3, 0, 40, 0], [0, 0, 40, 0], [3, 0, 40, 0], [6, 0, 40, 0]],
			 "protect": {"min": [-10, -1, 36], "max": [10, 8, 48]}, "barriers": [{"min": [-10, -1, 36], "max": [10, 8, 36.4]}],
			 "exits": [[0, 0, 35]]},
		],
		"floors": [
			{"id": "ground", "min": [-60, -1, -60], "max": [60, 0, 60], "surface": "stone"},
			{"id": "ledge", "min": [20, 0, 10], "max": [30, 1.5, 20], "surface": "stone"},
			{"id": "slab_above_a", "min": [-40, 3.5, -3], "max": [-30, 4.0, 3], "surface": "stone"},
		],
		"ramps": [],
		"solids": [
			{"id": "wall_n", "min": [-30, 0, -26], "max": [30, 4, -25], "kind": "building"},
			{"id": "wall_test", "min": [-5, 0, 12], "max": [5, 4, 13], "kind": "building"},
		],
		"blockers": [],
		"water": [],
		"perch_ledges": [{"a": [20, 1.5, 10], "b": [20, 1.5, 20], "normal": [-1, 0, 0]}],
		"decor": [],
		"nav": {"cell_size": 0.25, "agent_radius": 0.45, "agent_height": 1.8, "agent_max_climb": 0.36, "agent_max_slope": 46.0},
	}


func make_sim(layout_dict: Dictionary = {}, mode: String = WR.MODE_OFFLINE, build_nav: bool = false) -> MatchSim:
	var sim := MatchSim.new()
	sim.name = "Sim"
	add_child(sim)
	var lay: ArenaLayout = ArenaLayout.from_dict(layout_dict if not layout_dict.is_empty() else flat_layout())
	sim.setup(lay, mode, 1234, build_nav)
	await get_tree().physics_frame
	await get_tree().physics_frame
	return sim


func spawn_pair(sim: MatchSim, a_id: String, b_id: String, gap: float = 1.3) -> Array:
	## Fighter A (team 0) at origin facing +Z (south, toward B); B (team 1) `gap` m south facing A.
	var a: FighterBody = sim.add_fighter(a_id, 0, 0, "A")
	var b: FighterBody = sim.add_fighter(b_id, 1, 0, "B")
	place(a, Vector3(0, 0.002, 0), PI)
	place(b, Vector3(0, 0.002, gap), 0.0)
	return [a, b]


func place(f: FighterBody, pos: Vector3, yaw: float) -> void:
	f.global_position = pos
	f.velocity = Vector3.ZERO
	f.st.yaw = yaw
	f.apply_yaw()
	f.set_meta("safe_pos", pos)
	f.st.spawn_protected = false


func frame(yaw: float, buttons: int = 0, move: Vector2 = Vector2.ZERO) -> InputFrame:
	var i := InputFrame.new()
	i.yaw = yaw
	i.buttons = buttons
	i.move = move
	return i


func run(sim: MatchSim, n: int, input_fn: Callable = Callable()) -> Array[Dictionary]:
	## Runs n authoritative ticks; input_fn(tick_index) -> Dictionary{entity_id: InputFrame}.
	var all: Array[Dictionary] = []
	for i in range(n):
		await get_tree().physics_frame
		if input_fn.is_valid():
			var d: Dictionary = input_fn.call(i)
			for eid in d.keys():
				sim.set_input(int(eid), d[eid])
		all.append_array(sim.step_tick())
	return all


func hold(sim: MatchSim, entries: Dictionary, n: int) -> Array[Dictionary]:
	## Holds the same inputs for n ticks.
	return await run(sim, n, func(_i: int) -> Dictionary:
		var d: Dictionary = {}
		for k in entries.keys():
			d[k] = (entries[k] as InputFrame).copy()
		return d)


func press(sim: MatchSim, eid: int, yaw: float, btn: int, move: Vector2 = Vector2.ZERO, others: Dictionary = {}) -> Array[Dictionary]:
	## One tick with `btn` pressed, then one tick released.
	var ev: Array[Dictionary] = []
	var d1: Dictionary = others.duplicate()
	d1[eid] = frame(yaw, btn, move)
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return d1))
	var d2: Dictionary = others.duplicate()
	d2[eid] = frame(yaw, 0, move)
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return d2))
	return ev


static func count(events: Array, type: String, extra: Dictionary = {}) -> int:
	var n: int = 0
	for e in events:
		if String(e.get("type", "")) != type:
			continue
		var ok: bool = true
		for k in extra.keys():
			if e.get(k) != extra[k]:
				ok = false
		if ok:
			n += 1
	return n
