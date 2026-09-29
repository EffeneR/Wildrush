class_name FighterCard
extends Button
## Selectable fighter card (offline/training select, lobby character select, collection):
## portrait (file or runtime capture) or vector species emblem, name, role, mastery level and
## an explicit state tag (selected / taken / locked in) — never colour alone.

var fighter_id: String = "nyx"
var palette: String = "default"
var level: int = 0
## "" | "taken" | "locked" | "yours"
var state: String = ""
var state_text: String = ""
var compact: bool = false

var _portrait: TextureRect
var _emblem: FighterEmblem
var _name: Label
var _role: Label
var _level_chip: Control
var _veil: ColorRect
var _state_box: HBoxContainer
var _state_icon: UiIcon
var _state_label: Label
var _sel_bar: ColorRect
var _check: UiIcon


func _init(fid: String = "nyx", p_compact: bool = false) -> void:
	fighter_id = fid
	compact = p_compact
	toggle_mode = true
	focus_mode = Control.FOCUS_ALL
	clip_contents = true
	custom_minimum_size = Vector2(118, 150) if compact else Vector2(150, 206)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text = ""


func _ready() -> void:
	_apply_styles()
	UiKit.hover_focus(self)
	var d: FighterDef = UiKit.fighter_def(fighter_id)
	_emblem = FighterEmblem.new()
	_emblem.fighter_id = fighter_id
	_emblem.plate = false
	_emblem.set_anchors_preset(Control.PRESET_FULL_RECT)
	_emblem.anchor_bottom = 0.72
	_emblem.offset_left = 18
	_emblem.offset_right = -18
	_emblem.offset_top = 14
	add_child(_emblem)
	_portrait = TextureRect.new()
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	_portrait.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_portrait.offset_left = 1
	_portrait.offset_top = 1
	_portrait.offset_right = -1
	_portrait.offset_bottom = -1
	_portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_portrait.visible = false
	add_child(_portrait)
	var shade := TextureRect.new()
	var gt := GradientTexture2D.new()
	var g := Gradient.new()
	g.set_color(0, Color(UiKit.BG0, 0.0))
	g.set_color(1, Color(UiKit.BG0, 0.96))
	gt.gradient = g
	gt.fill_from = Vector2(0, 0)
	gt.fill_to = Vector2(0, 1)
	shade.texture = gt
	shade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	shade.stretch_mode = TextureRect.STRETCH_SCALE
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.anchor_top = 0.45
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(shade)
	var info := VBoxContainer.new()
	info.add_theme_constant_override("separation", -2)
	info.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	info.offset_left = 12
	info.offset_right = -10
	info.offset_bottom = -10
	info.offset_top = -64 if not compact else -52
	info.alignment = BoxContainer.ALIGNMENT_END
	info.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(info)
	_name = UiKit.label(d.display_name if d != null else fighter_id.to_upper(), &"Heading")
	if compact:
		_name.add_theme_font_size_override("font_size", 23)
	_name.mouse_filter = Control.MOUSE_FILTER_IGNORE
	info.add_child(_name)
	_role = UiKit.label(("%s · %s" % [UiKit.species_label(fighter_id), d.role]) if d != null else "", &"Small")
	_role.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_role.clip_text = true
	_role.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if compact:
		_role.text = UiKit.species_label(fighter_id)
		_role.add_theme_font_size_override("font_size", 13)
	info.add_child(_role)
	_sel_bar = ColorRect.new()
	_sel_bar.color = UiKit.ACCENT
	_sel_bar.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_sel_bar.offset_top = -4
	_sel_bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_sel_bar)
	_check = UiKit.icon("check", 20.0, Color.WHITE)
	_check.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	_check.position = Vector2(8, 8)
	_check.size = Vector2(20, 20)
	add_child(_check)
	_veil = ColorRect.new()
	_veil.color = Color(UiKit.BG0, 0.62)
	_veil.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_veil.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_veil)
	_state_box = UiKit.hbox(5)
	_state_box.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	_state_box.offset_top = 8
	_state_box.offset_left = 8
	_state_box.offset_right = -8
	_state_box.offset_bottom = 30
	_state_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_state_box)
	_state_icon = UiKit.icon("lock", 15.0, UiKit.TEXT)
	_state_box.add_child(_state_icon)
	_state_label = UiKit.label("", &"ChipLabel")
	_state_label.clip_text = true
	_state_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_state_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_state_box.add_child(_state_label)
	_level_chip = UiKit.chip("LV %d" % level, UiKit.GOLD, "star")
	_level_chip.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_level_chip.position = Vector2(size.x - 70, 8)
	add_child(_level_chip)
	toggled.connect(func(_on: bool) -> void: _refresh())
	resized.connect(_place_chip)
	_refresh()
	_load_portrait()


func _apply_styles() -> void:
	var n := StyleBoxFlat.new()
	n.bg_color = Color(UiKit.BG2, 0.96)
	n.border_color = UiKit.LINE
	n.set_border_width_all(1)
	n.set_corner_radius_all(4)
	var h: StyleBoxFlat = n.duplicate()
	h.bg_color = Color(UiKit.BG3, 0.98)
	h.border_color = UiKit.LINE_BRIGHT
	var p: StyleBoxFlat = n.duplicate()
	p.bg_color = Color(UiKit.BG3, 0.98)
	p.border_color = UiKit.ACCENT
	p.set_border_width_all(2)
	var dis: StyleBoxFlat = n.duplicate()
	dis.bg_color = Color(UiKit.BG1, 0.9)
	add_theme_stylebox_override("normal", n)
	add_theme_stylebox_override("hover", h)
	add_theme_stylebox_override("pressed", p)
	add_theme_stylebox_override("hover_pressed", p)
	add_theme_stylebox_override("disabled", dis)


func _place_chip() -> void:
	if _level_chip != null:
		var w: float = _level_chip.get_combined_minimum_size().x
		_level_chip.position = Vector2(size.x - w - 8, 8)


func set_level(lv: int) -> void:
	level = lv
	if _level_chip != null:
		UiKit.clear_children(_level_chip)
		var h := UiKit.hbox(4)
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(UiKit.icon("star", 12.0, UiKit.GOLD))
		var l := UiKit.label("LV %d" % lv, &"ChipLabel")
		l.add_theme_color_override("font_color", UiKit.GOLD.lerp(UiKit.TEXT, 0.35))
		h.add_child(l)
		_level_chip.add_child(h)
		_level_chip.visible = lv > 0
		_place_chip.call_deferred()


func set_state(p_state: String, p_text: String = "") -> void:
	state = p_state
	state_text = p_text
	_refresh()


func set_palette(p: String) -> void:
	palette = p
	_load_portrait()


func _load_portrait() -> void:
	var t: Texture2D = PortraitCache.get_portrait(fighter_id, palette)
	if t != null:
		_set_portrait(t)
		return
	var pc: PortraitCache = PortraitCache.instance()
	if pc != null and not pc.portrait_ready.is_connected(_on_portrait):
		pc.portrait_ready.connect(_on_portrait)


func _on_portrait(k: String, t: Texture2D) -> void:
	if k == PortraitCache.key(fighter_id, palette) and is_instance_valid(self):
		_set_portrait(t)


func _set_portrait(t: Texture2D) -> void:
	if _portrait == null:
		return
	_portrait.texture = t
	_portrait.visible = true
	_emblem.visible = false


func _refresh() -> void:
	if _veil == null:
		return
	var taken: bool = state == "taken"
	disabled = taken
	_veil.visible = taken
	_sel_bar.visible = button_pressed and not taken
	_check.visible = (button_pressed or state == "locked") and not taken
	_state_box.visible = state != ""
	_emblem.dimmed = taken
	match state:
		"taken":
			_state_icon.kind = "lock"
			_state_icon.color = UiKit.TEXT_DIM
			_state_label.text = state_text if state_text != "" else "TAKEN"
		"locked":
			_state_icon.kind = "check"
			_state_icon.color = UiKit.OK
			_state_label.text = state_text if state_text != "" else "LOCKED IN"
		"yours":
			_state_icon.kind = "user"
			_state_icon.color = UiKit.TEXT
			_state_label.text = state_text if state_text != "" else "YOUR PICK"
		_:
			_state_label.text = ""
	if _check.visible:
		_state_box.offset_left = 34
	else:
		_state_box.offset_left = 8
	_name.add_theme_color_override("font_color", UiKit.TEXT_FAINT if taken else (Color.WHITE if button_pressed else UiKit.TEXT))
