class_name HistoryScreen
extends MenuScreen
## History & Replays (docs/UI_CONTRACT.md §6): offline history (Profile.data["history"]),
## online history (GET /v1/matches/history) when signed in, and replay files in
## user://replays/ (list with size/date/summary, play, delete with confirmation).

## Replay folder (the screenshot tool points it at fixtures).
static var replay_dir: String = "user://replays/"
const TAB_IDS: Array[String] = ["offline", "online", "replays"]

var tabs: UiTabs
var online_items: Array = []
var online_error: String = ""
var online_loaded: bool = false
var replays: Array = []            # [{path, name, size, mtime, header}]
var _body: VBoxContainer
var _pending_headers: Array[int] = []
var _loading: bool = false


func build() -> void:
	title = "History & replays"
	var v := UiKit.vbox(12)
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(v)
	tabs = UiTabs.new()
	for t in ["Offline matches", "Online matches", "Replays"]:
		tabs.add_tab(t)
	tabs.tab_changed.connect(func(_i: int) -> void: _rebuild(true))
	v.add_child(tabs)
	var p := UiKit.panel(&"PanelGlass")
	p.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(p)
	_body = UiKit.vbox(8)
	var m := UiKit.margin(2, 2, 16, 2)
	m.add_child(_body)
	p.add_child(UiKit.scroll(m))


func enter(params: Dictionary) -> void:
	if params.has("tab"):
		tabs.select(maxi(0, TAB_IDS.find(String(params["tab"]))), false)
	if not params.get("back", false):
		online_loaded = false
	scan_replays()
	_rebuild(true)


func hints() -> Array:
	return [["accept", "Select"], ["tabs", "Switch tab"], ["back", "Back"]]


func screen_input(event: InputEvent) -> bool:
	return tabs.handle_shortcut(event)


func default_focus() -> Control:
	var f: Control = UiKit.first_focusable(_body)
	return f if f != null else tabs.tab_buttons[tabs.current]


func _rebuild(focus_first: bool) -> void:
	UiKit.clear_children(_body)
	match TAB_IDS[tabs.current]:
		"offline": _build_offline()
		"online": _build_online()
		"replays": _build_replays()
	if focus_first:
		_focus_first.call_deferred()


func _focus_first() -> void:
	if menu == null or menu.is_modal_open() or not is_visible_in_tree():
		return
	var f: Control = UiKit.first_focusable(_body)
	if f == null:
		f = tabs.tab_buttons[tabs.current]
	UiKit.focus(f)
	for b in tabs.tab_buttons:
		b.focus_neighbor_bottom = b.get_path_to(f)


func _empty(icon_kind: String, head: String, text: String) -> void:
	var h := UiKit.hbox(14)
	h.add_child(UiKit.icon(icon_kind, 30.0, UiKit.TEXT_FAINT))
	var tv := UiKit.vbox(2)
	tv.add_child(UiKit.label(head, &"Heading"))
	tv.add_child(UiKit.label(text, &"Dim", true))
	tv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(tv)
	_body.add_child(UiKit.gap(8))
	_body.add_child(h)


func _result_chip(won: bool) -> PanelContainer:
	return UiKit.chip("VICTORY" if won else "DEFEAT", UiKit.OK if won else UiKit.ERR, "trophy" if won else "cross")


func _fighter_cell(fid: String) -> HBoxContainer:
	var h := UiKit.hbox(8)
	var e := FighterEmblem.new()
	e.fighter_id = fid
	e.custom_minimum_size = Vector2(30, 30)
	h.add_child(e)
	h.add_child(UiKit.label(UiKit.fighter_name(fid) if fid != "" else "—"))
	h.custom_minimum_size = Vector2(150, 0)
	return h


# ------------------------------------------------------------------------------------------
# offline
# ------------------------------------------------------------------------------------------
func _build_offline() -> void:
	var hist: Array = Profile.data.get("history", [])
	var totals: Dictionary = Profile.data.get("totals", {})
	var head := UiKit.hbox(28)
	head.add_child(UiKit.key_value("Matches", str(int(totals.get("matches", 0)))))
	head.add_child(UiKit.key_value("Wins", str(int(totals.get("wins", 0)))))
	head.add_child(UiKit.key_value("Stored", "last %d" % Profile.HISTORY_MAX))
	_body.add_child(head)
	_body.add_child(UiKit.rule())
	if hist.is_empty():
		_empty("clock", "No offline matches yet", "Finished offline matches appear here with their result, score and mastery XP.")
		return
	var g := UiKit.grid(7, 20, 8)
	_body.add_child(g)
	for h in ["RESULT", "FIGHTER", "SCORE", "KOS", "XP", "PLAYED", ""]:
		g.add_child(UiKit.label(String(h), &"Caption"))
	var i: int = 0
	for e in hist:
		var d: Dictionary = e
		g.add_child(_result_chip(bool(d.get("won", false))))
		g.add_child(_fighter_cell(String(d.get("fighter", ""))))
		var sc: Array = d.get("score", [0, 0])
		var team: int = int(d.get("team", 0))
		var mine: int = int(sc[team]) if sc.size() > team else 0
		var theirs: int = int(sc[1 - team]) if sc.size() > 1 - team else 0
		g.add_child(UiKit.label("%d – %d" % [mine, theirs], &"Stat"))
		g.add_child(UiKit.label(str(int(d.get("kos", 0))), &"Dim"))
		g.add_child(UiKit.label("+%d" % int(d.get("xp", 0)), &"Dim"))
		g.add_child(UiKit.label(UiKit.fmt_datetime(String(d.get("when", ""))), &"Small"))
		var rp: String = String(d.get("replay", ""))
		if rp != "" and FileAccess.file_exists(rp):
			var b := UiKit.button("Watch replay", &"SmallButton", func() -> void: _play(rp))
			b.name = "OfflineReplay_%d" % i
			g.add_child(b)
		else:
			g.add_child(UiKit.label("", &"Small"))
		i += 1


# ------------------------------------------------------------------------------------------
# online
# ------------------------------------------------------------------------------------------
func _build_online() -> void:
	if not Online.is_configured() or not Online.is_logged_in():
		var msg: String = String(Online.url_status()["message"]) if not Online.is_configured() else "Sign in (Play online → Account) to see matches recorded by the service."
		_empty("wifi_off", "Online history unavailable", msg)
		var b := UiKit.button("Go to Play online", &"", func() -> void: menu.open_screen("online", {"tab": "account"}))
		b.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		_body.add_child(b)
		return
	if not online_loaded and not _loading:
		_load_online("")
	if _loading and online_items.is_empty():
		_body.add_child(UiKit.label("Loading match history…", &"Dim"))
		return
	if online_error != "":
		var h := UiKit.hbox(8)
		h.add_child(UiKit.icon("error", 18.0, UiKit.ERR))
		h.add_child(UiKit.label(online_error, &"ErrorLabel"))
		_body.add_child(h)
		var rb := UiKit.button("Retry", &"", func() -> void: _load_online(""))
		rb.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		_body.add_child(rb)
		return
	if online_items.is_empty():
		_empty("clock", "No online matches yet", "Matches submitted by game servers appear here with rating and mastery changes.")
		return
	var g := UiKit.grid(6, 20, 8)
	_body.add_child(g)
	for h2 in ["RESULT", "MODE", "FIGHTER", "SCORE", "RATING", "PLAYED"]:
		g.add_child(UiKit.label(String(h2), &"Caption"))
	for e in online_items:
		var d: Dictionary = e
		g.add_child(_result_chip(bool(d.get("won", false))))
		g.add_child(UiKit.label(UiKit.mode_label(String(d.get("mode", ""))), &"Dim"))
		g.add_child(_fighter_cell(String(d.get("fighter", "")) if d.get("fighter") != null else ""))
		var sc: Array = d.get("score", [0, 0]) if d.get("score") is Array else [0, 0]
		var team: int = clampi(int(d.get("team", 0)), 0, 1)
		g.add_child(UiKit.label("%d – %d" % [int(sc[team]), int(sc[1 - team])], &"Stat"))
		var rd: Variant = d.get("rating_delta")
		var rtxt: String = "—" if rd == null else ("%+d" % int(round(float(rd))))
		var rl := UiKit.label(rtxt, &"Dim")
		if rd != null:
			rl.add_theme_color_override("font_color", UiKit.OK if float(rd) >= 0.0 else UiKit.ERR)
		g.add_child(rl)
		g.add_child(UiKit.label(UiKit.fmt_datetime(String(d.get("ended_at", ""))), &"Small"))
	if online_items.size() % 20 == 0:
		var more := UiKit.button("Load older matches", &"", func() -> void:
			_load_online(String((online_items[online_items.size() - 1] as Dictionary).get("ended_at", ""))))
		more.name = "LoadMore"
		more.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		_body.add_child(more)


func _load_online(before: String) -> void:
	_loading = true
	if before == "":
		online_items = []
	var r: Dictionary = await Online.history(20, before)
	_loading = false
	online_loaded = true
	if not is_inside_tree():
		return
	if bool(r["ok"]) and r["data"] is Array:
		online_items.append_array(r["data"] as Array)
		online_error = ""
	else:
		online_error = String((r["error"] as Dictionary).get("message", "Could not load the history."))
	if TAB_IDS[tabs.current] == "online":
		_rebuild(false)


# ------------------------------------------------------------------------------------------
# replays
# ------------------------------------------------------------------------------------------
func scan_replays() -> void:
	replays.clear()
	_pending_headers.clear()
	var dir := DirAccess.open(replay_dir)
	if dir == null:
		return
	for f in dir.get_files():
		if not f.ends_with(".wrr"):
			continue
		var path: String = replay_dir + f
		var fa := FileAccess.open(path, FileAccess.READ)
		var sz: int = fa.get_length() if fa != null else 0
		if fa != null:
			fa.close()
		replays.append({"path": path, "name": f.get_basename(), "size": sz, "mtime": FileAccess.get_modified_time(path), "header": null})
	replays.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return int(a["mtime"]) > int(b["mtime"]))
	for i in range(replays.size()):
		_pending_headers.append(i)


func _process(_delta: float) -> void:
	# replay headers need the whole file decompressed: read one per frame, only while visible
	if _pending_headers.is_empty() or not is_visible_in_tree():
		return
	var i: int = _pending_headers.pop_front()
	if i >= replays.size():
		return
	var h: Dictionary = ReplayRecorder.read_header(String(replays[i]["path"]))
	replays[i]["header"] = h
	if _pending_headers.is_empty() and TAB_IDS[tabs.current] == "replays":
		_rebuild(false)


func _build_replays() -> void:
	if replays.is_empty():
		_empty("film", "No replays yet", "Every match you finish records a replay automatically (%s)." % ProjectSettings.globalize_path(replay_dir))
		return
	var total: int = 0
	for r in replays:
		total += int(r["size"])
	_body.add_child(UiKit.label("%d replays · %s on disk" % [replays.size(), UiKit.fmt_bytes(total)], &"Small"))
	var g := UiKit.grid(6, 20, 8)
	_body.add_child(g)
	for h in ["RECORDED", "MATCH", "SCORE", "SIZE", "", ""]:
		g.add_child(UiKit.label(String(h), &"Caption"))
	for i in range(replays.size()):
		var r: Dictionary = replays[i]
		var path: String = String(r["path"])
		g.add_child(UiKit.label(UiKit.fmt_unix(int(r["mtime"])), &""))
		var hd: Variant = r["header"]
		var summary: String = "Reading…"
		var score: String = "—"
		if hd is Dictionary:
			var hdd: Dictionary = hd
			if hdd.is_empty():
				summary = "Unreadable or incompatible file"
			else:
				var res: Dictionary = hdd.get("result", {}) if hdd.get("result") is Dictionary else {}
				summary = "%s · %s" % [UiKit.mode_label(String(hdd.get("mode", ""))), String(hdd.get("arena", "Briarport"))]
				if String(hdd.get("build", "")) != WR.BUILD_ID:
					summary += " · other build"
				if not res.is_empty():
					score = UiKit.tr_score(res.get("score", []))
		g.add_child(UiKit.label(summary, &"Dim"))
		g.add_child(UiKit.label(score, &"Stat"))
		g.add_child(UiKit.label(UiKit.fmt_bytes(int(r["size"])), &"Small"))
		var play := UiKit.button("Play", &"SmallButton", func() -> void: _play(path))
		play.name = "PlayReplay_%d" % i
		g.add_child(play)
		var del := UiKit.button("Delete", &"SmallButton", func() -> void: _delete(path))
		del.name = "DeleteReplay_%d" % i
		g.add_child(del)


func _play(path: String) -> void:
	UiKit.play("ui_lockin")
	Game.goto(Game.SCENE_MATCH, {"mode": "replay", "replay_path": path})


func _delete(path: String) -> void:
	var id: String = await menu.modal("Delete replay?", "%s will be removed from your computer. This cannot be undone." % path.get_file(),
		[["delete", "Delete", &"DangerButton"], ["cancel", "Cancel", &""]], "cancel", "cancel")
	if id != "delete":
		return
	var err: int = DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	if err == OK:
		toast("Replay deleted.", "ok")
	else:
		toast("Could not delete the replay (%s)." % error_string(err), "error")
	scan_replays()
	_rebuild(true)
