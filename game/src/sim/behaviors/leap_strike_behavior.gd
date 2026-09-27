class_name LeapStrikeBehavior
extends ActionBehavior
## Nyx Q "Pounce": aimed wind-up, committed forward leap (no homing), claw strike near the
## end of the leap; walls stop it; landing recovery is longer on a miss.


func start(f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	f.st.set_phase("aim")
	f.st.act_data = {"hit": false, "outcome": ""}


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"aim":
			if st.act_tick >= a.pticks("aim_s", 0.30):
				st.act_data["dir"] = f.forward()
				st.set_phase("leap")
				ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "nyx_pounce_leap", "predictable": true})
				_leap_velocity(f)
			else:
				f.velocity = Vector3(0, f.velocity.y, 0)
		"leap":
			var n: int = a.pticks("leap_s", 0.40)
			if st.act_phase_tick >= n or (st.act_phase_tick > n / 2 and f.is_on_floor()):
				_land(f, "hit" if bool(st.act_data["hit"]) else "miss", ctx)
			else:
				_leap_velocity(f)
		"land":
			f.velocity = Vector3(0, f.velocity.y, 0)
			if st.act_phase_tick >= int(st.act_data.get("land_len", 20)) - 1:
				FighterLogic.end_action(f, ctx, "done")


func _leap_velocity(f: FighterBody) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	var n: int = a.pticks("leap_s", 0.40)
	var tau: float = float(st.act_phase_tick) / float(n)
	var h: float = float(a.param("leap_height", 0.7))
	var vy: float = 4.0 * h * (1.0 - 2.0 * tau) / (float(n) * WR.TICK_DT)
	var horiz: Vector3 = Vector3.ZERO
	if not bool(st.act_data["hit"]):
		horiz = (st.act_data["dir"] as Vector3) * (float(a.param("leap_distance", 6.0)) / (float(n) * WR.TICK_DT))
	f.velocity = Vector3(horiz.x, vy, horiz.z)


func _land(f: FighterBody, outcome: String, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	st.act_data["outcome"] = outcome
	var key: String = "land_hit_s" if outcome == "hit" else ("land_wall_s" if outcome == "wall" else "land_miss_s")
	st.act_data["land_len"] = a.pticks(key, 0.5)
	st.set_phase("land")
	ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "nyx_pounce_land", "predictable": true})


func post_move(f: FighterBody, ctx: SimContext) -> void:
	var st: FighterState = f.st
	if st.act_phase == "leap" and f.is_on_wall() and not bool(st.act_data["hit"]):
		var n: Vector3 = f.get_wall_normal()
		if n.dot(st.act_data["dir"] as Vector3) < -0.4:
			f.velocity = Vector3(0, minf(f.velocity.y, 0.0), 0)
			_land(f, "wall", ctx)


func move_mode(f: FighterBody) -> String:
	return "owned" if f.st.act_phase == "leap" else "planted"


func hit_active(f: FighterBody, h: HitDef) -> bool:
	return f.st.act_phase == "leap" and not bool(f.st.act_data["hit"]) and f.st.act_tick >= h.t0 and f.st.act_tick < h.t1


func on_hit(f: FighterBody, _target: FighterBody, _h: HitDef, _ctx: SimContext) -> void:
	f.st.act_data["hit"] = true


func on_blocked(f: FighterBody, _target: FighterBody, _h: HitDef, _ctx: SimContext) -> void:
	f.st.act_data["hit"] = true   # stops forward travel against the guard; lands with hit timing


func can_cancel(_f: FighterBody, _c: String) -> bool:
	return false


func anim(f: FighterBody) -> Array:
	var st: FighterState = f.st
	match st.act_phase:
		"aim": return [clip_name(f, "prep", "skill_q_prep"), float(st.act_phase_tick) * WR.TICK_DT]
		"leap": return [clip_name(f, "air", "skill_q_air"), float(st.act_phase_tick) * WR.TICK_DT]
	var miss: bool = String(st.act_data.get("outcome", "")) != "hit"
	return [clip_name(f, "land_miss" if miss else "land", "skill_q_land"), float(st.act_phase_tick) * WR.TICK_DT]


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase != "leap"
