class_name MainMenu
extends Control
## Main menu hub (res://scenes/main_menu.tscn, docs/UI_CONTRACT.md "Main menu sub-screens").
## Sub-screens are switched in place; `Game.goto_menu({"screen": "history"})` opens one
## directly. Esc / B goes back; on Home it asks to quit.

const SETTINGS_SCENE: String = "res://scenes/ui/settings_panel.tscn"
const SCREEN_IDS: Array[String] = ["home", "offline", "training", "online", "collection", "history", "credits"]

var current: MenuScreen = null
var settings_panel: SettingsPanel = null
var _screens: Dictionary = {}
var _stack: Array[String] = []
var _host: Control
var _top: HBoxContainer
var _title: Label
var _subtitle: Label
var _back: Button
var _profile_chip: HBoxContainer
var _online_chip: HBoxContainer
var _hints: UiHintBar
var _build_label: Label
var _modal_open: bool = false
var _fade: Tween = null


func _ready() -> void:
	_build()
	UiKit.music("music_menu")
	Profile.profile_changed.connect(_refresh_status)
	Online.auth_changed.connect(func(_on: bool, _r: String) -> void: _refresh_status())
	Online.account_changed.connect(func(_a: Dictionary) -> void: _refresh_status())
	Settings.changed.connect(func(s: String) -> void:
		if s == "online" or s == "player":
			_refresh_status())
	var params: Dictionary = Game.pending.duplicate()
	Game.pending = {}
	open_screen("home", {}, false)
	var start: String = String(params.get("screen", "home"))
	if start == "settings":
		open_settings(String(params.get("tab", "")))
	elif start != "home" and SCREEN_IDS.has(start):
		open_screen(start, params)
	_refresh_status()


func _build() -> void:
	add_child(MenuBackground.new())
	var outer := UiKit.margin(52, 34, 52, 24)
	outer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	outer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(outer)
	var mw := MaxWidthContainer.new()
	mw.max_width = 1840.0
	mw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	outer.add_child(mw)
	var v := UiKit.vbox(14)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	mw.add_child(v)
	_top = UiKit.hbox(16)
	_top.custom_minimum_size = Vector2(0, 58)
	v.add_child(_top)
	_back = UiKit.button("", &"GhostButton", go_back)
	_back.custom_minimum_size = Vector2(48, 48)
	_back.tooltip_text = "Back"
	var bi := UiKit.icon("chevron_left", 26.0, UiKit.TEXT)
	bi.follow_parent_font_color = true
	bi.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bi.offset_left = 11
	bi.offset_right = -11
	bi.offset_top = 11
	bi.offset_bottom = -11
	_back.add_child(bi)
	_top.add_child(_back)
	var tv := UiKit.vbox(-6)
	_title = UiKit.label("", &"Title")
	tv.add_child(_title)
	_subtitle = UiKit.label("", &"Dim")
	tv.add_child(_subtitle)
	_top.add_child(tv)
	_top.add_child(UiKit.spacer())
	_online_chip = UiKit.hbox(8)
	_top.add_child(_online_chip)
	_profile_chip = UiKit.hbox(8)
	_top.add_child(_profile_chip)
	_host = Control.new()
	_host.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_host.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(_host)
	var bottom := UiKit.hbox(12)
	v.add_child(bottom)
	_build_label = UiKit.label("%s  ·  Godot %s" % [WR.BUILD_ID, String(Engine.get_version_info()["string"])], &"Small")
	_build_label.add_theme_color_override("font_color", UiKit.TEXT_FAINT)
	bottom.add_child(_build_label)
	bottom.add_child(UiKit.spacer())
	_hints = UiHintBar.new()
	bottom.add_child(_hints)


# ------------------------------------------------------------------------------------------
# navigation
# ------------------------------------------------------------------------------------------
func _make_screen(id: String) -> MenuScreen:
	var s: MenuScreen = null
	match id:
		"home": s = HomeScreen.new()
		"offline": s = OfflineSetupScreen.new()
		"training": s = TrainingSetupScreen.new()
		"online": s = OnlineScreen.new()
		"collection": s = CollectionScreen.new()
		"history": s = HistoryScreen.new()
		"credits": s = CreditsScreen.new()
	if s == null:
		return null
	s.name = id.capitalize().replace(" ", "") + "Screen"
	s.menu = self
	s.screen_id = id
	s.visible = false
	_host.add_child(s)
	s.build()
	s.built = true
	return s


func screen(id: String) -> MenuScreen:
	if not _screens.has(id):
		var s: MenuScreen = _make_screen(id)
		if s == null:
			return null
		_screens[id] = s
	return _screens[id]


func open_screen(id: String, params: Dictionary = {}, push: bool = true) -> MenuScreen:
	var s: MenuScreen = screen(id)
	if s == null:
		return null
	if current != null and current != s:
		current.exit()
		current.visible = false
		if push:
			_stack.append(current.screen_id)
	current = s
	s.visible = true
	s.enter(params)
	_update_chrome()
	if _fade != null and _fade.is_valid():
		_fade.kill()
	s.modulate.a = 0.0
	_fade = create_tween()
	_fade.tween_property(s, "modulate:a", 1.0, 0.16)
	_focus_current.call_deferred()
	return s


func _focus_current() -> void:
	if current == null or _modal_open or (settings_panel != null and settings_panel.visible):
		return
	var f: Control = current.default_focus()
	if f != null:
		UiKit.focus(f)


func go_back() -> void:
	if _modal_open:
		return
	if settings_panel != null and settings_panel.visible:
		settings_panel.close()
		return
	if current != null and current.handle_back():
		return
	if _stack.is_empty():
		if current != null and current.screen_id == "home":
			confirm_quit()
		else:
			open_screen("home", {}, false)
		return
	UiKit.play("ui_back")
	var prev: String = _stack.pop_back()
	open_screen(prev, {"back": true}, false)


func go_home() -> void:
	_stack.clear()
	open_screen("home", {}, false)


func _update_chrome() -> void:
	var home: bool = current != null and current.screen_id == "home"
	_back.visible = not home
	_title.visible = not home
	_subtitle.visible = not home
	if current != null:
		_title.text = current.title.to_upper()
		_subtitle.text = current.subtitle
		_subtitle.visible = not home and current.subtitle != ""
		refresh_hints()


func refresh_hints() -> void:
	if current != null:
		_hints.set_hints(current.hints())


func set_subtitle(text: String) -> void:
	if current != null:
		current.subtitle = text
	_subtitle.text = text
	_subtitle.visible = text != "" and current != null and current.screen_id != "home"


func _refresh_status() -> void:
	if _profile_chip == null:
		return
	UiKit.clear_children(_profile_chip)
	var badge: String = String(Profile.data.get("selected_badge", ""))
	if badge != "":
		_profile_chip.add_child(UiKit.icon(UiKit.badge_icon_kind(badge), 18.0, UiKit.GOLD))
	else:
		_profile_chip.add_child(UiKit.icon("user", 18.0, UiKit.TEXT_DIM))
	var pv := UiKit.vbox(-4)
	pv.add_child(UiKit.label(String(Profile.data.get("display_name", "Player")), &"Subheading"))
	var sub := UiKit.label(UiKit.badge_display(badge) if badge != "" else "Offline profile", &"Small")
	pv.add_child(sub)
	_profile_chip.add_child(pv)
	UiKit.clear_children(_online_chip)
	var col: Color = UiKit.TEXT_FAINT
	var txt: String = "Online: not configured"
	var ic: String = "wifi_off"
	if Online.is_logged_in():
		col = UiKit.OK
		txt = "Online: %s" % Online.display_name() if Online.display_name() != "" else "Online: signed in"
		ic = "wifi"
	elif Online.is_configured():
		col = UiKit.TEXT_DIM
		txt = "Online: signed out"
		ic = "wifi"
	_online_chip.add_child(UiKit.chip(txt.to_upper(), col, ic))
	_online_chip.add_child(UiKit.gap(10))


# ------------------------------------------------------------------------------------------
# overlays
# ------------------------------------------------------------------------------------------
func open_settings(tab: String = "") -> void:
	if settings_panel == null:
		settings_panel = (load(SETTINGS_SCENE) as PackedScene).instantiate() as SettingsPanel
		settings_panel.closed.connect(_on_settings_closed)
		add_child(settings_panel)
	settings_panel.visible = true
	if tab != "":
		settings_panel.open_tab(tab)
	else:
		settings_panel.open_tab("display")
	_hints.visible = false


func _on_settings_closed() -> void:
	_hints.visible = true
	if settings_panel != null:
		settings_panel.queue_free()
		settings_panel = null
	if current != null:
		current.enter({"back": true})
	_focus_current.call_deferred()


func confirm_quit() -> void:
	if _modal_open:
		return
	_modal_open = true
	var m := UiModal.open(self, "Quit WILDRUSH?", "Your settings and offline progress are saved.",
		[["quit", "Quit game", &"DangerButton"], ["cancel", "Cancel", &""]], "cancel", "cancel")
	var id: String = await m.chosen
	_modal_open = false
	if id == "quit":
		Game.quit_game()


func modal(title: String, message: String, buttons: Array, cancel_id: String = "cancel", default_id: String = "") -> String:
	## Convenience for screens: awaitable dialog on top of the menu.
	_modal_open = true
	var m := UiModal.open(self, title, message, buttons, cancel_id, default_id)
	var id: String = await m.chosen
	_modal_open = false
	return id


func is_modal_open() -> bool:
	return _modal_open or (settings_panel != null and settings_panel.visible)


# ------------------------------------------------------------------------------------------
# input
# ------------------------------------------------------------------------------------------
func _input(event: InputEvent) -> void:
	UiHintBar.note_input(event)
	if is_modal_open() or current == null:
		return
	# shoulder buttons switch tabs even while a slider/cycler holds focus
	if event is InputEventJoypadButton and current.screen_input(event):
		get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	if is_modal_open() or current == null:
		return
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		go_back()
		return
	if current.screen_input(event):
		get_viewport().set_input_as_handled()
		return
	# nothing focused (e.g. after a mouse click on empty space): any navigation key refocuses
	if get_viewport().gui_get_focus_owner() == null and (event.is_action_pressed("ui_down") or event.is_action_pressed("ui_up") \
			or event.is_action_pressed("ui_left") or event.is_action_pressed("ui_right") or event.is_action_pressed("ui_accept")):
		get_viewport().set_input_as_handled()
		_focus_current()
