class_name PauseMenu
extends Control
## In-match menu (Esc / Start). Offline and training pause the simulation; online matches
## keep running (the server never pauses). Settings open the shared settings panel.

signal resumed
signal leave_requested

var online: bool = false
var _main: VBoxContainer
var _confirm: VBoxContainer
var _settings: Control = null


func build(p_online: bool, title: String) -> void:
	online = p_online
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.025, 0.03, 0.72)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(center)
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", HudStyle.panel_box(12, 0.92))
	panel.custom_minimum_size = Vector2(420, 0)
	center.add_child(panel)
	var stack := VBoxContainer.new()
	stack.add_theme_constant_override("separation", 10)
	panel.add_child(stack)
	var t := HudStyle.label(title, 34, HudStyle.INK, HudStyle.head_font(), 0)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	stack.add_child(t)
	if online:
		var sub := HudStyle.label("The match continues while this menu is open.", 14, HudStyle.INK_DIM, HudStyle.body_font(), 0)
		sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		stack.add_child(sub)
	_main = VBoxContainer.new()
	_main.add_theme_constant_override("separation", 8)
	stack.add_child(_main)
	var resume := _button("Resume", func() -> void: close())
	_button("Settings", _open_settings)
	_button("Leave match", func() -> void:
		_main.visible = false
		_confirm.visible = true
		(_confirm.get_child(1) as Button).grab_focus())
	_confirm = VBoxContainer.new()
	_confirm.add_theme_constant_override("separation", 8)
	_confirm.visible = false
	stack.add_child(_confirm)
	var q := HudStyle.label("Leave the match?" + ("\nLeaving a ranked match counts as a loss." if online else "\nThe match will count as a forfeit."), 16, HudStyle.INK, HudStyle.body_font(), 0)
	q.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_confirm.add_child(q)
	var yes := Button.new()
	yes.text = "Leave"
	yes.custom_minimum_size = Vector2(0, 44)
	yes.pressed.connect(func() -> void:
		AudioDirector.ui("ui_select")
		leave_requested.emit())
	_confirm.add_child(yes)
	var no := Button.new()
	no.text = "Stay"
	no.custom_minimum_size = Vector2(0, 44)
	no.pressed.connect(func() -> void:
		AudioDirector.ui("ui_back")
		_confirm.visible = false
		_main.visible = true
		resume.grab_focus())
	_confirm.add_child(no)
	visible = false


func _button(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 46)
	b.pressed.connect(func() -> void:
		AudioDirector.ui("ui_select")
		cb.call())
	b.focus_entered.connect(func() -> void: AudioDirector.ui("ui_hover"))
	_main.add_child(b)
	return b


func open() -> void:
	visible = true
	_main.visible = true
	_confirm.visible = false
	(_main.get_child(0) as Button).grab_focus()


func close() -> void:
	if _settings != null and is_instance_valid(_settings):
		_settings.queue_free()
		_settings = null
	visible = false
	resumed.emit()


func _open_settings() -> void:
	var path: String = "res://scenes/ui/settings_panel.tscn"
	if not ResourceLoader.exists(path):
		return
	var ps: PackedScene = load(path) as PackedScene
	_settings = ps.instantiate() as Control
	add_child(_settings)
	_main.visible = false
	if _settings.has_signal("closed"):
		_settings.connect("closed", func() -> void:
			_settings.queue_free()
			_settings = null
			_main.visible = true
			(_main.get_child(1) as Button).grab_focus())


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event.is_action_pressed("ui_cancel") or event.is_action_pressed("menu"):
		if _settings != null:
			return   # the settings panel handles its own back navigation
		if _confirm.visible:
			_confirm.visible = false
			_main.visible = true
			(_main.get_child(0) as Button).grab_focus()
		else:
			close()
		get_viewport().set_input_as_handled()
