extends SceneTree
## Loads res://chars/<id>/<id>.glb for each id, checks skeleton / clips / materials against
## <id>_anim.json, renders all fighters side by side (idle) and writes a JSON report.
## usage: godot --path <scratch> --script res://check_chars.gd -- nyx,bruno out.png out.json

var ids: PackedStringArray
var out_png := ""
var out_json := ""
var report := {}
var frames := 0
var anims := []

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	ids = a[0].split(",")
	out_png = a[1]
	out_json = a[2]
	var world := Node3D.new()
	root.add_child(world)
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.09, 0.10, 0.12)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.55, 0.58, 0.62)
	e.ambient_light_energy = 0.6
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.environment = e
	world.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, 30, 0)
	sun.light_energy = 1.6
	sun.shadow_enabled = true
	world.add_child(sun)
	var cam := Camera3D.new()
	var n := ids.size()
	var span := 1.1 * n
	cam.position = Vector3(0, 1.05, 2.2 + 0.9 * n)
	cam.fov = 38.0
	world.add_child(cam)
	cam.look_at(Vector3(0, 0.9, 0))
	for i in n:
		var id := ids[i]
		var rep := {"id": id}
		report[id] = rep
		var path := "res://chars/%s/%s.glb" % [id, id]
		var ps: PackedScene = load(path) as PackedScene
		if ps == null:
			rep["error"] = "load failed: " + path
			continue
		var inst: Node3D = ps.instantiate() as Node3D
		inst.rotation.y = 0.0   # glTF +Z forward faces the camera at +Z
		inst.position = Vector3((i - (n - 1) * 0.5) * 1.1, 0, 0)
		world.add_child(inst)
		var skel: Skeleton3D = _find(inst, "Skeleton3D") as Skeleton3D
		var ap: AnimationPlayer = _find(inst, "AnimationPlayer") as AnimationPlayer
		rep["bones"] = skel.get_bone_count() if skel else 0
		var names := []
		if skel:
			for b in skel.get_bone_count():
				names.append(skel.get_bone_name(b))
		rep["bone_names"] = names
		var tris := 0
		var mats := []
		for mi in _all(inst, "MeshInstance3D"):
			var m: Mesh = (mi as MeshInstance3D).mesh
			for s in m.get_surface_count():
				tris += m.surface_get_array_index_len(s) / 3
				var mat := m.surface_get_material(s)
				mats.append(mat.resource_name if mat else "<none>")
			rep["skinned"] = (mi as MeshInstance3D).skin != null
		rep["triangles"] = tris
		rep["materials"] = mats
		var clips := {}
		if ap:
			for an in ap.get_animation_list():
				var anim: Animation = ap.get_animation(an)
				clips[an] = {"length": snappedf(anim.length, 0.0001), "tracks": anim.get_track_count(), "loop": anim.loop_mode}
		rep["clips"] = clips
		# compare with anim json
		var jp := "res://chars/%s/%s_anim.json" % [id, id]
		var meta = JSON.parse_string(FileAccess.get_file_as_string(jp)) if FileAccess.file_exists(jp) else null
		var missing := []
		var bad_len := []
		var bad_loop := []
		if typeof(meta) == TYPE_DICTIONARY:
			for cn in meta["clips"].keys():
				if not clips.has(cn):
					missing.append(cn)
				else:
					if absf(float(clips[cn]["length"]) - float(meta["clips"][cn]["duration"])) > 0.02:
						bad_len.append([cn, clips[cn]["length"], meta["clips"][cn]["duration"]])
					var want_loop: bool = bool(meta["clips"][cn]["loop"])
					if want_loop != (int(clips[cn]["loop"]) != 0):
						bad_loop.append(cn)
		rep["missing_clips"] = missing
		rep["length_mismatch"] = bad_len
		rep["loop_mismatch"] = bad_loop
		if ap and ap.has_animation("idle"):
			ap.play("idle")
			ap.seek(0.5, true)
			anims.append(ap)

func _process(_delta: float) -> bool:
	frames += 1
	if frames == 12:
		var img := root.get_texture().get_image()
		img.save_png(out_png)
		var f := FileAccess.open(out_json, FileAccess.WRITE)
		f.store_string(JSON.stringify(report, " "))
		f.close()
		for id in report.keys():
			var r: Dictionary = report[id]
			print("CHARCHECK %s bones=%s tris=%s clips=%s missing=%s len_mismatch=%s loop_mismatch=%s mats=%s" % [id, r.get("bones", 0), r.get("triangles", 0), r.get("clips", {}).size(), r.get("missing_clips", []), r.get("length_mismatch", []), r.get("loop_mismatch", []), r.get("materials", [])])
		return true
	return false

func _find(n: Node, cls: String) -> Node:
	if n.is_class(cls):
		return n
	for c in n.get_children():
		var r := _find(c, cls)
		if r != null:
			return r
	return null

func _all(n: Node, cls: String) -> Array:
	var out := []
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		out.append_array(_all(c, cls))
	return out
