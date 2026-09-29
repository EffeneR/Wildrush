class_name UiHintBar
extends HBoxContainer
## Input hints ("Enter Select · Esc Back" / "A Select · B Back"), switching glyphs with the last
## used device. Screens feed hints as [[kind, label], ...] with kind in
## accept | back | tabs | alt | adjust | scroll.

static var pad_mode: bool = false
static var _instances: Array[UiHintBar] = []

var hints: Array = []


static func note_input(event: InputEvent) -> void:
	## Called from screen roots' _input: tracks the last device kind for glyphs.
	var pad: bool = pad_mode
	if event is InputEventJoypadButton:
		pad = true
	elif event is InputEventJoypadMotion and absf((event as InputEventJoypadMotion).axis_value) > 0.5:
		pad = true
	elif event is InputEventKey or event is InputEventMouseButton:
		pad = false
	if pad != pad_mode:
		pad_mode = pad
		for h in _instances:
			if is_instance_valid(h):
				h._rebuild()


static func glyph(kind: String) -> String:
	if pad_mode:
		return {"accept": "A", "back": "B", "tabs": "LB  RB", "alt": "X", "adjust": "◀ ▶", "updown": "▲ ▼",
			"alt2": "Y"}.get(kind, "?")
	return {"accept": "Enter", "back": "Esc", "tabs": "Q  E", "alt": "Space", "adjust": "← →", "updown": "↑ ↓",
		"alt2": "Del"}.get(kind, "?")


func _init() -> void:
	add_theme_constant_override("separation", 18)
	alignment = BoxContainer.ALIGNMENT_END
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	size_flags_vertical = Control.SIZE_SHRINK_CENTER


func _enter_tree() -> void:
	_instances.append(self)


func _exit_tree() -> void:
	_instances.erase(self)


func set_hints(h: Array) -> void:
	hints = h
	_rebuild()


func _rebuild() -> void:
	UiKit.clear_children(self)
	for pair in hints:
		var arr: Array = pair
		var item := UiKit.hbox(7)
		item.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var cap := UiKit.panel(&"KeyCap")
		cap.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var g := UiKit.label(glyph(String(arr[0])), &"KeyGlyph")
		g.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		cap.add_child(g)
		item.add_child(cap)
		var l := UiKit.label(String(arr[1]).to_upper(), &"Caption")
		item.add_child(l)
		add_child(item)
