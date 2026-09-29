class_name UiThemeBuilder
extends RefCounted
## Builds the project theme (res://assets/ui/wildrush_theme.tres) from code so every style is
## reproducible. Regenerate with:
##   $GODOT_BIN --headless --path game --script res://tools/build_ui_theme.gd
## Type variations used by the screens are listed in `VARIATIONS`.

const VARIATIONS: Array[String] = [
	"Hero", "Title", "Heading", "Subheading", "Caption", "Dim", "Small", "Stat", "StatLarge", "ChipLabel",
	"ErrorLabel", "OkLabel", "KeyGlyph", "PrimaryButton", "DangerButton", "GhostButton", "MenuItem", "TabButton",
	"SmallButton", "Card", "PanelDark", "PanelGlass", "PanelRaised", "Toast", "Chip", "KeyCap", "XpBar", "HealthBar",
	"FlatSlider", "ValueButton",
]


static func _sb(bg: Color, border: Color = Color(0, 0, 0, 0), bw: int = 0, radius: int = 3,
		ml: float = 16.0, mt: float = 9.0, mr: float = 16.0, mb: float = 9.0) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(bw)
	s.set_corner_radius_all(radius)
	s.content_margin_left = ml
	s.content_margin_top = mt
	s.content_margin_right = mr
	s.content_margin_bottom = mb
	s.anti_aliasing = true
	s.anti_aliasing_size = 0.8
	return s


static func _focus_box(radius: int = 4, expand: float = 2.0) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.draw_center = false
	s.border_color = UiKit.ACCENT_BRIGHT
	s.set_border_width_all(2)
	s.set_corner_radius_all(radius)
	s.set_expand_margin_all(expand)
	return s


static func _empty() -> StyleBoxEmpty:
	return StyleBoxEmpty.new()


static var _symbols: Font = null


static func _fv(base: Font, spacing: int = 0) -> FontVariation:
	## Theme fonts are FontVariations with the DejaVu Sans symbol fallback (pad glyphs, arrows).
	if _symbols == null:
		_symbols = load(UiKit.FONT_SYMBOLS_PATH) as Font
	var f := FontVariation.new()
	f.base_font = base
	f.spacing_glyph = spacing
	if _symbols != null:
		f.fallbacks = [_symbols]
	return f


static func _button_family(t: Theme, type: StringName, normal: StyleBox, hover: StyleBox, pressed: StyleBox,
		disabled: StyleBox, font: Font, size: int, fc: Color, fhc: Color, fpc: Color) -> void:
	t.set_stylebox("normal", type, normal)
	t.set_stylebox("hover", type, hover)
	t.set_stylebox("pressed", type, pressed)
	t.set_stylebox("hover_pressed", type, pressed)
	t.set_stylebox("disabled", type, disabled)
	t.set_stylebox("focus", type, _focus_box())
	t.set_font("font", type, font)
	t.set_font_size("font_size", type, size)
	t.set_color("font_color", type, fc)
	t.set_color("font_hover_color", type, fhc)
	t.set_color("font_focus_color", type, fhc)
	t.set_color("font_pressed_color", type, fpc)
	t.set_color("font_hover_pressed_color", type, fpc)
	t.set_color("font_disabled_color", type, UiKit.TEXT_FAINT)
	t.set_color("icon_normal_color", type, fc)
	t.set_color("icon_hover_color", type, fhc)
	t.set_color("icon_focus_color", type, fhc)
	t.set_color("icon_pressed_color", type, fpc)
	t.set_color("icon_disabled_color", type, UiKit.TEXT_FAINT)


static func build() -> Theme:
	var t := Theme.new()
	var body: FontVariation = _fv(UiKit.FONT_BODY)
	var body_regular: FontVariation = _fv(UiKit.FONT_BODY_REGULAR)
	var body_semi: FontVariation = _fv(UiKit.FONT_BODY_SEMIBOLD)
	var body_bold: FontVariation = _fv(UiKit.FONT_BODY_BOLD)
	var display: FontVariation = _fv(UiKit.FONT_DISPLAY, 1)
	var display_semi: FontVariation = _fv(UiKit.FONT_DISPLAY_SEMIBOLD, 1)
	var display_xb: FontVariation = _fv(UiKit.FONT_DISPLAY_XBOLD, 2)
	var caption: FontVariation = _fv(UiKit.FONT_BODY_SEMIBOLD, 1)
	t.default_font = body
	t.default_font_size = 18

	# ---------------------------------------------------------------- labels
	t.set_color("font_color", "Label", UiKit.TEXT)
	t.set_color("font_shadow_color", "Label", Color(0, 0, 0, 0))
	t.set_constant("line_spacing", "Label", 2)
	var labels: Array = [
		["Hero", _fv(UiKit.FONT_DISPLAY_ITALIC, 1), 96, UiKit.TEXT],
		["Title", display_xb, 46, UiKit.TEXT],
		["Heading", display, 28, UiKit.TEXT],
		["Subheading", display_semi, 22, UiKit.TEXT],
		["Caption", caption, 14, UiKit.TEXT_DIM],
		["Dim", body_regular, 16, UiKit.TEXT_DIM],
		["Small", body_regular, 15, UiKit.TEXT_DIM],
		["Stat", display, 26, UiKit.TEXT],
		["StatLarge", display_xb, 40, UiKit.TEXT],
		["ChipLabel", caption, 13, UiKit.TEXT],
		["ErrorLabel", body_semi, 16, UiKit.ERR],
		["OkLabel", body_semi, 16, UiKit.OK],
		["KeyGlyph", body_bold, 13, UiKit.TEXT],
	]
	for l in labels:
		var name: StringName = StringName(String(l[0]))
		t.set_type_variation(name, &"Label")
		t.set_font("font", name, l[1] as Font)
		t.set_font_size("font_size", name, int(l[2]))
		t.set_color("font_color", name, l[3] as Color)

	# ---------------------------------------------------------------- panels
	t.set_stylebox("panel", "PanelContainer", _sb(Color(UiKit.BG1, 0.94), UiKit.LINE, 1, 4, 18, 16, 18, 16))
	t.set_stylebox("panel", "Panel", _sb(Color(UiKit.BG1, 0.94), UiKit.LINE, 1, 4))
	var panels: Array = [
		["PanelDark", _sb(Color(UiKit.BG0, 0.9), UiKit.LINE, 1, 4, 14, 12, 14, 12)],
		["PanelGlass", _sb(Color(UiKit.BG0, 0.62), Color(UiKit.LINE, 0.6), 1, 4, 18, 16, 18, 16)],
		["PanelRaised", _sb(Color(UiKit.BG2, 0.96), UiKit.LINE, 1, 4, 16, 12, 16, 12)],
		["Card", _sb(Color(UiKit.BG2, 0.95), UiKit.LINE, 1, 4, 12, 10, 12, 10)],
		["Toast", _sb(Color(UiKit.BG2, 0.97), UiKit.LINE_BRIGHT, 1, 4, 16, 10, 16, 10)],
		["Chip", _sb(Color(UiKit.BG3, 0.8), UiKit.LINE, 1, 3, 7, 1, 8, 1)],
		["KeyCap", _sb(Color(UiKit.BG3, 1.0), UiKit.LINE_BRIGHT, 1, 3, 6, 0, 6, 1)],
	]
	for p in panels:
		var pn: StringName = StringName(String(p[0]))
		t.set_type_variation(pn, &"PanelContainer")
		t.set_stylebox("panel", pn, p[1] as StyleBox)

	# ---------------------------------------------------------------- buttons
	var b_normal := _sb(Color(UiKit.BG2, 0.94), UiKit.LINE, 1, 3, 18, 8, 18, 8)
	var b_hover := _sb(Color(UiKit.BG3, 0.98), UiKit.LINE_BRIGHT, 1, 3, 18, 8, 18, 8)
	var b_pressed := _sb(Color(UiKit.ACCENT_DARK, 0.95), UiKit.ACCENT, 1, 3, 18, 8, 18, 8)
	var b_disabled := _sb(Color(UiKit.BG1, 0.6), Color(UiKit.LINE, 0.5), 1, 3, 18, 8, 18, 8)
	_button_family(t, &"Button", b_normal, b_hover, b_pressed, b_disabled, display_semi, 21,
		UiKit.TEXT, Color.WHITE, Color.WHITE)
	t.set_constant("h_separation", "Button", 8)
	t.set_constant("outline_size", "Button", 0)
	# OptionButton / MenuButton share the button look
	for bt in [&"OptionButton", &"MenuButton"]:
		_button_family(t, bt, b_normal, b_hover, b_pressed, b_disabled, body, 18,
			UiKit.TEXT, Color.WHITE, Color.WHITE)
	t.set_constant("arrow_margin", "OptionButton", 10)

	var prim_n := _sb(UiKit.ACCENT, UiKit.ACCENT, 1, 3, 22, 9, 22, 9)
	var prim_h := _sb(UiKit.ACCENT_BRIGHT, UiKit.ACCENT_BRIGHT, 1, 3, 22, 9, 22, 9)
	var prim_p := _sb(UiKit.ACCENT_DARK, UiKit.ACCENT, 1, 3, 22, 9, 22, 9)
	t.set_type_variation(&"PrimaryButton", &"Button")
	_button_family(t, &"PrimaryButton", prim_n, prim_h, prim_p, b_disabled, display, 23, Color.WHITE, Color.WHITE, Color.WHITE)

	var dang_n := _sb(Color(UiKit.BG2, 0.94), Color(UiKit.ERR, 0.7), 1, 3, 18, 8, 18, 8)
	var dang_h := _sb(Color(UiKit.ERR, 0.22), UiKit.ERR, 1, 3, 18, 8, 18, 8)
	t.set_type_variation(&"DangerButton", &"Button")
	_button_family(t, &"DangerButton", dang_n, dang_h, prim_p, b_disabled, display_semi, 21, UiKit.ERR.lerp(UiKit.TEXT, 0.3), Color.WHITE, Color.WHITE)

	var ghost_n := _sb(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 3, 12, 6, 12, 6)
	var ghost_h := _sb(Color(UiKit.BG3, 0.7), Color(0, 0, 0, 0), 0, 3, 12, 6, 12, 6)
	t.set_type_variation(&"GhostButton", &"Button")
	_button_family(t, &"GhostButton", ghost_n, ghost_h, ghost_h, ghost_n, body_semi, 17, UiKit.TEXT_DIM, UiKit.TEXT, UiKit.TEXT)

	var sel := _sb(Color(UiKit.BG3, 0.98), UiKit.ACCENT, 2, 3, 18, 8, 18, 8)
	sel.border_width_top = 1
	sel.border_width_right = 1
	sel.border_width_bottom = 1
	sel.border_width_left = 4
	t.set_type_variation(&"ValueButton", &"Button")
	_button_family(t, &"ValueButton", b_normal, b_hover, sel, b_disabled, body, 18, UiKit.TEXT, Color.WHITE, Color.WHITE)

	var small_n := _sb(Color(UiKit.BG2, 0.94), UiKit.LINE, 1, 3, 10, 3, 10, 3)
	var small_h := _sb(Color(UiKit.BG3, 0.98), UiKit.LINE_BRIGHT, 1, 3, 10, 3, 10, 3)
	var small_p := _sb(Color(UiKit.ACCENT_DARK, 0.95), UiKit.ACCENT, 1, 3, 10, 3, 10, 3)
	var small_d := _sb(Color(UiKit.BG1, 0.6), Color(UiKit.LINE, 0.5), 1, 3, 10, 3, 10, 3)
	t.set_type_variation(&"SmallButton", &"Button")
	_button_family(t, &"SmallButton", small_n, small_h, small_p, small_d, body_semi, 15, UiKit.TEXT_DIM, Color.WHITE, Color.WHITE)

	# home menu entries: big condensed type, accent bar on focus/hover
	var mi_n := _sb(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 0, 22, 4, 16, 4)
	var mi_h := _sb(Color(UiKit.ACCENT, 0.13), UiKit.ACCENT, 0, 0, 22, 4, 16, 4)
	mi_h.border_width_left = 4
	var mi_f := StyleBoxFlat.new()
	mi_f.draw_center = false
	mi_f.border_color = UiKit.ACCENT_BRIGHT
	mi_f.border_width_left = 4
	t.set_type_variation(&"MenuItem", &"Button")
	_button_family(t, &"MenuItem", mi_n, mi_h, mi_h, mi_n, _fv(UiKit.FONT_DISPLAY, 2), 36, UiKit.TEXT_DIM, Color.WHITE, Color.WHITE)
	t.set_stylebox("focus", &"MenuItem", mi_f)

	# tab strip buttons (toggle mode; pressed == selected tab)
	var tb_n := _sb(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 0, 16, 8, 16, 8)
	var tb_h := _sb(Color(UiKit.BG3, 0.6), Color(0, 0, 0, 0), 0, 0, 16, 8, 16, 8)
	var tb_p := _sb(Color(UiKit.BG1, 0.95), UiKit.ACCENT, 0, 0, 16, 8, 16, 8)
	tb_p.border_width_bottom = 3
	var tb_f := StyleBoxFlat.new()
	tb_f.draw_center = false
	tb_f.border_color = UiKit.ACCENT_BRIGHT
	tb_f.set_border_width_all(2)
	t.set_type_variation(&"TabButton", &"Button")
	_button_family(t, &"TabButton", tb_n, tb_h, tb_p, tb_n, display, 21, UiKit.TEXT_FAINT, UiKit.TEXT, Color.WHITE)
	t.set_stylebox("focus", &"TabButton", tb_f)

	# check boxes: text + default glyphs; switches are drawn by UiSwitch
	for ct in [&"CheckBox", &"CheckButton"]:
		t.set_stylebox("normal", ct, _sb(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 3, 6, 4, 6, 4))
		t.set_stylebox("hover", ct, _sb(Color(UiKit.BG3, 0.6), Color(0, 0, 0, 0), 0, 3, 6, 4, 6, 4))
		t.set_stylebox("pressed", ct, _sb(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 3, 6, 4, 6, 4))
		t.set_stylebox("hover_pressed", ct, _sb(Color(UiKit.BG3, 0.6), Color(0, 0, 0, 0), 0, 3, 6, 4, 6, 4))
		t.set_stylebox("focus", ct, _focus_box())
		t.set_color("font_color", ct, UiKit.TEXT)
		t.set_color("font_hover_color", ct, Color.WHITE)
		t.set_color("font_pressed_color", ct, UiKit.TEXT)
		t.set_color("font_hover_pressed_color", ct, Color.WHITE)
		t.set_color("font_focus_color", ct, Color.WHITE)
		t.set_font("font", ct, body)
		t.set_font_size("font_size", ct, 18)

	# ---------------------------------------------------------------- text entry
	var le_n := _sb(Color(UiKit.BG0, 0.92), UiKit.LINE, 1, 3, 12, 8, 12, 8)
	var le_f := _sb(Color(UiKit.BG0, 0.95), UiKit.ACCENT_BRIGHT, 2, 3, 12, 8, 12, 8)
	var le_ro := _sb(Color(UiKit.BG1, 0.6), Color(UiKit.LINE, 0.5), 1, 3, 12, 8, 12, 8)
	t.set_stylebox("normal", "LineEdit", le_n)
	t.set_stylebox("focus", "LineEdit", le_f)
	t.set_stylebox("read_only", "LineEdit", le_ro)
	t.set_color("font_color", "LineEdit", UiKit.TEXT)
	t.set_color("font_placeholder_color", "LineEdit", UiKit.TEXT_FAINT)
	t.set_color("caret_color", "LineEdit", UiKit.ACCENT_BRIGHT)
	t.set_color("selection_color", "LineEdit", Color(UiKit.ACCENT, 0.45))
	t.set_color("font_selected_color", "LineEdit", Color.WHITE)
	t.set_font("font", "LineEdit", body)
	t.set_font_size("font_size", "LineEdit", 18)
	t.set_constant("caret_width", "LineEdit", 2)
	t.set_stylebox("normal", "TextEdit", le_n)
	t.set_stylebox("focus", "TextEdit", le_f)
	t.set_color("font_color", "TextEdit", UiKit.TEXT)

	# ---------------------------------------------------------------- ranges
	var track := _sb(Color(UiKit.BG0, 0.95), UiKit.LINE, 1, 3, 0, 3, 0, 3)
	var track_fill := _sb(UiKit.ACCENT, Color(0, 0, 0, 0), 0, 3, 0, 3, 0, 3)
	var track_fill_hl := _sb(UiKit.ACCENT_BRIGHT, Color(0, 0, 0, 0), 0, 3, 0, 3, 0, 3)
	t.set_stylebox("slider", "HSlider", track)
	t.set_stylebox("grabber_area", "HSlider", track_fill)
	t.set_stylebox("grabber_area_highlight", "HSlider", track_fill_hl)
	t.set_stylebox("focus", "HSlider", _focus_box(4, 4.0))
	t.set_constant("center_grabber", "HSlider", 1)
	t.set_icon("grabber", "HSlider", _circle_icon(18, UiKit.TEXT))
	t.set_icon("grabber_highlight", "HSlider", _circle_icon(18, Color.WHITE))
	t.set_icon("grabber_disabled", "HSlider", _circle_icon(18, UiKit.TEXT_FAINT))
	t.set_icon("tick", "HSlider", _circle_icon(4, UiKit.LINE_BRIGHT))

	var pb_bg := _sb(Color(UiKit.BG0, 0.95), UiKit.LINE, 1, 2, 0, 0, 0, 0)
	var pb_fill := _sb(UiKit.ACCENT, Color(0, 0, 0, 0), 0, 2, 0, 0, 0, 0)
	t.set_stylebox("background", "ProgressBar", pb_bg)
	t.set_stylebox("fill", "ProgressBar", pb_fill)
	t.set_color("font_color", "ProgressBar", UiKit.TEXT)
	t.set_font_size("font_size", "ProgressBar", 13)
	t.set_type_variation(&"XpBar", &"ProgressBar")
	t.set_stylebox("fill", &"XpBar", _sb(UiKit.GOLD, Color(0, 0, 0, 0), 0, 2, 0, 0, 0, 0))
	t.set_stylebox("background", &"XpBar", pb_bg)
	t.set_type_variation(&"HealthBar", &"ProgressBar")
	t.set_stylebox("fill", &"HealthBar", _sb(UiKit.TEXT_DIM, Color(0, 0, 0, 0), 0, 2, 0, 0, 0, 0))
	t.set_stylebox("background", &"HealthBar", pb_bg)

	# ---------------------------------------------------------------- scrolling
	var blank: ImageTexture = _blank_icon()
	for sb_type in [&"VScrollBar", &"HScrollBar"]:
		t.set_stylebox("scroll", sb_type, _sb(Color(UiKit.BG0, 0.5), Color(0, 0, 0, 0), 0, 3, 3, 3, 3, 3))
		t.set_stylebox("scroll_focus", sb_type, _sb(Color(UiKit.BG0, 0.5), Color(0, 0, 0, 0), 0, 3, 3, 3, 3, 3))
		t.set_stylebox("grabber", sb_type, _sb(UiKit.LINE_BRIGHT, Color(0, 0, 0, 0), 0, 3, 3, 3, 3, 3))
		t.set_stylebox("grabber_highlight", sb_type, _sb(UiKit.TEXT_FAINT, Color(0, 0, 0, 0), 0, 3, 3, 3, 3, 3))
		t.set_stylebox("grabber_pressed", sb_type, _sb(UiKit.TEXT_DIM, Color(0, 0, 0, 0), 0, 3, 3, 3, 3, 3))
		for ic in ["increment", "increment_highlight", "increment_pressed", "decrement", "decrement_highlight", "decrement_pressed"]:
			t.set_icon(ic, sb_type, blank)
	t.set_stylebox("panel", "ScrollContainer", _empty())
	t.set_stylebox("focus", "ScrollContainer", _empty())

	# ---------------------------------------------------------------- tabs
	var tab_sel := _sb(Color(UiKit.BG1, 0.96), UiKit.ACCENT, 0, 0, 18, 9, 18, 9)
	tab_sel.border_width_bottom = 3
	var tab_un := _sb(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 0, 18, 9, 18, 9)
	var tab_hov := _sb(Color(UiKit.BG3, 0.6), Color(0, 0, 0, 0), 0, 0, 18, 9, 18, 9)
	for tt in [&"TabBar", &"TabContainer"]:
		t.set_stylebox("tab_selected", tt, tab_sel)
		t.set_stylebox("tab_unselected", tt, tab_un)
		t.set_stylebox("tab_hovered", tt, tab_hov)
		t.set_stylebox("tab_focus", tt, _focus_box(2, 0.0))
		t.set_stylebox("tab_disabled", tt, tab_un)
		t.set_font("font", tt, display)
		t.set_font_size("font_size", tt, 21)
		t.set_color("font_selected_color", tt, Color.WHITE)
		t.set_color("font_unselected_color", tt, UiKit.TEXT_FAINT)
		t.set_color("font_hovered_color", tt, UiKit.TEXT)
		t.set_color("font_disabled_color", tt, UiKit.TEXT_FAINT)
	t.set_stylebox("panel", "TabContainer", _sb(Color(UiKit.BG1, 0.94), UiKit.LINE, 1, 0, 20, 16, 20, 16))
	t.set_stylebox("tabbar_background", "TabContainer", _sb(Color(UiKit.BG0, 0.75), Color(0, 0, 0, 0), 0, 0, 0, 0, 0, 0))

	# ---------------------------------------------------------------- popups, lists, tooltips
	t.set_stylebox("panel", "PopupMenu", _sb(Color(UiKit.BG1, 0.99), UiKit.LINE_BRIGHT, 1, 3, 6, 6, 6, 6))
	t.set_stylebox("hover", "PopupMenu", _sb(Color(UiKit.ACCENT, 0.28), Color(0, 0, 0, 0), 0, 2, 8, 4, 8, 4))
	t.set_color("font_color", "PopupMenu", UiKit.TEXT)
	t.set_color("font_hover_color", "PopupMenu", Color.WHITE)
	t.set_color("font_disabled_color", "PopupMenu", UiKit.TEXT_FAINT)
	t.set_font("font", "PopupMenu", body)
	t.set_font_size("font_size", "PopupMenu", 18)
	t.set_constant("v_separation", "PopupMenu", 8)
	t.set_stylebox("panel", "PopupPanel", _sb(Color(UiKit.BG1, 0.99), UiKit.LINE_BRIGHT, 1, 3, 8, 8, 8, 8))
	t.set_stylebox("panel", "TooltipPanel", _sb(Color(UiKit.BG2, 0.98), UiKit.LINE_BRIGHT, 1, 3, 10, 6, 10, 6))
	t.set_color("font_color", "TooltipLabel", UiKit.TEXT)
	t.set_font("font", "TooltipLabel", body_regular)
	t.set_font_size("font_size", "TooltipLabel", 16)

	t.set_stylebox("panel", "ItemList", _sb(Color(UiKit.BG0, 0.8), UiKit.LINE, 1, 3, 6, 6, 6, 6))
	t.set_stylebox("focus", "ItemList", _focus_box(3, 0.0))
	t.set_stylebox("selected", "ItemList", _sb(Color(UiKit.ACCENT, 0.25), Color(0, 0, 0, 0), 0, 2, 4, 4, 4, 4))
	t.set_stylebox("selected_focus", "ItemList", _sb(Color(UiKit.ACCENT, 0.35), UiKit.ACCENT, 1, 2, 4, 4, 4, 4))
	t.set_stylebox("cursor", "ItemList", _focus_box(2, 0.0))
	t.set_stylebox("cursor_unfocused", "ItemList", _empty())
	t.set_color("font_color", "ItemList", UiKit.TEXT_DIM)
	t.set_color("font_selected_color", "ItemList", Color.WHITE)
	t.set_color("font_hovered_color", "ItemList", UiKit.TEXT)

	t.set_color("default_color", "RichTextLabel", UiKit.TEXT)
	t.set_font("normal_font", "RichTextLabel", body_regular)
	t.set_font("bold_font", "RichTextLabel", body_bold)
	t.set_font("italics_font", "RichTextLabel", body_regular)
	t.set_font_size("normal_font_size", "RichTextLabel", 17)
	t.set_font_size("bold_font_size", "RichTextLabel", 17)
	t.set_stylebox("focus", "RichTextLabel", _empty())
	t.set_stylebox("normal", "RichTextLabel", _empty())

	t.set_constant("separation", "HSeparator", 12)
	t.set_stylebox("separator", "HSeparator", _line_box(false))
	t.set_constant("separation", "VSeparator", 12)
	t.set_stylebox("separator", "VSeparator", _line_box(true))

	# window/dialogs (only used by engine popups; screens use UiModal)
	t.set_stylebox("panel", "AcceptDialog", _sb(Color(UiKit.BG1, 0.99), UiKit.LINE_BRIGHT, 1, 4, 16, 16, 16, 16))
	return t


static func _line_box(vertical: bool) -> StyleBoxLine:
	var s := StyleBoxLine.new()
	s.color = UiKit.LINE
	s.thickness = 1
	s.vertical = vertical
	return s


static func _circle_icon(px: int, color: Color) -> ImageTexture:
	## Anti-aliased filled circle with a dark rim (slider grabbers).
	var img := Image.create(px, px, false, Image.FORMAT_RGBA8)
	var r: float = px * 0.5
	var rim: Color = UiKit.BG0
	for y in range(px):
		for x in range(px):
			var d: float = Vector2(x + 0.5 - r, y + 0.5 - r).length()
			var outer: float = clampf(r - d, 0.0, 1.0)
			var inner: float = clampf((r - 2.0) - d, 0.0, 1.0)
			var c: Color = rim.lerp(color, inner)
			c.a = outer
			img.set_pixel(x, y, c)
	return ImageTexture.create_from_image(img)


static func _blank_icon() -> ImageTexture:
	var img := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	return ImageTexture.create_from_image(img)
