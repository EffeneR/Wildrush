class_name DodgeBehavior
extends ActionBehavior
## Shared directional dodge (D-010): explicit evasion window, ease-out displacement.


func start(f: FighterBody, inp: InputFrame, _ctx: SimContext) -> void:
	var st: FighterState = f.st
	var mv: Vector2 = inp.move if inp != null else Vector2.ZERO
	var dir: Vector3
	var name: String
	if mv.length() < 0.2:
		dir = -f.forward()
		name = "b"
	else:
		dir = (MathX.yaw_right(inp.yaw) * mv.x + MathX.yaw_forward(inp.yaw) * mv.y).normalized()
		var local: Vector3 = MathX.world_dir_to_local(st.yaw, dir)
		if absf(local.x) > absf(local.z):
			name = "r" if local.x > 0.0 else "l"
		else:
			name = "f" if local.z > 0.0 else "b"
	st.act_data = {"dir": dir, "dn": name}
	st.set_phase("dodge")


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	if f.st.act_tick >= Tuning.dodge_ticks - 1:
		FighterLogic.end_action(f, ctx, "done")


func move_mode(_f: FighterBody) -> String:
	return "curve"


func curve_velocity(f: FighterBody) -> Vector3:
	var t: int = f.st.act_tick
	if t >= Tuning.dodge_move_end:
		return Vector3.ZERO
	var n: float = float(Tuning.dodge_move_end)
	var d1: float = MathX.ease_out(float(t + 1) / n) * Tuning.dodge_distance
	var d0: float = MathX.ease_out(float(t) / n) * Tuning.dodge_distance
	return (f.st.act_data["dir"] as Vector3) * ((d1 - d0) / WR.TICK_DT)


func turn_rate(_f: FighterBody) -> float:
	return 0.0


func can_cancel(f: FighterBody, category: String) -> bool:
	return f.st.act_tick >= Tuning.dodge_cancel_from and category != "dodge"


func is_evading(f: FighterBody) -> bool:
	return f.st.act_tick >= Tuning.dodge_evade_from and f.st.act_tick <= Tuning.dodge_evade_to


func is_offensive(_f: FighterBody) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_tick > Tuning.dodge_evade_to


func anim(f: FighterBody) -> Array:
	return ["dodge_" + String(f.st.act_data.get("dn", "b")), float(f.st.act_tick) * WR.TICK_DT]
