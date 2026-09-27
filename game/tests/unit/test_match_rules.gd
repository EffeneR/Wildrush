extends WRTest
## Turf Shift rules (spec §4, D-005, D-006) — pure logic, no physics.

const T: int = 60


func _rules() -> TurfShiftRules:
	var r := TurfShiftRules.new()
	r.configure(Tuning.rules)
	r.start_live()
	return r


func _tick(r: TurfShiftRules, p0: int, p1: int, n: int = 1) -> Array[Dictionary]:
	var ev: Array[Dictionary] = []
	for i in range(n):
		r.advance_clock()
		ev.append_array(r.evaluate([p0, p1]))
	return ev


func test_initial_state_and_config() -> void:
	var r := _rules()
	assert_eq(r.active_zone, "B", "first active zone is B")
	assert_eq(r.regulation_ticks, 480 * T)
	assert_eq(r.score_limit, 250)
	assert_eq(r.rotation_ticks, 60 * T)
	assert_eq(r.reveal_before_ticks, 15 * T)
	assert_eq(r.order, ["B", "A", "C"] as Array[String])
	assert_false(r.next_revealed, "next zone hidden at start")


func test_rotation_order_and_timing() -> void:
	var r := _rules()
	var seen: Array[String] = [r.active_zone]
	var rot_ticks: Array[int] = []
	for i in range(420 * T):
		r.advance_clock()
		for e in r.evaluate([0, 0]):
			if e["type"] == "zone_rotated":
				seen.append(String(e["zone"]))
				rot_ticks.append(r.match_tick)
	assert_eq(seen, ["B", "A", "C", "B", "A", "C", "B", "A"] as Array[String], "rotation B→A→C→B…")
	for k in range(rot_ticks.size()):
		assert_eq(rot_ticks[k], (k + 1) * 60 * T, "rotation exactly every 60 s")


func test_reveal_15s_before_and_countdown_visible() -> void:
	var r := _rules()
	var reveal_tick: int = -1
	var reveal_zone: String = ""
	for i in range(60 * T):
		r.advance_clock()
		assert_true(r.ticks_to_rotation() >= 0, "countdown always available")
		for e in r.evaluate([0, 0]):
			if e["type"] == "zone_revealed" and reveal_tick < 0:
				reveal_tick = r.match_tick
				reveal_zone = String(e["zone"])
		if r.match_tick == 44 * T:
			assert_false(r.next_revealed, "not revealed before 45 s")
	assert_eq(reveal_tick, 45 * T, "revealed exactly 15 s before rotation")
	assert_eq(reveal_zone, "A", "upcoming after B is A")


func test_final_period_has_no_misleading_reveal() -> void:
	var r := _rules()
	var reveals_after_420: int = 0
	for i in range(479 * T):
		r.advance_clock()
		for e in r.evaluate([0, 0]):
			if e["type"] == "zone_revealed" and r.match_tick > 420 * T:
				reveals_after_420 += 1
	assert_eq(reveals_after_420, 0, "no next-zone reveal in the final period (match ends at rotation time)")
	assert_true(r.is_final_period())
	assert_eq(r.ticks_to_rotation(), T, "countdown shows time to regulation end")


func test_scoring_one_point_per_second_sole_control() -> void:
	var r := _rules()
	_tick(r, 1, 0, 59)
	assert_eq(r.scores[0], 0, "no point before a full second")
	_tick(r, 1, 0, 1)
	assert_eq(r.scores[0], 1, "1 point after 60 ticks of sole control")
	_tick(r, 1, 0, 600)
	assert_eq(r.scores[0], 11, "1 point per second")


func test_more_teammates_do_not_multiply() -> void:
	var a := _rules()
	var b := _rules()
	_tick(a, 1, 0, 600)
	_tick(b, 5, 0, 600)
	assert_eq(a.scores[0], b.scores[0], "5 occupants score like 1")
	assert_eq(b.scores[0], 10)


func test_contested_pauses_and_neutral_resets() -> void:
	var r := _rules()
	_tick(r, 1, 0, 30)
	var ev: Array[Dictionary] = _tick(r, 2, 1, 120)
	assert_eq(r.scores[0] + r.scores[1], 0, "contested zone never scores")
	assert_eq(r.zone_state, WR.ZoneState.CONTESTED)
	assert_true(count(ev, "zone_state", {"state": WR.ZoneState.CONTESTED}) >= 1)
	_tick(r, 1, 0, 59)
	assert_eq(r.scores[0], 0, "partial second before contest was discarded (no hidden progress)")
	_tick(r, 0, 0, 10)
	assert_eq(r.zone_state, WR.ZoneState.NEUTRAL, "empty active zone is neutral")
	_tick(r, 0, 1, 60)
	assert_eq(r.scores[1], 1, "sole occupancy by team 1 scores for team 1")
	_tick(r, 0, 0, 600)
	assert_eq(r.scores[1], 1, "no unattended persistent ownership")


func test_eliminations_do_not_score() -> void:
	var r := _rules()
	_tick(r, 0, 0, 300)
	assert_eq(r.scores, [0, 0] as Array[int], "no points without occupancy regardless of KOs")


func test_first_to_250_wins_immediately_once() -> void:
	var r := _rules()
	var ends: int = 0
	var ev: Array[Dictionary] = []
	for i in range(260 * T):
		r.advance_clock()
		var e2: Array[Dictionary] = r.evaluate([1, 0])
		ev.append_array(e2)
		if r.finished:
			break
	ends = count(ev, "match_end")
	assert_eq(ends, 1, "match_end emitted once")
	assert_eq(r.scores[0], 250)
	assert_eq(r.winner, 0)
	assert_eq(r.end_reason, "score_limit")
	# further ticks do nothing
	var more: Array[Dictionary] = _tick(r, 1, 0, 200)
	assert_eq(more.size(), 0, "no events after completion")
	assert_eq(r.scores[0], 250, "no score after completion")
	assert_eq(count(r.forfeit(1), "match_end"), 0, "forfeit after completion is ignored")


func test_regulation_end_higher_score_wins() -> void:
	var r := _rules()
	_tick(r, 0, 1, 20 * T)
	_tick(r, 0, 0, 460 * T - 1)
	assert_false(r.finished, "still running just before 8:00")
	var ev: Array[Dictionary] = _tick(r, 0, 0, 1)
	assert_true(r.finished, "ends at 8:00")
	assert_eq(r.winner, 1)
	assert_eq(r.end_reason, "time")
	assert_eq(count(ev, "match_end"), 1)


func test_tie_goes_to_sudden_death_with_frozen_rotation() -> void:
	var r := _rules()
	_tick(r, 0, 0, 480 * T)
	assert_false(r.finished)
	assert_true(r.sudden_death, "tie → sudden death")
	var zone: String = r.active_zone
	assert_eq(zone, "A", "the zone active at regulation end (period 7 = A) continues")
	# contested and neutral do not end it; rotation frozen
	_tick(r, 1, 1, 120 * T)
	assert_eq(r.active_zone, zone, "rotation frozen in sudden death")
	assert_false(r.finished)
	_tick(r, 0, 1, 59)
	assert_false(r.finished)
	var ev: Array[Dictionary] = _tick(r, 0, 1, 1)
	assert_true(r.finished, "first uncontested scoring tick wins")
	assert_eq(r.winner, 1)
	assert_eq(r.end_reason, "sudden_death")
	assert_eq(count(ev, "match_end"), 1)


func test_point_at_exact_regulation_end_counts_before_time_check() -> void:
	var r := _rules()
	_tick(r, 0, 0, 480 * T - 60)
	_tick(r, 1, 0, 60)   # 60th tick of control happens on the 480 s tick
	assert_true(r.finished)
	assert_eq(r.scores[0], 1, "scoring (step 10) precedes regulation check (step 11)")
	assert_eq(r.winner, 0)


func test_rotation_resets_control_timer() -> void:
	var r := _rules()
	_tick(r, 0, 0, 60 * T - 30)
	_tick(r, 1, 0, 30)   # control across the rotation boundary
	var s_before: int = r.scores[0]
	_tick(r, 1, 0, 45)
	assert_eq(r.active_zone, "A")
	assert_eq(r.scores[0], s_before, "timer restarted on the new zone: 45 ticks < 1 s")
	_tick(r, 1, 0, 15)
	assert_eq(r.scores[0], s_before + 1)


func test_score_warnings_emitted_once() -> void:
	var r := _rules()
	var ev: Array[Dictionary] = []
	for i in range(246 * T):
		r.advance_clock()
		ev.append_array(r.evaluate([1, 0]))
	assert_eq(count(ev, "score_warning", {"team": 0}), 3, "warnings at 200, 230, 245")


func test_occupancy_hysteresis_and_band() -> void:
	var occ := ZoneOccupancy.new()
	occ.configure(Tuning.rules, [{"id": "B", "center": [0, 0, 0], "floor_y": 0.0}])
	occ.set_zone("B")
	assert_true(occ.is_inside(1, Vector3(8.9, 0, 0)), "inside enter radius")
	assert_true(occ.is_inside(1, Vector3(9.2, 0, 0)), "stays inside within exit radius (hysteresis)")
	assert_false(occ.is_inside(1, Vector3(9.4, 0, 0)), "leaves beyond exit radius")
	assert_false(occ.is_inside(1, Vector3(9.2, 0, 0)), "must re-enter within the enter radius")
	assert_true(occ.is_inside(2, Vector3(0, 0.95, 0)), "normal jump apex stays in band")
	assert_false(occ.is_inside(3, Vector3(0, 3.5, 0)), "bridge/roof above the zone cannot capture")
	assert_false(occ.is_inside(4, Vector3(0, -1.0, 0)), "below the floor band does not count")
	occ.set_zone("A")
	assert_false(occ.is_inside(1, Vector3(0, 0, 0)), "only the active zone counts")
