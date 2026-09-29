class_name UiKit
extends RefCounted
## Shared look & feel for WILDRUSH screens (docs/UI_CONTRACT.md): palette, fonts, widget
## factories, focus/sound helpers and formatting. Colour is always paired with a shape, icon
## or label; team/relation colours come from Settings.relation_color(), never from here.

# ------------------------------------------------------------------------------------------
# palette (dark, restrained esports look; brand red from the WILDRUSH icon)
# ------------------------------------------------------------------------------------------
const BG0: Color = Color("0b0c0f")
const BG1: Color = Color("121419")
const BG2: Color = Color("1a1d23")
const BG3: Color = Color("252933")
const LINE: Color = Color("2c313b")
const LINE_BRIGHT: Color = Color("454d5c")
const TEXT: Color = Color("ece7dd")
const TEXT_DIM: Color = Color("a6abb4")
const TEXT_FAINT: Color = Color("6f7580")
const ACCENT: Color = Color("d23b41")
const ACCENT_BRIGHT: Color = Color("f05a5f")
const ACCENT_DARK: Color = Color("7e1f24")
const GOLD: Color = Color("e2b347")
const OK: Color = Color("58c27d")
const WARN: Color = Color("e8a33d")
const ERR: Color = Color("ef5b5f")

const FONT_BODY: FontFile = preload("res://assets/ui/fonts/Barlow-Medium.ttf")
const FONT_BODY_REGULAR: FontFile = preload("res://assets/ui/fonts/Barlow-Regular.ttf")
const FONT_BODY_SEMIBOLD: FontFile = preload("res://assets/ui/fonts/Barlow-SemiBold.ttf")
const FONT_BODY_BOLD: FontFile = preload("res://assets/ui/fonts/Barlow-Bold.ttf")
const FONT_DISPLAY: FontFile = preload("res://assets/ui/fonts/BarlowCondensed-Bold.ttf")
const FONT_DISPLAY_SEMIBOLD: FontFile = preload("res://assets/ui/fonts/BarlowCondensed-SemiBold.ttf")
const FONT_DISPLAY_XBOLD: FontFile = preload("res://assets/ui/fonts/BarlowCondensed-ExtraBold.ttf")
const FONT_DISPLAY_ITALIC: FontFile = preload("res://assets/ui/fonts/BarlowCondensed-ExtraBoldItalic.ttf")
const FONT_SYMBOLS_PATH: String = "res://assets/ui/fonts/DejaVuSans.ttf"

## Fur tones used by the vector species emblems and the preview stand-in (spec §6 sheets).
const FUR: Dictionary = {
	"nyx": Color("8d9097"), "bruno": Color("c99c63"), "vex": Color("c8622a"),
	"hops": Color("e9e4da"), "scrap": Color("7d8088"),
}
const SPECIES_LABEL: Dictionary = {"cat": "Cat", "dog": "Dog", "fox": "Fox", "rabbit": "Rabbit", "raccoon": "Raccoon"}
const BADGE_TIERS: Array[String] = ["initiate", "adept", "veteran", "master"]
const TEAM_NAMES: Array[String] = ["North", "South"]

static var _focus_quiet_until_ms: int = 0


# ------------------------------------------------------------------------------------------
# factories
# ------------------------------------------------------------------------------------------
static func label(text: String, variation: StringName = &"", wrap: bool = false) -> Label:
	var l := Label.new()
	l.text = text
	if variation != &"":
		l.theme_type_variation = variation
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.custom_minimum_size.x = 40.0
	return l


static func button(text: String, variation: StringName = &"", cb: Callable = Callable()) -> Button:
	var b := Button.new()
	b.text = text
	if variation != &"":
		b.theme_type_variation = variation
	b.focus_mode = Control.FOCUS_ALL
	hover_focus(b)
	b.pressed.connect(func() -> void: play("ui_select"))
	if cb.is_valid():
		b.pressed.connect(cb)
	return b


static func vbox(sep: int = 8) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", sep)
	return v


static func hbox(sep: int = 8) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", sep)
	return h


static func grid(cols: int, hsep: int = 8, vsep: int = 8) -> GridContainer:
	var g := GridContainer.new()
	g.columns = cols
	g.add_theme_constant_override("h_separation", hsep)
	g.add_theme_constant_override("v_separation", vsep)
	return g


static func panel(variation: StringName = &"") -> PanelContainer:
	var p := PanelContainer.new()
	if variation != &"":
		p.theme_type_variation = variation
	return p


static func margin(l: int, t: int, r: int, b: int) -> MarginContainer:
	var m := MarginContainer.new()
	m.add_theme_constant_override("margin_left", l)
	m.add_theme_constant_override("margin_top", t)
	m.add_theme_constant_override("margin_right", r)
	m.add_theme_constant_override("margin_bottom", b)
	return m


static func spacer(expand_h: bool = true, expand_v: bool = false) -> Control:
	var c := Control.new()
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if expand_h:
		c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if expand_v:
		c.size_flags_vertical = Control.SIZE_EXPAND_FILL
	return c


static func gap(px: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(px, px)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


static func rule() -> ColorRect:
	var r := ColorRect.new()
	r.color = LINE
	r.custom_minimum_size = Vector2(1, 1)
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return r


static func icon(kind: String, px: float = 18.0, color: Color = TEXT) -> UiIcon:
	var ic := UiIcon.new()
	ic.kind = kind
	ic.color = color
	ic.custom_minimum_size = Vector2(px, px)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return ic


static func chip(text: String, color: Color, icon_kind: String = "") -> PanelContainer:
	## Small status tag: always an icon/shape + text, tinted — never colour alone.
	var p := PanelContainer.new()
	p.theme_type_variation = &"Chip"
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(color, 0.14)
	sb.border_color = Color(color, 0.7)
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(3)
	sb.content_margin_left = 7.0
	sb.content_margin_right = 8.0
	sb.content_margin_top = 1.0
	sb.content_margin_bottom = 1.0
	p.add_theme_stylebox_override("panel", sb)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var h := hbox(5)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.add_child(h)
	if icon_kind != "":
		h.add_child(icon(icon_kind, 13.0, color))
	var l := label(text, &"ChipLabel")
	l.add_theme_color_override("font_color", color.lerp(TEXT, 0.35))
	h.add_child(l)
	return p


static func key_value(key: String, value: String) -> VBoxContainer:
	var v := vbox(0)
	v.add_child(label(key.to_upper(), &"Caption"))
	v.add_child(label(value, &"Stat"))
	return v


static func scroll(child: Control, horizontal: bool = false) -> ScrollContainer:
	var s := ScrollContainer.new()
	s.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO if horizontal else ScrollContainer.SCROLL_MODE_DISABLED
	s.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	s.follow_focus = true
	s.size_flags_vertical = Control.SIZE_EXPAND_FILL
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	child.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.add_child(child)
	return s


static func line_edit(placeholder: String, max_len: int = 0, secret: bool = false) -> LineEdit:
	var e := LineEdit.new()
	e.placeholder_text = placeholder
	e.secret = secret
	if max_len > 0:
		e.max_length = max_len
	e.custom_minimum_size = Vector2(220, 40)
	e.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	e.caret_blink = true
	e.select_all_on_focus = true
	return e


static func progress(value: float, max_value: float = 1.0, variation: StringName = &"") -> ProgressBar:
	var pb := ProgressBar.new()
	pb.max_value = max_value
	pb.value = value
	pb.show_percentage = false
	pb.custom_minimum_size = Vector2(80, 8)
	if variation != &"":
		pb.theme_type_variation = variation
	return pb


# ------------------------------------------------------------------------------------------
# focus & sound
# ------------------------------------------------------------------------------------------
static func hover_focus(c: Control) -> void:
	## Mouse hover moves keyboard/pad focus, so exactly one item is ever highlighted.
	c.mouse_entered.connect(func() -> void:
		if c.is_visible_in_tree() and c.focus_mode != Control.FOCUS_NONE and not (c is BaseButton and (c as BaseButton).disabled):
			if c.get_viewport() != null and c.get_viewport().gui_get_focus_owner() != c:
				c.grab_focus())


static func focus(c: Control) -> void:
	## Programmatic focus (screen entry) without the hover tick.
	if c == null or not c.is_inside_tree() or not c.is_visible_in_tree():
		return
	_focus_quiet_until_ms = Time.get_ticks_msec() + 60
	c.grab_focus()


static func focus_sound_allowed() -> bool:
	return Time.get_ticks_msec() > _focus_quiet_until_ms


static func _autoload(n: String) -> Node:
	## Autoloads looked up at runtime so this file also compiles in `--script` tools.
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null or tree.root == null:
		return null
	return tree.root.get_node_or_null(n)


static func play(cue: String) -> void:
	var ad: Node = _autoload("AudioDirector")
	if ad != null:
		ad.call("ui", cue)


static func music(track: String) -> void:
	var ad: Node = _autoload("AudioDirector")
	if ad != null:
		ad.call("music", track)


static func chain_vertical(ctrls: Array[Control], wrap: bool = false) -> void:
	## Explicit up/down neighbours for a vertical list (automatic search fails across columns).
	var n: int = ctrls.size()
	for i in range(n):
		var c: Control = ctrls[i]
		if i > 0:
			c.focus_neighbor_top = c.get_path_to(ctrls[i - 1])
		elif wrap:
			c.focus_neighbor_top = c.get_path_to(ctrls[n - 1])
		if i < n - 1:
			c.focus_neighbor_bottom = c.get_path_to(ctrls[i + 1])
		elif wrap:
			c.focus_neighbor_bottom = c.get_path_to(ctrls[0])


static func chain_horizontal(ctrls: Array[Control], wrap: bool = false) -> void:
	var n: int = ctrls.size()
	for i in range(n):
		var c: Control = ctrls[i]
		if i > 0:
			c.focus_neighbor_left = c.get_path_to(ctrls[i - 1])
		elif wrap:
			c.focus_neighbor_left = c.get_path_to(ctrls[n - 1])
		if i < n - 1:
			c.focus_neighbor_right = c.get_path_to(ctrls[i + 1])
		elif wrap:
			c.focus_neighbor_right = c.get_path_to(ctrls[0])


static func first_focusable(root: Node) -> Control:
	if root is Control:
		var c := root as Control
		if not c.is_visible_in_tree():
			return null
		if c.focus_mode == Control.FOCUS_ALL and not (c is BaseButton and (c as BaseButton).disabled):
			return c
	for ch in root.get_children():
		var f: Control = first_focusable(ch)
		if f != null:
			return f
	return null


static func clear_children(n: Node) -> void:
	for c in n.get_children():
		n.remove_child(c)
		c.queue_free()


# ------------------------------------------------------------------------------------------
# game data helpers
# ------------------------------------------------------------------------------------------
static func fighter_def(fid: String) -> FighterDef:
	var t: Node = _autoload("Tuning")
	if t == null:
		return null
	return t.call("fighter", fid) as FighterDef


static func fighter_name(fid: String) -> String:
	var d: FighterDef = fighter_def(fid)
	return d.display_name.capitalize() if d != null else fid.capitalize()


static func species_label(fid: String) -> String:
	var d: FighterDef = fighter_def(fid)
	if d == null:
		return ""
	return String(SPECIES_LABEL.get(d.species, d.species.capitalize()))


static func palette_info(fid: String, pal: String) -> Dictionary:
	## {"name", "primary", "secondary", "accent", "trim"} as Colors (+ name).
	var d: FighterDef = fighter_def(fid)
	var src: Dictionary = {}
	if d != null:
		src = d.palettes.get(pal, d.palettes.get("default", {}))
	var out: Dictionary = {"name": String(src.get("name", pal.capitalize()))}
	for k in ["primary", "secondary", "accent", "trim"]:
		out[k] = Color.html(String(src.get(k, "#555555")))
	return out


static func palette_display_name(fid: String, pal: String) -> String:
	return String(palette_info(fid, pal)["name"])


static func palette_ids(fid: String) -> Array[String]:
	## Palettes in unlock order (default, dusk, ember, frost).
	var out: Array[String] = []
	var d: FighterDef = fighter_def(fid)
	var order: Array[String] = ["default", "dusk", "ember", "frost"]
	for p in order:
		if d == null or d.palettes.has(p):
			out.append(p)
	if d != null:
		for k in d.palettes.keys():
			if not out.has(String(k)):
				out.append(String(k))
	return out


static func badge_display(badge: String) -> String:
	if badge == "":
		return "No badge"
	if badge == "pack_debut":
		return "Pack Debut"
	var parts: PackedStringArray = badge.split("_", false, 1)
	if parts.size() == 2:
		return "%s %s" % [fighter_name(parts[0]), parts[1].capitalize()]
	return badge.capitalize()


static func badge_icon_kind(badge: String) -> String:
	if badge == "pack_debut":
		return "paw"
	if badge.ends_with("_initiate"):
		return "circle"
	if badge.ends_with("_adept"):
		return "diamond"
	if badge.ends_with("_veteran"):
		return "shield"
	if badge.ends_with("_master"):
		return "star"
	return "dot"


static func mode_label(mode: String) -> String:
	match mode:
		"offline": return "Offline"
		"training": return "Training"
		"private": return "Private"
		"casual": return "Casual"
		"ranked": return "Ranked"
		"replay": return "Replay"
		"online": return "Online"
	return mode.capitalize()


# ------------------------------------------------------------------------------------------
# formatting
# ------------------------------------------------------------------------------------------
static func fmt_clock(seconds: float) -> String:
	var s: int = maxi(0, int(ceil(seconds - 0.001)))
	return "%d:%02d" % [s / 60, s % 60]


static func fmt_duration(seconds: float) -> String:
	var s: int = maxi(0, int(round(seconds)))
	if s >= 3600:
		return "%d:%02d:%02d" % [s / 3600, (s / 60) % 60, s % 60]
	return "%d:%02d" % [s / 60, s % 60]


static func fmt_bytes(n: int) -> String:
	if n < 1024:
		return "%d B" % n
	if n < 1024 * 1024:
		return "%.1f KB" % (n / 1024.0)
	return "%.1f MB" % (n / 1048576.0)


static func fmt_datetime(iso: String) -> String:
	## RFC 3339 / ISO UTC string -> local "YYYY-MM-DD HH:MM".
	if iso == "":
		return "—"
	var clean: String = iso.replace("Z", "").replace("T", " ")
	if clean.length() > 19:
		clean = clean.substr(0, 19)
	var unix: int = Time.get_unix_time_from_datetime_string(clean.replace(" ", "T"))
	if unix <= 0:
		return clean.substr(0, 16)
	return fmt_unix(unix)


static func fmt_unix(unix: int) -> String:
	var bias_min: int = int(Time.get_time_zone_from_system().get("bias", 0))
	var d: Dictionary = Time.get_datetime_dict_from_unix_time(unix + bias_min * 60)
	return "%04d-%02d-%02d %02d:%02d" % [int(d["year"]), int(d["month"]), int(d["day"]), int(d["hour"]), int(d["minute"])]


static func tr_score(score: Variant) -> String:
	if score is Array and (score as Array).size() >= 2:
		return "%d – %d" % [int(score[0]), int(score[1])]
	return "—"
