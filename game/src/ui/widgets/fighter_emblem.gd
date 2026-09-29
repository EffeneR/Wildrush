@tool
class_name FighterEmblem
extends Control
## Vector head emblem per species (cat, dog, fox, rabbit, raccoon): the ear/muzzle silhouette
## identifies the fighter without relying on colour. Original art drawn from primitives.

@export var fighter_id: String = "nyx":
	set(v):
		fighter_id = v
		queue_redraw()
## Draw a dark circular backplate behind the head.
@export var plate: bool = true:
	set(v):
		plate = v
		queue_redraw()
@export var plate_color: Color = Color("1a1d23"):
	set(v):
		plate_color = v
		queue_redraw()
@export var ring_color: Color = Color(0, 0, 0, 0):
	set(v):
		ring_color = v
		queue_redraw()
@export var dimmed: bool = false:
	set(v):
		dimmed = v
		queue_redraw()


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _get_minimum_size() -> Vector2:
	return Vector2(16, 16)


func _s() -> float:
	return minf(size.x, size.y) / 100.0


func _o() -> Vector2:
	return (size - Vector2(100, 100) * _s()) * 0.5


func _pt(x: float, y: float) -> Vector2:
	return _o() + Vector2(x, y) * _s()


func _poly(arr: Array, c: Color) -> void:
	var pts := PackedVector2Array()
	var i: int = 0
	while i + 1 < arr.size():
		pts.append(_pt(float(arr[i]), float(arr[i + 1])))
		i += 2
	if pts.size() >= 3:
		draw_colored_polygon(pts, _c(c))


func _ellipse(cx: float, cy: float, rx: float, ry: float, c: Color, rot: float = 0.0) -> void:
	var pts := PackedVector2Array()
	for i in range(28):
		var a: float = TAU * float(i) / 28.0
		var v := Vector2(cos(a) * rx, sin(a) * ry).rotated(rot)
		pts.append(_pt(cx + v.x, cy + v.y))
	draw_colored_polygon(pts, _c(c))


func _line(arr: Array, c: Color, w: float) -> void:
	var pts := PackedVector2Array()
	var i: int = 0
	while i + 1 < arr.size():
		pts.append(_pt(float(arr[i]), float(arr[i + 1])))
		i += 2
	draw_polyline(pts, _c(c), maxf(1.0, w * _s()), true)


func _c(c: Color) -> Color:
	if dimmed:
		var g: float = c.get_luminance()
		return Color(g, g, g, c.a).lerp(Color("0b0c0f"), 0.45)
	return c


func _draw() -> void:
	if plate:
		draw_circle(_pt(50, 50), 49.0 * _s(), _c(plate_color), true, -1.0, true)
	if ring_color.a > 0.0:
		draw_arc(_pt(50, 50), 48.0 * _s(), 0.0, TAU, 48, _c(ring_color), maxf(1.5, 3.0 * _s()), true)
	var fur: Color = UiKit.FUR.get(fighter_id, Color("8d9097"))
	var dark: Color = fur.darkened(0.45)
	var pale: Color = Color("efe9df")
	var eye: Color = Color("f2b43c")
	var nose: Color = Color("2a2224")
	match fighter_id:
		"nyx":  # cat: upright pointed ears, tabby stripes, pale muzzle, amber eyes
			_poly([24, 44, 27, 14, 46, 32], fur)
			_poly([76, 44, 73, 14, 54, 32], fur)
			_poly([29, 38, 30, 22, 41, 33], Color("c98f8f"))
			_poly([71, 38, 70, 22, 59, 33], Color("c98f8f"))
			_ellipse(50, 56, 28, 25, fur)
			_line([42, 33, 44, 43], dark, 3.5)
			_line([50, 31, 50, 42], dark, 3.5)
			_line([58, 33, 56, 43], dark, 3.5)
			_ellipse(50, 67, 13, 10, pale)
			_ellipse(40, 54, 4.2, 3.6, eye)
			_ellipse(60, 54, 4.2, 3.6, eye)
			_ellipse(40, 54, 1.3, 3.2, nose)
			_ellipse(60, 54, 1.3, 3.2, nose)
			_poly([46, 62, 54, 62, 50, 66], Color("b56d74"))
		"bruno":  # dog: broad head, folded ears, cream muzzle and dark nose
			_ellipse(50, 53, 30, 27, fur)
			_poly([22, 34, 34, 28, 30, 58, 20, 55], fur.darkened(0.25))
			_poly([78, 34, 66, 28, 70, 58, 80, 55], fur.darkened(0.25))
			_ellipse(50, 67, 17, 13, Color("efdcbf"))
			_ellipse(50, 60, 6.5, 4.5, nose)
			_ellipse(39, 49, 3.8, 3.8, Color("3a2a1c"))
			_ellipse(61, 49, 3.8, 3.8, Color("3a2a1c"))
			_line([44, 72, 50, 74, 56, 72], Color("7a5a44"), 2.5)
		"vex":  # fox: tall pointed ears with dark tips, narrow muzzle, cream cheeks
			_poly([22, 46, 22, 8, 45, 30], fur)
			_poly([78, 46, 78, 8, 55, 30], fur)
			_poly([22, 8, 22, 20, 30, 17], Color("2a2226"))
			_poly([78, 8, 78, 20, 70, 17], Color("2a2226"))
			_poly([26, 40, 27, 22, 40, 33], Color("f1e2cf"))
			_poly([74, 40, 73, 22, 60, 33], Color("f1e2cf"))
			_poly([22, 48, 34, 32, 66, 32, 78, 48, 62, 66, 50, 84, 38, 66], fur)
			_poly([22, 48, 38, 58, 50, 84, 36, 68], pale)
			_poly([78, 48, 62, 58, 50, 84, 64, 68], pale)
			_ellipse(50, 82, 4, 3.2, nose)
			_poly([35, 48, 45, 50, 38, 53], eye)
			_poly([65, 48, 55, 50, 62, 53], eye)
		"hops":  # rabbit: long upright ears, round face, pink nose
			_ellipse(38, 24, 7, 22, fur, -0.12)
			_ellipse(62, 24, 7, 22, fur, 0.12)
			_ellipse(38, 25, 3.2, 16, Color("e3b3b8"), -0.12)
			_ellipse(62, 25, 3.2, 16, Color("e3b3b8"), 0.12)
			_ellipse(50, 60, 26, 24, fur)
			_ellipse(36, 58, 4, 5, Color("59626b"))
			_ellipse(64, 58, 4, 5, Color("59626b"))
			_ellipse(50, 68, 4, 3, Color("d58c95"))
			_line([50, 71, 50, 75], Color("9aa0a8"), 2.0)
			_ellipse(62, 44, 7, 4, Color("c9c4bb"), 0.3)
		"scrap":  # raccoon: rounded ears, dark mask band, pale muzzle
			_ellipse(28, 32, 11, 11, fur)
			_ellipse(72, 32, 11, 11, fur)
			_ellipse(28, 32, 5.5, 5.5, Color("e6e2da"))
			_ellipse(72, 32, 5.5, 5.5, Color("e6e2da"))
			_ellipse(50, 56, 30, 26, fur)
			_ellipse(50, 42, 20, 7, Color("d8d4cc"))
			_poly([20, 52, 34, 44, 50, 52, 66, 44, 80, 52, 70, 62, 50, 58, 30, 62], Color("26282c"))
			_ellipse(38, 52, 3.5, 3.5, Color("f0d8a0"))
			_ellipse(62, 52, 3.5, 3.5, Color("f0d8a0"))
			_ellipse(50, 70, 14, 10, Color("e6e2da"))
			_ellipse(50, 66, 5, 3.5, nose)
		_:
			_ellipse(50, 55, 28, 26, fur)
