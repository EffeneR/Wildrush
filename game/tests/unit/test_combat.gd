extends WRTest
## Shared combat and movement (spec §5, D-010, D-011).

const SOUTH: float = PI   # yaw facing +Z
const NORTH: float = 0.0  # yaw facing -Z


func _idle(sim: MatchSim, pair: Array, n: int) -> Array[Dictionary]:
	return await hold(sim, {pair[0].entity_id: frame(pair[0].st.yaw), pair[1].entity_id: frame(pair[1].st.yaw)}, n)


func test_move_speed_strafe_and_vex_light_steps() -> void:
	var sim: MatchSim = await make_sim()
	var nyx: FighterBody = sim.add_fighter("nyx", 0, 0, "n")
	var vex: FighterBody = sim.add_fighter("vex", 1, 0, "v")
	place(nyx, Vector3(-20, 0.002, 0), NORTH)
	place(vex, Vector3(20, 0.002, 0), NORTH)
	await hold(sim, {nyx.entity_id: frame(NORTH, 0, Vector2(0, 1)), vex.entity_id: frame(NORTH, 0, Vector2(0, 1))}, 40)
	assert_near(Vector2(nyx.velocity.x, nyx.velocity.z).length(), 7.2, 0.05, "Nyx forward speed 7.2")
	assert_near(Vector2(vex.velocity.x, vex.velocity.z).length(), 7.0, 0.05, "Vex forward speed 7.0")
	await hold(sim, {nyx.entity_id: frame(NORTH, 0, Vector2(1, 0)), vex.entity_id: frame(NORTH, 0, Vector2(1, 0))}, 40)
	assert_near(Vector2(nyx.velocity.x, nyx.velocity.z).length(), 7.2 * 0.88, 0.08, "default strafe = 88%")
	assert_near(Vector2(vex.velocity.x, vex.velocity.z).length(), 7.0 * 0.96, 0.08, "Vex Light Steps strafe = 96%")
	await hold(sim, {nyx.entity_id: frame(NORTH), vex.entity_id: frame(NORTH)}, 30)
	assert_lt(Vector2(nyx.velocity.x, nyx.velocity.z).length(), 0.05, "decelerates to stop")


func test_light_hit_damage_and_single_hit_per_strike() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "bruno", 1.3)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	await _idle(sim, p, 3)
	var ev: Array[Dictionary] = await press(sim, a.entity_id, SOUTH, WR.BTN_LIGHT, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	ev.append_array(await _idle(sim, p, 30))
	assert_eq(count(ev, "hit"), 1, "exactly one hit from one strike")
	assert_near(b.st.health, 280.0 - 18.0, 0.01, "light = 18 damage")


func test_no_friendly_fire() -> void:
	var sim: MatchSim = await make_sim()
	var a: FighterBody = sim.add_fighter("nyx", 0, 0, "a")
	var b: FighterBody = sim.add_fighter("bruno", 0, 1, "b")
	place(a, Vector3(0, 0.002, 0), SOUTH)
	place(b, Vector3(0, 0.002, 1.3), NORTH)
	var ev: Array[Dictionary] = await press(sim, a.entity_id, SOUTH, WR.BTN_HEAVY, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	ev.append_array(await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH)}, 70))
	assert_eq(count(ev, "hit"), 0, "teammates are never damaged")
	assert_eq(b.st.health, 280.0)


func test_guard_blocks_front_not_back() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "vex", "bruno", 1.3)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	# B guards facing A
	await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH, WR.BTN_GUARD)}, 5)
	var ev: Array[Dictionary] = []
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return {a.entity_id: frame(SOUTH, WR.BTN_LIGHT), b.entity_id: frame(NORTH, WR.BTN_GUARD)}))
	ev.append_array(await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH, WR.BTN_GUARD)}, 30))
	assert_eq(count(ev, "block"), 1, "frontal guard blocks")
	assert_eq(b.st.health, 280.0, "no damage through guard")
	assert_near(b.st.stamina, 100.0 - 12.0, 0.01, "blocked light costs 12 stamina")
	# B turns its back while guarding → hit lands
	place(b, Vector3(0, 0.002, 1.3), SOUTH)
	await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(SOUTH, WR.BTN_GUARD)}, 3)
	var ev2: Array[Dictionary] = []
	ev2.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return {a.entity_id: frame(SOUTH, WR.BTN_LIGHT), b.entity_id: frame(SOUTH, WR.BTN_GUARD)}))
	ev2.append_array(await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(SOUTH, WR.BTN_GUARD)}, 30))
	assert_eq(count(ev2, "hit"), 1, "guard does not protect the back")
	assert_near(b.st.health, 280.0 - 18.0, 0.01)


func test_guard_break_is_punishable() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "bruno", "nyx", 1.3)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	b.st.stamina = 20.0
	b.st.last_spend_tick = sim.tick
	await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH, WR.BTN_GUARD)}, 3)
	var ev: Array[Dictionary] = []
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return {a.entity_id: frame(SOUTH, WR.BTN_HEAVY), b.entity_id: frame(NORTH, WR.BTN_GUARD)}))
	ev.append_array(await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH, WR.BTN_GUARD)}, 32))
	assert_eq(count(ev, "guard_break"), 1, "heavy (28 guard dmg) breaks a 20-stamina guard")
	assert_eq(b.st.ctrl, WR.Ctrl.GUARD_BREAK, "guard break stun active")
	assert_false(b.st.guarding, "guard dropped")
	assert_true(b.st.has_cr(sim.tick), "guard break grants control resistance")


func test_stamina_costs_and_regen_rules() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "hops", "scrap", 6.0)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	await _idle(sim, p, 3)
	await press(sim, a.entity_id, SOUTH, WR.BTN_DODGE, Vector2(0, -1), {b.entity_id: frame(NORTH)})
	assert_near(a.st.stamina, 75.0, 0.01, "dodge costs 25")
	await _idle(sim, p, 40)
	await press(sim, a.entity_id, SOUTH, WR.BTN_HEAVY, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	assert_near(a.st.stamina, 60.0, 0.01, "heavy costs 15, no regen before 0.9 s")
	await _idle(sim, p, 70)
	var s1: float = a.st.stamina
	await _idle(sim, p, 30)
	assert_near(a.st.stamina - s1, 12.0, 0.2, "regen 24/s after the delay")
	# no regen while holding guard
	var s2: float = a.st.stamina
	await hold(sim, {a.entity_id: frame(SOUTH, WR.BTN_GUARD), b.entity_id: frame(NORTH)}, 60)
	assert_near(a.st.stamina, s2, 0.01, "no stamina regen while guarding")


func test_health_regen_after_six_seconds() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "vex", 1.3)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	await press(sim, a.entity_id, SOUTH, WR.BTN_LIGHT, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	await _idle(sim, p, 30)
	var hp: float = b.st.health
	assert_near(hp, 202.0, 0.01)
	await _idle(sim, p, 5 * 60)
	assert_near(b.st.health, hp, 0.01, "no regen within 6 s of damage")
	await _idle(sim, p, 90)
	assert_gt(b.st.health, hp + 10.0, "regenerates at 18/s after 6 s")


func test_dodge_evades_and_is_limited() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "bruno", "nyx", 1.2)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	# A heavy: active from tick 27. B dodges back so the evasion window (ticks 2..13) covers it.
	var ev: Array[Dictionary] = []
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return {a.entity_id: frame(SOUTH, WR.BTN_HEAVY), b.entity_id: frame(NORTH)}))
	ev.append_array(await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH)}, 18))
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH, WR.BTN_DODGE, Vector2(1, 0))}))
	ev.append_array(await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH)}, 50))
	assert_eq(count(ev, "hit"), 0, "dodge evades or outspaces the heavy")
	assert_eq(b.st.health, 230.0 * 0.0 + Tuning.fighter("nyx").health, "no damage taken")
	var evade_ticks: int = Tuning.dodge_evade_to - Tuning.dodge_evade_from + 1
	assert_true(evade_ticks <= 14, "evasion window is short and explicit (%d ticks)" % evade_ticks)


func test_hits_do_not_pass_through_walls() -> void:
	var sim: MatchSim = await make_sim()
	var vex: FighterBody = sim.add_fighter("vex", 0, 0, "v")
	var t: FighterBody = sim.add_fighter("hops", 1, 0, "t")
	# wall_test spans x[-5,5] z[12,13], 4 m tall
	place(vex, Vector3(0, 0.002, 11.55), SOUTH)
	place(t, Vector3(0, 0.002, 13.45), NORTH)
	var ev: Array[Dictionary] = await press(sim, vex.entity_id, SOUTH, WR.BTN_R, Vector2.ZERO, {t.entity_id: frame(NORTH)})
	ev.append_array(await hold(sim, {vex.entity_id: frame(SOUTH), t.entity_id: frame(NORTH)}, 60))
	assert_eq(count(ev, "hit"), 0, "tail sweep does not hit through the wall")
	# control: same spacing without a wall
	place(vex, Vector3(20, 0.002, 11.55), SOUTH)
	place(t, Vector3(20, 0.002, 13.45), NORTH)
	vex.st.cd_ready["r"] = 0
	vex.st.stamina = 100.0
	var ev2: Array[Dictionary] = await press(sim, vex.entity_id, SOUTH, WR.BTN_R, Vector2.ZERO, {t.entity_id: frame(NORTH)})
	ev2.append_array(await hold(sim, {vex.entity_id: frame(SOUTH), t.entity_id: frame(NORTH)}, 60))
	assert_eq(count(ev2, "hit"), 1, "same sweep hits without the wall")


func test_knockout_respawn_and_protection() -> void:
	var sim: MatchSim = await make_sim()
	sim.begin_live()
	var p: Array = spawn_pair(sim, "bruno", "hops", 1.3)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	b.st.health = 10.0
	var ev: Array[Dictionary] = await press(sim, a.entity_id, SOUTH, WR.BTN_LIGHT, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	ev.append_array(await _idle(sim, p, 20))
	assert_eq(count(ev, "ko"), 1, "KO at 0 health")
	assert_false(b.st.alive)
	assert_false(b.is_eligible_occupant(), "KO removes from occupancy immediately")
	assert_eq(a.st.kos, 1, "KO credited")
	var ko_tick: int = int(ev.filter(func(e: Dictionary) -> bool: return e["type"] == "ko")[0]["tick"])
	var ev2: Array[Dictionary] = await _idle(sim, p, 600)
	var resp: Array = ev2.filter(func(e: Dictionary) -> bool: return e["type"] == "respawn")
	assert_eq(resp.size(), 1, "respawned once")
	if not resp.is_empty():
		assert_eq(int(resp[0]["tick"]) - ko_tick, 600, "respawn after exactly 10 s")
	assert_true(b.st.alive)
	assert_eq(b.st.health, 230.0, "resources restored")
	assert_true(b.st.spawn_protected, "spawn protection active")
	assert_true(sim.layout.spawn_volume(1).has_point(b.global_position + Vector3(0, 0.5, 0)), "respawned inside own spawn")


func test_spawn_protection_ends_on_offense() -> void:
	var sim: MatchSim = await make_sim()
	var a: FighterBody = sim.add_fighter("nyx", 1, 0, "a")
	place(a, Vector3(0, 0.002, 42), NORTH)
	a.st.spawn_protected = true
	a.st.protect_until = sim.tick + 480
	await hold(sim, {a.entity_id: frame(NORTH)}, 5)
	assert_true(a.st.spawn_protected)
	var ev: Array[Dictionary] = await press(sim, a.entity_id, NORTH, WR.BTN_LIGHT)
	assert_false(a.st.spawn_protected, "offensive action ends protection")
	assert_eq(count(ev, "protect_end", {"reason": "offense"}), 1)


func test_spawn_protection_ends_when_leaving_volume() -> void:
	var sim: MatchSim = await make_sim()
	var a: FighterBody = sim.add_fighter("nyx", 1, 0, "a")
	place(a, Vector3(0, 0.002, 38), NORTH)
	a.st.spawn_protected = true
	a.st.protect_until = sim.tick + 480
	await hold(sim, {a.entity_id: frame(NORTH, 0, Vector2(0, 1))}, 40)
	assert_false(a.st.spawn_protected, "leaving the protected volume ends protection")


func test_enemy_cannot_enter_protected_spawn() -> void:
	var sim: MatchSim = await make_sim()
	var intruder: FighterBody = sim.add_fighter("hops", 1, 0, "i")   # team 1 approaching team 0's spawn
	place(intruder, Vector3(0, 0.002, -32), NORTH)
	await hold(sim, {intruder.entity_id: frame(NORTH, 0, Vector2(0, 1))}, 120)
	assert_gt(intruder.global_position.z, -36.05, "blocked at the enemy spawn barrier")
	var owner_f: FighterBody = sim.add_fighter("nyx", 0, 0, "o")
	place(owner_f, Vector3(3, 0.002, -32), NORTH)
	await hold(sim, {owner_f.entity_id: frame(NORTH, 0, Vector2(0, 1)), intruder.entity_id: frame(NORTH)}, 60)
	assert_lt(owner_f.global_position.z, -37.0, "own team passes its barrier")


func test_control_resistance_prevents_repeated_lockdown() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "scrap", "vex", 1.1)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	var ev: Array[Dictionary] = await press(sim, a.entity_id, SOUTH, WR.BTN_E, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	ev.append_array(await _idle(sim, p, 30))
	assert_eq(count(ev, "hit"), 1, "leg sweep hits")
	assert_true(b.st.ctrl == WR.Ctrl.KNOCKDOWN or b.st.ctrl == WR.Ctrl.GETUP, "knocked down")
	assert_true(b.st.has_cr(sim.tick), "CR granted")
	# wait until B is up, sweep again within CR → downgraded
	await _idle(sim, p, 80)
	assert_eq(b.st.ctrl, WR.Ctrl.NONE, "B recovered")
	a.st.cd_ready["e"] = 0
	a.st.stamina = 100.0
	place(b, Vector3(0, 0.002, 1.1), NORTH)
	var ev2: Array[Dictionary] = await press(sim, a.entity_id, SOUTH, WR.BTN_E, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	ev2.append_array(await _idle(sim, p, 20))
	assert_eq(count(ev2, "hit"), 1, "second sweep still damages")
	assert_eq(count(ev2, "resisted"), 1, "second knockdown resisted")
	assert_ne(b.st.ctrl, WR.Ctrl.KNOCKDOWN, "no repeated knockdown under CR")


func test_stale_buffered_input_does_not_fire() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "bruno", "scrap", 3.0)
	var a: FighterBody = p[0]
	var b: FighterBody = p[1]
	# heavy: no light cancel until 0.92 s; a light pressed early must expire
	await run(sim, 1, func(_i: int) -> Dictionary: return {a.entity_id: frame(SOUTH, WR.BTN_HEAVY), b.entity_id: frame(NORTH)})
	await hold(sim, {a.entity_id: frame(SOUTH), b.entity_id: frame(NORTH)}, 10)
	await press(sim, a.entity_id, SOUTH, WR.BTN_LIGHT, Vector2.ZERO, {b.entity_id: frame(NORTH)})
	var ev: Array[Dictionary] = await _idle(sim, p, 80)
	assert_eq(count(ev, "action", {"e": a.entity_id}), 0, "stale light press never fires later")


func test_teammates_cannot_trap_each_other() -> void:
	var sim: MatchSim = await make_sim()
	var a: FighterBody = sim.add_fighter("bruno", 0, 0, "a")
	var b: FighterBody = sim.add_fighter("scrap", 0, 1, "b")
	place(a, Vector3(0, 0.002, 0), NORTH)
	place(b, Vector3(0, 0.002, 3), NORTH)
	await hold(sim, {a.entity_id: frame(NORTH), b.entity_id: frame(NORTH, 0, Vector2(0, 1))}, 90)
	assert_lt(b.global_position.z, -2.0, "a fighter walks through a standing teammate (no hard collision)")
	var d: float = Vector2(a.global_position.x - b.global_position.x, a.global_position.z - b.global_position.z).length()
	assert_gt(d, 0.5, "soft separation keeps bodies apart")


func test_perch_is_nyx_only_and_validated() -> void:
	var sim: MatchSim = await make_sim()
	var nyx: FighterBody = sim.add_fighter("nyx", 0, 0, "n")
	var bruno: FighterBody = sim.add_fighter("bruno", 0, 1, "b")
	# ledge top 1.5 m at x in [20,30], z in [10,20]; west face at x=20, climb side normal (-1,0,0)
	var east: float = -PI / 2.0   # yaw facing +X
	place(nyx, Vector3(19.4, 0.002, 12), east)
	place(bruno, Vector3(19.4, 0.002, 17), east)
	await hold(sim, {nyx.entity_id: frame(east), bruno.entity_id: frame(east)}, 3)
	var ev: Array[Dictionary] = await press(sim, nyx.entity_id, east, WR.BTN_JUMP, Vector2.ZERO, {bruno.entity_id: frame(east, WR.BTN_JUMP)})
	ev.append_array(await hold(sim, {nyx.entity_id: frame(east), bruno.entity_id: frame(east)}, 40))
	assert_eq(count(ev, "perch", {"e": nyx.entity_id}), 1, "Nyx scrambles onto the designated ledge")
	assert_gt(nyx.global_position.y, 1.4, "Nyx on top of the 1.5 m ledge")
	assert_gt(nyx.global_position.x, 20.2, "moved past the edge onto the top")
	assert_lt(bruno.global_position.y, 0.3, "others cannot climb it (1.5 m is above any jump)")
