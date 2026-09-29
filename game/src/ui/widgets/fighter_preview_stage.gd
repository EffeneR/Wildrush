class_name FighterPreviewStage
extends Node3D
## 3D stage for fighter previews and portrait captures: environment, key/rim/fill lights,
## floor disc with accent ring, camera, and one FighterView.create_preview() model.

var view: FighterView = null
var cam: Camera3D = null
var framing: String = "full"
var fighter_id: String = ""
var palette: String = "default"
var ring_mat: StandardMaterial3D = null
## Default turn: three-quarter view toward the camera (fighters face -Z, the camera sits at +Z).
var yaw: float = PI - 0.42


static func build(vp: SubViewport, fid: String, pal: String, p_framing: String = "full", show_stage: bool = true,
		clip: String = "") -> FighterPreviewStage:
	var s := FighterPreviewStage.new()
	s.name = "Stage"
	s.framing = p_framing
	s._make(show_stage)
	vp.add_child(s)
	s.set_fighter(fid, pal, clip if clip != "" else ("idle" if p_framing == "bust" else "select"))
	return s


func _make(show_stage: bool) -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_CLEAR_COLOR
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("8a96a8")
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_white = 6.0
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-38, -32, 0)
	key.light_energy = 1.25
	key.light_color = Color("fff1e0")
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 12.0
	add_child(key)
	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-14, 160, 0)
	rim.light_energy = 1.35
	rim.light_color = Color("ff9a86")
	add_child(rim)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-10, 60, 0)
	fill.light_energy = 0.35
	fill.light_color = Color("9fb8ff")
	add_child(fill)
	if show_stage:
		var disc := MeshInstance3D.new()
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.74
		cyl.bottom_radius = 0.74
		cyl.height = 0.03
		cyl.radial_segments = 64
		disc.mesh = cyl
		disc.position = Vector3(0, -0.016, 0)
		var dm := StandardMaterial3D.new()
		dm.albedo_color = Color("0d0e11")
		dm.roughness = 1.0
		dm.metallic_specular = 0.1
		disc.material_override = dm
		add_child(disc)
		var ring := MeshInstance3D.new()
		var tor := TorusMesh.new()
		tor.inner_radius = 0.745
		tor.outer_radius = 0.765
		tor.rings = 96
		tor.ring_segments = 8
		ring.mesh = tor
		ring.scale = Vector3(1, 0.3, 1)
		ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		ring_mat = StandardMaterial3D.new()
		ring_mat.albedo_color = UiKit.ACCENT
		ring_mat.emission_enabled = true
		ring_mat.emission = UiKit.ACCENT
		ring_mat.emission_energy_multiplier = 1.1
		ring.material_override = ring_mat
		add_child(ring)
	cam = Camera3D.new()
	cam.current = true
	add_child(cam)


func frame() -> void:
	var h: float = 1.7
	var d: FighterDef = UiKit.fighter_def(fighter_id)
	if d != null:
		h = d.height
	if framing == "bust":
		cam.fov = 26.0
		cam.position = Vector3(0.28, h * 0.9, 1.95)
		cam.look_at(Vector3(0.0, h * 0.8, 0.0), Vector3.UP)
	else:
		# whole body incl. tall ears plus the floor disc stay inside a 32° vertical FOV
		cam.fov = 32.0
		cam.position = Vector3(0.0, h * 0.58, 4.4)
		cam.look_at(Vector3(0.0, h * 0.5, 0.0), Vector3.UP)


func set_fighter(fid: String, pal: String, clip: String = "select") -> void:
	if fid == fighter_id and view != null:
		set_palette(pal)
		view.play_clip(clip)
		return
	fighter_id = fid
	palette = pal
	if view != null:
		view.queue_free()
		view = null
	if UiKit.fighter_def(fid) != null:
		view = FighterView.create_preview(fid, pal)
		view.rotation.y = yaw
		add_child(view)
		view.play_clip(clip)
	frame()


func set_palette(pal: String) -> void:
	palette = pal
	if view != null:
		view.set_palette(pal)


func play_clip(clip: String) -> void:
	if view != null:
		view.play_clip(clip)


func set_yaw(y: float) -> void:
	yaw = y
	if view != null:
		view.rotation.y = y


func set_accent(c: Color) -> void:
	if ring_mat != null:
		ring_mat.albedo_color = c
		ring_mat.emission = c
