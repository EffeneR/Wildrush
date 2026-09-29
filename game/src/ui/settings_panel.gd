class_name SettingsPanel
extends Control
## Reusable settings overlay (res://scenes/ui/settings_panel.tscn, docs/UI_CONTRACT.md §7).
## Tabs: Display, Audio, Controls (full KB/M + pad rebinding with conflict → swap/cancel),
## Accessibility (colour mode with live swatches), Gameplay & Online. Works on top of menus
## and on top of a running (possibly paused) match; never changes scenes. Emits `closed`.

signal closed

const TABS: Array[String] = ["display", "audio", "controls", "access", "online"]
const TAB_TITLES: Array[String] = ["Display", "Audio", "Controls", "Accessibility", "Gameplay & Online"]
const RESOLUTIONS: Array[Vector2i] = [Vector2i(1280, 720), Vector2i(1366, 768), Vector2i(1600, 900), Vector2i(1920, 1080),
	Vector2i(2560, 1080), Vector2i(2560, 1440), Vector2i(3440, 1440), Vector2i(3840, 2160)]
const CAPTURE_TIMEOUT_S: float = 8.0

var tabs: UiTabs
var _content: VBoxContainer
var _scroll: ScrollContainer
var _hints: UiHintBar
var _tab_index: int = 0
var _modal_open: bool = false
var _capture: BindCapture = null
var _url_status: Label
var _url_icon: UiIcon
var _name_error: Label
var _region_error: Label
var _res_row_value: Control
var _res_note: Label
var _dirty: bool = false
## rebinding table buttons, rebuilt on bindings_changed
var _bind_buttons: Dictionary = {}   # "action|pad" -> Button


## Waits for one key/mouse (or pad) event and reports it. Lives inside the capture modal.
class BindCapture extends Control:
	signal captured(ev: InputEvent)
	signal cancelled
	var pad: bool = false
	var left_s: float = 8.0
	var bar: ProgressBar
	var _done: bool = false

	func _init(p_pad: bool, timeout_s: float) -> void:
		pad = p_pad
		left_s = timeout_s
		custom_minimum_size = Vector2(0, 10)
		process_mode = Node.PROCESS_MODE_ALWAYS

	func _ready() -> void:
		bar = UiKit.progress(1.0, 1.0)
		bar.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		add_child(bar)

	func _process(delta: float) -> void:
		if _done:
			return
		left_s -= delta
		bar.value = clampf(left_s / 8.0, 0.0, 1.0)
		if left_s <= 0.0:
			_done = true
			cancelled.emit()

	func _input(event: InputEvent) -> void:
		if _done:
			return
		if event is InputEventKey and (event as InputEventKey).pressed and not (event as InputEventKey).echo:
			var k := event as InputEventKey
			get_viewport().set_input_as_handled()
			if k.physical_keycode == KEY_ESCAPE or k.keycode == KEY_ESCAPE:
				_done = true
				cancelled.emit()
				return
			if pad:
				return
			var code: int = k.physical_keycode if k.physical_keycode != 0 else k.keycode
			if code == 0:
				return
			var e := InputEventKey.new()
			e.physical_keycode = code as Key
			_done = true
			captured.emit(e)
			return
		if event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
			var mb := event as InputEventMouseButton
			get_viewport().set_input_as_handled()
			if pad:
				return
			if mb.button_index in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE, MOUSE_BUTTON_XBUTTON1, MOUSE_BUTTON_XBUTTON2]:
				var e2 := InputEventMouseButton.new()
				e2.button_index = mb.button_index
				_done = true
				captured.emit(e2)
			return
		if event is InputEventJoypadButton and (event as InputEventJoypadButton).pressed:
			get_viewport().set_input_as_handled()
			if not pad:
				return
			var e3 := InputEventJoypadButton.new()
			e3.button_index = (event as InputEventJoypadButton).button_index
			_done = true
			captured.emit(e3)
			return
		if event is InputEventJoypadMotion:
			get_viewport().set_input_as_handled()
			var jm := event as InputEventJoypadMotion
			if not pad or absf(jm.axis_value) < 0.6:
				return
			var e4 := InputEventJoypadMotion.new()
			e4.axis = jm.axis
			e4.axis_value = signf(jm.axis_value)
			_done = true
			captured.emit(e4)
			return
		if event is InputEventMouseMotion:
			return
		get_viewport().set_input_as_handled()


func _init() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)


func _ready() -> void:
	_build()
	Settings.bindings_changed.connect(_refresh_bindings)
	open_tab(TABS[_tab_index])


func _build() -> void:
	var dim := ColorRect.new()
	dim.color = Color(UiKit.BG0, 0.84)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)
	var outer := UiKit.margin(40, 32, 40, 28)
	outer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	outer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(outer)
	var mw := MaxWidthContainer.new()
	mw.max_width = 1320.0
	mw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	outer.add_child(mw)
	var panel := UiKit.panel(&"PanelDark")
	mw.add_child(panel)
	var v := UiKit.vbox(12)
	panel.add_child(v)
	var head := UiKit.hbox(14)
	v.add_child(head)
	head.add_child(UiKit.icon("gear", 30.0, UiKit.ACCENT))
	head.add_child(UiKit.label("SETTINGS", &"Title"))
	head.add_child(UiKit.spacer())
	var back := UiKit.button("Back", &"", close)
	back.custom_minimum_size = Vector2(140, 0)
	head.add_child(back)
	tabs = UiTabs.new()
	for t in TAB_TITLES:
		tabs.add_tab(t)
	tabs.tab_changed.connect(func(i: int) -> void: _show_tab(i))
	v.add_child(tabs)
	v.add_child(UiKit.rule())
	_content = UiKit.vbox(10)
	_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var pad := UiKit.margin(4, 4, 18, 4)
	pad.add_child(_content)
	_scroll = UiKit.scroll(pad)
	v.add_child(_scroll)
	v.add_child(UiKit.rule())
	var foot := UiKit.hbox(12)
	v.add_child(foot)
	var note := UiKit.label("Changes apply immediately and are saved.", &"Small")
	foot.add_child(note)
	foot.add_child(UiKit.spacer())
	_hints = UiHintBar.new()
	_hints.set_hints([["accept", "Select"], ["adjust", "Change"], ["tabs", "Switch tab"], ["back", "Back"]])
	foot.add_child(_hints)


func open_tab(tab_name: String) -> void:
	var i: int = maxi(0, TABS.find(tab_name))
	if tabs != null:
		tabs.select(i, false)
	_show_tab(i)


func _show_tab(i: int) -> void:
	_tab_index = i
	UiKit.clear_children(_content)
	_bind_buttons.clear()
	match TABS[i]:
		"display": _build_display()
		"audio": _build_audio()
		"controls": _build_controls()
		"access": _build_access()
		"online": _build_online()
	_scroll.scroll_vertical = 0
	_focus_first.call_deferred()


func _focus_first() -> void:
	var f: Control = UiKit.first_focusable(_content)
	if f != null:
		UiKit.focus(f)
		# up from the first row goes to the tab strip
		f.focus_neighbor_top = f.get_path_to(tabs.tab_buttons[_tab_index])
	for b in tabs.tab_buttons:
		if f != null:
			b.focus_neighbor_bottom = b.get_path_to(f)


func close() -> void:
	if _modal_open:
		return
	Settings.save_settings()
	UiKit.play("ui_back")
	visible = false
	closed.emit()


func _unhandled_input(event: InputEvent) -> void:
	if not is_visible_in_tree() or _modal_open:
		return
	if tabs.handle_shortcut(event):
		get_viewport().set_input_as_handled()


func _input(event: InputEvent) -> void:
	## Back/tab shortcuts are taken in _input so an enclosing pause overlay (our parent in the
	## match scene) never sees the Esc/B that closes this panel.
	if not is_visible_in_tree():
		return
	UiHintBar.note_input(event)
	if _modal_open:
		return
	if event.is_action_pressed("ui_cancel") or (InputMap.has_action("menu") and event.is_action_pressed("menu")):
		get_viewport().set_input_as_handled()
		close()
		return
	# LB/RB also work while a slider/cycler has focus
	if event is InputEventJoypadButton and tabs.handle_shortcut(event):
		get_viewport().set_input_as_handled()


# ------------------------------------------------------------------------------------------
# row helpers
# ------------------------------------------------------------------------------------------
func _section(title: String) -> void:
	if _content.get_child_count() > 0:
		_content.add_child(UiKit.gap(10))
	var l := UiKit.label(title.to_upper(), &"Subheading")
	l.add_theme_color_override("font_color", UiKit.TEXT_DIM)
	_content.add_child(l)


func _row(label_text: String, ctrl: Control, help: String = "") -> HBoxContainer:
	var h := UiKit.hbox(18)
	var lv := UiKit.vbox(0)
	lv.custom_minimum_size = Vector2(360, 0)
	var l := UiKit.label(label_text)
	lv.add_child(l)
	if help != "":
		var hl := UiKit.label(help, &"Small", true)
		hl.custom_minimum_size = Vector2(340, 0)
		lv.add_child(hl)
	h.add_child(lv)
	ctrl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ctrl.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	h.add_child(ctrl)
	_content.add_child(h)
	return h


func _cycler(section: String, key: String, options: Array, on_change: Callable = Callable()) -> UiCycler:
	var cur: Variant = Settings.get_value(section, key)
	var idx: int = 0
	for i in range(options.size()):
		if options[i][0] == cur:
			idx = i
	var c := UiCycler.new(options, idx)
	c.custom_minimum_size = Vector2(320, 42)
	c.value_changed.connect(func(_i: int, v: Variant) -> void:
		Settings.set_value(section, key, v)
		if on_change.is_valid():
			on_change.call(v))
	return c


func _toggle(section: String, key: String, on_change: Callable = Callable()) -> UiToggle:
	var cb := UiToggle.new("", "switch", bool(Settings.get_value(section, key)))
	cb.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	cb.custom_minimum_size = Vector2(150, 40)
	cb.toggled.connect(func(on: bool) -> void:
		Settings.set_value(section, key, on)
		if on_change.is_valid():
			on_change.call(on))
	return cb


func _slider(section: String, key: String, lo: float, hi: float, step: float, fmt: Callable,
		on_change: Callable = Callable()) -> HBoxContainer:
	var h := UiKit.hbox(14)
	var s := HSlider.new()
	s.min_value = lo
	s.max_value = hi
	s.step = step
	s.value = clampf(float(Settings.get_value(section, key)), lo, hi)
	s.focus_mode = Control.FOCUS_ALL
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	s.custom_minimum_size = Vector2(260, 28)
	UiKit.hover_focus(s)
	var val := UiKit.label(String(fmt.call(s.value)), &"Stat")
	val.custom_minimum_size = Vector2(96, 0)
	val.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	s.value_changed.connect(func(v: float) -> void:
		val.text = String(fmt.call(v))
		Settings.set_value(section, key, v, false)
		_dirty = true
		if on_change.is_valid():
			on_change.call(v))
	s.drag_ended.connect(func(_changed: bool) -> void: Settings.save_settings())
	s.focus_exited.connect(func() -> void:
		if _dirty:
			_dirty = false
			Settings.save_settings())
	h.add_child(s)
	h.add_child(val)
	return h


static func _pct(v: float) -> String:
	return "%d%%" % int(round(v * 100.0))


func _reset_button(section: String, label_text: String) -> void:
	_content.add_child(UiKit.gap(8))
	var b := UiKit.button(label_text, &"GhostButton", func() -> void: _confirm_reset(section))
	b.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_content.add_child(b)


func _confirm_reset(section: String) -> void:
	_modal_open = true
	var m := UiModal.open(self, "Restore defaults?", "All %s settings return to their default values." % TAB_TITLES[_tab_index].to_lower(),
		[["reset", "Restore", &"PrimaryButton"], ["cancel", "Cancel", &""]])
	var id: String = await m.chosen
	_modal_open = false
	if id != "reset":
		return
	if section == "controls":
		Settings.reset_section("controls")
		Settings.reset_bindings()
	else:
		Settings.reset_section(section)
	UiToasts.notify(self, "%s settings restored." % TAB_TITLES[_tab_index], "ok")
	_show_tab(_tab_index)


# ------------------------------------------------------------------------------------------
# Display
# ------------------------------------------------------------------------------------------
func _build_display() -> void:
	_section("Window")
	var wm: String = String(Settings.get_value("display", "window_mode"))
	var modes: Array = [["windowed", "Windowed"], ["fullscreen", "Fullscreen (borderless)"], ["exclusive", "Exclusive fullscreen"]]
	var wmc: UiCycler = _cycler("display", "window_mode", modes, func(_v: Variant) -> void: _update_res_row())
	if wm == "borderless":
		wmc.select_value("fullscreen")
	_row("Window mode", wmc)
	var res_opts: Array = []
	var screen: Vector2i = DisplayServer.screen_get_size() if DisplayServer.get_name() != "headless" else Vector2i(3840, 2160)
	var cur: Vector2i = Settings.get_value("display", "resolution")
	var found: bool = false
	for r in RESOLUTIONS:
		if r.x <= screen.x and r.y <= screen.y:
			res_opts.append([r, "%d × %d" % [r.x, r.y]])
			found = found or r == cur
	if not found:
		res_opts.append([cur, "%d × %d" % [cur.x, cur.y]])
	var rc: UiCycler = _cycler("display", "resolution", res_opts)
	var rbox := UiKit.hbox(12)
	rbox.add_child(rc)
	_res_note = UiKit.label("Fullscreen uses the display's native resolution.", &"Dim")
	rbox.add_child(_res_note)
	_res_row_value = rc
	_row("Resolution", rbox, "Window size when windowed.")
	_update_res_row()
	_row("VSync", _toggle("display", "vsync"), "Synchronise frames with the display to avoid tearing.")
	_row("Frame rate cap", _cycler("display", "frame_cap", [[0, "Unlimited"], [30, "30 FPS"], [60, "60 FPS"], [90, "90 FPS"],
		[120, "120 FPS"], [144, "144 FPS"], [165, "165 FPS"], [240, "240 FPS"]]))
	_section("Rendering")
	_row("Quality preset", _cycler("display", "quality", [["low", "Low"], ["medium", "Medium"], ["high", "High"],
		["competitive", "Competitive (high frame rate)"]]), "Shadows and anti-aliasing. Competitive favours frame rate.")
	_row("Render scale", _slider("display", "render_scale", 0.5, 1.0, 0.05, _pct), "3D resolution; below 100% uses FSR upscaling.")
	_row("Brightness", _slider("display", "brightness", 0.5, 1.5, 0.05, _pct))
	_row("Field of view", _slider("display", "fov", 65.0, 90.0, 1.0, func(v: float) -> String: return "%d°" % int(v)),
		"Vertical field of view of the match camera.")
	_row("Interface scale", _slider("display", "ui_scale", 0.75, 1.25, 0.05, _pct), "Size of menus and text.")
	_reset_button("display", "Restore display defaults")


func _update_res_row() -> void:
	if _res_row_value == null:
		return
	var windowed: bool = String(Settings.get_value("display", "window_mode")) == "windowed"
	_res_row_value.visible = windowed
	_res_note.visible = not windowed


# ------------------------------------------------------------------------------------------
# Audio
# ------------------------------------------------------------------------------------------
func _build_audio() -> void:
	_section("Volume")
	var labels: Dictionary = {"Master": "Master", "Music": "Music", "SFX": "Effects", "UI": "Interface", "Ambience": "Ambience"}
	for bus in ["Master", "Music", "SFX", "UI", "Ambience"]:
		var b: String = bus
		_row(String(labels[b]), _slider("audio", b, 0.0, 1.0, 0.05, _pct, func(_v: float) -> void:
			if b == "UI" or b == "Master":
				UiKit.play("ui_hover")))
	_reset_button("audio", "Restore audio defaults")


# ------------------------------------------------------------------------------------------
# Controls
# ------------------------------------------------------------------------------------------
func _build_controls() -> void:
	_section("Aiming")
	_row("Mouse sensitivity", _slider("controls", "mouse_sensitivity", 0.05, 1.0, 0.01, func(v: float) -> String: return "%.2f" % v))
	_row("Controller sensitivity", _slider("controls", "pad_sensitivity", 0.5, 6.0, 0.1, func(v: float) -> String: return "%.1f" % v))
	_row("Invert vertical look", _toggle("controls", "invert_y"))
	_section("Controller deadzones")
	_row("Left stick inner", _slider("controls", "left_deadzone_inner", 0.0, 0.5, 0.01, _pct, func(_v: float) -> void: Settings._apply_deadzones()))
	_row("Left stick outer", _slider("controls", "left_deadzone_outer", 0.6, 1.0, 0.01, _pct))
	_row("Right stick inner", _slider("controls", "right_deadzone_inner", 0.0, 0.5, 0.01, _pct, func(_v: float) -> void: Settings._apply_deadzones()))
	_row("Right stick outer", _slider("controls", "right_deadzone_outer", 0.6, 1.0, 0.01, _pct))
	_section("Bindings")
	var hint := UiKit.label("Select a binding and press the new key, mouse button or controller input. Esc cancels.", &"Small", true)
	_content.add_child(hint)
	var head := UiKit.hbox(12)
	var h1 := UiKit.label("ACTION", &"Caption")
	h1.custom_minimum_size = Vector2(360, 0)
	head.add_child(h1)
	var h2 := UiKit.hbox(6)
	h2.add_child(UiKit.icon("keyboard", 16.0, UiKit.TEXT_DIM))
	h2.add_child(UiKit.label("KEYBOARD & MOUSE", &"Caption"))
	h2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(h2)
	var h3 := UiKit.hbox(6)
	h3.add_child(UiKit.icon("gamepad", 16.0, UiKit.TEXT_DIM))
	h3.add_child(UiKit.label("CONTROLLER", &"Caption"))
	h3.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(h3)
	_content.add_child(head)
	var rows: Array[Control] = []
	for action in Settings.GAMEPLAY_ACTIONS:
		var a: String = action
		var h := UiKit.hbox(12)
		var l := UiKit.label(String(Settings.ACTION_LABELS.get(a, a.capitalize())))
		l.custom_minimum_size = Vector2(360, 0)
		h.add_child(l)
		if a.begins_with("look_"):
			var ml := UiKit.label("Mouse movement", &"Dim")
			ml.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			h.add_child(ml)
		else:
			h.add_child(_bind_button(a, false))
		h.add_child(_bind_button(a, true))
		_content.add_child(h)
		rows.append(h)
	_refresh_bindings()
	_reset_button("controls", "Restore default controls")


func _bind_button(action: String, pad: bool) -> Button:
	var b := UiKit.button("", &"ValueButton", func() -> void: _start_capture(action, pad))
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.custom_minimum_size = Vector2(200, 38)
	b.clip_text = true
	_bind_buttons["%s|%s" % [action, "pad" if pad else "kbm"]] = b
	return b


func _refresh_bindings() -> void:
	for k in _bind_buttons.keys():
		var parts: PackedStringArray = String(k).split("|")
		var b: Button = _bind_buttons[k]
		if is_instance_valid(b):
			var lab: String = Settings.binding_label(parts[0], parts[1] == "pad")
			b.text = lab if lab != "—" else "Unbound"


func _start_capture(action: String, pad: bool) -> void:
	if _modal_open:
		return
	_modal_open = true
	var act_label: String = String(Settings.ACTION_LABELS.get(action, action))
	var msg: String = ("Press a controller button, trigger or stick direction for “%s”. Esc cancels." % act_label) if pad \
		else ("Press a key or mouse button for “%s”. Esc cancels." % act_label)
	var m := UiModal.open(self, "Rebind %s" % act_label, msg, [], "cancel")
	var cap := BindCapture.new(pad, CAPTURE_TIMEOUT_S)
	m.add_content(cap)
	_capture = cap
	var result: Array = []
	cap.captured.connect(func(ev: InputEvent) -> void:
		result.append(ev)
		m.close("captured"))
	cap.cancelled.connect(func() -> void: m.close("cancel"))
	var id: String = await m.chosen
	_capture = null
	_modal_open = false
	if id != "captured" or result.is_empty():
		return
	await _apply_binding(action, result[0] as InputEvent)


func _apply_binding(action: String, ev: InputEvent) -> void:
	var conflict: String = Settings.rebind(action, ev, false)
	if conflict == "":
		UiKit.play("ui_select")
		UiToasts.notify(self, "%s → %s" % [String(Settings.ACTION_LABELS.get(action, action)), Settings.event_label(ev)], "ok")
		return
	if conflict == "invalid":
		UiToasts.notify(self, "That input cannot be bound.", "error")
		return
	var pad: bool = Settings.is_pad_event(ev)
	var mine: String = Settings.binding_label(action, pad)
	var other_label: String = String(Settings.ACTION_LABELS.get(conflict, conflict))
	var swap_note: String = ("“%s” gets %s instead." % [other_label, mine]) if mine != "—" else ("“%s” will be left unbound." % other_label)
	_modal_open = true
	var m := UiModal.open(self, "Input already in use",
		"%s is bound to “%s”. Swap the bindings? %s" % [Settings.event_label(ev), other_label, swap_note],
		[["swap", "Swap", &"PrimaryButton"], ["cancel", "Cancel", &""]])
	var id: String = await m.chosen
	_modal_open = false
	if id == "swap":
		Settings.rebind(action, ev, true)
		UiToasts.notify(self, "Swapped with %s." % other_label, "ok")


# ------------------------------------------------------------------------------------------
# Accessibility
# ------------------------------------------------------------------------------------------
func _build_access() -> void:
	_section("Colour")
	_row("Colour-vision mode", _cycler("access", "color_mode", [["standard", "Standard"], ["deuteranopia", "Deuteranopia (red–green)"],
		["protanopia", "Protanopia (red–green)"], ["tritanopia", "Tritanopia (blue–yellow)"]]),
		"Team, territory and marker colours. Shapes and labels always accompany colour.")
	var sw := SwatchPreview.new()
	var sw_row := UiKit.hbox(0)
	sw_row.add_child(UiKit.gap(378))
	sw_row.add_child(sw)
	_content.add_child(sw_row)
	_section("Effects & camera")
	_row("Reduced effects", _toggle("access", "reduced_effects"), "Fewer particles and flashes.")
	_row("Camera shake", _slider("access", "camera_shake", 0.0, 1.0, 0.05, func(v: float) -> String: return "Off" if v <= 0.001 else _pct(v)),
		"Off by default.")
	_section("HUD")
	_row("HUD scale", _slider("access", "hud_scale", 0.75, 1.5, 0.05, _pct))
	_row("Damage numbers", _toggle("access", "damage_numbers"), "Show the damage of your hits as numbers.")
	_reset_button("access", "Restore accessibility defaults")


# ------------------------------------------------------------------------------------------
# Gameplay & Online
# ------------------------------------------------------------------------------------------
func _build_online() -> void:
	_section("Player")
	var name_box := UiKit.vbox(4)
	var name_edit := UiKit.line_edit("Your name", 20)
	name_edit.text = String(Settings.get_value("player", "name"))
	name_box.add_child(name_edit)
	_name_error = UiKit.label("", &"ErrorLabel")
	_name_error.visible = false
	name_box.add_child(_name_error)
	name_edit.text_submitted.connect(func(t: String) -> void: _apply_name(t))
	name_edit.focus_exited.connect(func() -> void: _apply_name(name_edit.text))
	_row("Player name", name_box, "Shown in offline matches and direct-connect lobbies (3–20 characters).")
	_section("Online service")
	var url_box := UiKit.vbox(6)
	var url_edit := UiKit.line_edit("https://play.example.org", 200)
	url_edit.text = String(Settings.get_value("online", "service_url"))
	url_box.add_child(url_edit)
	var st := UiKit.hbox(8)
	_url_icon = UiKit.icon("info", 18.0, UiKit.TEXT_DIM)
	st.add_child(_url_icon)
	_url_status = UiKit.label("", &"Small", true)
	_url_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	st.add_child(_url_status)
	url_box.add_child(st)
	url_edit.text_changed.connect(func(t: String) -> void: _show_url_status(t))
	url_edit.text_submitted.connect(func(t: String) -> void: _apply_url(t))
	url_edit.focus_exited.connect(func() -> void: _apply_url(url_edit.text))
	_show_url_status(url_edit.text)
	_row("Service URL", url_box, "Address of the WILDRUSH control service. Leave empty to play offline only.")
	var reg_box := UiKit.vbox(4)
	var reg_edit := UiKit.line_edit("local", 20)
	reg_edit.text = String(Settings.get_value("online", "region"))
	reg_box.add_child(reg_edit)
	_region_error = UiKit.label("", &"ErrorLabel")
	_region_error.visible = false
	reg_box.add_child(_region_error)
	reg_edit.text_submitted.connect(func(t: String) -> void: _apply_region(t))
	reg_edit.focus_exited.connect(func() -> void: _apply_region(reg_edit.text))
	_row("Region", reg_box, "Matchmaking region code configured by your service (e.g. eu-west).")
	var test := UiKit.button("Test connection", &"", func() -> void: _test_connection(url_edit.text))
	test.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_row("", test)


func _apply_name(t: String) -> void:
	var n: String = t.strip_edges()
	var ok: bool = n.length() >= 3 and n.length() <= 20
	_name_error.visible = not ok
	_name_error.text = "" if ok else "Names need 3 to 20 characters."
	if not ok or n == String(Settings.get_value("player", "name")):
		return
	Settings.set_value("player", "name", n)
	Profile.data["display_name"] = n
	Profile.save_profile()
	Profile.profile_changed.emit()


func _show_url_status(t: String) -> void:
	var chk: Dictionary = Online.check_url(t)
	if t.strip_edges() == "":
		_url_icon.kind = "wifi_off"
		_url_icon.color = UiKit.TEXT_DIM
		_url_status.text = "Not configured — online features are hidden; offline play works as usual."
		_url_status.add_theme_color_override("font_color", UiKit.TEXT_DIM)
	elif bool(chk["ok"]):
		var secure: bool = bool(chk["secure"])
		_url_icon.kind = "lock" if secure else "info"
		_url_icon.color = UiKit.OK if secure else UiKit.WARN
		_url_status.text = "Secure HTTPS connection." if secure else "Local development service on this computer (plain HTTP is allowed only for loopback)."
		_url_status.add_theme_color_override("font_color", UiKit.OK if secure else UiKit.WARN)
	else:
		_url_icon.kind = "error"
		_url_icon.color = UiKit.ERR
		_url_status.text = String(chk["message"])
		_url_status.add_theme_color_override("font_color", UiKit.ERR)


func _apply_url(t: String) -> void:
	var u: String = t.strip_edges()
	var chk: Dictionary = Online.check_url(u)
	if u != "" and not bool(chk["ok"]):
		return   # keep the previous valid value; the status line explains why
	var norm: String = String(chk["base"]) if u != "" else ""
	if norm != String(Settings.get_value("online", "service_url")):
		Settings.set_value("online", "service_url", norm)


func _apply_region(t: String) -> void:
	var r: String = t.strip_edges().to_lower()
	var ok: bool = Online.valid_region(r)
	_region_error.visible = not ok
	_region_error.text = "" if ok else "Use 2–20 lowercase letters, digits or dashes."
	if ok and r != String(Settings.get_value("online", "region")):
		Settings.set_value("online", "region", r)


func _test_connection(url_text: String) -> void:
	_apply_url(url_text)
	if not Online.is_configured():
		UiToasts.notify(self, String(Online.url_status()["message"]), "error")
		return
	var r: Dictionary = await Online.version()
	if not is_inside_tree():
		return
	if bool(r["ok"]) and r["data"] is Dictionary:
		var d: Dictionary = r["data"]
		var proto: int = int(d.get("protocol", -1))
		var compat: String = "compatible" if proto == WR.PROTOCOL_VERSION else "protocol %d — this game uses %d" % [proto, WR.PROTOCOL_VERSION]
		UiToasts.notify(self, "Connected: service %s (%s)." % [String(d.get("service_build", "?")), compat], "ok" if proto == WR.PROTOCOL_VERSION else "warn")
	else:
		UiToasts.notify(self, String(r["error"].get("message", "Connection failed.")), "error")
