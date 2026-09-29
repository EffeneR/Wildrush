class_name WordmarkLogo
extends Control
## WILDRUSH brand mark. Uses the brand cut-out texture when the lead adds
## res://assets/ui/logo.png (D-017: derived from reference #1); otherwise a typographic
## wordmark with the three-claw-mark motif of the game icon, plus the tagline.

const LOGO_PATH: String = "res://assets/ui/logo.png"
const TAGLINE: String = "Five animals. One pack."

@export var font_size: int = 104:
	set(v):
		font_size = v
		update_minimum_size()
		queue_redraw()
@export var show_tagline: bool = true
## 0..1 reveal amount (splash animation)
var reveal: float = 1.0:
	set(v):
		reveal = v
		queue_redraw()
var _logo: Texture2D = null


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _ready() -> void:
	if ResourceLoader.exists(LOGO_PATH):
		_logo = load(LOGO_PATH) as Texture2D
	update_minimum_size()


func _get_minimum_size() -> Vector2:
	var f: Font = UiKit.FONT_DISPLAY_ITALIC
	var w: float = f.get_string_size("WILDRUSH", HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x + font_size * 0.25
	var h: float = font_size * 1.02 + (font_size * 0.36 if show_tagline else 0.0)
	return Vector2(w, h)


func _draw() -> void:
	var f: Font = UiKit.FONT_DISPLAY_ITALIC
	var fs: int = font_size
	var ms: Vector2 = get_minimum_size()
	if _logo != null:
		var ts: Vector2 = _logo.get_size()
		var sc: float = minf(size.x / ts.x, (size.y - (fs * 0.36 if show_tagline else 0.0)) / ts.y)
		draw_texture_rect(_logo, Rect2(Vector2.ZERO, ts * sc), false, Color(1, 1, 1, reveal))
	else:
		var asc: float = f.get_ascent(fs)
		var pos := Vector2(fs * 0.04, asc * 0.92)
		var a: float = clampf(reveal, 0.0, 1.0)
		# claw marks behind the letters
		var cx: float = ms.x * 0.62
		for i in range(3):
			var x0: float = cx + float(i) * fs * 0.2 - fs * 0.25
			var p0 := Vector2(x0 + fs * 0.1, -fs * 0.02)
			var p1 := Vector2(x0 - fs * 0.12, fs * 1.0)
			_stroke(p0, p0.lerp(p1, clampf(a * 1.4 - float(i) * 0.15, 0.0, 1.0)), fs * 0.085, Color(UiKit.ACCENT, 0.9 * a))
		draw_string(f, pos + Vector2(3, 4), "WILDRUSH", HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(0, 0, 0, 0.45 * a))
		draw_string(f, pos, "WILDRUSH", HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(UiKit.TEXT, a))
	if show_tagline:
		var tf: Font = UiKit.FONT_BODY_SEMIBOLD
		var ts2: int = maxi(14, int(fs * 0.2))
		var y: float = fs * 1.02 + ts2 * 0.95
		var bar_w: float = fs * 0.32
		draw_rect(Rect2(Vector2(fs * 0.06, y - ts2 * 0.42), Vector2(bar_w, 3)), Color(UiKit.ACCENT, reveal))
		draw_string(tf, Vector2(fs * 0.06 + bar_w + 12, y), TAGLINE.to_upper(), HORIZONTAL_ALIGNMENT_LEFT, -1, ts2,
			Color(UiKit.TEXT_DIM, reveal))


func _stroke(a: Vector2, b: Vector2, width: float, c: Color) -> void:
	var d: Vector2 = b - a
	if d.length() < 1.0:
		return
	var n: Vector2 = Vector2(-d.y, d.x).normalized()
	var pts := PackedVector2Array()
	var steps: int = 12
	for i in range(steps + 1):
		var t: float = float(i) / float(steps)
		pts.append(a + d * t + n * sin(t * PI) * width * 0.5)
	for i in range(steps, -1, -1):
		var t2: float = float(i) / float(steps)
		pts.append(a + d * t2 - n * sin(t2 * PI) * width * 0.5)
	draw_colored_polygon(pts, c)
