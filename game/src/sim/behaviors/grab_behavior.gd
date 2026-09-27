class_name GrabBehavior
extends ActionBehavior
## Scrap R "Turnabout": brief contact grapple that swings the opponent to Scrap's other side
## and releases them. Guard does not stop it; dodging does. A hit on Scrap during the grapple
## breaks it. Landing space is validated (capsule overlap + floor + no wall between) and the
## victim is moved with collision, so it can never be pulled through a wall.


func start(f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	f.st.set_phase("reach")
	f.st.act_data = {"victim": -1}


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	match st.act_phase:
		"reach":
			var h: HitDef = a.hits[0] if not a.hits.is_empty() else null
			if h != null and st.act_tick >= h.t1:
				st.act_data["len"] = a.pticks("whiff_recover_s", 0.5)
				st.set_phase("whiff")
		"grapple":
			var victim: FighterBody = _victim(f, ctx)
			if victim == null or not victim.st.alive or victim.st.ctrl != WR.Ctrl.GRABBED:
				st.act_data["len"] = a.pticks("hit_recover_s", 0.3)
				st.act_data["victim"] = -1
				st.set_phase("release")
				return
			var n: int = a.pticks("grapple_s", 0.45)
			var u: float = clampf(float(st.act_phase_tick + 1) / float(n), 0.0, 1.0)
			# Scrap pivots 180° over the grapple
			st.yaw = wrapf(float(st.act_data["yaw0"]) + PI * u, -PI, PI)
			f.apply_yaw()
			# victim follows an arc around Scrap toward the validated destination
			var c: Vector3 = f.global_position
			var r0: float = float(st.act_data["r0"])
			var r1: float = float(st.act_data["r1"])
			var ang0: float = float(st.act_data["ang0"])
			var dang: float = float(st.act_data["dang"])
			var ang: float = ang0 + dang * u
			var rr: float = lerpf(r0, r1, u)
			var target_p: Vector3 = c + Vector3(sin(ang), 0, cos(ang)) * rr
			target_p.y = victim.global_position.y
			victim.move_and_collide(target_p - victim.global_position)
			victim.st.yaw = MathX.yaw_from_dir((c - victim.global_position).normalized()) if (c - victim.global_position).length() > 0.05 else victim.st.yaw
			victim.apply_yaw()
			if st.act_phase_tick >= n - 1:
				_release(f, victim, ctx, true)
		"release", "whiff":
			if st.act_phase_tick >= int(st.act_data.get("len", 20)) - 1:
				FighterLogic.end_action(f, ctx, "done")


func _victim(f: FighterBody, ctx: SimContext) -> FighterBody:
	var vid: int = int(f.st.act_data.get("victim", -1))
	for o in ctx.fighters:
		if o.entity_id == vid:
			return o
	return null


func on_hit(f: FighterBody, target: FighterBody, _h: HitDef, ctx: SimContext) -> void:
	## Grab contact (unblockable by guard; dodge/spawn protection handled by the resolver).
	var st: FighterState = f.st
	var a: ActionDef = st.act
	if st.act_phase != "reach":
		return
	var applied: int = FighterLogic.apply_control(target, WR.Ctrl.GRABBED, a.pticks("grapple_s", 0.45) + 12, ctx, f.entity_id)
	if applied != WR.Ctrl.GRABBED:
		# control resistance: no grapple, target only flinches
		st.act_data["len"] = a.pticks("hit_recover_s", 0.3)
		st.set_phase("release")
		ctx.emit({"type": "grab_resisted", "e": f.entity_id, "t": target.entity_id})
		return
	var dest: Variant = _choose_destination(f, target, ctx)
	var c: Vector3 = f.global_position
	var v0: Vector3 = target.global_position - c
	v0.y = 0.0
	var ang0: float = atan2(v0.x, v0.z)
	var r0: float = maxf(0.6, v0.length())
	var dang: float = 0.0
	var r1: float = r0
	if dest != null:
		var v1: Vector3 = (dest as Vector3) - c
		v1.y = 0.0
		var ang1: float = atan2(v1.x, v1.z)
		dang = wrapf(ang1 - ang0, -PI, PI)
		if absf(dang) < 0.01:
			dang = PI
		r1 = v1.length()
	st.act_data = {"victim": target.entity_id, "yaw0": st.yaw, "ang0": ang0, "dang": dang, "r0": r0, "r1": r1,
		"placed": dest != null}
	st.set_phase("grapple")
	ctx.emit({"type": "grab", "e": f.entity_id, "t": target.entity_id, "predictable": false})


func _choose_destination(f: FighterBody, target: FighterBody, ctx: SimContext) -> Variant:
	var a: ActionDef = f.st.act
	var dist: float = float(a.param("place_distance", 1.3))
	var base_dir: Vector3 = -f.forward()
	var candidates: Array = [0.0]
	for d in a.param("alt_angles_deg", [45, -45, 90, -90, 135, -135]):
		candidates.append(deg_to_rad(float(d)))
	var chest_off := Vector3(0, target.def.height * 0.6, 0)
	for off in candidates:
		var dir: Vector3 = base_dir.rotated(Vector3.UP, float(off))
		var p: Vector3 = f.global_position + dir * (dist + target.def.hurt_radius)
		var ground: Variant = ctx.ground_below(p + Vector3(0, 0.6, 0), 1.4)
		if ground == null:
			continue
		var g: Vector3 = ground
		if absf(g.y - f.global_position.y) > 0.5:
			continue
		if not ctx.capsule_free_at(g, target.def.hurt_radius, target.def.height, WR.LAYER_WORLD | WR.LAYER_BLOCKER | WR.fighter_collision_mask(target.team)):
			continue
		if ctx.ray_blocked(f.chest_position(), g + chest_off, WR.LAYER_WORLD | WR.LAYER_BLOCKER):
			continue
		return g
	return null


func _release(f: FighterBody, victim: FighterBody, ctx: SimContext, completed: bool) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	if victim != null and victim.st.ctrl == WR.Ctrl.GRABBED:
		victim.st.ctrl = WR.Ctrl.STAGGER if completed else WR.Ctrl.FLINCH
		victim.st.ctrl_tick = 0
		victim.st.ctrl_len = a.pticks("release_stun_s", 0.35) if completed else 6
		if completed and not ctx.predicting:
			CombatResolver.apply_damage(victim, float(a.param("damage", 12.0)), f, ctx)
			ctx.emit({"type": "hit", "a": f.entity_id, "t": victim.entity_id, "dmg": float(a.param("damage", 12.0)),
				"ev": st.act_event, "hi": 0, "kind": "grab_release", "p": victim.chest_position()})
	st.act_data["victim"] = -1
	st.act_data["len"] = a.pticks("hit_recover_s", 0.3)
	st.set_phase("release")


func finish(f: FighterBody, ctx: SimContext, _reason: String) -> void:
	# Interrupted mid-grapple (e.g. an ally hit Scrap): release the victim in place.
	if f.st.act_phase == "grapple":
		var v: FighterBody = _victim(f, ctx)
		if v != null and v.st.ctrl == WR.Ctrl.GRABBED:
			v.st.ctrl = WR.Ctrl.FLINCH
			v.st.ctrl_tick = 0
			v.st.ctrl_len = 6
			ctx.emit({"type": "grab_broken", "e": f.entity_id, "t": v.entity_id})


func hit_active(f: FighterBody, h: HitDef) -> bool:
	return f.st.act_phase == "reach" and f.st.act_tick >= h.t0 and f.st.act_tick < h.t1


func move_mode(_f: FighterBody) -> String:
	return "planted"


func turn_rate(f: FighterBody) -> float:
	return f.st.act.turn_rate_at(f.st.act_tick) if f.st.act_phase == "reach" else 0.0


func can_cancel(_f: FighterBody, _c: String) -> bool:
	return false


func exposed(f: FighterBody) -> bool:
	return f.st.act_phase == "whiff" or f.st.act_phase == "reach"


func anim(f: FighterBody) -> Array:
	var ph: String = f.st.act_phase
	return [clip_name(f, ph, "skill_r_" + ph), float(f.st.act_phase_tick) * WR.TICK_DT]
