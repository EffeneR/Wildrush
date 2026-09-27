class_name ChargeBehavior
extends ActionBehavior
## Bruno Q "Shoulder Rush": committed charge with limited steering; stops on first contact
## (short displacement along the charge), on walls (bump) or when blocked; punishable miss.


func start(f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	f.st.set_phase("windup")
	f.st.act_data = {"dir_yaw": f.st.yaw, "outcome": ""}


func step(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"windup":
			if st.act_tick >= a.pticks("windup_s", 0.25):
				st.act_data["dir_yaw"] = st.yaw
				st.set_phase("charge")
				ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "bruno_rush_start", "predictable": true})
		"charge":
			var steer: float = deg_to_rad(float(a.param("steer_deg_s", 90.0))) / WR.TICK_RATE
			var dy: float = MathX.rotate_toward(float(st.act_data["dir_yaw"]), inp.yaw, steer)
			st.act_data["dir_yaw"] = dy
			st.yaw = dy
			f.apply_yaw()
			if st.act_phase_tick >= a.pticks("charge_s", 0.70):
				_end_phase(f, "miss")
		_:
			if st.act_phase_tick >= int(st.act_data.get("end_len", 20)) - 1:
				FighterLogic.end_action(f, ctx, "done")


func _end_phase(f: FighterBody, outcome: String) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	st.act_data["outcome"] = outcome
	var key: String = {"hit": "hit_recover_s", "miss": "miss_recover_s", "wall": "wall_recover_s", "blocked": "blocked_recover_s"}.get(outcome, "miss_recover_s")
	st.act_data["end_len"] = a.pticks(key, 0.5)
	st.set_phase(outcome)


func post_move(f: FighterBody, ctx: SimContext) -> void:
	var st: FighterState = f.st
	if st.act_phase == "charge" and f.is_on_wall():
		var n: Vector3 = f.get_wall_normal()
		if n.dot(MathX.yaw_forward(float(st.act_data["dir_yaw"]))) < -0.5:
			_end_phase(f, "wall")
			ctx.emit({"type": "wall_bump", "e": f.entity_id, "predictable": true})


func move_mode(f: FighterBody) -> String:
	return "curve" if f.st.act_phase == "charge" else "planted"


func curve_velocity(f: FighterBody) -> Vector3:
	return MathX.yaw_forward(float(f.st.act_data["dir_yaw"])) * float(f.st.act.param("speed", 11.0))


func turn_rate(f: FighterBody) -> float:
	return f.st.act.turn_rate_at(f.st.act_tick) if f.st.act_phase == "windup" else 0.0


func hit_active(f: FighterBody, _h: HitDef) -> bool:
	return f.st.act_phase == "charge"


func on_hit(f: FighterBody, _target: FighterBody, _h: HitDef, ctx: SimContext) -> void:
	_end_phase(f, "hit")
	ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "bruno_rush_impact"})


func on_blocked(f: FighterBody, target: FighterBody, _h: HitDef, _ctx: SimContext) -> void:
	_end_phase(f, "blocked")
	FighterLogic.apply_knockback(target, MathX.yaw_forward(float(f.st.act_data["dir_yaw"])), float(f.st.act.param("blocked_push", 0.6)))


func can_cancel(_f: FighterBody, _c: String) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase != "charge"


func anim(f: FighterBody) -> Array:
	var st: FighterState = f.st
	var ph: String = st.act_phase
	var key: String = "windup" if ph == "windup" else ("charge" if ph == "charge" else ph)
	return [clip_name(f, key, "skill_q_" + key), float(st.act_phase_tick) * WR.TICK_DT]
