class_name CombatResolver
extends RefCounted
## Step 6 of the authoritative tick (D-005, D-011, D-012): gathers every swept hit candidate,
## sorts deterministically, and resolves protection → evasion → parry → grab → guard → hit.


static func resolve(ctx: SimContext) -> void:
	var cands: Array = []
	var ordered: Array = ctx.fighters.duplicate()
	ordered.sort_custom(func(x: FighterBody, y: FighterBody) -> bool: return x.entity_id < y.entity_id)
	for f: FighterBody in ordered:
		if not f.present or not f.st.alive or f.st.act == null:
			continue
		var beh: ActionBehavior = Behaviors.of(f.st.act)
		for h: HitDef in f.st.act.hits:
			if not beh.hit_active(f, h):
				f.st.act_prev_pos.erase(h.index)
				continue
			var t_s: float = beh.hit_time_s(f, h)
			var p1: Vector3 = MathX.local_to_world(f.global_position, f.st.yaw, h.local_pos_at(t_s))
			var p0: Vector3
			if f.st.act_prev_pos.has(h.index):
				p0 = f.st.act_prev_pos[h.index]
			else:
				p0 = MathX.local_to_world(f.global_position, f.st.yaw, h.local_pos_at(maxf(0.0, t_s - WR.TICK_DT)))
			f.st.act_prev_pos[h.index] = p1
			var rewind: int = 0 if ctx.predicting else ctx.rewind_ticks(f)
			for t: FighterBody in ordered:
				if t == f or t.team == f.team or not t.can_be_hit():
					continue   # no friendly fire (D-010)
				var key: String = "%d:%d" % [h.index, t.entity_id]
				if f.st.act_hit_done.has(key):
					continue
				var tfeet: Vector3 = t.position_at_tick(ctx.tick - rewind) if rewind > 0 else t.global_position
				var seg: Array = t.hurt_segment_at(tfeet)
				var cp: Array = MathX.closest_points_segments(p0, p1, seg[0], seg[1])
				var dist: float = (cp[0] as Vector3).distance_to(cp[1] as Vector3)
				if dist > h.radius + float(seg[2]):
					continue
				if h.low and not t.st.grounded and t.st.air_ticks > 2:
					continue   # low sweeps pass under airborne targets
				if ctx.ray_blocked(f.chest_position(), cp[1]):
					continue   # no hits through walls
				cands.append({"att": f, "tgt": t, "hit": h, "key": key, "ev": f.st.act_event,
					"point": (cp[0] as Vector3).lerp(cp[1] as Vector3, 0.5)})
	if cands.is_empty():
		return
	cands.sort_custom(func(x: Dictionary, y: Dictionary) -> bool:
		var ax: int = (x["att"] as FighterBody).entity_id
		var ay: int = (y["att"] as FighterBody).entity_id
		if ax != ay:
			return ax < ay
		if int(x["ev"]) != int(y["ev"]):
			return int(x["ev"]) < int(y["ev"])
		if (x["hit"] as HitDef).index != (y["hit"] as HitDef).index:
			return (x["hit"] as HitDef).index < (y["hit"] as HitDef).index
		return (x["tgt"] as FighterBody).entity_id < (y["tgt"] as FighterBody).entity_id)
	var parried: Dictionary = {}
	for c in cands:
		var att: FighterBody = c["att"]
		if parried.has(att.entity_id):
			continue
		if ctx.predicting:
			_predict_one(c, ctx)
		else:
			if _resolve_one(c, ctx) == "parried":
				parried[att.entity_id] = true


static func _predict_one(c: Dictionary, ctx: SimContext) -> void:
	## Client prediction: cosmetic, deduplicated by (attacker, action event, hit, target).
	var att: FighterBody = c["att"]
	att.st.act_hit_done[c["key"]] = true
	ctx.emit({"type": "predicted_hit", "a": att.entity_id, "t": (c["tgt"] as FighterBody).entity_id,
		"ev": c["ev"], "hi": (c["hit"] as HitDef).index, "p": c["point"], "predictable": true})


static func _resolve_one(c: Dictionary, ctx: SimContext) -> String:
	var att: FighterBody = c["att"]
	var tgt: FighterBody = c["tgt"]
	var h: HitDef = c["hit"]
	var key: String = c["key"]
	if not tgt.st.alive or att.st.act == null or att.st.act_hit_done.has(key):
		return "skip"
	var base := {"a": att.entity_id, "t": tgt.entity_id, "ev": c["ev"], "hi": h.index, "p": c["point"]}
	# 1. spawn protection
	if tgt.st.spawn_protected:
		att.st.act_hit_done[key] = true
		ctx.emit(_merge(base, {"type": "protected"}))
		return "protected"
	# 2. evasion windows (dodge, slip, feint step, get-up)
	if is_evading(tgt):
		att.st.act_hit_done[key] = true
		ctx.emit(_merge(base, {"type": "evaded"}))
		return "evaded"
	# 3. parry (Scrap only: behaviour provides the window)
	if h.parryable and tgt.st.act != null:
		var tb: ActionBehavior = Behaviors.of(tgt.st.act)
		if tb.in_parry_window(tgt) and _facing_within(tgt, att, (tb as ParryBehavior).parry_arc_half(tgt)):
			att.st.act_hit_done[key] = true
			tb.on_parry_success(tgt, att, ctx)
			ctx.emit(_merge(base, {"type": "parry"}))
			return "parried"
	# 4. grabs ignore guard
	if h.effect == WR.Effect.GRAB:
		att.st.act_hit_done[key] = true
		Behaviors.of(att.st.act).on_hit(att, tgt, h, ctx)
		return "grab"
	# 5. guard
	var g: Dictionary = guard_info(tgt, att)
	if not h.unblockable and g["active"]:
		att.st.act_hit_done[key] = true
		var cost: float = h.guard_damage * float(g["stamina_mult"])
		FighterLogic.spend_stamina(tgt, cost, ctx)
		var push_dir: Vector3 = tgt.global_position - att.global_position
		FighterLogic.apply_knockback(tgt, push_dir, h.knockback * Tuning.block_push_mult * float(g["kb_mult"]) * _grounded_mult(tgt, h))
		var heavy_like: bool = att.st.act.kind == "heavy" or h.guard_damage >= 20.0
		if tgt.st.stamina <= 0.0:
			guard_break(tgt, att, ctx)
			ctx.emit(_merge(base, {"type": "guard_break", "cost": cost}))
		else:
			if tgt.st.act == null:
				tgt.st.ctrl = WR.Ctrl.BLOCKSTUN
				tgt.st.ctrl_tick = 0
				tgt.st.ctrl_len = Tuning.block_stun_heavy if heavy_like else Tuning.block_stun_light
			ctx.emit(_merge(base, {"type": "block", "cost": cost, "heavy": heavy_like, "stance": g.get("stance", false)}))
		Behaviors.of(att.st.act).on_blocked(att, tgt, h, ctx)
		return "blocked"
	# 6. clean hit
	att.st.act_hit_done[key] = true
	apply_damage(tgt, h.damage, att, ctx)
	var kind: int = WR.Ctrl.FLINCH
	match h.effect:
		WR.Effect.STAGGER: kind = WR.Ctrl.STAGGER
		WR.Effect.KNOCKDOWN: kind = WR.Ctrl.KNOCKDOWN
		_: kind = WR.Ctrl.FLINCH
	var applied: int = WR.Ctrl.NONE
	if h.stun_ticks > 0:
		applied = FighterLogic.apply_control(tgt, kind, h.stun_ticks, ctx, att.entity_id)
	var dir: Vector3
	if h.kb_radial:
		dir = tgt.global_position - att.global_position
	elif h.push_along_motion:
		dir = Vector3(att.velocity.x, 0, att.velocity.z)
		if dir.length() < 0.1:
			dir = att.forward()
	else:
		dir = att.forward()
	var kb: float = h.knockback
	if att.st.act_finisher and att.st.act.kind == "light":
		kb *= Tuning.finisher_kb_mult
	kb *= _grounded_mult(tgt, h)
	if applied == WR.Ctrl.FLINCH and kind != WR.Ctrl.FLINCH:
		kb *= Tuning.cr_disp_mult   # downgraded by control resistance
	FighterLogic.apply_knockback(tgt, dir, kb)
	var heavy: bool = att.st.act.kind == "heavy" or h.damage >= 30.0
	ctx.emit(_merge(base, {"type": "hit", "dmg": h.damage, "heavy": heavy, "effect": applied, "kb": kb}))
	if att.st.act != null:
		Behaviors.of(att.st.act).on_hit(att, tgt, h, ctx)
	return "hit"


static func _merge(a: Dictionary, b: Dictionary) -> Dictionary:
	var d: Dictionary = a.duplicate()
	d.merge(b, true)
	return d


static func _grounded_mult(tgt: FighterBody, h: HitDef) -> float:
	## Bruno passive "Grounded": light pushes move him half as far; major control unaffected.
	if tgt.def.passive_id != "grounded":
		return 1.0
	if h.effect == WR.Effect.FLINCH and h.knockback <= float(tgt.def.passive_param("light_push_max", 1.5)):
		return float(tgt.def.passive_param("light_push_mult", 0.5))
	return 1.0


static func is_evading(t: FighterBody) -> bool:
	if t.st.ctrl == WR.Ctrl.GETUP and t.st.ctrl_tick < Tuning.getup_evade_ticks:
		return true
	if t.st.act != null and Behaviors.of(t.st.act).is_evading(t):
		return true
	return false


static func _facing_within(defender: FighterBody, attacker: FighterBody, arc_half: float) -> bool:
	var to: Vector3 = attacker.global_position - defender.global_position
	to.y = 0.0
	if to.length() < 0.05:
		return true
	return defender.forward().angle_to(to.normalized()) <= arc_half


static func guard_info(t: FighterBody, attacker: FighterBody) -> Dictionary:
	## Frontal guard: basic guard (±60°) or an action-provided guard (Stand Firm ±90°).
	var info := {"active": false, "stamina_mult": 1.0, "kb_mult": 1.0}
	if t.st.ctrl == WR.Ctrl.GUARD_BREAK:
		return info
	var arc: float = -1.0
	if t.st.guarding and (t.st.ctrl == WR.Ctrl.NONE or t.st.ctrl == WR.Ctrl.BLOCKSTUN):
		arc = Tuning.guard_arc_half
	if t.st.act != null:
		var gm: Dictionary = Behaviors.of(t.st.act).guard_mod(t)
		if not gm.is_empty():
			arc = float(gm["arc_half"])
			info["stamina_mult"] = gm["stamina_mult"]
			info["kb_mult"] = gm["kb_mult"]
			info["stance"] = true
	if arc < 0.0:
		return info
	info["active"] = _facing_within(t, attacker, arc)
	return info


static func guard_break(t: FighterBody, by: FighterBody, ctx: SimContext) -> void:
	t.st.stamina = 0.0
	t.st.guarding = false
	FighterLogic.apply_control(t, WR.Ctrl.GUARD_BREAK, Tuning.guard_break_ticks, ctx, by.entity_id)


static func apply_damage(tgt: FighterBody, amount: float, att: FighterBody, ctx: SimContext) -> void:
	if amount <= 0.0 or not tgt.st.alive:
		return
	var before: float = tgt.st.health
	if tgt.is_dummy and tgt.has_meta("invulnerable") and bool(tgt.get_meta("invulnerable")):
		before = before  # training dummies can be set to not lose health
	else:
		tgt.st.health = maxf(0.0, before - amount)
	tgt.st.last_damage_tick = ctx.tick
	tgt.st.last_hit_by = att.entity_id
	tgt.st.last_hit_tick = ctx.tick
	att.st.damage_dealt += before - tgt.st.health
	att.st.last_offense_tick = ctx.tick
