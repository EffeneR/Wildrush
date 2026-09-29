class_name OnlineLobby
extends Control
## Online lobby + character select (res://scenes/online_lobby.tscn, docs/UI_CONTRACT.md
## "Online lobby"), bound to Game.session (ClientSession). The server owns every decision:
## this screen only renders the lobby payload and sends requests (pick, lock, swap, ready,
## chat, rematch, admin commands). match_setup → SCENE_MATCH {"mode": "online"}.

enum Stage { LOBBY, SELECT, MATCH, RESULTS, CLOSING }

const ERRORS: Dictionary = {
	"taken": "A teammate already picked that fighter.", "locked": "You already locked in.",
	"not_selecting": "Character select is not running.", "no_pick": "Pick a fighter before locking in.",
	"target_locked": "That teammate already locked in.", "no_target": "Nobody is in that slot.",
	"no_request": "That swap request is no longer open.", "not_admin": "Only the lobby host can do that.",
	"team_full": "That team is full.", "not_all_ready": "Not every player is ready yet.",
	"wrong_stage": "Not possible at this stage.", "invalid": "That request was refused.",
	"unknown_player": "You are not a player in this lobby.", "unknown_cmd": "Unknown command.",
}
const FAIL_REASONS: Dictionary = {
	"bad_password": "Wrong lobby password.", "version_mismatch": "The server runs a different game version.",
	"match_in_progress": "A match is already running on this server.", "closing": "The server is shutting down this lobby.",
	"observers_disabled": "The host does not allow observers.", "observer_not_authorized": "Observing this server needs an invitation.",
	"ticket_expired": "Your join ticket expired — queue again.", "ticket_used": "That join ticket was already used.",
}

var session: ClientSession = null
var lobby: Dictionary = {}
var stage: int = -1
var me_pid: int = -1
var is_admin: bool = false
var observer: bool = false
var mode: String = ""
var select_left: float = 0.0
var preview_fid: String = ""
var chat_log: Array[String] = []
var _built_stage: int = -99
var _title: Label
var _subtitle: Label
var _status_chip: HBoxContainer
var _body: Control
var _chat_text: RichTextLabel
var _chat_edit: LineEdit
var _chat_team: UiToggle
var _timer_label: Label
var _preview: FighterPreview
var _kit: KitList
var _pname: Label
var _ptitle: Label
var _cards: Array[FighterCard] = []
var _lock_btn: Button
var _ready_btn: Button
var _hints: UiHintBar
var _last_chat_ms: int = -10000
var _modal_open: bool = false
var _leaving: bool = false
var _status: String = ""
var _status_detail: String = ""
var _left_col: VBoxContainer
var _right_col: VBoxContainer
var _right_dyn: VBoxContainer
var _chat_node: PanelContainer = null


func _ready() -> void:
	add_child(MenuBackground.new())
	_build_frame()
	UiKit.music("music_menu")
	get_viewport().gui_focus_changed.connect(func(_c: Control) -> void:
		if UiKit.focus_sound_allowed():
			UiKit.play("ui_hover"))
	bind_session(Game.session)


func bind_session(s: ClientSession) -> void:
	session = s
	if session == null:
		_status = "none"
		_render()
		return
	session.status_changed.connect(_on_status)
	session.welcomed.connect(_on_welcome)
	session.lobby_updated.connect(apply_lobby)
	session.match_setup_received.connect(_on_match_setup)
	session.chat_received.connect(_on_chat)
	session.server_notice.connect(_on_notice)
	session.results_received.connect(func(_r: Dictionary) -> void: _render())
	_status = session.status
	if not session.info.is_empty():
		_on_welcome(session.info)
	if not session.lobby.is_empty():
		apply_lobby(session.lobby)
	else:
		_render()


# ------------------------------------------------------------------------------------------
# frame
# ------------------------------------------------------------------------------------------
func _build_frame() -> void:
	var outer := UiKit.margin(48, 30, 48, 22)
	outer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	outer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(outer)
	var mw := MaxWidthContainer.new()
	mw.max_width = 2000.0
	mw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	outer.add_child(mw)
	var v := UiKit.vbox(12)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	mw.add_child(v)
	var top := UiKit.hbox(16)
	v.add_child(top)
	var tv := UiKit.vbox(-6)
	_title = UiKit.label("LOBBY", &"Title")
	tv.add_child(_title)
	_subtitle = UiKit.label("", &"Dim")
	tv.add_child(_subtitle)
	top.add_child(tv)
	top.add_child(UiKit.spacer())
	_status_chip = UiKit.hbox(8)
	top.add_child(_status_chip)
	var leave := UiKit.button("Leave", &"DangerButton", confirm_leave)
	leave.name = "LeaveLobby"
	top.add_child(leave)
	_body = Control.new()
	_body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_body.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(_body)
	var foot := UiKit.hbox(12)
	v.add_child(foot)
	foot.add_child(UiKit.label("%s · protocol %d" % [WR.BUILD_ID, WR.PROTOCOL_VERSION], &"Small"))
	foot.add_child(UiKit.spacer())
	_hints = UiHintBar.new()
	foot.add_child(_hints)


# ------------------------------------------------------------------------------------------
# session events
# ------------------------------------------------------------------------------------------
func _on_status(s: String, detail: String) -> void:
	_status = s
	_status_detail = detail
	if s == "failed" or s == "disconnected":
		UiKit.play("ui_error")
	_render()


func _on_welcome(d: Dictionary) -> void:
	me_pid = int(d.get("pid", me_pid))
	observer = bool(d.get("observer", false))
	is_admin = bool(d.get("admin", false))
	mode = String(d.get("mode", mode))
	_status = "connected"
	_render()


func apply_lobby(d: Dictionary) -> void:
	lobby = d
	var st: int = int(d.get("stage", 0))
	if st != stage and st == Stage.SELECT:
		UiKit.music("music_select")
		UiKit.play("ui_match_found")
	stage = st
	mode = String(d.get("mode", mode))
	is_admin = int(d.get("admin", -1)) == me_pid and me_pid >= 0
	select_left = float(d.get("select_left_s", 0.0))
	if session != null and not session.info.is_empty():
		me_pid = int(session.info.get("pid", me_pid))
	_render()


func _on_match_setup(_d: Dictionary) -> void:
	UiKit.play("ui_lockin")
	Game.goto(Game.SCENE_MATCH, {"mode": "online"})


func _on_chat(msg: Dictionary) -> void:
	var team: int = int(msg.get("team", -1))
	var my_team: int = _my_team()
	var rel: String = "neutral" if team < 0 or my_team < 0 else ("ally" if team == my_team else "enemy")
	var col: String = Settings.relation_color(rel).to_html(false) if rel != "neutral" else UiKit.TEXT_DIM.to_html(false)
	var prefix: String = "[TEAM] " if bool(msg.get("team_only", false)) else ""
	var line: String = "[color=#%s]%s%s[/color]: %s" % [col, prefix, _esc(String(msg.get("from", "?"))), _esc(String(msg.get("text", "")))]
	chat_log.append(line)
	while chat_log.size() > 80:
		chat_log.pop_front()
	UiKit.play("ui_chat")
	_refresh_chat()


func _on_notice(d: Dictionary) -> void:
	match String(d.get("t", "")):
		"error":
			var code: String = String(d.get("code", ""))
			UiToasts.notify(self, String(ERRORS.get(code, "Request refused (%s)." % code)), "error")
		"cancelled":
			_show_end("Match cancelled", "The match was cancelled: %s." % ("not enough players joined" if String(d.get("reason", "")) == "players_missing" else String(d.get("reason", "unknown reason"))))
		"kicked":
			_show_end("Removed from the lobby", "The server removed you (%s)." % ("inactivity" if String(d.get("reason", "")) == "afk" else String(d.get("reason", "host decision"))))
		"afk_warning":
			UiToasts.notify(self, "You will be removed for inactivity soon.", "warn")
		_:
			if d.has("msg"):
				UiToasts.notify(self, String(d["msg"]), "info")


func _show_end(title_text: String, msg: String) -> void:
	if _modal_open:
		return
	_modal_open = true
	var m := UiModal.open(self, title_text, msg, [["ok", "Back to menu", &"PrimaryButton"]], "ok")
	await m.chosen
	_modal_open = false
	_leave_now()


static func _esc(s: String) -> String:
	return s.replace("[", "[lb]")


# ------------------------------------------------------------------------------------------
# helpers over the payload
# ------------------------------------------------------------------------------------------
func teams() -> Array:
	var r: Dictionary = lobby.get("roster", {}) if lobby.get("roster") is Dictionary else {}
	var t: Array = r.get("teams", [[], []]) if r.get("teams") is Array else [[], []]
	while t.size() < 2:
		t.append([])
	return t


func me() -> Dictionary:
	for t in teams():
		for p in t:
			if int((p as Dictionary).get("pid", -1)) == me_pid:
				return p
	return {}


func _my_team() -> int:
	var tl: Array = teams()
	for i in range(tl.size()):
		for p in tl[i]:
			if int((p as Dictionary).get("pid", -1)) == me_pid:
				return i
	return -1


func _swaps() -> Array:
	var r: Dictionary = lobby.get("roster", {}) if lobby.get("roster") is Dictionary else {}
	return r.get("swaps", []) if r.get("swaps") is Array else []


func _request(d: Dictionary) -> void:
	if session != null:
		session.request(d)


# ------------------------------------------------------------------------------------------
# rendering
# ------------------------------------------------------------------------------------------
func _render() -> void:
	_update_header()
	var key: int = stage if (_status == "connected" and not lobby.is_empty()) else -10 - ["none", "idle", "connecting", "failed", "disconnected", "connected"].find(_status)
	var fo: Control = get_viewport().gui_get_focus_owner()
	var fo_name: String = String(fo.name) if fo != null and _body.is_ancestor_of(fo) else ""
	if key != _built_stage:
		_built_stage = key
		if _chat_node != null and _chat_node.get_parent() != null:
			_chat_node.get_parent().remove_child(_chat_node)   # keep chat (and typed text) across stages
		UiKit.clear_children(_body)
		_cards.clear()
		_chat_text = null
		match key:
			Stage.LOBBY: _build_lobby()
			Stage.SELECT: _build_select()
			Stage.MATCH: _build_message("swords", "Match starting", "Loading Briarport…", false)
			Stage.RESULTS: _build_results()
			Stage.CLOSING: _build_message("exit", "Lobby closing", "The server is closing this lobby.", true)
			_: _build_connection()
		fo_name = ""
	else:
		_update_dynamic()
	_restore_focus.call_deferred(fo_name)


func _restore_focus(fo_name: String) -> void:
	if _modal_open or not is_inside_tree():
		return
	var cur: Control = get_viewport().gui_get_focus_owner()
	if cur != null and cur.is_visible_in_tree() and is_ancestor_of(cur):
		return
	var t: Control = null
	if fo_name != "":
		t = _body.find_child(fo_name, true, false) as Control
	if t == null or not t.is_visible_in_tree():
		t = _default_focus()
	if t != null:
		UiKit.focus(t)


func _default_focus() -> Control:
	if stage == Stage.SELECT and not _cards.is_empty():
		for c in _cards:
			if c.fighter_id == String(me().get("fighter", "")):
				return c
		for c2 in _cards:
			if not c2.disabled:
				return c2
	if _ready_btn != null and is_instance_valid(_ready_btn) and _ready_btn.is_visible_in_tree():
		return _ready_btn
	return UiKit.first_focusable(_body) if UiKit.first_focusable(_body) != null else UiKit.first_focusable(self)


func _update_header() -> void:
	var host: String = "%s:%d" % [session.host, session.port] if session != null else ""
	var m: String = UiKit.mode_label(mode) if mode != "" else "Online"
	_title.text = ("PRIVATE LOBBY" if mode == "private" else "%s MATCH" % m.to_upper()) if stage != Stage.SELECT else "CHARACTER SELECT"
	var parts: PackedStringArray = PackedStringArray()
	if host != "":
		parts.append(host)
	parts.append(m)
	if UiState.private_join_code != "" and mode == "private":
		parts.append("Join code " + UiState.private_join_code)
	if observer:
		parts.append("Observing")
	_subtitle.text = "  ·  ".join(parts)
	UiKit.clear_children(_status_chip)
	var col: Color = UiKit.TEXT_DIM
	var ic: String = "wifi"
	var txt: String = _status.to_upper()
	match _status:
		"connected":
			col = UiKit.OK
			txt = "CONNECTED"
		"connecting":
			col = UiKit.WARN
			ic = "hourglass"
			txt = "CONNECTING"
		"failed", "disconnected", "none", "idle":
			col = UiKit.ERR
			ic = "wifi_off"
			txt = "NOT CONNECTED"
	_status_chip.add_child(UiKit.chip(txt, col, ic))
	var h: Array = [["accept", "Select"], ["back", "Leave"]]
	if stage == Stage.SELECT:
		h = [["accept", "Pick"], ["alt", "Lock in"], ["back", "Leave"]]
	_hints.set_hints(h)


func _build_message(icon_kind: String, head: String, text: String, with_leave: bool) -> void:
	var c := CenterContainer.new()
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_body.add_child(c)
	var v := UiKit.vbox(14)
	c.add_child(v)
	var h := UiKit.hbox(16)
	h.add_child(UiKit.icon(icon_kind, 44.0, UiKit.TEXT_DIM))
	var tv := UiKit.vbox(2)
	tv.add_child(UiKit.label(head.to_upper(), &"Title"))
	var l := UiKit.label(text, &"Dim", true)
	l.custom_minimum_size = Vector2(520, 0)
	tv.add_child(l)
	h.add_child(tv)
	v.add_child(h)
	if with_leave:
		var b := UiKit.button("Back to menu", &"PrimaryButton", _leave_now)
		b.name = "BackToMenu"
		b.size_flags_horizontal = Control.SIZE_SHRINK_END
		v.add_child(b)


func _build_connection() -> void:
	match _status:
		"none":
			_build_message("wifi_off", "Not connected", "There is no online session. Join a match from Play online.", true)
		"connecting", "connected":
			_build_message("hourglass", "Connecting", "Contacting %s:%d and verifying your ticket…" % [session.host, session.port] if session != null else "Connecting…", false)
		"failed":
			var why: String = String(FAIL_REASONS.get(_status_detail, _status_detail if _status_detail != "" else "The server did not accept the connection."))
			_build_message("error", "Connection failed", why, true)
		"disconnected":
			_build_message("wifi_off", "Disconnected", "The connection to the server was lost.", true)
		_:
			_build_message("wifi_off", "Not connected", "The online session ended.", true)


# ------------------------------------------------------------------------------------------
# LOBBY stage
# ------------------------------------------------------------------------------------------
func _build_lobby() -> void:
	var h := UiKit.hbox(18)
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_body.add_child(h)
	_left_col = UiKit.vbox(10)
	_left_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_left_col.size_flags_stretch_ratio = 2.0
	h.add_child(_left_col)
	_right_col = UiKit.vbox(10)
	_right_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_right_col.custom_minimum_size = Vector2(420, 0)
	h.add_child(_right_col)
	_right_dyn = UiKit.vbox(10)
	_right_col.add_child(_right_dyn)
	_right_col.add_child(_chat_panel())
	_fill_lobby_left()
	_fill_lobby_right()


func _fill_lobby_left() -> void:
	UiKit.clear_children(_left_col)
	var row := UiKit.hbox(14)
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_left_col.add_child(row)
	var tl: Array = teams()
	for t in range(2):
		row.add_child(_team_column(t, tl[t] as Array))
	var exp_n: int = int(lobby.get("expected", 0))
	var humans: int = 0
	for t2 in tl:
		for p in t2:
			if not bool((p as Dictionary).get("bot", false)):
				humans += 1
	var info_row := UiKit.hbox(12)
	info_row.add_child(UiKit.icon("users", 18.0, UiKit.TEXT_DIM))
	if mode == "private":
		info_row.add_child(UiKit.label("%d player%s in the lobby. The host assigns teams and starts the match." % [humans, "" if humans == 1 else "s"], &"Small"))
	else:
		info_row.add_child(UiKit.label("Waiting for players: %d / %d joined. Character select starts when everyone is here." % [humans, exp_n], &"Small"))
	_left_col.add_child(info_row)


func _team_column(team: int, players: Array) -> PanelContainer:
	var p := UiKit.panel(&"PanelGlass")
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var my_team: int = _my_team()
	var rel: String = "neutral" if my_team < 0 else ("ally" if team == my_team else "enemy")
	var sb: StyleBoxFlat = (p.get_theme_stylebox("panel") as StyleBoxFlat).duplicate()
	sb.border_width_top = 3
	sb.border_color = Settings.relation_color(rel) if rel != "neutral" else UiKit.LINE_BRIGHT
	p.add_theme_stylebox_override("panel", sb)
	var v := UiKit.vbox(8)
	p.add_child(v)
	var head := UiKit.hbox(10)
	head.add_child(UiKit.icon("circle" if rel == "ally" else ("diamond" if rel == "enemy" else "flag"), 16.0, sb.border_color))
	head.add_child(UiKit.label("TEAM %s" % UiKit.TEAM_NAMES[team].to_upper(), &"Heading"))
	if rel != "neutral":
		head.add_child(UiKit.label("YOUR TEAM" if rel == "ally" else "OPPONENTS", &"Caption"))
	v.add_child(head)
	var by_slot: Dictionary = {}
	for pl in players:
		by_slot[int((pl as Dictionary).get("slot", 0))] = pl
	for s in range(WR.TEAM_SIZE):
		if by_slot.has(s):
			v.add_child(_player_row(by_slot[s] as Dictionary, team))
		else:
			var e := UiKit.hbox(10)
			e.custom_minimum_size = Vector2(0, 44)
			e.add_child(UiKit.icon("user", 20.0, UiKit.LINE_BRIGHT))
			var r: Dictionary = lobby.get("roster", {}) if lobby.get("roster") is Dictionary else {}
			e.add_child(UiKit.label("Open slot" + (" — a bot fills it at character select" if bool(r.get("allow_bots", false)) else ""), &"Small"))
			v.add_child(e)
	return p


func _player_row(p: Dictionary, team: int) -> HBoxContainer:
	var h := UiKit.hbox(8)
	h.custom_minimum_size = Vector2(0, 44)
	var pid: int = int(p.get("pid", -1))
	var bot: bool = bool(p.get("bot", false))
	var admin: bool = pid == int(lobby.get("admin", -2))
	h.add_child(UiKit.icon("crown" if admin else ("bot" if bot else "user"), 20.0, UiKit.GOLD if admin else UiKit.TEXT_DIM))
	var n := UiKit.label(String(p.get("name", "?")))
	n.clip_text = true
	n.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	n.custom_minimum_size = Vector2(90, 0)
	n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if pid == me_pid:
		n.add_theme_color_override("font_color", Color.WHITE)
	h.add_child(n)
	if pid == me_pid:
		h.add_child(UiKit.chip("YOU", UiKit.TEXT, "user"))
	if bot:
		h.add_child(UiKit.chip("BOT", UiKit.TEXT_DIM, "bot"))
	elif not bool(p.get("connected", true)):
		h.add_child(UiKit.chip("OFFLINE", UiKit.ERR, "wifi_off"))
	elif bool(p.get("ready", false)):
		h.add_child(UiKit.chip("READY", UiKit.OK, "check"))
	else:
		h.add_child(UiKit.chip("NOT READY", UiKit.TEXT_FAINT, "clock"))
	if is_admin and mode == "private" and pid != me_pid and not bot:
		var mv := UiKit.button("Move", &"SmallButton", func() -> void: _request({"t": "admin", "cmd": "set_team", "args": {"pid": pid, "team": 1 - team}}))
		mv.name = "Move_%d" % pid
		mv.tooltip_text = "Move to team %s" % UiKit.TEAM_NAMES[1 - team]
		h.add_child(mv)
		var kk := UiKit.button("Kick", &"SmallButton", func() -> void: _confirm_kick(pid, String(p.get("name", "?"))))
		kk.name = "Kick_%d" % pid
		h.add_child(kk)
	elif is_admin and mode == "private" and pid == me_pid:
		var mv2 := UiKit.button("Switch team", &"SmallButton", func() -> void: _request({"t": "admin", "cmd": "set_team", "args": {"pid": pid, "team": 1 - team}}))
		mv2.name = "Move_%d" % pid
		h.add_child(mv2)
	return h


func _fill_lobby_right() -> void:
	UiKit.clear_children(_right_dyn)
	var r: Dictionary = lobby.get("roster", {}) if lobby.get("roster") is Dictionary else {}
	var p := UiKit.panel(&"PanelGlass")
	_right_dyn.add_child(p)
	var v := UiKit.vbox(10)
	p.add_child(v)
	if observer:
		v.add_child(UiKit.label("OBSERVER", &"Heading"))
		v.add_child(UiKit.label("You are watching this lobby. Observers see the match but cannot join a team.", &"Small", true))
	else:
		var mep: Dictionary = me()
		var ready: bool = bool(mep.get("ready", false))
		_ready_btn = UiKit.button("Ready" if not ready else "Ready — click to cancel", &"PrimaryButton" if not ready else &"", func() -> void:
			UiKit.play("ui_ready")
			_request({"t": "ready", "v": not bool(me().get("ready", false))}))
		_ready_btn.name = "ReadyButton"
		_ready_btn.custom_minimum_size = Vector2(0, 50)
		v.add_child(_ready_btn)
	if mode == "private" and is_admin:
		v.add_child(UiKit.label("LOBBY SETTINGS", &"Caption"))
		var bots := UiToggle.new("Fill empty slots with bots", "switch", bool(r.get("allow_bots", false)))
		bots.name = "AllowBots"
		bots.toggled.connect(func(on: bool) -> void:
			_request({"t": "admin", "cmd": "bots", "args": {"enabled": on, "difficulty": String(r.get("bot_difficulty", "normal"))}}))
		v.add_child(bots)
		var diffs: Array = [["easy", "Bots: Easy"], ["normal", "Bots: Normal"], ["hard", "Bots: Hard"]]
		var dc := UiCycler.new(diffs, 1)
		dc.name = "BotDifficulty"
		dc.select_value(String(r.get("bot_difficulty", "normal")))
		dc.value_changed.connect(func(_i: int, val: Variant) -> void:
			_request({"t": "admin", "cmd": "bots", "args": {"enabled": bool(r.get("allow_bots", false)), "difficulty": String(val)}}))
		v.add_child(dc)
		var obs := UiToggle.new("Allow observers", "switch", bool(lobby.get("observers_allowed", true)))
		obs.name = "AllowObservers"
		obs.toggled.connect(func(on: bool) -> void: _request({"t": "admin", "cmd": "observers", "args": {"allowed": on}}))
		v.add_child(obs)
		var start := UiKit.button("Start match", &"PrimaryButton", _admin_start)
		start.name = "StartMatch"
		start.custom_minimum_size = Vector2(0, 50)
		v.add_child(start)
	elif mode == "private":
		v.add_child(UiKit.label("The host starts the match when everyone is ready.", &"Small", true))
		var bl: String = ("Bots fill empty slots (%s)." % String(r.get("bot_difficulty", "normal"))) if bool(r.get("allow_bots", false)) else "No bots: empty slots stay empty."
		v.add_child(UiKit.label(bl, &"Small", true))


func _chat_panel() -> PanelContainer:
	if _chat_node != null:
		if _chat_node.get_parent() != null:
			_chat_node.get_parent().remove_child(_chat_node)
		return _chat_node
	var p := UiKit.panel(&"PanelDark")
	_chat_node = p
	p.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var v := UiKit.vbox(8)
	p.add_child(v)
	var hh := UiKit.hbox(8)
	hh.add_child(UiKit.icon("chat", 18.0, UiKit.TEXT_DIM))
	hh.add_child(UiKit.label("CHAT", &"Caption"))
	v.add_child(hh)
	_chat_text = RichTextLabel.new()
	_chat_text.bbcode_enabled = true
	_chat_text.scroll_following = true
	_chat_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_chat_text.custom_minimum_size = Vector2(0, 120)
	_chat_text.focus_mode = Control.FOCUS_NONE
	v.add_child(_chat_text)
	var row := UiKit.hbox(8)
	_chat_edit = UiKit.line_edit("Message (Enter to send)", 120)
	_chat_edit.name = "ChatInput"
	_chat_edit.select_all_on_focus = false
	_chat_edit.text_submitted.connect(func(_t: String) -> void: _send_chat())
	row.add_child(_chat_edit)
	_chat_team = UiToggle.new("Team", "check")
	_chat_team.name = "ChatTeamOnly"
	_chat_team.tooltip_text = "Only your team sees the message."
	row.add_child(_chat_team)
	v.add_child(row)
	_refresh_chat()
	return p


func _refresh_chat() -> void:
	if _chat_text == null or not is_instance_valid(_chat_text):
		return
	_chat_text.text = "\n".join(chat_log) if not chat_log.is_empty() else "[color=#%s]No messages yet.[/color]" % UiKit.TEXT_FAINT.to_html(false)


func _send_chat() -> void:
	var t: String = _chat_edit.text.strip_edges()
	if t == "":
		return
	var now: int = Time.get_ticks_msec()
	if now - _last_chat_ms < 1000:
		UiToasts.notify(self, "One message per second.", "warn")
		return
	_last_chat_ms = now
	_request({"t": "chat", "text": t.substr(0, 120), "team": _chat_team.button_pressed})
	_chat_edit.text = ""


func _confirm_kick(pid: int, pname: String) -> void:
	_modal_open = true
	var m := UiModal.open(self, "Kick %s?" % pname, "They are removed from this lobby.", [["kick", "Kick", &"DangerButton"], ["cancel", "Cancel", &""]], "cancel", "cancel")
	var id: String = await m.chosen
	_modal_open = false
	if id == "kick":
		_request({"t": "admin", "cmd": "kick", "args": {"pid": pid}})


func _admin_start() -> void:
	var all_ready: bool = true
	for t in teams():
		for p in t:
			var d: Dictionary = p
			if not bool(d.get("bot", false)) and bool(d.get("connected", true)) and not bool(d.get("ready", false)):
				all_ready = false
	if all_ready:
		_request({"t": "admin", "cmd": "start", "args": {"force": false}})
		return
	_modal_open = true
	var m := UiModal.open(self, "Start without everyone ready?", "Some players have not readied up.", [["start", "Start anyway", &"PrimaryButton"], ["cancel", "Wait", &""]], "cancel", "cancel")
	var id: String = await m.chosen
	_modal_open = false
	if id == "start":
		_request({"t": "admin", "cmd": "start", "args": {"force": true}})


# ------------------------------------------------------------------------------------------
# SELECT stage (character select)
# ------------------------------------------------------------------------------------------
func _build_select() -> void:
	var root := UiKit.hbox(18)
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_body.add_child(root)
	_left_col = UiKit.vbox(10)
	_left_col.custom_minimum_size = Vector2(380, 0)
	root.add_child(_left_col)
	var center := UiKit.vbox(8)
	center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_child(center)
	var th := UiKit.hbox(12)
	th.alignment = BoxContainer.ALIGNMENT_CENTER
	th.add_child(UiKit.icon("clock", 26.0, UiKit.GOLD))
	_timer_label = UiKit.label(UiKit.fmt_clock(select_left), &"StatLarge")
	th.add_child(_timer_label)
	th.add_child(UiKit.label("TO LOCK IN", &"Caption"))
	center.add_child(th)
	var pv := Control.new()
	pv.size_flags_vertical = Control.SIZE_EXPAND_FILL
	pv.mouse_filter = Control.MOUSE_FILTER_IGNORE
	center.add_child(pv)
	_preview = FighterPreview.new()
	_preview.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pv.add_child(_preview)
	var nm := UiKit.hbox(12)
	nm.alignment = BoxContainer.ALIGNMENT_CENTER
	_pname = UiKit.label("", &"Title")
	nm.add_child(_pname)
	_ptitle = UiKit.label("", &"Subheading")
	_ptitle.add_theme_color_override("font_color", UiKit.ACCENT_BRIGHT)
	_ptitle.size_flags_vertical = Control.SIZE_SHRINK_END
	nm.add_child(_ptitle)
	center.add_child(nm)
	var cards := UiKit.hbox(8)
	cards.alignment = BoxContainer.ALIGNMENT_CENTER
	center.add_child(cards)
	for fid in WR.FIGHTER_IDS:
		var c := FighterCard.new(fid, true)
		c.custom_minimum_size = Vector2(112, 146)
		c.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		c.name = "Pick_" + fid
		var f: String = fid
		c.pressed.connect(func() -> void: _pick(f))
		c.focus_entered.connect(func() -> void: _show_preview(f))
		cards.add_child(c)
		_cards.append(c)
	var lr := UiKit.hbox(12)
	lr.alignment = BoxContainer.ALIGNMENT_CENTER
	_lock_btn = UiKit.button("Lock in", &"PrimaryButton", _lock)
	_lock_btn.name = "LockIn"
	_lock_btn.custom_minimum_size = Vector2(300, 52)
	lr.add_child(_lock_btn)
	center.add_child(lr)
	var cc: Array[Control] = []
	for c2 in _cards:
		cc.append(c2)
	UiKit.chain_horizontal(cc, false)
	for c3 in _cards:
		c3.focus_neighbor_bottom = c3.get_path_to(_lock_btn)
	_lock_btn.focus_neighbor_top = _lock_btn.get_path_to(_cards[2])
	_right_col = UiKit.vbox(10)
	_right_col.custom_minimum_size = Vector2(400, 0)
	root.add_child(_right_col)
	_right_dyn = UiKit.vbox(10)
	_right_col.add_child(_right_dyn)
	var kp := UiKit.panel(&"PanelGlass")
	_kit = KitList.new(true)
	kp.add_child(_kit)
	_right_col.add_child(kp)
	_right_col.add_child(_chat_panel())
	_update_dynamic()


func _select_rows(team: int, box: VBoxContainer) -> void:
	UiKit.clear_children(box)
	var my_team: int = _my_team()
	var rel: String = "neutral" if my_team < 0 else ("ally" if team == my_team else "enemy")
	var head := UiKit.hbox(10)
	head.add_child(UiKit.icon("circle" if rel == "ally" else ("diamond" if rel == "enemy" else "flag"), 16.0,
		Settings.relation_color(rel) if rel != "neutral" else UiKit.TEXT_DIM))
	head.add_child(UiKit.label(("YOUR TEAM" if rel == "ally" else "TEAM %s" % UiKit.TEAM_NAMES[team].to_upper()), &"Subheading"))
	box.add_child(head)
	var players: Array = teams()[team]
	var mine: Dictionary = me()
	var swaps: Array = _swaps()
	for p in players:
		var d: Dictionary = p
		var pid: int = int(d.get("pid", -1))
		var fid: String = String(d.get("fighter", ""))
		var row := UiKit.panel(&"Card")
		var h := UiKit.hbox(10)
		row.add_child(h)
		var e := FighterEmblem.new()
		e.fighter_id = fid
		e.custom_minimum_size = Vector2(40, 40)
		e.dimmed = fid == ""
		h.add_child(e)
		var tv := UiKit.vbox(-3)
		tv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var n := UiKit.label(String(d.get("name", "?")))
		n.clip_text = true
		n.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		n.custom_minimum_size = Vector2(80, 0)
		tv.add_child(n)
		tv.add_child(UiKit.label(UiKit.fighter_name(fid).to_upper() if fid != "" else "CHOOSING…", &"Caption"))
		h.add_child(tv)
		if pid == me_pid:
			h.add_child(UiKit.chip("YOU", UiKit.TEXT, "user"))
		if bool(d.get("bot", false)):
			h.add_child(UiKit.chip("BOT", UiKit.TEXT_DIM, "bot"))
		elif bool(d.get("locked", false)):
			h.add_child(UiKit.chip("LOCKED", UiKit.OK, "check"))
		else:
			h.add_child(UiKit.chip("PICKING", UiKit.TEXT_FAINT, "clock"))
		# swaps: only between un-locked teammates, before lock-in (server validates)
		if rel == "ally" and pid != me_pid and not bool(d.get("bot", false)) and not bool(d.get("locked", false)) \
				and not mine.is_empty() and not bool(mine.get("locked", false)) and fid != "":
			var slot: int = int(d.get("slot", 0))
			var asked: bool = false
			for s in swaps:
				if int(s[0]) == me_pid and int(s[1]) == pid:
					asked = true
			var sb := UiKit.button("Asked" if asked else "Swap", &"SmallButton", func() -> void:
				_request({"t": "swap_req", "slot": slot})
				UiToasts.notify(self, "Swap request sent.", "info"))
			sb.name = "Swap_%d" % pid
			sb.disabled = asked
			h.add_child(sb)
		for s2 in swaps:
			if int(s2[1]) == me_pid and int(s2[0]) == pid:
				var from_pid: int = pid
				var ab := UiKit.button("Accept swap", &"PrimaryButton", func() -> void: _request({"t": "swap_answer", "from": from_pid, "accept": true}))
				ab.name = "AcceptSwap_%d" % pid
				h.add_child(ab)
				var db := UiKit.button("Decline", &"SmallButton", func() -> void: _request({"t": "swap_answer", "from": from_pid, "accept": false}))
				db.name = "DeclineSwap_%d" % pid
				h.add_child(db)
		box.add_child(row)


func _update_dynamic() -> void:
	## Refresh the parts of the current stage that change with every lobby broadcast.
	if stage == Stage.LOBBY and _left_col != null and is_instance_valid(_left_col):
		_fill_lobby_left()
		_fill_lobby_right()
		return
	if stage != Stage.SELECT or _cards.is_empty():
		return
	var my_team: int = _my_team()
	_select_rows(my_team if my_team >= 0 else 0, _left_col)
	_select_rows(1 - my_team if my_team >= 0 else 1, _right_dyn)
	var mine: Dictionary = me()
	var my_fid: String = String(mine.get("fighter", ""))
	var locked: bool = bool(mine.get("locked", false))
	var taken: Dictionary = {}
	if my_team >= 0:
		for p in teams()[my_team]:
			var d: Dictionary = p
			if int(d.get("pid", -1)) != me_pid and String(d.get("fighter", "")) != "":
				taken[String(d["fighter"])] = String(d.get("name", "?"))
	for c in _cards:
		c.set_level(Profile.fighter_level(c.fighter_id))
		if taken.has(c.fighter_id):
			c.set_pressed_no_signal(false)
			c.set_state("taken", "TAKEN · %s" % String(taken[c.fighter_id]).to_upper())
		elif c.fighter_id == my_fid:
			c.set_pressed_no_signal(true)
			c.set_state("locked" if locked else "yours")
		else:
			c.set_pressed_no_signal(false)
			c.set_state("")
		if locked or observer:
			c.disabled = true
	_lock_btn.disabled = locked or my_fid == "" or observer
	_lock_btn.text = "LOCKED IN" if locked else "LOCK IN"
	_lock_btn.visible = not observer
	_show_preview(preview_fid if preview_fid != "" else (my_fid if my_fid != "" else WR.FIGHTER_IDS[0]))


func _show_preview(fid: String) -> void:
	if _preview == null or not is_instance_valid(_preview):
		return
	var d: FighterDef = UiKit.fighter_def(fid)
	if d == null:
		return
	_pname.text = d.display_name
	_ptitle.text = d.title.to_upper()
	if _kit != null and is_instance_valid(_kit):
		_kit.show_fighter(fid)
	if _preview.fighter_id != fid or _preview.stage == null or _preview.stage.view == null:
		_preview.show_fighter(fid, Profile.selected_palette(fid), "select")


func _pick(fid: String) -> void:
	preview_fid = fid
	UiKit.play("ui_select")
	_request({"t": "pick", "f": fid})


func _lock() -> void:
	if String(me().get("fighter", "")) == "":
		UiToasts.notify(self, String(ERRORS["no_pick"]), "error")
		return
	UiKit.play("ui_lockin")
	_request({"t": "lock"})


# ------------------------------------------------------------------------------------------
# RESULTS stage (server lobby between matches)
# ------------------------------------------------------------------------------------------
func _build_results() -> void:
	var c := CenterContainer.new()
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_body.add_child(c)
	var v := UiKit.vbox(14)
	c.add_child(v)
	v.add_child(UiKit.label("MATCH FINISHED", &"Title"))
	v.add_child(UiKit.label("The server returns to the lobby automatically.", &"Dim"))
	var row := UiKit.hbox(10)
	if mode == "private" and not observer:
		var rm := UiKit.button("Vote rematch", &"PrimaryButton", func() -> void:
			UiKit.play("ui_ready")
			_request({"t": "rematch", "v": true}))
		rm.name = "Rematch"
		row.add_child(rm)
	if is_admin:
		var rl := UiKit.button("Return to lobby now", &"", func() -> void: _request({"t": "admin", "cmd": "return_lobby", "args": {}}))
		rl.name = "ReturnLobby"
		row.add_child(rl)
	var res := UiKit.button("View results", &"", func() -> void:
		if not Game.last_result.is_empty():
			Game.goto(Game.SCENE_RESULTS, {}))
	res.name = "ViewResults"
	res.visible = not Game.last_result.is_empty()
	row.add_child(res)
	v.add_child(row)


func _process(delta: float) -> void:
	if stage == Stage.SELECT and _timer_label != null and is_instance_valid(_timer_label):
		select_left = maxf(0.0, select_left - delta)
		_timer_label.text = UiKit.fmt_clock(select_left)
		_timer_label.add_theme_color_override("font_color", UiKit.ERR if select_left <= 10.0 else UiKit.TEXT)


# ------------------------------------------------------------------------------------------
# leaving / input
# ------------------------------------------------------------------------------------------
func confirm_leave() -> void:
	if _modal_open or _leaving:
		return
	if _status != "connected":
		_leave_now()
		return
	_modal_open = true
	var ranked: bool = mode == "ranked"
	var msg: String = "Leaving a ranked match after it formed counts as a loss." if ranked else "You leave this lobby and return to the menu."
	var m := UiModal.open(self, "Leave the lobby?", msg, [["leave", "Leave", &"DangerButton"], ["cancel", "Stay", &""]], "cancel", "cancel")
	var id: String = await m.chosen
	_modal_open = false
	if id == "leave":
		_leave_now()


func _leave_now() -> void:
	if _leaving:
		return
	_leaving = true
	UiState.private_join_code = ""
	Game.end_online_session()
	Game.goto_menu({"screen": "online"})


func _input(event: InputEvent) -> void:
	UiHintBar.note_input(event)
	if _modal_open:
		return
	if stage == Stage.SELECT and _lock_btn != null and is_instance_valid(_lock_btn) and not _lock_btn.disabled:
		var fo: Control = get_viewport().gui_get_focus_owner()
		var alt: bool = (event is InputEventJoypadButton and (event as InputEventJoypadButton).pressed and (event as InputEventJoypadButton).button_index == JOY_BUTTON_X) \
			or (event is InputEventKey and (event as InputEventKey).pressed and not (event as InputEventKey).echo and (event as InputEventKey).keycode == KEY_SPACE and not (fo is LineEdit))
		if alt:
			get_viewport().set_input_as_handled()
			_lock()


func _unhandled_input(event: InputEvent) -> void:
	if _modal_open:
		return
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		var fo: Control = get_viewport().gui_get_focus_owner()
		if fo is LineEdit:
			fo.release_focus()
			_restore_focus("")
			return
		confirm_leave()
		return
	if get_viewport().gui_get_focus_owner() == null and (event.is_action_pressed("ui_down") or event.is_action_pressed("ui_up") \
			or event.is_action_pressed("ui_accept") or event.is_action_pressed("ui_left") or event.is_action_pressed("ui_right")):
		get_viewport().set_input_as_handled()
		_restore_focus("")
