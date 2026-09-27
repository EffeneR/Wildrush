extends WRTest
## Per-skill behaviour (G3): Vex, Hops, Scrap.

const S: float = PI
const N: float = 0.0


func _cast(sim: MatchSim, f: FighterBody, btn: int, others: Dictionary, move: Vector2 = Vector2.ZERO) -> Array[Dictionary]:
	var d: Dictionary = others.duplicate()
	d[f.entity_id] = frame(f.st.yaw, btn, move)
	return await run(sim, 1, func(_i: int) -> Dictionary: return d)


func _free_after(sim: MatchSim, f: FighterBody, others: Dictionary, limit: int = 200) -> int:
	var n: int = 0
	while n < limit and (f.st.act != null or f.st.ctrl != WR.Ctrl.NONE):
		var d: Dictionary = others.duplicate()
		d[f.entity_id] = frame(f.st.yaw)
		await run(sim, 1, func(_i: int) -> Dictionary: return d)
		n += 1
	return n


# ------------------------------------------------------------------------------ Vex
func test_vex_false_start_no_damage_sidestep_disguised() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "vex", "bruno", 1.3)
	var v: FighterBody = p[0]
	var b: FighterBody = p[1]
	await hold(sim, {v.entity_id: frame(S), b.entity_id: frame(N)}, 3)
	var x0: float = v.global_position.x
	var ev: Array[Dictionary] = await _cast(sim, v, WR.BTN_Q, {b.entity_id: frame(N)}, Vector2(-1, 0))
	assert_eq(Behaviors.of(v.st.act).display_id(v), "vex_heavy", "feint is shown to others as the heavy wind-up")
	ev.append_array(await hold(sim, {v.entity_id: frame(S, 0, Vector2(-1, 0)), b.entity_id: frame(N)}, 40))
	assert_eq(count(ev, "hit", {"a": v.entity_id}), 0, "feint deals no damage")
	# facing south, 'left' (move.x < 0) is the fighter's left = -right = +X world when facing +Z?
	var right: Vector3 = MathX.yaw_right(S)
	var moved: float = (v.global_position.x - x0) * right.x
	assert_lt(moved, -2.0, "sidestepped ~2.4 m to the chosen (left) side")
	assert_near(v.st.stamina, 90.0, 0.01)
	assert_eq(int(v.st.cd_ready["q"]) - sim.tick, WR.secs_to_ticks(6.0) - 40, "6 s cooldown")


func test_vex_sidewinder_curves_strikes_and_stops_at_contact() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "vex", "scrap", 5.5)
	var v: FighterBody = p[0]
	var s: FighterBody = p[1]
	await hold(sim, {v.entity_id: frame(S), s.entity_id: frame(N)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, v, WR.BTN_E, {s.entity_id: frame(N)}, Vector2(1, 0))
	var max_dev: float = 0.0
	for i in range(45):
		# the player steers the curve by keeping the camera on the target
		var aim: float = MathX.yaw_from_dir((s.global_position - v.global_position).normalized())
		ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return {v.entity_id: frame(aim), s.entity_id: frame(N)}))
		max_dev = maxf(max_dev, absf(v.global_position.x))
		assert_lt(v.global_position.z, s.global_position.z, "never passes the target")
	assert_gt(max_dev, 0.5, "curved approach (lateral deviation %.2f m)" % max_dev)
	assert_eq(count(ev, "hit", {"a": v.entity_id}), 1, "ends in a strike that connects")
	assert_near(s.st.health, 260.0 - 28.0, 0.01, "28 damage")


func test_vex_sidewinder_stops_at_wall() -> void:
	var sim: MatchSim = await make_sim()
	var v: FighterBody = sim.add_fighter("vex", 0, 0, "v")
	place(v, Vector3(0, 0.002, 8.5), S)
	await hold(sim, {v.entity_id: frame(S)}, 3)
	await _cast(sim, v, WR.BTN_E, {})
	await hold(sim, {v.entity_id: frame(S)}, 60)
	assert_lt(v.global_position.z, 12.0, "does not pass through the wall")


func test_vex_tail_sweep_low_guard_and_radius() -> void:
	var sim: MatchSim = await make_sim()
	var v: FighterBody = sim.add_fighter("vex", 0, 0, "v")
	var jumper: FighterBody = sim.add_fighter("hops", 1, 0, "j")
	var guard: FighterBody = sim.add_fighter("bruno", 1, 1, "g")
	var plain: FighterBody = sim.add_fighter("nyx", 1, 2, "p")
	var far: FighterBody = sim.add_fighter("scrap", 1, 3, "f")
	place(v, Vector3(0, 0.002, 0), S)
	place(jumper, Vector3(1.4, 0.002, 0.8), N)
	place(guard, Vector3(-1.4, 0.002, 0.6), -PI / 2.0 + 0.4)
	place(plain, Vector3(0, 0.002, -1.6), S)
	place(far, Vector3(0, 0.002, 4.0), N)
	# guard faces Vex: direction from guard to Vex is +X → yaw = -PI/2
	var gy: float = MathX.yaw_from_dir(Vector3(1.4, 0, -0.6).normalized())
	place(guard, Vector3(-1.4, 0.002, 0.6), gy)
	var idle := {v.entity_id: frame(S), jumper.entity_id: frame(N), guard.entity_id: frame(gy, WR.BTN_GUARD), plain.entity_id: frame(S), far.entity_id: frame(N)}
	await hold(sim, idle, 4)
	var ev: Array[Dictionary] = await _cast(sim, v, WR.BTN_R, idle)
	ev.append_array(await hold(sim, idle, 8))
	var dj: Dictionary = idle.duplicate()
	dj[jumper.entity_id] = frame(N, WR.BTN_JUMP)
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return dj))
	ev.append_array(await hold(sim, idle, 40))
	assert_eq(count(ev, "hit", {"t": jumper.entity_id}), 0, "jumping over the low sweep avoids it")
	assert_eq(count(ev, "block", {"t": guard.entity_id}), 1, "guard facing Vex blocks it")
	assert_eq(count(ev, "hit", {"t": plain.entity_id}), 1, "hits a grounded fighter behind Vex (rotational)")
	assert_near(plain.st.health, 220.0 - 20.0, 0.01, "modest 20 damage")
	assert_eq(count(ev, "hit", {"t": far.entity_id}), 0, "not a giant area: 4 m is out of reach")


# ------------------------------------------------------------------------------ Hops
func test_hops_lightfoot_keeps_landing_momentum() -> void:
	var sim: MatchSim = await make_sim()
	var h: FighterBody = sim.add_fighter("hops", 0, 0, "h")
	var n: FighterBody = sim.add_fighter("nyx", 0, 1, "n")
	place(h, Vector3(-10, 0.002, 30), N)
	place(n, Vector3(10, 0.002, 30), N)
	var run_in := {h.entity_id: frame(N, 0, Vector2(0, 1)), n.entity_id: frame(N, 0, Vector2(0, 1))}
	await hold(sim, run_in, 30)
	var jump := {h.entity_id: frame(N, WR.BTN_JUMP, Vector2(0, 1)), n.entity_id: frame(N, WR.BTN_JUMP, Vector2(0, 1))}
	await run(sim, 1, func(_i: int) -> Dictionary: return jump)
	var h_after: float = 0.0
	var n_after: float = 0.0
	var landed_h: bool = false
	var landed_n: bool = false
	for i in range(60):
		await run(sim, 1, func(_i: int) -> Dictionary: return run_in)
		if not landed_h and h.st.grounded and h.st.air_ticks == 0 and i > 5:
			landed_h = true
		if not landed_n and n.st.grounded and i > 5:
			landed_n = true
		if landed_h and h_after == 0.0:
			await run(sim, 3, func(_i: int) -> Dictionary: return run_in)
			h_after = Vector2(h.velocity.x, h.velocity.z).length() / 7.6
		if landed_n and n_after == 0.0:
			n_after = minf(1.0, Vector2(n.velocity.x, n.velocity.z).length() / 7.2)
	assert_true(sim.tick < n.st.landing_slow_until + 60, "Nyx had a landing slowdown")
	assert_gt(h_after, 0.97, "Hops keeps full momentum after landing")


func test_hops_bound_grounded_only_distance_no_damage() -> void:
	var sim: MatchSim = await make_sim()
	var h: FighterBody = sim.add_fighter("hops", 0, 0, "h")
	var e: FighterBody = sim.add_fighter("bruno", 1, 0, "e")
	place(h, Vector3(20, 0.002, 30), N)
	place(e, Vector3(20.3, 0.002, 26.0), S)
	await hold(sim, {h.entity_id: frame(N), e.entity_id: frame(S)}, 3)
	var z0: float = h.global_position.z
	var ev: Array[Dictionary] = await _cast(sim, h, WR.BTN_Q, {e.entity_id: frame(S)})
	ev.append_array(await hold(sim, {h.entity_id: frame(N), e.entity_id: frame(S)}, 60))
	assert_near(z0 - h.global_position.z, 7.5, 0.8, "~7.5 m leap")
	assert_eq(count(ev, "hit"), 0, "Bound deals no damage")
	# cannot activate in the air
	h.st.cd_ready["q"] = 0
	h.st.stamina = 100.0
	await run(sim, 1, func(_i: int) -> Dictionary: return {h.entity_id: frame(N, WR.BTN_JUMP), e.entity_id: frame(S)})
	await hold(sim, {h.entity_id: frame(N), e.entity_id: frame(S)}, 8)
	var ev2: Array[Dictionary] = await _cast(sim, h, WR.BTN_Q, {e.entity_id: frame(S)})
	ev2.append_array(await hold(sim, {h.entity_id: frame(N), e.entity_id: frame(S)}, 3))
	assert_eq(count(ev2, "action", {"e": h.entity_id, "a": "hops_bound"}), 0, "grounded activation only")


func test_hops_bound_air_control_is_bounded() -> void:
	var sim: MatchSim = await make_sim()
	var h: FighterBody = sim.add_fighter("hops", 0, 0, "h")
	place(h, Vector3(20, 0.002, 30), N)
	await hold(sim, {h.entity_id: frame(N)}, 3)
	await run(sim, 1, func(_i: int) -> Dictionary: return {h.entity_id: frame(N, WR.BTN_Q, Vector2(0, 1))})
	var land_pos: Vector3 = Vector3.ZERO
	for i in range(60):
		# forward during the crouch (sets the leap direction), then steer right in the air
		var mv: Vector2 = Vector2(0, 1) if i < 10 else Vector2(1, 0)
		await run(sim, 1, func(_i: int) -> Dictionary: return {h.entity_id: frame(N, 0, mv)})
		if h.st.act_phase == "land" and land_pos == Vector3.ZERO:
			land_pos = h.global_position
	var dx: float = land_pos.x - 20.0
	var dz: float = 30.0 - land_pos.z
	var ang: float = rad_to_deg(atan2(absf(dx), dz))
	assert_lt(ang, 26.0, "steering bounded to ±25° (got %.1f°)" % ang)
	assert_gt(ang, 3.0, "some steering applied")


func test_hops_double_kick_two_contacts() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "hops", "vex", 1.4)
	var h: FighterBody = p[0]
	var v: FighterBody = p[1]
	await hold(sim, {h.entity_id: frame(S), v.entity_id: frame(N)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, h, WR.BTN_E, {v.entity_id: frame(N)})
	ev.append_array(await hold(sim, {h.entity_id: frame(S), v.entity_id: frame(N)}, 50))
	assert_eq(count(ev, "hit", {"a": h.entity_id}), 2, "two separate kick contacts")
	assert_near(v.st.health, 220.0 - 34.0, 0.01, "15 + 19")


func test_hops_dropkick_hit_and_miss_crash() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "hops", "scrap", 3.5)
	var h: FighterBody = p[0]
	var s: FighterBody = p[1]
	await hold(sim, {h.entity_id: frame(S), s.entity_id: frame(N)}, 3)
	var z0: float = s.global_position.z
	var ev: Array[Dictionary] = await _cast(sim, h, WR.BTN_R, {s.entity_id: frame(N)})
	ev.append_array(await hold(sim, {h.entity_id: frame(S), s.entity_id: frame(N)}, 60))
	assert_eq(count(ev, "hit", {"a": h.entity_id}), 1, "dropkick connects")
	assert_near(s.st.health, 260.0 - 30.0, 0.01, "30 damage")
	assert_gt(s.global_position.z - z0, 1.8, "strong knockback")
	# miss → crash with long recovery
	var sim2: MatchSim = await make_sim()
	var h2: FighterBody = sim2.add_fighter("hops", 0, 0, "h2")
	place(h2, Vector3(-20, 0.002, 0), S)
	await hold(sim2, {h2.entity_id: frame(S)}, 3)
	await _cast(sim2, h2, WR.BTN_R, {})
	var total: int = 1 + await _free_after(sim2, h2, {})
	var expect: int = WR.secs_to_ticks(0.22) + WR.secs_to_ticks(0.40) + WR.secs_to_ticks(0.85)
	assert_true(absi(total - expect) <= 3, "miss: hop + flight + 0.85 s crash (%d vs %d)" % [total, expect])


# ------------------------------------------------------------------------------ Scrap
func test_scrap_quick_recovery_shorter_stun() -> void:
	var sim: MatchSim = await make_sim()
	var a1: FighterBody = sim.add_fighter("nyx", 0, 0, "a1")
	var s: FighterBody = sim.add_fighter("scrap", 1, 0, "s")
	var a2: FighterBody = sim.add_fighter("nyx", 0, 1, "a2")
	var v: FighterBody = sim.add_fighter("vex", 1, 1, "v")
	place(a1, Vector3(0, 0.002, 0), S)
	place(s, Vector3(0, 0.002, 1.3), N)
	place(a2, Vector3(10, 0.002, 0), S)
	place(v, Vector3(10, 0.002, 1.3), N)
	var idle := {a1.entity_id: frame(S), s.entity_id: frame(N), a2.entity_id: frame(S), v.entity_id: frame(N)}
	await hold(sim, idle, 3)
	var d := idle.duplicate()
	d[a1.entity_id] = frame(S, WR.BTN_LIGHT)
	d[a2.entity_id] = frame(S, WR.BTN_LIGHT)
	await run(sim, 1, func(_i: int) -> Dictionary: return d)
	await hold(sim, idle, 10)
	assert_eq(s.st.ctrl_len, int(round(12 * 0.8)), "Scrap stun ×0.8")
	assert_eq(v.st.ctrl_len, 12, "normal light stun")


func test_scrap_parry_success_redirects_attacker() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "scrap", "bruno", 1.3)
	var s: FighterBody = p[0]
	var b: FighterBody = p[1]
	await hold(sim, {s.entity_id: frame(S), b.entity_id: frame(N)}, 3)
	# Bruno jab active at tick 10; Scrap parry window ticks 3..15 → press parry 4 ticks after the jab
	var ev: Array[Dictionary] = await run(sim, 1, func(_i: int) -> Dictionary: return {s.entity_id: frame(S), b.entity_id: frame(N, WR.BTN_LIGHT)})
	ev.append_array(await hold(sim, {s.entity_id: frame(S), b.entity_id: frame(N)}, 3))
	ev.append_array(await _cast(sim, s, WR.BTN_Q, {b.entity_id: frame(N)}))
	ev.append_array(await hold(sim, {s.entity_id: frame(S), b.entity_id: frame(N)}, 20))
	assert_eq(count(ev, "parry", {"t": s.entity_id}), 1, "parry succeeds")
	assert_eq(s.st.health, 260.0, "no damage to Scrap")
	assert_true(b.st.ctrl == WR.Ctrl.STAGGER or b.st.has_cr(sim.tick), "attacker staggered")
	assert_true(absf(b.global_position.x) > 0.5, "attacker redirected aside")
	assert_true(int(s.st.cd_ready["q"]) - sim.tick < WR.secs_to_ticks(8.0) * 0.6, "cooldown refunded on success")


func test_scrap_parry_whiff_is_exposed_and_low_not_parryable() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "scrap", "vex", 1.3)
	var s: FighterBody = p[0]
	var v: FighterBody = p[1]
	await hold(sim, {s.entity_id: frame(S), v.entity_id: frame(N)}, 3)
	await _cast(sim, s, WR.BTN_Q, {v.entity_id: frame(N)})
	await hold(sim, {s.entity_id: frame(S), v.entity_id: frame(N)}, 17)
	assert_eq(s.st.act_phase, "whiff", "whiff leaves Scrap in recovery")
	var ev: Array[Dictionary] = await _cast(sim, v, WR.BTN_LIGHT, {s.entity_id: frame(S)})
	ev.append_array(await hold(sim, {s.entity_id: frame(S), v.entity_id: frame(N)}, 20))
	assert_eq(count(ev, "hit", {"t": s.entity_id}), 1, "whiff is punishable")
	# low sweep cannot be parried
	var sim2: MatchSim = await make_sim()
	var p2: Array = spawn_pair(sim2, "scrap", "vex", 1.3)
	var s2: FighterBody = p2[0]
	var v2: FighterBody = p2[1]
	await hold(sim2, {s2.entity_id: frame(S), v2.entity_id: frame(N)}, 3)
	var ev2: Array[Dictionary] = await run(sim2, 1, func(_i: int) -> Dictionary: return {s2.entity_id: frame(S), v2.entity_id: frame(N, WR.BTN_R)})
	ev2.append_array(await hold(sim2, {s2.entity_id: frame(S), v2.entity_id: frame(N)}, 12))
	ev2.append_array(await _cast(sim2, s2, WR.BTN_Q, {v2.entity_id: frame(N)}))
	ev2.append_array(await hold(sim2, {s2.entity_id: frame(S), v2.entity_id: frame(N)}, 30))
	assert_eq(count(ev2, "parry"), 0, "tail sweep is not parryable")
	assert_eq(count(ev2, "hit", {"t": s2.entity_id}), 1)


func test_scrap_leg_sweep_blocked_by_front_guard() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "scrap", "nyx", 1.1)
	var s: FighterBody = p[0]
	var n: FighterBody = p[1]
	await hold(sim, {s.entity_id: frame(S), n.entity_id: frame(N, WR.BTN_GUARD)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, s, WR.BTN_E, {n.entity_id: frame(N, WR.BTN_GUARD)})
	ev.append_array(await hold(sim, {s.entity_id: frame(S), n.entity_id: frame(N, WR.BTN_GUARD)}, 30))
	assert_eq(count(ev, "block", {"t": n.entity_id}), 1, "proper frontal guard defends the sweep")
	assert_ne(n.st.ctrl, WR.Ctrl.KNOCKDOWN)


func test_scrap_turnabout_repositions_releases_and_ignores_guard() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "scrap", "bruno", 1.1)
	var s: FighterBody = p[0]
	var b: FighterBody = p[1]
	await hold(sim, {s.entity_id: frame(S), b.entity_id: frame(N, WR.BTN_GUARD)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, s, WR.BTN_R, {b.entity_id: frame(N, WR.BTN_GUARD)})
	ev.append_array(await hold(sim, {s.entity_id: frame(S), b.entity_id: frame(N, WR.BTN_GUARD)}, 60))
	assert_eq(count(ev, "grab", {"e": s.entity_id}), 1, "grab connects through guard")
	assert_lt(b.global_position.z, s.global_position.z - 0.5, "opponent placed on Scrap's other side")
	assert_near(b.st.health, 280.0 - 12.0, 0.01, "12 damage on release")
	assert_eq(b.st.ctrl, WR.Ctrl.NONE, "released (free again)")
	assert_true(b.st.has_cr(sim.tick), "grab is hard control → CR")


func test_scrap_turnabout_never_through_wall() -> void:
	var sim: MatchSim = await make_sim()
	var s: FighterBody = sim.add_fighter("scrap", 0, 0, "s")
	var b: FighterBody = sim.add_fighter("vex", 1, 0, "b")
	# Scrap's back against wall_test (z 12..13): Scrap at z=11.55 facing north; target north of him
	place(s, Vector3(0, 0.002, 11.55), N)
	place(b, Vector3(0, 0.002, 10.45), S)
	await hold(sim, {s.entity_id: frame(N), b.entity_id: frame(S)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, s, WR.BTN_R, {b.entity_id: frame(S)})
	ev.append_array(await hold(sim, {s.entity_id: frame(N), b.entity_id: frame(S)}, 60))
	assert_eq(count(ev, "grab"), 1)
	assert_lt(b.global_position.z, 12.0 - b.def.hurt_radius + 0.05, "never pulled into/through the wall")


func test_scrap_turnabout_broken_by_hit_and_resisted_by_cr() -> void:
	var sim: MatchSim = await make_sim()
	var s: FighterBody = sim.add_fighter("scrap", 0, 0, "s")
	var b: FighterBody = sim.add_fighter("bruno", 1, 0, "b")
	var h: FighterBody = sim.add_fighter("hops", 1, 1, "h")
	place(s, Vector3(0, 0.002, 0), S)
	place(b, Vector3(0, 0.002, 1.1), N)
	place(h, Vector3(-1.2, 0.002, -0.2), -PI / 2.0)
	var idle := {s.entity_id: frame(S), b.entity_id: frame(N), h.entity_id: frame(-PI / 2.0)}
	await hold(sim, idle, 3)
	var ev: Array[Dictionary] = await _cast(sim, s, WR.BTN_R, {b.entity_id: frame(N), h.entity_id: frame(-PI / 2.0)})
	ev.append_array(await hold(sim, idle, 10))
	assert_eq(count(ev, "grab"), 1, "grab started")
	ev.append_array(await _cast(sim, h, WR.BTN_LIGHT, {s.entity_id: frame(S), b.entity_id: frame(N)}))
	ev.append_array(await hold(sim, idle, 20))
	assert_eq(count(ev, "grab_broken"), 1, "nearby attack breaks the grapple")
	# CR: target with control resistance cannot be grappled
	var sim2: MatchSim = await make_sim()
	var p2: Array = spawn_pair(sim2, "scrap", "nyx", 1.1)
	var s2: FighterBody = p2[0]
	var n2: FighterBody = p2[1]
	await hold(sim2, {s2.entity_id: frame(S), n2.entity_id: frame(N)}, 3)
	n2.st.cr_until = sim2.tick + 600
	var ev2: Array[Dictionary] = await _cast(sim2, s2, WR.BTN_R, {n2.entity_id: frame(N)})
	ev2.append_array(await hold(sim2, {s2.entity_id: frame(S), n2.entity_id: frame(N)}, 30))
	assert_eq(count(ev2, "grab_resisted"), 1, "control resistance prevents the grapple")
