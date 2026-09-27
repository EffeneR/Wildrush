extends WRTest
## G10: a complete offline bot match on Briarport (10 server-side bots, same rules as humans).
## Verifies completion, all three zones contested/controlled, combat, skills, and no stuck bots.


func test_full_bot_match_all_zones() -> void:
	var lay: ArenaLayout = ArenaLayout.load_file()
	var sim := MatchSim.new()
	sim.name = "Sim"
	add_child(sim)
	sim.setup(lay, WR.MODE_OFFLINE, 4242, true)
	var picks: Array = [["nyx", "bruno", "vex", "hops", "scrap"], ["scrap", "hops", "vex", "bruno", "nyx"]]
	for team in range(2):
		for slot in range(5):
			var f: FighterBody = sim.add_fighter(picks[team][slot], team, slot, "BOT", true)
			var b := BotAI.new()
			b.difficulty = ["easy", "normal", "hard", "normal", "hard"][slot]
			sim.bot_brains[f.entity_id] = b
	var waited: int = 0
	while not sim.nav_ready() and waited < 300:
		await get_tree().physics_frame
		waited += 1
	assert_true(sim.nav_ready(), "navigation ready")
	sim.begin_live()
	var controlled: Dictionary = {}
	var kinds: Dictionary = {}
	var skills: Dictionary = {}
	var stuck_max: Dictionary = {}
	var last_pos: Dictionary = {}
	var still_since: Dictionary = {}
	var t0: int = Time.get_ticks_msec()
	var ticks: int = 0
	while not sim.rules.finished and ticks < 480 * 60 + 60 * 60:
		await get_tree().physics_frame
		var ev: Array[Dictionary] = sim.step_tick()
		ticks += 1
		for e in ev:
			var t: String = String(e["type"])
			kinds[t] = int(kinds.get(t, 0)) + 1
			if t == "zone_state" and int(e["state"]) == WR.ZoneState.CONTROLLED:
				controlled[String(e["zone"])] = true
			if t == "action":
				var aid: String = String(e["a"])
				for fid in WR.FIGHTER_IDS:
					var d: FighterDef = Tuning.fighter(fid)
					for slot in ["q", "e", "r"]:
						if String(d.skill_ids.get(slot, "")) == aid:
							skills[aid] = int(skills.get(aid, 0)) + 1
		if ticks % 30 == 0:
			for f in sim.fighters:
				if not f.st.alive:
					still_since.erase(f.entity_id)
					continue
				var p: Vector3 = f.global_position
				var mode: String = String((sim.bot_brains[f.entity_id] as BotAI).intent.get("mode", ""))
				var travelling: bool = mode in ["objective", "rotate", "support", "retreat"]
				if not travelling or not last_pos.has(f.entity_id) or (last_pos[f.entity_id] as Vector3).distance_to(p) > 0.5:
					last_pos[f.entity_id] = p
					still_since[f.entity_id] = ticks
				else:
					var zc: Vector3 = lay.zone_center(sim.rules.active_zone)
					var in_zone: bool = Vector2(p.x - zc.x, p.z - zc.z).length() < 9.5
					if not in_zone:
						stuck_max[f.entity_id] = maxi(int(stuck_max.get(f.entity_id, 0)), ticks - int(still_since.get(f.entity_id, ticks)))
	var ms: int = Time.get_ticks_msec() - t0
	print("bot match: ticks=%d wall_ms=%d score=%s winner=%d reason=%s" % [ticks, ms, str(sim.rules.scores), sim.rules.winner, sim.rules.end_reason])
	print("event counts: ", kinds)
	print("zones controlled: ", controlled.keys(), " skills used: ", skills)
	print("max stuck ticks outside zone: ", stuck_max)
	assert_true(sim.rules.finished, "match completed")
	assert_eq(int(kinds.get("match_end", 0)), 1, "exactly one match_end")
	for z in ["A", "B", "C"]:
		assert_true(controlled.has(z), "zone %s was controlled at some point" % z)
	assert_gt(float(kinds.get("hit", 0)), 20.0, "bots fought")
	assert_gt(float(kinds.get("ko", 0)), 2.0, "knockouts happened")
	assert_gt(float(kinds.get("respawn", 0)), 2.0, "respawns happened")
	assert_gt(float(skills.size()), 9.0, "most of the 15 skills were used by bots (%d)" % skills.size())
	for eid in stuck_max.keys():
		assert_lt(float(stuck_max[eid]), 60.0 * 20.0, "bot %d never stuck > 20 s outside the zone" % eid)
	sim.queue_free()
