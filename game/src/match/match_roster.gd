class_name MatchRoster
extends RefCounted
## Server-controlled teams, slots and species reservations (spec §3, §11). Each team has
## exactly one of each species. Requests are processed sequentially by the server, so
## simultaneous selections can never produce duplicates. Swaps only before lock-in.

var players: Dictionary = {}      # pid -> Dictionary (see _new_player)
var swap_requests: Dictionary = {} # requester pid -> target pid
var allow_bots: bool = false
var bot_difficulty: String = "normal"


func _new_player(pid: int, name: String, team: int, slot: int, account: String, bot: bool) -> Dictionary:
	return {"pid": pid, "name": name, "team": team, "slot": slot, "fighter": "", "locked": false, "ready": false,
		"bot": bot, "account": account, "connected": true, "rematch": false, "palette": "default"}


func team_players(team: int) -> Array:
	var out: Array = []
	for p in players.values():
		if int(p["team"]) == team:
			out.append(p)
	out.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return int(a["slot"]) < int(b["slot"]))
	return out


func humans() -> Array:
	return players.values().filter(func(p: Dictionary) -> bool: return not bool(p["bot"]))


func free_slot(team: int) -> int:
	var used: Dictionary = {}
	for p in team_players(team):
		used[int(p["slot"])] = true
	for s in range(WR.TEAM_SIZE):
		if not used.has(s):
			return s
	return -1


func add_player(pid: int, name: String, team_pref: int = -1, account: String = "", bot: bool = false) -> Dictionary:
	var team: int = team_pref
	if team < 0 or free_slot(team) < 0:
		var c0: int = team_players(0).size()
		var c1: int = team_players(1).size()
		team = 0 if c0 <= c1 else 1
	var slot: int = free_slot(team)
	if slot < 0:
		team = 1 - team
		slot = free_slot(team)
	if slot < 0:
		return {}
	var p: Dictionary = _new_player(pid, name, team, slot, account, bot)
	players[pid] = p
	return p


func remove_player(pid: int) -> void:
	players.erase(pid)
	swap_requests.erase(pid)
	for k in swap_requests.keys():
		if int(swap_requests[k]) == pid:
			swap_requests.erase(k)


func taken_by(team: int, fighter: String) -> int:
	for p in team_players(team):
		if String(p["fighter"]) == fighter:
			return int(p["pid"])
	return -1


func pick(pid: int, fighter: String) -> String:
	if not players.has(pid):
		return "unknown_player"
	if not WR.FIGHTER_IDS.has(fighter):
		return "invalid"
	var p: Dictionary = players[pid]
	if bool(p["locked"]):
		return "locked"
	var holder: int = taken_by(int(p["team"]), fighter)
	if holder >= 0 and holder != pid:
		return "taken"
	p["fighter"] = fighter
	return ""


func lock(pid: int) -> String:
	if not players.has(pid):
		return "unknown_player"
	var p: Dictionary = players[pid]
	if String(p["fighter"]) == "":
		return "no_pick"
	p["locked"] = true
	return ""


func request_swap(pid: int, target_slot: int) -> String:
	## Ask a teammate to swap species (both must be un-locked).
	if not players.has(pid):
		return "unknown_player"
	var p: Dictionary = players[pid]
	if bool(p["locked"]):
		return "locked"
	for q in team_players(int(p["team"])):
		if int(q["slot"]) == target_slot and int(q["pid"]) != pid:
			if bool(q["locked"]) or bool(q["bot"]):
				return "target_locked"
			swap_requests[pid] = int(q["pid"])
			return ""
	return "no_target"


func answer_swap(pid: int, from_pid: int, accept: bool) -> String:
	if int(swap_requests.get(from_pid, -1)) != pid:
		return "no_request"
	swap_requests.erase(from_pid)
	if not accept:
		return "declined"
	var a: Dictionary = players.get(from_pid, {})
	var b: Dictionary = players.get(pid, {})
	if a.is_empty() or b.is_empty() or bool(a["locked"]) or bool(b["locked"]) or int(a["team"]) != int(b["team"]):
		return "invalid"
	var fa: String = String(a["fighter"])
	a["fighter"] = String(b["fighter"])
	b["fighter"] = fa
	return ""


func all_humans_locked() -> bool:
	for p in humans():
		if bool(p["connected"]) and not bool(p["locked"]):
			return false
	return true


func auto_assign(rng: RandomNumberGenerator) -> void:
	## Timer expiry: every unlocked player keeps a valid pick or receives a random free species.
	for team in range(2):
		for p in team_players(team):
			if String(p["fighter"]) == "":
				var free: Array = _free_species(team)
				if not free.is_empty():
					p["fighter"] = free[rng.randi_range(0, free.size() - 1)]
			p["locked"] = true


func _free_species(team: int) -> Array:
	var free: Array = []
	for fid in WR.FIGHTER_IDS:
		if taken_by(team, fid) < 0:
			free.append(fid)
	return free


func fill_bots(rng: RandomNumberGenerator, next_pid_fn: Callable) -> int:
	## Adds clearly labelled bots to empty slots (only where the mode allows it).
	if not allow_bots:
		return 0
	var added: int = 0
	for team in range(2):
		while free_slot(team) >= 0:
			var free: Array = _free_species(team)
			var fid: String = String(free[rng.randi_range(0, free.size() - 1)]) if not free.is_empty() else "nyx"
			var pid: int = int(next_pid_fn.call())
			var p: Dictionary = add_player(pid, "BOT " + Tuning.fighter(fid).display_name, team, "", true)
			if p.is_empty():
				break
			p["fighter"] = fid
			p["locked"] = true
			p["ready"] = true
			added += 1
	return added


func set_team(pid: int, team: int) -> String:
	if not players.has(pid) or team < 0 or team > 1:
		return "invalid"
	var p: Dictionary = players[pid]
	if int(p["team"]) == team:
		return ""
	var slot: int = free_slot(team)
	if slot < 0:
		return "team_full"
	p["team"] = team
	p["slot"] = slot
	if taken_by(team, String(p["fighter"])) >= 0:
		p["fighter"] = ""
	p["locked"] = false
	return ""


func reset_for_rematch() -> void:
	for p in players.values():
		if not bool(p["bot"]):
			p["locked"] = false
			p["rematch"] = false
	swap_requests.clear()


func state() -> Dictionary:
	var teams: Array = [[], []]
	for team in range(2):
		for p in team_players(team):
			teams[team].append({"pid": p["pid"], "name": p["name"], "slot": p["slot"], "fighter": p["fighter"],
				"locked": p["locked"], "ready": p["ready"], "bot": p["bot"], "connected": p["connected"]})
	var swaps: Array = []
	for k in swap_requests.keys():
		swaps.append([k, swap_requests[k]])
	return {"teams": teams, "swaps": swaps, "allow_bots": allow_bots, "bot_difficulty": bot_difficulty}
