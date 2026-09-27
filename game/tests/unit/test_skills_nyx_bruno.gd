extends WRTest
## Per-skill behaviour (G3): Nyx (Perch, Pounce, Crosscut, Slip) and Bruno (Grounded,
## Shoulder Rush, Warning Bark, Stand Firm): startup, cooldown, stamina, hit validity, miss
## recovery, wall interaction, interruption, control resistance.

const S: float = PI
const N: float = 0.0


func _first(ev: Array, type: String, extra: Dictionary = {}) -> Dictionary:
	for e in ev:
		if String(e.get("type", "")) != type:
			continue
		var ok: bool = true
		for k in extra.keys():
			if e.get(k) != extra[k]:
				ok = false
		if ok:
			return e
	return {}


func _cast(sim: MatchSim, f: FighterBody, btn: int, others: Dictionary, move: Vector2 = Vector2.ZERO) -> Array[Dictionary]:
	var d: Dictionary = others.duplicate()
	d[f.entity_id] = frame(f.st.yaw, btn, move)
	return await run(sim, 1, func(_i: int) -> Dictionary: return d)


func _action_ticks(sim: MatchSim, f: FighterBody, others: Dictionary, limit: int = 200) -> int:
	## Ticks until f is free again (no action, no control).
	var n: int = 0
	while n < limit and (f.st.act != null or f.st.ctrl != WR.Ctrl.NONE):
		var d: Dictionary = others.duplicate()
		d[f.entity_id] = frame(f.st.yaw)
		await run(sim, 1, func(_i: int) -> Dictionary: return d)
		n += 1
	return n


# ------------------------------------------------------------------------------ Nyx Pounce
func test_nyx_pounce_hits_with_startup_cost_cooldown() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "bruno", 5.0)
	var nyx: FighterBody = p[0]
	var b: FighterBody = p[1]
	await hold(sim, {nyx.entity_id: frame(S), b.entity_id: frame(N)}, 3)
	var t0: int = sim.tick
	var ev: Array[Dictionary] = await _cast(sim, nyx, WR.BTN_Q, {b.entity_id: frame(N)})
	assert_near(nyx.st.stamina, 90.0, 0.01, "Pounce costs 10 stamina")
	assert_eq(int(nyx.st.cd_ready["q"]) - sim.tick, WR.secs_to_ticks(9.0), "9 s cooldown starts on use")
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S), b.entity_id: frame(N)}, 70))
	var hit: Dictionary = _first(ev, "hit", {"a": nyx.entity_id})
	assert_false(hit.is_empty(), "Pounce connects at 5 m")
	if not hit.is_empty():
		assert_true(int(hit["tick"]) - t0 >= 27, "claw strike only in the late leap window (startup ≥ 0.45 s)")
	assert_near(b.st.health, 280.0 - 34.0, 0.01, "34 damage")
	# cannot recast during cooldown
	var ev2: Array[Dictionary] = await _cast(sim, nyx, WR.BTN_Q, {b.entity_id: frame(N)})
	assert_eq(count(ev2, "action", {"e": nyx.entity_id}), 0, "on cooldown")


func test_nyx_pounce_no_homing_and_miss_recovery() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "vex", 5.0)
	var nyx: FighterBody = p[0]
	var v: FighterBody = p[1]
	await hold(sim, {nyx.entity_id: frame(S), v.entity_id: frame(N)}, 3)
	await _cast(sim, nyx, WR.BTN_Q, {v.entity_id: frame(N)})
	# target sidesteps during the aim; Nyx keeps her committed direction
	var ev: Array[Dictionary] = await hold(sim, {nyx.entity_id: frame(S), v.entity_id: frame(N, 0, Vector2(1, 0))}, 18)
	var yaw_at_leap: float = nyx.st.yaw
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S + 0.8), v.entity_id: frame(N, 0, Vector2(1, 0))}, 30))
	assert_near(nyx.st.yaw, yaw_at_leap, 0.001, "no steering/homing after commitment")
	assert_eq(count(ev, "hit", {"a": nyx.entity_id}), 0, "moving target avoided the committed leap")
	assert_eq(String(nyx.st.act_data.get("outcome", "miss")), "miss", "miss outcome")
	assert_eq(nyx.st.act_phase, "land", "landing recovery")
	var rec: int = await _action_ticks(sim, nyx, {v.entity_id: frame(N)})
	assert_true(rec >= WR.secs_to_ticks(0.65) - 12, "miss leaves a long, punishable landing (%d ticks)" % rec)


func test_nyx_pounce_stopped_by_wall() -> void:
	var sim: MatchSim = await make_sim()
	var nyx: FighterBody = sim.add_fighter("nyx", 0, 0, "n")
	place(nyx, Vector3(0, 0.002, 9.5), S)   # wall_test at z 12..13
	await hold(sim, {nyx.entity_id: frame(S)}, 3)
	await _cast(sim, nyx, WR.BTN_Q, {})
	await hold(sim, {nyx.entity_id: frame(S)}, 45)
	assert_lt(nyx.global_position.z, 12.0 - nyx.def.hurt_radius + 0.05, "wall stops the leap")
	assert_eq(String(nyx.st.act_data.get("outcome", "")), "wall", "wall outcome")


func test_nyx_pounce_interrupted_during_aim() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "scrap", 1.2)
	var nyx: FighterBody = p[0]
	var s: FighterBody = p[1]
	await hold(sim, {nyx.entity_id: frame(S), s.entity_id: frame(N)}, 3)
	var ev: Array[Dictionary] = await run(sim, 1, func(_i: int) -> Dictionary: return {nyx.entity_id: frame(S, WR.BTN_Q), s.entity_id: frame(N, WR.BTN_LIGHT)})
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S), s.entity_id: frame(N)}, 20))
	assert_eq(count(ev, "interrupted", {"e": nyx.entity_id}), 1, "a hit during Pounce aim interrupts it")
	assert_eq(count(ev, "hit", {"a": nyx.entity_id}), 0)


# ------------------------------------------------------------------------------ Nyx Crosscut
func test_nyx_crosscut_two_separate_strikes() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "hops", 1.3)
	var nyx: FighterBody = p[0]
	var h: FighterBody = p[1]
	await hold(sim, {nyx.entity_id: frame(S), h.entity_id: frame(N)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, nyx, WR.BTN_E, {h.entity_id: frame(N)})
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S), h.entity_id: frame(N)}, 50))
	var hits: Array = ev.filter(func(e: Dictionary) -> bool: return e["type"] == "hit" and e["a"] == nyx.entity_id)
	assert_eq(hits.size(), 2, "two contacts")
	if hits.size() == 2:
		assert_ne(int(hits[0]["hi"]), int(hits[1]["hi"]), "separate hit windows")
		assert_true(int(hits[1]["tick"]) - int(hits[0]["tick"]) >= 12, "second window is later")
	assert_near(h.st.health, 230.0 - 36.0, 0.01, "16 + 20 damage")
	assert_near(nyx.st.stamina, 88.0, 0.01, "12 stamina")


func test_nyx_crosscut_second_not_guaranteed_vs_defense() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "hops", 1.3)
	var nyx: FighterBody = p[0]
	var h: FighterBody = p[1]
	await hold(sim, {nyx.entity_id: frame(S), h.entity_id: frame(N, WR.BTN_GUARD)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, nyx, WR.BTN_E, {h.entity_id: frame(N, WR.BTN_GUARD)})
	# first strike blocked; defender then dodges before the second window
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S), h.entity_id: frame(N, WR.BTN_GUARD)}, 14))
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return {nyx.entity_id: frame(S), h.entity_id: frame(N, WR.BTN_DODGE, Vector2(0, -1))}))
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S), h.entity_id: frame(N)}, 40))
	assert_eq(count(ev, "block", {"a": nyx.entity_id}), 1, "first strike blocked")
	assert_eq(count(ev, "hit", {"a": nyx.entity_id}), 0, "second strike avoided after a successful defense")


# ------------------------------------------------------------------------------ Nyx Slip
func test_nyx_slip_evades_and_counter_window() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "bruno", 1.3)
	var nyx: FighterBody = p[0]
	var b: FighterBody = p[1]
	await hold(sim, {nyx.entity_id: frame(S), b.entity_id: frame(N)}, 3)
	var x0: float = nyx.global_position.x
	var ev: Array[Dictionary] = await run(sim, 1, func(_i: int) -> Dictionary: return {nyx.entity_id: frame(S, WR.BTN_R, Vector2(-1, 0)), b.entity_id: frame(N, WR.BTN_LIGHT)})
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S), b.entity_id: frame(N)}, 9))
	# counter-swipe inside the window
	ev.append_array(await _cast(sim, nyx, WR.BTN_LIGHT, {b.entity_id: frame(N)}))
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S), b.entity_id: frame(N)}, 30))
	assert_near(absf(nyx.global_position.x - x0), 2.6, 0.35, "lateral 2.6 m evade (continuous, visible)")
	assert_eq(count(ev, "hit", {"a": b.entity_id}), 0, "Bruno's jab evaded")
	assert_eq(count(ev, "action", {"e": nyx.entity_id, "a": "nyx_slip_counter"}), 1, "counter-swipe triggered in window")
	assert_near(nyx.st.stamina, 85.0, 0.01, "15 stamina")


func test_nyx_slip_counter_only_in_window() -> void:
	var sim: MatchSim = await make_sim()
	var nyx: FighterBody = sim.add_fighter("nyx", 0, 0, "n")
	place(nyx, Vector3(0, 0.002, 0), S)
	await hold(sim, {nyx.entity_id: frame(S)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, nyx, WR.BTN_R, {})
	ev.append_array(await _cast(sim, nyx, WR.BTN_LIGHT, {}))  # too early (tick 1 < 0.12 s)
	ev.append_array(await hold(sim, {nyx.entity_id: frame(S)}, 40))
	assert_eq(count(ev, "action", {"a": "nyx_slip_counter"}), 0, "no counter outside its window")


# ------------------------------------------------------------------------------ Bruno
func test_bruno_grounded_halves_light_push() -> void:
	var sim: MatchSim = await make_sim()
	var nyx: FighterBody = sim.add_fighter("nyx", 0, 0, "n")
	var b: FighterBody = sim.add_fighter("bruno", 1, 0, "b")
	var v: FighterBody = sim.add_fighter("vex", 1, 1, "v")
	var nyx2: FighterBody = sim.add_fighter("nyx", 0, 1, "n2")
	place(nyx, Vector3(0, 0.002, 0), S)
	place(b, Vector3(0, 0.002, 1.3), N)
	place(nyx2, Vector3(10, 0.002, 0), S)
	place(v, Vector3(10, 0.002, 1.3), N)
	var all := {nyx.entity_id: frame(S), b.entity_id: frame(N), nyx2.entity_id: frame(S), v.entity_id: frame(N)}
	await hold(sim, all, 3)
	var zb: float = b.global_position.z
	var zv: float = v.global_position.z
	# light finisher push (3rd light) is the largest light push; use a single light here
	var d1: Dictionary = all.duplicate()
	d1[nyx.entity_id] = frame(S, WR.BTN_LIGHT)
	d1[nyx2.entity_id] = frame(S, WR.BTN_LIGHT)
	await run(sim, 1, func(_i: int) -> Dictionary: return d1)
	await hold(sim, all, 40)
	var pb: float = b.global_position.z - zb
	var pv: float = v.global_position.z - zv
	assert_gt(pv, 0.2, "Vex pushed by a light hit")
	assert_near(pb, pv * 0.5, 0.08, "Bruno Grounded: half the light push")


func test_bruno_rush_hit_knockback_and_steer_limit() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "bruno", "vex", 5.0)
	var b: FighterBody = p[0]
	var v: FighterBody = p[1]
	await hold(sim, {b.entity_id: frame(S), v.entity_id: frame(N)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, b, WR.BTN_Q, {v.entity_id: frame(N)})
	assert_near(b.st.stamina, 85.0, 0.01)
	var z0: float = v.global_position.z
	ev.append_array(await hold(sim, {b.entity_id: frame(S), v.entity_id: frame(N)}, 60))
	assert_eq(count(ev, "hit", {"a": b.entity_id}), 1, "rush connects once")
	assert_near(v.st.health, 220.0 - 26.0, 0.01, "26 damage")
	assert_gt(v.global_position.z - z0, 1.5, "short displacement along the charge")
	assert_true(v.st.has_cr(sim.tick), "0.5 s stagger is hard control → CR")


func test_bruno_rush_wall_bump_and_miss_recovery() -> void:
	var sim: MatchSim = await make_sim()
	var b: FighterBody = sim.add_fighter("bruno", 0, 0, "b")
	place(b, Vector3(0, 0.002, 8.0), S)
	await hold(sim, {b.entity_id: frame(S)}, 3)
	var ev: Array[Dictionary] = await _cast(sim, b, WR.BTN_Q, {})
	ev.append_array(await hold(sim, {b.entity_id: frame(S)}, 45))
	assert_eq(count(ev, "wall_bump", {"e": b.entity_id}), 1, "wall stops the charge")
	assert_lt(b.global_position.z, 12.0, "never passes through the wall")
	# open-field miss
	var sim2: MatchSim = await make_sim()
	var b2: FighterBody = sim2.add_fighter("bruno", 0, 0, "b2")
	place(b2, Vector3(-20, 0.002, 0), S)
	await hold(sim2, {b2.entity_id: frame(S)}, 3)
	await _cast(sim2, b2, WR.BTN_Q, {})
	var total: int = 1 + await _action_ticks(sim2, b2, {})
	var expect: int = WR.secs_to_ticks(0.25) + WR.secs_to_ticks(0.70) + WR.secs_to_ticks(0.55)
	assert_true(absi(total - expect) <= 3, "miss: windup+charge+0.55 s recovery (%d vs %d)" % [total, expect])


func test_bruno_bark_interrupts_exposed_no_damage_respects_walls() -> void:
	var sim: MatchSim = await make_sim()
	var b: FighterBody = sim.add_fighter("bruno", 0, 0, "b")
	var h: FighterBody = sim.add_fighter("hops", 1, 0, "h")      # in startup of a heavy → exposed
	var s: FighterBody = sim.add_fighter("scrap", 1, 1, "s")     # idle → pushed only
	var hid: FighterBody = sim.add_fighter("nyx", 1, 2, "x")     # behind wall_test → unaffected
	place(b, Vector3(0, 0.002, 9.0), S)
	place(h, Vector3(-1.0, 0.002, 11.2), N)
	place(s, Vector3(1.2, 0.002, 11.4), N)
	place(hid, Vector3(0, 0.002, 13.6), N)
	var idle := {b.entity_id: frame(S), h.entity_id: frame(N), s.entity_id: frame(N), hid.entity_id: frame(N)}
	await hold(sim, idle, 3)
	var d: Dictionary = idle.duplicate()
	d[b.entity_id] = frame(S, WR.BTN_E)
	var ev: Array[Dictionary] = await run(sim, 1, func(_i: int) -> Dictionary: return d)
	# Hops starts a heavy so she is in startup when the bark fires at 0.35 s
	ev.append_array(await hold(sim, idle, 8))
	var d2: Dictionary = idle.duplicate()
	d2[h.entity_id] = frame(N, WR.BTN_HEAVY)
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return d2))
	ev.append_array(await hold(sim, idle, 40))
	var bark: Dictionary = _first(ev, "bark")
	assert_false(bark.is_empty(), "bark fired")
	var aff: Dictionary = {}
	for a in bark.get("affected", []):
		aff[int(a[0])] = String(a[1])
	assert_eq(aff.get(h.entity_id, ""), "interrupted", "exposed startup interrupted")
	assert_eq(aff.get(s.entity_id, ""), "pushed", "idle enemy only pushed")
	assert_false(aff.has(hid.entity_id), "no effect through the wall")
	assert_eq(h.st.health, 230.0, "no damage")
	assert_eq(s.st.health, 260.0, "no damage")
	assert_true(h.st.has_cr(sim.tick), "interrupt grants CR")


func test_bruno_bark_respects_control_resistance() -> void:
	var sim: MatchSim = await make_sim()
	var b: FighterBody = sim.add_fighter("bruno", 0, 0, "b")
	var h: FighterBody = sim.add_fighter("hops", 1, 0, "h")
	place(b, Vector3(0, 0.002, 0), S)
	place(h, Vector3(0, 0.002, 2.0), N)
	await hold(sim, {b.entity_id: frame(S), h.entity_id: frame(N)}, 3)
	h.st.cr_until = sim.tick + 600
	await _cast(sim, b, WR.BTN_E, {h.entity_id: frame(N)})
	await hold(sim, {b.entity_id: frame(S), h.entity_id: frame(N)}, 9)
	var ev: Array[Dictionary] = await _cast(sim, h, WR.BTN_HEAVY, {b.entity_id: frame(S)})
	ev.append_array(await hold(sim, {b.entity_id: frame(S), h.entity_id: frame(N)}, 30))
	var bark: Dictionary = _first(ev, "bark")
	var status: String = ""
	for a in bark.get("affected", []):
		if int(a[0]) == h.entity_id:
			status = String(a[1])
	assert_eq(status, "pushed", "CR target is not interrupted, only pushed")


func test_bruno_stand_firm_front_back_no_attacks_cooldown_on_exit() -> void:
	var sim: MatchSim = await make_sim()
	var b: FighterBody = sim.add_fighter("bruno", 0, 0, "b")
	var nyx: FighterBody = sim.add_fighter("nyx", 1, 0, "n")
	var vex: FighterBody = sim.add_fighter("vex", 1, 1, "v")
	place(b, Vector3(0, 0.002, 0), S)
	place(nyx, Vector3(1.0, 0.002, 1.0), N)     # front-right, ~45° (outside basic 60°? inside 90°)
	place(vex, Vector3(0, 0.002, -1.3), S)      # behind
	var idle := {b.entity_id: frame(S), nyx.entity_id: frame(N + PI / 4.0), vex.entity_id: frame(S)}
	await hold(sim, idle, 3)
	var ev: Array[Dictionary] = await _cast(sim, b, WR.BTN_R, {nyx.entity_id: frame(N + PI / 4.0), vex.entity_id: frame(S)})
	ev.append_array(await hold(sim, idle, 12))
	assert_eq(b.st.act.id if b.st.act != null else "", "bruno_stand_firm", "stance active")
	# attacks are ignored while planted
	ev.append_array(await _cast(sim, b, WR.BTN_LIGHT, {nyx.entity_id: frame(N + PI / 4.0), vex.entity_id: frame(S)}))
	assert_eq(count(ev, "action", {"e": b.entity_id, "a": "bruno_light_s"}), 0, "cannot attack freely")
	# frontal heavy (45° off-axis, outside the normal ±60° guard? no — inside ±90°) is blocked at half stamina
	var st0: float = b.st.stamina
	var d: Dictionary = idle.duplicate()
	d[nyx.entity_id] = frame(N + PI / 4.0, WR.BTN_HEAVY)
	ev.append_array(await run(sim, 1, func(_i: int) -> Dictionary: return d))
	ev.append_array(await hold(sim, idle, 40))
	assert_eq(count(ev, "block", {"t": b.entity_id}), 1, "frontal heavy blocked by the wider guard")
	assert_near(st0 - b.st.stamina, 14.0, 0.01, "blocked heavy costs half (28 × 0.5)")
	assert_eq(count(ev, "hit", {"t": b.entity_id}), 0, "no damage from the front")
	# back remains open: a light from behind lands (and flinches Bruno out of the stance)
	var d2: Dictionary = idle.duplicate()
	d2[vex.entity_id] = frame(S, WR.BTN_LIGHT)
	var ev_b: Array[Dictionary] = await run(sim, 1, func(_i: int) -> Dictionary: return d2)
	ev_b.append_array(await hold(sim, idle, 20))
	assert_eq(count(ev_b, "hit", {"t": b.entity_id, "a": vex.entity_id}), 1, "back is open")
	# re-enter to test exit + cooldown
	b.st.cd_ready["r"] = 0
	b.st.stamina = 100.0
	await _cast(sim, b, WR.BTN_R, {nyx.entity_id: frame(N + PI / 4.0), vex.entity_id: frame(S)})
	await hold(sim, idle, 30)
	# exit with R → cooldown starts at exit
	ev.append_array(await _cast(sim, b, WR.BTN_R, idle))
	await hold(sim, idle, 20)
	assert_true(b.st.act == null, "stance ended")
	assert_true(int(b.st.cd_ready["r"]) > sim.tick + WR.secs_to_ticks(13.0), "14 s cooldown starts on exit")
