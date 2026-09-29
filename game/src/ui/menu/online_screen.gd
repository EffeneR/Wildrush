class_name OnlineScreen
extends MenuScreen
## Online hub (docs/UI_CONTRACT.md §4): account (register / sign in / sign out, HTTPS policy),
## party (create, invite by username, accept/decline, leave, kick, promote), queue (casual /
## ranked, party rules, timer, real queue counts, cancel, match found → join), private match
## (service create / join code) and direct connect, server browser. Polls at most once per
## second while visible and honours 429 Retry-After (via the Online autoload).

const TAB_IDS: Array[String] = ["account", "party", "play", "private", "servers"]
const TAB_TITLES: Array[String] = ["Account", "Party", "Play", "Private & direct", "Servers"]
const AUTO_JOIN_S: float = 10.0

var tabs: UiTabs
var poll_enabled: bool = true
var party: Dictionary = {}          # GET /v1/parties/current ({} = no party)
var incoming: Array = []            # GET /v1/invites
var queue: Dictionary = {}          # GET /v1/queue/status
var servers: Array = []             # GET /v1/servers
var profile_online: Dictionary = {}
var servers_error: String = ""
var busy: bool = false
var inline_error: String = ""
var _body: VBoxContainer
var _scroll: ScrollContainer
var _poll: Timer
var _poll_n: int = 0
var _q_in_flight: bool = false
var _p_in_flight: bool = false
var _queued_since_ms: int = 0
var _queued_base_s: float = 0.0
var _timer_label: Label = null
var _found_left: float = -1.0
var _found_bar: ProgressBar = null
var _joining: bool = false
var _was_matched: bool = false
var _queue_mode: String = "casual"
var _pref_fighter: String = ""
var _selected_server: int = -1
var _focus_after_build: String = ""


func build() -> void:
	title = "Play online"
	var v := UiKit.vbox(12)
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(v)
	tabs = UiTabs.new()
	for t in TAB_TITLES:
		tabs.add_tab(t)
	tabs.tab_changed.connect(func(i: int) -> void:
		UiState.online_tab = i
		_rebuild(true))
	v.add_child(tabs)
	var panel := UiKit.panel(&"PanelGlass")
	panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(panel)
	_body = UiKit.vbox(14)
	var m := UiKit.margin(2, 2, 16, 2)
	m.add_child(_body)
	_scroll = UiKit.scroll(m)
	panel.add_child(_scroll)
	_poll = Timer.new()
	_poll.wait_time = 1.0
	_poll.timeout.connect(_on_poll)
	add_child(_poll)
	Online.auth_changed.connect(_on_auth_changed)
	_queue_mode = UiState.queue_mode


func enter(params: Dictionary) -> void:
	if params.has("tab"):
		UiState.online_tab = maxi(0, TAB_IDS.find(String(params["tab"])))
	tabs.select(UiState.online_tab, false)
	_update_subtitle()
	_rebuild(true)
	if poll_enabled:
		_poll.start()
		_refresh_all()


func exit() -> void:
	_poll.stop()


func hints() -> Array:
	return [["accept", "Select"], ["tabs", "Switch tab"], ["back", "Back"]]


func screen_input(event: InputEvent) -> bool:
	return tabs.handle_shortcut(event)


func default_focus() -> Control:
	var f: Control = UiKit.first_focusable(_body)
	return f if f != null else tabs.tab_buttons[tabs.current]


func current_tab() -> String:
	return TAB_IDS[tabs.current]


func _update_subtitle() -> void:
	var chk: Dictionary = Online.url_status()
	var sub: String = "Service not configured"
	if bool(chk["ok"]):
		sub = "%s  ·  %s" % [String(chk["base"]), "signed in as " + Online.display_name() if Online.is_logged_in() else "signed out"]
	subtitle = sub
	if menu != null and menu.current == self:
		menu.set_subtitle(sub)


func _on_auth_changed(logged_in: bool, reason: String) -> void:
	if not logged_in:
		party = {}
		incoming = []
		queue = {}
		profile_online = {}
		if reason == "expired" and is_visible_in_tree():
			toast("Your online session expired — please sign in again.", "warn")
	_update_subtitle()
	if is_visible_in_tree():
		_rebuild(false)


# ------------------------------------------------------------------------------------------
# polling
# ------------------------------------------------------------------------------------------
func _refresh_all() -> void:
	if not Online.is_logged_in():
		if current_tab() == "servers" and Online.is_configured():
			_load_servers()
		return
	_poll_party()
	_poll_queue()
	if current_tab() == "servers":
		_load_servers()


func _on_poll() -> void:
	if not poll_enabled or not is_visible_in_tree() or not Online.is_logged_in():
		return
	_poll_n += 1
	var st: String = String(queue.get("state", "idle"))
	if st == "queued" or st == "matched" or _poll_n % 3 == 0:
		_poll_queue()
	if _poll_n % 3 == 0:
		_poll_party()


func _poll_party() -> void:
	if _p_in_flight:
		return
	_p_in_flight = true
	var r: Dictionary = await Online.party_current()
	var r2: Dictionary = await Online.invites()
	_p_in_flight = false
	if not is_inside_tree():
		return
	var changed: bool = false
	if bool(r["ok"]) and r["data"] is Dictionary:
		changed = changed or r["data"] != party
		party = r["data"]
	elif int(r["status"]) == 404:
		changed = changed or not party.is_empty()
		party = {}
	if bool(r2["ok"]) and r2["data"] is Array:
		var new_ids: Array = []
		for inv in (r2["data"] as Array):
			new_ids.append(String((inv as Dictionary).get("invite_id", "")))
		for inv in (r2["data"] as Array):
			var known: bool = false
			for old in incoming:
				if String((old as Dictionary).get("invite_id", "")) == String((inv as Dictionary).get("invite_id", "")):
					known = true
			if not known:
				toast("%s invited you to a party." % String((inv as Dictionary).get("from_username", "?")), "info")
		changed = changed or r2["data"] != incoming
		incoming = r2["data"]
	if changed and (current_tab() == "party" or current_tab() == "play"):
		_rebuild(false)


func _poll_queue() -> void:
	if _q_in_flight:
		return
	_q_in_flight = true
	var r: Dictionary = await Online.queue_status()
	_q_in_flight = false
	if not is_inside_tree() or not bool(r["ok"]) or not (r["data"] is Dictionary):
		return
	_apply_queue(r["data"])


func _apply_queue(d: Dictionary) -> void:
	var old_state: String = String(queue.get("state", "idle"))
	var old_match_ready: bool = _match_ready(queue)
	queue = d
	var st: String = String(d.get("state", "idle"))
	if st == "queued":
		_queued_base_s = float(d.get("queued_seconds", 0) if d.get("queued_seconds") != null else 0)
		_queued_since_ms = Time.get_ticks_msec()
	if st == "matched" and old_state != "matched":
		UiKit.play("ui_match_found")
		_was_matched = true
		_found_left = AUTO_JOIN_S
	if old_state == "matched" and st == "idle" and _was_matched and not _joining:
		_was_matched = false
		toast("The match was cancelled before it started. You can queue again.", "warn")
	var ready: bool = _match_ready(d)
	if ready and not old_match_ready:
		_found_left = AUTO_JOIN_S
	if st != old_state or ready != old_match_ready:
		if current_tab() == "play" or st == "matched":
			if st == "matched" and current_tab() != "play":
				tabs.select(TAB_IDS.find("play"), false)
			_rebuild(false)


static func _match_ready(q: Dictionary) -> bool:
	var m: Variant = q.get("match")
	return m is Dictionary and (m as Dictionary).get("host") != null and (m as Dictionary).get("port") != null


func _process(delta: float) -> void:
	if not is_visible_in_tree():
		return
	if _timer_label != null and is_instance_valid(_timer_label) and String(queue.get("state", "")) == "queued":
		var s: float = _queued_base_s + float(Time.get_ticks_msec() - _queued_since_ms) / 1000.0
		_timer_label.text = UiKit.fmt_duration(s)
	if _found_left > 0.0 and _match_ready(queue) and not _joining:
		_found_left -= delta
		if _found_bar != null and is_instance_valid(_found_bar):
			_found_bar.value = clampf(_found_left / AUTO_JOIN_S, 0.0, 1.0)
		if _found_left <= 0.0:
			_accept_match()


# ------------------------------------------------------------------------------------------
# view
# ------------------------------------------------------------------------------------------
func _rebuild(focus_first: bool) -> void:
	var fo: Control = get_viewport().gui_get_focus_owner() if is_inside_tree() else null
	var had_focus_inside: bool = fo != null and _body.is_ancestor_of(fo)
	var fo_name: String = String(fo.name) if had_focus_inside else ""
	_timer_label = null
	_found_bar = null
	UiKit.clear_children(_body)
	_update_subtitle()
	match current_tab():
		"account": _build_account()
		"party": _build_party()
		"play": _build_play()
		"private": _build_private()
		"servers": _build_servers()
	if inline_error != "":
		_body.add_child(_error_line(inline_error))
	if focus_first or had_focus_inside:
		_restore_focus.call_deferred(fo_name)


func _restore_focus(fo_name: String) -> void:
	if menu == null or menu.is_modal_open() or not is_visible_in_tree():
		return
	var target: Control = null
	if _focus_after_build != "":
		target = _body.find_child(_focus_after_build, true, false) as Control
		_focus_after_build = ""
	if target == null and fo_name != "":
		target = _body.find_child(fo_name, true, false) as Control
	if target == null or not target.is_visible_in_tree() or target.focus_mode == Control.FOCUS_NONE:
		target = UiKit.first_focusable(_body)
	if target != null:
		UiKit.focus(target)
		for b in tabs.tab_buttons:
			b.focus_neighbor_bottom = b.get_path_to(target)


func _error_line(text: String) -> HBoxContainer:
	var h := UiKit.hbox(8)
	h.add_child(UiKit.icon("error", 18.0, UiKit.ERR))
	var l := UiKit.label(text, &"ErrorLabel", true)
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(l)
	return h


func _heading(text: String, icon_kind: String = "") -> HBoxContainer:
	var h := UiKit.hbox(10)
	if icon_kind != "":
		h.add_child(UiKit.icon(icon_kind, 22.0, UiKit.ACCENT))
	h.add_child(UiKit.label(text.to_upper(), &"Heading"))
	return h


func _state_panel(icon_kind: String, head: String, text: String, actions: Array) -> VBoxContainer:
	## Honest explanation of a state that blocks the tab, with the actions that resolve it.
	var v := UiKit.vbox(12)
	v.add_child(UiKit.gap(12))
	var h := UiKit.hbox(14)
	h.add_child(UiKit.icon(icon_kind, 34.0, UiKit.TEXT_DIM))
	var tv := UiKit.vbox(4)
	tv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tv.add_child(UiKit.label(head, &"Heading"))
	var l := UiKit.label(text, &"Dim", true)
	tv.add_child(l)
	h.add_child(tv)
	v.add_child(h)
	var row := UiKit.hbox(10)
	for a in actions:
		var arr: Array = a
		var b := UiKit.button(String(arr[0]), (arr[2] as StringName) if arr.size() > 2 else &"", arr[1] as Callable)
		b.name = "Action_" + String(arr[0]).replace(" ", "_")
		row.add_child(b)
	if not actions.is_empty():
		v.add_child(row)
	return v


func _needs_login() -> bool:
	if not Online.is_configured():
		var chk: Dictionary = Online.url_status()
		_body.add_child(_state_panel("wifi_off", "Online service not available", String(chk["message"]) +
			"\nDirect connect on the Private & direct tab works without a service.",
			[["Open settings", func() -> void: menu.open_settings("online"), &"PrimaryButton"]]))
		return true
	if not Online.is_logged_in():
		_body.add_child(_state_panel("user", "Sign in required", "Sign in on the Account tab to use parties, queues and private matches.",
			[["Go to account", func() -> void: tabs.select(0), &"PrimaryButton"]]))
		return true
	return false


func _form_row(label_text: String, ctrl: Control) -> HBoxContainer:
	var h := UiKit.hbox(14)
	var l := UiKit.label(label_text)
	l.custom_minimum_size = Vector2(190, 0)
	h.add_child(l)
	ctrl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(ctrl)
	return h


# ------------------------------------------------------------------------------------------
# Account
# ------------------------------------------------------------------------------------------
func _build_account() -> void:
	var chk: Dictionary = Online.url_status()
	if not bool(chk["ok"]):
		_body.add_child(_state_panel("wifi_off", "Online service not configured" if String(chk["code"]) == "not_configured" else "Service URL refused",
			String(chk["message"]) + "\nOffline play, training and direct connect keep working.",
			[["Open settings", func() -> void: menu.open_settings("online"), &"PrimaryButton"]]))
		return
	var sec := UiKit.hbox(8)
	sec.add_child(UiKit.icon("lock" if bool(chk["secure"]) else "info", 16.0, UiKit.OK if bool(chk["secure"]) else UiKit.WARN))
	sec.add_child(UiKit.label(("Secure connection to %s" if bool(chk["secure"]) else "Local development service %s (plain HTTP allowed on this computer only)") % String(chk["base"]), &"Small"))
	if Online.is_logged_in():
		_build_account_card()
		_body.add_child(sec)
		return
	_body.add_child(sec)
	var cols := UiKit.hbox(28)
	_body.add_child(cols)
	# sign in
	var li := UiKit.vbox(10)
	li.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(li)
	li.add_child(_heading("Sign in", "user"))
	var user := UiKit.line_edit("Username", 16)
	user.name = "LoginUser"
	user.text = String(Settings.get_value("online", "last_username"))
	li.add_child(_form_row("Username", user))
	var pw := UiKit.line_edit("Password", 128, true)
	pw.name = "LoginPassword"
	li.add_child(_form_row("Password", pw))
	var remember := UiToggle.new("Remember me on this computer", "check")
	remember.name = "Remember"
	remember.tooltip_text = "Keeps the session token (never the password) in your user folder."
	li.add_child(_form_row("", remember))
	var login_b := UiKit.button("Sign in", &"PrimaryButton", func() -> void: _do_login(user.text.strip_edges(), pw.text, remember.button_pressed))
	login_b.name = "LoginButton"
	login_b.size_flags_horizontal = Control.SIZE_SHRINK_END
	li.add_child(login_b)
	pw.text_submitted.connect(func(_t: String) -> void: _do_login(user.text.strip_edges(), pw.text, remember.button_pressed))
	cols.add_child(VSeparator.new())
	# register
	var rg := UiKit.vbox(10)
	rg.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(rg)
	rg.add_child(_heading("Create account", "plus"))
	var ru := UiKit.line_edit("3–16 letters, digits, _", 16)
	ru.name = "RegUser"
	rg.add_child(_form_row("Username", ru))
	var rd := UiKit.line_edit("Optional, 3–20 characters", 20)
	rd.name = "RegDisplay"
	rg.add_child(_form_row("Display name", rd))
	var rp := UiKit.line_edit("At least 8 characters", 128, true)
	rp.name = "RegPassword"
	rg.add_child(_form_row("Password", rp))
	var rp2 := UiKit.line_edit("Repeat the password", 128, true)
	rp2.name = "RegPassword2"
	rg.add_child(_form_row("Confirm", rp2))
	var reg_b := UiKit.button("Create account", &"", func() -> void: _do_register(ru.text.strip_edges(), rd.text.strip_edges(), rp.text, rp2.text))
	reg_b.name = "RegisterButton"
	reg_b.size_flags_horizontal = Control.SIZE_SHRINK_END
	rg.add_child(reg_b)


func _build_account_card() -> void:
	var a: Dictionary = Online.account
	var card := UiKit.hbox(24)
	_body.add_child(card)
	var who := UiKit.vbox(2)
	who.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	who.add_child(UiKit.label("SIGNED IN", &"Caption"))
	who.add_child(UiKit.label(String(a.get("display_name", a.get("username", "Player"))), &"Title"))
	who.add_child(UiKit.label("@%s · member since %s" % [String(a.get("username", "?")), UiKit.fmt_datetime(String(a.get("created_at", ""))).substr(0, 10)], &"Dim"))
	card.add_child(who)
	var r: Dictionary = a.get("rating", {}) if a.get("rating") is Dictionary else {}
	var stats := UiKit.hbox(30)
	stats.add_child(UiKit.key_value("Rating", "%d ± %d" % [int(round(float(r.get("rating", 1500)))), int(round(float(r.get("deviation", 350))))]))
	stats.add_child(UiKit.key_value("Ranked games", str(int(r.get("games", 0)))))
	stats.add_child(UiKit.key_value("Wins / losses", "%d / %d" % [int(r.get("wins", 0)), int(r.get("losses", 0))]))
	card.add_child(stats)
	var note := UiKit.label("Online records and mastery are kept by the service, separately from your offline profile. Ranked rating is only changed by server-submitted results.", &"Small", true)
	_body.add_child(note)
	var row := UiKit.hbox(10)
	var ref := UiKit.button("Refresh", &"", func() -> void: _refresh_me())
	ref.name = "RefreshAccount"
	row.add_child(ref)
	var out := UiKit.button("Sign out", &"DangerButton", func() -> void: _do_logout())
	out.name = "SignOut"
	row.add_child(out)
	if Online.remember:
		var rl := UiKit.label("Remembered on this computer until you sign out.", &"Small")
		rl.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		row.add_child(rl)
	_body.add_child(row)


func _do_login(u: String, p: String, rem: bool) -> void:
	if busy:
		return
	if u == "" or p == "":
		_fail("Enter your username and password.")
		return
	busy = true
	inline_error = ""
	var r: Dictionary = await Online.login(u, p, rem)
	busy = false
	if not is_inside_tree():
		return
	if bool(r["ok"]):
		UiKit.play("ui_ready")
		toast("Signed in as %s." % Online.display_name(), "ok")
		_rebuild(true)
		_refresh_all()
	else:
		_fail(_msg(r))


func _do_register(u: String, d: String, p: String, p2: String) -> void:
	if busy:
		return
	if p != p2:
		_fail("The passwords do not match.")
		return
	busy = true
	inline_error = ""
	var r: Dictionary = await Online.register(u, p, d)
	if not is_inside_tree():
		busy = false
		return
	if not bool(r["ok"]):
		busy = false
		_fail(_msg(r))
		return
	toast("Account %s created." % u, "ok")
	var r2: Dictionary = await Online.login(u, p, false)
	busy = false
	if not is_inside_tree():
		return
	if bool(r2["ok"]):
		_rebuild(true)
		_refresh_all()
	else:
		_fail(_msg(r2))


func _do_logout() -> void:
	var r: Dictionary = await Online.logout()
	if not is_inside_tree():
		return
	toast("Signed out." if bool(r["ok"]) else "Signed out locally (%s)." % _msg(r), "info")
	_rebuild(true)


func _refresh_me() -> void:
	var r: Dictionary = await Online.me()
	if is_inside_tree():
		if bool(r["ok"]):
			_rebuild(false)
		else:
			_fail(_msg(r))


func _msg(r: Dictionary) -> String:
	var e: Dictionary = r.get("error", {})
	var code: String = String(e.get("code", ""))
	match code:
		"invalid_credentials": return "Wrong username or password."
		"username_taken": return "That username is already taken."
		"no_such_user": return "No player with that username exists."
		"already_in_party": return "That player is already in a party."
		"already_invited": return "That player already has a pending invite."
		"party_full": return "The party is full (5 players)."
		"not_leader": return "Only the party leader can do that."
		"expired": return "That invite has expired."
		"already_queued": return "You are already in a queue."
		"already_in_match": return "You are already assigned to a match."
		"already_matched": return "A match was already found — join it."
		"bots_in_ranked": return "Ranked matches never use bots."
		"invalid_join_code": return "No private match uses that join code."
		"match_full": return "That private match is full."
		"match_not_ready": return "That private match is not ready yet — try again in a moment."
		"already_hosting": return "You already host a private match."
		"no_server_available": return "No game server is available in your region right now."
		"allocation_timeout", "allocation_failed": return "The game server could not be started. Try again."
		"rate_limited": return String(e.get("message", "Too many requests — wait a moment."))
		"validation_error": return "The service rejected the request: %s" % String(e.get("message", "invalid input"))
	return String(e.get("message", "Request failed."))


func _fail(text: String) -> void:
	inline_error = text
	UiKit.play("ui_error")
	toast(text, "error")
	_rebuild(false)
	inline_error = ""


# ------------------------------------------------------------------------------------------
# Party
# ------------------------------------------------------------------------------------------
func _my_id() -> String:
	return String(Online.account.get("account_id", ""))


func _am_leader() -> bool:
	return not party.is_empty() and String(party.get("leader_id", "")) == _my_id()


func _build_party() -> void:
	if _needs_login():
		return
	if party.is_empty():
		_body.add_child(_heading("No party", "users"))
		_body.add_child(UiKit.label("Parties have up to five players, always play on the same team and queue together. Only the leader starts a queue.", &"Dim", true))
		var c := UiKit.button("Create party", &"PrimaryButton", func() -> void: _party_action(Online.party_create, [], "Party created."))
		c.name = "CreateParty"
		c.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		_body.add_child(c)
	else:
		var members: Array = party.get("members", [])
		_body.add_child(_heading("Party  %d / 5" % members.size(), "users"))
		var list := UiKit.vbox(6)
		_body.add_child(list)
		for mem in members:
			list.add_child(_member_row(mem as Dictionary))
		for i in range(members.size(), 5):
			var empty := UiKit.hbox(10)
			empty.add_child(UiKit.icon("user", 20.0, UiKit.LINE_BRIGHT))
			empty.add_child(UiKit.label("Open slot", &"Small"))
			list.add_child(empty)
		var inv_out: Array = party.get("invites", [])
		if not inv_out.is_empty():
			_body.add_child(UiKit.label("PENDING INVITES", &"Caption"))
			for inv in inv_out:
				var d: Dictionary = inv
				var h := UiKit.hbox(10)
				h.add_child(UiKit.icon("mail", 18.0, UiKit.TEXT_DIM))
				h.add_child(UiKit.label(String(d.get("to_username", "?")), &""))
				h.add_child(UiKit.label("expires %s" % UiKit.fmt_datetime(String(d.get("expires_at", ""))).substr(11), &"Small"))
				_body.add_child(h)
		if _am_leader():
			var ih := UiKit.hbox(10)
			var ie := UiKit.line_edit("Username to invite", 16)
			ie.name = "InviteUser"
			ih.add_child(ie)
			var ib := UiKit.button("Invite", &"", func() -> void: _party_action(Online.party_invite, [ie.text.strip_edges()], "Invite sent to %s." % ie.text.strip_edges()))
			ib.name = "InviteButton"
			ih.add_child(ib)
			ie.text_submitted.connect(func(t: String) -> void: _party_action(Online.party_invite, [t.strip_edges()], "Invite sent to %s." % t.strip_edges()))
			_body.add_child(_form_row("Invite player", ih))
		else:
			_body.add_child(UiKit.label("Only the party leader can invite players and start a queue.", &"Small"))
		var pq: Variant = party.get("queue")
		if pq is Dictionary:
			var qd: Dictionary = pq
			_body.add_child(UiKit.chip(("Party is %s · %s" % [String(qd.get("state", "")), UiKit.mode_label(String(qd.get("mode", "")))]).to_upper(), UiKit.GOLD, "hourglass"))
		var lv := UiKit.button("Leave party", &"DangerButton", func() -> void: _party_action(Online.party_leave, [], "You left the party."))
		lv.name = "LeaveParty"
		lv.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		_body.add_child(lv)
	_body.add_child(UiKit.rule())
	_body.add_child(UiKit.label("INVITES FOR YOU", &"Caption"))
	if incoming.is_empty():
		_body.add_child(UiKit.label("No pending invites.", &"Small"))
	for inv in incoming:
		var d2: Dictionary = inv
		var id: String = String(d2.get("invite_id", ""))
		var h2 := UiKit.hbox(10)
		h2.add_child(UiKit.icon("mail", 18.0, UiKit.GOLD))
		var l := UiKit.label("%s invited you" % String(d2.get("from_username", "?")))
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h2.add_child(l)
		h2.add_child(UiKit.label("until %s" % UiKit.fmt_datetime(String(d2.get("expires_at", ""))).substr(11), &"Small"))
		var acc := UiKit.button("Accept", &"PrimaryButton", func() -> void: _party_action(Online.invite_accept, [id], "You joined the party."))
		acc.name = "Accept_" + id.substr(0, 8)
		h2.add_child(acc)
		var dec := UiKit.button("Decline", &"", func() -> void: _party_action(Online.invite_decline, [id], "Invite declined."))
		dec.name = "Decline_" + id.substr(0, 8)
		h2.add_child(dec)
		_body.add_child(h2)


func _member_row(m: Dictionary) -> HBoxContainer:
	var h := UiKit.hbox(10)
	var aid: String = String(m.get("account_id", ""))
	var leader: bool = aid == String(party.get("leader_id", ""))
	h.add_child(UiKit.icon("crown" if leader else "user", 20.0, UiKit.GOLD if leader else UiKit.TEXT_DIM))
	var nm := UiKit.label(String(m.get("display_name", m.get("username", "?"))))
	h.add_child(nm)
	h.add_child(UiKit.label("@" + String(m.get("username", "")), &"Small"))
	if leader:
		h.add_child(UiKit.chip("LEADER", UiKit.GOLD))
	if aid == _my_id():
		h.add_child(UiKit.chip("YOU", UiKit.TEXT_DIM))
	h.add_child(UiKit.spacer())
	if _am_leader() and aid != _my_id():
		var pr := UiKit.button("Make leader", &"SmallButton", func() -> void: _party_action(Online.party_promote, [aid], "Leadership handed over."))
		h.add_child(pr)
		var kk := UiKit.button("Remove", &"SmallButton", func() -> void: _party_action(Online.party_kick, [aid], "Player removed from the party."))
		h.add_child(kk)
	return h


func _party_action(fn: Callable, args: Array, ok_text: String) -> void:
	if busy:
		return
	busy = true
	var r: Dictionary = await fn.callv(args)
	busy = false
	if not is_inside_tree():
		return
	if bool(r["ok"]):
		toast(ok_text, "ok")
		await _poll_party_now()
	else:
		_fail(_msg(r))


func _poll_party_now() -> void:
	_p_in_flight = false
	await _poll_party()
	_rebuild(false)


# ------------------------------------------------------------------------------------------
# Play (queue)
# ------------------------------------------------------------------------------------------
func _build_play() -> void:
	if _needs_login():
		return
	var st: String = String(queue.get("state", "idle"))
	if st == "matched":
		_build_match_found()
		return
	if st == "queued":
		_build_queued()
		return
	var in_party: bool = not party.is_empty()
	var members: int = (party.get("members", []) as Array).size() if in_party else 1
	_body.add_child(_heading("Find a match", "swords"))
	var modes := UiKit.hbox(14)
	_body.add_child(modes)
	var group := ButtonGroup.new()
	for md in [["casual", "Casual", "Unrated. If every queued party allows it, bots may fill empty slots after 20 s — always labelled BOT."],
			["ranked", "Ranked", "Exactly ten players, no bots, rating changes. Leaving counts as a loss."]]:
		var arr: Array = md
		var mid: String = String(arr[0])
		var b := Button.new()
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = _queue_mode == mid
		b.custom_minimum_size = Vector2(300, 118)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.name = "Mode_" + mid
		b.theme_type_variation = &"ValueButton"
		b.focus_mode = Control.FOCUS_ALL
		UiKit.hover_focus(b)
		b.pressed.connect(func() -> void:
			_queue_mode = mid
			UiState.queue_mode = mid
			UiKit.play("ui_select")
			_focus_after_build = "Mode_" + mid
			_rebuild(false))
		var mv := UiKit.vbox(4)
		mv.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		mv.offset_left = 16
		mv.offset_top = 12
		mv.offset_right = -16
		mv.offset_bottom = -10
		mv.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var head := UiKit.hbox(8)
		head.mouse_filter = Control.MOUSE_FILTER_IGNORE
		head.add_child(UiKit.icon("check" if _queue_mode == mid else "circle", 18.0, UiKit.ACCENT if _queue_mode == mid else UiKit.TEXT_FAINT))
		head.add_child(UiKit.label(String(arr[1]).to_upper(), &"Heading"))
		mv.add_child(head)
		var dl := UiKit.label(String(arr[2]), &"Small", true)
		dl.mouse_filter = Control.MOUSE_FILTER_IGNORE
		mv.add_child(dl)
		b.add_child(mv)
		modes.add_child(b)
	if _queue_mode == "casual":
		var ab := UiToggle.new("Allow bots to fill empty slots", "check", UiState.allow_bots)
		ab.name = "AllowBots"
		ab.toggled.connect(func(on: bool) -> void: UiState.allow_bots = on)
		_body.add_child(_form_row("Bots", ab))
	var opts: Array = [["", "No preference"]]
	for fid in WR.FIGHTER_IDS:
		opts.append([fid, UiKit.fighter_name(fid)])
	var pref := UiCycler.new(opts, 0)
	pref.name = "PreferredFighter"
	pref.select_value(_pref_fighter)
	pref.value_changed.connect(func(_i: int, v: Variant) -> void: _pref_fighter = String(v))
	_body.add_child(_form_row("Preferred fighter", pref))
	var region_row := UiKit.hbox(10)
	region_row.add_child(UiKit.label(Online.region(), &"Stat"))
	var rb := UiKit.button("Change", &"SmallButton", func() -> void: menu.open_settings("online"))
	region_row.add_child(rb)
	_body.add_child(_form_row("Region", region_row))
	var rules: String = "Solo queue." if not in_party else "Your party of %d queues together and plays on one team." % members
	if _queue_mode == "ranked":
		rules += " Ranked needs ten human players; the match starts only when they are found."
	_body.add_child(UiKit.label(rules, &"Small", true))
	if in_party and not _am_leader():
		_body.add_child(_state_panel("crown", "Waiting for your party leader", "Only the party leader can start a queue. You will join the match with your party automatically.", []))
	else:
		var go := UiKit.button("Find match", &"PrimaryButton", func() -> void: _do_queue())
		go.name = "FindMatch"
		go.custom_minimum_size = Vector2(260, 50)
		go.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		_body.add_child(go)
	_body.add_child(_queue_counts())


func _queue_counts() -> HBoxContainer:
	var h := UiKit.hbox(18)
	var counts: Dictionary = queue.get("counts", {}) if queue.get("counts") is Dictionary else {}
	h.add_child(UiKit.icon("users", 18.0, UiKit.TEXT_DIM))
	if counts.is_empty():
		h.add_child(UiKit.label("Queue sizes appear once the service answers.", &"Small"))
	else:
		h.add_child(UiKit.label("Casual: %d queued" % int(counts.get("casual", 0)), &"Small"))
		h.add_child(UiKit.label("Ranked: %d queued" % int(counts.get("ranked", 0)), &"Small"))
	return h


func _build_queued() -> void:
	_body.add_child(_heading("Searching — %s" % UiKit.mode_label(String(queue.get("mode", ""))), "hourglass"))
	var big := UiKit.hbox(16)
	_timer_label = UiKit.label(UiKit.fmt_duration(float(queue.get("queued_seconds", 0) if queue.get("queued_seconds") != null else 0)), &"StatLarge")
	_timer_label.add_theme_font_size_override("font_size", 64)
	big.add_child(_timer_label)
	var tv := UiKit.vbox(2)
	tv.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	tv.add_child(UiKit.label("TIME IN QUEUE", &"Caption"))
	tv.add_child(UiKit.label("Players are matched by queue, party size, region and rating.", &"Small"))
	big.add_child(tv)
	_body.add_child(big)
	_body.add_child(_queue_counts())
	var c := UiKit.button("Cancel search", &"DangerButton", func() -> void: _do_unqueue())
	c.name = "CancelQueue"
	c.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_body.add_child(c)
	if not party.is_empty():
		_body.add_child(UiKit.label("Cancelling removes your whole party from the queue.", &"Small"))


func _build_match_found() -> void:
	var m: Dictionary = queue.get("match", {}) if queue.get("match") is Dictionary else {}
	var ready: bool = _match_ready(queue)
	var h := _heading("Match found", "swords")
	_body.add_child(h)
	var info := UiKit.hbox(24)
	info.add_child(UiKit.key_value("Mode", UiKit.mode_label(String(m.get("mode", queue.get("mode", ""))))))
	info.add_child(UiKit.key_value("Your team", UiKit.TEAM_NAMES[clampi(int(m.get("team", 0)), 0, 1)] if m.get("team") != null and int(m.get("team", -1)) >= 0 else "Assigned in lobby"))
	info.add_child(UiKit.key_value("Server", "%s:%d" % [String(m.get("host")), int(m.get("port"))] if ready else "Starting…"))
	_body.add_child(info)
	if not ready:
		_body.add_child(_state_panel("hourglass", "Starting the match server", "A game server is being allocated for your match. You will be able to join in a moment.", []))
		return
	_found_bar = UiKit.progress(clampf(_found_left / AUTO_JOIN_S, 0.0, 1.0), 1.0)
	_found_bar.custom_minimum_size = Vector2(0, 8)
	_body.add_child(_found_bar)
	_body.add_child(UiKit.label("Joining automatically when the bar runs out.", &"Small"))
	var j := UiKit.button("Join match", &"PrimaryButton", func() -> void: _accept_match())
	j.name = "JoinMatch"
	j.custom_minimum_size = Vector2(260, 50)
	j.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_body.add_child(j)
	_focus_after_build = "JoinMatch"


func _do_queue() -> void:
	if busy:
		return
	busy = true
	var prefs: Array = [_pref_fighter] if _pref_fighter != "" else []
	var r: Dictionary = await Online.queue_join(_queue_mode, prefs, Online.region(), {}, UiState.allow_bots and _queue_mode == "casual")
	busy = false
	if not is_inside_tree():
		return
	if bool(r["ok"]) and r["data"] is Dictionary:
		UiKit.play("ui_ready")
		_apply_queue(r["data"])
		_rebuild(true)
	else:
		_fail(_msg(r))


func _do_unqueue() -> void:
	var r: Dictionary = await Online.queue_leave()
	if not is_inside_tree():
		return
	if bool(r["ok"]):
		UiKit.play("ui_back")
		queue["state"] = "idle"
		_was_matched = false
		toast("Search cancelled.", "info")
		_rebuild(true)
		_poll_queue()
	else:
		_fail(_msg(r))


func _accept_match() -> void:
	if _joining:
		return
	_joining = true
	var r: Dictionary = await Online.queue_accept()
	if not is_inside_tree():
		_joining = false
		return
	if not bool(r["ok"]):
		_joining = false
		if String(r["error"].get("code", "")) == "allocating":
			_found_left = 2.0
			return
		_fail(_msg(r))
		return
	var m: Dictionary = r["data"]
	_join_server(String(m.get("host", "")), int(m.get("port", 0)), {"ticket": String(m.get("ticket", ""))})


func _join_server(host: String, port: int, auth: Dictionary) -> void:
	var a: Dictionary = auth.duplicate()
	a["name"] = Online.display_name() if Online.is_logged_in() and not a.has("password") else String(Settings.get_value("player", "name"))
	UiKit.play("ui_lockin")
	var err: int = Game.start_online_session(host, port, a)
	_joining = false
	if err != OK:
		_fail("Could not start the connection to %s:%d (%s)." % [host, port, error_string(err)])
		Game.end_online_session()
		return
	Game.goto(Game.SCENE_ONLINE_LOBBY, {})


# ------------------------------------------------------------------------------------------
# Private matches & direct connect
# ------------------------------------------------------------------------------------------
func _build_private() -> void:
	var cols := UiKit.hbox(28)
	_body.add_child(cols)
	var left := UiKit.vbox(10)
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(left)
	left.add_child(_heading("Private match", "lock"))
	if not Online.is_configured() or not Online.is_logged_in():
		var why: String = String(Online.url_status()["message"]) if not Online.is_configured() else "Sign in on the Account tab to create or join private matches through the service."
		left.add_child(UiKit.label(why, &"Dim", true))
		if Online.is_configured():
			var gb := UiKit.button("Go to account", &"", func() -> void: tabs.select(0))
			gb.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
			left.add_child(gb)
	else:
		left.add_child(UiKit.label("Create a lobby on a service game server and share its join code. You administer teams, bots and observers. Private matches are never rated.", &"Small", true))
		var cb := UiKit.button("Create private match", &"PrimaryButton", func() -> void: _do_private_create())
		cb.name = "CreatePrivate"
		cb.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		left.add_child(cb)
		left.add_child(UiKit.gap(6))
		left.add_child(UiKit.label("JOIN WITH A CODE", &"Caption"))
		var code := UiKit.line_edit("8-character join code", 9)
		code.name = "JoinCode"
		left.add_child(_form_row("Join code", code))
		var role := UiCycler.new([["player", "Player"], ["observer", "Observer (spectate only)"]], 0)
		role.name = "JoinRole"
		left.add_child(_form_row("Join as", role))
		var jb := UiKit.button("Join", &"", func() -> void: _do_private_join(code.text, String(role.value())))
		jb.name = "JoinPrivate"
		jb.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		left.add_child(jb)
		code.text_submitted.connect(func(t: String) -> void: _do_private_join(t, String(role.value())))
	cols.add_child(VSeparator.new())
	var right := UiKit.vbox(10)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(right)
	right.add_child(_heading("Direct connect", "link"))
	right.add_child(UiKit.label("Connect straight to a dedicated server (LAN or self-hosted) by address. No account needed.", &"Small", true))
	var addr := UiKit.line_edit("host:port", 120)
	addr.name = "DirectAddress"
	addr.text = UiState.last_direct
	right.add_child(_form_row("Address", addr))
	var pw := UiKit.line_edit("Only if the host set one", 64, true)
	pw.name = "DirectPassword"
	right.add_child(_form_row("Password", pw))
	var nm := UiKit.label(String(Settings.get_value("player", "name")), &"Stat")
	right.add_child(_form_row("Your name", nm))
	var db := UiKit.button("Connect", &"PrimaryButton", func() -> void: _do_direct(addr.text, pw.text))
	db.name = "DirectConnect"
	db.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	right.add_child(db)
	addr.text_submitted.connect(func(_t: String) -> void: _do_direct(addr.text, pw.text))


static func parse_address(text: String) -> Dictionary:
	## "host:port", "host" (default port 24610) or "[v6]:port" -> {"ok", "host", "port", "message"}.
	var t: String = text.strip_edges()
	var out: Dictionary = {"ok": false, "host": "", "port": 24610, "message": ""}
	if t == "":
		out["message"] = "Enter a server address such as 192.168.1.20:24610."
		return out
	var host: String = t
	var port_s: String = ""
	if t.begins_with("["):
		var e: int = t.find("]")
		if e < 0:
			out["message"] = "Malformed IPv6 address."
			return out
		host = t.substr(1, e - 1)
		if t.substr(e + 1).begins_with(":"):
			port_s = t.substr(e + 2)
	elif t.count(":") == 1:
		host = t.get_slice(":", 0)
		port_s = t.get_slice(":", 1)
	if port_s != "":
		if not port_s.is_valid_int() or int(port_s) < 1 or int(port_s) > 65535:
			out["message"] = "The port must be a number from 1 to 65535."
			return out
		out["port"] = int(port_s)
	if host == "" or host.contains(" ") or host.contains("/"):
		out["message"] = "Enter a host name or IP address."
		return out
	out["ok"] = true
	out["host"] = host
	return out


func _do_direct(addr_text: String, password: String) -> void:
	var a: Dictionary = parse_address(addr_text)
	if not bool(a["ok"]):
		_fail(String(a["message"]))
		return
	UiState.last_direct = addr_text.strip_edges()
	var auth: Dictionary = {}
	if password != "":
		auth["password"] = password
	UiState.private_join_code = ""
	_join_server(String(a["host"]), int(a["port"]), auth)


func _do_private_create() -> void:
	if busy:
		return
	busy = true
	toast("Starting a private server — this can take up to 20 seconds.", "info")
	var r: Dictionary = await Online.private_create(Online.region())
	busy = false
	if not is_inside_tree():
		return
	if not bool(r["ok"]):
		_fail(_msg(r))
		return
	var d: Dictionary = r["data"]
	UiState.private_join_code = String(d.get("join_code", ""))
	_join_server(String(d.get("host", "")), int(d.get("port", 0)), {"ticket": String(d.get("ticket", ""))})


func _do_private_join(code: String, role: String) -> void:
	if busy:
		return
	busy = true
	var r: Dictionary = await Online.private_join(code, role)
	busy = false
	if not is_inside_tree():
		return
	if not bool(r["ok"]):
		_fail(_msg(r))
		return
	var d: Dictionary = r["data"]
	UiState.private_join_code = code.strip_edges().to_upper()
	var auth: Dictionary = {"ticket": String(d.get("ticket", ""))}
	if role == "observer":
		auth["observer"] = true
	_join_server(String(d.get("host", "")), int(d.get("port", 0)), auth)


# ------------------------------------------------------------------------------------------
# Server browser
# ------------------------------------------------------------------------------------------
func _build_servers() -> void:
	if not Online.is_configured():
		_body.add_child(_state_panel("wifi_off", "Online service not configured", String(Online.url_status()["message"]),
			[["Open settings", func() -> void: menu.open_settings("online"), &"PrimaryButton"]]))
		return
	var head := UiKit.hbox(12)
	head.add_child(_heading("Game servers", "server"))
	head.add_child(UiKit.spacer())
	var rb := UiKit.button("Refresh", &"", func() -> void: _load_servers())
	rb.name = "RefreshServers"
	head.add_child(rb)
	_body.add_child(head)
	_body.add_child(UiKit.label("Servers that reported to the service in the last 30 seconds. Matches are placed on them automatically; choosing one sets your region for queues and private matches.", &"Small", true))
	if servers_error != "":
		_body.add_child(_error_line(servers_error))
		return
	if servers.is_empty():
		_body.add_child(_state_panel("server", "No servers online", "No game server has reported to this service recently. Queues wait until one is available; direct connect still works.", []))
		return
	var g := UiKit.grid(7, 18, 8)
	_body.add_child(g)
	for h in ["", "NAME", "REGION", "STATUS", "MATCHES", "VERSION", "LAST SEEN"]:
		g.add_child(UiKit.label(String(h), &"Caption"))
	for i in range(servers.size()):
		var s: Dictionary = servers[i]
		var idx: int = i
		var pick := UiKit.button("Use region", &"SmallButton", func() -> void: _use_server(idx))
		pick.name = "UseServer_%d" % i
		g.add_child(pick)
		var nm := UiKit.label(String(s.get("name", s.get("server_id", "?"))))
		g.add_child(nm)
		g.add_child(UiKit.label(String(s.get("region", "")), &"Dim"))
		var online: bool = String(s.get("status", "")) == "online"
		g.add_child(UiKit.chip(String(s.get("status", "?")).to_upper(), UiKit.OK if online else UiKit.WARN, "check" if online else "warning"))
		g.add_child(UiKit.label("%d / %d" % [int(s.get("active_matches", 0)), int(s.get("capacity", 0))], &"Dim"))
		var compatible: bool = String(s.get("build_id", WR.BUILD_ID)) == WR.BUILD_ID and int(s.get("protocol", WR.PROTOCOL_VERSION)) == WR.PROTOCOL_VERSION
		g.add_child(UiKit.chip("COMPATIBLE" if compatible else "OTHER VERSION", UiKit.OK if compatible else UiKit.ERR, "check" if compatible else "cross"))
		g.add_child(UiKit.label(UiKit.fmt_datetime(String(s.get("last_seen", ""))).substr(11), &"Small"))


func _load_servers() -> void:
	var r: Dictionary = await Online.servers_list()
	if not is_inside_tree():
		return
	if bool(r["ok"]) and r["data"] is Array:
		servers = r["data"]
		servers_error = ""
	else:
		servers_error = _msg(r)
	if current_tab() == "servers":
		_rebuild(false)


func _use_server(i: int) -> void:
	if i < 0 or i >= servers.size():
		return
	var reg: String = String((servers[i] as Dictionary).get("region", ""))
	if Online.valid_region(reg):
		Settings.set_value("online", "region", reg)
		toast("Region set to %s." % reg, "ok")
