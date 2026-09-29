class_name MenuBackground
extends Control
## Dark backdrop for menu scenes: vertical gradient, faint oversized claw marks (the WILDRUSH
## icon motif), and a vignette. Drawn procedurally so it scales to any aspect ratio.

@export var accent: Color = Color("d23b41")
@export var intensity: float = 1.0
var _t: float = 0.0


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)


func _process(delta: float) -> void:
	_t += delta
	if int(_t * 10.0) % 3 == 0:
		queue_redraw()


func _draw() -> void:
	var w: float = size.x
	var h: float = size.y
	var top := Color("0e1014")
	var bottom := Color("08090b")
	draw_polygon(PackedVector2Array([Vector2(0, 0), Vector2(w, 0), Vector2(w, h), Vector2(0, h)]),
		PackedColorArray([top, top, bottom, bottom]))
	# warm glow behind the right-hand side (where previews sit)
	var glow_c := Vector2(w * 0.72, h * 0.55)
	var glow_r: float = h * 0.75
	for i in range(10):
		var f: float = 1.0 - float(i) / 10.0
		draw_circle(glow_c, glow_r * f, Color(accent, 0.012 * intensity))
	# claw marks: three long diagonal strokes + one cross stroke
	var base_x: float = w * 0.56
	var sway: float = sin(_t * 0.25) * 4.0
	for i in range(3):
		var x0: float = base_x + float(i) * h * 0.2
		var a := Vector2(x0 + sway, -h * 0.05)
		var b := Vector2(x0 + h * 0.34 + sway, h * 1.05)
		_stroke(a, b, h * 0.035, Color(Color("ece7dd"), 0.022 * intensity))
	_stroke(Vector2(base_x - h * 0.1, h * 0.72), Vector2(base_x + h * 0.8, h * 0.44), h * 0.02, Color(accent, 0.07 * intensity))
	# scan lines
	var y: float = 0.0
	while y < h:
		draw_line(Vector2(0, y), Vector2(w, y), Color(1, 1, 1, 0.012), 1.0)
		y += 4.0
	# vignette edges
	var edge := Color(0, 0, 0, 0.55)
	var clear := Color(0, 0, 0, 0)
	var ew: float = w * 0.18
	draw_polygon(PackedVector2Array([Vector2(0, 0), Vector2(ew, 0), Vector2(ew, h), Vector2(0, h)]),
		PackedColorArray([edge, clear, clear, edge]))
	draw_polygon(PackedVector2Array([Vector2(w - ew, 0), Vector2(w, 0), Vector2(w, h), Vector2(w - ew, h)]),
		PackedColorArray([clear, edge, edge, clear]))
	var eh: float = h * 0.2
	draw_polygon(PackedVector2Array([Vector2(0, h - eh), Vector2(w, h - eh), Vector2(w, h), Vector2(0, h)]),
		PackedColorArray([clear, clear, edge, edge]))


func _stroke(a: Vector2, b: Vector2, width: float, c: Color) -> void:
	## Tapered stroke (claw mark): thick in the middle, pointed at both ends.
	var d: Vector2 = (b - a)
	var n: Vector2 = Vector2(-d.y, d.x).normalized()
	var pts := PackedVector2Array()
	var steps: int = 16
	for i in range(steps + 1):
		var t: float = float(i) / float(steps)
		pts.append(a + d * t + n * sin(t * PI) * width * 0.5)
	for i in range(steps, -1, -1):
		var t2: float = float(i) / float(steps)
		pts.append(a + d * t2 - n * sin(t2 * PI) * width * 0.5)
	draw_colored_polygon(pts, c)
