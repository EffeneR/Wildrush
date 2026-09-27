extends Node
## Autoload "Profile": OFFLINE profile, cosmetics, mastery and local match history
## (user://profile_offline.json). Kept strictly separate from authenticated online records,
## which live in the control service (spec §11). Offline data can never produce ranked results.

signal profile_changed

const PATH: String = "user://profile_offline.json"
const LEVEL_XP: Array[int] = [0, 300, 800, 1500, 2400, 3500, 4800, 6300, 8000, 10000]
const PALETTE_UNLOCK: Dictionary = {"default": 1, "dusk": 3, "ember": 5, "frost": 7}
const BADGE_UNLOCK: Dictionary = {"initiate": 2, "adept": 4, "veteran": 6, "master": 8}
const HISTORY_MAX: int = 60

var data: Dictionary = {}


func _ready() -> void:
	load_profile()


func _default() -> Dictionary:
	var fighters: Dictionary = {}
	for fid in WR.FIGHTER_IDS:
		fighters[fid] = {"xp": 0, "selected_palette": "default"}
	return {"version": 1, "display_name": "Player", "selected_badge": "", "fighters": fighters, "history": [],
		"totals": {"matches": 0, "wins": 0}}


func load_profile() -> void:
	data = _default()
	if not FileAccess.file_exists(PATH):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_warning("Profile: corrupt file ignored")
		return
	var p: Dictionary = parsed
	data["display_name"] = String(p.get("display_name", "Player")).substr(0, 20)
	data["selected_badge"] = String(p.get("selected_badge", ""))
	for fid in WR.FIGHTER_IDS:
		var fd: Dictionary = p.get("fighters", {}).get(fid, {})
		data["fighters"][fid]["xp"] = maxi(0, int(fd.get("xp", 0)))
		data["fighters"][fid]["selected_palette"] = String(fd.get("selected_palette", "default"))
	data["history"] = (p.get("history", []) as Array).slice(0, HISTORY_MAX)
	data["totals"] = p.get("totals", {"matches": 0, "wins": 0})


func save_profile() -> void:
	var f := FileAccess.open(PATH, FileAccess.WRITE)
	if f == null:
		push_warning("Profile: cannot write %s" % PATH)
		return
	f.store_string(JSON.stringify(data, " "))
	f.close()


static func level_for_xp(xp: int) -> int:
	var lvl: int = 1
	for i in range(LEVEL_XP.size()):
		if xp >= LEVEL_XP[i]:
			lvl = i + 1
	return mini(lvl, LEVEL_XP.size())


func fighter_xp(fid: String) -> int:
	return int(data["fighters"].get(fid, {}).get("xp", 0))


func fighter_level(fid: String) -> int:
	return level_for_xp(fighter_xp(fid))


func unlocked_palettes(fid: String) -> Array[String]:
	var lvl: int = fighter_level(fid)
	var out: Array[String] = []
	for p in PALETTE_UNLOCK.keys():
		if lvl >= int(PALETTE_UNLOCK[p]):
			out.append(String(p))
	return out


func badges() -> Array[String]:
	var out: Array[String] = []
	for fid in WR.FIGHTER_IDS:
		var lvl: int = fighter_level(fid)
		for b in BADGE_UNLOCK.keys():
			if lvl >= int(BADGE_UNLOCK[b]):
				out.append("%s_%s" % [fid, b])
	if int(data["totals"].get("matches", 0)) > 0:
		out.append("pack_debut")
	return out


func selected_palette(fid: String) -> String:
	var p: String = String(data["fighters"].get(fid, {}).get("selected_palette", "default"))
	return p if unlocked_palettes(fid).has(p) else "default"


func select_palette(fid: String, palette: String) -> bool:
	if not unlocked_palettes(fid).has(palette):
		return false
	data["fighters"][fid]["selected_palette"] = palette
	save_profile()
	profile_changed.emit()
	return true


func select_badge(badge: String) -> bool:
	if badge != "" and not badges().has(badge):
		return false
	data["selected_badge"] = badge
	save_profile()
	profile_changed.emit()
	return true


static func xp_for(result_row: Dictionary, won: bool, mode_mult: float = 1.0) -> int:
	## Same formula as the service (docs/API_CONTRACT.md: mastery).
	var xp: int = 100 + (50 if won else 0)
	xp += mini(200, 2 * int(result_row.get("control_seconds", 0)))
	xp += mini(100, 10 * int(result_row.get("kos", 0)))
	return int(round(xp * mode_mult))


func award_offline_match(result: Dictionary, my_entity: int) -> Dictionary:
	## Returns {"fighter", "xp_gained", "level_before", "level_after", "unlocks": [...]}.
	var row: Dictionary = {}
	for r in result.get("players", []):
		if int(r.get("entity", -1)) == my_entity:
			row = r
	if row.is_empty():
		return {}
	var fid: String = String(row["fighter"])
	var won: bool = int(row["team"]) == int(result.get("winner_team", -1))
	var before_lvl: int = fighter_level(fid)
	var before_pal: Array[String] = unlocked_palettes(fid)
	var before_badges: Array[String] = badges()
	var gained: int = xp_for(row, won, 1.0)
	data["fighters"][fid]["xp"] = fighter_xp(fid) + gained
	data["totals"]["matches"] = int(data["totals"].get("matches", 0)) + 1
	if won:
		data["totals"]["wins"] = int(data["totals"].get("wins", 0)) + 1
	var entry := {"when": Time.get_datetime_string_from_system(true), "mode": String(result.get("mode", "offline")),
		"fighter": fid, "won": won, "score": result.get("score", [0, 0]), "team": int(row["team"]),
		"kos": int(row.get("kos", 0)), "xp": gained, "replay": String(result.get("replay_file", ""))}
	(data["history"] as Array).push_front(entry)
	data["history"] = (data["history"] as Array).slice(0, HISTORY_MAX)
	save_profile()
	profile_changed.emit()
	var unlocks: Array = []
	for p in unlocked_palettes(fid):
		if not before_pal.has(p):
			unlocks.append({"kind": "palette", "fighter": fid, "id": p})
	for b in badges():
		if not before_badges.has(b):
			unlocks.append({"kind": "badge", "id": b})
	return {"fighter": fid, "xp_gained": gained, "level_before": before_lvl, "level_after": fighter_level(fid), "unlocks": unlocks}
