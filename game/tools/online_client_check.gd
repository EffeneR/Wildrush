extends Node
## Live check of the game's own HTTP client (autoload `Online`) against a running control
## service (G9 support): version, register, login, me, profile get/patch, party create/invite/
## leave, casual queue join/status/leave, server browser, history, logout. Loopback HTTP only.
##   godot --headless --path game res://tools/online_client_check.tscn -- --service-url http://127.0.0.1:8080 [--json out.json]

var results: Array = []
var ok: bool = true


func _ready() -> void:
	await get_tree().process_frame
	var url: String = Config.get_arg("service-url", "http://127.0.0.1:8080")
	Settings.set_value("online", "service_url", url, false)
	await _run()
	var out := {"ok": ok, "service": url, "steps": results}
	var jp: String = Config.get_arg("json", "")
	if jp != "":
		var f := FileAccess.open(jp, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(out, "  "))
			f.close()
	print("[online_check] %s (%d steps)" % ["PASS" if ok else "FAIL", results.size()])
	for r in results:
		print("[online_check] %-22s %s %s" % [r["step"], "ok" if r["pass"] else "FAIL", r.get("note", "")])
	get_tree().quit(0 if ok else 1)


func _step(name: String, r: Dictionary, expect_ok: bool = true, note: String = "") -> Dictionary:
	var passed: bool = bool(r.get("ok", false)) == expect_ok
	if not passed:
		ok = false
	results.append({"step": name, "pass": passed, "status": r.get("status", 0), "note": note if passed else str(r.get("error", r))})
	return r


func _run() -> void:
	var tag: String = "%04x" % (randi() % 0xFFFF)
	var user: String = "oc%sa" % tag
	var friend: String = "oc%sb" % tag
	var pw: String = "pw-%s-%d" % [tag, randi()]
	_step("url_status", {"ok": Online.url_status().get("ok", false)}, true, "loopback http accepted")
	_step("version", await Online.version())
	_step("register", await Online.register(user, pw, "Online Check"))
	_step("register_friend", await Online.register(friend, pw, "Online Friend"))
	_step("register_duplicate", await Online.register(user, pw), false, "409 username_taken")
	_step("login_wrong_password", await Online.login(user, "wrong-password"), false, "401 invalid_credentials")
	_step("login", await Online.login(user, pw, false))
	var me: Dictionary = _step("me", await Online.me())
	_step("profile_get", await Online.profile_get())
	_step("profile_patch", await Online.profile_patch({"display_name": "Check %s" % tag}))
	_step("party_create", await Online.party_create())
	_step("party_invite", await Online.party_invite(friend))
	_step("party_current", await Online.party_current())
	_step("party_leave", await Online.party_leave())
	_step("queue_join_casual", await Online.queue_join("casual", ["vex"], "local", {"local": 5}, true))
	_step("queue_status", await Online.queue_status())
	_step("queue_leave", await Online.queue_leave())
	_step("servers_list", await Online.servers_list())
	_step("history", await Online.history(5))
	_step("logout", await Online.logout())
	_step("me_after_logout", await Online.me(), false, "401 after logout")
	if me.is_empty():
		ok = false
