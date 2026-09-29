extends SceneTree
## Scratch-project import check for the Briarport art chunks (run by tools/build_arena_art.sh).
## Loads every chunk listed in res://assets/arena/arena_art.json exactly like ArenaView does,
## then verifies: scenes load, node counts/triangles/materials, special node names, textures are
## the shared external res://assets/arena/textures/*.png, the coordinate mapping (water AABBs vs
## the layout), and floor tops by raycasting trimesh collision built from the imported meshes.
## Writes res://arena_check.json and exits 0 (pass) / 1 (fail).

const MANIFEST := "res://assets/arena/arena_art.json"
const LAYOUT := "res://layout.json"
const SKIP_COLLIDE := ["water_", "puddle_", "foliage_", "banner_", "emissive_", "lamp_post", "lantern", "boat_",
	"barrel_group", "pallet_stack", "forklift", "crane"]

var fails: PackedStringArray = []
var report: Dictionary = {}


func _init() -> void:
	call_deferred("_run")


func _fail(msg: String) -> void:
	fails.append(msg)
	printerr("ARENA_CHECK FAIL: ", msg)


func _run() -> void:
	var man: Variant = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST))
	if typeof(man) != TYPE_DICTIONARY:
		_fail("manifest missing or invalid")
		_finish()
		return
	var lay: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT))
	var root := Node3D.new()
	root.name = "ArenaCheck"
	get_root().add_child(root)
	var total_tris: int = 0
	var mats: Dictionary = {}
	var textures: Dictionary = {}
	var specials: Dictionary = {"water_": 0, "puddle_": 0, "foliage_": 0, "emissive_": 0, "banner_": 0, "emit_smoke_": 0}
	var chunk_reports: Array = []
	var named: Dictionary = {}
	for ch in (man as Dictionary).get("chunks", []):
		var path: String = String(ch.get("path", ""))
		if not path.begins_with("res://"):
			_fail("chunk %s has no res:// path" % ch.get("id"))
			continue
		var ps: PackedScene = load(path) as PackedScene
		if ps == null:
			_fail("cannot load %s" % path)
			continue
		var inst: Node3D = ps.instantiate() as Node3D
		root.add_child(inst)
		var st := {"id": ch.get("id"), "path": path, "mesh_instances": 0, "triangles": 0, "shared_mesh_users": 0}
		var meshes_seen: Dictionary = {}
		var stack: Array = [inst]
		while stack.size() > 0:
			var n: Node = stack.pop_back()
			for c in n.get_children():
				stack.append(c)
			var nm: String = String(n.name)
			named[nm] = n
			for pre in specials.keys():
				if nm.to_lower().begins_with(pre):
					specials[pre] += 1
			if n is MeshInstance3D:
				var mi := n as MeshInstance3D
				st["mesh_instances"] += 1
				if mi.mesh == null:
					_fail("%s has no mesh" % nm)
					continue
				var mid: int = mi.mesh.get_instance_id()
				if meshes_seen.has(mid):
					st["shared_mesh_users"] += 1
				meshes_seen[mid] = true
				for s in mi.mesh.get_surface_count():
					var arr: Array = mi.mesh.surface_get_arrays(s)
					var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX] if arr[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
					var t: int = idx.size() / 3 if idx.size() > 0 else (arr[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
					st["triangles"] += t
					var m: Material = mi.mesh.surface_get_material(s)
					if m == null:
						_fail("%s surface %d has no material" % [nm, s])
						continue
					mats[m.resource_name] = true
					if m is BaseMaterial3D:
						var bm := m as BaseMaterial3D
						for tex in [bm.albedo_texture, bm.normal_texture, bm.roughness_texture]:
							if tex == null:
								continue
							var rp: String = (tex as Resource).resource_path
							if not rp.begins_with("res://assets/arena/textures/"):
								_fail("%s uses a non-shared texture '%s'" % [nm, rp])
							textures[rp] = true
		total_tris += int(st["triangles"])
		chunk_reports.append(st)
	report["chunks"] = chunk_reports
	report["triangles"] = total_tris
	report["materials"] = mats.keys().size()
	report["material_names"] = mats.keys()
	report["textures_shared"] = textures.keys().size()
	report["special_nodes"] = specials
	if total_tris > 1200000:
		_fail("triangle budget exceeded: %d" % total_tris)
	if mats.keys().size() > 40:
		_fail("material budget exceeded: %d" % mats.keys().size())
	# coordinate mapping: water surfaces must match the layout rectangles
	for w in lay.get("water", []):
		var nm: String = "water_" + String(w["id"])
		if not named.has(nm):
			_fail("missing node %s" % nm)
			continue
		var mi := named[nm] as MeshInstance3D
		var aabb: AABB = mi.global_transform * mi.mesh.get_aabb()
		var want := AABB(Vector3(float(w["min"][0]), float(w["y"]), float(w["min"][1])),
			Vector3(float(w["max"][0]) - float(w["min"][0]), 0.0, float(w["max"][1]) - float(w["min"][1])))
		if aabb.position.distance_to(want.position) > 0.01 or aabb.end.distance_to(want.end) > 0.01:
			_fail("%s AABB %s != layout %s" % [nm, aabb, want])
	# floor tops via physics raycasts against trimesh colliders built from the imported art
	var body := StaticBody3D.new()
	root.add_child(body)
	var stack2: Array = [root]
	var colliders: int = 0
	while stack2.size() > 0:
		var n: Node = stack2.pop_back()
		for c in n.get_children():
			stack2.append(c)
		if n is MeshInstance3D:
			var nm2: String = String(n.name).to_lower()
			var skip := false
			for pre in SKIP_COLLIDE:
				if nm2.begins_with(pre):
					skip = true
			if skip or nm2.begins_with("skyline") or nm2.contains("_city"):
				continue
			var mi2 := n as MeshInstance3D
			var shape: Shape3D = mi2.mesh.create_trimesh_shape()
			if shape == null:
				continue
			var cs := CollisionShape3D.new()
			cs.shape = shape
			body.add_child(cs)
			cs.global_transform = mi2.global_transform
			colliders += 1
	report["colliders"] = colliders
	await physics_frame
	await physics_frame
	var space: PhysicsDirectSpaceState3D = body.get_world_3d().direct_space_state
	var n_ok: int = 0
	var worst: float = 0.0
	var samples: int = 0
	for f in lay.get("floors", []):
		if String(f.get("surface", "")) == "water":
			continue
		var mn: Array = f["min"]
		var mx: Array = f["max"]
		var top: float = float(mx[1])
		for fx in [0.25, 0.5, 0.75]:
			for fz in [0.3, 0.7]:
				var x: float = lerpf(float(mn[0]), float(mx[0]), fx)
				var z: float = lerpf(float(mn[2]), float(mx[2]), fz)
				if _covered(lay, x, z, top):
					continue
				var q := PhysicsRayQueryParameters3D.create(Vector3(x, top + 2.2, z), Vector3(x, top - 1.0, z))
				var hit: Dictionary = space.intersect_ray(q)
				samples += 1
				if hit.is_empty():
					_fail("no art surface under floor %s at (%.2f, %.2f)" % [f["id"], x, z])
					continue
				var e: float = (hit["position"] as Vector3).y - top
				worst = maxf(worst, absf(e))
				if absf(e) > 0.03:
					_fail("floor %s at (%.2f, %.2f): art top %.3f vs layout %.3f" % [f["id"], x, z, (hit["position"] as Vector3).y, top])
				else:
					n_ok += 1
	report["floor_samples"] = samples
	report["floor_ok"] = n_ok
	report["floor_worst_err_m"] = worst
	_finish()


func _covered(lay: Dictionary, x: float, z: float, top: float) -> bool:
	## true if (x,z) is under a solid, a ramp, a puddle/decal, or a higher floor
	for s in lay.get("solids", []):
		if not bool(s.get("collide", true)):
			continue
		if x > float(s["min"][0]) - 0.3 and x < float(s["max"][0]) + 0.3 and z > float(s["min"][2]) - 0.3 and z < float(s["max"][2]) + 0.3:
			return true
	for f in lay.get("floors", []):
		if float(f["max"][1]) > top + 0.01 and x > float(f["min"][0]) and x < float(f["max"][0]) and z > float(f["min"][2]) and z < float(f["max"][2]):
			return true
	for r in lay.get("ramps", []):
		var a := Vector2(float(r["from"][0]), float(r["from"][2]))
		var b := Vector2(float(r["to"][0]), float(r["to"][2]))
		var d := (b - a).normalized()
		var p := Vector2(x, z) - a
		var t: float = p.dot(d)
		var s2: float = absf(p.dot(Vector2(-d.y, d.x)))
		if t > -0.3 and t < (b - a).length() + 0.3 and s2 < float(r["width"]) / 2.0 + 0.3:
			return true
	return false


func _finish() -> void:
	report["passed"] = fails.is_empty()
	report["failures"] = fails
	var fa := FileAccess.open("res://arena_check.json", FileAccess.WRITE)
	fa.store_string(JSON.stringify(report, " "))
	fa.close()
	print("ARENA_CHECK ", JSON.stringify({"passed": report["passed"], "triangles": report.get("triangles"),
		"materials": report.get("materials"), "floor_samples": report.get("floor_samples"),
		"floor_worst_err_m": report.get("floor_worst_err_m"), "special_nodes": report.get("special_nodes"),
		"failures": fails.size()}))
	var r: Node = get_root().get_node_or_null("ArenaCheck")
	if r:
		r.free()
	quit(0 if fails.is_empty() else 1)
