class_name FeintBehavior
extends ActionBehavior
## Vex Q "False Start": convincing heavy wind-up (displayed to opponents as the heavy),
## cancelled into a sidestep in the held direction (left / right / default back). No damage.


func start(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	f.st.set_phase("feint")
	f.st.act_data = {}
	ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "vex_feint", "predictable": true})


func step(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"feint":
			if st.act_tick >= a.pticks("feint_s", 0.25):
				var dn: String = String(a.param("default_dir", "back"))
				if inp.move.x < -0.3:
					dn = "left"
				elif inp.move.x > 0.3:
					dn = "right"
				var dir: Vector3 = -f.forward()
				if dn == "left":
					dir = -MathX.yaw_right(st.yaw)
				elif dn == "right":
					dir = MathX.yaw_right(st.yaw)
				st.act_data = {"dir": dir, "dn": dn}
				st.set_phase("step")
				ctx.emit({"type": "afterimage", "e": f.entity_id, "predictable": true})
		"step":
			if st.act_phase_tick >= a.pticks("step_s", 0.25):
				st.set_phase("recover")
		"recover":
			if st.act_phase_tick >= a.pticks("recovery_s", 0.10) - 1:
				FighterLogic.end_action(f, ctx, "done")


func move_mode(f: FighterBody) -> String:
	return "curve" if f.st.act_phase == "step" else "planted"


func curve_velocity(f: FighterBody) -> Vector3:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	var n: float = float(a.pticks("step_s", 0.25))
	var dist: float = float(a.param("step_distance", 2.4))
	var d1: float = MathX.ease_out(float(st.act_phase_tick + 1) / n) * dist
	var d0: float = MathX.ease_out(float(st.act_phase_tick) / n) * dist
	return (st.act_data["dir"] as Vector3) * ((d1 - d0) / WR.TICK_DT)


func turn_rate(f: FighterBody) -> float:
	return f.st.act.turn_rate_at(f.st.act_tick) if f.st.act_phase == "feint" else 0.0


func can_cancel(f: FighterBody, category: String) -> bool:
	return f.st.act_phase == "recover" or (f.st.act_phase == "step" and f.st.act_phase_tick >= 10 and category != "dodge")


func is_evading(f: FighterBody) -> bool:
	var a: ActionDef = f.st.act
	return f.st.act_tick >= a.pticks("evade_from_s", 0.27) and f.st.act_tick <= a.pticks("evade_to_s", 0.40)


func display_id(f: FighterBody) -> String:
	if f.st.act_phase == "feint":
		return String(f.st.act.param("display_as", f.st.act.id))
	return f.st.act.id


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase == "feint"


func anim(f: FighterBody) -> Array:
	var st: FighterState = f.st
	if st.act_phase == "feint":
		return ["heavy", float(st.act_tick) * WR.TICK_DT]
	var dn: String = String(st.act_data.get("dn", "back"))
	var key: String = {"left": "step_l", "right": "step_r"}.get(dn, "step_b")
	var t: float = float(st.act_tick - st.act.pticks("feint_s", 0.25)) * WR.TICK_DT
	return [clip_name(f, key, "skill_q_" + key), t]
