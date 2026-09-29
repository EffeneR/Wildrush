class_name PaletteButton
extends Button
## Palette choice: three colour chips + name; locked palettes show a lock and the mastery
## level that unlocks them (label, not colour, carries the state).

var fighter_id: String = ""
var palette_id: String = ""
var locked: bool = false
var unlock_level: int = 1
var _chips: HBoxContainer
var _name: Label
var _sub: Label
var _lock: UiIcon


func _init(fid: String, pal: String, p_locked: bool = false, p_unlock_level: int = 1) -> void:
	fighter_id = fid
	palette_id = pal
	locked = p_locked
	unlock_level = p_unlock_level
	toggle_mode = true
	focus_mode = Control.FOCUS_ALL
	custom_minimum_size = Vector2(150, 64)
	text = ""
	clip_contents = true


func _ready() -> void:
	UiKit.hover_focus(self)
	var info: Dictionary = UiKit.palette_info(fighter_id, palette_id)
	var n := StyleBoxFlat.new()
	n.bg_color = Color(UiKit.BG2, 0.95)
	n.border_color = UiKit.LINE
	n.set_border_width_all(1)
	n.set_corner_radius_all(3)
	var h: StyleBoxFlat = n.duplicate()
	h.bg_color = Color(UiKit.BG3, 0.98)
	h.border_color = UiKit.LINE_BRIGHT
	var p: StyleBoxFlat = n.duplicate()
	p.border_color = UiKit.ACCENT
	p.set_border_width_all(2)
	p.bg_color = Color(UiKit.BG3, 0.98)
	add_theme_stylebox_override("normal", n)
	add_theme_stylebox_override("hover", h)
	add_theme_stylebox_override("pressed", p)
	add_theme_stylebox_override("hover_pressed", p)
	add_theme_stylebox_override("disabled", n)
	var m := UiKit.margin(10, 7, 10, 7)
	m.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	m.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(m)
	var v := UiKit.vbox(3)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	m.add_child(v)
	_chips = UiKit.hbox(3)
	_chips.mouse_filter = Control.MOUSE_FILTER_IGNORE
	for k in ["primary", "secondary", "accent"]:
		var c := ColorRect.new()
		c.color = info[k]
		c.custom_minimum_size = Vector2(22, 12)
		c.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_chips.add_child(c)
	_lock = UiKit.icon("lock", 14.0, UiKit.TEXT_DIM)
	_chips.add_child(UiKit.spacer())
	_chips.add_child(_lock)
	v.add_child(_chips)
	_name = UiKit.label(String(info["name"]), &"Small")
	_name.clip_text = true
	_name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_name.add_theme_color_override("font_color", UiKit.TEXT)
	_name.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(_name)
	_sub = UiKit.label("", &"Caption")
	_sub.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(_sub)
	_refresh()


func set_locked(p_locked: bool, p_unlock_level: int) -> void:
	locked = p_locked
	unlock_level = p_unlock_level
	_refresh()


func _refresh() -> void:
	if _lock == null:
		return
	_lock.visible = locked
	_sub.visible = locked
	_sub.text = "MASTERY %d" % unlock_level
	for c in _chips.get_children():
		if c is ColorRect:
			(c as ColorRect).modulate = Color(1, 1, 1, 0.35) if locked else Color.WHITE
	_name.add_theme_color_override("font_color", UiKit.TEXT_FAINT if locked else UiKit.TEXT)
