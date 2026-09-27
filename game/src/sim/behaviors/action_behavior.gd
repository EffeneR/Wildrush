class_name ActionBehavior
extends RefCounted
## Stateless strategy object for an action (D-011). All per-instance state lives in
## FighterState.act_* so it is snapshot/replay-safe. Subclasses override hooks.


func start(_f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	pass


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	## Default: fixed-length action; ends after its last tick (plus finisher recovery).
	var st: FighterState = f.st
	var total: int = st.act.total_ticks + (Tuning.finisher_extra_recovery if st.act_finisher else 0)
	if st.act_tick >= total - 1:
		FighterLogic.end_action(f, ctx, "done")


func post_move(_f: FighterBody, _ctx: SimContext) -> void:
	pass


func finish(_f: FighterBody, _ctx: SimContext, _reason: String) -> void:
	pass


func turn_rate(f: FighterBody) -> float:
	return f.st.act.turn_rate_at(f.st.act_tick)


func can_cancel(f: FighterBody, category: String) -> bool:
	var st: FighterState = f.st
	if st.act_finisher and category == "light":
		return false
	return st.act.can_cancel_into(st.act_tick, category)


func consume_press(_f: FighterBody, _btn: int, _inp: InputFrame, _ctx: SimContext) -> bool:
	return false


func move_mode(f: FighterBody) -> String:
	return "curve" if not f.st.act.move_keys.is_empty() else "planted"


func curve_velocity(f: FighterBody) -> Vector3:
	var a: ActionDef = f.st.act
	var t: float = float(f.st.act_tick) * WR.TICK_DT
	var p1: Vector3 = MathX.sample_keys_smooth(a.move_keys, t)
	var p0: Vector3 = MathX.sample_keys_smooth(a.move_keys, t - WR.TICK_DT)
	var d: Vector3 = p1 - p0
	return (MathX.yaw_right(f.st.yaw) * d.x + MathX.yaw_forward(f.st.yaw) * d.z) / WR.TICK_DT


func loco_speed_mult(_f: FighterBody) -> float:
	return 1.0


func hit_active(f: FighterBody, h: HitDef) -> bool:
	return h.rel == "" and f.st.act_tick >= h.t0 and f.st.act_tick < h.t1


func hit_time_s(f: FighterBody, _h: HitDef) -> float:
	return float(f.st.act_tick) * WR.TICK_DT


func on_hit(_f: FighterBody, _target: FighterBody, _h: HitDef, _ctx: SimContext) -> void:
	pass


func on_blocked(_f: FighterBody, _target: FighterBody, _h: HitDef, _ctx: SimContext) -> void:
	pass


func on_land(_f: FighterBody, _ctx: SimContext) -> void:
	pass


func is_evading(_f: FighterBody) -> bool:
	return false


func is_guarding(_f: FighterBody) -> bool:
	return false


func guard_mod(_f: FighterBody) -> Dictionary:
	## {"arc_half": rad, "stamina_mult": x, "kb_mult": x} when the action provides guard.
	return {}


func in_parry_window(_f: FighterBody) -> bool:
	return false


func on_parry_success(_f: FighterBody, _attacker: FighterBody, _ctx: SimContext) -> void:
	pass


func is_offensive(_f: FighterBody) -> bool:
	return true


func cooldown_on_start() -> bool:
	return true


func display_id(f: FighterBody) -> String:
	## Action id shown to OTHER clients (feints display as the heavy wind-up).
	return f.st.act.id


func anim(f: FighterBody) -> Array:
	## [clip_name, time_s] for presentation.
	var a: ActionDef = f.st.act
	return [a.clip, float(f.st.act_tick) * WR.TICK_DT]


func exposed(f: FighterBody) -> bool:
	## "Exposed" for Warning Bark: in startup or recovery of an offensive action.
	var st: FighterState = f.st
	var a: ActionDef = st.act
	if a == null:
		return false
	for h in a.hits:
		if h.rel == "" and st.act_tick >= h.t0 and st.act_tick < h.t1:
			return false
	return true


func clip_len(f: FighterBody, key: String, fallback_s: float) -> int:
	var c: Variant = f.st.act.clips.get(key)
	if c is Array and (c as Array).size() >= 2:
		return WR.secs_to_ticks(float(c[1]))
	return WR.secs_to_ticks(fallback_s)


func clip_name(f: FighterBody, key: String, fallback: String) -> String:
	var c: Variant = f.st.act.clips.get(key)
	if c is Array and (c as Array).size() >= 1:
		return String(c[0])
	return fallback
