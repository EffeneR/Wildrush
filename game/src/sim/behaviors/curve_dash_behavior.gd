class_name CurveDashBehavior
extends ActionBehavior
## Vex E "Sidewinder": player-steered curved approach ending in a strike. Starts 45° to the
## held side and bends toward the camera direction at a limited rate. Stops at walls and
## at opponents (contact triggers the strike) — never moves behind the target automatically
## and never passes through anything (collision stays on).


func start(f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	f.st.set_phase("windup")
	f.st.act_data = {"heading": f.st.yaw, "side": 1.0, "hit": false}


func step(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"windup":
			if st.act_tick >= a.pticks("windup_s", 0.10):
				var side: float = -1.0 if inp.move.x < -0.3 else 1.0
				var ang: float = deg_to_rad(float(a.param("initial_angle_deg", 45.0)))
				st.act_data["side"] = side
				st.act_data["heading"] = wrapf(st.yaw - side * ang, -PI, PI)
				st.set_phase("dash")
				ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "vex_sidewinder", "predictable": true})
		"dash":
			var steer: float = deg_to_rad(float(a.param("steer_deg_s", 220.0))) / WR.TICK_RATE
			var hd: float = MathX.rotate_toward(float(st.act_data["heading"]), inp.yaw, steer)
			st.act_data["heading"] = hd
			st.yaw = hd
			f.apply_yaw()
			if st.act_phase_tick >= a.pticks("dash_s", 0.50) or _contact(f, ctx):
				_strike(f)
		"strike":
			if st.act_phase_tick >= a.pticks("strike_s", 0.18):
				var key: String = "hit_recover_s" if bool(st.act_data["hit"]) else "miss_recover_s"
				st.act_data["rec_len"] = a.pticks(key, 0.5)
				st.set_phase("recover")
		"recover":
			if st.act_phase_tick >= int(st.act_data.get("rec_len", 20)) - 1:
				FighterLogic.end_action(f, ctx, "done")


func _strike(f: FighterBody) -> void:
	f.st.set_phase("strike")


func _contact(f: FighterBody, ctx: SimContext) -> bool:
	var rng: float = float(f.st.act.param("contact_range", 1.1))
	var fwd: Vector3 = f.forward()
	for t: FighterBody in ctx.enemies_of(f):
		var d: Vector3 = t.global_position - f.global_position
		d.y = 0.0
		if d.length() <= rng + t.def.hurt_radius and d.length() > 0.01 and fwd.angle_to(d.normalized()) < deg_to_rad(60.0):
			return true
	return false


func post_move(f: FighterBody, _ctx: SimContext) -> void:
	if f.st.act_phase == "dash" and f.is_on_wall():
		var n: Vector3 = f.get_wall_normal()
		if n.dot(f.forward()) < -0.5:
			_strike(f)


func move_mode(f: FighterBody) -> String:
	return "curve" if f.st.act_phase == "dash" else "planted"


func curve_velocity(f: FighterBody) -> Vector3:
	return MathX.yaw_forward(float(f.st.act_data["heading"])) * float(f.st.act.param("speed", 10.0))


func turn_rate(f: FighterBody) -> float:
	return f.st.act.turn_rate_at(f.st.act_tick) if f.st.act_phase == "windup" else 0.0


func hit_active(f: FighterBody, h: HitDef) -> bool:
	return f.st.act_phase == "strike" and h.rel == "strike" and f.st.act_phase_tick >= h.t0 and f.st.act_phase_tick < h.t1


func hit_time_s(f: FighterBody, _h: HitDef) -> float:
	return float(f.st.act_phase_tick) * WR.TICK_DT


func on_hit(f: FighterBody, _t: FighterBody, _h: HitDef, _ctx: SimContext) -> void:
	f.st.act_data["hit"] = true


func can_cancel(_f: FighterBody, _c: String) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase == "windup" or f.st.act_phase == "recover"


func anim(f: FighterBody) -> Array:
	var st: FighterState = f.st
	match st.act_phase:
		"windup": return [clip_name(f, "windup", "skill_e_windup"), float(st.act_phase_tick) * WR.TICK_DT]
		"dash":
			var side: float = float(st.act_data.get("side", 1.0))
			return [clip_name(f, "dash_r" if side > 0.0 else "dash_l", "skill_e_dash_r"), float(st.act_phase_tick) * WR.TICK_DT]
		"strike": return [clip_name(f, "strike", "skill_e_strike"), float(st.act_phase_tick) * WR.TICK_DT]
	return [clip_name(f, "recover", "skill_e_recover"), float(st.act_phase_tick) * WR.TICK_DT]
