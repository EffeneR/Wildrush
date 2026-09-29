extends Node
## G11 UI screenshot + layout gate (docs/UI_CONTRACT.md "Verification").
##   xvfb-run -a -s "-screen 0 3440x1440x24" $GODOT_BIN --path game res://tools/ui_screenshots.tscn [-- --only name_substring]
## Opens every screen / sub-screen and key state (rebind prompt, conflict prompt, lobby with 10
## players, character select, results victory/defeat, online errors) at 1280x720, 1920x1080
## and 3440x1440, saves PNGs to evidence/ui/<WxH>/<state>.png, runs scripted keyboard/pad
## focus-navigation checks, and exits non-zero on any engine error or any visible Control
## clipped outside the viewport. Online states marked "fixture" render injected service data
## (no service is contacted); nothing is written to the player's profile or settings.

const RESOLUTIONS: Array[Vector2i] = [Vector2i(1280, 720), Vector2i(1920, 1080), Vector2i(3440, 1440)]
const FIXTURE_URL: String = "https://play.wildrush.example"

class ErrLog extends Logger:
	var errors: Array[String] = []
	var mutex := Mutex.new()
	func _log_error(function: String, file: String, line: int, code: String, rationale: String, _editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		if error_type == Logger.ERROR_TYPE_WARNING:
			return
		mutex.lock()
		errors.append("%s:%d %s %s %s" % [file, line, function, code, rationale])
		mutex.unlock()
	func _log_message(_message: String, _error: bool) -> void:
		pass

var out_dir: String = ""
var errlog: ErrLog
var shots: Array = []
var interactions: Array = []
var failures: Array[String] = []
var only: String = ""
var _scene: Node = null
var _saved_profile: Dictionary = {}
var _saved_settings: Dictionary = {}
var _fixture_dir: String = "user://ui_screenshot_fixtures/"
var _session: ClientSession = null


func _ready() -> void:
	errlog = ErrLog.new()
	OS.add_logger(errlog)
	only = Config.get_arg("only", "")
	out_dir = ProjectSettings.globalize_path("res://").path_join("../evidence/ui").simplify_path()
	DirAccess.make_dir_recursive_absolute(out_dir)
	if DisplayServer.get_name() == "headless":
		push_error("ui_screenshots needs a rendering display (run under xvfb-run, not --headless)")
		get_tree().quit(2)
		return
	_saved_profile = Profile.data.duplicate(true)
	_saved_settings = Settings.values.duplicate(true)
	_make_fixtures()
	var t0: int = Time.get_ticks_msec()
	for res in RESOLUTIONS:
		await _set_resolution(res)
		await _run_states(res)
	await _run_interactions()
	_restore()
	var rep: Dictionary = {"godot": Engine.get_version_info()["string"], "renderer": RenderingServer.get_video_adapter_name(),
		"driver": RenderingServer.get_current_rendering_driver_name(), "ms": Time.get_ticks_msec() - t0,
		"shots": shots, "interactions": interactions, "engine_errors": errlog.errors, "failures": failures,
		"ok": failures.is_empty() and errlog.errors.is_empty()}
	var f := FileAccess.open(out_dir.path_join("report.json"), FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(rep, "  "))
		f.close()
	for e in errlog.errors:
		print("ENGINE ERROR: ", e)
	for fl in failures:
		print("FAIL: ", fl)
	print("UI SCREENSHOTS: %d shots, %d interactions, %d failures, %d engine errors -> %s" % [shots.size(), interactions.size(), failures.size(), errlog.errors.size(), out_dir])
	# stop music so the audio stream is released before quitting
	for p in AudioDirector.get_children():
		if p is AudioStreamPlayer:
			(p as AudioStreamPlayer).stop()
	await get_tree().process_frame
	get_tree().quit(0 if bool(rep["ok"]) else 1)


# ------------------------------------------------------------------------------------------
# fixtures (memory only; restored at the end)
# ------------------------------------------------------------------------------------------
func _make_fixtures() -> void:
	Profile.data["display_name"] = "Ashbrook"
	Profile.data["fighters"]["nyx"]["xp"] = 2650
	Profile.data["fighters"]["bruno"]["xp"] = 820
	Profile.data["fighters"]["vex"]["xp"] = 5100
	Profile.data["fighters"]["hops"]["xp"] = 310
	Profile.data["fighters"]["scrap"]["xp"] = 90
	Profile.data["fighters"]["vex"]["selected_palette"] = "ember"
	Profile.data["selected_badge"] = "vex_adept"
	Profile.data["totals"] = {"matches": 23, "wins": 13}
	var hist: Array = []
	var fids: Array[String] = ["vex", "nyx", "vex", "bruno", "hops", "vex", "scrap"]
	for i in range(fids.size()):
		hist.append({"when": "2026-09-2%dT1%d:0%d:00" % [8 - i % 3, i, i], "mode": "offline", "fighter": fids[i], "won": i % 3 != 1,
			"score": [250 - i * 7, 171 + i * 5] if i % 3 != 1 else [188, 250], "team": 0, "kos": 3 + i, "xp": 190 + i * 12, "replay": ""})
	Profile.data["history"] = hist
	Settings.values["player"]["name"] = "Ashbrook"
	# fixture replays (real .wrr format written by ReplayRecorder)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_fixture_dir + "replays"))
	for i in range(3):
		var rr := ReplayRecorder.new()
		rr.header = {"magic": ReplayRecorder.MAGIC, "version": 1, "build": WR.BUILD_ID, "protocol": WR.PROTOCOL_VERSION,
			"match_id": "offline-fixture-%d" % i, "mode": "offline" if i != 1 else "casual", "arena": "Briarport",
			"recorded_at": "2026-09-28T12:0%d:00" % i, "fighters": [], "result": {"score": [250, 180 + i * 20], "winner_team": 0}}
		rr.save(_fixture_dir + "replays/match_%d.wrr" % i)
	HistoryScreen.replay_dir = _fixture_dir + "replays/"


func _restore() -> void:
	Profile.data = _saved_profile
	Settings.values = _saved_settings
	Online.token = ""
	Online.account = {}
	HistoryScreen.replay_dir = "user://replays/"
	Game.last_result = {}
	Game.session = null
	if _session != null and is_instance_valid(_session):
		_session.queue_free()
	var d := DirAccess.open(_fixture_dir + "replays")
	if d != null:
		for f in d.get_files():
			d.remove(f)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(_fixture_dir + "replays"))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(_fixture_dir))


func _set_url(url: String) -> void:
	Settings.values["online"]["service_url"] = url


func _fake_login(on: bool) -> void:
	if on:
		_set_url(FIXTURE_URL)
		Online.token = "fixture-token"
		Online.token_base = FIXTURE_URL
		Online.account = {"account_id": "a-1", "username": "ashbrook", "display_name": "Ashbrook", "created_at": "2026-08-14T10:00:00Z",
			"rating": {"rating": 1612.4, "deviation": 88.1, "games": 31, "wins": 18, "losses": 13}}
	else:
		Online.token = ""
		Online.token_base = ""
		Online.account = {}


func _results_fixture(victory: bool) -> Dictionary:
	var players: Array = []
	var bots: Array = []
	var names: Array[String] = ["Ashbrook", "Rook", "Marlow", "Tinsel", "Quill", "Vesper", "Oakley", "Juniper", "Sable", "Wren"]
	var e: int = 0
	for team in range(2):
		for fid in WR.FIGHTER_IDS:
			var row: Dictionary = {"entity": e, "team": team, "fighter": fid, "name": names[e], "account_id": "", "kos": (e * 7) % 9,
				"knocked_out": (e * 5) % 7, "damage_dealt": 900 + e * 173 % 1100, "control_seconds": 20 + (e * 13) % 70,
				"abandoned": e == 8 and not victory, "afk": e == 6 and not victory, "bot": false}
			if (victory and e > 0) or (not victory and e in [3, 4, 9]):
				row["bot"] = true
				row["name"] = "BOT " + UiKit.fighter_name(fid).to_upper()
				bots.append(row)
			else:
				players.append(row)
			e += 1
	var res: Dictionary = {"match_id": "offline-fixture" if victory else "c0ffee00-fixture", "mode": "offline" if victory else "casual",
		"winner_team": 0 if victory else 1, "score": [250, 173] if victory else [212, 216], "duration_s": 402.5 if victory else 480.0 + 23.0,
		"sudden_death": not victory, "ended_reason": "score_limit" if victory else "sudden_death", "players": players, "bots": bots,
		"seed": 1234, "build": WR.BUILD_ID}
	var info: Dictionary = {"result": res, "my_entity": 1 if not victory else 0, "my_team": 0, "mode": res["mode"],
		"fighter": "vex" if victory else "bruno", "replay_path": "",
		"params": {"mode": "offline", "fighter": "vex", "palette": "ember", "difficulty": "normal"}}
	if victory:
		info["awards"] = {"fighter": "vex", "xp_gained": 310, "level_before": 5, "level_after": 6,
			"unlocks": [{"kind": "badge", "id": "vex_veteran"}]}
	else:
		info["online"] = true
		info["awards"] = {}
	return info


func _lobby_fixture(stage: int) -> Dictionary:
	var names: Array[String] = ["Ashbrook", "Rook", "Marlow", "Tinsel", "Quill", "Vesper", "Oakley", "Juniper", "Sable", "Wren"]
	var teams: Array = [[], []]
	var pid: int = 1
	for t in range(2):
		for s in range(5):
			var fid: String = ""
			var locked: bool = false
			if stage == 1:
				fid = WR.FIGHTER_IDS[(s + t * 2) % 5] if not (t == 0 and s == 0) else "vex"
				if t == 0 and s == 2:
					fid = "hops"
				if t == 0 and s == 1:
					fid = "bruno"
				if t == 0 and s == 3:
					fid = ""
				if t == 0 and s == 4:
					fid = "scrap"
				locked = (s % 2 == 1) and fid != ""
			teams[t].append({"pid": pid, "name": names[pid - 1], "slot": s, "fighter": fid, "locked": locked,
				"ready": (pid % 3) != 0, "bot": stage == 1 and t == 1 and s == 4, "connected": pid != 7})
			pid += 1
	if stage == 1:
		teams[0][0]["fighter"] = "vex"
		teams[0][0]["locked"] = false
		teams[0][2]["locked"] = false
	return {"t": "lobby", "stage": stage, "roster": {"teams": teams, "swaps": [[3, 1]] if stage == 1 else [],
		"allow_bots": stage == 1, "bot_difficulty": "normal"}, "admin": 1, "mode": "private",
		"select_left_s": 27.0 if stage == 1 else 0.0, "observers_allowed": true, "expected": 10}


# ------------------------------------------------------------------------------------------
# scenes
# ------------------------------------------------------------------------------------------
func _open(path: String) -> Node:
	_close()
	var ps: PackedScene = load(path) as PackedScene
	_scene = ps.instantiate()
	add_child(_scene)
	await _frames(3)
	return _scene


func _close() -> void:
	if _scene != null and is_instance_valid(_scene):
		remove_child(_scene)
		_scene.queue_free()
	_scene = null
	for c in get_tree().get_nodes_in_group(UiToasts.GROUP):
		c.get_parent().queue_free()


func _frames(n: int) -> void:
	for i in range(n):
		await get_tree().process_frame


func _set_resolution(res: Vector2i) -> void:
	get_window().mode = Window.MODE_WINDOWED
	get_window().size = res
	get_window().position = Vector2i.ZERO
	await _frames(6)
	if get_window().size != res:
		failures.append("window could not be resized to %s (got %s)" % [res, get_window().size])


func _run_states(res: Vector2i) -> void:
	var dir: String = out_dir.path_join("%dx%d" % [res.x, res.y])
	DirAccess.make_dir_recursive_absolute(dir)
	# splash
	var sp: Node = await _open("res://scenes/splash.tscn")
	sp.call("freeze_for_capture")
	await _shot(dir, "splash")
	# main menu
	_fake_login(false)
	_set_url("")
	var menu: MainMenu = await _open("res://scenes/main_menu.tscn") as MainMenu
	await _shot(dir, "menu_home", 4)
	menu.open_screen("offline")
	await _shot(dir, "menu_offline_setup", 8)
	menu.open_screen("training")
	await _shot(dir, "menu_training_setup", 8)
	menu.open_screen("collection")
	await _shot(dir, "menu_collection", 8)
	var hs: HistoryScreen = menu.open_screen("history") as HistoryScreen
	await _shot(dir, "menu_history_offline", 3)
	hs.tabs.select(2)
	await _frames(6)
	await _shot(dir, "menu_history_replays", 3)
	menu.open_screen("credits")
	await _shot(dir, "menu_credits", 3)
	menu.go_home()
	await _frames(2)
	menu.confirm_quit()
	await _shot(dir, "menu_quit_confirm", 3)
	_close_modals()
	# online: unconfigured, insecure URL, signed-out form with error, signed-in fixture states
	var on: OnlineScreen = menu.open_screen("online") as OnlineScreen
	on.poll_enabled = false
	on._poll.stop()
	on.tabs.select(0)
	await _shot(dir, "menu_online_unconfigured", 3)
	_set_url("http://example.com")
	on.tabs.select(0)
	await _shot(dir, "menu_online_error_insecure_url", 3)
	_set_url(FIXTURE_URL)
	on.inline_error = "Wrong username or password."
	on.tabs.select(0)
	on.inline_error = ""
	await _shot(dir, "menu_online_account_error_fixture", 3)
	_fake_login(true)
	on.tabs.select(0)
	await _shot(dir, "menu_online_account_signed_in_fixture", 3)
	on.party = {"party_id": "p-1", "leader_id": "a-1", "members": [
		{"account_id": "a-1", "username": "ashbrook", "display_name": "Ashbrook"},
		{"account_id": "a-2", "username": "rook_77", "display_name": "Rook"},
		{"account_id": "a-3", "username": "marlow", "display_name": "Marlow"}],
		"invites": [{"invite_id": "i-1", "to_username": "tinsel", "expires_at": "2026-09-28T12:34:00Z"}], "queue": null}
	on.incoming = [{"invite_id": "i-9", "party_id": "p-9", "from_username": "quillfeather", "expires_at": "2026-09-28T12:36:00Z"}]
	on.queue = {"state": "idle", "mode": null, "queued_seconds": null, "counts": {"casual": 7, "ranked": 12}, "match": null}
	on.tabs.select(1)
	await _shot(dir, "menu_online_party_fixture", 3)
	on.tabs.select(2)
	await _shot(dir, "menu_online_play_fixture", 3)
	on._apply_queue({"state": "queued", "mode": "casual", "queued_seconds": 47, "counts": {"casual": 7, "ranked": 12}, "match": null})
	on._rebuild(false)
	await _shot(dir, "menu_online_queued_fixture", 3)
	on._found_left = 1000.0
	on.queue = {"state": "matched", "mode": "casual", "queued_seconds": null, "counts": {"casual": 0, "ranked": 12},
		"match": {"match_id": "m-1", "host": "203.0.113.20", "port": 24617, "ticket": "t", "team": 1, "expires_at": "2026-09-28T12:40:00Z", "mode": "casual", "state": "ready"}}
	on._rebuild(false)
	await _shot(dir, "menu_online_match_found_fixture", 3)
	on._found_left = -1.0
	on.queue = {"state": "idle", "counts": {"casual": 7, "ranked": 12}}
	on.tabs.select(3)
	await _shot(dir, "menu_online_private_fixture", 3)
	on.servers = [
		{"server_id": "eu-west-1", "name": "Briarport EU West 1", "region": "eu-west", "host": "203.0.113.20", "status": "online", "capacity": 8, "active_matches": 3, "last_seen": "2026-09-28T12:30:05Z", "build_id": WR.BUILD_ID, "protocol": WR.PROTOCOL_VERSION},
		{"server_id": "eu-west-2", "name": "Briarport EU West 2", "region": "eu-west", "host": "203.0.113.21", "status": "draining", "capacity": 8, "active_matches": 1, "last_seen": "2026-09-28T12:30:02Z", "build_id": WR.BUILD_ID, "protocol": WR.PROTOCOL_VERSION},
		{"server_id": "us-east-1", "name": "Harbor US East", "region": "us-east", "host": "198.51.100.7", "status": "online", "capacity": 6, "active_matches": 0, "last_seen": "2026-09-28T12:29:58Z", "build_id": "wildrush-0.9.0", "protocol": 2}]
	on.tabs.select(4)
	await _shot(dir, "menu_online_servers_fixture", 3)
	var hs2: HistoryScreen = menu.open_screen("history") as HistoryScreen
	hs2.online_loaded = true
	hs2.online_items = [
		{"match_id": "m-9", "mode": "ranked", "ended_at": "2026-09-27T20:14:00Z", "team": 0, "fighter": "vex", "won": true, "score": [250, 201], "rating_delta": 14.2},
		{"match_id": "m-8", "mode": "casual", "ended_at": "2026-09-27T19:40:00Z", "team": 1, "fighter": "nyx", "won": false, "score": [250, 233], "rating_delta": null},
		{"match_id": "m-7", "mode": "private", "ended_at": "2026-09-26T21:02:00Z", "team": 0, "fighter": "bruno", "won": true, "score": [250, 96], "rating_delta": null}]
	hs2.tabs.select(1)
	await _shot(dir, "menu_history_online_fixture", 3)
	_fake_login(false)
	_set_url("")
	# settings overlay
	menu.go_home()
	menu.open_settings("display")
	await _shot(dir, "settings_display", 3)
	menu.settings_panel.open_tab("audio")
	await _shot(dir, "settings_audio", 3)
	menu.settings_panel.open_tab("controls")
	await _shot(dir, "settings_controls", 3)
	menu.settings_panel._start_capture("skill_q", false)
	await _shot(dir, "settings_controls_rebind_prompt", 3)
	_close_modals()
	await _frames(2)
	var ev := InputEventKey.new()
	ev.physical_keycode = KEY_E
	menu.settings_panel._apply_binding("skill_q", ev)
	await _shot(dir, "settings_controls_conflict_prompt", 3)
	_close_modals()
	await _frames(2)
	menu.settings_panel.open_tab("access")
	await _shot(dir, "settings_accessibility", 3)
	_set_url("http://example.com")
	menu.settings_panel.open_tab("online")
	await _shot(dir, "settings_online_error", 3)
	_set_url("")
	menu.settings_panel.close()
	await _frames(2)
	# results
	Game.last_result = _results_fixture(true)
	await _open("res://scenes/results.tscn")
	await _shot(dir, "results_victory", 30)
	Game.last_result = _results_fixture(false)
	await _open("res://scenes/results.tscn")
	await _shot(dir, "results_defeat", 30)
	Game.last_result = {}
	# online lobby (fixture session: never connected, nothing is sent)
	if _session == null:
		_session = ClientSession.new()
		_session.name = "FixtureSession"
		add_child(_session)
	_session.host = "203.0.113.20"
	_session.port = 24617
	_session.status = "connected"
	_session.info = {"pid": 1, "admin": true, "mode": "private"}
	_session.lobby = _lobby_fixture(0)
	Game.session = _session
	UiState.private_join_code = "K7QM2XWP"
	await _open("res://scenes/online_lobby.tscn")
	await _shot(dir, "lobby_10_players_fixture", 4)
	_session.lobby = _lobby_fixture(1)
	(_scene as OnlineLobby).apply_lobby(_session.lobby)
	await _shot(dir, "lobby_character_select_fixture", 10)
	_session.lobby = {}
	_session.info = {}
	_session.status = "failed"
	await _open("res://scenes/online_lobby.tscn")
	(_scene as OnlineLobby)._on_status("failed", "bad_password")
	await _shot(dir, "lobby_error_connection_failed", 3)
	Game.session = null
	UiState.private_join_code = ""
	_close()
	await _frames(2)


func _close_modals() -> void:
	for n in _all_nodes(get_tree().root):
		if n is UiModal:
			(n as UiModal).close("cancel")


func _all_nodes(n: Node) -> Array[Node]:
	var out: Array[Node] = [n]
	for c in n.get_children():
		out.append_array(_all_nodes(c))
	return out


# ------------------------------------------------------------------------------------------
# capture + layout checks
# ------------------------------------------------------------------------------------------
func _shot(dir: String, name: String, settle_frames: int = 4) -> void:
	if only != "" and not name.contains(only):
		return
	await _frames(settle_frames)
	await RenderingServer.frame_post_draw
	var img: Image = get_viewport().get_texture().get_image()
	var path: String = dir.path_join(name + ".png")
	var err: int = img.save_png(path) if img != null else FAILED
	var issues: Array[String] = _layout_issues()
	var entry: Dictionary = {"state": name, "resolution": dir.get_file(), "file": path, "size": [img.get_width(), img.get_height()] if img != null else [0, 0],
		"saved": err == OK, "clipped": issues, "errors_so_far": errlog.errors.size()}
	shots.append(entry)
	if err != OK:
		failures.append("%s/%s: screenshot not saved (%d)" % [dir.get_file(), name, err])
	for i in issues:
		failures.append("%s/%s: %s" % [dir.get_file(), name, i])
	print("shot %s/%s %s" % [dir.get_file(), name, "OK" if issues.is_empty() and err == OK else "ISSUES %s" % str(issues)])


func _layout_issues() -> Array[String]:
	var out: Array[String] = []
	var vr: Rect2 = get_viewport().get_visible_rect()
	_check_node(get_tree().root, vr, out, false)
	return out


func _check_node(n: Node, vr: Rect2, out: Array[String], clipped_parent: bool) -> void:
	if n is SubViewport:
		return
	var clip: bool = clipped_parent
	if n is Control:
		var c := n as Control
		if not c.is_visible_in_tree():
			return
		if not clipped_parent and c.size.x > 0.5 and c.size.y > 0.5:
			var r: Rect2 = c.get_global_rect()
			if r.position.x < vr.position.x - 1.0 or r.position.y < vr.position.y - 1.0 \
					or r.end.x > vr.end.x + 1.0 or r.end.y > vr.end.y + 1.0:
				out.append("%s (%s) rect %s outside viewport %s" % [c.get_path(), c.get_class(), r, vr.size])
				return
		if c.clip_contents or c is ScrollContainer:
			clip = true
		if c is Label and not clipped_parent:
			var l := c as Label
			if not l.clip_text and l.autowrap_mode == TextServer.AUTOWRAP_OFF and l.text_overrun_behavior == TextServer.OVERRUN_NO_TRIMMING:
				var need: float = l.get_minimum_size().x
				if need > l.size.x + 2.0:
					out.append("%s label text clipped (%.0f > %.0f): %s" % [c.get_path(), need, l.size.x, l.text.left(40)])
	for ch in n.get_children():
		_check_node(ch, vr, out, clip)


# ------------------------------------------------------------------------------------------
# scripted keyboard / controller navigation
# ------------------------------------------------------------------------------------------
func _press(action: String) -> void:
	var a := InputEventAction.new()
	a.action = action
	a.pressed = true
	Input.parse_input_event(a)
	await _frames(1)
	var b := InputEventAction.new()
	b.action = action
	b.pressed = false
	Input.parse_input_event(b)
	await _frames(2)


func _pad(button: JoyButton) -> void:
	var a := InputEventJoypadButton.new()
	a.button_index = button
	a.pressed = true
	Input.parse_input_event(a)
	await _frames(1)
	var b := InputEventJoypadButton.new()
	b.button_index = button
	b.pressed = false
	Input.parse_input_event(b)
	await _frames(2)


func _focus_name() -> String:
	var f: Control = get_viewport().gui_get_focus_owner()
	return String(f.name) if f != null else "<none>"


func _check(name: String, ok: bool, detail: String) -> void:
	interactions.append({"check": name, "ok": ok, "detail": detail})
	if not ok:
		failures.append("interaction %s: %s" % [name, detail])
	print("%s %s: %s" % ["PASS" if ok else "FAIL", name, detail])


func _run_interactions() -> void:
	if only != "":
		return
	await _set_resolution(Vector2i(1920, 1080))
	_set_url("")
	var menu: MainMenu = await _open("res://scenes/main_menu.tscn") as MainMenu
	await _frames(4)
	_check("home_initial_focus", _focus_name() == "Menu_offline", "focus=" + _focus_name())
	await _press("ui_down")
	await _press("ui_down")
	_check("home_down_moves_focus", _focus_name() == "Menu_online", "focus=" + _focus_name())
	await _press("ui_up")
	await _press("ui_accept")
	await _frames(4)
	_check("accept_opens_training", menu.current != null and menu.current.screen_id == "training", "screen=" + (menu.current.screen_id if menu.current else "?"))
	var tr: TrainingSetupScreen = menu.current as TrainingSetupScreen
	var before: String = tr.fighter_id
	await _press("ui_right")
	await _frames(3)
	_check("select_right_changes_fighter", tr.fighter_id != before, "%s -> %s" % [before, tr.fighter_id])
	await _press("ui_cancel")
	await _frames(4)
	_check("cancel_goes_back_home", menu.current.screen_id == "home", "screen=" + menu.current.screen_id)
	menu.open_screen("history")
	await _frames(4)
	var hs: HistoryScreen = menu.current as HistoryScreen
	await _pad(JOY_BUTTON_RIGHT_SHOULDER)
	await _frames(3)
	_check("pad_rb_switches_tab", hs.tabs.current == 1, "tab=%d" % hs.tabs.current)
	await _press("ui_cancel")
	await _frames(3)
	menu.open_settings("controls")
	await _frames(4)
	await _pad(JOY_BUTTON_LEFT_SHOULDER)
	await _frames(3)
	_check("settings_lb_switches_tab", menu.settings_panel != null and menu.settings_panel.tabs.current == 1, "tab=%d" % (menu.settings_panel.tabs.current if menu.settings_panel else -1))
	await _press("ui_cancel")
	await _frames(4)
	_check("settings_cancel_closes_overlay", menu.settings_panel == null, "panel=%s" % str(menu.settings_panel))
	await _press("ui_cancel")
	await _frames(4)
	var modal_open: bool = false
	for n in _all_nodes(get_tree().root):
		if n is UiModal:
			modal_open = true
	_check("cancel_on_home_asks_to_quit", modal_open, "quit dialog open=%s" % modal_open)
	await _press("ui_cancel")
	await _frames(3)
	_close()
	await _frames(2)
