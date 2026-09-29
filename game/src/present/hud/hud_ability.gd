class_name HudAbility
extends Control
## One ability slot: glyph, cooldown sweep + seconds, key label, "ready" pulse.

var slot_label: String = "Q"
var key_text: String = "Q"
var ability_name: String = ""
var glyph: String = "Q"
var cd_left: float = 0.0
var cd_total: float = 1.0
var active: bool = false
var accent: Color = Color(0.95, 0.75, 0.3)
var _ready_pulse: float = 0.0
var _was_cooling: bool = false


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	custom_minimum_size = Vector2(76, 104)


func set_cd(left: float, total: float, is_active: bool) -> void:
	if _was_cooling and left <= 0.0:
		_ready_pulse = 1.0
	_was_cooling = left > 0.0
	cd_left = left
	cd_total = maxf(0.01, total)
	active = is_active
	queue_redraw()


func _process(dt: float) -> void:
	if _ready_pulse > 0.0:
		_ready_pulse = maxf(0.0, _ready_pulse - dt * 2.5)
		queue_redraw()


func _draw() -> void:
	var s: float = minf(size.x, 64.0)
	var c := Vector2(size.x * 0.5, s * 0.5)
	var rad: float = s * 0.46
	draw_circle(c, rad, Color(0.05, 0.06, 0.07, 0.8))
	var is_ready: bool = cd_left <= 0.0
	var ring_col: Color = accent if is_ready else Color(0.45, 0.47, 0.5)
	if active:
		ring_col = Color(1, 1, 1)
	draw_arc(c, rad, 0, TAU, 48, ring_col, 3.0, true)
	var f: Font = HudStyle.head_font()
	var fs: int = int(s * 0.42)
	var gw: Vector2 = f.get_string_size(glyph, HORIZONTAL_ALIGNMENT_CENTER, -1, fs)
	var gcol: Color = HudStyle.INK if is_ready else Color(0.6, 0.62, 0.65)
	draw_string(f, Vector2(c.x - gw.x * 0.5, c.y + fs * 0.35), glyph, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, gcol)
	if not is_ready:
		var frac: float = clampf(cd_left / cd_total, 0.0, 1.0)
		var pts := PackedVector2Array([c])
		var n: int = 40
		for i in range(n + 1):
			var a: float = -PI * 0.5 + TAU * frac * float(i) / n
			pts.append(c + Vector2(cos(a), sin(a)) * rad)
		if pts.size() >= 3:
			draw_colored_polygon(pts, Color(0, 0, 0, 0.55))
		var t: String = ("%.1f" % cd_left) if cd_left < 3.0 else str(int(ceil(cd_left)))
		var nf: Font = HudStyle.num_font()
		var tw: Vector2 = nf.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, int(s * 0.34))
		draw_string_outline(nf, Vector2(c.x - tw.x * 0.5, c.y + s * 0.13), t, HORIZONTAL_ALIGNMENT_LEFT, -1, int(s * 0.34), 5, Color(0, 0, 0))
		draw_string(nf, Vector2(c.x - tw.x * 0.5, c.y + s * 0.13), t, HORIZONTAL_ALIGNMENT_LEFT, -1, int(s * 0.34), Color.WHITE)
	if _ready_pulse > 0.0:
		draw_arc(c, rad + 6.0 * (1.0 - _ready_pulse), 0, TAU, 48, Color(accent.r, accent.g, accent.b, _ready_pulse), 3.0, true)
	# key label under the icon
	var kf: Font = HudStyle.body_font()
	var kw: Vector2 = kf.get_string_size(key_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 13)
	var kr := Rect2(Vector2(c.x - kw.x * 0.5 - 5, s + 2), Vector2(kw.x + 10, 17))
	draw_rect(kr, Color(0, 0, 0, 0.6))
	draw_string(kf, Vector2(kr.position.x + 5, kr.position.y + 13), key_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, HudStyle.INK_DIM)
	if ability_name != "":
		var nm: String = ability_name.to_upper()
		var fs2: int = 11
		var nw: Vector2 = kf.get_string_size(nm, HORIZONTAL_ALIGNMENT_LEFT, -1, fs2)
		while nw.x > size.x - 2.0 and fs2 > 8:
			fs2 -= 1
			nw = kf.get_string_size(nm, HORIZONTAL_ALIGNMENT_LEFT, -1, fs2)
		draw_string_outline(kf, Vector2(c.x - nw.x * 0.5, s + 34), nm, HORIZONTAL_ALIGNMENT_LEFT, -1, fs2, 4, Color(0, 0, 0, 0.9))
		draw_string(kf, Vector2(c.x - nw.x * 0.5, s + 34), nm, HORIZONTAL_ALIGNMENT_LEFT, -1, fs2, HudStyle.INK_DIM)
