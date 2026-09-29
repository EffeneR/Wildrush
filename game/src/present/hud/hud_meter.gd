class_name HudMeter
extends Control
## Horizontal meter with a delayed "damage chunk" trail and optional cost tick marks
## (stamina shows where a dodge/heavy would leave you).

var value: float = 1.0          # 0..1
var trail: float = 1.0
var color: Color = HudStyle.HP
var back: Color = Color(0, 0, 0, 0.55)
var ticks: Array[float] = []    # 0..1 positions
var segments: int = 0
var flash: float = 0.0
var show_text: String = ""


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_value(v: float) -> void:
	v = clampf(v, 0.0, 1.0)
	if v < value - 0.001:
		flash = 1.0
	value = v
	if trail < value:
		trail = value
	queue_redraw()


func _process(dt: float) -> void:
	if trail > value:
		trail = maxf(value, trail - dt * 0.6)
		queue_redraw()
	if flash > 0.0:
		flash = maxf(0.0, flash - dt * 4.0)
		queue_redraw()


func _draw() -> void:
	var r := Rect2(Vector2.ZERO, size)
	draw_rect(r, back)
	draw_rect(Rect2(Vector2.ZERO, Vector2(size.x * trail, size.y)), Color(1.0, 0.95, 0.85, 0.55))
	var c: Color = color.lerp(Color.WHITE, flash * 0.5)
	draw_rect(Rect2(Vector2.ZERO, Vector2(size.x * value, size.y)), c)
	draw_rect(Rect2(Vector2.ZERO, Vector2(size.x * value, size.y * 0.35)), Color(1, 1, 1, 0.12))
	if segments > 1:
		for i in range(1, segments):
			var x: float = size.x * float(i) / segments
			draw_line(Vector2(x, 0), Vector2(x, size.y), Color(0, 0, 0, 0.45), 2.0)
	for tk in ticks:
		var tx: float = size.x * tk
		draw_line(Vector2(tx, -3), Vector2(tx, size.y + 3), Color(1, 1, 1, 0.7), 2.0)
	draw_rect(r, Color(1, 1, 1, 0.18), false, 1.0)
	if show_text != "":
		var f: Font = HudStyle.num_font()
		var fs: int = int(size.y * 0.95)
		var tw: Vector2 = f.get_string_size(show_text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
		draw_string_outline(f, Vector2(size.x - tw.x - 6, size.y * 0.5 + fs * 0.36), show_text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 5, Color(0, 0, 0, 0.9))
		draw_string(f, Vector2(size.x - tw.x - 6, size.y * 0.5 + fs * 0.36), show_text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, HudStyle.INK)
