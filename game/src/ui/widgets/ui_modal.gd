class_name UiModal
extends Control
## Modal dialog: dims and blocks everything behind it, traps focus, `ui_cancel` picks the
## cancel choice (if any). Works on top of menus and on top of a running 3D match.
##   var m := UiModal.open(self, "Quit WILDRUSH?", "Unsaved …", [["quit", "Quit", &"DangerButton"], ["cancel", "Cancel", &""]])
##   var id: String = await m.chosen

signal chosen(id: String)

var cancel_id: String = "cancel"
var body: VBoxContainer
var buttons_row: HBoxContainer
var title_label: Label
var message_label: Label
var _buttons: Array[Button] = []
var _prev_focus: Control = null
var _closed: bool = false


static func open(parent: Node, title: String, message: String, buttons: Array, p_cancel_id: String = "cancel",
		default_id: String = "") -> UiModal:
	var m := UiModal.new()
	m.cancel_id = p_cancel_id
	parent.add_child(m)
	m._build(title, message, buttons, default_id)
	return m


func _init() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	process_mode = Node.PROCESS_MODE_ALWAYS
	z_index = 50


func _build(title: String, message: String, buttons: Array, default_id: String) -> void:
	var vp: Viewport = get_viewport()
	_prev_focus = vp.gui_get_focus_owner() if vp != null else null
	var dim := ColorRect.new()
	dim.color = Color(UiKit.BG0, 0.74)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)
	var p := UiKit.panel(&"PanelRaised")
	p.custom_minimum_size = Vector2(560, 0)
	center.add_child(p)
	var accent := ColorRect.new()
	accent.color = UiKit.ACCENT
	accent.custom_minimum_size = Vector2(0, 3)
	accent.mouse_filter = Control.MOUSE_FILTER_IGNORE
	body = UiKit.vbox(14)
	p.add_child(body)
	body.add_child(accent)
	title_label = UiKit.label(title.to_upper(), &"Heading")
	body.add_child(title_label)
	message_label = UiKit.label(message, &"", true)
	message_label.custom_minimum_size = Vector2(520, 0)
	message_label.add_theme_color_override("font_color", UiKit.TEXT_DIM)
	message_label.visible = message != ""
	body.add_child(message_label)
	buttons_row = UiKit.hbox(10)
	buttons_row.alignment = BoxContainer.ALIGNMENT_END
	body.add_child(UiKit.gap(4))
	body.add_child(buttons_row)
	var default_btn: Button = null
	for b in buttons:
		var arr: Array = b
		var id: String = String(arr[0])
		var btn := UiKit.button(String(arr[1]), (arr[2] as StringName) if arr.size() > 2 else &"")
		btn.custom_minimum_size = Vector2(130, 0)
		btn.pressed.connect(func() -> void: close(id))
		buttons_row.add_child(btn)
		_buttons.append(btn)
		if id == default_id or (default_btn == null and default_id == "" and id != cancel_id):
			default_btn = btn
	if default_btn == null and not _buttons.is_empty():
		default_btn = _buttons[0]
	var ctrls: Array[Control] = []
	for bb in _buttons:
		ctrls.append(bb)
	UiKit.chain_horizontal(ctrls, true)
	for bb in _buttons:
		bb.focus_neighbor_top = bb.get_path_to(bb)
		bb.focus_neighbor_bottom = bb.get_path_to(bb)
		bb.focus_next = bb.get_path_to(bb)
		bb.focus_previous = bb.get_path_to(bb)
	if default_btn != null:
		UiKit.focus.call_deferred(default_btn)
	UiKit.play("ui_notify")


func add_content(c: Control) -> void:
	## Extra content between the message and the buttons.
	body.add_child(c)
	body.move_child(c, body.get_child_count() - 3)


func buttons() -> Array[Button]:
	return _buttons


func close(id: String) -> void:
	if _closed:
		return
	_closed = true
	if id == cancel_id:
		UiKit.play("ui_back")
	chosen.emit(id)
	if _prev_focus != null and is_instance_valid(_prev_focus) and _prev_focus.is_visible_in_tree():
		UiKit.focus(_prev_focus)
	queue_free()


func _input(event: InputEvent) -> void:
	if _closed or not is_visible_in_tree():
		return
	if event.is_action_pressed("ui_cancel") and cancel_id != "":
		get_viewport().set_input_as_handled()
		close(cancel_id)
		return
	# keep focus inside the dialog
	var fo: Control = get_viewport().gui_get_focus_owner()
	if (event is InputEventKey or event is InputEventJoypadButton or event is InputEventJoypadMotion) and (fo == null or not is_ancestor_of(fo)):
		if not _buttons.is_empty():
			UiKit.focus(_buttons[0])
