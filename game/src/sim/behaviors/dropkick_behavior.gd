class_name DropkickBehavior
extends ActionBehavior
## Hops R "Dropkick": grounded activation, committed forward flying kick; knockback on
## contact then a short rebound landing; a miss crashes Hops onto her back (long recovery).
## Grounded-only activation of Bound/Dropkick prevents chained air movement.


func start(f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	f.st.set_phase("hop")
	f.st.act_data = {"hit": false}


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"hop":
			f.velocity = Vector3(0, f.velocity.y, 0)
			if st.act_tick >= a.pticks("hop_s", 0.22):
				st.act_data["dir"] = f.forward()
				st.set_phase("flight")
				ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "hops_dropkick", "predictable": true})
				_flight_velocity(f)
		"flight":
			var n: int = a.pticks("flight_s", 0.40)
			if st.act_phase_tick >= n:
				_to_crash(f, ctx)
			else:
				_flight_velocity(f)
		"land", "crash":
			if st.act_phase == "land" and st.act_phase_tick < 10:
				var back: Vector3 = -(st.act_data["dir"] as Vector3) * (float(a.param("rebound", 0.6)) / (10.0 * WR.TICK_DT))
				f.velocity = Vector3(back.x, maxf(f.velocity.y - Tuning.gravity * WR.TICK_DT, -Tuning.max_fall_speed), back.z)
			else:
				f.velocity = Vector3(0, maxf(f.velocity.y - Tuning.gravity * WR.TICK_DT, -Tuning.max_fall_speed), 0)
			if st.act_phase_tick >= int(st.act_data.get("end_len", 20)) - 1:
				FighterLogic.end_action(f, ctx, "done")


func _flight_velocity(f: FighterBody) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	var n: int = a.pticks("flight_s", 0.40)
	var tau: float = (float(st.act_phase_tick) + 0.5) / float(n)
	var h: float = float(a.param("height", 0.6))
	var vy: float = 4.0 * h * (1.0 - 2.0 * tau) / (float(n) * WR.TICK_DT)
	var hz: Vector3 = (st.act_data["dir"] as Vector3) * (float(a.param("distance", 5.5)) / (float(n) * WR.TICK_DT))
	f.velocity = Vector3(hz.x, vy, hz.z)


func _to_crash(f: FighterBody, ctx: SimContext) -> void:
	f.st.act_data["end_len"] = f.st.act.pticks("miss_crash_s", 0.85)
	f.st.set_phase("crash")
	ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "hops_dropkick_crash", "predictable": true})


func post_move(f: FighterBody, ctx: SimContext) -> void:
	var st: FighterState = f.st
	if st.act_phase == "flight" and f.is_on_wall():
		var n: Vector3 = f.get_wall_normal()
		if n.dot(st.act_data["dir"] as Vector3) < -0.4:
			_to_crash(f, ctx)


func on_hit(f: FighterBody, _t: FighterBody, _h: HitDef, _ctx: SimContext) -> void:
	var st: FighterState = f.st
	st.act_data["hit"] = true
	st.act_data["end_len"] = st.act.pticks("hit_land_s", 0.35)
	st.set_phase("land")


func on_blocked(f: FighterBody, t: FighterBody, h: HitDef, ctx: SimContext) -> void:
	on_hit(f, t, h, ctx)


func move_mode(f: FighterBody) -> String:
	return "planted" if f.st.act_phase == "hop" else "owned"


func turn_rate(f: FighterBody) -> float:
	return f.st.act.turn_rate_at(f.st.act_tick) if f.st.act_phase == "hop" else 0.0


func hit_active(f: FighterBody, h: HitDef) -> bool:
	return f.st.act_phase == "flight" and f.st.act_tick >= h.t0 and f.st.act_tick < h.t1


func can_cancel(_f: FighterBody, _c: String) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase != "flight"


func anim(f: FighterBody) -> Array:
	var ph: String = f.st.act_phase
	return [clip_name(f, ph, "skill_r_" + ph), float(f.st.act_phase_tick) * WR.TICK_DT]
