class_name UiToggle
extends Button
## On/off control drawn with canvas primitives (crisp at every scale): "switch" (pill + knob,
## state text On/Off) or "check" (box + tick). Shape and text carry the state, not colour.

@export var style: String = "switch"
@export var show_state_text: bool = true
var label_text: String = ""


func _init(p_label: String = "", p_style: String = "switch", pressed_now: bool = false) -> void:
	label_text = p_label
	style = p_style
	toggle_mode = true
	button_pressed = pressed_now
	focus_mode = Control.FOCUS_ALL
	theme_type_variation = &"GhostButton"
	alignment = HORIZONTAL_ALIGNMENT_LEFT
	custom_minimum_size = Vector2(0, 40)
	_update_text()


func _ready() -> void:
	UiKit.hover_focus(self)
	toggled.connect(func(_on: bool) -> void:
		UiKit.play("ui_select")
		_update_text()
		queue_redraw())


func _indicator_w() -> float:
	return 50.0 if style == "switch" else 24.0


func _update_text() -> void:
	var pad: String = "            " if style == "switch" else "        "
	var t: String = label_text
	if style == "switch" and show_state_text:
		t = ("On" if button_pressed else "Off") + (("  ·  " + label_text) if label_text != "" else "")
	text = pad + t


func set_pressed_quiet(on: bool) -> void:
	set_pressed_no_signal(on)
	_update_text()
	queue_redraw()


func _draw() -> void:
	var on: bool = button_pressed
	var h: float = size.y
	var x0: float = 12.0
	var dis: bool = disabled
	if style == "switch":
		var w: float = 44.0
		var th: float = 24.0
		var r := Rect2(Vector2(x0, (h - th) * 0.5), Vector2(w, th))
		var track := StyleBoxFlat.new()
		track.set_corner_radius_all(int(th * 0.5))
		track.bg_color = (UiKit.ACCENT if on else UiKit.BG0) if not dis else UiKit.BG1
		track.border_color = UiKit.ACCENT_BRIGHT if on else UiKit.LINE_BRIGHT
		track.set_border_width_all(1)
		track.anti_aliasing = true
		draw_style_box(track, r)
		var kr: float = th * 0.5 - 4.0
		var kx: float = r.position.x + (r.size.x - th * 0.5) if on else r.position.x + th * 0.5
		draw_circle(Vector2(kx, r.position.y + th * 0.5), kr, Color.WHITE if on else UiKit.TEXT_DIM, true, -1.0, true)
	else:
		var s: float = 20.0
		var r2 := Rect2(Vector2(x0, (h - s) * 0.5), Vector2(s, s))
		var box := StyleBoxFlat.new()
		box.set_corner_radius_all(3)
		box.bg_color = UiKit.ACCENT if on else UiKit.BG0
		box.border_color = UiKit.ACCENT_BRIGHT if on else UiKit.LINE_BRIGHT
		box.set_border_width_all(2 if not on else 1)
		box.anti_aliasing = true
		draw_style_box(box, r2)
		if on:
			var p0 := r2.position
			draw_polyline(PackedVector2Array([p0 + Vector2(4.5, 10.5), p0 + Vector2(8.5, 14.5), p0 + Vector2(15.5, 6.0)]), Color.WHITE, 2.4, true)
