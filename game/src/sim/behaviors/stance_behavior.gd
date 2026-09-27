class_name StanceBehavior
extends ActionBehavior
## Bruno R "Stand Firm": planted stance with a wider, stronger frontal guard and reduced
## movement. No attacks while planted; back remains open. R again (after a minimum hold)
## or the maximum hold ends it. Cooldown starts when the stance ends. No shield object.


func start(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	f.st.set_phase("enter")
	f.st.act_data = {}
	f.st.guarding = false
	ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "bruno_stand_firm", "predictable": true})


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"enter":
			if st.act_phase_tick >= a.pticks("enter_s", 0.15):
				st.set_phase("hold")
		"hold":
			if st.act_phase_tick >= a.pticks("max_hold_s", 3.0):
				st.set_phase("exit")
		"exit":
			if st.act_phase_tick >= a.pticks("exit_s", 0.25) - 1:
				FighterLogic.end_action(f, ctx, "done")


func consume_press(f: FighterBody, btn: int, _inp: InputFrame, _ctx: SimContext) -> bool:
	var st: FighterState = f.st
	if btn == WR.BTN_R and st.act_phase == "hold" and st.act_phase_tick >= st.act.pticks("min_hold_s", 0.3):
		st.set_phase("exit")
		return true
	# attacks are ignored while planted (consumed so they do not fire late)
	if btn == WR.BTN_LIGHT or btn == WR.BTN_HEAVY or btn == WR.BTN_Q or btn == WR.BTN_E:
		return true
	return false


func finish(f: FighterBody, ctx: SimContext, _reason: String) -> void:
	f.st.cd_ready["r"] = ctx.tick + f.st.act.cooldown_ticks


func cooldown_on_start() -> bool:
	return false


func move_mode(_f: FighterBody) -> String:
	return "loco"


func loco_speed_mult(f: FighterBody) -> float:
	return float(f.st.act.param("move_mult", 0.3))


func turn_rate(_f: FighterBody) -> float:
	return deg_to_rad(240.0) / WR.TICK_RATE


func can_cancel(f: FighterBody, category: String) -> bool:
	return category == "dodge" and f.st.act_phase == "hold"


func is_guarding(f: FighterBody) -> bool:
	return f.st.act_phase == "hold" or (f.st.act_phase == "enter" and f.st.act_phase_tick >= 3)


func guard_mod(f: FighterBody) -> Dictionary:
	if not is_guarding(f):
		return {}
	var a: ActionDef = f.st.act
	return {"arc_half": deg_to_rad(float(a.param("guard_arc_deg", 180.0)) * 0.5),
			"stamina_mult": float(a.param("block_stamina_mult", 0.5)),
			"kb_mult": float(a.param("front_knockback_mult", 0.25)), "stance": true}


func is_offensive(_f: FighterBody) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase == "exit"


func anim(f: FighterBody) -> Array:
	var ph: String = f.st.act_phase
	return [clip_name(f, ph, "skill_r_" + ph), float(f.st.act_phase_tick) * WR.TICK_DT]
