class_name PerchBehavior
extends ActionBehavior
## Nyx passive "Perch": scramble onto a validated designated ledge (landing checked at start).


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var n: int = int(st.act_data.get("len", 27))
	var from: Vector3 = st.act_data["from"]
	var to: Vector3 = st.act_data["to"]
	var u: float = clampf(float(st.act_tick + 1) / float(n), 0.0, 1.0)
	# rise first (60%), then move over the edge
	var target: Vector3
	if u < 0.6:
		var k: float = MathX.ease_out(u / 0.6)
		target = Vector3(from.x, lerpf(from.y, to.y + 0.08, k), from.z)
	else:
		var k2: float = (u - 0.6) / 0.4
		target = Vector3(lerpf(from.x, to.x, k2), to.y + 0.08, lerpf(from.z, to.z, k2))
	f.velocity = (target - f.global_position) / WR.TICK_DT
	if st.act_tick >= n - 1:
		FighterLogic.end_action(f, ctx, "done")


func move_mode(_f: FighterBody) -> String:
	return "owned"


func turn_rate(_f: FighterBody) -> float:
	return 0.0


func can_cancel(_f: FighterBody, _category: String) -> bool:
	return false


func is_offensive(_f: FighterBody) -> bool:
	return false


func anim(f: FighterBody) -> Array:
	return ["perch_climb", float(f.st.act_tick) * WR.TICK_DT]
