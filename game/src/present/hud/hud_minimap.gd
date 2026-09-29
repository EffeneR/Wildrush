class_name HudMinimap
extends Control
## North-up minimap of Briarport: walkable floors, water, buildings, zones (state by pattern
## + colour), allies, currently visible enemies and pings. Never shows hidden enemies.

var layout: ArenaLayout = null
var host: MatchHost = null
var world_rect := Rect2(-62, -58, 124, 116)   # x, z extents shown
var dots: Array = []                           # [{pos, rel, alive, self, yaw}]
var pings: Array = []                          # [{pos, kind, t}]
var mstate: Dictionary = {}
var _static_cache: Array = []


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func setup(p_layout: ArenaLayout, p_host: MatchHost) -> void:
	layout = p_layout
	host = p_host
	_static_cache.clear()
	for f in layout.data.get("floors", []):
		var kind: String = "water" if String(f.get("surface", "")) == "water" else "floor"
		_static_cache.append([kind, Rect2(float(f["min"][0]), float(f["min"][2]), float(f["max"][0]) - float(f["min"][0]), float(f["max"][2]) - float(f["min"][2]))])
	for w in layout.data.get("water", []):
		_static_cache.append(["water", Rect2(float(w["min"][0]), float(w["min"][1]), float(w["max"][0]) - float(w["min"][0]), float(w["max"][1]) - float(w["min"][1]))])
	for s in layout.data.get("solids", []):
		if bool(s.get("collide", true)) and String(s["kind"]) in ["building", "wall_low", "container", "crate_stack", "stall", "fountain", "column", "planter"]:
			_static_cache.append(["solid", Rect2(float(s["min"][0]), float(s["min"][2]), float(s["max"][0]) - float(s["min"][0]), float(s["max"][2]) - float(s["min"][2]))])


func to_map(p: Vector3) -> Vector2:
	var u: float = (p.x - world_rect.position.x) / world_rect.size.x
	var v: float = (p.z - world_rect.position.y) / world_rect.size.y
	return Vector2(u * size.x, v * size.y)


func _rect_to_map(r: Rect2) -> Rect2:
	var a: Vector2 = to_map(Vector3(r.position.x, 0, r.position.y))
	var b: Vector2 = to_map(Vector3(r.end.x, 0, r.end.y))
	return Rect2(a, b - a).abs()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.04, 0.05, 0.06, 0.78))
	for it in _static_cache:
		var col: Color = Color(0.3, 0.31, 0.33, 0.9)
		match String(it[0]):
			"water": col = Color(0.12, 0.26, 0.34, 0.95)
			"solid": col = Color(0.12, 0.12, 0.13, 0.95)
		draw_rect(_rect_to_map(it[1]), col)
	if layout != null:
		for z in layout.zones:
			var id: String = String(z["id"])
			var c: Vector2 = to_map(layout.zone_center(id))
			var rr: float = float(z.get("radius", 9.0)) / world_rect.size.x * size.x
			var active: bool = String(mstate.get("zone", "")) == id
			var nxt: bool = String(mstate.get("next", "")) == id
			var col: Color = Settings.relation_color("inactive")
			if active:
				match int(mstate.get("state", 1)):
					WR.ZoneState.CONTROLLED:
						var ct: int = int(mstate.get("ctrl", -1))
						col = Settings.relation_color("ally" if (host != null and ct == host.local_team) else "enemy")
					WR.ZoneState.CONTESTED:
						col = Settings.relation_color("contested")
					_:
						col = Settings.relation_color("neutral")
				draw_circle(c, rr, Color(col.r, col.g, col.b, 0.25))
				draw_arc(c, rr, 0, TAU, 40, col, 2.5, true)
			elif nxt:
				for i in range(16):
					var a0: float = TAU * i / 16.0
					draw_arc(c, rr, a0, a0 + TAU / 32.0, 4, Settings.relation_color("neutral"), 2.0, true)
			else:
				draw_arc(c, rr, 0, TAU, 40, Color(col.r, col.g, col.b, 0.5), 1.0, true)
			var f: Font = HudStyle.head_font()
			draw_string(f, c + Vector2(-5, 6), id, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, HudStyle.INK if active or nxt else HudStyle.INK_DIM)
	for p in pings:
		var pc: Vector2 = to_map(p["pos"])
		var life: float = float(p["t"])
		var colp: Color = Settings.relation_color("enemy") if String(p["kind"]) == "enemy" else Settings.relation_color("neutral")
		draw_arc(pc, 5.0 + 8.0 * fmod(life, 1.0), 0, TAU, 20, Color(colp.r, colp.g, colp.b, 1.0 - fmod(life, 1.0)), 2.0, true)
		draw_circle(pc, 3.0, colp)
	for d in dots:
		var dp: Vector2 = to_map(d["pos"])
		var col2: Color = Settings.relation_color(String(d["rel"]))
		if not bool(d["alive"]):
			draw_line(dp - Vector2(4, 4), dp + Vector2(4, 4), Color(col2.r, col2.g, col2.b, 0.6), 2.0)
			draw_line(dp - Vector2(4, -4), dp + Vector2(4, -4), Color(col2.r, col2.g, col2.b, 0.6), 2.0)
			continue
		if bool(d["self"]):
			var fwd: Vector2 = Vector2(-sin(float(d["yaw"])), -cos(float(d["yaw"])))
			var rt: Vector2 = Vector2(-fwd.y, fwd.x)
			draw_colored_polygon(PackedVector2Array([dp + fwd * 9.0, dp - fwd * 5.0 + rt * 6.0, dp - fwd * 2.0, dp - fwd * 5.0 - rt * 6.0]), Color.WHITE)
		elif String(d["rel"]) == "enemy":
			# enemies: diamonds (shape, not only colour)
			draw_colored_polygon(PackedVector2Array([dp + Vector2(0, -6), dp + Vector2(6, 0), dp + Vector2(0, 6), dp + Vector2(-6, 0)]), col2)
		else:
			draw_circle(dp, 5.0, col2)
			draw_arc(dp, 5.0, 0, TAU, 12, Color(0, 0, 0, 0.6), 1.0, true)
	draw_rect(Rect2(Vector2.ZERO, size), Color(1, 1, 1, 0.15), false, 1.0)
	# north marker
	draw_string(HudStyle.body_font(), Vector2(size.x * 0.5 - 4, 14), "N", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, HudStyle.INK_DIM)


func tick(dt: float) -> void:
	for p in pings:
		p["t"] = float(p["t"]) + dt
	pings = pings.filter(func(p: Dictionary) -> bool: return float(p["t"]) < 6.0)
	queue_redraw()
