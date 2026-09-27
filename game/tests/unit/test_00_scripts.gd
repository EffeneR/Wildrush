extends WRTest
## G1: every script in the project parses and every tuning file loads.


func _collect(path: String, out: Array[String]) -> void:
	var d := DirAccess.open(path)
	if d == null:
		return
	for f in d.get_files():
		if f.ends_with(".gd"):
			out.append(path.path_join(f))
	for sub in d.get_directories():
		if sub.begins_with("."):
			continue
		_collect(path.path_join(sub), out)


func test_all_scripts_parse() -> void:
	var files: Array[String] = []
	_collect("res://src", files)
	_collect("res://scenes", files)
	assert_gt(files.size(), 20, "found project scripts")
	for p in files:
		var s: Resource = load(p)
		assert_true(s != null and s is GDScript and (s as GDScript).can_instantiate(), "script loads: " + p)


func test_tuning_loaded_for_all_fighters() -> void:
	assert_eq(Tuning.load_errors.size(), 0, "no tuning load errors: " + str(Tuning.load_errors))
	for fid in WR.FIGHTER_IDS:
		var d: FighterDef = Tuning.fighter(fid)
		assert_true(d != null, "fighter def " + fid)
		if d == null:
			continue
		for slot in ["q", "e", "r"]:
			var s: ActionDef = d.skill(slot)
			assert_true(s != null, "%s skill %s exists" % [fid, slot])
			if s != null:
				assert_gt(s.cooldown_ticks, 0, "%s %s has a cooldown" % [fid, s.id])
				assert_true(s.desc.length() > 20, "%s %s has a description" % [fid, s.id])
				assert_true(Behaviors.names().has(s.behavior), "%s %s behaviour registered" % [fid, s.id])
		for k in ["s", "l", "r", "air"]:
			assert_true(d.action(String(d.light_ids.get(k, ""))) != null, "%s light %s" % [fid, k])
		assert_true(d.action(d.heavy_id) != null, fid + " heavy")
		assert_true(d.passive_id != "" and d.passive_desc != "", fid + " passive defined")


func test_spec_vitals() -> void:
	var expect := {"nyx": [220.0, 7.2, 1.70], "bruno": [280.0, 6.6, 1.77], "vex": [220.0, 7.0, 1.73], "hops": [230.0, 7.6, 1.67], "scrap": [260.0, 6.8, 1.63]}
	for fid in expect.keys():
		var d: FighterDef = Tuning.fighter(fid)
		assert_eq(d.health, expect[fid][0], fid + " health")
		assert_eq(d.move_speed, expect[fid][1], fid + " speed")
		assert_eq(d.height, expect[fid][2], fid + " height")
	assert_eq(Tuning.stamina_max, 100.0)
	assert_eq(Tuning.dodge_stamina, 25.0)
	assert_eq(Tuning.fighter("nyx").action("nyx_heavy").stamina, 15.0, "heavy costs 15")
	assert_near(Tuning.stamina_regen_per_tick * 60.0, 24.0, 1e-6, "stamina regen 24/s")
	assert_eq(Tuning.stamina_regen_delay, 54, "0.9 s regen delay")
	assert_near(Tuning.hp_regen_per_tick * 60.0, 18.0, 1e-6, "health regen 18/s")
	assert_eq(Tuning.hp_regen_delay, 360, "6 s health regen delay")


func test_no_guaranteed_light_chains() -> void:
	## D-010: light hit-stun ends >= 3 ticks before the next chained strike can become active,
	## for every fighter and every pair of directional lights, even for a hit on the last active tick.
	for fid in WR.FIGHTER_IDS:
		var d: FighterDef = Tuning.fighter(fid)
		for k1 in ["s", "l", "r"]:
			var a1: ActionDef = d.action(String(d.light_ids[k1]))
			var h1: HitDef = a1.hits[0]
			var chain_from: int = -1
			for c in a1.cancels:
				if (c[2] as PackedStringArray).has("light"):
					chain_from = int(c[0])
			assert_true(chain_from > 0, "%s %s has a chain window" % [fid, a1.id])
			for k2 in ["s", "l", "r"]:
				var a2: ActionDef = d.action(String(d.light_ids[k2]))
				var next_active: int = chain_from + a2.hits[0].t0
				var worst_hit: int = h1.t1 - 1
				var stun_end: int = worst_hit + h1.stun_ticks
				assert_true(next_active - stun_end >= 3, "%s %s→%s: stun ends %d ticks before next active (need ≥3)" % [fid, a1.id, a2.id, next_active - stun_end])
