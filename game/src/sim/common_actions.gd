class_name CommonActions
extends RefCounted
## Actions shared by every fighter that are not in the per-fighter JSON (dodge, perch climb).

static var _dodge: ActionDef = null
static var _perch: ActionDef = null


static func dodge() -> ActionDef:
	if _dodge == null:
		var a := ActionDef.new()
		a.id = "dodge"
		a.kind = "dodge"
		a.behavior = "dodge"
		a.display_name = "Dodge"
		a.stamina = 0.0   # charged by the behaviour (shared tuning)
		a.total_ticks = Tuning.dodge_ticks
		a.turn_table = [[0, 0.0]]
		_dodge = a
	return _dodge


static func perch() -> ActionDef:
	if _perch == null:
		var a := ActionDef.new()
		a.id = "perch_climb"
		a.kind = "move"
		a.behavior = "perch"
		a.display_name = "Perch"
		a.clip = "perch_climb"
		a.turn_table = [[0, 0.0]]
		_perch = a
	return _perch


static func resolve(def: FighterDef, action_id: String) -> ActionDef:
	if action_id == "dodge":
		return dodge()
	if action_id == "perch_climb":
		return perch()
	return def.action(action_id)
