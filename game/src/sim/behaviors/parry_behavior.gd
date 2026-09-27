class_name ParryBehavior
extends ActionBehavior
## Scrap Q "Catch & Turn": narrow timed parry against eligible frontal melee strikes.
## Success cancels the strike and redirects the attacker (turned + pushed aside, exposed).
## A whiff leaves Scrap exposed. Only Scrap has a parry (REFERENCE_AUDIT A5).


func start(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	f.st.set_phase("stance")
	f.st.act_data = {}
	ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "scrap_parry_stance", "predictable": true})


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"stance":
			if st.act_tick >= a.pticks("window_to_s", 0.267):
				st.act_data["len"] = a.pticks("whiff_recover_s", 0.45)
				st.set_phase("whiff")
		"whiff", "success":
			if st.act_phase_tick >= int(st.act_data.get("len", 20)) - 1:
				FighterLogic.end_action(f, ctx, "done")


func in_parry_window(f: FighterBody) -> bool:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	return st.act_phase == "stance" and st.act_tick >= a.pticks("window_from_s", 0.05) and st.act_tick < a.pticks("window_to_s", 0.267)


func parry_arc_half(f: FighterBody) -> float:
	return deg_to_rad(float(f.st.act.param("arc_deg", 140.0)) * 0.5)


func on_parry_success(f: FighterBody, attacker: FighterBody, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	st.act_data["len"] = a.pticks("success_recover_s", 0.2)
	st.set_phase("success")
	# cooldown refund on success
	var refund: float = float(a.param("success_cooldown_refund", 0.5))
	st.cd_ready["q"] = ctx.tick + int(round(a.cooldown_ticks * (1.0 - refund)))
	# redirect the attacker: cancel its action, stagger, turn it and push it to Scrap's side
	var to_att: Vector3 = attacker.global_position - f.global_position
	to_att.y = 0.0
	var side: Vector3 = MathX.yaw_right(st.yaw)
	if side.dot(to_att) < 0.0:
		side = -side
	var turn: float = deg_to_rad(float(a.param("redirect_turn_deg", 70.0)))
	var applied: int = FighterLogic.apply_control(attacker, WR.Ctrl.STAGGER, a.pticks("attacker_stagger_s", 0.6), ctx, f.entity_id)
	if applied != WR.Ctrl.NONE:
		attacker.st.yaw = wrapf(attacker.st.yaw + (turn if side.dot(MathX.yaw_right(attacker.st.yaw)) < 0.0 else -turn), -PI, PI)
		attacker.apply_yaw()
	FighterLogic.apply_knockback(attacker, side, float(a.param("redirect_push", 1.2)))


func move_mode(_f: FighterBody) -> String:
	return "planted"


func turn_rate(f: FighterBody) -> float:
	return deg_to_rad(240.0) / WR.TICK_RATE if f.st.act_phase == "stance" else 0.0


func can_cancel(f: FighterBody, category: String) -> bool:
	return f.st.act_phase == "success" and f.st.act_phase_tick >= 6 and category != "skill"


func is_offensive(_f: FighterBody) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase == "whiff"


func anim(f: FighterBody) -> Array:
	var ph: String = f.st.act_phase
	return [clip_name(f, ph, "skill_q_" + ph), float(f.st.act_phase_tick) * WR.TICK_DT]
