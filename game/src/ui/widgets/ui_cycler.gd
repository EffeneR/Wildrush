class_name UiCycler
extends Button
## Pad-friendly value selector "‹ value ›": left/right (D-pad, stick, arrow keys) step the
## value while focused; click/accept steps forward; clicking the left third steps back.

signal value_changed(index: int, value: Variant)

var options: Array = []      # [[value, label], ...]
var index: int = 0
var wrap_around: bool = true
var _left: UiIcon
var _right: UiIcon


func _init(p_options: Array = [], p_index: int = 0) -> void:
	options = p_options
	index = clampi(p_index, 0, maxi(0, options.size() - 1))
	focus_mode = Control.FOCUS_ALL
	custom_minimum_size = Vector2(240, 40)
	text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	clip_text = true


func _ready() -> void:
	theme_type_variation = &"ValueButton"
	UiKit.hover_focus(self)
	_left = UiKit.icon("chevron_left", 16.0, UiKit.TEXT_DIM)
	_left.follow_parent_font_color = true
	_left.set_anchors_and_offsets_preset(Control.PRESET_CENTER_LEFT)
	_left.offset_left = 10
	_left.offset_right = 26
	_left.offset_top = -8
	_left.offset_bottom = 8
	add_child(_left)
	_right = UiKit.icon("chevron_right", 16.0, UiKit.TEXT_DIM)
	_right.follow_parent_font_color = true
	_right.set_anchors_and_offsets_preset(Control.PRESET_CENTER_RIGHT)
	_right.offset_left = -26
	_right.offset_right = -10
	_right.offset_top = -8
	_right.offset_bottom = 8
	add_child(_right)
	_update_text()


func set_options(p_options: Array, p_index: int = 0) -> void:
	options = p_options
	index = clampi(p_index, 0, maxi(0, options.size() - 1))
	_update_text()


func select_value(v: Variant) -> void:
	for i in range(options.size()):
		if options[i][0] == v:
			index = i
			_update_text()
			return


func value() -> Variant:
	if options.is_empty():
		return null
	return options[index][0]


func step(d: int) -> void:
	if options.is_empty() or disabled:
		return
	var n: int = options.size()
	var ni: int = index + d
	if wrap_around:
		ni = posmod(ni, n)
	else:
		ni = clampi(ni, 0, n - 1)
	if ni == index:
		return
	index = ni
	_update_text()
	UiKit.play("ui_hover")
	value_changed.emit(index, options[index][0])


func _update_text() -> void:
	text = String(options[index][1]) if not options.is_empty() else "—"


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT and mb.position.x < size.x / 3.0:
			step(-1)
			accept_event()
			return
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			step(1)
			accept_event()
			return
	if event.is_action_pressed("ui_left", true):
		step(-1)
		accept_event()
	elif event.is_action_pressed("ui_right", true):
		step(1)
		accept_event()
	elif event.is_action_pressed("ui_accept"):
		step(1)
		accept_event()
