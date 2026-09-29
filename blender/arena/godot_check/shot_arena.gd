extends SceneTree
## In-engine look check of the imported Briarport chunks (scratch project only).
## Mirrors game/src/present/arena_view.gd: loads chunks[].path from arena_art.json, applies the
## same special-name post-processing (water shader copied from the game if present at
## res://water.gdshader) and a similar sun/sky. Saves res://shots/godot_<view>.png.
##   xvfb-run -a -s "-screen 0 1600x900x24" godot --path <scratch> --script res://shot_arena.gd

const MANIFEST := "res://assets/arena/arena_art.json"
const VIEWS := {
	"overview": [Vector3(-18, 92, 118), Vector3(2, 0, 2), 42.0],
	"A": [Vector3(-30.5, 3.0, 11.0), Vector3(-46.0, 0.8, -3.5), 70.0],
	"B": [Vector3(1.5, 3.2, 17.5), Vector3(-1.0, 3.0, -10.0), 75.0],
	"C": [Vector3(33.0, 3.0, 13.5), Vector3(50.0, 1.8, -2.0), 75.0],
	"north": [Vector3(0.0, 3.0, -53.5), Vector3(0.0, 2.2, -38.0), 75.0],
}
var cam: Camera3D


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var root := Node3D.new()
	get_root().add_child(root)
	var we := WorldEnvironment.new()
	var env := Environment.new()
	var sky := Sky.new()
	var psm := ProceduralSkyMaterial.new()
	psm.sky_top_color = Color(0.32, 0.5, 0.78)
	psm.sky_horizon_color = Color(0.78, 0.76, 0.7)
	psm.ground_bottom_color = Color(0.2, 0.18, 0.16)
	psm.ground_horizon_color = Color(0.62, 0.58, 0.52)
	sky.sky_material = psm
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.75
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.ssao_enabled = true
	env.fog_enabled = true
	env.fog_density = 0.0016
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48.0, -32.0, 0.0)
	sun.light_color = Color(1.0, 0.94, 0.84)
	sun.light_energy = 1.35
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 120.0
	root.add_child(sun)
	var water_shader: Shader = load("res://water.gdshader") if ResourceLoader.exists("res://water.gdshader") else null
	var man: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST))
	for ch in man.get("chunks", []):
		var ps: PackedScene = load(String(ch["path"]))
		var inst := ps.instantiate()
		root.add_child(inst)
		_post(inst, water_shader)
	cam = Camera3D.new()
	cam.far = 1500.0
	root.add_child(cam)
	cam.current = true
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://shots"))
	for v in VIEWS.keys():
		var p: Array = VIEWS[v]
		cam.fov = float(p[2])
		cam.look_at_from_position(p[0], p[1], Vector3.UP)
		for i in 12:
			await process_frame
		var img: Image = get_root().get_viewport().get_texture().get_image()
		img.save_png("res://shots/godot_%s.png" % v)
		print("SHOT ", v)
	root.queue_free()
	await process_frame
	quit(0)


func _post(n: Node, water_shader: Shader) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		var nm := String(mi.name).to_lower()
		if nm.begins_with("water_") and water_shader != null:
			var wm := ShaderMaterial.new()
			wm.shader = water_shader
			mi.material_override = wm
		elif nm.begins_with("puddle_"):
			var pm := StandardMaterial3D.new()
			pm.albedo_color = Color(0.1, 0.12, 0.13, 0.55)
			pm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			pm.roughness = 0.03
			mi.material_override = pm
	for c in n.get_children():
		_post(c, water_shader)
