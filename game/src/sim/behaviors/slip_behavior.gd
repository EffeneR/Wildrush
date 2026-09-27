class_name SlipBehavior
extends ActionBehavior
## Nyx R "Slip": short lateral evasion (visible, continuous motion — no teleport), followed by
## a brief optional counter-swipe input window.


func start(f: FighterBody, inp: InputFrame, _ctx: SimContext) -> void:
	var side: float = 1.0
	if inp != null and inp.move.x < -0.3:
		side = -1.0
	f.st.act_data = {"side": side, "dir": MathX.yaw_right(f.st.yaw) * side}
	f.st.set_phase("evade")


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	var evade_n: int = a.pticks("evade_s", 0.30)
	if st.act_phase == "evade" and st.act_tick >= evade_n:
		st.set_phase("recover")
	var end_t: int = maxi(evade_n + a.pticks("recovery_s", 0.12), a.pticks("counter_to_s", 0.45))
	if st.act_tick >= end_t - 1:
		FighterLogic.end_action(f, ctx, "done")


func consume_press(f: FighterBody, btn: int, inp: InputFrame, ctx: SimContext) -> bool:
	if btn != WR.BTN_LIGHT:
		return false
	var st: FighterState = f.st
	var a: ActionDef = st.act
	if st.act_tick < a.pticks("counter_from_s", 0.12) or st.act_tick > a.pticks("counter_to_s", 0.45):
		return false
	var counter: ActionDef = f.def.action(String(a.param("counter_action", "")))
	if counter == null:
		return false
	FighterLogic.start_action(f, counter, ctx, inp)
	return true


func move_mode(f: FighterBody) -> String:
	return "curve" if f.st.act_phase == "evade" else "planted"


func curve_velocity(f: FighterBody) -> Vector3:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	var n: float = float(a.pticks("evade_s", 0.30))
	var dist: float = float(a.param("distance", 2.6))
	var d1: float = MathX.ease_out(float(st.act_tick + 1) / n) * dist
	var d0: float = MathX.ease_out(float(st.act_tick) / n) * dist
	return (st.act_data["dir"] as Vector3) * ((d1 - d0) / WR.TICK_DT)


func turn_rate(_f: FighterBody) -> float:
	return 0.0


func can_cancel(_f: FighterBody, _c: String) -> bool:
	return false


func is_evading(f: FighterBody) -> bool:
	var a: ActionDef = f.st.act
	return f.st.act_tick >= a.pticks("evade_from_s", 0.017) and f.st.act_tick <= a.pticks("evade_to_s", 0.20)


func is_offensive(_f: FighterBody) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase == "recover"


func anim(f: FighterBody) -> Array:
	var side: float = float(f.st.act_data.get("side", 1.0))
	return [clip_name(f, "right" if side > 0.0 else "left", "skill_r_right"), float(f.st.act_tick) * WR.TICK_DT]
