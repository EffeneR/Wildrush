extends Node
## Arena build + fairness analysis (spec §7, gate G5). Run:
##   godot --headless --path game res://tools/arena_analysis.tscn -- --out ../evidence/arena
## Bakes and saves the navmesh, then measures shortest ordinary travel (navmesh only — no
## perch or skill links) from both teams' spawn exits to every objective for every species,
## checks reachability/islands, occupancy through floors and camera obstruction along routes.

var out_dir: String = ""
var report: Dictionary = {}


func _ready() -> void:
	out_dir = Config.get_arg("out", "")
	await get_tree().physics_frame
	var layout: ArenaLayout = ArenaLayout.load_file()
	var root := Node3D.new()
	add_child(root)
	var col: Node3D = ArenaBuilder.build_collision(root, layout)
	await get_tree().physics_frame
	await get_tree().physics_frame
	var t0: int = Time.get_ticks_msec()
	var nm: NavigationMesh = ArenaBuilder.bake_navmesh(col, layout)
	var bake_ms: int = Time.get_ticks_msec() - t0
	var polys: int = nm.get_polygon_count()
	report["navmesh"] = {"polygons": polys, "vertices": nm.get_vertices().size(), "bake_ms": bake_ms,
		"pruned_island_polygons": int(nm.get_meta("pruned_islands", 0))}
	var save_err: int = ResourceSaver.save(nm, ArenaBuilder.NAVMESH_PATH)
	report["navmesh"]["saved"] = save_err == OK
	var map: RID = NavigationServer3D.map_create()
	NavigationServer3D.map_set_cell_size(map, nm.cell_size)
	NavigationServer3D.map_set_cell_height(map, nm.cell_height)
	NavigationServer3D.map_set_active(map, true)
	var region: RID = NavigationServer3D.region_create()
	NavigationServer3D.region_set_map(region, map)
	NavigationServer3D.region_set_navigation_mesh(region, nm)
	# 4.7: maps synchronise asynchronously; wait for the first iteration
	var waited: int = 0
	while not ArenaBuilder.nav_synced(map, region, nm) and waited < 600:
		await get_tree().physics_frame
		waited += 1
	report["navmesh"]["sync_frames"] = waited
	var ok: bool = polys > 0
	# ---- travel times
	var travel: Dictionary = {}
	var worst_diff: float = 0.0
	for zone in layout.zones:
		var zid: String = String(zone["id"])
		var zc_raw: Vector3 = ArenaLayout.v3(zone["center"])
		# objective target: nearest navigable point to the zone centre (B's centre is the fountain)
		var zc: Vector3 = NavigationServer3D.map_get_closest_point(map, zc_raw)
		var per_team: Array = []
		for team in range(2):
			var best_len: float = INF
			var best_path: PackedVector3Array
			var sp: Array = layout.spawn_points(team)
			var start: Vector3 = (sp[2]["pos"] as Vector3)   # central spawn point
			var p: PackedVector3Array = NavigationServer3D.map_get_path(map, start, zc, true)
			var end_ok: bool = p.size() > 1 and (p[p.size() - 1] - zc).length() < 0.6 and Vector2(zc.x - zc_raw.x, zc.z - zc_raw.z).length() < 9.0
			# ordinary travel time = path length until the objective's 9 m scoring radius is entered
			var L: float = _len_until_radius(p, zc_raw, 9.0)
			if end_ok and L < best_len:
				best_len = L
				best_path = p
			per_team.append({"length_to_zone_m": snappedf(best_len, 0.01), "full_path_m": snappedf(_path_len(p), 0.01), "reached": end_ok, "points": best_path.size()})
			if not end_ok:
				ok = false
		var times: Dictionary = {}
		for fid in WR.FIGHTER_IDS:
			var sp_v: float = Tuning.fighter(fid).move_speed
			var t_a: float = float(per_team[0]["length_to_zone_m"]) / sp_v
			var t_b: float = float(per_team[1]["length_to_zone_m"]) / sp_v
			var diff: float = absf(t_a - t_b) / maxf(0.001, minf(t_a, t_b)) * 100.0
			worst_diff = maxf(worst_diff, diff)
			times[fid] = {"team0_s": snappedf(t_a, 0.01), "team1_s": snappedf(t_b, 0.01), "diff_pct": snappedf(diff, 0.01)}
		travel[zid] = {"team0": per_team[0], "team1": per_team[1], "times": times}
	report["travel"] = travel
	report["worst_team_diff_pct"] = snappedf(worst_diff, 0.01)
	report["fairness_target_pct"] = 10.0
	if worst_diff > 10.0:
		ok = false
	# ---- reachability sampling (unreachable islands / stuck spots)
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var samples: int = 0
	var unreachable: Array = []
	for i in range(400):
		var q := Vector3(rng.randf_range(-60, 60), 2.0, rng.randf_range(-56, 56))
		var np: Vector3 = NavigationServer3D.map_get_closest_point(map, q)
		if (Vector2(np.x, np.z) - Vector2(q.x, q.z)).length() > 2.0:
			continue
		samples += 1
		var reach: int = 0
		for zone in layout.zones:
			var zc: Vector3 = NavigationServer3D.map_get_closest_point(map, ArenaLayout.v3(zone["center"]))
			var p: PackedVector3Array = NavigationServer3D.map_get_path(map, np, zc, true)
			if p.size() > 1 and (p[p.size() - 1] - zc).length() < 0.6:
				reach += 1
		if reach < layout.zones.size():
			unreachable.append([snappedf(np.x, 0.1), snappedf(np.y, 0.1), snappedf(np.z, 0.1)])
	report["reachability"] = {"samples_on_navmesh": samples, "unreachable_samples": unreachable.size(), "examples": unreachable.slice(0, 10)}
	if not unreachable.is_empty():
		ok = false
	# ---- occupancy through floors: any walkable surface above a zone within its radius but above the band
	var through: Array = []
	var band_above: float = float(Tuning.rules["occupancy"]["band_above"])
	for zone in layout.zones:
		var zc: Vector3 = ArenaLayout.v3(zone["center"])
		for f in layout.data.get("floors", []):
			var top: float = float(f["max"][1])
			if top <= float(zone["floor_y"]) + band_above:
				continue
			var cx: float = clampf(zc.x, float(f["min"][0]), float(f["max"][0]))
			var cz: float = clampf(zc.z, float(f["min"][2]), float(f["max"][2]))
			if Vector2(cx - zc.x, cz - zc.z).length() < 9.35:
				through.append({"zone": zone["id"], "floor": f["id"], "top": top, "note": "above band → cannot capture (by rule)"})
	report["elevated_surfaces_over_zones"] = through
	# ---- camera obstruction along the main routes (follow camera 4.4 m behind, pivot 1.35 m)
	var space: PhysicsDirectSpaceState3D = get_viewport().world_3d.direct_space_state
	var cam_checks: int = 0
	var cam_blocked: int = 0
	for zone in layout.zones:
		var zc: Vector3 = NavigationServer3D.map_get_closest_point(map, ArenaLayout.v3(zone["center"]))
		for team in range(2):
			var start: Vector3 = (layout.spawn_points(team)[2]["pos"] as Vector3)
			var p: PackedVector3Array = NavigationServer3D.map_get_path(map, start, zc, true)
			var pts: Array = _resample(p, 2.0)
			for i in range(1, pts.size()):
				var pos: Vector3 = pts[i]
				var dir: Vector3 = (pts[i] - pts[i - 1])
				dir.y = 0
				if dir.length() < 0.01:
					continue
				dir = dir.normalized()
				var pivot: Vector3 = pos + Vector3(0, 1.35, 0)
				var cam: Vector3 = pivot - dir * 4.4 + Vector3(0, 1.1, 0) + dir.cross(Vector3.UP) * -0.45
				var q := PhysicsRayQueryParameters3D.create(pivot, cam, WR.LAYER_WORLD)
				cam_checks += 1
				if not space.intersect_ray(q).is_empty():
					cam_blocked += 1
	report["camera"] = {"route_samples": cam_checks, "needs_retraction": cam_blocked,
		"retraction_pct": snappedf(100.0 * cam_blocked / maxf(1.0, cam_checks), 0.1),
		"note": "samples where the ideal camera position is inside geometry; the camera rig retracts (spring arm) in these cases"}
	report["ok"] = ok
	report["godot"] = Engine.get_version_info()["string"]
	var txt: String = JSON.stringify(report, "  ")
	print(txt)
	if out_dir != "":
		DirAccess.make_dir_recursive_absolute(out_dir)
		var f := FileAccess.open(out_dir.path_join("travel_times.json"), FileAccess.WRITE)
		f.store_string(txt)
		f.close()
	NavigationServer3D.free_rid(region)
	NavigationServer3D.free_rid(map)
	get_tree().quit(0 if ok else 1)


func _len_until_radius(p: PackedVector3Array, c: Vector3, r: float) -> float:
	var L: float = 0.0
	for i in range(1, p.size()):
		var a: Vector3 = p[i - 1]
		var b: Vector3 = p[i]
		var seg: float = a.distance_to(b)
		if Vector2(b.x - c.x, b.z - c.z).length() <= r:
			# find the entry point on this segment
			var lo: float = 0.0
			var hi: float = 1.0
			for _k in range(20):
				var mid: float = (lo + hi) * 0.5
				var m: Vector3 = a.lerp(b, mid)
				if Vector2(m.x - c.x, m.z - c.z).length() <= r:
					hi = mid
				else:
					lo = mid
			return L + seg * hi
		L += seg
	return L


func _path_len(p: PackedVector3Array) -> float:
	var L: float = 0.0
	for i in range(1, p.size()):
		L += p[i].distance_to(p[i - 1])
	return L


func _resample(p: PackedVector3Array, step: float) -> Array:
	var out: Array = []
	if p.size() < 2:
		return out
	out.append(p[0])
	var acc: float = 0.0
	for i in range(1, p.size()):
		var a: Vector3 = p[i - 1]
		var b: Vector3 = p[i]
		var seg: float = a.distance_to(b)
		var t: float = step - acc
		while t <= seg:
			out.append(a.lerp(b, t / seg))
			t += step
		acc = seg - (t - step)
	return out
