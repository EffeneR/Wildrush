class_name LeapBehavior
extends ActionBehavior
## Hops Q "Bound": grounded-only directional leap with bounded air control (±steer_deg total,
## ±speed_adjust) and a readable landing. No damage, no invulnerability.


func start(f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	f.st.set_phase("crouch")
	f.st.act_data = {"steer_used": 0.0}


func step(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"crouch":
			if st.act_tick >= a.pticks("crouch_s", 0.15):
				var dir: Vector3 = f.forward()
				if inp.move.length() > 0.2:
					dir = (MathX.yaw_right(inp.yaw) * inp.move.x + MathX.yaw_forward(inp.yaw) * inp.move.y).normalized()
				st.act_data["dir"] = dir
				st.act_data["base_dir"] = dir
				st.set_phase("air")
				ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "hops_bound_takeoff", "predictable": true})
				_air_velocity(f, inp)
		"air":
			var n: int = a.pticks("air_s", 0.55)
			if st.act_phase_tick > n / 2 and f.is_on_floor():
				st.set_phase("land")
				f.velocity = Vector3(0, f.velocity.y, 0)   # readable, planted landing
				ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "hops_bound_land", "predictable": true})
			else:
				_air_velocity(f, inp)
		"land":
			if st.act_phase_tick >= a.pticks("land_s", 0.25) - 1:
				FighterLogic.end_action(f, ctx, "done")


func _air_velocity(f: FighterBody, inp: InputFrame) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	var n: int = a.pticks("air_s", 0.55)
	var dir: Vector3 = st.act_data["dir"]
	# bounded air control: steer toward the held direction, limited total rotation
	if inp.move.length() > 0.2:
		var want: Vector3 = (MathX.yaw_right(inp.yaw) * inp.move.x + MathX.yaw_forward(inp.yaw) * inp.move.y).normalized()
		var cur_yaw: float = MathX.yaw_from_dir(dir)
		var want_yaw: float = MathX.yaw_from_dir(want)
		var base_yaw: float = MathX.yaw_from_dir(st.act_data["base_dir"])
		var limit: float = deg_to_rad(float(a.param("steer_deg", 25.0)))
		var step_yaw: float = MathX.rotate_toward(cur_yaw, want_yaw, deg_to_rad(90.0) / WR.TICK_RATE)
		var off: float = clampf(MathX.angle_diff(base_yaw, step_yaw), -limit, limit)
		dir = MathX.yaw_forward(base_yaw + off)
		st.act_data["dir"] = dir
	var adj: float = float(a.param("speed_adjust", 0.25))
	var fwd_in: float = 0.0
	if inp.move.length() > 0.2:
		var want2: Vector3 = (MathX.yaw_right(inp.yaw) * inp.move.x + MathX.yaw_forward(inp.yaw) * inp.move.y)
		fwd_in = clampf(want2.dot(dir), -1.0, 1.0)
	var speed: float = float(a.param("distance", 7.5)) / (float(n) * WR.TICK_DT) * (1.0 + adj * fwd_in)
	var tau: float = (float(st.act_phase_tick) + 0.5) / float(n)
	var h: float = float(a.param("height", 1.6))
	var vy: float
	if tau <= 1.0:
		vy = 4.0 * h * (1.0 - 2.0 * tau) / (float(n) * WR.TICK_DT)
	else:
		vy = maxf(f.velocity.y - Tuning.gravity * WR.TICK_DT, -Tuning.max_fall_speed)
	f.velocity = Vector3(dir.x * speed, vy, dir.z * speed)


func move_mode(f: FighterBody) -> String:
	return "owned" if f.st.act_phase == "air" else "planted"


func turn_rate(f: FighterBody) -> float:
	return f.st.act.turn_rate_at(f.st.act_tick) if f.st.act_phase == "crouch" else 0.0


func can_cancel(f: FighterBody, category: String) -> bool:
	return f.st.act_phase == "land" and f.st.act_phase_tick >= 8 and (category == "guard" or category == "light")


func is_offensive(_f: FighterBody) -> bool:
	return false


func anim(f: FighterBody) -> Array:
	var ph: String = f.st.act_phase
	return [clip_name(f, ph, "skill_q_" + ph), float(f.st.act_phase_tick) * WR.TICK_DT]
