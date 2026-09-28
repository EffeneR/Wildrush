class_name MatchHost
extends Node
## Presentation-side view of a match (D-019). The match scene, HUD and VFX read only this
## interface; implementations: LocalMatchHost (offline/training, authoritative sim in-process),
## NetMatchHost (online client: prediction + interpolation), ReplayHost (recorded frames).

signal events(evs: Array)                 # presentation events (sim event dictionaries)
signal finished(info: Dictionary)         # {"result": Dictionary, ...}
signal chat(msg: Dictionary)
signal ping(msg: Dictionary)
signal notice(text: String)

var mode: String = ""
var local_entity: int = -1
var local_team: int = 0
var spectator: bool = false
var fighter_info: Dictionary = {}         # e -> {"team", "fighter", "name", "bot", "palette"}
var regulation_s: float = 480.0
var result_info: Dictionary = {}


func physics_step(_inp: InputFrame) -> void:
	pass


func views(_dt: float) -> Dictionary:
	## e -> {pos, yaw, vel, clip (name), ct, ctrl, flags, hp, st}
	return {}


func match_state() -> Dictionary:
	## {phase, match_tick, scores, zone, next, state, ctrl, rot (ticks), sd, final, countdown_s}
	return {}


func local_status() -> Dictionary:
	## {hp, hp_max, st, alive, respawn_s, protected, cr, cd: {q, e, r, dodge} (s left), cd_total}
	return {}


func roster() -> Array:
	## Scoreboard rows: {e, team, fighter, name, bot, kos, kod, dmg, ctrl_s, alive, respawn_s}
	return []


func send_chat(_text: String, _team: bool) -> void:
	pass


func send_ping(_pos: Vector3, _kind: String) -> void:
	pass


func leave() -> void:
	pass


func time_left_s(m: Dictionary) -> float:
	return maxf(0.0, regulation_s - float(m.get("tick", 0)) / WR.TICK_RATE)


func relation_of(e: int) -> String:
	if e == local_entity:
		return "self"
	var t: int = int(fighter_info.get(e, {}).get("team", -1))
	if spectator:
		return "ally" if t == 0 else "enemy"
	return "ally" if t == local_team else "enemy"


static func view_from_body(f: FighterBody, tick: int) -> Dictionary:
	var vs: Dictionary = Protocol.fighter_view_state(f, f.team, true, tick)
	vs["clip"] = Protocol.clip_name(int(vs["clip"]))
	return vs


static func status_from_body(f: FighterBody, tick: int) -> Dictionary:
	var cd: Dictionary = {}
	var total: Dictionary = {}
	for slot in ["q", "e", "r"]:
		var ad: ActionDef = f.def.skill(slot)
		cd[slot] = maxf(0.0, float(int(f.st.cd_ready.get(slot, 0)) - tick) / WR.TICK_RATE)
		total[slot] = ad.cooldown_s if ad != null else 1.0
	cd["dodge"] = maxf(0.0, float(int(f.st.cd_ready.get("dodge", 0)) - tick) / WR.TICK_RATE)
	total["dodge"] = float(Tuning.shared.get("dodge", {}).get("cooldown_s", 0.6))
	return {"hp": f.st.health, "hp_max": f.def.health, "st": f.st.stamina, "st_max": Tuning.stamina_max,
		"alive": f.st.alive, "respawn_s": maxf(0.0, float(f.st.respawn_at - tick) / WR.TICK_RATE) if not f.st.alive else 0.0,
		"protected": f.st.spawn_protected, "cr": f.st.has_cr(tick), "cd": cd, "cd_total": total,
		"guarding": f.st.guarding, "ctrl": f.st.ctrl, "last_hit_by": f.st.last_hit_by}
