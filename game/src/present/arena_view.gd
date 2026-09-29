class_name ArenaView
extends Node3D
## Visual Briarport: lighting/environment, the Blender-built art chunks when exported
## (game/assets/arena/arena_art.json, docs/ENVIRONMENT_CONTRACT.md), otherwise a textured
## kit built from the same layout JSON. Draws state-driven territory rings and beacons.
## Never adds collision — gameplay collision is built by ArenaBuilder from the layout.

const ART_MANIFEST: String = "res://assets/arena/arena_art.json"
const TEX: String = "res://assets/arena/textures/"
const RING_SHADER: Shader = preload("res://src/present/shaders/zone_ring.gdshader")
const WATER_SHADER: Shader = preload("res://src/present/shaders/water.gdshader")

var layout: ArenaLayout
var env: Environment
var sun: DirectionalLight3D
var zone_nodes: Dictionary = {}       # id -> {"ring": MeshInstance3D, "mat": ShaderMaterial, "beacon": MeshInstance3D, "label": Label3D}
var used_art_chunks: bool = false
var _mats: Dictionary = {}


func build(p_layout: ArenaLayout) -> void:
	layout = p_layout
	_build_environment()
	if not _load_art_chunks():
		_build_kit()
	_build_zones()
	apply_quality()
	Settings.changed.connect(func(s: String) -> void:
		if s == "display" or s == "access":
			apply_quality())


# ------------------------------------------------------------------------------------------
# environment & light
# ------------------------------------------------------------------------------------------
func _build_environment() -> void:
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	env = Environment.new()
	var sky := Sky.new()
	var psm := ProceduralSkyMaterial.new()
	psm.sky_top_color = Color(0.36, 0.55, 0.8)
	psm.sky_horizon_color = Color(0.86, 0.82, 0.74)
	psm.ground_bottom_color = Color(0.2, 0.18, 0.16)
	psm.ground_horizon_color = Color(0.62, 0.58, 0.52)
	psm.sun_angle_max = 30.0
	sky.sky_material = psm
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_color = Color(0.92, 0.86, 0.78)
	env.ambient_light_sky_contribution = 0.55
	env.ambient_light_energy = 0.95
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 1.12
	env.tonemap_white = 6.0
	env.glow_enabled = true
	env.glow_intensity = 0.35
	env.glow_bloom = 0.04
	env.glow_hdr_threshold = 1.2
	env.fog_enabled = true
	env.fog_light_color = Color(0.72, 0.74, 0.78)
	env.fog_density = 0.0016
	env.fog_aerial_perspective = 0.35
	env.fog_sky_affect = 0.2
	env.adjustment_enabled = true
	we.environment = env
	add_child(we)
	sun = DirectionalLight3D.new()
	sun.name = "Sun"
	sun.rotation_degrees = Vector3(-48.0, -32.0, 0.0)
	sun.light_color = Color(1.0, 0.93, 0.8)
	sun.light_energy = 1.9
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 70.0
	sun.shadow_bias = 0.04
	sun.shadow_normal_bias = 1.2
	add_child(sun)


func apply_quality() -> void:
	var q: String = String(Settings.get_value("display", "quality"))
	env.ssao_enabled = q == "high"
	env.ssao_radius = 1.2
	env.ssao_intensity = 1.6
	env.glow_enabled = q != "low" and q != "competitive"
	env.fog_enabled = q != "low"
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS if q == "high" else DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	sun.shadow_enabled = q != "low"
	env.adjustment_brightness = clampf(float(Settings.get_value("display", "brightness")), 0.6, 1.6)
	env.adjustment_saturation = 0.85 if q == "competitive" else 1.0


# ------------------------------------------------------------------------------------------
# art chunks (Blender pipeline)
# ------------------------------------------------------------------------------------------
func _load_art_chunks() -> bool:
	if not FileAccess.file_exists(ART_MANIFEST):
		return false
	var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(ART_MANIFEST))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	var loaded: int = 0
	for ch in (d as Dictionary).get("chunks", []):
		var path: String = String(ch.get("path", ch.get("file", "")))
		if path == "":
			continue
		if not path.begins_with("res://"):
			path = "res://assets/arena/" + path.get_file()
		if not AssetUtil.imported(path):
			continue
		var ps: PackedScene = load(path) as PackedScene
		if ps == null:
			continue
		var inst: Node = ps.instantiate()
		add_child(inst)
		_post_process(inst)
		loaded += 1
	used_art_chunks = loaded > 0
	return used_art_chunks


func _post_process(n: Node) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		var nm: String = String(mi.name).to_lower()
		if nm.begins_with("water_"):
			var wm := ShaderMaterial.new()
			wm.shader = WATER_SHADER
			mi.material_override = wm
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		elif nm.begins_with("puddle_"):
			var pm := StandardMaterial3D.new()
			pm.albedo_color = Color(0.1, 0.12, 0.13, 0.55)
			pm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			pm.roughness = 0.03
			pm.metallic_specular = 0.8
			mi.material_override = pm
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		elif nm.begins_with("foliage_") or nm.begins_with("banner_"):
			for s in range(mi.mesh.get_surface_count() if mi.mesh != null else 0):
				var m: Material = mi.get_active_material(s)
				if m is BaseMaterial3D:
					var bm := (m as BaseMaterial3D).duplicate() as BaseMaterial3D
					bm.cull_mode = BaseMaterial3D.CULL_DISABLED
					if nm.begins_with("foliage_"):
						bm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
					mi.set_surface_override_material(s, bm)
	for c in n.get_children():
		_post_process(c)


# ------------------------------------------------------------------------------------------
# textured kit from the layout (fallback when art chunks are not exported)
# ------------------------------------------------------------------------------------------
func _tex_mat(name: String, uv_scale: float = 0.25, tint: Color = Color.WHITE) -> BaseMaterial3D:
	var key: String = "%s:%.3f:%s" % [name, uv_scale, tint.to_html()]
	if _mats.has(key):
		return _mats[key]
	var m := ORMMaterial3D.new()
	var alb: String = TEX + name + "_albedo.png"
	var base: String = name.get_slice("_", 0)
	if ResourceLoader.exists(alb):
		m.albedo_texture = load(alb)
	m.albedo_color = tint
	for nrm in [TEX + name + "_normal.png", TEX + base + "_normal.png"]:
		if ResourceLoader.exists(nrm):
			m.normal_enabled = true
			m.normal_texture = load(nrm)
			break
	for orm in [TEX + name + "_orm.png", TEX + base + "_orm.png"]:
		if ResourceLoader.exists(orm):
			m.orm_texture = load(orm)
			break
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE * uv_scale
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	_mats[key] = m
	return m


func _flat_mat(c: Color, rough: float = 0.8, emissive: float = 0.0) -> StandardMaterial3D:
	var key: String = "flat:%s:%.2f:%.2f" % [c.to_html(), rough, emissive]
	if _mats.has(key):
		return _mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	if emissive > 0.0:
		m.emission_enabled = true
		m.emission = c
		m.emission_energy_multiplier = emissive
	_mats[key] = m
	return m


func _box(parent: Node3D, a: Vector3, b: Vector3, mat: Material, shadows: bool = true) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = (b - a).abs()
	mi.mesh = bm
	mi.position = (a + b) * 0.5
	mi.material_override = mat
	if not shadows:
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)
	return mi


func _v(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


func _build_kit() -> void:
	var kit := Node3D.new()
	kit.name = "Kit"
	add_child(kit)
	var d: Dictionary = layout.data
	var building_styles: Array = ["brick_red", "brick_brown", "plaster_ochre", "plaster_cream", "plaster_rose", "plaster_white"]
	var bi: int = 0
	for f in d.get("floors", []):
		var surf: String = String(f.get("surface", "stone"))
		if surf == "water":
			continue
		var tex: String = {"wood": "wood_planks", "metal": "metal_deck"}.get(surf, "paving_flag")
		var dist: String = String(f.get("district", ""))
		if surf == "stone" and dist in ["C", "yard", "loading"]:
			tex = "paving_concrete"
		elif surf == "stone" and dist in ["north", "south", "A"]:
			tex = "paving_cobble"
		_box(kit, _v(f["min"]), _v(f["max"]), _tex_mat(tex, 0.25))
	for r in d.get("ramps", []):
		var tr: Array = ArenaBuilder.ramp_transform(r, 0.3)
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = tr[1]
		mi.mesh = bm
		mi.transform = tr[0]
		mi.material_override = _tex_mat("stone_ashlar", 0.3)
		kit.add_child(mi)
	for s in d.get("solids", []):
		var a: Vector3 = _v(s["min"])
		var b: Vector3 = _v(s["max"])
		var k: String = String(s["kind"])
		match k:
			"building":
				var st: String = String(building_styles[bi % building_styles.size()])
				bi += 1
				_box(kit, a, b, _tex_mat(st, 0.22))
				# base course, cornice and terracotta roof cap
				_box(kit, Vector3(a.x - 0.05, a.y, a.z - 0.05), Vector3(b.x + 0.05, minf(b.y, a.y + 0.9), b.z + 0.05), _tex_mat("stone_ashlar", 0.3))
				if b.y - a.y > 4.0:
					_box(kit, Vector3(a.x - 0.25, b.y - 0.35, a.z - 0.25), Vector3(b.x + 0.25, b.y, b.z + 0.25), _tex_mat("stone_trim", 0.3))
					_box(kit, Vector3(a.x - 0.4, b.y, a.z - 0.4), Vector3(b.x + 0.4, b.y + 0.6, b.z + 0.4), _tex_mat("roof_terracotta", 0.35))
			"column":
				_box(kit, a, b, _tex_mat("stone_ashlar", 0.4))
			"planter":
				_box(kit, a, b, _tex_mat("stone_trim", 0.4))
				var c: Vector3 = (a + b) * 0.5
				var tree := MeshInstance3D.new()
				var sm := SphereMesh.new()
				sm.radius = minf(b.x - a.x, b.z - a.z) * 0.45 + 0.4
				sm.height = sm.radius * 1.6
				tree.mesh = sm
				tree.position = Vector3(c.x, b.y + 1.6, c.z)
				tree.material_override = _tex_mat("foliage", 0.5, Color(0.75, 0.9, 0.7))
				kit.add_child(tree)
				_box(kit, Vector3(c.x - 0.08, b.y, c.z - 0.08), Vector3(c.x + 0.08, b.y + 1.2, c.z + 0.08), _tex_mat("bark", 0.6))
			"balustrade", "wall_low":
				_box(kit, a, b, _tex_mat("stone_trim" if k == "balustrade" else "stone_ashlar", 0.4))
			"crate_stack":
				_box(kit, a, b, _tex_mat("wood_planks", 0.5, Color(0.9, 0.8, 0.65)))
			"stall":
				_box(kit, a, Vector3(b.x, a.y + 0.95, b.z), _tex_mat("wood_planks", 0.5))
				_box(kit, Vector3(a.x - 0.3, b.y - 0.15, a.z - 0.3), Vector3(b.x + 0.3, b.y, b.z + 0.3),
					_tex_mat("canvas_red" if bi % 2 == 0 else "canvas_green", 0.5))
				bi += 1
			"container":
				_box(kit, a, b, _tex_mat(["container_blue", "container_red", "container_green"][bi % 3], 0.3))
				bi += 1
			"fountain":
				_box(kit, a, b, _tex_mat("stone_trim", 0.4))
				var wtop := MeshInstance3D.new()
				var pm := PlaneMesh.new()
				pm.size = Vector2(b.x - a.x - 0.6, b.z - a.z - 0.6)
				wtop.mesh = pm
				wtop.position = Vector3((a.x + b.x) * 0.5, b.y - 0.1, (a.z + b.z) * 0.5)
				var wm := ShaderMaterial.new()
				wm.shader = WATER_SHADER
				wtop.material_override = wm
				kit.add_child(wtop)
			"fountain_statue":
				_box(kit, a, b, _tex_mat("bronze", 0.6))
			_:
				_box(kit, a, b, _tex_mat("plaster_cream", 0.25))
	for w in d.get("water", []):
		var mn: Array = w["min"]
		var mx: Array = w["max"]
		var y: float = float(w["y"])
		var wmi := MeshInstance3D.new()
		var plane := PlaneMesh.new()
		plane.size = Vector2(float(mx[0]) - float(mn[0]), float(mx[1]) - float(mn[1]))
		plane.subdivide_width = 8
		plane.subdivide_depth = 8
		wmi.mesh = plane
		wmi.position = Vector3((float(mn[0]) + float(mx[0])) * 0.5, y, (float(mn[1]) + float(mx[1])) * 0.5)
		var wmat := ShaderMaterial.new()
		wmat.shader = WATER_SHADER
		wmi.material_override = wmat
		wmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		wmi.name = "water_%s" % String(w.get("id", "canal"))
		kit.add_child(wmi)
		# canal walls down to the bed
		_box(kit, Vector3(float(mn[0]), -3.0, float(mn[1])), Vector3(float(mx[0]), y - 1.2, float(mx[1])), _flat_mat(Color(0.08, 0.12, 0.13)))
	for dec in d.get("decor", []):
		_decor(kit, dec)


func _decor(kit: Node3D, dec: Dictionary) -> void:
	var p: Vector3 = _v(dec["pos"])
	var yaw: float = deg_to_rad(float(dec.get("yaw", 0.0)))
	var sc: float = float(dec.get("scale", 1.0))
	var root := Node3D.new()
	root.position = p
	root.rotation.y = yaw
	root.scale = Vector3.ONE * sc
	kit.add_child(root)
	var iron: BaseMaterial3D = _tex_mat("iron", 0.8)
	match String(dec["kind"]):
		"lamp_post":
			_box(root, Vector3(-0.07, 0, -0.07), Vector3(0.07, 3.4, 0.07), iron)
			_box(root, Vector3(-0.18, 3.4, -0.18), Vector3(0.18, 3.85, 0.18), _flat_mat(Color(1.0, 0.86, 0.6), 0.2, 1.4), false)
			_box(root, Vector3(-0.22, 3.85, -0.22), Vector3(0.22, 3.95, 0.22), iron)
		"banner_on_post":
			_box(root, Vector3(-0.05, 0, -0.05), Vector3(0.05, 4.2, 0.05), iron)
			var bn := _box(root, Vector3(0.05, 2.2, -0.02), Vector3(0.95, 4.0, 0.02), _tex_mat("banner", 1.0), false)
			bn.name = "banner_post"
		"banner_wall":
			_box(root, Vector3(-0.6, 3.0, -0.03), Vector3(0.6, 6.0, 0.03), _tex_mat("banner", 0.6), false)
		"boat":
			_box(root, Vector3(-1.2, -0.4, -3.2), Vector3(1.2, 0.35, 3.2), _tex_mat("wood_planks", 0.5, Color(0.8, 0.6, 0.45)))
			_box(root, Vector3(-0.08, 0.35, -0.2), Vector3(0.08, 4.2, 0.2), _tex_mat("wood_planks", 0.5))
		"barrel_group":
			for i in range(3):
				var bmi := MeshInstance3D.new()
				var cm := CylinderMesh.new()
				cm.top_radius = 0.32
				cm.bottom_radius = 0.32
				cm.height = 0.9
				bmi.mesh = cm
				bmi.position = Vector3(0.7 * i - 0.7, 0.45, 0.3 * (i % 2))
				bmi.material_override = _tex_mat("wood_planks", 0.8, Color(0.75, 0.55, 0.4))
				root.add_child(bmi)
		"pallet_stack":
			_box(root, Vector3(-0.6, 0, -0.5), Vector3(0.6, 0.8, 0.5), _tex_mat("wood_planks", 0.7, Color(0.95, 0.85, 0.7)))
		"crane":
			_box(root, Vector3(-0.4, 0, -0.4), Vector3(0.4, 14.0, 0.4), _tex_mat("paint_yellow", 0.4))
			_box(root, Vector3(-0.3, 13.2, -0.3), Vector3(0.3, 13.9, 12.0), _tex_mat("paint_yellow", 0.4))
		"forklift":
			_box(root, Vector3(-0.7, 0, -1.2), Vector3(0.7, 1.4, 1.0), _tex_mat("paint_yellow", 0.5))
			_box(root, Vector3(-0.5, 0, -1.9), Vector3(0.5, 2.4, -1.2), iron)
		"puddle":
			var pmi := MeshInstance3D.new()
			var pl := PlaneMesh.new()
			pl.size = Vector2(1.8, 1.2) * sc
			pmi.mesh = pl
			pmi.position = Vector3(0, 0.006, 0)
			var pmat := StandardMaterial3D.new()
			pmat.albedo_color = Color(0.1, 0.12, 0.13, 0.5)
			pmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			pmat.roughness = 0.03
			pmi.material_override = pmat
			pmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			root.add_child(pmi)
		"skyline_cathedral", "skyline_clock_tower", "skyline_tower":
			var h: float = {"skyline_cathedral": 34.0, "skyline_clock_tower": 42.0, "skyline_tower": 30.0}.get(String(dec["kind"]), 30.0)
			_box(root, Vector3(-5, 0, -5), Vector3(5, h, 5), _tex_mat("stone_ashlar", 0.15, Color(0.8, 0.8, 0.85)))
			_box(root, Vector3(-3, h, -3), Vector3(3, h + 8.0, 3), _tex_mat("roof_metal", 0.2))
		"chimney_smoke":
			pass   # smoke emitters are spawned by the VFX layer


# ------------------------------------------------------------------------------------------
# territory rings
# ------------------------------------------------------------------------------------------
func _build_zones() -> void:
	for z in layout.zones:
		var id: String = String(z["id"])
		var c: Vector3 = layout.zone_center(id)
		var r: float = float(z.get("radius", 9.0))
		var ring := MeshInstance3D.new()
		var q := QuadMesh.new()
		q.size = Vector2.ONE * (r + 0.6) * 2.0
		q.orientation = PlaneMesh.FACE_Y
		ring.mesh = q
		ring.position = c + Vector3(0, 0.04, 0)
		ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var mat := ShaderMaterial.new()
		mat.shader = RING_SHADER
		mat.set_shader_parameter("radius", r)
		mat.set_shader_parameter("state", 0)
		ring.material_override = mat
		add_child(ring)
		var beacon := MeshInstance3D.new()
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.35
		cyl.bottom_radius = 0.6
		cyl.height = 26.0
		cyl.cap_top = false
		cyl.cap_bottom = false
		beacon.mesh = cyl
		beacon.position = c + Vector3(0, 13.0, 0)
		var bmat := StandardMaterial3D.new()
		bmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		bmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		bmat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		bmat.cull_mode = BaseMaterial3D.CULL_DISABLED
		bmat.albedo_color = Color(1, 0.8, 0.3, 0.25)
		beacon.material_override = bmat
		beacon.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		beacon.visible = false
		add_child(beacon)
		var label := Label3D.new()
		label.text = "%s · %s" % [id, String(z.get("name", ""))]
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = false
		label.pixel_size = 0.012
		label.font_size = 64
		label.outline_size = 12
		label.position = c + Vector3(0, 5.5, 0)
		label.visible = false
		add_child(label)
		zone_nodes[id] = {"ring": ring, "mat": mat, "beacon": beacon, "beacon_mat": bmat, "label": label}


func update_zones(m: Dictionary, local_team: int, spectator: bool) -> void:
	## m: host match_state. Shows the active zone state and the revealed next zone.
	var active: String = String(m.get("zone", ""))
	var nxt: String = String(m.get("next", ""))
	var st: int = int(m.get("state", WR.ZoneState.NEUTRAL))
	var ctrl_team: int = int(m.get("ctrl", -1))
	for id in zone_nodes.keys():
		var zn: Dictionary = zone_nodes[id]
		var mat: ShaderMaterial = zn["mat"]
		var shape_state: int = 0
		var col: Color = Settings.relation_color("inactive")
		if id == active and not bool(m.get("training", false)):
			match st:
				WR.ZoneState.CONTROLLED:
					shape_state = 3
					var rel: String = ("ally" if ctrl_team == 0 else "enemy") if spectator else ("ally" if ctrl_team == local_team else "enemy")
					col = Settings.relation_color(rel)
				WR.ZoneState.CONTESTED:
					shape_state = 4
					col = Settings.relation_color("contested")
				_:
					shape_state = 2
					col = Settings.relation_color("neutral")
		elif id == nxt:
			shape_state = 1
			col = Settings.relation_color("neutral")
		mat.set_shader_parameter("state", shape_state)
		mat.set_shader_parameter("color", col)
		var beacon: MeshInstance3D = zn["beacon"]
		beacon.visible = shape_state >= 2
		(zn["beacon_mat"] as StandardMaterial3D).albedo_color = Color(col.r, col.g, col.b, 0.22)
		var label: Label3D = zn["label"]
		label.visible = shape_state >= 1
		label.modulate = col
