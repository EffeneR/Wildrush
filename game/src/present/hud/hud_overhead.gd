class_name HudOverhead
extends Control
## Screen-space nameplates and health bars above fighters (projected each frame), off-screen
## ally arrows, damage numbers (optional accessibility/gameplay setting) and pings in world.

var camera: Camera3D = null
var host: MatchHost = null
var views: Dictionary = {}                 # e -> FighterView
var states: Dictionary = {}                # e -> view state
var numbers: Array = []                    # [{pos, text, t, col}]
var world_pings: Array = []                # [{pos, kind, t, from}]


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func add_number(pos: Vector3, amount: float, on_me: bool) -> void:
	numbers.append({"pos": pos + Vector3(randf_range(-0.2, 0.2), 0.2, 0), "text": str(int(round(amount))), "t": 0.0,
		"col": Color(1.0, 0.45, 0.4) if on_me else Color(1.0, 0.95, 0.75)})


func add_ping(pos: Vector3, kind: String, from_name: String) -> void:
	world_pings.append({"pos": pos, "kind": kind, "t": 0.0, "from": from_name})


func tick(dt: float) -> void:
	for n in numbers:
		n["t"] = float(n["t"]) + dt
	numbers = numbers.filter(func(n: Dictionary) -> bool: return float(n["t"]) < 0.9)
	for p in world_pings:
		p["t"] = float(p["t"]) + dt
	world_pings = world_pings.filter(func(p: Dictionary) -> bool: return float(p["t"]) < 6.0)
	queue_redraw()


func _draw() -> void:
	if camera == null or host == null:
		return
	var f: Font = HudStyle.body_font()
	var nf: Font = HudStyle.num_font()
	var cam_pos: Vector3 = camera.global_position
	for e in views.keys():
		if e == host.local_entity:
			continue
		var v: FighterView = views[e]
		var vs: Dictionary = states.get(e, {})
		if vs.is_empty() or bool(vs.get("hidden", false)) or bool(vs.get("unseen", false)) or not v.visible:
			continue
		if (int(vs.get("flags", 0)) & Protocol.F_ALIVE) == 0:
			continue
		var head: Vector3 = v.head_world()
		var dist: float = cam_pos.distance_to(head)
		var rel: String = host.relation_of(int(e))
		if rel == "enemy" and dist > 30.0:
			continue
		if camera.is_position_behind(head):
			continue
		var sp: Vector2 = camera.unproject_position(head)
		if not Rect2(Vector2.ZERO, size).grow(40).has_point(sp):
			continue
		# occlusion: don't draw enemy plates through walls
		if rel == "enemy":
			var space: PhysicsDirectSpaceState3D = camera.get_world_3d().direct_space_state
			var q := PhysicsRayQueryParameters3D.create(cam_pos, head, WR.LAYER_WORLD | WR.LAYER_CAMERA_BLOCK)
			if not space.intersect_ray(q).is_empty():
				continue
		var col: Color = Settings.relation_color(rel)
		var sc: float = clampf(14.0 / maxf(dist, 1.0), 0.55, 1.0)
		var bw: float = 74.0 * sc
		var bh: float = 7.0 * sc
		var hp_frac: float = clampf(float(vs.get("hp", 0.0)) / v.def.health, 0.0, 1.0)
		var bar := Rect2(sp + Vector2(-bw * 0.5, 0), Vector2(bw, bh))
		draw_rect(bar.grow(1.0), Color(0, 0, 0, 0.7))
		draw_rect(Rect2(bar.position, Vector2(bw * hp_frac, bh)), col)
		var name_s: String = String(host.fighter_info.get(e, {}).get("name", ""))
		var fs: int = int(15.0 * sc) + 2
		var tw: Vector2 = f.get_string_size(name_s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
		draw_string_outline(f, sp + Vector2(-tw.x * 0.5, -5), name_s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 4, Color(0, 0, 0, 0.85))
		draw_string(f, sp + Vector2(-tw.x * 0.5, -5), name_s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, col.lerp(Color.WHITE, 0.4))
		# relation shape marker left of the name
		var mk: Vector2 = sp + Vector2(-tw.x * 0.5 - 9, -10)
		if rel == "enemy":
			draw_colored_polygon(PackedVector2Array([mk + Vector2(0, -5), mk + Vector2(5, 0), mk + Vector2(0, 5), mk + Vector2(-5, 0)]), col)
		else:
			draw_circle(mk, 4.0, col)
		if (int(vs.get("flags", 0)) & Protocol.F_PROTECTED) != 0:
			draw_string(f, sp + Vector2(-20, bh + 14), "PROTECTED", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color(0.75, 0.9, 1.0))
	for n in numbers:
		var p3: Vector3 = (n["pos"] as Vector3) + Vector3(0, float(n["t"]) * 1.2, 0)
		if camera.is_position_behind(p3):
			continue
		var p2: Vector2 = camera.unproject_position(p3)
		var a: float = 1.0 - float(n["t"]) / 0.9
		var c: Color = n["col"]
		draw_string_outline(nf, p2, String(n["text"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 26, 5, Color(0, 0, 0, a * 0.8))
		draw_string(nf, p2, String(n["text"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 26, Color(c.r, c.g, c.b, a))
	for p in world_pings:
		var wp: Vector3 = p["pos"]
		var col2: Color = Settings.relation_color("enemy") if String(p["kind"]) == "enemy" else Settings.relation_color("neutral")
		var label: String = {"attack": "ATTACK", "defend": "DEFEND", "help": "HELP", "enemy": "ENEMY", "on_my_way": "ON MY WAY"}.get(String(p["kind"]), "PING")
		var on_screen: bool = not camera.is_position_behind(wp)
		var p2b: Vector2 = camera.unproject_position(wp) if on_screen else Vector2(size.x * 0.5, size.y - 40)
		p2b = p2b.clamp(Vector2(30, 30), size - Vector2(30, 30))
		var a2: float = clampf(1.5 - float(p["t"]) / 4.0, 0.0, 1.0)
		draw_arc(p2b, 12.0 + 4.0 * sin(float(p["t"]) * 6.0), 0, TAU, 24, Color(col2.r, col2.g, col2.b, a2), 3.0, true)
		draw_circle(p2b, 4.0, Color(col2.r, col2.g, col2.b, a2))
		var txt: String = "%s · %s  %dm" % [label, String(p["from"]), int(cam_pos.distance_to(wp))]
		var tw2: Vector2 = f.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 13)
		draw_string_outline(f, p2b + Vector2(-tw2.x * 0.5, -20), txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, 4, Color(0, 0, 0, a2 * 0.9))
		draw_string(f, p2b + Vector2(-tw2.x * 0.5, -20), txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(1, 1, 1, a2))
