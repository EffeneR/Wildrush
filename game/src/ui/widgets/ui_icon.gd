@tool
class_name UiIcon
extends Control
## Vector icon drawn with canvas primitives (crisp at every UI scale / resolution). Icons pair
## with colour everywhere so state is never conveyed by colour alone. Design grid: 24 x 24.

@export var kind: String = "dot":
	set(v):
		kind = v
		queue_redraw()
@export var color: Color = Color("ece7dd"):
	set(v):
		color = v
		queue_redraw()
@export var line_width: float = 2.0:
	set(v):
		line_width = v
		queue_redraw()
## When set, the icon takes the parent Button's current font colour (hover/pressed/disabled).
var follow_parent_font_color: bool = false


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(_delta: float) -> void:
	if follow_parent_font_color:
		queue_redraw()


func _get_minimum_size() -> Vector2:
	return Vector2(12, 12)


func _col() -> Color:
	if follow_parent_font_color and get_parent() is Button:
		var b := get_parent() as Button
		var mode: int = b.get_draw_mode()
		if b.disabled:
			return b.get_theme_color("font_disabled_color")
		if mode == BaseButton.DRAW_HOVER or b.has_focus():
			return b.get_theme_color("font_hover_color")
		if mode == BaseButton.DRAW_PRESSED or mode == BaseButton.DRAW_HOVER_PRESSED:
			return b.get_theme_color("font_pressed_color")
		return b.get_theme_color("font_color")
	return color


func _p(x: float, y: float) -> Vector2:
	var s: float = minf(size.x, size.y) / 24.0
	var off: Vector2 = (size - Vector2(24.0, 24.0) * s) * 0.5
	return off + Vector2(x, y) * s


func _pts(arr: Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	var i: int = 0
	while i + 1 < arr.size():
		out.append(_p(float(arr[i]), float(arr[i + 1])))
		i += 2
	return out


func _w() -> float:
	return maxf(1.0, line_width * minf(size.x, size.y) / 24.0)


func _line(arr: Array, c: Color) -> void:
	draw_polyline(_pts(arr), c, _w(), true)


func _fill(arr: Array, c: Color) -> void:
	var pts: PackedVector2Array = _pts(arr)
	if pts.size() >= 3:
		draw_colored_polygon(pts, c)


func _circle(x: float, y: float, r: float, c: Color, filled: bool = true) -> void:
	var s: float = minf(size.x, size.y) / 24.0
	if filled:
		draw_circle(_p(x, y), r * s, c, true, -1.0, true)
	else:
		draw_arc(_p(x, y), r * s, 0.0, TAU, 32, c, _w(), true)


func _arc(x: float, y: float, r: float, a0: float, a1: float, c: Color) -> void:
	var s: float = minf(size.x, size.y) / 24.0
	draw_arc(_p(x, y), r * s, a0, a1, 24, c, _w(), true)


func _draw() -> void:
	var c: Color = _col()
	match kind:
		"dot":
			_circle(12, 12, 4, c)
		"circle":
			_circle(12, 12, 8, c, false)
			_circle(12, 12, 3.5, c)
		"check":
			_line([4, 12.5, 9.5, 18, 20, 6.5], c)
		"cross":
			_line([6, 6, 18, 18], c)
			_line([18, 6, 6, 18], c)
		"plus":
			_line([12, 5, 12, 19], c)
			_line([5, 12, 19, 12], c)
		"minus":
			_line([5, 12, 19, 12], c)
		"lock":
			_fill([5, 11, 19, 11, 19, 21, 5, 21], c)
			_arc(12, 11, 5, PI, TAU, c)
			_line([7, 11, 7, 8.5], c)
			_line([17, 11, 17, 8.5], c)
		"unlock":
			_fill([5, 11, 19, 11, 19, 21, 5, 21], c)
			_arc(12, 8, 5, PI, TAU, c)
			_line([7, 8, 7, 5.5], c)
		"crown":
			_fill([3, 18, 4, 7, 9, 12, 12, 5, 15, 12, 20, 7, 21, 18], c)
			_fill([3, 19.5, 21, 19.5, 21, 21, 3, 21], c)
		"bot":
			_line([6, 9, 18, 9, 18, 19, 6, 19, 6, 9], c)
			_line([12, 9, 12, 5], c)
			_circle(12, 4.5, 1.6, c)
			_circle(9.5, 13.5, 1.6, c)
			_circle(14.5, 13.5, 1.6, c)
			_line([3, 13, 3, 16], c)
			_line([21, 13, 21, 16], c)
		"user":
			_circle(12, 8, 4, c)
			_fill([4, 21, 5, 16, 8, 13.5, 16, 13.5, 19, 16, 20, 21], c)
		"users":
			_circle(9, 8, 3.5, c)
			_fill([2, 20, 3, 15.5, 5.5, 13, 12.5, 13, 15, 15.5, 16, 20], c)
			_circle(16.5, 7.5, 3, Color(c, 0.75))
			_fill([15.5, 12.5, 19.5, 12.5, 21.5, 14.5, 22, 19, 17.5, 19, 16.8, 15], Color(c, 0.75))
		"clock":
			_circle(12, 12, 9, c, false)
			_line([12, 7, 12, 12, 16, 14], c)
		"warning":
			_line([12, 3, 22, 20, 2, 20, 12, 3], c)
			_line([12, 9, 12, 14], c)
			_circle(12, 17, 1.2, c)
		"info":
			_circle(12, 12, 9, c, false)
			_line([12, 11, 12, 17], c)
			_circle(12, 7.5, 1.2, c)
		"error":
			_circle(12, 12, 9, c, false)
			_line([8.5, 8.5, 15.5, 15.5], c)
			_line([15.5, 8.5, 8.5, 15.5], c)
		"chevron_left":
			_line([15, 5, 8, 12, 15, 19], c)
		"chevron_right":
			_line([9, 5, 16, 12, 9, 19], c)
		"chevron_down":
			_line([5, 9, 12, 16, 19, 9], c)
		"chevron_up":
			_line([5, 15, 12, 8, 19, 15], c)
		"play":
			_fill([7, 4, 20, 12, 7, 20], c)
		"pause":
			_fill([6, 5, 10, 5, 10, 19, 6, 19], c)
			_fill([14, 5, 18, 5, 18, 19, 14, 19], c)
		"trash":
			_line([4, 6.5, 20, 6.5], c)
			_line([9, 6.5, 9.5, 3.5, 14.5, 3.5, 15, 6.5], c)
			_line([6, 6.5, 7.5, 21, 16.5, 21, 18, 6.5], c)
			_line([10.5, 10, 10.5, 17.5], c)
			_line([13.5, 10, 13.5, 17.5], c)
		"gear":
			_circle(12, 12, 6.5, c, false)
			_circle(12, 12, 2.2, c)
			for i in range(8):
				var a: float = TAU * float(i) / 8.0
				_line([12 + cos(a) * 7.5, 12 + sin(a) * 7.5, 12 + cos(a) * 10.5, 12 + sin(a) * 10.5], c)
		"star":
			var pts: Array = []
			for i in range(10):
				var a: float = -PI / 2.0 + PI * float(i) / 5.0
				var rr: float = 10.0 if i % 2 == 0 else 4.3
				pts.append(12 + cos(a) * rr)
				pts.append(12.5 + sin(a) * rr)
			_fill(pts, c)
		"diamond":
			_fill([12, 2.5, 20.5, 12, 12, 21.5, 3.5, 12], c)
		"shield":
			_fill([12, 2.5, 20, 5.5, 19, 13, 12, 21.5, 5, 13, 4, 5.5], c)
		"paw":
			_circle(12, 15.5, 4.5, c)
			_circle(6, 10, 2.2, c)
			_circle(9.5, 6, 2.2, c)
			_circle(14.5, 6, 2.2, c)
			_circle(18, 10, 2.2, c)
		"trophy":
			_fill([7, 3.5, 17, 3.5, 16.5, 10, 14, 13.5, 10, 13.5, 7.5, 10], c)
			_line([7, 5.5, 3.5, 5.5, 4.5, 9.5, 7.8, 11], c)
			_line([17, 5.5, 20.5, 5.5, 19.5, 9.5, 16.2, 11], c)
			_fill([11, 13.5, 13, 13.5, 13, 17.5, 11, 17.5], c)
			_fill([7.5, 18, 16.5, 18, 16.5, 21, 7.5, 21], c)
		"flag":
			_line([5, 21, 5, 3], c)
			_fill([5, 3.5, 19, 3.5, 15.5, 8, 19, 12.5, 5, 12.5], c)
		"swap":
			_line([4, 8, 19, 8], c)
			_line([15, 4, 19, 8, 15, 12], c)
			_line([20, 16, 5, 16], c)
			_line([9, 12, 5, 16, 9, 20], c)
		"mail":
			_line([3, 6, 21, 6, 21, 18, 3, 18, 3, 6], c)
			_line([3, 6.5, 12, 13, 21, 6.5], c)
		"exit":
			_line([13, 4, 4, 4, 4, 20, 13, 20], c)
			_line([10, 12, 21, 12], c)
			_line([17, 8, 21, 12, 17, 16], c)
		"film":
			_line([3, 5, 21, 5, 21, 19, 3, 19, 3, 5], c)
			_fill([10, 8.5, 16, 12, 10, 15.5], c)
		"refresh":
			_arc(12, 12, 8, -PI * 0.1, PI * 1.45, c)
			_fill([20.5, 4.5, 21, 11, 14.5, 9.5], c)
		"search":
			_circle(10, 10, 6.5, c, false)
			_line([15, 15, 21, 21], c)
		"link":
			_line([10, 14, 14, 10], c)
			_arc(8.5, 15.5, 4.5, PI * 0.25, PI * 1.25, c)
			_arc(15.5, 8.5, 4.5, -PI * 0.75, PI * 0.25, c)
		"globe":
			_circle(12, 12, 9, c, false)
			_line([3, 12, 21, 12], c)
			_arc(12, 12, 9, -PI / 2.0, PI / 2.0, Color(c, 0.0))
			draw_arc(_p(12, 12), 4.5 * minf(size.x, size.y) / 24.0, 0.0, TAU, 24, Color(c, 0.0), 1.0)
			_line([12, 3, 12, 21], c)
		"wifi":
			_arc(12, 19, 14, -PI * 0.78, -PI * 0.22, c)
			_arc(12, 19, 9.5, -PI * 0.75, -PI * 0.25, c)
			_arc(12, 19, 5, -PI * 0.72, -PI * 0.28, c)
			_circle(12, 19, 1.6, c)
		"wifi_off":
			_arc(12, 19, 14, -PI * 0.78, -PI * 0.22, Color(c, 0.45))
			_arc(12, 19, 9.5, -PI * 0.75, -PI * 0.25, Color(c, 0.45))
			_circle(12, 19, 1.6, c)
			_line([4, 3, 20, 21], c)
		"edit":
			_line([4, 20, 5, 15, 16, 4, 20, 8, 9, 19, 4, 20], c)
		"eye":
			_arc(12, 18, 11, -PI * 0.8, -PI * 0.2, c)
			_arc(12, 6, 11, PI * 0.2, PI * 0.8, c)
			_circle(12, 12, 3, c)
		"keyboard":
			_line([2.5, 6.5, 21.5, 6.5, 21.5, 17.5, 2.5, 17.5, 2.5, 6.5], c)
			for kx in [6, 10, 14, 18]:
				_circle(float(kx), 10, 1.0, c)
			_line([7, 14, 17, 14], c)
		"gamepad":
			_line([6, 7, 18, 7, 22, 17, 19, 19, 15, 15, 9, 15, 5, 19, 2, 17, 6, 7], c)
			_line([6.5, 11, 10.5, 11], c)
			_line([8.5, 9, 8.5, 13], c)
			_circle(15.5, 10, 1.1, c)
			_circle(17.5, 12.5, 1.1, c)
		"volume":
			_fill([3, 9, 7, 9, 12, 4.5, 12, 19.5, 7, 15, 3, 15], c)
			_arc(13, 12, 4, -PI * 0.3, PI * 0.3, c)
			_arc(13, 12, 8, -PI * 0.3, PI * 0.3, c)
		"display":
			_line([3, 4.5, 21, 4.5, 21, 16.5, 3, 16.5, 3, 4.5], c)
			_line([9, 20.5, 15, 20.5], c)
			_line([12, 16.5, 12, 20.5], c)
		"access":
			_circle(12, 4.5, 2, c)
			_line([4, 8.5, 20, 8.5], c)
			_line([12, 8.5, 12, 14, 8, 21], c)
			_line([12, 14, 16, 21], c)
		"target":
			_circle(12, 12, 9, c, false)
			_circle(12, 12, 4.5, c, false)
			_circle(12, 12, 1.5, c)
		"server":
			_line([4, 4, 20, 4, 20, 11, 4, 11, 4, 4], c)
			_line([4, 13, 20, 13, 20, 20, 4, 20, 4, 13], c)
			_circle(7.5, 7.5, 1.1, c)
			_circle(7.5, 16.5, 1.1, c)
		"chat":
			_line([3, 5, 21, 5, 21, 16, 10, 16, 5, 20.5, 6, 16, 3, 16, 3, 5], c)
		"swords":
			_line([4, 4, 17, 17], c)
			_line([20, 4, 7, 17], c)
			_line([14, 20, 20, 14], c)
			_line([4, 14, 10, 20], c)
		"hourglass":
			_line([6, 3, 18, 3], c)
			_line([6, 21, 18, 21], c)
			_line([7, 3, 7, 6, 17, 18, 17, 21], c)
			_line([17, 3, 17, 6, 7, 18, 7, 21], c)
		_:
			_circle(12, 12, 4, c)
