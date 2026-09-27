class_name TurfShiftRules
extends RefCounted
## Authoritative Turf Shift rules (spec §4, D-005, D-006). Pure logic, no nodes.
## The simulation calls, once per tick (D-005 order):
##   advance_clock()            -- step 2
##   evaluate(presence)         -- steps 9..12 with presence[team] = eligible occupants of the active zone
## Every call returns an Array of event Dictionaries.

var regulation_ticks: int = 480 * 60
var score_limit: int = 250
var rotation_ticks: int = 60 * 60
var reveal_before_ticks: int = 15 * 60
var order: Array[String] = ["B", "A", "C"]
var score_warnings: Array[int] = [200, 230, 245]

var phase: int = WR.Phase.WAITING
var match_tick: int = 0            # ticks of match clock since LIVE started
var scores: Array[int] = [0, 0]
var control_ticks: Array[int] = [0, 0]
var period_index: int = 0          # rotation period count since LIVE
var active_zone: String = ""
var next_zone: String = ""
var next_revealed: bool = false
var zone_state: int = WR.ZoneState.NEUTRAL
var controlling_team: int = -1
var winner: int = -1
var end_reason: String = ""
var finished: bool = false
var sudden_death: bool = false
var warnings_sent: Array = [{}, {}]
var control_seconds_total: Array[int] = [0, 0]


func configure(r: Dictionary) -> void:
	if r.is_empty():
		return
	regulation_ticks = WR.secs_to_ticks(float(r.get("regulation_s", 480)))
	score_limit = int(r.get("score_limit", 250))
	rotation_ticks = WR.secs_to_ticks(float(r.get("rotation_period_s", 60)))
	reveal_before_ticks = WR.secs_to_ticks(float(r.get("reveal_before_s", 15)))
	order.clear()
	for z in r.get("zone_order", ["B", "A", "C"]):
		order.append(String(z))
	score_warnings.clear()
	for w in r.get("score_warning_at", [200, 230, 245]):
		score_warnings.append(int(w))


func start_live() -> Array[Dictionary]:
	phase = WR.Phase.LIVE
	match_tick = 0
	scores = [0, 0]
	control_ticks = [0, 0]
	period_index = 0
	active_zone = order[0]
	next_zone = order[1 % order.size()]
	next_revealed = false
	zone_state = WR.ZoneState.NEUTRAL
	controlling_team = -1
	winner = -1
	finished = false
	sudden_death = false
	warnings_sent = [{}, {}]
	return [{"type": "zone_activated", "zone": active_zone, "tick": match_tick}]


func is_running() -> bool:
	return phase == WR.Phase.LIVE or phase == WR.Phase.SUDDEN_DEATH


func advance_clock() -> void:
	if is_running():
		match_tick += 1


func seconds_remaining() -> float:
	return maxf(0.0, float(regulation_ticks - match_tick) / WR.TICK_RATE)


func ticks_to_rotation() -> int:
	## Countdown to the next rotation; in the final period this is the regulation end.
	if sudden_death:
		return 0
	var next_rot: int = (period_index + 1) * rotation_ticks
	return maxi(0, mini(next_rot, regulation_ticks) - match_tick)


func is_final_period() -> bool:
	return (period_index + 1) * rotation_ticks >= regulation_ticks


func evaluate(presence: Array) -> Array[Dictionary]:
	var events: Array[Dictionary] = []
	if not is_running() or finished:
		return events
	var p0: int = int(presence[0])
	var p1: int = int(presence[1])
	# --- step 9: zone state
	var new_state: int
	var new_ctrl: int = -1
	if p0 > 0 and p1 > 0:
		new_state = WR.ZoneState.CONTESTED
	elif p0 > 0:
		new_state = WR.ZoneState.CONTROLLED
		new_ctrl = 0
	elif p1 > 0:
		new_state = WR.ZoneState.CONTROLLED
		new_ctrl = 1
	else:
		new_state = WR.ZoneState.NEUTRAL
	if new_state != zone_state or new_ctrl != controlling_team:
		zone_state = new_state
		controlling_team = new_ctrl
		events.append({"type": "zone_state", "zone": active_zone, "state": zone_state, "team": controlling_team, "tick": match_tick})
	# --- step 10: scoring (1 point per full second of continuous sole control)
	if zone_state == WR.ZoneState.CONTROLLED:
		var t: int = controlling_team
		control_ticks[1 - t] = 0
		control_ticks[t] += 1
		if control_ticks[t] >= WR.TICK_RATE:
			control_ticks[t] -= WR.TICK_RATE
			scores[t] += 1
			control_seconds_total[t] += 1
			events.append({"type": "score", "team": t, "score": scores[t], "tick": match_tick})
			for w in score_warnings:
				if scores[t] == w and not warnings_sent[t].has(w):
					warnings_sent[t][w] = true
					events.append({"type": "score_warning", "team": t, "at": w, "tick": match_tick})
			if sudden_death:
				_finish(t, "sudden_death", events)
				return events
			if scores[t] >= score_limit:
				_finish(t, "score_limit", events)
				return events
	else:
		control_ticks[0] = 0
		control_ticks[1] = 0
	# --- step 11: regulation end
	if phase == WR.Phase.LIVE and match_tick >= regulation_ticks:
		if scores[0] != scores[1]:
			_finish(0 if scores[0] > scores[1] else 1, "time", events)
			return events
		phase = WR.Phase.SUDDEN_DEATH
		sudden_death = true
		next_revealed = false
		next_zone = ""
		events.append({"type": "sudden_death", "zone": active_zone, "tick": match_tick})
		return events
	# --- step 12: reveal / rotation (frozen in sudden death)
	if sudden_death:
		return events
	var in_period: int = match_tick - period_index * rotation_ticks
	if not next_revealed and not is_final_period() and in_period >= rotation_ticks - reveal_before_ticks:
		next_revealed = true
		next_zone = order[(period_index + 1) % order.size()]
		events.append({"type": "zone_revealed", "zone": next_zone, "in_ticks": rotation_ticks - in_period, "tick": match_tick})
	if in_period >= rotation_ticks and match_tick < regulation_ticks:
		period_index += 1
		var old: String = active_zone
		active_zone = order[period_index % order.size()]
		next_zone = order[(period_index + 1) % order.size()]
		next_revealed = false
		control_ticks = [0, 0]
		zone_state = WR.ZoneState.NEUTRAL
		controlling_team = -1
		events.append({"type": "zone_rotated", "from": old, "zone": active_zone, "tick": match_tick})
	return events


func forfeit(losing_team: int, reason: String = "forfeit") -> Array[Dictionary]:
	var events: Array[Dictionary] = []
	if finished:
		return events
	_finish(1 - losing_team, reason, events)
	return events


func _finish(team: int, reason: String, events: Array[Dictionary]) -> void:
	if finished:
		return  # one-shot latch: completion happens exactly once
	finished = true
	winner = team
	end_reason = reason
	phase = WR.Phase.FINISHED
	events.append({"type": "match_end", "winner": team, "reason": reason, "score": [scores[0], scores[1]], "tick": match_tick})


func snapshot() -> Dictionary:
	return {
		"phase": phase, "tick": match_tick, "scores": [scores[0], scores[1]], "zone": active_zone,
		"next": next_zone if next_revealed else "", "state": zone_state, "ctrl": controlling_team,
		"rot": ticks_to_rotation(), "sd": sudden_death, "final": is_final_period(), "winner": winner,
		"reason": end_reason,
	}
