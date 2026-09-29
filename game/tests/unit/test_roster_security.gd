extends WRTest
## G8 (unit level): server-authoritative selection — races, ownership, lock rules, swaps.


func _roster_two_same_team() -> MatchRoster:
	var r := MatchRoster.new()
	r.add_player(1, "A", 0)
	r.add_player(2, "B", 0)
	r.add_player(3, "C", 1)
	return r


func test_simultaneous_same_species_picks_resolve_to_one_owner() -> void:
	var r := _roster_two_same_team()
	# both requests arrive in the same server tick: processed sequentially, first wins
	assert_eq(r.pick(1, "nyx"), "", "first pick granted")
	assert_eq(r.pick(2, "nyx"), "taken", "second identical pick refused")
	assert_eq(r.taken_by(0, "nyx"), 1, "exactly one owner")
	assert_eq(r.pick(3, "nyx"), "", "the other team may field the same species")
	assert_eq(r.pick(1, "vex"), "", "re-pick releases the old species")
	assert_eq(r.pick(2, "nyx"), "", "released species can be picked")


func test_locked_players_cannot_change_or_be_swapped() -> void:
	var r := _roster_two_same_team()
	assert_eq(r.lock(1), "no_pick", "cannot lock without a pick")
	r.pick(1, "bruno")
	assert_eq(r.lock(1), "")
	assert_eq(r.pick(1, "hops"), "locked", "locked pick is final")
	r.pick(2, "scrap")
	var slot_a: int = int(r.players[1]["slot"])
	assert_eq(r.request_swap(2, slot_a), "target_locked", "cannot swap with a locked teammate")


func test_swaps_need_the_named_target_and_same_team() -> void:
	var r := _roster_two_same_team()
	r.pick(1, "nyx")
	r.pick(2, "vex")
	var slot_b: int = int(r.players[2]["slot"])
	assert_eq(r.request_swap(1, slot_b), "")
	assert_eq(r.answer_swap(3, 1, true), "no_request", "a third party cannot answer someone else's swap")
	assert_eq(r.answer_swap(2, 1, true), "", "target accepts")
	assert_eq(String(r.players[1]["fighter"]), "vex")
	assert_eq(String(r.players[2]["fighter"]), "nyx")
	assert_eq(r.answer_swap(2, 1, true), "no_request", "an answered request cannot be replayed")


func test_unknown_players_and_species_rejected() -> void:
	var r := _roster_two_same_team()
	assert_eq(r.pick(99, "nyx"), "unknown_player")
	assert_eq(r.pick(1, "wolf"), "invalid")
	assert_eq(r.lock(99), "unknown_player")


func test_auto_assign_never_duplicates_within_a_team() -> void:
	var r := MatchRoster.new()
	for i in range(10):
		r.add_player(i + 1, "P%d" % i, i % 2)
	r.pick(1, "nyx")
	r.pick(3, "nyx")   # same team as pid 1 -> refused, stays unpicked
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	r.auto_assign(rng)
	for team in range(2):
		var seen: Dictionary = {}
		for p in r.team_players(team):
			var f: String = String(p["fighter"])
			assert_true(f != "", "everyone has a fighter after auto-assign")
			assert_false(seen.has(f), "no duplicate species on team %d" % team)
			seen[f] = true
