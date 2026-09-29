class_name MatchHud
extends CanvasLayer
## Gameplay HUD (spec §11): score/clock/zone bar, vitals, abilities, minimap, kill feed,
## toasts, crosshair + hit markers, overhead plates, respawn/spectate overlay, scoreboard,
## chat and pings, countdown and end banners, training and replay panels. Reads only the
## MatchHost interface; all text comes from real match/tuning data.

signal chat_focus_changed(active: bool)
signal replay_command(cmd: String, value: float)
signal training_command(cmd: String)

var host: MatchHost = null
var layout: ArenaLayout = null
var views: Dictionary = {}
var camera_rig: CameraRig = null
var root: Control
var scorebar: HudScorebar
var minimap: HudMinimap
var overhead: HudOverhead
var hp_meter: HudMeter
var st_meter: HudMeter
var vitals_name: Label
var status_chips: HBoxContainer
var abilities: Dictionary = {}          # slot -> HudAbility
var passive_label: Label
var killfeed: VBoxContainer
var toasts: VBoxContainer
var center_big: Label
var center_sub: Label
var crosshair: Control
var respawn_panel: PanelContainer
var respawn_title: Label
var respawn_timer: Label
var respawn_hint: Label
var scoreboard: PanelContainer
var sb_grid: GridContainer
var chat_log: VBoxContainer
var chat_edit: LineEdit
var chat_team: bool = true
var chat_active: bool = false
var training_panel: PanelContainer
var training_info: Label
var replay_bar: PanelContainer
var replay_slider: HSlider
var replay_time: Label
var replay_speed: Label
var ping_wheel: Control
var vitals_box: Control
var ability_box: HBoxContainer

var _hit_marker: float = 0.0
var _hit_marker_heavy: bool = false
var _last_status: Dictionary = {}
var _center_timer: float = 0.0
var _banner_locked: bool = false
var _last_countdown: int = -1
var _killer_text: String = ""
var _last_training_hit: String = ""
var _combo: int = 0
var _combo_t: float = 0.0
var _replay_dragging: bool = false
var hud_scale: float = 1.0


func setup(p_host: MatchHost, p_layout: ArenaLayout, p_views: Dictionary, rig: CameraRig) -> void:
	host = p_host
	layout = p_layout
	views = p_views
	camera_rig = rig
	layer = 10
	root = Control.new()
	root.name = "HudRoot"
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	_build()
	_apply_scale()
	Settings.changed.connect(func(s: String) -> void:
		if s == "access":
			_apply_scale()
		if s == "controls":
			_refresh_key_labels())
	Settings.bindings_changed.connect(_refresh_key_labels)


func _apply_scale() -> void:
	hud_scale = clampf(float(Settings.get_value("access", "hud_scale")), 0.75, 1.5)
	for c in [scorebar, minimap, vitals_box, ability_box, killfeed, respawn_panel]:
		if c != null:
			(c as Control).scale = Vector2.ONE * hud_scale
	_relayout()


func _relayout() -> void:
	if root == null:
		return
	var vp: Vector2 = root.get_viewport_rect().size
	scorebar.position = Vector2((vp.x - scorebar.size.x * hud_scale) * 0.5, 10)
	minimap.position = Vector2(vp.x - minimap.size.x * hud_scale - 16, 16)
	vitals_box.position = Vector2((vp.x - vitals_box.size.x * hud_scale) * 0.5, vp.y - vitals_box.size.y * hud_scale - 22)
	ability_box.position = Vector2(vp.x - ability_box.size.x * hud_scale - 22, vp.y - ability_box.size.y * hud_scale - 18)
	killfeed.position = Vector2(16, 16)
	respawn_panel.position = Vector2((vp.x - respawn_panel.size.x * hud_scale) * 0.5, vp.y * 0.62)


# ------------------------------------------------------------------------------------------
# construction
# ------------------------------------------------------------------------------------------
func _build() -> void:
	overhead = HudOverhead.new()
	overhead.set_anchors_preset(Control.PRESET_FULL_RECT)
	overhead.host = host
	overhead.views = views
	root.add_child(overhead)

	scorebar = HudScorebar.new()
	scorebar.size = Vector2(620, 118)
	scorebar.left_team = host.local_team if not host.spectator else 0
	scorebar.target = int(Tuning.rules.get("score_target", 250))
	scorebar.regulation_s = host.regulation_s
	for z in layout.zones:
		scorebar.zone_names[String(z["id"])] = String(z.get("name", ""))
	root.add_child(scorebar)

	minimap = HudMinimap.new()
	minimap.size = Vector2(250, 234)
	minimap.setup(layout, host)
	root.add_child(minimap)

	# vitals
	vitals_box = VBoxContainer.new()
	vitals_box.size = Vector2(460, 84)
	vitals_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vitals_box.add_theme_constant_override("separation", 5)
	var top_row := HBoxContainer.new()
	top_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vitals_name = HudStyle.label("", 20, HudStyle.INK, HudStyle.head_font())
	top_row.add_child(vitals_name)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top_row.add_child(spacer)
	status_chips = HBoxContainer.new()
	status_chips.mouse_filter = Control.MOUSE_FILTER_IGNORE
	status_chips.add_theme_constant_override("separation", 6)
	top_row.add_child(status_chips)
	vitals_box.add_child(top_row)
	hp_meter = HudMeter.new()
	hp_meter.custom_minimum_size = Vector2(460, 24)
	vitals_box.add_child(hp_meter)
	st_meter = HudMeter.new()
	st_meter.custom_minimum_size = Vector2(460, 10)
	st_meter.color = HudStyle.STAMINA
	st_meter.segments = 4
	st_meter.ticks = [float(Tuning.shared.get("dodge", {}).get("stamina", 25)) / Tuning.stamina_max]
	vitals_box.add_child(st_meter)
	root.add_child(vitals_box)

	# abilities
	ability_box = HBoxContainer.new()
	ability_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ability_box.add_theme_constant_override("separation", 6)
	var pv := VBoxContainer.new()
	pv.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pv.alignment = BoxContainer.ALIGNMENT_END
	passive_label = HudStyle.label("", 13, HudStyle.INK_DIM)
	passive_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	passive_label.custom_minimum_size = Vector2(120, 0)
	passive_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	pv.add_child(passive_label)
	ability_box.add_child(pv)
	for slot in ["dodge", "q", "e", "r"]:
		var ab := HudAbility.new()
		ab.slot_label = slot
		ab.glyph = "⇄" if slot == "dodge" else slot.to_upper()
		ab.accent = Color(0.8, 0.85, 0.9) if slot == "dodge" else Color(0.98, 0.76, 0.3)
		ability_box.add_child(ab)
		abilities[slot] = ab
	ability_box.size = Vector2(130 + 4 * 82, 104)
	root.add_child(ability_box)

	killfeed = VBoxContainer.new()
	killfeed.mouse_filter = Control.MOUSE_FILTER_IGNORE
	killfeed.add_theme_constant_override("separation", 3)
	killfeed.size = Vector2(380, 160)
	root.add_child(killfeed)

	toasts = VBoxContainer.new()
	toasts.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toasts.set_anchors_preset(Control.PRESET_CENTER_TOP)
	toasts.position = Vector2(-260, 150)
	toasts.size = Vector2(520, 120)
	toasts.alignment = BoxContainer.ALIGNMENT_BEGIN
	root.add_child(toasts)

	center_big = HudStyle.label("", 72, HudStyle.INK, HudStyle.head_font(), 10)
	center_big.set_anchors_preset(Control.PRESET_CENTER)
	center_big.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	center_big.size = Vector2(900, 90)
	center_big.position = Vector2(-450, -170)
	root.add_child(center_big)
	center_sub = HudStyle.label("", 22, HudStyle.INK_DIM, HudStyle.body_font())
	center_sub.set_anchors_preset(Control.PRESET_CENTER)
	center_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	center_sub.size = Vector2(900, 30)
	center_sub.position = Vector2(-450, -84)
	root.add_child(center_sub)

	crosshair = Control.new()
	crosshair.set_anchors_preset(Control.PRESET_CENTER)
	crosshair.size = Vector2(40, 40)
	crosshair.position = Vector2(-20, -20)
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	crosshair.draw.connect(_draw_crosshair)
	root.add_child(crosshair)

	_build_respawn()
	_build_scoreboard()
	_build_chat()
	_build_ping_wheel()
	if host.mode == WR.MODE_TRAINING:
		_build_training()
	if host.mode == "replay":
		_build_replay_bar()
	if host.spectator:
		vitals_box.visible = false
		ability_box.visible = false
	else:
		_setup_local_fighter()
	root.resized.connect(_relayout)
	_relayout()


func _setup_local_fighter() -> void:
	var fid: String = String(host.fighter_info.get(host.local_entity, {}).get("fighter", ""))
	var def: FighterDef = Tuning.fighter(fid)
	if def == null:
		return
	vitals_name.text = "%s  ·  %s" % [def.display_name, def.title.to_upper()]
	passive_label.text = "PASSIVE\n%s" % def.passive_name.to_upper()
	for slot in ["q", "e", "r"]:
		var ad: ActionDef = def.skill(slot)
		if ad != null:
			(abilities[slot] as HudAbility).ability_name = ad.display_name
	(abilities["dodge"] as HudAbility).ability_name = "Dodge"
	_refresh_key_labels()


func _refresh_key_labels() -> void:
	var pad: bool = Input.get_connected_joypads().size() > 0
	var map: Dictionary = {"dodge": "dodge", "q": "skill_q", "e": "skill_e", "r": "skill_r"}
	for slot in map.keys():
		if abilities.has(slot):
			(abilities[slot] as HudAbility).key_text = Settings.binding_label(String(map[slot]), pad)
			(abilities[slot] as HudAbility).queue_redraw()


func _build_respawn() -> void:
	respawn_panel = PanelContainer.new()
	respawn_panel.add_theme_stylebox_override("panel", HudStyle.panel_box(8, 0.8))
	respawn_panel.size = Vector2(460, 120)
	respawn_panel.custom_minimum_size = Vector2(460, 120)
	respawn_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var v := VBoxContainer.new()
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	respawn_title = HudStyle.label("KNOCKED OUT", 28, Color(1.0, 0.55, 0.45), HudStyle.head_font())
	respawn_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	respawn_timer = HudStyle.label("", 22, HudStyle.INK, HudStyle.num_font())
	respawn_timer.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	respawn_hint = HudStyle.label("", 14, HudStyle.INK_DIM)
	respawn_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(respawn_title)
	v.add_child(respawn_timer)
	v.add_child(respawn_hint)
	respawn_panel.add_child(v)
	respawn_panel.visible = false
	root.add_child(respawn_panel)


func _build_scoreboard() -> void:
	scoreboard = PanelContainer.new()
	scoreboard.add_theme_stylebox_override("panel", HudStyle.panel_box(10, 0.88))
	scoreboard.set_anchors_preset(Control.PRESET_CENTER)
	scoreboard.custom_minimum_size = Vector2(880, 0)
	scoreboard.position = Vector2(-440, -220)
	scoreboard.mouse_filter = Control.MOUSE_FILTER_IGNORE
	sb_grid = GridContainer.new()
	sb_grid.columns = 8
	sb_grid.add_theme_constant_override("h_separation", 22)
	sb_grid.add_theme_constant_override("v_separation", 6)
	scoreboard.add_child(sb_grid)
	scoreboard.visible = false
	root.add_child(scoreboard)


func _build_chat() -> void:
	var box := VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	box.position = Vector2(16, -300)
	box.size = Vector2(440, 220)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	chat_log = VBoxContainer.new()
	chat_log.mouse_filter = Control.MOUSE_FILTER_IGNORE
	chat_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	chat_log.alignment = BoxContainer.ALIGNMENT_END
	box.add_child(chat_log)
	chat_edit = LineEdit.new()
	chat_edit.placeholder_text = "Team chat — Tab: switch to all · Enter: send · Esc: cancel"
	chat_edit.max_length = Protocol.MAX_CHAT_CHARS
	chat_edit.visible = false
	chat_edit.text_submitted.connect(_on_chat_submit)
	chat_edit.gui_input.connect(_on_chat_gui_input)
	box.add_child(chat_edit)
	root.add_child(box)


func _build_ping_wheel() -> void:
	ping_wheel = Control.new()
	ping_wheel.set_anchors_preset(Control.PRESET_CENTER)
	ping_wheel.size = Vector2(260, 260)
	ping_wheel.position = Vector2(-130, -130)
	ping_wheel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ping_wheel.visible = false
	ping_wheel.draw.connect(_draw_ping_wheel)
	root.add_child(ping_wheel)


func _build_training() -> void:
	training_panel = PanelContainer.new()
	training_panel.add_theme_stylebox_override("panel", HudStyle.panel_box(8, 0.8))
	training_panel.set_anchors_preset(Control.PRESET_CENTER_LEFT)
	training_panel.position = Vector2(16, -80)
	training_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var v := VBoxContainer.new()
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(HudStyle.label("TRAINING", 20, Color(0.98, 0.76, 0.3), HudStyle.head_font()))
	v.add_child(HudStyle.label("F1 Idle · F2 Guard · F3 Attack · F4 Dodge\nF5 Reset positions & health", 13, HudStyle.INK_DIM))
	training_info = HudStyle.label("Dummies: idle", 15, HudStyle.INK)
	v.add_child(training_info)
	training_panel.add_child(v)
	root.add_child(training_panel)


func _build_replay_bar() -> void:
	replay_bar = PanelContainer.new()
	replay_bar.add_theme_stylebox_override("panel", HudStyle.panel_box(8, 0.85))
	replay_bar.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	replay_bar.custom_minimum_size = Vector2(900, 64)
	replay_bar.position = Vector2(-450, -84)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 10)
	var play := Button.new()
	play.text = "Pause"
	play.custom_minimum_size = Vector2(80, 0)
	play.pressed.connect(func() -> void: replay_command.emit("toggle", 0.0))
	h.add_child(play)
	replay_time = HudStyle.label("0:00 / 0:00", 16, HudStyle.INK, HudStyle.num_font())
	replay_time.custom_minimum_size = Vector2(110, 0)
	h.add_child(replay_time)
	replay_slider = HSlider.new()
	replay_slider.min_value = 0.0
	replay_slider.max_value = 1.0
	replay_slider.step = 0.0005
	replay_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	replay_slider.drag_started.connect(func() -> void: _replay_dragging = true)
	replay_slider.drag_ended.connect(func(_c: bool) -> void:
		_replay_dragging = false
		replay_command.emit("seek", replay_slider.value))
	h.add_child(replay_slider)
	for sp in [0.25, 0.5, 1.0, 2.0, 4.0]:
		var b := Button.new()
		b.text = ("%sx" % str(sp)).replace(".0x", "x")
		b.pressed.connect(func() -> void: replay_command.emit("speed", sp))
		h.add_child(b)
	var cam := Button.new()
	cam.text = "Free camera"
	cam.pressed.connect(func() -> void: replay_command.emit("free_cam", 0.0))
	h.add_child(cam)
	var nxt := Button.new()
	nxt.text = "Follow next"
	nxt.pressed.connect(func() -> void: replay_command.emit("follow_next", 0.0))
	h.add_child(nxt)
	replay_speed = HudStyle.label("1x", 14, HudStyle.INK_DIM)
	h.add_child(replay_speed)
	replay_bar.add_child(h)
	root.add_child(replay_bar)
	play.set_meta("is_play", true)
	replay_bar.set_meta("play_btn", play)


# ------------------------------------------------------------------------------------------
# per-frame update (called by the match scene)
# ------------------------------------------------------------------------------------------
func update(dt: float, vstates: Dictionary, m: Dictionary, follow_entity: int) -> void:
	m["spectator"] = host.spectator
	scorebar.update_state(m, dt)
	# minimap dots: allies always; enemies only when their state is present (visible)
	var dots: Array = []
	for e in vstates.keys():
		var vs: Dictionary = vstates[e]
		if bool(vs.get("hidden", false)) or bool(vs.get("unseen", false)):
			continue
		var rel: String = host.relation_of(int(e))
		dots.append({"pos": vs["pos"], "rel": "ally" if rel == "self" else rel, "alive": (int(vs.get("flags", 0)) & Protocol.F_ALIVE) != 0,
			"self": int(e) == (host.local_entity if host.local_entity >= 0 else follow_entity), "yaw": float(vs["yaw"])})
	minimap.dots = dots
	minimap.mstate = m
	minimap.tick(dt)
	overhead.states = vstates
	overhead.camera = get_viewport().get_camera_3d()
	overhead.tick(dt)
	_update_local(dt, m)
	_update_center(dt, m)
	scoreboard.visible = Input.is_action_pressed("scoreboard") and not chat_active
	if scoreboard.visible:
		_fill_scoreboard()
	_hit_marker = maxf(0.0, _hit_marker - dt * 4.0)
	crosshair.queue_redraw()
	for t in toasts.get_children():
		var age: float = float(t.get_meta("age", 0.0)) + dt
		t.set_meta("age", age)
		(t as Control).modulate.a = clampf(3.5 - age, 0.0, 1.0)
		if age > 3.5:
			t.queue_free()
	for k in killfeed.get_children():
		var age2: float = float(k.get_meta("age", 0.0)) + dt
		k.set_meta("age", age2)
		(k as Control).modulate.a = clampf(8.0 - age2, 0.0, 1.0)
		if age2 > 8.0:
			k.queue_free()
	for c in chat_log.get_children():
		var age3: float = float(c.get_meta("age", 0.0)) + dt
		c.set_meta("age", age3)
		(c as Control).modulate.a = 1.0 if chat_active else clampf(10.0 - age3, 0.0, 1.0)
	if training_panel != null:
		_combo_t += dt
		if _combo_t > 1.2:
			_combo = 0
	if replay_bar != null and host is ReplayHost:
		var rh := host as ReplayHost
		if not _replay_dragging:
			replay_slider.set_value_no_signal(rh.progress())
		replay_time.text = "%s / %s" % [HudStyle.fmt_time((rh.t - rh.start_tick) / WR.TICK_RATE), HudStyle.fmt_time(rh.duration_ticks / float(WR.TICK_RATE))]
		replay_speed.text = "%sx%s" % [str(rh.speed), "  (paused)" if rh.paused else ""]
		var pb: Button = replay_bar.get_meta("play_btn")
		pb.text = "Play" if rh.paused else "Pause"


func _update_local(dt: float, _m: Dictionary) -> void:
	if host.spectator:
		respawn_panel.visible = false
		return
	var s: Dictionary = host.local_status()
	if s.is_empty():
		return
	hp_meter.set_value(float(s["hp"]) / maxf(1.0, float(s["hp_max"])))
	hp_meter.color = HudStyle.HP if float(s["hp"]) / maxf(1.0, float(s["hp_max"])) > 0.3 else HudStyle.HP_LOW
	hp_meter.show_text = "%d / %d" % [int(ceil(float(s["hp"]))), int(s["hp_max"])]
	st_meter.set_value(float(s["st"]) / maxf(1.0, float(s["st_max"])))
	var cd: Dictionary = s["cd"]
	var tot: Dictionary = s["cd_total"]
	for slot in abilities.keys():
		(abilities[slot] as HudAbility).set_cd(float(cd.get(slot, 0.0)), float(tot.get(slot, 1.0)), false)
	# status chips
	var chips: Array = []
	if bool(s.get("protected", false)):
		chips.append(["PROTECTED", Color(0.75, 0.9, 1.0)])
	if bool(s.get("cr", false)):
		chips.append(["RESIST", Color(0.8, 0.8, 0.85)])
	if bool(s.get("guarding", false)):
		chips.append(["GUARD", Color(0.6, 0.8, 1.0)])
	if int(s.get("ctrl", 0)) == WR.Ctrl.GUARD_BREAK:
		chips.append(["GUARD BROKEN", Color(1.0, 0.6, 0.3)])
	var sig: String = str(chips)
	if sig != str(_last_status.get("chips", "")):
		for c in status_chips.get_children():
			c.queue_free()
		for ch in chips:
			var l := HudStyle.label(String(ch[0]), 13, ch[1], HudStyle.body_font(), 4)
			status_chips.add_child(l)
		_last_status["chips"] = sig
	var alive: bool = bool(s.get("alive", true))
	respawn_panel.visible = not alive
	if not alive:
		respawn_timer.text = "Respawning in %d" % int(ceil(float(s.get("respawn_s", 0.0))))
		respawn_title.text = "KNOCKED OUT" + (("  —  by " + _killer_text) if _killer_text != "" else "")
		respawn_hint.text = "Spectating allies · %s / %s to switch" % [Settings.binding_label("attack_light"), Settings.binding_label("attack_heavy")]
	crosshair.visible = alive


func _update_center(dt: float, m: Dictionary) -> void:
	if bool(m.get("loading", false)):
		center_big.text = ""
		center_sub.text = "Preparing Briarport…"
		return
	var cd_s: float = float(m.get("countdown_s", 0.0))
	if int(m.get("phase", 0)) == WR.Phase.COUNTDOWN and cd_s > 0.0:
		var n: int = int(ceil(cd_s))
		center_big.text = str(n)
		center_sub.text = "Turf Shift · first to %d or most points in %d:00" % [scorebar.target, int(host.regulation_s / 60.0)]
		if n != _last_countdown:
			_last_countdown = n
			AudioDirector.ui("countdown_tick")
		_center_timer = 0.0
		return
	if _last_countdown > 0 and int(m.get("phase", 0)) == WR.Phase.LIVE:
		_last_countdown = 0
		show_center("FIGHT", "Take Zone %s" % String(m.get("zone", "B")), 1.2)
		AudioDirector.ui("countdown_go")
	if _center_timer > 0.0:
		_center_timer -= dt
		if _center_timer <= 0.0 and not _banner_locked:
			center_big.text = ""
			center_sub.text = ""
	elif not _banner_locked and center_sub.text == "Preparing Briarport…":
		center_sub.text = ""


func show_center(big: String, sub: String, secs: float, lock: bool = false) -> void:
	center_big.text = big
	center_sub.text = sub
	_center_timer = secs
	_banner_locked = lock


func toast(text: String, col: Color = HudStyle.INK) -> void:
	var l := HudStyle.label(text, 20, col, HudStyle.head_font(), 7)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.custom_minimum_size = Vector2(520, 0)
	l.set_meta("age", 0.0)
	toasts.add_child(l)
	while toasts.get_child_count() > 3:
		toasts.get_child(0).queue_free()
		toasts.remove_child(toasts.get_child(0))


func _name_of(e: int) -> String:
	return String(host.fighter_info.get(e, {}).get("name", "?"))


func _fighter_of(e: int) -> String:
	var d: FighterDef = Tuning.fighter(String(host.fighter_info.get(e, {}).get("fighter", "")))
	return d.display_name if d != null else ""


func _rel_color(e: int) -> Color:
	var r: String = host.relation_of(e)
	return Settings.relation_color("ally" if r == "self" else r)


# ------------------------------------------------------------------------------------------
# events
# ------------------------------------------------------------------------------------------
func handle(evs: Array) -> void:
	for e in evs:
		var t: String = String(e.get("type", ""))
		match t:
			"ko":
				_on_ko(e)
			"hit":
				if int(e.get("a", -1)) == host.local_entity and host.local_entity >= 0:
					_hit_marker = 1.0
					_hit_marker_heavy = bool(e.get("heavy", false))
					if training_panel != null:
						_combo += 1
						_combo_t = 0.0
						training_info.text = "Last hit: %d damage · combo %d" % [int(round(float(e.get("dmg", 0.0)))), _combo]
			"block":
				if int(e.get("a", -1)) == host.local_entity and training_panel != null:
					training_info.text = "Blocked (stamina cost %d)" % int(round(float(e.get("cost", 0.0))))
			"parry":
				if int(e.get("t", -1)) == host.local_entity:
					toast("PARRIED!", Color(1.0, 0.9, 0.5))
			"guard_break":
				if int(e.get("t", -1)) == host.local_entity:
					toast("GUARD BROKEN", Color(1.0, 0.6, 0.3))
				elif int(e.get("a", -1)) == host.local_entity:
					toast("Guard broken!", Color(1.0, 0.85, 0.5))
			"zone_activated":
				AudioDirector.ui("zone_activate")
				toast("Zone %s is active" % String(e.get("zone", "")), Settings.relation_color("neutral"))
			"zone_revealed":
				AudioDirector.ui("zone_reveal")
				toast("Next zone: %s in %d s" % [String(e.get("zone", "")), int(round(float(e.get("in_ticks", 900)) / WR.TICK_RATE))], Settings.relation_color("neutral"))
			"zone_rotated":
				AudioDirector.ui("zone_activate")
				toast("Zone shifted → %s" % String(e.get("zone", "")), Settings.relation_color("neutral"))
			"zone_state":
				var st: int = int(e.get("state", 0))
				if st == WR.ZoneState.CONTROLLED:
					var ally: bool = int(e.get("team", -1)) == host.local_team and not host.spectator
					AudioDirector.ui("zone_ally" if ally else "zone_enemy")
					toast(("Your team holds " if ally else "Enemy holds ") + String(e.get("zone", "")), Settings.relation_color("ally" if ally else "enemy"))
				elif st == WR.ZoneState.CONTESTED:
					AudioDirector.ui("zone_contested")
			"score_warning":
				var at: int = int(e.get("at", 200))
				var lvl: int = 1 if at < 230 else (2 if at < 245 else 3)
				AudioDirector.ui("score_warning_%d" % lvl)
				var mine: bool = int(e.get("team", -1)) == host.local_team and not host.spectator
				toast(("Your team" if mine else "Enemy team") + " at %d points" % at, Settings.relation_color("ally" if mine else "enemy"))
			"sudden_death":
				AudioDirector.ui("sudden_death")
				show_center("SUDDEN DEATH", "Hold the zone alone to win", 3.0)
			"match_end":
				var w: int = int(e.get("winner", -1))
				var won: bool = w == host.local_team
				if host.spectator:
					show_center("TEAM %s WINS" % ("A" if w == 0 else "B"), "%d – %d" % [int(e["score"][0]), int(e["score"][1])], 99.0, true)
				elif w < 0:
					show_center("DRAW", "", 99.0, true)
				else:
					show_center("VICTORY" if won else "DEFEAT", "%d – %d" % [int(e["score"][host.local_team]), int(e["score"][1 - host.local_team])], 99.0, true)
					AudioDirector.ui("victory" if won else "defeat")
			"respawn":
				if int(e.get("e", -1)) == host.local_entity:
					_killer_text = ""


func _on_ko(e: Dictionary) -> void:
	var victim: int = int(e.get("e", -1))
	var by: int = int(e.get("by", -1))
	var row := HBoxContainer.new()
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_theme_constant_override("separation", 8)
	var bg := PanelContainer.new()
	bg.add_theme_stylebox_override("panel", HudStyle.panel_box(4, 0.7))
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var inner := HBoxContainer.new()
	inner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	inner.add_theme_constant_override("separation", 8)
	if by >= 0:
		inner.add_child(HudStyle.label(_name_of(by), 15, _rel_color(by), HudStyle.body_font(), 3))
		inner.add_child(HudStyle.label("KO", 13, HudStyle.INK_DIM, HudStyle.head_font(), 3))
	inner.add_child(HudStyle.label(_name_of(victim), 15, _rel_color(victim), HudStyle.body_font(), 3))
	bg.add_child(inner)
	row.add_child(bg)
	row.set_meta("age", 0.0)
	killfeed.add_child(row)
	while killfeed.get_child_count() > 5:
		var old: Node = killfeed.get_child(0)
		killfeed.remove_child(old)
		old.queue_free()
	if victim == host.local_entity:
		_killer_text = ("%s (%s)" % [_name_of(by), _fighter_of(by)]) if by >= 0 else ""
	elif by == host.local_entity and host.local_entity >= 0:
		toast("Knocked out %s" % _name_of(victim), Color(1.0, 0.9, 0.6))


func show_damage(pos: Vector3, dmg: float, on_me: bool) -> void:
	if bool(Settings.get_value("access", "damage_numbers")):
		overhead.add_number(pos, dmg, on_me)


func on_ping(msg: Dictionary) -> void:
	var from: int = int(msg.get("from", -1))
	overhead.add_ping(msg["pos"], String(msg.get("kind", "attack")), _name_of(from))
	minimap.pings.append({"pos": msg["pos"], "kind": String(msg.get("kind", "attack")), "t": 0.0})
	AudioDirector.ui("ui_ping")


func on_chat(msg: Dictionary) -> void:
	var team_only: bool = bool(msg.get("team_only", false))
	var col: Color = Settings.relation_color("ally") if int(msg.get("team", -1)) == host.local_team else Settings.relation_color("enemy")
	var l := HudStyle.label("%s%s: %s" % ["[TEAM] " if team_only else "[ALL] ", String(msg.get("from", "")), String(msg.get("text", ""))], 15, HudStyle.INK, HudStyle.body_font(), 4)
	l.add_theme_color_override("font_color", col.lerp(Color.WHITE, 0.55))
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(440, 0)
	l.set_meta("age", 0.0)
	chat_log.add_child(l)
	while chat_log.get_child_count() > 7:
		var old: Node = chat_log.get_child(0)
		chat_log.remove_child(old)
		old.queue_free()
	AudioDirector.ui("ui_chat")


func notice(text: String) -> void:
	toast(text, Color(1.0, 0.85, 0.6))


# ------------------------------------------------------------------------------------------
# chat input
# ------------------------------------------------------------------------------------------
func open_chat() -> void:
	if host.mode not in ["online"]:
		return
	chat_active = true
	chat_edit.visible = true
	chat_edit.placeholder_text = ("Team chat" if chat_team else "All chat") + " — Tab: switch · Enter: send · Esc: cancel"
	chat_edit.grab_focus()
	chat_focus_changed.emit(true)


func close_chat() -> void:
	chat_active = false
	chat_edit.text = ""
	chat_edit.visible = false
	chat_edit.release_focus()
	chat_focus_changed.emit(false)


func _on_chat_submit(text: String) -> void:
	var t: String = Protocol.sanitize_chat(text)
	if t != "":
		host.send_chat(t, chat_team)
	close_chat()


func _on_chat_gui_input(ev: InputEvent) -> void:
	if ev is InputEventKey and (ev as InputEventKey).pressed:
		var k := ev as InputEventKey
		if k.keycode == KEY_ESCAPE:
			close_chat()
			chat_edit.accept_event()
		elif k.keycode == KEY_TAB:
			chat_team = not chat_team
			chat_edit.placeholder_text = ("Team chat" if chat_team else "All chat") + " — Tab: switch · Enter: send · Esc: cancel"
			chat_edit.accept_event()


# ------------------------------------------------------------------------------------------
# scoreboard
# ------------------------------------------------------------------------------------------
func _fill_scoreboard() -> void:
	for c in sb_grid.get_children():
		sb_grid.remove_child(c)
		c.queue_free()
	var heads: Array = ["", "PLAYER", "FIGHTER", "KO", "KO'D", "DMG", "ZONE s", "PING"]
	for h in heads:
		sb_grid.add_child(HudStyle.label(h, 13, HudStyle.INK_DIM, HudStyle.body_font(), 2))
	var rows: Array = host.roster()
	var order: Array = [host.local_team if not host.spectator else 0]
	order.append(1 - int(order[0]))
	for team in order:
		for r in rows:
			if int(r["team"]) != team:
				continue
			var e: int = int(r["e"])
			var col: Color = _rel_color(e)
			var mark := HudStyle.label("◆" if host.relation_of(e) == "enemy" else "●", 14, col, HudStyle.body_font(), 2)
			sb_grid.add_child(mark)
			var nm: String = String(r["name"]) + ("  (you)" if e == host.local_entity else "")
			if not bool(r.get("alive", true)):
				nm += "  · %ds" % int(ceil(float(r.get("respawn_s", 0.0))))
			sb_grid.add_child(HudStyle.label(nm, 16, HudStyle.INK if e != host.local_entity else Color(1.0, 0.9, 0.6), HudStyle.body_font(), 2))
			var d: FighterDef = Tuning.fighter(String(r["fighter"]))
			sb_grid.add_child(HudStyle.label(d.display_name if d != null else "", 15, HudStyle.INK_DIM, HudStyle.body_font(), 2))
			for k in ["kos", "kod", "dmg", "ctrl_s"]:
				var v: int = int(r.get(k, 0))
				sb_grid.add_child(HudStyle.label("—" if v < 0 else str(v), 16, HudStyle.INK, HudStyle.num_font(), 2))
			var pm: int = int(r.get("ping_ms", -1))
			sb_grid.add_child(HudStyle.label("BOT" if bool(r.get("bot", false)) else ("—" if pm < 0 else "%d ms" % pm), 14, HudStyle.INK_DIM, HudStyle.body_font(), 2))


# ------------------------------------------------------------------------------------------
# drawing helpers
# ------------------------------------------------------------------------------------------
func _draw_crosshair() -> void:
	var c: Vector2 = crosshair.size * 0.5
	var col := Color(1, 1, 1, 0.85)
	crosshair.draw_circle(c, 2.0, col)
	if _hit_marker > 0.0:
		var a: float = _hit_marker
		var r0: float = 7.0
		var r1: float = 14.0 if _hit_marker_heavy else 11.0
		var hc := Color(1.0, 0.95, 0.8, a)
		for d in [Vector2(1, 1), Vector2(-1, 1), Vector2(1, -1), Vector2(-1, -1)]:
			crosshair.draw_line(c + d.normalized() * r0, c + d.normalized() * r1, hc, 2.5)


var ping_select: String = ""


func _draw_ping_wheel() -> void:
	var c: Vector2 = ping_wheel.size * 0.5
	var kinds: Array = Protocol.PING_KINDS
	var labels: Dictionary = {"attack": "ATTACK", "defend": "DEFEND", "help": "HELP", "enemy": "ENEMY", "on_my_way": "ON MY WAY"}
	ping_wheel.draw_circle(c, 110.0, Color(0, 0, 0, 0.45))
	for i in range(kinds.size()):
		var a: float = -PI * 0.5 + TAU * i / kinds.size()
		var p: Vector2 = c + Vector2(cos(a), sin(a)) * 78.0
		var sel: bool = String(kinds[i]) == ping_select
		ping_wheel.draw_circle(p, 30.0, Color(0.98, 0.76, 0.3, 0.9) if sel else Color(0.1, 0.11, 0.12, 0.9))
		var f: Font = HudStyle.body_font()
		var txt: String = String(labels[kinds[i]])
		var tw: Vector2 = f.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		ping_wheel.draw_string(f, p + Vector2(-tw.x * 0.5, 4), txt, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0, 0, 0) if sel else HudStyle.INK)


func show_ping_wheel(on: bool, sel: String) -> void:
	ping_wheel.visible = on
	ping_select = sel
	ping_wheel.queue_redraw()
