class_name BarkBehavior
extends ActionBehavior
## Bruno E "Warning Bark": telegraphed short cone. Interrupts enemies caught in exposed
## actions (startup/recovery), pushes everyone in the cone back. No damage. Walls block it
## (line of sight), frontal guard absorbs it (stamina cost), control resistance prevents the
## interrupt and halves the push.


func start(f: FighterBody, _inp: InputFrame, _ctx: SimContext) -> void:
	f.st.set_phase("inhale")
	f.st.act_data = {"fired": false}


func step(f: FighterBody, _inp: InputFrame, ctx: SimContext) -> void:
	var st: FighterState = f.st
	var a: ActionDef = st.act
	if not bool(st.act_data["fired"]) and st.act_tick >= a.pticks("trigger_s", 0.35):
		st.act_data["fired"] = true
		st.set_phase("bark")
		_fire(f, ctx)
	if st.act_tick >= a.total_ticks - 1:
		FighterLogic.end_action(f, ctx, "done")


func _fire(f: FighterBody, ctx: SimContext) -> void:
	var a: ActionDef = f.st.act
	var affected: Array = []
	ctx.emit({"type": "skill_fx", "e": f.entity_id, "fx": "bruno_bark", "predictable": true})
	if ctx.predicting:
		return
	var rng: float = float(a.param("range", 5.0))
	var half: float = deg_to_rad(float(a.param("cone_deg", 60.0)) * 0.5)
	var head: Vector3 = f.head_position()
	var fwd: Vector3 = f.forward()
	var ordered: Array = ctx.enemies_of(f)
	ordered.sort_custom(func(x: FighterBody, y: FighterBody) -> bool: return x.entity_id < y.entity_id)
	for t: FighterBody in ordered:
		var to: Vector3 = t.chest_position() - head
		var to_h := Vector3(to.x, 0, to.z)
		if to_h.length() > rng + t.def.hurt_radius:
			continue
		if to_h.length() > 0.05 and fwd.angle_to(to_h.normalized()) > half:
			continue
		if ctx.ray_blocked(head, t.chest_position()):
			continue
		if t.st.spawn_protected:
			continue
		var tb: ActionBehavior = Behaviors.of(t.st.act) if t.st.act != null else null
		if tb != null and tb.is_evading(t):
			continue
		var away: Vector3 = to_h.normalized() if to_h.length() > 0.05 else fwd
		var cr: bool = t.st.has_cr(ctx.tick)
		var disp_mult: float = Tuning.cr_disp_mult if cr else 1.0
		var ginfo: Dictionary = CombatResolver.guard_info(t, f)
		if ginfo["active"]:
			FighterLogic.spend_stamina(t, float(a.param("guard_stamina", 15.0)) * float(ginfo["stamina_mult"]), ctx)
			FighterLogic.apply_knockback(t, away, float(a.param("guard_push", 0.3)) * float(ginfo["kb_mult"]))
			if t.st.stamina <= 0.0:
				CombatResolver.guard_break(t, f, ctx)
			affected.append([t.entity_id, "guarded"])
			continue
		var exposed: bool = tb != null and tb.exposed(t)
		if exposed and not cr:
			FighterLogic.apply_control(t, WR.Ctrl.FLINCH, a.pticks("interrupt_stun_s", 0.35), ctx, f.entity_id)
			t.st.cr_until = ctx.tick + a.pticks("interrupt_stun_s", 0.35) + Tuning.cr_ticks  # bark interrupt is hard control (D-010)
			FighterLogic.apply_knockback(t, away, float(a.param("push_exposed", 1.5)) * disp_mult)
			affected.append([t.entity_id, "interrupted"])
		else:
			FighterLogic.apply_knockback(t, away, float(a.param("push_other", 1.0)) * disp_mult * _grounded_mult(t))
			affected.append([t.entity_id, "pushed"])
	ctx.emit({"type": "bark", "e": f.entity_id, "affected": affected})


func _grounded_mult(t: FighterBody) -> float:
	if t.def.passive_id == "grounded":
		return float(t.def.passive_param("light_push_mult", 0.5))
	return 1.0


func can_cancel(_f: FighterBody, _c: String) -> bool:
	return false


func is_offensive(_f: FighterBody) -> bool:
	return true


func exposed(_f: FighterBody) -> bool:
	return true


func anim(f: FighterBody) -> Array:
	return [f.st.act.clip if f.st.act.clip != "" else "skill_e", float(f.st.act_tick) * WR.TICK_DT]
