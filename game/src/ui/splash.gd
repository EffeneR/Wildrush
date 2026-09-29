extends Control
## Splash (res://scenes/splash.tscn): brand sting, then the main menu. Any key, click or
## controller button skips it.

const HOLD_S: float = 1.6

var logo: WordmarkLogo
var _done: bool = false
var _tw: Tween = null


func _ready() -> void:
	var bg := MenuBackground.new()
	bg.intensity = 0.6
	add_child(bg)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)
	var v := UiKit.vbox(26)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	center.add_child(v)
	logo = WordmarkLogo.new()
	logo.font_size = 150
	logo.reveal = 0.0
	v.add_child(logo)
	var made := UiKit.label("MADE WITH GODOT ENGINE", &"Caption")
	made.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made.modulate.a = 0.0
	v.add_child(made)
	UiKit.music("music_menu")
	_tw = create_tween()
	_tw.tween_property(logo, "reveal", 1.0, 0.9).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_tw.parallel().tween_property(made, "modulate:a", 1.0, 0.9).set_delay(0.4)
	_tw.tween_interval(HOLD_S)
	_tw.tween_callback(finish)


func freeze_for_capture() -> void:
	## Screenshot tool: show the finished sting and never leave the scene.
	_done = true
	if _tw != null and _tw.is_valid():
		_tw.kill()
	logo.reveal = 1.0
	for c in logo.get_parent().get_children():
		(c as CanvasItem).modulate.a = 1.0


func finish() -> void:
	if _done:
		return
	_done = true
	if _tw != null and _tw.is_valid():
		_tw.kill()
	var t: Tween = create_tween()
	t.tween_property(self, "modulate:a", 0.0, 0.25)
	t.tween_callback(func() -> void: Game.goto(Game.SCENE_MENU, {}))


func _input(event: InputEvent) -> void:
	if _done:
		return
	var skip: bool = (event is InputEventKey and (event as InputEventKey).pressed) \
		or (event is InputEventMouseButton and (event as InputEventMouseButton).pressed) \
		or (event is InputEventJoypadButton and (event as InputEventJoypadButton).pressed)
	if skip:
		get_viewport().set_input_as_handled()
		finish()
