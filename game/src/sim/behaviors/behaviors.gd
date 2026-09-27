class_name Behaviors
extends RefCounted
## Registry: behaviour name (ActionDef.behavior) -> stateless ActionBehavior instance.

static var _reg: Dictionary = {}


static func _ensure() -> void:
	if not _reg.is_empty():
		return
	_reg["generic"] = ActionBehavior.new()
	_reg["dodge"] = DodgeBehavior.new()
	_reg["perch"] = PerchBehavior.new()
	_reg["leap_strike"] = LeapStrikeBehavior.new()
	_reg["slip"] = SlipBehavior.new()
	_reg["charge"] = ChargeBehavior.new()
	_reg["bark"] = BarkBehavior.new()
	_reg["stance"] = StanceBehavior.new()
	_reg["feint"] = FeintBehavior.new()
	_reg["curve_dash"] = CurveDashBehavior.new()
	_reg["leap"] = LeapBehavior.new()
	_reg["dropkick"] = DropkickBehavior.new()
	_reg["parry"] = ParryBehavior.new()
	_reg["grab"] = GrabBehavior.new()


static func of(a: ActionDef) -> ActionBehavior:
	_ensure()
	var b: ActionBehavior = _reg.get(a.behavior)
	if b == null:
		push_error("unknown behaviour '%s' for %s" % [a.behavior, a.id])
		return _reg["generic"]
	return b


static func names() -> Array:
	_ensure()
	return _reg.keys()
