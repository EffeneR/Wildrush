class_name HudStyle
extends RefCounted
## Shared HUD fonts/colours. Fonts are the bundled OFL Barlow family (assets/ui/fonts);
## falls back to the theme default if a file is missing.

const FONT_DIR: String = "res://assets/ui/fonts/"
const INK := Color(0.93, 0.94, 0.95)
const INK_DIM := Color(0.66, 0.69, 0.73)
const PANEL := Color(0.06, 0.07, 0.08, 0.72)
const PANEL_EDGE := Color(1, 1, 1, 0.08)
const HP := Color(0.36, 0.86, 0.5)
const HP_LOW := Color(0.95, 0.35, 0.3)
const STAMINA := Color(0.98, 0.8, 0.3)

static var _fonts: Dictionary = {}


static func font(name: String) -> Font:
	if _fonts.has(name):
		return _fonts[name]
	var path: String = FONT_DIR + name + ".ttf"
	var f: Font = load(path) as Font if ResourceLoader.exists(path) else ThemeDB.fallback_font
	_fonts[name] = f
	return f


static func num_font() -> Font:
	return font("BarlowCondensed-Bold")


static func head_font() -> Font:
	return font("BarlowCondensed-ExtraBold")


static func body_font() -> Font:
	return font("Barlow-SemiBold")


static func label(text: String, size: int, color: Color = INK, f: Font = null, outline: int = 6) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", f if f != null else body_font())
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	l.add_theme_constant_override("outline_size", outline)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


static func panel_box(radius: int = 6, alpha: float = 0.72) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(PANEL.r, PANEL.g, PANEL.b, alpha)
	sb.set_corner_radius_all(radius)
	sb.border_color = PANEL_EDGE
	sb.set_border_width_all(1)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	return sb


static func fmt_time(s: float) -> String:
	var t: int = int(ceil(maxf(0.0, s)))
	return "%d:%02d" % [t / 60, t % 60]
