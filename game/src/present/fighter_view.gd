class_name FighterView
extends Node3D
## Visual representation of one fighter (never simulated). Driven each render frame by a
## view state from the match host (docs/DECISIONS.md D-019):
##   {pos, yaw, vel, clip: String, ct: float, ctrl: int, flags: int, hp: float}
## Uses game/assets/characters/<id>/<id>.glb when present (AnimationPlayer clips per
## docs/CHARACTER_CONTRACT.md §5), otherwise the procedural ProcRig stand-in.

const CHAR_DIR: String = "res://assets/characters/"
const MARKER_SHADER: Shader = preload("res://src/present/shaders/team_marker.gdshader")
const FLASH_SHADER: Shader = preload("res://src/present/shaders/flash_overlay.gdshader")
const PALETTE_SHADER: Shader = preload("res://src/present/shaders/palette_cloth.gdshader")
## Durations of non-action clips (contract §5); action clip durations come from tuning.
const COMMON_DUR: Dictionary = {"hit_front": 0.3, "hit_back": 0.3, "hit_heavy": 0.5, "stagger": 0.6, "knockdown": 0.8,
	"getup": 0.45, "grabbed": 0.45, "knockout": 1.2, "respawn": 0.8, "guard_break": 0.9, "guard_block": 0.2,
	"guard_enter": 0.1, "guard_exit": 0.12, "jump_start": 0.12, "jump_land": 0.2, "dodge_f": 0.367, "dodge_b": 0.367,
	"dodge_l": 0.367, "dodge_r": 0.367, "perch_climb": 0.45, "victory": 2.5, "defeat": 2.0, "idle": 2.0, "select": 3.0}
const CTRL_CLIP: Dictionary = {WR.Ctrl.FLINCH: "hit_front", WR.Ctrl.STAGGER: "stagger", WR.Ctrl.KNOCKDOWN: "knockdown",
	WR.Ctrl.GETUP: "getup", WR.Ctrl.GRABBED: "grabbed", WR.Ctrl.GUARD_BREAK: "guard_break",
	WR.Ctrl.BLOCKSTUN: "guard_block", WR.Ctrl.LANDING: "jump_land"}

var entity: int = -1
var fid: String = ""
var def: FighterDef = null
var relation: String = "enemy"
var palette_id: String = "default"
var rig: ProcRig = null
var model: Node3D = null
var anim: AnimationPlayer = null
var anim_meta: Dictionary = {}          # from <id>_anim.json
var marker: MeshInstance3D = null
var marker_mat: ShaderMaterial = null
var flash_mat: ShaderMaterial = null
var cloth_mats: Array[ShaderMaterial] = []
var durations: Dictionary = {}          # clip -> seconds (tuning + common)
var hit_from_behind: bool = false
var show_marker: bool = true
var alive: bool = true
var is_protected: bool = false
var hp: float = 1.0

var _manual_clip: String = ""
var _manual_t: float = 0.0
var _clip: String = ""
var _ctrl_prev: int = WR.Ctrl.NONE
var _ctrl_t: float = 0.0
var _ko_t: float = 0.0
var _respawn_t: float = 99.0
var _flash: float = 0.0
var _flash_color: Color = Color.WHITE
var _guard_t: float = 0.0
var _was_guard: bool = false
var _prev_pos: Vector3 = Vector3.ZERO
var _smooth_vel: Vector3 = Vector3.ZERO


static func create_preview(fighter_id: String, palette: String) -> FighterView:
	var v := FighterView.new()
	v.setup(Tuning.fighter(fighter_id), palette, "self", false)
	v.play_clip("select")
	return v


func setup(p_def: FighterDef, p_palette: String, p_relation: String, p_show_marker: bool = true) -> void:
	def = p_def
	fid = def.id
	palette_id = p_palette if def.palettes.has(p_palette) else "default"
	relation = p_relation
	show_marker = p_show_marker
	name = "View_%s" % fid
	_collect_durations()
	var glb_path: String = CHAR_DIR + fid + "/" + fid + ".glb"
	if ResourceLoader.exists(glb_path):
		_setup_glb(glb_path)
	if model == null:
		rig = ProcRig.new()
		rig.name = "ProcRig"
		add_child(rig)
		rig.build(fid, def.height, def.palettes.get(palette_id, {}))
		model = rig
	flash_mat = ShaderMaterial.new()
	flash_mat.shader = FLASH_SHADER
	_set_overlay(model, flash_mat)
	if show_marker:
		marker = MeshInstance3D.new()
		var q := QuadMesh.new()
		q.size = Vector2(1.25, 1.25)
		q.orientation = PlaneMesh.FACE_Y
		marker.mesh = q
		marker.position = Vector3(0, 0.035, 0)
		marker.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		marker_mat = ShaderMaterial.new()
		marker_mat.shader = MARKER_SHADER
		marker.material_override = marker_mat
		add_child(marker)
	set_relation(relation)
	Settings.changed.connect(_on_settings_changed)


func _on_settings_changed(section: String) -> void:
	if section == "access":
		set_relation(relation)


func _collect_durations() -> void:
	durations = COMMON_DUR.duplicate()
	for a in def.actions.values():
		var ad: ActionDef = a
		if ad.clip != "":
			durations[ad.clip] = ad.total_ticks / float(WR.TICK_RATE) if ad.total_ticks > 0 else 0.5
		for c in ad.clips.values():
			if c is Array and (c as Array).size() >= 2:
				durations[String(c[0])] = float(c[1])


func _setup_glb(path: String) -> void:
	var ps: PackedScene = load(path) as PackedScene
	if ps == null:
		return
	var inst: Node = ps.instantiate()
	if not (inst is Node3D):
		inst.free()
		return
	model = inst as Node3D
	model.rotation.y = PI      # glTF assets face +Z; gameplay forward is -Z (D-003)
	add_child(model)
	anim = _find_anim(model)
	var meta_path: String = CHAR_DIR + fid + "/" + fid + "_anim.json"
	if FileAccess.file_exists(meta_path):
		var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(meta_path))
		if typeof(d) == TYPE_DICTIONARY:
			anim_meta = d
	_setup_palette_materials(model)


func _find_anim(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n as AnimationPlayer
	for c in n.get_children():
		var a: AnimationPlayer = _find_anim(c)
		if a != null:
			return a
	return null


func _setup_palette_materials(n: Node) -> void:
	var mask_p: String = CHAR_DIR + fid + "/" + fid + "_cloth_mask.png"
	var detail_p: String = CHAR_DIR + fid + "/" + fid + "_cloth_detail.png"
	if not (ResourceLoader.exists(mask_p) and ResourceLoader.exists(detail_p)):
		return
	var normal_p: String = CHAR_DIR + fid + "/" + fid + "_cloth_normal.png"
	for mi in _mesh_instances(n):
		for s in range(mi.mesh.get_surface_count() if mi.mesh != null else 0):
			var m: Material = mi.get_active_material(s)
			if m != null and String(m.resource_name).ends_with("_cloth"):
				var sm := ShaderMaterial.new()
				sm.shader = PALETTE_SHADER
				sm.set_shader_parameter("mask_tex", load(mask_p))
				sm.set_shader_parameter("detail_tex", load(detail_p))
				if ResourceLoader.exists(normal_p):
					sm.set_shader_parameter("normal_tex", load(normal_p))
					sm.set_shader_parameter("has_normal", true)
				mi.set_surface_override_material(s, sm)
				cloth_mats.append(sm)
	set_palette(palette_id)


func _mesh_instances(n: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if n is MeshInstance3D:
		out.append(n as MeshInstance3D)
	for c in n.get_children():
		out.append_array(_mesh_instances(c))
	return out


func _set_overlay(n: Node, m: Material) -> void:
	for mi in _mesh_instances(n):
		mi.material_overlay = m


func set_palette(p: String) -> void:
	palette_id = p if def.palettes.has(p) else "default"
	var pal: Dictionary = def.palettes.get(palette_id, {})
	if rig != null:
		rig.set_palette(pal)
	for sm in cloth_mats:
		for k in ["primary", "secondary", "accent", "trim"]:
			sm.set_shader_parameter(k, Color.html(String(pal.get(k, "#444444"))))


func set_relation(r: String) -> void:
	relation = r
	if marker_mat != null:
		marker_mat.set_shader_parameter("color", Settings.relation_color("ally" if r == "self" else r))
		marker_mat.set_shader_parameter("shape", 0 if r == "self" else (1 if r == "ally" else 2))


func play_clip(clip: String) -> void:
	## Manual playback (menus / previews / victory poses).
	_manual_clip = clip
	_manual_t = 0.0


func flash(color: Color, strength: float = 1.0) -> void:
	_flash_color = color
	_flash = maxf(_flash, strength)


func head_world() -> Vector3:
	return global_position + Vector3(0, def.height * 1.08, 0)


# ------------------------------------------------------------------------------------------
# per-frame
# ------------------------------------------------------------------------------------------
func _process(dt: float) -> void:
	if _manual_clip != "":
		_manual_t += dt
		var dur: float = float(durations.get(_manual_clip, 1.0))
		var looping: bool = _manual_clip in ["idle", "victory", "select", "guard_hold", "run_f", "walk_f"]
		var t: float = fmod(_manual_t, dur) if looping else minf(_manual_t, dur)
		_drive(_manual_clip, t, Vector3.ZERO, true, dt)
	_update_flash(dt)


func apply_state(vs: Dictionary, dt: float) -> void:
	## vs from the match host (see class doc). Called once per render frame.
	_manual_clip = ""
	var pos: Vector3 = vs["pos"]
	global_position = pos
	rotation.y = float(vs["yaw"])
	var flags: int = int(vs.get("flags", Protocol.F_ALIVE | Protocol.F_GROUNDED | Protocol.F_PRESENT))
	var now_alive: bool = (flags & Protocol.F_ALIVE) != 0
	var present: bool = (flags & Protocol.F_PRESENT) != 0
	visible = present and (now_alive or _ko_t < 2.2)
	is_protected = (flags & Protocol.F_PROTECTED) != 0
	hp = float(vs.get("hp", def.health)) / def.health
	if not now_alive and alive:
		_ko_t = 0.0
	if now_alive and not alive:
		_respawn_t = 0.0
		_set_alpha(1.0)
	alive = now_alive
	var vel: Vector3 = vs.get("vel", Vector3.ZERO)
	_smooth_vel = _smooth_vel.lerp(vel, 1.0 - exp(-14.0 * dt))
	var local_v: Vector3 = MathX.world_dir_to_local(float(vs["yaw"]), _smooth_vel)
	var grounded: bool = (flags & Protocol.F_GROUNDED) != 0
	var ctrl: int = int(vs.get("ctrl", WR.Ctrl.NONE))
	if ctrl != _ctrl_prev:
		_ctrl_t = 0.0
		_ctrl_prev = ctrl
	else:
		_ctrl_t += dt
	var clip: String = String(vs.get("clip", "idle"))
	var ct: float = float(vs.get("ct", 0.0))
	var guard: bool = (flags & Protocol.F_GUARD) != 0
	if guard != _was_guard:
		_guard_t = 0.0
		_was_guard = guard
	else:
		_guard_t += dt
	if not alive:
		_ko_t += dt
		_drive("knockout", _ko_t, Vector3.ZERO, true, dt)
		if _ko_t > 1.4:
			_set_alpha(clampf(1.0 - (_ko_t - 1.4) / 0.7, 0.0, 1.0))
		return
	if ctrl != WR.Ctrl.NONE and CTRL_CLIP.has(ctrl):
		var cc: String = String(CTRL_CLIP[ctrl])
		if cc == "hit_front" and hit_from_behind:
			cc = "hit_back"
		_drive(cc, _ctrl_t, local_v, grounded, dt)
	elif clip != "idle" and clip != "":
		_drive(clip, ct, local_v, grounded, dt)
	elif guard:
		_drive("guard_hold", _guard_t, local_v, grounded, dt)
	elif _respawn_t < 0.8:
		_respawn_t += dt
		_drive("respawn", _respawn_t, local_v, grounded, dt)
	else:
		_drive("", 0.0, local_v, grounded, dt)
	if marker != null:
		marker.visible = alive


func _drive(clip: String, t: float, local_v: Vector3, grounded: bool, dt: float) -> void:
	if rig != null:
		var dur: float = maxf(0.05, float(durations.get(clip, 0.5)))
		var tn: float = t / dur
		if clip in ["idle", "victory", "select", "guard_hold"]:
			tn = fmod(tn, 1.0)
		var sharp: float = 30.0 if clip.begins_with("light") or clip.begins_with("skill") or clip == "heavy" else 16.0
		rig.pose("" if clip == "idle" else clip, tn, local_v, grounded, dt, sharp)
		return
	if anim == null:
		return
	if clip == "":
		_locomotion_glb(local_v, grounded)
		return
	if not anim.has_animation(clip):
		clip = "idle"
	if _clip != clip:
		anim.play(clip, 0.08)
		_clip = clip
	anim.speed_scale = 1.0
	var length: float = anim.current_animation_length
	var looping: bool = clip in ["idle", "guard_hold", "victory", "jump_air", "jump_fall"]
	anim.seek(fmod(t, length) if looping and length > 0.0 else minf(t, length), true)


func _locomotion_glb(v: Vector3, grounded: bool) -> void:
	var clip: String = "idle"
	var speed: float = Vector2(v.x, v.z).length()
	var ref: float = 1.0
	if not grounded:
		clip = "jump_air" if v.y > 0.5 else "jump_fall"
	elif speed > 0.3:
		var dir: String = "f"
		if absf(v.x) > absf(v.z):
			dir = "r" if v.x > 0.0 else "l"
		elif v.z < 0.0:
			dir = "b"
		var run: bool = speed > 3.2
		clip = ("run_" if run else "walk_") + dir
		ref = float(anim_meta.get("clips", {}).get(clip, {}).get("ref_speed", def.move_speed if run else 2.0))
	if not anim.has_animation(clip):
		clip = "idle"
	if _clip != clip:
		anim.play(clip, 0.15)
		_clip = clip
	anim.speed_scale = clampf(speed / maxf(0.5, ref), 0.6, 1.6) if clip.begins_with("run") or clip.begins_with("walk") else 1.0


func _update_flash(dt: float) -> void:
	if flash_mat == null:
		return
	_flash = maxf(0.0, _flash - dt * 5.0)
	var amt: float = _flash
	var col: Color = _flash_color
	if is_protected and alive:
		var pulse: float = 0.35 + 0.2 * sin(float(Time.get_ticks_msec()) / 1000.0 * 7.0)
		if pulse > amt:
			amt = pulse
			col = Color(0.75, 0.9, 1.0)
	flash_mat.set_shader_parameter("amount", amt)
	flash_mat.set_shader_parameter("color", col)


func _set_alpha(a: float) -> void:
	if rig != null:
		rig.set_alpha(a)
	else:
		for mi in _mesh_instances(model):
			mi.transparency = 1.0 - a
