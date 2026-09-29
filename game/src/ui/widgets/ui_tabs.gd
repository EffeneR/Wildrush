class_name UiTabs
extends HBoxContainer
## Tab strip (toggle buttons). Switch with click / accept, LB/RB on a controller, or Q/E and
## Ctrl+Tab on the keyboard (see `handle_shortcut`). Content switching is up to the owner via
## `tab_changed`.

signal tab_changed(index: int)

var current: int = 0
var tab_buttons: Array[Button] = []
var _group := ButtonGroup.new()


func _init() -> void:
	add_theme_constant_override("separation", 2)


func add_tab(title: String) -> Button:
	var b := Button.new()
	b.text = title.to_upper()
	b.theme_type_variation = &"TabButton"
	b.toggle_mode = true
	b.button_group = _group
	b.focus_mode = Control.FOCUS_ALL
	b.button_pressed = tab_buttons.is_empty()
	var i: int = tab_buttons.size()
	b.pressed.connect(func() -> void: select(i))
	UiKit.hover_focus(b)
	add_child(b)
	tab_buttons.append(b)
	return b


func select(i: int, emit: bool = true) -> void:
	if tab_buttons.is_empty():
		return
	i = clampi(i, 0, tab_buttons.size() - 1)
	var changed: bool = i != current
	current = i
	for j in range(tab_buttons.size()):
		tab_buttons[j].set_pressed_no_signal(j == i)
	if changed:
		UiKit.play("ui_select")
	if emit:
		tab_changed.emit(i)


func step(d: int) -> void:
	var n: int = tab_buttons.size()
	if n == 0:
		return
	var i: int = posmod(current + d, n)
	while not tab_buttons[i].visible and i != current:
		i = posmod(i + d, n)
	select(i)


static func shortcut_dir(event: InputEvent, focus_owner: Control) -> int:
	## -1 / +1 when `event` is a tab-switch shortcut, else 0.
	if event is InputEventJoypadButton and (event as InputEventJoypadButton).pressed:
		match (event as InputEventJoypadButton).button_index:
			JOY_BUTTON_LEFT_SHOULDER: return -1
			JOY_BUTTON_RIGHT_SHOULDER: return 1
	if event is InputEventKey and (event as InputEventKey).pressed and not (event as InputEventKey).echo:
		var k := event as InputEventKey
		if k.keycode == KEY_TAB and k.ctrl_pressed:
			return -1 if k.shift_pressed else 1
		if focus_owner is LineEdit or focus_owner is TextEdit:
			return 0
		if k.physical_keycode == KEY_Q and not k.ctrl_pressed and not k.alt_pressed:
			return -1
		if k.physical_keycode == KEY_E and not k.ctrl_pressed and not k.alt_pressed:
			return 1
	return 0


func handle_shortcut(event: InputEvent) -> bool:
	if not is_visible_in_tree():
		return false
	var d: int = shortcut_dir(event, get_viewport().gui_get_focus_owner())
	if d == 0:
		return false
	step(d)
	return true
