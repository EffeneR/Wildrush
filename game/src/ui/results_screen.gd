class_name ResultsScreen
extends Control
## Match results (res://scenes/results.tscn, docs/UI_CONTRACT.md "Results"): victory/defeat
## banner, score, duration, sudden-death flag, per-team table (fighter, name, KOs, KO'd,
## damage, control seconds, bot/afk/abandoned tags), mastery progress + unlocks, and
## Play again / Watch replay / Back to lobby / Main menu.

const REASONS: Dictionary = {"score_limit": "Score limit reached", "time": "Regulation time — higher score wins",
	"sudden_death": "Decided in sudden death", "forfeit": "Forfeit"}

var info: Dictionary = {}
var result: Dictionary = {}
var my_team: int = -1
var buttons: Array[Button] = []
var _xp_bar: ProgressBar
var _xp_label: Label
var _level_label: Label
var _mastery_box: VBoxContainer
var _online_tries: int = 0
var _hints: UiHintBar


func _ready() -> void:
	info = Game.last_result.duplicate(true)
	result = info.get("result", {}) if info.get("result") is Dictionary else {}
	my_team = _my_team()
	add_child(MenuBackground.new())
	_build()
	UiKit.music("music_results")
	get_viewport().gui_focus_changed.connect(_on_focus_changed)
	if bool(info.get("online", false)) or String(info.get("mode", "")) in ["casual", "ranked", "private", "online"]:
		_fetch_online.call_deferred()


func _on_focus_changed(_c: Control) -> void:
	if UiKit.focus_sound_allowed():
		UiKit.play("ui_hover")


func _my_team() -> int:
	if info.has("my_team"):
		return int(info["my_team"])
	var me: int = int(info.get("my_entity", -1))
	for key in ["players", "bots"]:
		for r in result.get(key, []):
			if int((r as Dictionary).get("entity", -2)) == me:
				return int((r as Dictionary).get("team", -1))
	return -1


func _mode() -> String:
	return String(info.get("mode", result.get("mode", "offline")))


func _build() -> void:
	var outer := UiKit.margin(56, 36, 56, 26)
	outer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	outer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(outer)
	var mw := MaxWidthContainer.new()
	mw.max_width = 1760.0
	mw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	outer.add_child(mw)
	var v := UiKit.vbox(14)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	mw.add_child(v)
	if result.is_empty():
		v.add_child(UiKit.label("NO RESULT", &"Title"))
		v.add_child(UiKit.label("There is no finished match to show.", &"Dim"))
		var mb := UiKit.button("Main menu", &"PrimaryButton", func() -> void: _to_menu())
		mb.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		v.add_child(mb)
		buttons.append(mb)
		UiKit.focus.call_deferred(mb)
		return
	v.add_child(_banner())
	var mid := UiKit.hbox(22)
	mid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(mid)
	var tables := UiKit.vbox(12)
	tables.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tables.size_flags_stretch_ratio = 2.2
	var order: Array[int] = [0, 1]
	if my_team >= 0:
		order = [my_team, 1 - my_team]
	for t in order:
		tables.add_child(_team_table(t))
	var ts := UiKit.scroll(tables)
	ts.size_flags_stretch_ratio = 2.2
	mid.add_child(ts)
	var side := UiKit.panel(&"PanelGlass")
	side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	side.custom_minimum_size = Vector2(380, 0)
	mid.add_child(side)
	_mastery_box = UiKit.vbox(10)
	side.add_child(_mastery_box)
	_build_mastery()
	var foot := UiKit.hbox(12)
	v.add_child(foot)
	_hints = UiHintBar.new()
	_hints.set_hints([["accept", "Select"]])
	foot.add_child(UiKit.label("%s · %s" % [String(result.get("match_id", "")), String(result.get("build", WR.BUILD_ID))], &"Small"))
	foot.add_child(UiKit.spacer())
	var mode: String = _mode()
	var params: Dictionary = info.get("params", {}) if info.get("params") is Dictionary else {}
	if params.is_empty() and mode in ["offline", "training"]:
		params = UiState.last_match_params
	if mode == "offline" and not params.is_empty():
		buttons.append(UiKit.button("Play again", &"PrimaryButton", func() -> void: _play_again(params)))
	var rp: String = String(info.get("replay_path", ""))
	if rp != "" and FileAccess.file_exists(rp):
		buttons.append(UiKit.button("Watch replay", &"", func() -> void:
			Game.goto(Game.SCENE_MATCH, {"mode": "replay", "replay_path": rp})))
	if Game.session != null and Game.session.status in ["connected", "connecting"] and Game.session.live \
			and String(Game.session.info.get("mode", "")) == "private":
		buttons.append(UiKit.button("Back to lobby", &"PrimaryButton" if buttons.is_empty() else &"", func() -> void:
			Game.goto(Game.SCENE_ONLINE_LOBBY, {})))
	buttons.append(UiKit.button("Main menu", &"" if not buttons.is_empty() else &"PrimaryButton", func() -> void: _to_menu()))
	for b in buttons:
		b.custom_minimum_size = Vector2(190, 50)
		foot.add_child(b)
	var ctrls: Array[Control] = []
	for b2 in buttons:
		ctrls.append(b2)
	UiKit.chain_horizontal(ctrls, true)
	foot.add_child(_hints)
	UiKit.focus.call_deferred(buttons[0])


func _banner() -> Control:
	var winner: int = int(result.get("winner_team", -1))
	var won: bool = my_team >= 0 and winner == my_team
	var h := UiKit.hbox(26)
	var head := UiKit.vbox(-8)
	var big: String
	if my_team < 0:
		big = ("%s wins" % UiKit.TEAM_NAMES[winner]) if winner >= 0 else "Match over"
	else:
		big = "Victory" if won else "Defeat"
	var t := UiKit.label(big.to_upper(), &"Hero")
	t.add_theme_font_size_override("font_size", 104)
	if my_team >= 0:
		t.add_theme_color_override("font_color", Color.WHITE if won else UiKit.TEXT_DIM)
	var ic := UiKit.icon("trophy" if won else ("cross" if my_team >= 0 else "flag"), 64.0, UiKit.GOLD if won else UiKit.TEXT_DIM)
	var hh := UiKit.hbox(18)
	hh.add_child(ic)
	hh.add_child(t)
	head.add_child(hh)
	var reason: String = String(REASONS.get(String(result.get("ended_reason", "")), String(result.get("ended_reason", "")).capitalize()))
	head.add_child(UiKit.label("TURF SHIFT · %s · BRIARPORT  —  %s" % [UiKit.mode_label(_mode()).to_upper(), reason.to_upper()], &"Caption"))
	h.add_child(head)
	h.add_child(UiKit.spacer())
	var sc: Array = result.get("score", [0, 0]) if result.get("score") is Array else [0, 0]
	var score := UiKit.hbox(18)
	score.add_child(_team_score(0, int(sc[0]) if sc.size() > 0 else 0, winner == 0))
	var dash := UiKit.label("–", &"StatLarge")
	dash.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	score.add_child(dash)
	score.add_child(_team_score(1, int(sc[1]) if sc.size() > 1 else 0, winner == 1))
	h.add_child(score)
	var meta := UiKit.vbox(6)
	meta.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	meta.add_child(UiKit.key_value("Duration", UiKit.fmt_duration(float(result.get("duration_s", 0.0)))))
	if bool(result.get("sudden_death", false)):
		meta.add_child(UiKit.chip("SUDDEN DEATH", UiKit.WARN, "hourglass"))
	h.add_child(meta)
	return h


func _relation(team: int) -> String:
	if my_team < 0:
		return "neutral"
	return "ally" if team == my_team else "enemy"


func _team_score(team: int, pts: int, winner: bool) -> VBoxContainer:
	var v := UiKit.vbox(-4)
	var col: Color = Settings.relation_color(_relation(team)) if my_team >= 0 else UiKit.TEXT
	var n := UiKit.label(str(pts), &"StatLarge")
	n.add_theme_font_size_override("font_size", 64)
	n.add_theme_color_override("font_color", col)
	n.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(n)
	var tag: String = UiKit.TEAM_NAMES[team].to_upper()
	if my_team >= 0:
		tag += "  ·  " + ("YOUR TEAM" if team == my_team else "OPPONENTS")
	var hl := UiKit.hbox(6)
	hl.alignment = BoxContainer.ALIGNMENT_CENTER
	if winner:
		hl.add_child(UiKit.icon("trophy", 14.0, UiKit.GOLD))
	hl.add_child(UiKit.label(tag, &"Caption"))
	v.add_child(hl)
	return v


func _rows_for(team: int) -> Array:
	var rows: Array = []
	for key in ["players", "bots"]:
		for r in result.get(key, []):
			var d: Dictionary = r
			if int(d.get("team", -1)) == team:
				rows.append(d)
	rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if int(a.get("control_seconds", 0)) != int(b.get("control_seconds", 0)):
			return int(a.get("control_seconds", 0)) > int(b.get("control_seconds", 0))
		return int(a.get("kos", 0)) > int(b.get("kos", 0)))
	return rows


func _team_table(team: int) -> PanelContainer:
	var p := UiKit.panel(&"PanelGlass")
	var sb: StyleBoxFlat = (p.get_theme_stylebox("panel") as StyleBoxFlat).duplicate()
	sb.border_width_left = 4
	sb.border_color = Settings.relation_color(_relation(team)) if my_team >= 0 else UiKit.LINE_BRIGHT
	p.add_theme_stylebox_override("panel", sb)
	var v := UiKit.vbox(6)
	p.add_child(v)
	var head := UiKit.hbox(10)
	var rel_shape: String = "circle" if _relation(team) == "ally" else ("diamond" if _relation(team) == "enemy" else "flag")
	head.add_child(UiKit.icon(rel_shape, 16.0, sb.border_color))
	head.add_child(UiKit.label("%s%s" % [UiKit.TEAM_NAMES[team].to_upper(), ("  —  YOUR TEAM" if team == my_team else ("  —  OPPONENTS" if my_team >= 0 else ""))], &"Subheading"))
	v.add_child(head)
	var g := UiKit.grid(7, 16, 5)
	v.add_child(g)
	var cols: Array = [["FIGHTER", 170], ["PLAYER", 220], ["KOS", 50], ["KO'D", 50], ["DAMAGE", 80], ["CONTROL", 80], ["", 150]]
	for c in cols:
		var l := UiKit.label(String(c[0]), &"Caption")
		l.custom_minimum_size = Vector2(float(c[1]), 0)
		g.add_child(l)
	var me: int = int(info.get("my_entity", -1))
	for r in _rows_for(team):
		var d: Dictionary = r
		var fh := UiKit.hbox(8)
		var e := FighterEmblem.new()
		e.fighter_id = String(d.get("fighter", ""))
		e.custom_minimum_size = Vector2(30, 30)
		fh.add_child(e)
		fh.add_child(UiKit.label(UiKit.fighter_name(String(d.get("fighter", "")))))
		g.add_child(fh)
		var nh := UiKit.hbox(8)
		var nm := UiKit.label(String(d.get("name", "")))
		nm.clip_text = true
		nm.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		nm.custom_minimum_size = Vector2(120, 0)
		nh.add_child(nm)
		if int(d.get("entity", -2)) == me:
			nh.add_child(UiKit.chip("YOU", UiKit.TEXT, "user"))
		g.add_child(nh)
		g.add_child(UiKit.label(str(int(d.get("kos", 0))), &"Stat"))
		g.add_child(UiKit.label(str(int(d.get("knocked_out", 0))), &"Stat"))
		g.add_child(UiKit.label(str(int(d.get("damage_dealt", 0))), &"Stat"))
		g.add_child(UiKit.label("%ds" % int(d.get("control_seconds", 0)), &"Stat"))
		var tags := UiKit.hbox(6)
		if bool(d.get("bot", false)):
			tags.add_child(UiKit.chip("BOT", UiKit.TEXT_DIM, "bot"))
		if bool(d.get("afk", false)):
			tags.add_child(UiKit.chip("AFK", UiKit.WARN, "warning"))
		if bool(d.get("abandoned", false)):
			tags.add_child(UiKit.chip("LEFT", UiKit.ERR, "exit"))
		g.add_child(tags)
	return p


# ------------------------------------------------------------------------------------------
# mastery
# ------------------------------------------------------------------------------------------
func _build_mastery() -> void:
	UiKit.clear_children(_mastery_box)
	_mastery_box.add_child(UiKit.label("MASTERY", &"Caption"))
	var fid: String = String(info.get("fighter", ""))
	var aw: Dictionary = info.get("awards", {}) if info.get("awards") is Dictionary else {}
	var mode: String = _mode()
	var head := UiKit.hbox(12)
	var e := FighterEmblem.new()
	e.fighter_id = fid
	e.custom_minimum_size = Vector2(56, 56)
	head.add_child(e)
	var hv := UiKit.vbox(-4)
	hv.add_child(UiKit.label(UiKit.fighter_name(fid).to_upper() if fid != "" else "—", &"Heading"))
	_level_label = UiKit.label("", &"Dim")
	hv.add_child(_level_label)
	head.add_child(hv)
	_mastery_box.add_child(head)
	if mode == "offline" and not aw.is_empty():
		var gained: int = int(aw.get("xp_gained", aw.get("xp", 0)))
		var lb: int = int(aw.get("level_before", 1))
		var la: int = int(aw.get("level_after", lb))
		var after_xp: int = Profile.fighter_xp(fid)
		var before_xp: int = maxi(0, after_xp - gained)
		var gl := UiKit.label("+%d XP" % gained, &"StatLarge")
		gl.add_theme_color_override("font_color", UiKit.GOLD)
		_mastery_box.add_child(gl)
		_xp_bar = UiKit.progress(_frac(before_xp), 1.0, &"XpBar")
		_xp_bar.custom_minimum_size = Vector2(0, 10)
		_mastery_box.add_child(_xp_bar)
		_xp_label = UiKit.label("", &"Small")
		_mastery_box.add_child(_xp_label)
		_level_label.text = "Mastery level %d" % lb
		_animate_xp(before_xp, after_xp, lb, la)
		var unlocks: Array = aw.get("unlocks", aw.get("unlocked", []))
		if not unlocks.is_empty():
			_mastery_box.add_child(UiKit.label("UNLOCKED", &"Caption"))
			for u in unlocks:
				_mastery_box.add_child(_unlock_row(u, fid))
		_mastery_box.add_child(UiKit.label("Offline progress. Online mastery is only granted by server-submitted results.", &"Small", true))
	elif mode == "training":
		_level_label.text = "Training"
		_mastery_box.add_child(UiKit.label("Training sessions do not change mastery.", &"Small", true))
	elif mode == "replay":
		_level_label.text = "Replay"
	else:
		_level_label.text = "Online match"
		var msg: String = "Mastery and rating for online matches are recorded by the service from the server's result."
		if not Online.is_logged_in():
			msg += " Sign in to see them here."
		_mastery_box.add_child(UiKit.label(msg, &"Small", true))


func _frac(xp: int) -> float:
	var lvl: int = Profile.level_for_xp(xp)
	if lvl >= Profile.LEVEL_XP.size():
		return 1.0
	var lo: int = Profile.LEVEL_XP[lvl - 1]
	var hi: int = Profile.LEVEL_XP[lvl]
	return float(xp - lo) / float(maxi(1, hi - lo))


func _xp_text(xp: int) -> String:
	var lvl: int = Profile.level_for_xp(xp)
	if lvl >= Profile.LEVEL_XP.size():
		return "Max level · %d XP" % xp
	return "%d / %d XP to level %d" % [xp - Profile.LEVEL_XP[lvl - 1], Profile.LEVEL_XP[lvl] - Profile.LEVEL_XP[lvl - 1], lvl + 1]


func _animate_xp(before_xp: int, after_xp: int, lb: int, la: int) -> void:
	_xp_label.text = _xp_text(before_xp)
	var step: Callable = func(x: float) -> void:
		var xi: int = int(round(x))
		_xp_bar.value = _frac(xi)
		_xp_label.text = _xp_text(xi)
		_level_label.text = "Mastery level %d" % Profile.level_for_xp(xi)
	var tw: Tween = create_tween()
	tw.tween_interval(0.5)
	tw.tween_method(step, float(before_xp), float(after_xp), 1.4)
	if la > lb:
		tw.tween_callback(func() -> void:
			UiKit.play("ui_notify")
			_level_label.text = "Mastery level %d — level up!" % la)


func _unlock_row(u: Variant, fid: String) -> HBoxContainer:
	var h := UiKit.hbox(10)
	var kind: String = "palette"
	var id: String = ""
	var f: String = fid
	if u is Dictionary:
		kind = String((u as Dictionary).get("kind", "palette"))
		id = String((u as Dictionary).get("id", ""))
		f = String((u as Dictionary).get("fighter", fid))
	else:
		id = String(u)
		kind = "badge" if id.contains("_") or id == "pack_debut" else "palette"
	if kind == "palette":
		var pi: Dictionary = UiKit.palette_info(f, id)
		for k in ["primary", "secondary", "accent"]:
			var c := ColorRect.new()
			c.color = pi[k]
			c.custom_minimum_size = Vector2(14, 14)
			c.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			h.add_child(c)
		h.add_child(UiKit.label("Palette: %s (%s)" % [String(pi["name"]), UiKit.fighter_name(f)]))
	else:
		h.add_child(UiKit.icon(UiKit.badge_icon_kind(id), 20.0, UiKit.GOLD))
		h.add_child(UiKit.label("Badge: %s" % UiKit.badge_display(id)))
	return h


func _fetch_online() -> void:
	## Server-submitted result → rating / mastery changes for this account (retries while the
	## game server is still submitting).
	var mid: String = String(result.get("match_id", ""))
	if mid == "" or not Online.is_logged_in():
		return
	while _online_tries < 5 and is_inside_tree():
		_online_tries += 1
		var r: Dictionary = await Online.match_get(mid)
		if not is_inside_tree():
			return
		if bool(r["ok"]) and r["data"] is Dictionary and (r["data"] as Dictionary).get("result") != null:
			_show_online(r["data"])
			return
		await get_tree().create_timer(2.0).timeout


func _show_online(d: Dictionary) -> void:
	var aid: String = String(Online.account.get("account_id", ""))
	var rc: Dictionary = (d.get("rating_changes", {}) as Dictionary).get(aid, {}) if d.get("rating_changes") is Dictionary else {}
	var mc: Dictionary = (d.get("mastery_changes", {}) as Dictionary).get(aid, {}) if d.get("mastery_changes") is Dictionary else {}
	if not mc.is_empty():
		var gl := UiKit.label("+%d XP" % int(mc.get("xp_gained", 0)), &"StatLarge")
		gl.add_theme_color_override("font_color", UiKit.GOLD)
		_mastery_box.add_child(gl)
		_level_label.text = "Online mastery level %d" % int(mc.get("level", 1))
		for b in mc.get("badges_unlocked", []):
			_mastery_box.add_child(_unlock_row({"kind": "badge", "id": String(b)}, String(mc.get("fighter", ""))))
	if not rc.is_empty():
		var before: float = float(rc.get("before", 0.0))
		var after: float = float(rc.get("after", 0.0))
		var h := UiKit.hbox(10)
		h.add_child(UiKit.label("RATING", &"Caption"))
		var l := UiKit.label("%d → %d (%+d)" % [int(round(before)), int(round(after)), int(round(after - before))], &"Stat")
		l.add_theme_color_override("font_color", UiKit.OK if after >= before else UiKit.ERR)
		h.add_child(l)
		_mastery_box.add_child(h)


func _play_again(params: Dictionary) -> void:
	var p: Dictionary = params.duplicate(true)
	p["seed"] = randi() % 1000000
	UiState.remember_match(p)
	UiKit.play("ui_lockin")
	Game.goto(Game.SCENE_MATCH, p)


func _to_menu() -> void:
	if Game.session != null:
		Game.end_online_session()
	Game.goto_menu()


func _input(event: InputEvent) -> void:
	UiHintBar.note_input(event)


func _unhandled_input(event: InputEvent) -> void:
	if get_viewport().gui_get_focus_owner() == null and not buttons.is_empty() and (event.is_action_pressed("ui_accept") \
			or event.is_action_pressed("ui_left") or event.is_action_pressed("ui_right") or event.is_action_pressed("ui_down")):
		get_viewport().set_input_as_handled()
		UiKit.focus(buttons[0])
