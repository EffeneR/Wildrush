class_name VfxDirector
extends Node3D
## Pooled presentation effects and event sounds (spec §9): impact sparks, block/parry/guard
## break rings, knockout puffs, respawn columns, skill flourishes and footsteps. Purely
## cosmetic — driven by host events and view states; never affects the simulation.
## Respects Settings access/reduced_effects (fewer particles, no bright flashes).

const RING_SHADER: Shader = preload("res://src/present/shaders/shock_ring.gdshader")
const SPARK_POOL: int = 24
const RING_POOL: int = 24

var views: Dictionary = {}            # e -> FighterView (set by the match scene)
var layout: ArenaLayout = null
var local_entity: int = -1
var camera_rig: CameraRig = null
var hud: Node = null                  # optional: damage numbers (has method show_damage)
var _sparks: Array[CPUParticles3D] = []
var _spark_i: int = 0
var _rings: Array = []                # [{mi, mat, t, dur, grow, billboard}]
var _ring_i: int = 0
var _foot_acc: Dictionary = {}        # e -> metres since last step
var _foot_prev: Dictionary = {}
var reduced: bool = false


func _ready() -> void:
	reduced = bool(Settings.get_value("access", "reduced_effects"))
	Settings.changed.connect(func(s: String) -> void:
		if s == "access":
			reduced = bool(Settings.get_value("access", "reduced_effects")))
	for i in range(SPARK_POOL):
		var p := CPUParticles3D.new()
		p.emitting = false
		p.one_shot = true
		p.explosiveness = 0.95
		p.amount = 18
		p.lifetime = 0.35
		p.direction = Vector3(0, 1, 0)
		p.spread = 70.0
		p.initial_velocity_min = 2.5
		p.initial_velocity_max = 6.0
		p.gravity = Vector3(0, -9.0, 0)
		p.scale_amount_min = 0.03
		p.scale_amount_max = 0.07
		var qm := QuadMesh.new()
		qm.size = Vector2(1, 1)
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		m.vertex_color_use_as_albedo = true
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		qm.material = m
		p.mesh = qm
		var grad := Gradient.new()
		grad.set_color(0, Color(1, 1, 1, 1))
		grad.set_color(1, Color(1, 1, 1, 0))
		p.color_ramp = grad
		add_child(p)
		_sparks.append(p)
	for i in range(RING_POOL):
		var mi := MeshInstance3D.new()
		var q := QuadMesh.new()
		q.size = Vector2(1, 1)
		mi.mesh = q
		var mat := ShaderMaterial.new()
		mat.shader = RING_SHADER
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.visible = false
		add_child(mi)
		_rings.append({"mi": mi, "mat": mat, "t": 1.0, "dur": 0.3, "grow": 1.0, "base": 1.0, "billboard": false})


# ------------------------------------------------------------------------------------------
# primitives
# ------------------------------------------------------------------------------------------
func sparks(pos: Vector3, color: Color, amount: int = 18, speed: float = 5.0, up: Vector3 = Vector3.UP, gravity: float = -9.0) -> void:
	var p: CPUParticles3D = _sparks[_spark_i]
	_spark_i = (_spark_i + 1) % _sparks.size()
	p.global_position = pos
	p.amount = maxi(4, amount / 2 if reduced else amount)
	p.color = color
	p.direction = up
	p.initial_velocity_min = speed * 0.5
	p.initial_velocity_max = speed
	p.gravity = Vector3(0, gravity, 0)
	p.restart()
	p.emitting = true


func ring(pos: Vector3, color: Color, size: float, dur: float, ground: bool = true, kind: int = 0) -> void:
	if reduced and kind == 1:
		color.a *= 0.4
	var r: Dictionary = _rings[_ring_i]
	_ring_i = (_ring_i + 1) % _rings.size()
	var mi: MeshInstance3D = r["mi"]
	mi.visible = true
	mi.global_position = pos + (Vector3(0, 0.06, 0) if ground else Vector3.ZERO)
	var q: QuadMesh = mi.mesh
	q.orientation = PlaneMesh.FACE_Y if ground else PlaneMesh.FACE_Z
	(r["mat"] as ShaderMaterial).set_shader_parameter("color", color)
	(r["mat"] as ShaderMaterial).set_shader_parameter("kind", kind)
	r["t"] = 0.0
	r["dur"] = dur
	r["base"] = size
	r["billboard"] = not ground
	mi.scale = Vector3.ONE * size


func _process(dt: float) -> void:
	var cam: Camera3D = get_viewport().get_camera_3d()
	for r in _rings:
		if float(r["t"]) >= 1.0:
			continue
		r["t"] = minf(1.0, float(r["t"]) + dt / float(r["dur"]))
		var mi: MeshInstance3D = r["mi"]
		(r["mat"] as ShaderMaterial).set_shader_parameter("life", float(r["t"]))
		if bool(r["billboard"]) and cam != null:
			mi.look_at(cam.global_position, Vector3.UP)
			mi.rotate_object_local(Vector3.UP, PI)
		if float(r["t"]) >= 1.0:
			mi.visible = false


# ------------------------------------------------------------------------------------------
# events
# ------------------------------------------------------------------------------------------
func _pos_of(e: int, height: float = 1.0) -> Vector3:
	var v: FighterView = views.get(e)
	if v == null:
		return Vector3.INF
	return v.global_position + Vector3(0, v.def.height * height, 0)


func _near(pos: Vector3, r: float = 60.0) -> bool:
	var cam: Camera3D = get_viewport().get_camera_3d()
	return cam != null and pos != Vector3.INF and cam.global_position.distance_to(pos) < r


func handle(evs: Array) -> void:
	for e in evs:
		var t: String = String(e.get("type", ""))
		match t:
			"hit", "predicted_hit":
				_on_hit(e, t == "predicted_hit")
			"block":
				var pb: Vector3 = e.get("p", _pos_of(int(e.get("t", -1)), 0.7))
				sparks(pb, Color(0.7, 0.85, 1.0), 14, 4.0)
				ring(pb, Color(0.6, 0.8, 1.0, 0.9), 1.1, 0.22, false)
				_flash_target(int(e.get("t", -1)), Color(0.55, 0.75, 1.0), 0.5)
				AudioDirector.play_at("guard_block", pb)
			"guard_break":
				var pg: Vector3 = _pos_of(int(e.get("t", -1)), 0.75)
				sparks(pg, Color(1.0, 0.8, 0.3), 30, 7.0)
				ring(pg, Color(1.0, 0.75, 0.25), 2.4, 0.4, false)
				_flash_target(int(e.get("t", -1)), Color(1.0, 0.7, 0.2), 1.0)
				AudioDirector.play_at("guard_break", pg)
				_shake_if_local(int(e.get("t", -1)), 0.6)
			"parry":
				var pp: Vector3 = e.get("p", _pos_of(int(e.get("t", -1)), 0.7))
				sparks(pp, Color(1.0, 0.95, 0.6), 26, 6.5)
				ring(pp, Color(1.0, 0.92, 0.55), 1.8, 0.3, false)
				ring(pp, Color(1.0, 1.0, 0.9, 0.8), 0.9, 0.12, false, 1)
				AudioDirector.play_at("parry", pp)
			"evaded":
				var pe: Vector3 = _pos_of(int(e.get("t", -1)), 0.6)
				ring(pe, Color(0.8, 0.9, 1.0, 0.5), 1.2, 0.25, false)
			"protected":
				var pr: Vector3 = _pos_of(int(e.get("t", -1)), 0.7)
				ring(pr, Color(0.75, 0.9, 1.0, 0.7), 1.4, 0.3, false)
			"ko":
				var pk: Vector3 = _pos_of(int(e.get("e", -1)), 0.4)
				if pk != Vector3.INF:
					sparks(pk, Color(0.85, 0.82, 0.75), 30, 2.5, Vector3.UP, -1.0)
					ring(pk - Vector3(0, 0.4, 0), Color(0.9, 0.9, 0.85, 0.6), 2.6, 0.6)
					AudioDirector.play_at("knockout", pk)
				_shake_if_local(int(e.get("e", -1)), 0.5)
			"respawn":
				var ps: Vector3 = _pos_of(int(e.get("e", -1)), 0.0)
				if ps != Vector3.INF:
					ring(ps, Color(0.7, 0.9, 1.0, 0.9), 2.2, 0.8)
					sparks(ps + Vector3(0, 0.3, 0), Color(0.75, 0.9, 1.0), 20, 3.5, Vector3.UP, 2.0)
					AudioDirector.play_at("respawn", ps)
			"skill_fx":
				_skill_fx(e)
			"action":
				_on_action(e)
			"jump":
				var pj: Vector3 = _pos_of(int(e.get("e", -1)), 0.0)
				if _near(pj, 30.0):
					AudioDirector.play_at("jump", pj)
			"land":
				var pl: Vector3 = _pos_of(int(e.get("e", -1)), 0.0)
				if _near(pl, 30.0):
					AudioDirector.play_at("land_" + _surface(pl), pl)
					if int(e.get("air", 0)) > 30:
						ring(pl, Color(0.8, 0.75, 0.65, 0.5), 1.6, 0.35)
			"bark":
				pass
			"grab":
				var pgr: Vector3 = _pos_of(int(e.get("t", -1)), 0.8)
				AudioDirector.play_at("grab", pgr)
			"wall_bump":
				var pw: Vector3 = _pos_of(int(e.get("e", -1)), 0.8)
				sparks(pw, Color(0.8, 0.75, 0.65), 20, 3.0)
				AudioDirector.play_at("hit_heavy", pw, -6.0)


func _on_hit(e: Dictionary, predicted: bool) -> void:
	var p: Vector3 = e.get("p", _pos_of(int(e.get("t", -1)), 0.7))
	if p == Vector3.INF:
		return
	var heavy: bool = bool(e.get("heavy", false))
	if predicted:
		# client-side confirm cue for the attacker only (the server hit follows ~RTT later)
		sparks(p, Color(1.0, 0.95, 0.8), 8, 3.5)
		return
	if bool(e.get("confirmed_predicted", false)):
		# already shown as a predicted hit: add the weight (sound/flash) without double sparks
		_flash_target(int(e.get("t", -1)), Color(1, 1, 1), 0.8 if heavy else 0.55)
	else:
		sparks(p, Color(1.0, 0.72, 0.3) if heavy else Color(1.0, 0.95, 0.75), 26 if heavy else 16, 7.0 if heavy else 5.0)
		ring(p, Color(1.0, 0.9, 0.7, 0.85), 1.2 if heavy else 0.8, 0.14, false, 1)
		_flash_target(int(e.get("t", -1)), Color(1, 1, 1), 0.8 if heavy else 0.55)
	var tv: FighterView = views.get(int(e.get("t", -1)))
	var av: FighterView = views.get(int(e.get("a", -1)))
	if tv != null and av != null:
		var to_att: Vector3 = av.global_position - tv.global_position
		tv.hit_from_behind = to_att.dot(MathX.yaw_forward(tv.rotation.y)) < 0.0
	AudioDirector.play_at("hit_heavy" if heavy else "hit_light", p)
	if heavy and int(e.get("effect", 0)) == WR.Effect.KNOCKDOWN:
		AudioDirector.play_at("body_fall", p - Vector3(0, 0.8, 0), -3.0)
	_shake_if_local(int(e.get("t", -1)), 0.45 if heavy else 0.2)
	_shake_if_local(int(e.get("a", -1)), 0.12)
	if hud != null and hud.has_method("show_damage") and (int(e.get("a", -1)) == local_entity or int(e.get("t", -1)) == local_entity):
		hud.show_damage(p, float(e.get("dmg", 0.0)), int(e.get("t", -1)) == local_entity)


func _flash_target(e: int, c: Color, s: float) -> void:
	var v: FighterView = views.get(e)
	if v != null:
		v.flash(c, s * (0.4 if reduced else 1.0))


func _shake_if_local(e: int, amount: float) -> void:
	if e == local_entity and camera_rig != null:
		camera_rig.add_shake(amount)


func _on_action(e: Dictionary) -> void:
	var ent: int = int(e.get("e", -1))
	var p: Vector3 = _pos_of(ent, 0.8)
	if not _near(p, 40.0):
		return
	var a: String = String(e.get("a", ""))
	if a.contains("dodge"):
		AudioDirector.play_at("dodge", p)
		ring(p - Vector3(0, 0.75, 0), Color(0.85, 0.85, 0.8, 0.35), 1.4, 0.25)
	elif a.contains("heavy"):
		AudioDirector.play_at("swing_heavy", p)
	elif a.contains("light"):
		AudioDirector.play_at("kick_whoosh" if a.begins_with("hops") else "swing_light", p)
	elif a == "vex_tail_sweep":
		AudioDirector.play_at("vex_tail_sweep", p)
	elif a == "hops_double_kick":
		AudioDirector.play_at("hops_double_kick", p)
	elif a == "nyx_crosscut":
		AudioDirector.play_at("nyx_crosscut", p)
	elif a == "scrap_leg_sweep":
		AudioDirector.play_at("scrap_leg_sweep", p)
	elif a == "nyx_slip":
		AudioDirector.play_at("nyx_slip", p)
	elif a == "scrap_turnabout":
		AudioDirector.play_at("scrap_turnabout", p)


func _skill_fx(e: Dictionary) -> void:
	var ent: int = int(e.get("e", -1))
	var fx: String = String(e.get("fx", ""))
	var feet: Vector3 = _pos_of(ent, 0.0)
	var chest: Vector3 = _pos_of(ent, 0.7)
	if feet == Vector3.INF:
		return
	AudioDirector.play_at(fx, chest)
	var dust := Color(0.8, 0.74, 0.62, 0.7)
	match fx:
		"nyx_pounce_leap", "hops_bound_takeoff", "hops_dropkick", "bruno_rush_start":
			sparks(feet + Vector3(0, 0.1, 0), dust, 16, 2.5, Vector3.UP, -3.0)
			ring(feet, dust, 1.6, 0.35)
		"nyx_pounce_land", "hops_bound_land", "hops_dropkick_crash":
			sparks(feet + Vector3(0, 0.1, 0), dust, 24, 3.5, Vector3.UP, -4.0)
			ring(feet, dust, 3.0, 0.45)
		"bruno_rush_impact":
			sparks(chest, Color(1.0, 0.8, 0.5), 26, 6.0)
			ring(chest, Color(1.0, 0.85, 0.55, 0.9), 2.2, 0.3, false)
			_shake_if_local(ent, 0.3)
		"bruno_bark":
			for i in range(3):
				get_tree().create_timer(0.08 * i).timeout.connect(func() -> void:
					ring(chest, Color(1.0, 0.9, 0.6, 0.55), 3.5 + 2.0 * i, 0.4, false))
		"bruno_stand_firm":
			ring(feet, Color(0.9, 0.8, 0.5, 0.8), 2.4, 0.5)
		"vex_feint", "vex_sidewinder":
			ring(chest, Color(1.0, 0.6, 0.3, 0.45), 1.4, 0.25, false)
		"scrap_parry_stance":
			ring(chest, Color(1.0, 0.95, 0.7, 0.6), 1.0, 0.2, false, 1)


# ------------------------------------------------------------------------------------------
# footsteps (cosmetic; derived from rendered movement)
# ------------------------------------------------------------------------------------------
func footsteps(view_states: Dictionary) -> void:
	for e in view_states.keys():
		var vs: Dictionary = view_states[e]
		if (int(vs.get("flags", 0)) & Protocol.F_GROUNDED) == 0 or (int(vs.get("flags", 0)) & Protocol.F_ALIVE) == 0:
			_foot_prev.erase(e)
			continue
		var p: Vector3 = vs["pos"]
		if not _near(p, 28.0):
			continue
		if _foot_prev.has(e):
			var d: float = Vector2(p.x - (_foot_prev[e] as Vector3).x, p.z - (_foot_prev[e] as Vector3).z).length()
			if d < 2.0:
				var acc: float = float(_foot_acc.get(e, 0.0)) + d
				var vel: Vector3 = vs.get("vel", Vector3.ZERO)
				var stride: float = 1.5 if Vector2(vel.x, vel.z).length() > 4.0 else 0.85
				if acc >= stride:
					acc = 0.0
					AudioDirector.play_at("foot_" + _surface(p), p, -2.0 if e != local_entity else 0.0)
				_foot_acc[e] = acc
		_foot_prev[e] = p


func _surface(p: Vector3) -> String:
	if layout == null:
		return "stone"
	var s: String = layout.surface_at(p)
	match s:
		"wood": return "wood"
		"metal": return "metal"
		"wet", "puddle": return "wet"
	return "stone"
