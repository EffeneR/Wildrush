extends Node
## Autoload "Settings": persisted user settings (user://settings.cfg), input bindings with
## remapping + conflict detection, and application of display/audio options (spec §11).

signal changed(section: String)
signal bindings_changed

const PATH: String = "user://settings.cfg"
const GAMEPLAY_ACTIONS: Array[String] = [
	"move_forward", "move_back", "move_left", "move_right", "attack_light", "attack_heavy", "jump",
	"dodge", "guard", "skill_q", "skill_e", "skill_r", "scoreboard", "ping", "chat", "menu",
	"look_left", "look_right", "look_up", "look_down", "quick_chat_1", "quick_chat_2",
]
const ACTION_LABELS: Dictionary = {
	"move_forward": "Move forward", "move_back": "Move back", "move_left": "Move left", "move_right": "Move right",
	"attack_light": "Light attack", "attack_heavy": "Heavy attack", "jump": "Jump", "dodge": "Dodge",
	"guard": "Guard (hold)", "skill_q": "Skill Q", "skill_e": "Skill E", "skill_r": "Skill R",
	"scoreboard": "Scoreboard (hold)", "ping": "Ping", "chat": "Text chat", "menu": "Menu",
	"look_left": "Look left (pad)", "look_right": "Look right (pad)", "look_up": "Look up (pad)", "look_down": "Look down (pad)",
	"quick_chat_1": "Quick chat: On my way", "quick_chat_2": "Quick chat: Need help",
}
const QUALITY_PRESETS: Array[String] = ["low", "medium", "high", "competitive"]
const COLOR_MODES: Array[String] = ["standard", "deuteranopia", "protanopia", "tritanopia"]

var values: Dictionary = {}
var _cfg := ConfigFile.new()


func _defaults() -> Dictionary:
	return {
		"display": {"window_mode": "windowed", "resolution": Vector2i(1600, 900), "vsync": true, "frame_cap": 0,
			"render_scale": 1.0, "quality": "high", "brightness": 1.0, "fov": 75.0, "ui_scale": 1.0},
		"controls": {"mouse_sensitivity": 0.25, "invert_y": false, "pad_sensitivity": 2.6,
			"left_deadzone_inner": 0.15, "left_deadzone_outer": 0.95, "right_deadzone_inner": 0.12, "right_deadzone_outer": 0.95},
		"audio": {"Master": 0.9, "Music": 0.55, "SFX": 0.85, "UI": 0.8, "Ambience": 0.6},
		"access": {"color_mode": "standard", "reduced_effects": false, "camera_shake": 0.0, "hud_scale": 1.0, "damage_numbers": false},
		"online": {"service_url": "", "last_username": "", "region": "local"},
		"player": {"name": "Player"},
	}


func _ready() -> void:
	values = _defaults()
	load_settings()
	register_default_bindings()
	load_bindings()
	if not Config.is_server:
		apply_all()


func get_value(section: String, key: String) -> Variant:
	return values.get(section, {}).get(key, _defaults().get(section, {}).get(key))


func set_value(section: String, key: String, v: Variant, save_now: bool = true) -> void:
	if not values.has(section):
		values[section] = {}
	values[section][key] = v
	if save_now:
		save_settings()
	apply_section(section)
	changed.emit(section)


func load_settings() -> void:
	var err: int = _cfg.load(PATH)
	if err != OK:
		if not Config.is_server and Config.autopilot == "" and not FileAccess.file_exists(PATH):
			save_settings.call_deferred()   # first launch: write defaults so the file exists
		return
	var d: Dictionary = _defaults()
	for section in d.keys():
		for key in (d[section] as Dictionary).keys():
			if _cfg.has_section_key(section, key):
				var v: Variant = _cfg.get_value(section, key)
				# robust restore: only accept values of the expected type
				if typeof(v) == typeof(d[section][key]) or (typeof(d[section][key]) == TYPE_FLOAT and typeof(v) == TYPE_INT):
					values[section][key] = v


func save_settings() -> void:
	for section in values.keys():
		for key in (values[section] as Dictionary).keys():
			_cfg.set_value(section, key, values[section][key])
	var err: int = _cfg.save(PATH)
	if err != OK:
		push_warning("Settings: could not save (%d)" % err)


func reset_section(section: String) -> void:
	values[section] = (_defaults()[section] as Dictionary).duplicate()
	save_settings()
	apply_section(section)
	changed.emit(section)


# ------------------------------------------------------------------------------------------
# apply
# ------------------------------------------------------------------------------------------
func apply_all() -> void:
	for s in ["display", "audio", "access"]:
		apply_section(s)


func apply_section(section: String) -> void:
	if Config.is_server:
		return
	match section:
		"display":
			_apply_display()
		"audio":
			for bus in (values["audio"] as Dictionary).keys():
				var idx: int = AudioServer.get_bus_index(String(bus))
				if idx >= 0:
					var lin: float = clampf(float(values["audio"][bus]), 0.0, 1.0)
					AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(lin, 0.0001)))
					AudioServer.set_bus_mute(idx, lin <= 0.001)
		"access":
			var root: Window = get_tree().root if get_tree() != null else null
			if root != null:
				root.content_scale_factor = clampf(float(get_value("display", "ui_scale")), 0.75, 1.5)


func _apply_display() -> void:
	if DisplayServer.get_name() == "headless":
		return
	var mode_s: String = String(get_value("display", "window_mode"))
	var mode: int = DisplayServer.WINDOW_MODE_WINDOWED
	match mode_s:
		"fullscreen": mode = DisplayServer.WINDOW_MODE_FULLSCREEN
		"exclusive": mode = DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN
		"borderless": mode = DisplayServer.WINDOW_MODE_FULLSCREEN
	if DisplayServer.window_get_mode() != mode:
		DisplayServer.window_set_mode(mode)
	if mode == DisplayServer.WINDOW_MODE_WINDOWED:
		var res: Vector2i = get_value("display", "resolution")
		if res.x >= 640 and res.y >= 360:
			DisplayServer.window_set_size(res)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if bool(get_value("display", "vsync")) else DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = int(get_value("display", "frame_cap"))
	var vp: Viewport = get_viewport()
	var rs: float = clampf(float(get_value("display", "render_scale")), 0.5, 1.0)
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR if rs < 0.99 else Viewport.SCALING_3D_MODE_BILINEAR
	vp.scaling_3d_scale = rs
	var q: String = String(get_value("display", "quality"))
	vp.msaa_3d = Viewport.MSAA_2X if q == "high" else Viewport.MSAA_DISABLED
	vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA if q != "low" else Viewport.SCREEN_SPACE_AA_DISABLED
	RenderingServer.directional_shadow_atlas_set_size({"low": 1024, "medium": 2048, "high": 4096, "competitive": 2048}.get(q, 2048), true)
	get_tree().root.content_scale_factor = clampf(float(get_value("display", "ui_scale")), 0.75, 1.5)


# ------------------------------------------------------------------------------------------
# bindings
# ------------------------------------------------------------------------------------------
func _key(code: int) -> InputEventKey:
	var e := InputEventKey.new()
	e.physical_keycode = code
	return e


func _mouse(btn: int) -> InputEventMouseButton:
	var e := InputEventMouseButton.new()
	e.button_index = btn
	return e


func _joy(btn: int) -> InputEventJoypadButton:
	var e := InputEventJoypadButton.new()
	e.button_index = btn
	return e


func _axis(axis: int, v: float) -> InputEventJoypadMotion:
	var e := InputEventJoypadMotion.new()
	e.axis = axis
	e.axis_value = v
	return e


func default_events() -> Dictionary:
	return {
		"move_forward": [_key(KEY_W), _axis(JOY_AXIS_LEFT_Y, -1.0)],
		"move_back": [_key(KEY_S), _axis(JOY_AXIS_LEFT_Y, 1.0)],
		"move_left": [_key(KEY_A), _axis(JOY_AXIS_LEFT_X, -1.0)],
		"move_right": [_key(KEY_D), _axis(JOY_AXIS_LEFT_X, 1.0)],
		"attack_light": [_mouse(MOUSE_BUTTON_LEFT), _joy(JOY_BUTTON_X)],
		"attack_heavy": [_mouse(MOUSE_BUTTON_RIGHT), _joy(JOY_BUTTON_Y)],
		"jump": [_key(KEY_SPACE), _joy(JOY_BUTTON_A)],
		"dodge": [_key(KEY_SHIFT), _joy(JOY_BUTTON_B)],
		"guard": [_key(KEY_F), _axis(JOY_AXIS_TRIGGER_LEFT, 1.0)],
		"skill_q": [_key(KEY_Q), _joy(JOY_BUTTON_LEFT_SHOULDER)],
		"skill_e": [_key(KEY_E), _joy(JOY_BUTTON_RIGHT_SHOULDER)],
		"skill_r": [_key(KEY_R), _axis(JOY_AXIS_TRIGGER_RIGHT, 1.0)],
		"scoreboard": [_key(KEY_TAB), _joy(JOY_BUTTON_BACK)],
		"ping": [_mouse(MOUSE_BUTTON_MIDDLE), _joy(JOY_BUTTON_DPAD_UP)],
		"chat": [_key(KEY_ENTER)],
		"menu": [_key(KEY_ESCAPE), _joy(JOY_BUTTON_START)],
		"look_left": [_axis(JOY_AXIS_RIGHT_X, -1.0)],
		"look_right": [_axis(JOY_AXIS_RIGHT_X, 1.0)],
		"look_up": [_axis(JOY_AXIS_RIGHT_Y, -1.0)],
		"look_down": [_axis(JOY_AXIS_RIGHT_Y, 1.0)],
		"quick_chat_1": [_joy(JOY_BUTTON_DPAD_LEFT)],
		"quick_chat_2": [_joy(JOY_BUTTON_DPAD_RIGHT)],
	}


func register_default_bindings() -> void:
	var defs: Dictionary = default_events()
	for action in GAMEPLAY_ACTIONS:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.2)
		InputMap.action_erase_events(action)
		for ev in defs.get(action, []):
			InputMap.action_add_event(action, ev)
	_apply_deadzones()


func _apply_deadzones() -> void:
	var inner_l: float = float(get_value("controls", "left_deadzone_inner"))
	var inner_r: float = float(get_value("controls", "right_deadzone_inner"))
	for a in ["move_forward", "move_back", "move_left", "move_right"]:
		InputMap.action_set_deadzone(a, clampf(inner_l, 0.0, 0.6))
	for a in ["look_left", "look_right", "look_up", "look_down"]:
		InputMap.action_set_deadzone(a, clampf(inner_r, 0.0, 0.6))


func apply_stick_deadzone(v: Vector2, stick: String) -> Vector2:
	## Radial inner/outer deadzone remap for controller sticks.
	var inner: float = float(get_value("controls", stick + "_deadzone_inner"))
	var outer: float = float(get_value("controls", stick + "_deadzone_outer"))
	var m: float = v.length()
	if m <= inner:
		return Vector2.ZERO
	var t: float = clampf((m - inner) / maxf(0.01, outer - inner), 0.0, 1.0)
	return v / m * t


static func event_to_dict(e: InputEvent) -> Dictionary:
	if e is InputEventKey:
		return {"t": "key", "c": (e as InputEventKey).physical_keycode}
	if e is InputEventMouseButton:
		return {"t": "mouse", "c": (e as InputEventMouseButton).button_index}
	if e is InputEventJoypadButton:
		return {"t": "joyb", "c": (e as InputEventJoypadButton).button_index}
	if e is InputEventJoypadMotion:
		return {"t": "joya", "c": (e as InputEventJoypadMotion).axis, "v": signf((e as InputEventJoypadMotion).axis_value)}
	return {}


func dict_to_event(d: Dictionary) -> InputEvent:
	match String(d.get("t", "")):
		"key": return _key(int(d["c"]))
		"mouse": return _mouse(int(d["c"]))
		"joyb": return _joy(int(d["c"]))
		"joya": return _axis(int(d["c"]), float(d.get("v", 1.0)))
	return null


static func events_equal(a: InputEvent, b: InputEvent) -> bool:
	return event_to_dict(a) == event_to_dict(b)


static func is_pad_event(e: InputEvent) -> bool:
	return e is InputEventJoypadButton or e is InputEventJoypadMotion


func find_conflict(event: InputEvent, except_action: String = "") -> String:
	for action in GAMEPLAY_ACTIONS:
		if action == except_action:
			continue
		for ev in InputMap.action_get_events(action):
			if events_equal(ev, event):
				return action
	return ""


func rebind(action: String, event: InputEvent, swap_on_conflict: bool = false) -> String:
	## Replaces the KB/M (or pad) binding of `action` with `event`. Returns "" on success or the
	## conflicting action name when not swapping. Escape / Enter for menu/chat stay protected.
	if not GAMEPLAY_ACTIONS.has(action) or event == null:
		return "invalid"
	var conflict: String = find_conflict(event, action)
	var pad: bool = is_pad_event(event)
	var old: InputEvent = null
	for ev in InputMap.action_get_events(action):
		if is_pad_event(ev) == pad:
			old = ev
			break
	if conflict != "":
		if not swap_on_conflict:
			return conflict
		for ev2 in InputMap.action_get_events(conflict):
			if events_equal(ev2, event):
				InputMap.action_erase_event(conflict, ev2)
		if old != null:
			InputMap.action_add_event(conflict, old)
	if old != null:
		InputMap.action_erase_event(action, old)
	InputMap.action_add_event(action, event)
	save_bindings()
	bindings_changed.emit()
	return ""


func reset_bindings() -> void:
	register_default_bindings()
	save_bindings()
	bindings_changed.emit()


func save_bindings() -> void:
	var out: Dictionary = {}
	for action in GAMEPLAY_ACTIONS:
		var arr: Array = []
		for ev in InputMap.action_get_events(action):
			arr.append(event_to_dict(ev))
		out[action] = arr
	_cfg.set_value("bindings", "map", JSON.stringify(out))
	save_settings()


func load_bindings() -> void:
	if not _cfg.has_section_key("bindings", "map"):
		return
	var parsed: Variant = JSON.parse_string(String(_cfg.get_value("bindings", "map")))
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	for action in GAMEPLAY_ACTIONS:
		if not (parsed as Dictionary).has(action):
			continue
		var evs: Array = []
		for d in parsed[action]:
			var e: InputEvent = dict_to_event(d)
			if e != null:
				evs.append(e)
		if evs.is_empty():
			continue
		InputMap.action_erase_events(action)
		for e2 in evs:
			InputMap.action_add_event(action, e2)
	_apply_deadzones()


func binding_label(action: String, pad: bool = false) -> String:
	for ev in InputMap.action_get_events(action):
		if is_pad_event(ev) != pad:
			continue
		return event_label(ev)
	return "—"


static func event_label(ev: InputEvent) -> String:
	if ev is InputEventKey:
		return OS.get_keycode_string((ev as InputEventKey).physical_keycode)
	if ev is InputEventMouseButton:
		return {MOUSE_BUTTON_LEFT: "LMB", MOUSE_BUTTON_RIGHT: "RMB", MOUSE_BUTTON_MIDDLE: "MMB",
			MOUSE_BUTTON_XBUTTON1: "Mouse 4", MOUSE_BUTTON_XBUTTON2: "Mouse 5"}.get((ev as InputEventMouseButton).button_index, "Mouse %d" % (ev as InputEventMouseButton).button_index)
	if ev is InputEventJoypadButton:
		return {JOY_BUTTON_A: "A / ✕", JOY_BUTTON_B: "B / ○", JOY_BUTTON_X: "X / □", JOY_BUTTON_Y: "Y / △",
			JOY_BUTTON_LEFT_SHOULDER: "LB / L1", JOY_BUTTON_RIGHT_SHOULDER: "RB / R1", JOY_BUTTON_BACK: "View",
			JOY_BUTTON_START: "Menu", JOY_BUTTON_DPAD_UP: "D-pad ↑", JOY_BUTTON_DPAD_DOWN: "D-pad ↓",
			JOY_BUTTON_DPAD_LEFT: "D-pad ←", JOY_BUTTON_DPAD_RIGHT: "D-pad →"}.get((ev as InputEventJoypadButton).button_index, "Pad %d" % (ev as InputEventJoypadButton).button_index)
	if ev is InputEventJoypadMotion:
		var m := ev as InputEventJoypadMotion
		match m.axis:
			JOY_AXIS_TRIGGER_LEFT: return "LT / L2"
			JOY_AXIS_TRIGGER_RIGHT: return "RT / R2"
			JOY_AXIS_LEFT_X, JOY_AXIS_LEFT_Y: return "Left stick"
			JOY_AXIS_RIGHT_X, JOY_AXIS_RIGHT_Y: return "Right stick"
	return "?"


# ------------------------------------------------------------------------------------------
# colour language (spec §11: colour paired with shapes/labels; colour-vision options)
# ------------------------------------------------------------------------------------------
func relation_color(relation: String) -> Color:
	## relation: ally | enemy | neutral | inactive | contested | self
	var mode: String = String(get_value("access", "color_mode"))
	var ally := Color(0.29, 0.62, 1.0)
	var enemy := Color(0.93, 0.27, 0.25)
	var neutral := Color(0.98, 0.76, 0.22)
	var contested := Color(0.66, 0.38, 0.95)
	match mode:
		"deuteranopia", "protanopia":
			ally = Color(0.26, 0.55, 1.0)
			enemy = Color(1.0, 0.55, 0.1)
			contested = Color(0.85, 0.85, 0.95)
		"tritanopia":
			ally = Color(0.2, 0.75, 0.85)
			enemy = Color(0.95, 0.25, 0.45)
			neutral = Color(0.95, 0.9, 0.55)
	match relation:
		"ally", "self": return ally
		"enemy": return enemy
		"neutral": return neutral
		"contested": return contested
		"inactive": return Color(0.55, 0.57, 0.6)
	return Color.WHITE
