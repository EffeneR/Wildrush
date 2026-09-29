extends Node
## Autoload "Online": HTTP client for the WILDRUSH control service (docs/API_CONTRACT.md,
## services/CONTRACT_NOTES.md). docs/UI_CONTRACT.md "Online client":
## * base URL from Settings online/service_url; non-HTTPS URLs are refused unless the host is
##   loopback (127.0.0.1, localhost, ::1) — the refusal is returned as an error the UI shows;
## * the bearer token lives in memory; only with "remember me" is it written to
##   user://session.cfg (token + expiry + the service it belongs to — never the password);
## * every call is awaitable and returns {"ok", "status", "data", "error": {"code", "message"}};
## * 429 responses block further calls of the same endpoint until Retry-After has passed.

signal auth_changed(logged_in: bool, reason: String)
signal account_changed(account: Dictionary)

const SESSION_PATH: String = "user://session.cfg"
const LOOPBACK_HOSTS: Array[String] = ["127.0.0.1", "localhost", "::1"]
const DEFAULT_TIMEOUT_S: float = 15.0
const PRIVATE_CREATE_TIMEOUT_S: float = 35.0   # the service blocks up to ~20 s while allocating
const USERNAME_RE: String = "^[A-Za-z0-9_]{3,16}$"
const REGION_RE: String = "^[a-z0-9-]{2,20}$"

var token: String = ""
var token_expires_at: String = ""
var token_base: String = ""          # service the token belongs to
var account: Dictionary = {}         # GET /v1/me
var remember: bool = false
var in_flight: int = 0
var last_error: Dictionary = {}
var _retry_until_ms: Dictionary = {}  # bucket -> ticks msec
var _re_user := RegEx.new()
var _re_region := RegEx.new()


func _ready() -> void:
	_re_user.compile(USERNAME_RE)
	_re_region.compile(REGION_RE)
	if Config.is_server or Config.autopilot != "":
		return
	Settings.changed.connect(_on_settings_changed)
	_load_session()


# ------------------------------------------------------------------------------------------
# configuration / URL policy
# ------------------------------------------------------------------------------------------
func service_url() -> String:
	return String(Settings.get_value("online", "service_url")).strip_edges()


static func check_url(url: String) -> Dictionary:
	## {"ok", "code", "message", "base", "host", "secure"}; base = "scheme://host[:port]".
	var u: String = url.strip_edges()
	var out: Dictionary = {"ok": false, "code": "", "message": "", "base": "", "host": "", "secure": false}
	if u == "":
		out["code"] = "not_configured"
		out["message"] = "No online service is configured. Enter the service URL in Settings → Online."
		return out
	var lower: String = u.to_lower()
	var scheme: String = ""
	if lower.begins_with("https://"):
		scheme = "https"
	elif lower.begins_with("http://"):
		scheme = "http"
	else:
		out["code"] = "invalid_url"
		out["message"] = "The service URL must start with https:// (for example https://play.example.org)."
		return out
	var rest: String = u.substr(scheme.length() + 3)
	var slash: int = rest.find("/")
	var authority: String = rest if slash < 0 else rest.substr(0, slash)
	var path: String = "" if slash < 0 else rest.substr(slash)
	if path != "" and path != "/":
		out["code"] = "invalid_url"
		out["message"] = "The service URL must not contain a path — use https://host[:port]."
		return out
	if authority.contains("@") or authority.contains("?") or authority.contains("#") or authority == "":
		out["code"] = "invalid_url"
		out["message"] = "The service URL must look like https://host[:port]."
		return out
	var host: String = authority
	var port_s: String = ""
	if authority.begins_with("["):
		var close_i: int = authority.find("]")
		if close_i < 0:
			out["code"] = "invalid_url"
			out["message"] = "Malformed IPv6 address in the service URL."
			return out
		host = authority.substr(1, close_i - 1)
		var after: String = authority.substr(close_i + 1)
		if after.begins_with(":"):
			port_s = after.substr(1)
		elif after != "":
			out["code"] = "invalid_url"
			out["message"] = "The service URL must look like https://host[:port]."
			return out
	elif authority.count(":") == 1:
		host = authority.get_slice(":", 0)
		port_s = authority.get_slice(":", 1)
	elif authority.count(":") > 1:
		out["code"] = "invalid_url"
		out["message"] = "Put IPv6 addresses in brackets, e.g. http://[::1]:8080."
		return out
	if port_s != "" and (not port_s.is_valid_int() or int(port_s) < 1 or int(port_s) > 65535):
		out["code"] = "invalid_url"
		out["message"] = "The port in the service URL must be a number from 1 to 65535."
		return out
	if host == "" or host.contains(" "):
		out["code"] = "invalid_url"
		out["message"] = "The service URL has no valid host name."
		return out
	var loopback: bool = LOOPBACK_HOSTS.has(host.to_lower())
	if scheme == "http" and not loopback:
		out["code"] = "insecure_url"
		out["message"] = "Online services require HTTPS. Plain http:// is only allowed for this computer (127.0.0.1, localhost or ::1)."
		out["host"] = host
		return out
	var h_out: String = ("[%s]" % host) if host.contains(":") else host
	out["ok"] = true
	out["host"] = host
	out["secure"] = scheme == "https"
	out["base"] = "%s://%s%s" % [scheme, h_out.to_lower() if scheme == "http" else h_out, (":" + port_s) if port_s != "" else ""]
	return out


func url_status() -> Dictionary:
	return check_url(service_url())


func is_configured() -> bool:
	return bool(url_status()["ok"])


func is_logged_in() -> bool:
	return token != ""


func display_name() -> String:
	if account.is_empty():
		return ""
	return String(account.get("display_name", account.get("username", "")))


func valid_username(u: String) -> bool:
	return _re_user.search(u) != null


func valid_region(r: String) -> bool:
	return _re_region.search(r) != null


func region() -> String:
	var r: String = String(Settings.get_value("online", "region")).strip_edges().to_lower()
	return r if valid_region(r) else "local"


func _on_settings_changed(section: String) -> void:
	if section != "online" or token == "":
		return
	var chk: Dictionary = url_status()
	if not bool(chk["ok"]) or String(chk["base"]) != token_base:
		# never send a token to a different service than the one that issued it
		_clear_session("service_changed")


# ------------------------------------------------------------------------------------------
# transport
# ------------------------------------------------------------------------------------------
static func _err(status: int, code: String, message: String) -> Dictionary:
	return {"ok": false, "status": status, "data": null, "error": {"code": code, "message": message}}


func _bucket(method: int, path: String) -> String:
	var p: String = path.get_slice("?", 0)
	var parts: PackedStringArray = p.split("/", false)
	for i in range(parts.size()):
		# ids in paths (invites/{id}, matches/{id}) share one bucket per endpoint
		if parts[i].length() >= 16 and not parts[i] in ["current", "history", "status"]:
			parts[i] = "{id}"
	return "%d /%s" % [method, "/".join(parts)]


func retry_after_s(method: int, path: String) -> float:
	var until: int = int(_retry_until_ms.get(_bucket(method, path), 0))
	return maxf(0.0, float(until - Time.get_ticks_msec()) / 1000.0)


func request(method: int, path: String, body: Variant = null, auth: bool = true, timeout_s: float = DEFAULT_TIMEOUT_S) -> Dictionary:
	var chk: Dictionary = url_status()
	if not bool(chk["ok"]):
		return _finish(_err(0, String(chk["code"]), String(chk["message"])))
	if auth and token == "":
		return _finish(_err(401, "not_logged_in", "Sign in to use online features."))
	if auth and token_base != "" and token_base != String(chk["base"]):
		_clear_session("service_changed")
		return _finish(_err(401, "not_logged_in", "The service URL changed — sign in again."))
	var bucket: String = _bucket(method, path)
	var wait_ms: int = int(_retry_until_ms.get(bucket, 0)) - Time.get_ticks_msec()
	if wait_ms > 0:
		return _finish(_err(429, "rate_limited", "Too many requests — try again in %d s." % int(ceil(wait_ms / 1000.0))))
	var http := HTTPRequest.new()
	http.timeout = timeout_s
	http.max_redirects = 0          # never follow a redirect (no silent HTTPS -> HTTP downgrade)
	http.accept_gzip = true
	http.body_size_limit = 4 * 1024 * 1024
	add_child(http)
	var headers := PackedStringArray(["Accept: application/json", "User-Agent: WILDRUSH/%s" % WR.BUILD_ID])
	var data: String = ""
	if body != null:
		headers.append("Content-Type: application/json")
		data = JSON.stringify(body)
	if auth:
		headers.append("Authorization: Bearer " + token)
	var url: String = String(chk["base"]) + path
	var err: int = http.request(url, headers, method, data)
	if err != OK:
		http.queue_free()
		return _finish(_err(0, "request_failed", "Could not send the request (%s)." % error_string(err)))
	in_flight += 1
	var res: Array = await http.request_completed
	in_flight -= 1
	http.queue_free()
	var result: int = int(res[0])
	var code: int = int(res[1])
	var resp_headers: PackedStringArray = res[2]
	var raw: PackedByteArray = res[3]
	if result != HTTPRequest.RESULT_SUCCESS:
		return _finish(_net_error(result, String(chk["host"])))
	var parsed: Variant = null
	var text: String = raw.get_string_from_utf8()
	if text.strip_edges() != "":
		parsed = JSON.parse_string(text)
	if code == 429:
		var ra: float = 5.0
		for h in resp_headers:
			if h.to_lower().begins_with("retry-after:"):
				ra = clampf(float(h.get_slice(":", 1).strip_edges()), 1.0, 600.0)
		_retry_until_ms[bucket] = Time.get_ticks_msec() + int(ra * 1000.0)
	if code >= 200 and code < 300:
		return _finish({"ok": true, "status": code, "data": parsed, "error": {}})
	var e: Dictionary = {"code": "http_%d" % code, "message": "The online service answered with HTTP %d." % code}
	if parsed is Dictionary and (parsed as Dictionary).get("error") is Dictionary:
		var pe: Dictionary = (parsed as Dictionary)["error"]
		e = {"code": String(pe.get("code", e["code"])), "message": String(pe.get("message", e["message"]))}
	if code == 429:
		e["message"] = "Too many requests — try again in %d s." % int(ceil(retry_after_s(method, path)))
	if code == 401 and auth:
		_clear_session("expired")
	return _finish({"ok": false, "status": code, "data": parsed, "error": e})


func _finish(r: Dictionary) -> Dictionary:
	if not bool(r["ok"]):
		last_error = r["error"]
	return r


func _net_error(result: int, host: String) -> Dictionary:
	match result:
		HTTPRequest.RESULT_CANT_CONNECT, HTTPRequest.RESULT_CONNECTION_ERROR:
			return _err(0, "cant_connect", "Cannot reach the online service at %s. Offline play is unaffected." % host)
		HTTPRequest.RESULT_CANT_RESOLVE:
			return _err(0, "cant_resolve", "The service host name “%s” could not be resolved." % host)
		HTTPRequest.RESULT_TLS_HANDSHAKE_ERROR:
			return _err(0, "tls_error", "Secure connection to %s failed (certificate not trusted or expired)." % host)
		HTTPRequest.RESULT_TIMEOUT:
			return _err(0, "timeout", "The online service did not answer in time.")
		HTTPRequest.RESULT_NO_RESPONSE:
			return _err(0, "no_response", "The online service closed the connection without answering.")
		HTTPRequest.RESULT_REDIRECT_LIMIT_REACHED:
			return _err(0, "redirect_refused", "The service tried to redirect the request; redirects are not followed.")
		HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED:
			return _err(0, "response_too_large", "The service response was too large.")
	return _err(0, "request_failed", "The request to the online service failed (%d)." % result)


func _http_get(path: String, auth: bool = true) -> Dictionary:
	return await request(HTTPClient.METHOD_GET, path, null, auth)


func _http_post(path: String, body: Variant = null, auth: bool = true, timeout_s: float = DEFAULT_TIMEOUT_S) -> Dictionary:
	return await request(HTTPClient.METHOD_POST, path, body, auth, timeout_s)


# ------------------------------------------------------------------------------------------
# session persistence (only with "remember me"; token only — never the password)
# ------------------------------------------------------------------------------------------
func _load_session() -> void:
	if not FileAccess.file_exists(SESSION_PATH):
		return
	var cfg := ConfigFile.new()
	if cfg.load(SESSION_PATH) != OK:
		return
	var t: String = String(cfg.get_value("session", "token", ""))
	var base: String = String(cfg.get_value("session", "service", ""))
	var chk: Dictionary = url_status()
	if t == "" or not bool(chk["ok"]) or base != String(chk["base"]):
		return
	token = t
	token_base = base
	token_expires_at = String(cfg.get_value("session", "expires_at", ""))
	remember = true
	_validate_restored.call_deferred()


func _validate_restored() -> void:
	## A remembered token is checked once; 401 clears it (see request()), network errors keep it.
	var r: Dictionary = await me()
	if bool(r["ok"]):
		auth_changed.emit(true, "restored")


func _save_session() -> void:
	if not remember or token == "":
		_delete_session_file()
		return
	var cfg := ConfigFile.new()
	cfg.set_value("session", "token", token)
	cfg.set_value("session", "expires_at", token_expires_at)
	cfg.set_value("session", "service", token_base)
	if cfg.save(SESSION_PATH) != OK:
		push_warning("Online: could not write %s" % SESSION_PATH)


func _delete_session_file() -> void:
	if FileAccess.file_exists(SESSION_PATH):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SESSION_PATH))


func _clear_session(reason: String) -> void:
	var was: bool = token != ""
	token = ""
	token_base = ""
	token_expires_at = ""
	account = {}
	_delete_session_file()
	if was:
		auth_changed.emit(false, reason)
		account_changed.emit(account)


# ------------------------------------------------------------------------------------------
# accounts
# ------------------------------------------------------------------------------------------
func register(username: String, password: String, p_display_name: String = "") -> Dictionary:
	if not valid_username(username):
		return _finish(_err(422, "invalid_username", "Usernames are 3–16 letters, digits or underscores."))
	if password.length() < 8 or password.length() > 128:
		return _finish(_err(422, "invalid_password", "Passwords need 8 to 128 characters."))
	var body: Dictionary = {"username": username, "password": password}
	if p_display_name.strip_edges() != "":
		body["display_name"] = p_display_name.strip_edges()
	return await _http_post("/v1/auth/register", body, false)


func login(username: String, password: String, p_remember: bool = false) -> Dictionary:
	var r: Dictionary = await _http_post("/v1/auth/login", {"username": username, "password": password}, false)
	if not bool(r["ok"]) or not (r["data"] is Dictionary):
		return r
	var d: Dictionary = r["data"]
	token = String(d.get("token", ""))
	token_expires_at = String(d.get("expires_at", ""))
	token_base = String(url_status()["base"])
	account = d.get("account", {}) if d.get("account") is Dictionary else {}
	remember = p_remember
	_save_session()
	Settings.set_value("online", "last_username", username)
	auth_changed.emit(true, "login")
	account_changed.emit(account)
	return r


func logout() -> Dictionary:
	var r: Dictionary = {"ok": true, "status": 204, "data": null, "error": {}}
	if token != "":
		r = await _http_post("/v1/auth/logout")
	remember = false
	_clear_session("logout")
	return r


func me() -> Dictionary:
	var r: Dictionary = await _http_get("/v1/me")
	if bool(r["ok"]) and r["data"] is Dictionary:
		account = r["data"]
		account_changed.emit(account)
	return r


func profile_get() -> Dictionary:
	return await _http_get("/v1/profile")


func profile_patch(changes: Dictionary) -> Dictionary:
	return await request(HTTPClient.METHOD_PATCH, "/v1/profile", changes)


# ------------------------------------------------------------------------------------------
# parties
# ------------------------------------------------------------------------------------------
func party_create() -> Dictionary:
	return await _http_post("/v1/parties")


func party_current() -> Dictionary:
	return await _http_get("/v1/parties/current")


func party_invite(username: String) -> Dictionary:
	if not valid_username(username):
		return _finish(_err(422, "invalid_username", "Enter a valid username (3–16 letters, digits or underscores)."))
	return await _http_post("/v1/parties/current/invites", {"username": username})


func invites() -> Dictionary:
	return await _http_get("/v1/invites")


func invite_accept(invite_id: String) -> Dictionary:
	return await _http_post("/v1/invites/%s/accept" % invite_id.uri_encode())


func invite_decline(invite_id: String) -> Dictionary:
	return await _http_post("/v1/invites/%s/decline" % invite_id.uri_encode())


func party_leave() -> Dictionary:
	return await _http_post("/v1/parties/current/leave")


func party_kick(account_id: String) -> Dictionary:
	return await _http_post("/v1/parties/current/kick", {"account_id": account_id})


func party_promote(account_id: String) -> Dictionary:
	return await _http_post("/v1/parties/current/promote", {"account_id": account_id})


# ------------------------------------------------------------------------------------------
# queue / matches
# ------------------------------------------------------------------------------------------
func queue_join(mode: String, roster_prefs: Array = [], p_region: String = "", latency_ms: Dictionary = {},
		allow_bots: bool = false) -> Dictionary:
	var body: Dictionary = {"mode": mode, "region": p_region if valid_region(p_region) else region()}
	var prefs: Array = []
	for f in roster_prefs:
		if WR.FIGHTER_IDS.has(String(f)) and not prefs.has(String(f)) and prefs.size() < 5:
			prefs.append(String(f))
	body["roster_prefs"] = prefs
	if not latency_ms.is_empty():
		body["latency_ms"] = latency_ms
	body["allow_bots"] = allow_bots and mode == "casual"
	return await _http_post("/v1/queue", body)


func queue_status() -> Dictionary:
	return await _http_get("/v1/queue/status")


func queue_leave() -> Dictionary:
	return await request(HTTPClient.METHOD_DELETE, "/v1/queue")


func queue_accept() -> Dictionary:
	## "Match found → accept". The service has no accept call: accepting means taking the join
	## assignment (host, port, ticket) from the queue status; a fresh ticket is issued there while
	## the match is ready/running.
	var st: Dictionary = await queue_status()
	if not bool(st["ok"]):
		return st
	var m: Variant = (st["data"] as Dictionary).get("match") if st["data"] is Dictionary else null
	if not (m is Dictionary):
		return _finish(_err(409, "no_match", "No match is waiting for you any more."))
	var md: Dictionary = m
	if md.get("host") == null or md.get("port") == null:
		return _finish(_err(409, "allocating", "The match server is still starting — joining as soon as it is ready."))
	if md.get("ticket") == null:
		return await ticket_get(String(md.get("match_id", "")))
	return {"ok": true, "status": 200, "data": md, "error": {}}


func ticket_get(match_id: String) -> Dictionary:
	## Fresh join ticket for a running match (reconnect): POST /v1/matches/{id}/rejoin.
	return await _http_post("/v1/matches/%s/rejoin" % match_id.uri_encode())


func private_create(p_region: String = "") -> Dictionary:
	return await _http_post("/v1/private", {"region": p_region if valid_region(p_region) else region()}, true, PRIVATE_CREATE_TIMEOUT_S)


func private_join(join_code: String, role: String = "player") -> Dictionary:
	var code: String = join_code.strip_edges().to_upper().replace(" ", "").replace("-", "")
	if code.length() != 8:
		return _finish(_err(422, "invalid_join_code", "Join codes have 8 characters."))
	return await _http_post("/v1/private/join", {"join_code": code, "role": "observer" if role == "observer" else "player"})


func servers_list() -> Dictionary:
	return await _http_get("/v1/servers", false)


func history(limit: int = 20, before: String = "") -> Dictionary:
	var q: String = "?limit=%d" % clampi(limit, 1, 100)
	if before != "":
		q += "&before=" + before.uri_encode()
	return await _http_get("/v1/matches/history" + q)


func match_get(match_id: String) -> Dictionary:
	return await _http_get("/v1/matches/%s" % match_id.uri_encode())


func version() -> Dictionary:
	return await _http_get("/v1/version", false)


func health() -> Dictionary:
	return await _http_get("/healthz", false)
