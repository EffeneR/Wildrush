class_name ArenaBuilder
extends RefCounted
## Builds gameplay collision (and optional greybox visuals) from an ArenaLayout.
## Collision is authored as simple boxes/cylinders (clean, fast, headless-safe); the art
## chunks exported from Blender are visual only (docs/ENVIRONMENT_CONTRACT.md).

const NAVMESH_PATH: String = "res://data/arena/briarport_navmesh.tres"


static func build_collision(root: Node3D, layout: ArenaLayout) -> Node3D:
	var arena := Node3D.new()
	arena.name = "ArenaCollision"
	root.add_child(arena)
	var world := StaticBody3D.new()
	world.name = "World"
	world.collision_layer = WR.LAYER_WORLD | WR.LAYER_CAMERA_BLOCK
	world.collision_mask = 0
	arena.add_child(world)
	var d: Dictionary = layout.data
	for f in d.get("floors", []):
		_add_box(world, f["min"], f["max"], "floor_" + String(f["id"]))
	for s in d.get("solids", []):
		if not bool(s.get("collide", true)):
			continue
		if String(s.get("shape", "")) == "cylinder":
			_add_cylinder(world, s)
		else:
			_add_box(world, s["min"], s["max"], "solid_" + String(s["id"]))
	for r in d.get("ramps", []):
		_add_ramp(world, r)
	var blockers := StaticBody3D.new()
	blockers.name = "Blockers"
	blockers.collision_layer = WR.LAYER_BLOCKER
	blockers.collision_mask = 0
	arena.add_child(blockers)
	for b in d.get("blockers", []):
		_add_box(blockers, b["min"], b["max"], "blk_" + String(b["id"]))
	for s in d.get("spawns", []):
		var team: int = int(s["team"])
		var bar := StaticBody3D.new()
		bar.name = "SpawnBarrier_team%d" % team
		bar.collision_layer = WR.barrier_layer_for_spawn_of(team)
		bar.collision_mask = 0
		arena.add_child(bar)
		for bb in s.get("barriers", []):
			_add_box(bar, bb["min"], bb["max"], "barrier")
	return arena


static func _add_box(body: StaticBody3D, mn: Array, mx: Array, nm: String) -> void:
	var a := Vector3(float(mn[0]), float(mn[1]), float(mn[2]))
	var b := Vector3(float(mx[0]), float(mx[1]), float(mx[2]))
	var cs := CollisionShape3D.new()
	cs.name = nm
	var shape := BoxShape3D.new()
	shape.size = (b - a).abs()
	cs.shape = shape
	cs.position = (a + b) * 0.5
	body.add_child(cs)


static func _add_cylinder(body: StaticBody3D, s: Dictionary) -> void:
	var mn: Array = s["min"]
	var mx: Array = s["max"]
	var cs := CollisionShape3D.new()
	cs.name = "solid_" + String(s["id"])
	var shape := CylinderShape3D.new()
	shape.radius = float(s.get("radius", (float(mx[0]) - float(mn[0])) * 0.5))
	shape.height = float(mx[1]) - float(mn[1])
	cs.shape = shape
	cs.position = Vector3((float(mn[0]) + float(mx[0])) * 0.5, (float(mn[1]) + float(mx[1])) * 0.5, (float(mn[2]) + float(mx[2])) * 0.5)
	body.add_child(cs)


static func ramp_transform(r: Dictionary, thickness: float) -> Array:
	## Returns [Transform3D, size] for a ramp box whose top face follows from→to.
	var a: Vector3 = ArenaLayout.v3(r["from"])
	var b: Vector3 = ArenaLayout.v3(r["to"])
	var w: float = float(r["width"])
	var d: Vector3 = b - a
	var zaxis: Vector3 = d.normalized()
	var xaxis: Vector3 = zaxis.cross(Vector3.UP).normalized()
	var yaxis: Vector3 = xaxis.cross(zaxis).normalized()
	if yaxis.y < 0.0:
		yaxis = -yaxis
		xaxis = -xaxis
	var basis := Basis(xaxis, yaxis, zaxis)
	var extra: float = 0.3
	var length: float = d.length() + extra * 2.0
	var center: Vector3 = (a + b) * 0.5 - yaxis * (thickness * 0.5)
	return [Transform3D(basis, center), Vector3(w, thickness, length)]


static func _add_ramp(body: StaticBody3D, r: Dictionary) -> void:
	var tr: Array = ramp_transform(r, 0.6)
	var cs := CollisionShape3D.new()
	cs.name = "ramp_" + String(r["id"])
	var shape := BoxShape3D.new()
	shape.size = tr[1]
	cs.shape = shape
	cs.transform = tr[0]
	body.add_child(cs)


# ------------------------------------------------------------------------------------------
# Navigation
# ------------------------------------------------------------------------------------------
static func make_navmesh_params(layout: ArenaLayout) -> NavigationMesh:
	var n: Dictionary = layout.data.get("nav", {})
	var nm := NavigationMesh.new()
	nm.cell_size = float(n.get("cell_size", 0.25))
	nm.cell_height = float(n.get("cell_height", 0.1))
	nm.agent_radius = float(n.get("agent_radius", 0.45))
	nm.agent_height = float(n.get("agent_height", 1.8))
	nm.agent_max_climb = float(n.get("agent_max_climb", 0.36))
	nm.agent_max_slope = float(n.get("agent_max_slope", 46.0))
	nm.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	nm.geometry_collision_mask = WR.LAYER_WORLD | WR.LAYER_BLOCKER
	nm.geometry_source_geometry_mode = NavigationMesh.SOURCE_GEOMETRY_ROOT_NODE_CHILDREN
	nm.region_min_size = 4.0
	var fp: Dictionary = layout.data.get("footprint", {})
	var fx: Array = fp.get("x", [-72, 72])
	var fz: Array = fp.get("z", [-56, 56])
	nm.filter_baking_aabb = AABB(Vector3(float(fx[0]), -4.0, float(fz[0])), Vector3(float(fx[1]) - float(fx[0]), 16.0, float(fz[1]) - float(fz[0])))
	return nm


static func bake_navmesh(collision_root: Node3D, layout: ArenaLayout) -> NavigationMesh:
	var nm: NavigationMesh = make_navmesh_params(layout)
	var src := NavigationMeshSourceGeometryData3D.new()
	NavigationServer3D.parse_source_geometry_data(nm, src, collision_root)
	NavigationServer3D.bake_from_source_geometry_data(nm, src)
	var seeds: Array = []
	for t in range(WR.NUM_TEAMS):
		for sp in layout.spawn_points(t):
			seeds.append(sp["pos"])
	return prune_islands(nm, seeds)


static func prune_islands(nm: NavigationMesh, seeds: Array) -> NavigationMesh:
	## Keeps only polygons edge-connected to a spawn point: removes unreachable islands such
	## as stall roofs or the fountain rim, so ordinary navigation never targets them.
	var verts: PackedVector3Array = nm.get_vertices()
	var n: int = nm.get_polygon_count()
	var polys: Array = []
	var edge_owner: Dictionary = {}
	for i in range(n):
		var poly: PackedInt32Array = nm.get_polygon(i)
		polys.append(poly)
		for k in range(poly.size()):
			var a: Vector3 = verts[poly[k]].snapped(Vector3(0.01, 0.01, 0.01))
			var b: Vector3 = verts[poly[(k + 1) % poly.size()]].snapped(Vector3(0.01, 0.01, 0.01))
			var key: String = str(a) + str(b) if str(a) < str(b) else str(b) + str(a)
			if not edge_owner.has(key):
				edge_owner[key] = []
			(edge_owner[key] as Array).append(i)
	var adj: Array = []
	adj.resize(n)
	for i in range(n):
		adj[i] = []
	for key in edge_owner.keys():
		var owners: Array = edge_owner[key]
		for x in owners:
			for y in owners:
				if x != y:
					(adj[x] as Array).append(y)
	var keep: Dictionary = {}
	var queue: Array = []
	for s in seeds:
		var best: int = -1
		var best_d: float = INF
		for i in range(n):
			var c := Vector3.ZERO
			for vi in polys[i]:
				c += verts[vi]
			c /= float((polys[i] as PackedInt32Array).size())
			var d: float = c.distance_to(s as Vector3)
			if d < best_d:
				best_d = d
				best = i
		if best >= 0 and not keep.has(best):
			keep[best] = true
			queue.append(best)
	while not queue.is_empty():
		var cur: int = queue.pop_back()
		for nb in adj[cur]:
			if not keep.has(nb):
				keep[nb] = true
				queue.append(nb)
	var out: NavigationMesh = nm.duplicate()
	out.clear_polygons()
	for i in range(n):
		if keep.has(i):
			out.add_polygon(polys[i])
	out.set_meta("pruned_islands", n - keep.size())
	return out


static func nav_synced(map: RID, region: RID, nm: NavigationMesh) -> bool:
	## Godot 4.7 synchronises regions and maps asynchronously. The map is usable once it
	## reports our region as the owner of a point on the navmesh.
	if not map.is_valid() or NavigationServer3D.map_get_iteration_id(map) == 0:
		return false
	var v: PackedVector3Array = nm.get_vertices()
	if v.is_empty():
		return false
	return NavigationServer3D.map_get_closest_point_owner(map, v[0]) == region


static func load_or_bake_navmesh(collision_root: Node3D, layout: ArenaLayout, path: String = NAVMESH_PATH) -> NavigationMesh:
	if ResourceLoader.exists(path):
		var res: Resource = load(path)
		if res is NavigationMesh and (res as NavigationMesh).get_polygon_count() > 0:
			return res
	return bake_navmesh(collision_root, layout)


# ------------------------------------------------------------------------------------------
# Greybox (internal work-in-progress visual; replaced by art chunks when present)
# ------------------------------------------------------------------------------------------
static func build_greybox(root: Node3D, layout: ArenaLayout) -> Node3D:
	var g := Node3D.new()
	g.name = "Greybox"
	root.add_child(g)
	var mats := {
		"floor": _mat(Color(0.52, 0.49, 0.45)), "wood": _mat(Color(0.45, 0.32, 0.2)), "metal": _mat(Color(0.42, 0.45, 0.5)),
		"building": _mat(Color(0.55, 0.38, 0.3)), "wall_low": _mat(Color(0.62, 0.6, 0.55)), "column": _mat(Color(0.7, 0.66, 0.58)),
		"stall": _mat(Color(0.6, 0.2, 0.18)), "planter": _mat(Color(0.3, 0.45, 0.25)), "crate_stack": _mat(Color(0.55, 0.4, 0.22)),
		"container": _mat(Color(0.25, 0.35, 0.55)), "fountain": _mat(Color(0.6, 0.62, 0.62)), "balustrade": _mat(Color(0.75, 0.72, 0.66)),
		"water": _mat(Color(0.12, 0.3, 0.42)),
	}
	var d: Dictionary = layout.data
	for f in d.get("floors", []):
		if String(f.get("surface", "")) == "water":
			continue
		var key: String = "wood" if f.get("surface") == "wood" else ("metal" if f.get("surface") == "metal" else "floor")
		_box_mesh(g, f["min"], f["max"], mats[key])
	for s in d.get("solids", []):
		var k: String = String(s["kind"])
		_box_mesh(g, s["min"], s["max"], mats.get(k, mats["building"]))
	for r in d.get("ramps", []):
		var tr: Array = ramp_transform(r, 0.3)
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = tr[1]
		mi.mesh = bm
		mi.transform = tr[0]
		mi.material_override = mats["floor"]
		g.add_child(mi)
	for w in d.get("water", []):
		var mn: Array = w["min"]
		var mx: Array = w["max"]
		_box_mesh(g, [mn[0], float(w["y"]) - 0.05, mn[1]], [mx[0], float(w["y"]), mx[1]], mats["water"])
	return g


static func _mat(c: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = 0.85
	return m


static func _box_mesh(parent: Node3D, mn: Array, mx: Array, mat: Material) -> void:
	var a := Vector3(float(mn[0]), float(mn[1]), float(mn[2]))
	var b := Vector3(float(mx[0]), float(mx[1]), float(mx[2]))
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = (b - a).abs()
	mi.mesh = bm
	mi.position = (a + b) * 0.5
	mi.material_override = mat
	parent.add_child(mi)
