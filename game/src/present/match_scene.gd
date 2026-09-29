extends Node3D
## scenes/match.tscn — one scene for offline, training, online and replay (params from
## Game.pending, docs/UI_CONTRACT.md). Wires a MatchHost to the visual world: arena view,
## fighter views, camera, local input, HUD, VFX and audio. Contains no game rules.
##
## Automation flags (tests, screenshots, soak, profiling):
##   -- --mode offline|training|replay --fighter nyx --difficulty hard --seed 7
##      --autopilot-self           (a bot drives the local fighter; used by soak/perf runs)
##      --capture-dir DIR --capture-at 8,20,45 [--capture-tag name]   (PNG screenshots)
##      --perf-log PATH            (frame-time samples as JSON lines)
##      --quit-after-s N
##      --result-json PATH         (write Game.last_result when the match ends, then quit)

var host: MatchHost = null
var layout: ArenaLayout
var arena: ArenaView
var rig: CameraRig
var player_input: PlayerInput
var hud: MatchHud
var vfx: VfxDirector
var pause_menu: PauseMenu
var views: Dictionary = {}              # e -> FighterView
var params: Dictionary = {}
var follow_entity: int = -1
var paused: bool = false
var finished: bool = false
var free_cam: bool = false
var _ping_down_ms: int = -1
var _ping_accum := Vector2.ZERO
var _t: float = 0.0
var _captures: Array = []
var _capture_dir: String = ""
var _perf: FileAccess = null
var _perf_acc: Array = []
var _replay_collision: Node3D = null
var _district: String = ""
var _ui_layer: CanvasLayer
var _error_label: Label


func _ready() -> void:
	params = Game.pending.duplicate()
	if params.is_empty():
		params = {"mode": Config.get_arg("mode", "offline"), "fighter": Config.get_arg("fighter", "nyx"),
			"difficulty": Config.get_arg("difficulty", "normal"), "seed": int(Config.get_arg("seed", "0"))}
		if params["mode"] == "replay":
			params["replay_path"] = Config.get_arg("replay", "")
	if int(params.get("seed", 0)) == 0:
		params.erase("seed")
	if Config.has("autopilot-self"):
		params["autopilot_self"] = true
	layout = ArenaLayout.load_file()
	_setup_capture()
	var mode: String = String(params.get("mode", "offline"))
	match mode:
		"online":
			if Game.session == null or Game.session.setup.is_empty():
				if Config.connect_to != "":
					_auto_connect()   # automation: direct connect + auto pick/lock
					return
				_fatal("No online match is in progress.")
				return
			var nh := NetMatchHost.new()
			nh.name = "Host"
			add_child(nh)
			player_input = PlayerInput.new()
			add_child(player_input)
			nh.setup_session(Game.session, player_input)
			host = nh
		"replay":
			var rh := ReplayHost.new()
			rh.name = "Host"
			add_child(rh)
			if not rh.load_replay(String(params.get("replay_path", ""))):
				_fatal(rh.load_error)
				return
			host = rh
			_replay_collision = Node3D.new()
			_replay_collision.name = "ReplayCollision"
			add_child(_replay_collision)
			ArenaBuilder.build_collision(_replay_collision, layout)
		_:
			var lh := LocalMatchHost.new()
			lh.name = "Host"
			add_child(lh)
			lh.setup(params)
			if bool(params.get("autopilot_self", false)):
				var b := BotAI.new()
				b.difficulty = String(params.get("difficulty", "normal"))
				lh.sim.bot_brains[lh.local_entity] = b
			host = lh
			player_input = PlayerInput.new()
			add_child(player_input)
	_build_world(mode)


func _build_world(mode: String) -> void:
	arena = ArenaView.new()
	arena.name = "Arena"
	add_child(arena)
	arena.build(layout)
	for e in host.fighter_info.keys():
		var fi: Dictionary = host.fighter_info[e]
		var v := FighterView.new()
		v.setup(Tuning.fighter(String(fi["fighter"])), String(fi.get("palette", "default")), host.relation_of(int(e)))
		v.entity = int(e)
		add_child(v)
		views[int(e)] = v
	rig = CameraRig.new()
	rig.name = "CameraRig"
	add_child(rig)
	if player_input != null:
		player_input.rig = rig
	follow_entity = host.local_entity if host.local_entity >= 0 else _first_entity()
	_attach_camera(follow_entity)
	rig.auto_yaw = bool(params.get("autopilot_self", false)) or host.spectator
	if host.local_entity >= 0:
		# start looking the way the fighter faces
		var vs0: Dictionary = host.views(0.0).get(host.local_entity, {})
		rig.yaw = float(vs0.get("yaw", 0.0))
	vfx = VfxDirector.new()
	vfx.name = "Vfx"
	add_child(vfx)
	vfx.views = views
	vfx.layout = layout
	vfx.local_entity = host.local_entity
	vfx.camera_rig = rig
	hud = MatchHud.new()
	hud.name = "Hud"
	add_child(hud)
	hud.setup(host, layout, views, rig)
	vfx.hud = hud
	_ui_layer = CanvasLayer.new()
	_ui_layer.layer = 20
	add_child(_ui_layer)
	pause_menu = PauseMenu.new()
	_ui_layer.add_child(pause_menu)
	pause_menu.build(mode == "online", "PAUSED" if mode in ["offline", "training"] else "MENU")
	pause_menu.resumed.connect(_on_resume)
	pause_menu.leave_requested.connect(_leave)
	host.events.connect(_on_events)
	host.finished.connect(_on_finished)
	host.chat.connect(func(m: Dictionary) -> void: hud.on_chat(m))
	host.ping.connect(func(m: Dictionary) -> void: hud.on_ping(m))
	host.notice.connect(func(t: String) -> void: hud.notice(t))
	hud.chat_focus_changed.connect(func(on: bool) -> void:
		if player_input != null:
			player_input.enabled = not on
		rig.capture_mouse(not on and not paused))
	hud.replay_command.connect(_on_replay_command)
	AudioDirector.music("music_match", 2.0)
	if mode == "replay":
		rig.capture_mouse(false)
	else:
		rig.capture_mouse(true)


func _fatal(msg: String) -> void:
	push_warning("match: " + msg)
	var layer := CanvasLayer.new()
	add_child(layer)
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", HudStyle.panel_box(10, 0.95))
	p.set_anchors_preset(Control.PRESET_CENTER)
	p.position = Vector2(-260, -80)
	p.custom_minimum_size = Vector2(520, 160)
	var v := VBoxContainer.new()
	v.add_child(HudStyle.label(msg, 18, HudStyle.INK, HudStyle.body_font(), 0))
	var b := Button.new()
	b.text = "Back to menu"
	b.pressed.connect(func() -> void: Game.goto_menu())
	v.add_child(b)
	p.add_child(v)
	layer.add_child(p)
	b.grab_focus()
	set_process(false)
	set_physics_process(false)


func _first_entity() -> int:
	var ks: Array = host.fighter_info.keys()
	ks.sort()
	return int(ks[0]) if not ks.is_empty() else -1


func _attach_camera(e: int) -> void:
	var v: FighterView = views.get(e)
	if v != null:
		rig.set_target(v, v.def.height)


# ------------------------------------------------------------------------------------------
# loop
# ------------------------------------------------------------------------------------------
func _physics_process(_dt: float) -> void:
	if host == null:
		return
	if host is LocalMatchHost:
		if paused and host.mode != "online":
			return
		var inp: InputFrame = player_input.sample() if player_input != null else InputFrame.new()
		host.physics_step(inp)


func _process(dt: float) -> void:
	if host == null:
		return
	_t += dt
	if host is ReplayHost:
		(host as ReplayHost).advance(dt)
	var vstates: Dictionary = host.views(dt)
	for e in vstates.keys():
		var v: FighterView = views.get(int(e))
		if v == null:
			continue
		var vs: Dictionary = vstates[e]
		if bool(vs.get("hidden", false)):
			v.visible = false
			continue
		v.apply_state(vs, dt)
	var m: Dictionary = host.match_state()
	arena.update_zones(m, host.local_team, host.spectator)
	_update_follow(vstates)
	hud.update(dt, vstates, m, follow_entity)
	vfx.footsteps(vstates)
	_update_ambience()
	_capture_tick()
	_perf_tick(dt)
	if Config.quit_after_s > 0.0 and _t > Config.quit_after_s:
		_quit_automation()


func _update_follow(vstates: Dictionary) -> void:
	if free_cam:
		return
	var want: int = follow_entity
	if host.local_entity >= 0:
		var me: Dictionary = vstates.get(host.local_entity, {})
		var alive: bool = (int(me.get("flags", Protocol.F_ALIVE)) & Protocol.F_ALIVE) != 0
		if alive:
			want = host.local_entity
		elif want == host.local_entity or not _is_alive(vstates, want):
			# knocked out: spectate an ally (team-visible information only)
			var ally: int = _next_ally(vstates, want, 1)
			if ally >= 0 and (int(me.get("flags", 0)) & Protocol.F_ALIVE) == 0 and _t > 0.0:
				want = ally if _ko_elapsed() > 1.4 else host.local_entity
	if want != follow_entity or rig.target == null:
		follow_entity = want
		_attach_camera(want)


var _ko_since: float = -1.0


func _ko_elapsed() -> float:
	var s: Dictionary = host.local_status()
	if s.is_empty() or bool(s.get("alive", true)):
		_ko_since = -1.0
		return 0.0
	if _ko_since < 0.0:
		_ko_since = _t
	return _t - _ko_since


func _is_alive(vstates: Dictionary, e: int) -> bool:
	var vs: Dictionary = vstates.get(e, {})
	return not vs.is_empty() and (int(vs.get("flags", 0)) & Protocol.F_ALIVE) != 0 and not bool(vs.get("hidden", false))


func _next_ally(vstates: Dictionary, from: int, dir: int) -> int:
	var allies: Array = []
	for e in host.fighter_info.keys():
		if int(host.fighter_info[e]["team"]) == host.local_team and int(e) != host.local_entity and _is_alive(vstates, int(e)):
			allies.append(int(e))
	if allies.is_empty():
		return -1
	allies.sort()
	var idx: int = allies.find(from)
	return int(allies[(idx + dir + allies.size()) % allies.size()]) if idx >= 0 else int(allies[0])


func _update_ambience() -> void:
	if rig == null or rig.camera == null:
		return
	var x: float = rig.global_position.x
	var d: String = "amb_harbor" if x < -21.0 else ("amb_yard" if x > 21.0 else "amb_market")
	if d != _district:
		_district = d
		AudioDirector.ambience(d, 2.5)


# ------------------------------------------------------------------------------------------
# input
# ------------------------------------------------------------------------------------------
func _unhandled_input(event: InputEvent) -> void:
	if host == null:
		return
	if pause_menu.visible:
		return
	if hud.chat_active:
		return
	if event.is_action_pressed("menu"):
		_open_pause()
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("chat") and host.mode == "online":
		hud.open_chat()
		get_viewport().set_input_as_handled()
		return
	if host is ReplayHost:
		_replay_input(event)
		return
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed and not rig.mouse_captured:
		rig.capture_mouse(true)
	# spectating allies while knocked out
	var st: Dictionary = host.local_status()
	if not st.is_empty() and not bool(st.get("alive", true)):
		if event.is_action_pressed("attack_light") or event.is_action_pressed("attack_heavy"):
			var dir: int = 1 if event.is_action_pressed("attack_light") else -1
			var nxt: int = _next_ally(host.views(0.0), follow_entity, dir)
			if nxt >= 0:
				follow_entity = nxt
				_attach_camera(nxt)
	# pings: tap = contextual, hold = wheel (mouse direction selects)
	if event.is_action_pressed("ping"):
		_ping_down_ms = Time.get_ticks_msec()
		_ping_accum = Vector2.ZERO
	elif event.is_action_released("ping") and _ping_down_ms >= 0:
		var held: int = Time.get_ticks_msec() - _ping_down_ms
		_ping_down_ms = -1
		var kind: String = hud.ping_select if held > 250 and hud.ping_select != "" else _contextual_ping()
		hud.show_ping_wheel(false, "")
		rig.input_enabled = true
		_send_ping(kind)
	elif event is InputEventMouseMotion and _ping_down_ms >= 0 and Time.get_ticks_msec() - _ping_down_ms > 250:
		rig.input_enabled = false
		_ping_accum += (event as InputEventMouseMotion).relative
		hud.show_ping_wheel(true, _wheel_kind(_ping_accum))
	if event.is_action_pressed("quick_chat_1") and host.mode == "online":
		host.send_chat("On my way!", true)
	if event.is_action_pressed("quick_chat_2") and host.mode == "online":
		host.send_chat("Need help!", true)
	if host.mode == WR.MODE_TRAINING and event is InputEventKey and (event as InputEventKey).pressed:
		var lh := host as LocalMatchHost
		match (event as InputEventKey).keycode:
			KEY_F1: _training("idle", lh)
			KEY_F2: _training("guard", lh)
			KEY_F3: _training("attack", lh)
			KEY_F4: _training("dodge", lh)
			KEY_F5:
				lh.reset_training()
				hud.training_info.text = "Positions and health reset"


func _training(b: String, lh: LocalMatchHost) -> void:
	lh.set_dummy_behaviour(b)
	hud.training_info.text = "Dummies: %s" % b


func _wheel_kind(v: Vector2) -> String:
	if v.length() < 12.0:
		return ""
	var kinds: Array = Protocol.PING_KINDS
	var a: float = fposmod(atan2(v.y, v.x) + PI * 0.5 + PI / kinds.size(), TAU)
	return String(kinds[int(a / TAU * kinds.size()) % kinds.size()])


func _contextual_ping() -> String:
	var aim: Vector3 = rig.aim_point()
	var vstates: Dictionary = host.views(0.0)
	for e in vstates.keys():
		if host.relation_of(int(e)) == "enemy" and not bool(vstates[e].get("hidden", false)):
			if (vstates[e]["pos"] as Vector3).distance_to(aim) < 2.5:
				return "enemy"
	var zone: String = String(host.match_state().get("zone", ""))
	if zone != "" and layout.zone_center(zone).distance_to(aim) < 10.0:
		return "attack"
	return "on_my_way"


func _send_ping(kind: String) -> void:
	var pos: Vector3 = rig.aim_point()
	host.send_ping(pos, kind)
	if host.mode != "online":
		pass   # local host echoes the ping through its signal


func _replay_input(event: InputEvent) -> void:
	var rh := host as ReplayHost
	if event.is_action_pressed("jump") or (event is InputEventKey and (event as InputEventKey).pressed and (event as InputEventKey).keycode == KEY_SPACE):
		_on_replay_command("toggle", 0.0)
	elif event is InputEventKey and (event as InputEventKey).pressed:
		match (event as InputEventKey).keycode:
			KEY_LEFT: rh.seek(rh.t - 5.0 * WR.TICK_RATE)
			KEY_RIGHT: rh.seek(rh.t + 5.0 * WR.TICK_RATE)
			KEY_F: _on_replay_command("free_cam", 0.0)
			KEY_TAB: _on_replay_command("follow_next", 0.0)
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_RIGHT:
			rig.capture_mouse(mb.pressed)


func _on_replay_command(cmd: String, value: float) -> void:
	var rh := host as ReplayHost
	if rh == null:
		return
	match cmd:
		"toggle":
			rh.paused = not rh.paused
		"seek":
			rh.seek(float(rh.start_tick) + value * rh.duration_ticks)
		"speed":
			rh.speed = value
		"free_cam":
			free_cam = not free_cam
			rig.spectator_free = free_cam
			if not free_cam:
				_attach_camera(follow_entity)
		"follow_next":
			free_cam = false
			rig.spectator_free = false
			var ks: Array = host.fighter_info.keys()
			ks.sort()
			var i: int = ks.find(follow_entity)
			follow_entity = int(ks[(i + 1) % ks.size()])
			_attach_camera(follow_entity)


func _open_pause() -> void:
	paused = host.mode in ["offline", "training"]
	if host is ReplayHost:
		(host as ReplayHost).paused = true
	rig.capture_mouse(false)
	rig.input_enabled = false
	if player_input != null:
		player_input.enabled = false
	pause_menu.open()


func _on_resume() -> void:
	paused = false
	rig.input_enabled = true
	if player_input != null:
		player_input.enabled = true
		player_input.clear()
	if not (host is ReplayHost) and not finished:
		rig.capture_mouse(true)


func _leave() -> void:
	host.leave()
	AudioDirector.stop_ambience()
	AudioDirector.stop_all_sfx()
	Game.goto_menu()


# ------------------------------------------------------------------------------------------
# events & end of match
# ------------------------------------------------------------------------------------------
func _on_events(evs: Array) -> void:
	vfx.handle(evs)
	hud.handle(evs)


func _on_finished(info: Dictionary) -> void:
	if finished:
		return
	finished = true
	Game.last_result = info
	var rj: String = Config.get_arg("result-json", "")
	if rj != "":
		var f := FileAccess.open(rj, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(info, "  "))
			f.close()
		print("[match] result written: " + rj)
		get_tree().create_timer(1.0).timeout.connect(_quit_automation)
		return
	if host is ReplayHost:
		return
	get_tree().create_timer(4.5).timeout.connect(func() -> void:
		if _capture_dir != "" or Config.quit_after_s > 0.0:
			return   # automation stays in the scene
		rig.capture_mouse(false)
		AudioDirector.stop_ambience()
		if ResourceLoader.exists(Game.SCENE_RESULTS):
			Game.goto(Game.SCENE_RESULTS, {})
		else:
			Game.goto_menu())


# ------------------------------------------------------------------------------------------
# automation: screenshots and frame-time logging
# ------------------------------------------------------------------------------------------
func _setup_capture() -> void:
	_capture_dir = Config.get_arg("capture-dir", "")
	if _capture_dir != "":
		DirAccess.make_dir_recursive_absolute(_capture_dir)
		for s in Config.get_arg("capture-at", "8").split(",", false):
			_captures.append(float(s))
		_captures.sort()
	var perf_path: String = Config.get_arg("perf-log", "")
	if perf_path != "":
		_perf = FileAccess.open(perf_path, FileAccess.WRITE)


func _capture_tick() -> void:
	if _captures.is_empty() or _t < float(_captures[0]):
		return
	var at: float = _captures.pop_front()
	var img: Image = get_viewport().get_texture().get_image()
	var tag: String = Config.get_arg("capture-tag", String(params.get("mode", "match")))
	var path: String = _capture_dir.path_join("%s_%03ds.png" % [tag, int(at)])
	img.save_png(path)
	print("[capture] " + path)
	if _captures.is_empty() and Config.quit_after_s <= 0.0:
		_quit_automation()


func _perf_tick(dt: float) -> void:
	if _perf == null:
		return
	_perf_acc.append(dt)
	if _perf_acc.size() >= 60:
		var s: Array = _perf_acc.duplicate()
		s.sort()
		var total: float = 0.0
		for x in s:
			total += float(x)
		_perf.store_line(JSON.stringify({"t": snappedf(_t, 0.01), "fps": snappedf(s.size() / total, 0.1),
			"p50_ms": snappedf(float(s[s.size() / 2]) * 1000.0, 0.01), "p99_ms": snappedf(float(s[int(s.size() * 0.99)]) * 1000.0, 0.01),
			"max_ms": snappedf(float(s[s.size() - 1]) * 1000.0, 0.01),
			"physics_ms": snappedf(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0, 0.01),
			"draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
			"prims": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
			"mem_mb": snappedf(Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0, 0.1)}))
		_perf.flush()
		_perf_acc.clear()


func _quit_automation() -> void:
	if _perf != null:
		_perf.close()
		_perf = null
	get_tree().quit(0)


# ------------------------------------------------------------------------------------------
# automation: online direct connect (tests/screenshots). Real players use the lobby screens.
# ------------------------------------------------------------------------------------------
var _auto_last_req: int = -100000


func _auto_connect() -> void:
	var hp: PackedStringArray = Config.connect_to.split(":")
	var auth: Dictionary = {"name": Config.player_name if Config.player_name != "" else "Viewer"}
	if Config.ticket != "":
		auth["ticket"] = Config.ticket
	var err: int = Game.start_online_session(hp[0], int(hp[1]) if hp.size() > 1 else 24610, auth)
	if err != OK:
		_fatal("Could not connect (%s)." % error_string(err))
		return
	Game.session.lobby_updated.connect(_auto_lobby)
	Game.session.match_setup_received.connect(func(_d: Dictionary) -> void:
		if host != null:
			return
		var nh := NetMatchHost.new()
		nh.name = "Host"
		add_child(nh)
		player_input = PlayerInput.new()
		add_child(player_input)
		nh.setup_session(Game.session, player_input)
		host = nh
		_build_world("online"))


func _auto_lobby(l: Dictionary) -> void:
	if int(l.get("stage", 0)) != 1:
		return
	var me: int = int(Game.session.info.get("pid", -1))
	var mine: Dictionary = {}
	var team_i: int = 0
	for t in range(2):
		for pl in l["roster"]["teams"][t]:
			if int(pl["pid"]) == me:
				mine = pl
				team_i = t
	if mine.is_empty() or bool(mine["locked"]):
		return
	if Time.get_ticks_msec() - _auto_last_req < 700:
		return
	_auto_last_req = Time.get_ticks_msec()
	var taken: Dictionary = {}
	for pl2 in l["roster"]["teams"][team_i]:
		if int(pl2["pid"]) != me and String(pl2["fighter"]) != "":
			taken[String(pl2["fighter"])] = true
	if String(mine["fighter"]) == "" or taken.has(String(mine["fighter"])):
		var prefs: Array = [String(params.get("fighter", "nyx"))]
		prefs.append_array(WR.FIGHTER_IDS)
		for f in prefs:
			if not taken.has(f):
				Game.session.request({"t": "pick", "f": f})
				return
	else:
		Game.session.request({"t": "lock"})
