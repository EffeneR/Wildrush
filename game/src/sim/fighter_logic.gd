class_name FighterLogic
extends RefCounted
## Per-fighter authoritative step (D-005 steps 3–5). Identical code runs on the dedicated
## server, in offline matches and in client-side prediction.

const PRESS_PRIORITY: Array[int] = [WR.BTN_Q, WR.BTN_E, WR.BTN_R, WR.BTN_HEAVY, WR.BTN_LIGHT, WR.BTN_DODGE, WR.BTN_JUMP]


static func step(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	if not f.present:
		return
	if not st.alive:
		_ko_physics(f)
		return
	st.last_input_seq = inp.seq
	# ---- step 3: vitals, control timers, spawn protection
	_vitals(f, inp, ctx)
	_advance_control(f, ctx)
	_spawn_protection(f, ctx)
	# ---- input edges -> short buffer (D-011: presses expire after input_buffer_ticks)
	var pressed: int = inp.buttons & ~st.prev_buttons
	st.prev_buttons = inp.buttons
	if pressed != 0:
		for b in PRESS_PRIORITY:
			if (pressed & b) != 0:
				st.buf_btn = b
				st.buf_tick = ctx.tick
				st.buf_move = inp.move
				break
	if inp.buttons != 0 or inp.move.length() > 0.2:
		st.idle_ticks = 0
	else:
		st.idle_ticks += 1
	# ---- step 4: facing, guard, action state machine
	if st.act != null:
		st.act_tick += 1
		st.act_phase_tick += 1
	_update_facing(f, inp)
	_update_guard(f, inp, ctx)
	_try_consume_buffer(f, inp, ctx)
	if st.act != null:
		Behaviors.of(st.act).step(f, inp, ctx)
	# ---- step 5: movement
	_move(f, inp, ctx)


# ------------------------------------------------------------------------------------------
# vitals / control
# ------------------------------------------------------------------------------------------
static func _vitals(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	# "no stamina regen while holding guard": the held button counts from the first tick
	var guarding_like: bool = st.guarding or inp.held(WR.BTN_GUARD) or (st.act != null and Behaviors.of(st.act).is_guarding(f))
	if not guarding_like and ctx.tick - st.last_spend_tick >= Tuning.stamina_regen_delay:
		st.stamina = minf(Tuning.stamina_max, st.stamina + Tuning.stamina_regen_per_tick)
	if st.health < f.def.health and ctx.tick - maxi(st.last_offense_tick, st.last_damage_tick) >= Tuning.hp_regen_delay:
		st.health = minf(f.def.health, st.health + Tuning.hp_regen_per_tick)


static func _advance_control(f: FighterBody, ctx: SimContext) -> void:
	var st: FighterState = f.st
	if st.ctrl == WR.Ctrl.NONE:
		return
	st.ctrl_tick += 1
	st.control_ticks += 1
	if st.ctrl_tick >= st.ctrl_len:
		if st.ctrl == WR.Ctrl.KNOCKDOWN:
			st.ctrl = WR.Ctrl.GETUP
			st.ctrl_tick = 0
			st.ctrl_len = Tuning.getup_ticks
			ctx.emit({"type": "getup", "e": f.entity_id, "predictable": true})
		elif st.ctrl == WR.Ctrl.GRABBED:
			st.ctrl = WR.Ctrl.NONE  # safety timeout; grabber normally releases explicitly
		else:
			st.ctrl = WR.Ctrl.NONE


static func _spawn_protection(f: FighterBody, ctx: SimContext) -> void:
	var st: FighterState = f.st
	if not st.spawn_protected:
		return
	var vol: Variant = ctx.spawn_volumes.get(f.team)
	var outside: bool = vol != null and not (vol as AABB).has_point(f.global_position + Vector3(0, 0.5, 0))
	if ctx.tick >= st.protect_until or outside:
		end_spawn_protection(f, ctx, "left" if outside else "timeout")


static func end_spawn_protection(f: FighterBody, ctx: SimContext, reason: String) -> void:
	if f.st.spawn_protected:
		f.st.spawn_protected = false
		ctx.emit({"type": "protect_end", "e": f.entity_id, "reason": reason})


static func is_hard(kind: int, ticks: int) -> bool:
	return kind == WR.Ctrl.KNOCKDOWN or kind == WR.Ctrl.GRABBED or kind == WR.Ctrl.GUARD_BREAK or ticks >= Tuning.hard_control_min


static func apply_control(target: FighterBody, kind: int, ticks: int, ctx: SimContext, by: int) -> int:
	## Applies a control effect honouring control resistance (D-010). Returns the effect applied.
	var st: FighterState = target.st
	var hard: bool = is_hard(kind, ticks)
	if hard and st.has_cr(ctx.tick) and kind != WR.Ctrl.GUARD_BREAK:
		kind = WR.Ctrl.FLINCH
		ticks = Tuning.cr_flinch_ticks
		hard = false
		ctx.emit({"type": "resisted", "e": target.entity_id, "by": by})
	if target.def.passive_id == "quick_recovery" and (kind == WR.Ctrl.FLINCH or kind == WR.Ctrl.STAGGER or kind == WR.Ctrl.BLOCKSTUN):
		ticks = maxi(1, int(round(ticks * float(target.def.passive_param("stun_mult", 0.8)))))
	if st.act != null:
		end_action(target, ctx, "interrupted")
	if kind != WR.Ctrl.BLOCKSTUN:
		st.guarding = false
	st.ctrl = kind
	st.ctrl_tick = 0
	st.ctrl_len = maxi(1, ticks)
	st.ctrl_by = by
	st.buf_btn = 0
	if hard:
		st.cr_until = ctx.tick + ticks + Tuning.cr_ticks
		ctx.emit({"type": "cr", "e": target.entity_id, "until": st.cr_until})
	return kind


static func apply_knockback(f: FighterBody, dir: Vector3, distance: float, ticks: int = -1) -> void:
	dir.y = 0.0
	if dir.length() < 1e-4 or distance <= 0.0:
		return
	dir = dir.normalized()
	var n: int = ticks if ticks > 0 else clampi(int(round(6.0 + distance * 4.0)), 6, 20)
	f.st.knock_vel = dir * (2.0 * distance / (float(n) * WR.TICK_DT))
	f.st.knock_left = n


# ------------------------------------------------------------------------------------------
# facing / guard
# ------------------------------------------------------------------------------------------
static func _update_facing(f: FighterBody, inp: InputFrame) -> void:
	var st: FighterState = f.st
	var max_step: float
	if st.ctrl != WR.Ctrl.NONE and st.ctrl != WR.Ctrl.BLOCKSTUN:
		max_step = 0.0
	elif st.act != null:
		max_step = Behaviors.of(st.act).turn_rate(f)
	else:
		max_step = Tuning.turn_rate_per_tick
	if max_step > 0.0:
		st.yaw = MathX.rotate_toward(st.yaw, inp.yaw, max_step)
	f.apply_yaw()


static func _update_guard(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var want: bool = inp.held(WR.BTN_GUARD)
	var ctrl_ok: bool = st.ctrl == WR.Ctrl.NONE or st.ctrl == WR.Ctrl.BLOCKSTUN
	var act_ok: bool = st.act == null or Behaviors.of(st.act).can_cancel(f, "guard")
	if want and ctrl_ok and act_ok and f.is_on_floor():
		if st.act != null:
			end_action(f, ctx, "guard_cancel")
		if not st.guarding:
			st.guarding = true
			st.guard_tick = 0
			ctx.emit({"type": "guard_up", "e": f.entity_id, "predictable": true})
		else:
			st.guard_tick += 1
	elif st.guarding and (not want or not ctrl_ok):
		st.guarding = false
		st.guard_exit_until = ctx.tick + Tuning.guard_exit_ticks
		ctx.emit({"type": "guard_down", "e": f.entity_id, "predictable": true})


# ------------------------------------------------------------------------------------------
# action starts
# ------------------------------------------------------------------------------------------
static func _try_consume_buffer(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	if st.buf_btn == 0:
		return
	if ctx.tick - st.buf_tick > Tuning.input_buffer_ticks:
		st.buf_btn = 0   # stale intent is dropped, never fired late
		return
	# Behaviours may consume presses themselves (Slip counter, Stand Firm exit).
	if st.act != null and Behaviors.of(st.act).consume_press(f, st.buf_btn, inp, ctx):
		st.buf_btn = 0
		return
	if _try_start(f, st.buf_btn, st.buf_move, inp, ctx):
		st.buf_btn = 0


static func _category_for(btn: int) -> String:
	match btn:
		WR.BTN_LIGHT: return "light"
		WR.BTN_HEAVY: return "heavy"
		WR.BTN_DODGE: return "dodge"
		WR.BTN_JUMP: return "jump"
	return "skill"


static func _try_start(f: FighterBody, btn: int, mv: Vector2, inp: InputFrame, ctx: SimContext) -> bool:
	var st: FighterState = f.st
	if st.ctrl != WR.Ctrl.NONE:
		return false
	var cat: String = _category_for(btn)
	var in_act: bool = st.act != null
	if in_act and not Behaviors.of(st.act).can_cancel(f, cat):
		return false
	var grounded: bool = f.is_on_floor() or st.coyote_left > 0
	var attacking: bool = cat == "light" or cat == "heavy" or cat == "skill"
	if attacking and (st.guarding or ctx.tick < st.guard_exit_until):
		return false
	match cat:
		"jump":
			if st.guarding:
				return false
			if f.def.passive_id == "perch" and grounded and _try_perch(f, ctx):
				return true
			if not grounded:
				return false
			if in_act:
				end_action(f, ctx, "jump_cancel")
			f.velocity.y = f.def.jump_velocity
			st.jumped = true
			st.coyote_left = 0
			st.air_light_used = false
			ctx.emit({"type": "jump", "e": f.entity_id, "predictable": true})
			return true
		"dodge":
			if not grounded or st.stamina < Tuning.dodge_stamina or ctx.tick < int(st.cd_ready.get("dodge", 0)):
				return false
			if st.guarding:
				st.guarding = false
			var dd := CommonActions.dodge()
			start_action(f, dd, ctx, inp)
			spend_stamina(f, Tuning.dodge_stamina, ctx)
			st.cd_ready["dodge"] = ctx.tick + Tuning.dodge_ticks + Tuning.dodge_cooldown
			return true
		"light":
			var aid: String
			if not grounded:
				if st.air_light_used:
					return false
				aid = String(f.def.light_ids.get("air", ""))
			elif mv.x < -0.5:
				aid = String(f.def.light_ids.get("l", ""))
			elif mv.x > 0.5:
				aid = String(f.def.light_ids.get("r", ""))
			else:
				aid = String(f.def.light_ids.get("s", ""))
			var a: ActionDef = f.def.action(aid)
			if a == null:
				return false
			var chained: bool = in_act and st.act.kind == "light"
			if chained and st.chain_count >= Tuning.chain_max:
				return false
			if not chained and ctx.tick - st.chain_last_tick > Tuning.chain_reset_ticks:
				st.chain_count = 0
			st.chain_count += 1
			st.chain_last_tick = ctx.tick
			if not grounded:
				st.air_light_used = true
			start_action(f, a, ctx, inp)
			st.act_finisher = st.chain_count >= Tuning.chain_max
			return true
		"heavy":
			var h: ActionDef = f.def.action(f.def.heavy_id)
			if h == null or not grounded or st.stamina < h.stamina:
				return false
			start_action(f, h, ctx, inp)
			spend_stamina(f, h.stamina, ctx)
			st.chain_count = 0
			return true
		"skill":
			var slot: String = "q" if btn == WR.BTN_Q else ("e" if btn == WR.BTN_E else "r")
			var s: ActionDef = f.def.skill(slot)
			if s == null:
				return false
			if ctx.tick < int(st.cd_ready.get(slot, 0)):
				return false
			if st.stamina < s.stamina:
				return false
			if s.grounded_only and not grounded:
				return false
			start_action(f, s, ctx, inp)
			spend_stamina(f, s.stamina, ctx)
			if Behaviors.of(s).cooldown_on_start():
				st.cd_ready[slot] = ctx.tick + s.cooldown_ticks
			st.chain_count = 0
			return true
	return false


static func start_action(f: FighterBody, a: ActionDef, ctx: SimContext, inp: InputFrame) -> void:
	var st: FighterState = f.st
	if st.act != null:
		end_action(f, ctx, "chained")
	st.act = a
	st.act_tick = 0
	st.act_event += 1
	st.act_phase = ""
	st.act_phase_tick = 0
	st.act_data = {}
	st.act_hit_done = {}
	st.act_prev_pos = {}
	st.act_finisher = false
	st.act_origin_yaw = st.yaw
	if a.kind == "light" or a.kind == "heavy" or a.kind == "skill" or a.kind == "counter":
		if Behaviors.of(a).is_offensive(f):
			st.last_offense_tick = ctx.tick
			end_spawn_protection(f, ctx, "offense")
	Behaviors.of(a).start(f, inp, ctx)
	ctx.emit({"type": "action", "e": f.entity_id, "a": a.id, "ev": st.act_event, "predictable": true})


static func end_action(f: FighterBody, ctx: SimContext, reason: String = "done") -> void:
	var st: FighterState = f.st
	if st.act == null:
		return
	var a: ActionDef = st.act
	Behaviors.of(a).finish(f, ctx, reason)
	st.clear_action()
	if reason == "interrupted":
		ctx.emit({"type": "interrupted", "e": f.entity_id, "a": a.id})


static func spend_stamina(f: FighterBody, amount: float, ctx: SimContext) -> void:
	if amount <= 0.0:
		return
	f.st.stamina = maxf(0.0, f.st.stamina - amount)
	f.st.last_spend_tick = ctx.tick


static func _try_perch(f: FighterBody, ctx: SimContext) -> bool:
	## Nyx passive: scramble onto a designated short ledge (valid landing check).
	var p: Dictionary = f.def.passive_params
	var reach: float = float(p.get("reach", 1.0))
	var feet: Vector3 = f.global_position
	var fwd: Vector3 = f.forward()
	for L in ctx.perch_ledges:
		var a: Vector3 = L["a"]
		var b: Vector3 = L["b"]
		var n: Vector3 = L["normal"]
		var h: float = a.y - feet.y
		if h < float(p.get("min_height", 0.9)) or h > float(p.get("max_height", 2.4)):
			continue
		var d2: float = MathX.point_segment_distance_2d(Vector2(feet.x, feet.z), Vector2(a.x, a.z), Vector2(b.x, b.z))
		if d2 > reach + f.def.hurt_radius:
			continue
		# must be on the climb side and facing the ledge
		if n.dot(feet - Vector3(a.x, feet.y, a.z)) < 0.0:
			continue
		if fwd.dot(-n) < 0.5:
			continue
		# landing point: onto the ledge top, 0.6 m past the edge
		var ab: Vector3 = b - a
		var t: float = clampf((feet - a).dot(ab) / maxf(ab.length_squared(), 1e-6), 0.0, 1.0)
		var edge: Vector3 = a + ab * t
		var land: Vector3 = Vector3(edge.x, a.y, edge.z) - n * (f.def.hurt_radius + 0.35)
		if not ctx.capsule_free_at(land, f.def.hurt_radius, f.def.height, WR.LAYER_WORLD | WR.LAYER_BLOCKER):
			continue
		var start := CommonActions.perch()
		start_action(f, start, ctx, null)
		f.st.act_data = {"from": feet, "to": land, "len": WR.secs_to_ticks(float(p.get("climb_s", 0.45)))}
		ctx.emit({"type": "perch", "e": f.entity_id, "predictable": true})
		return true
	return false


# ------------------------------------------------------------------------------------------
# movement
# ------------------------------------------------------------------------------------------
static func _move(f: FighterBody, inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var was_grounded: bool = f.is_on_floor()
	var vel: Vector3 = f.velocity
	var mode: String = "loco"
	if st.ctrl != WR.Ctrl.NONE and st.ctrl != WR.Ctrl.BLOCKSTUN:
		mode = "ctrl"
	elif st.act != null:
		mode = Behaviors.of(st.act).move_mode(f)
	var dt: float = WR.TICK_DT
	match mode:
		"owned":
			vel = f.velocity  # behaviour set the full velocity this tick
		"ctrl", "planted":
			var hz := Vector3(vel.x, 0, vel.z).move_toward(Vector3.ZERO, Tuning.ground_decel * dt)
			vel.x = hz.x
			vel.z = hz.z
		"curve":
			var cv: Vector3 = Behaviors.of(st.act).curve_velocity(f)
			vel.x = cv.x
			vel.z = cv.z
		_:
			var desired: Vector3 = _desired_velocity(f, inp, ctx)
			var hz2 := Vector3(vel.x, 0, vel.z)
			if was_grounded:
				var rate: float = Tuning.ground_accel if desired.length() > hz2.length() else Tuning.ground_decel
				hz2 = hz2.move_toward(desired, rate * dt)
			else:
				var ac: float = Tuning.air_accel * (0.45 / 0.35 if f.def.passive_id == "lightfoot" else 1.0)
				hz2 = hz2.move_toward(desired * maxf(Tuning.air_control, 0.0) + hz2 * (1.0 - Tuning.air_control), ac * dt)
			vel.x = hz2.x
			vel.z = hz2.z
	if mode != "owned":
		if was_grounded and vel.y <= 0.0:
			vel.y = -0.5
		else:
			vel.y = maxf(vel.y - Tuning.gravity * dt, -Tuning.max_fall_speed)
	# knockback (sim-owned displacement)
	if st.knock_left > 0:
		vel.x += st.knock_vel.x
		vel.z += st.knock_vel.z
		var L: int = st.knock_left
		st.knock_vel *= float(L - 1) / float(L)
		st.knock_left -= 1
	var pre_pos: Vector3 = f.global_position
	f.velocity = vel
	f.move_and_slide()
	_try_step_up(f, pre_pos, vel, was_grounded)
	if st.act != null:
		Behaviors.of(st.act).post_move(f, ctx)
	var now_grounded: bool = f.is_on_floor()
	if now_grounded:
		if not was_grounded:
			_on_land(f, ctx)
		st.air_ticks = 0
		st.coyote_left = Tuning.coyote_ticks
		st.jumped = false
		f.set_meta("safe_pos", f.global_position)
	else:
		st.air_ticks += 1
		if st.coyote_left > 0:
			st.coyote_left -= 1
		if st.jumped:
			st.coyote_left = 0
	st.grounded = now_grounded
	if f.global_position.y < -1.5:
		_recover_fall(f, ctx)


static func _desired_velocity(f: FighterBody, inp: InputFrame, ctx: SimContext) -> Vector3:
	var st: FighterState = f.st
	var mv: Vector2 = inp.move
	if mv.length() < 0.08:
		return Vector3.ZERO
	var dir: Vector3 = MathX.yaw_right(inp.yaw) * mv.x + MathX.yaw_forward(inp.yaw) * mv.y
	var mag: float = minf(1.0, mv.length())
	dir = dir.normalized()
	# strafe / backpedal multipliers relative to the fighter's actual facing (Vex Light Steps)
	var local: Vector3 = MathX.world_dir_to_local(st.yaw, dir)
	var lat2: float = local.x * local.x
	var fw2: float = local.z * local.z
	var mult: float
	if local.z >= 0.0:
		mult = fw2 * 1.0 + lat2 * f.def.strafe_mult
	else:
		mult = fw2 * f.def.backpedal_mult + lat2 * f.def.strafe_mult
	var speed: float = f.def.move_speed * mag * mult
	if st.guarding:
		speed *= Tuning.guard_move_mult
	if ctx.tick < st.landing_slow_until:
		speed *= Tuning.landing_slow_mult
	if st.act != null:
		speed *= Behaviors.of(st.act).loco_speed_mult(f)
	return dir * speed


static func _try_step_up(f: FighterBody, pre_pos: Vector3, vel: Vector3, was_grounded: bool) -> void:
	## Explicit step handling for low curbs (<= step_height) the capsule would otherwise stop at.
	if not was_grounded or not f.is_on_wall():
		return
	var hz := Vector3(vel.x, 0, vel.z)
	if hz.length() < 1.0:
		return
	var moved: float = Vector3(f.global_position.x - pre_pos.x, 0, f.global_position.z - pre_pos.z).length()
	var want: float = hz.length() * WR.TICK_DT
	if moved > want * 0.6:
		return
	var up := Vector3(0, Tuning.step_height, 0)
	var fwd: Vector3 = hz.normalized() * maxf(want, 0.12)
	var t0: Transform3D = f.global_transform
	t0.origin = pre_pos
	if f.test_move(t0, up):
		return
	var t1: Transform3D = t0.translated(up)
	if f.test_move(t1, fwd):
		return
	var t2: Transform3D = t1.translated(fwd)
	var col := KinematicCollision3D.new()
	if f.test_move(t2, Vector3(0, -Tuning.step_height - 0.05, 0), col):
		var n: Vector3 = col.get_normal()
		if n.angle_to(Vector3.UP) <= Tuning.floor_max_angle:
			f.global_position = t2.origin + col.get_travel()
			f.apply_floor_snap()


static func _on_land(f: FighterBody, ctx: SimContext) -> void:
	var st: FighterState = f.st
	st.air_light_used = false
	var keep_momentum: bool = f.def.passive_id == "lightfoot" and not bool(f.def.passive_param("landing_slow", false))
	if st.air_ticks > 15 and st.act == null and not keep_momentum:
		st.landing_slow_until = ctx.tick + Tuning.landing_slow_ticks
	ctx.emit({"type": "land", "e": f.entity_id, "air": st.air_ticks, "predictable": true})
	if st.act != null:
		Behaviors.of(st.act).on_land(f, ctx)


static func _recover_fall(f: FighterBody, ctx: SimContext) -> void:
	## Anything that leaves the fighting surface (canal, out of bounds) is returned to the last
	## safe grounded position — water is scenery, never a lethal ring-out (REFERENCE_AUDIT A8).
	var safe: Vector3 = f.get_meta("safe_pos", Vector3.ZERO)
	f.global_position = safe + Vector3(0, 0.1, 0)
	f.velocity = Vector3.ZERO
	f.st.knock_left = 0
	ctx.emit({"type": "fall_recovered", "e": f.entity_id})


static func _ko_physics(f: FighterBody) -> void:
	var v: Vector3 = f.velocity
	v.x = 0.0
	v.z = 0.0
	v.y = -0.5 if f.is_on_floor() else maxf(v.y - Tuning.gravity * WR.TICK_DT, -Tuning.max_fall_speed)
	f.velocity = v
	f.move_and_slide()
