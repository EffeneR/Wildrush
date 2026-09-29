class_name ServerService
extends Node
## Dedicated server ↔ control service (docs/API_CONTRACT.md): local ticket verification,
## single-use redemption, match-started and idempotent result submission, all signed with the
## per-server HMAC secret (never logged).

signal result_submitted(ok: bool, response: Dictionary)

var base_url: String = ""
var server_id: String = ""
var _secret: PackedByteArray = PackedByteArray()
var used_ticket_ids: Dictionary = {}
var enabled: bool = false


func configure(url: String, sid: String, secret: String) -> void:
	base_url = url.rstrip("/")
	server_id = sid
	_secret = secret.to_utf8_buffer()
	enabled = base_url != "" and sid != "" and not _secret.is_empty()


static func b64url_decode(s: String) -> PackedByteArray:
	var t: String = s.replace("-", "+").replace("_", "/")
	while t.length() % 4 != 0:
		t += "="
	return Marshalls.base64_to_raw(t)


static func _is_b64url(s: String) -> bool:
	for i in range(s.length()):
		var c: int = s.unicode_at(i)
		var ok: bool = (c >= 65 and c <= 90) or (c >= 97 and c <= 122) or (c >= 48 and c <= 57) or c == 45 or c == 95
		if not ok:
			return false
	return s.length() % 4 != 1   # a single trailing sextet can never be valid base64


static func b64url_encode(b: PackedByteArray) -> String:
	return Marshalls.raw_to_base64(b).replace("+", "-").replace("/", "_").replace("=", "")


static func consteq(a: PackedByteArray, b: PackedByteArray) -> bool:
	if a.size() != b.size():
		return false
	var acc: int = 0
	for i in range(a.size()):
		acc |= a[i] ^ b[i]
	return acc == 0


func verify_ticket(ticket: String, match_id: String) -> Dictionary:
	## Local verification: signature, server binding, match binding, expiry, single use.
	if ticket.length() > 2048 or ticket.count(".") != 1:
		return {"ok": false, "reason": "malformed_ticket"}
	if _secret.is_empty():
		return {"ok": false, "reason": "tickets_not_accepted"}   # direct-connect server: no service secret
	var parts: PackedStringArray = ticket.split(".")
	for part in parts:
		if part == "" or not _is_b64url(part):
			return {"ok": false, "reason": "malformed_ticket"}
	var payload_b64: String = parts[0]
	var sig: PackedByteArray = b64url_decode(parts[1])
	var crypto := Crypto.new()
	var want: PackedByteArray = crypto.hmac_digest(HashingContext.HASH_SHA256, _secret, payload_b64.to_utf8_buffer())
	if not consteq(sig, want):
		return {"ok": false, "reason": "bad_signature"}
	var pj: Variant = JSON.parse_string(b64url_decode(payload_b64).get_string_from_utf8())
	if typeof(pj) != TYPE_DICTIONARY:
		return {"ok": false, "reason": "bad_payload"}
	var p: Dictionary = pj
	if String(p.get("sid", "")) != server_id:
		return {"ok": false, "reason": "wrong_server"}
	if String(p.get("mid", "")) != match_id:
		return {"ok": false, "reason": "wrong_match"}
	if float(p.get("exp", 0)) < Time.get_unix_time_from_system():
		return {"ok": false, "reason": "ticket_expired"}
	var tid: String = String(p.get("tid", ""))
	if tid == "" or used_ticket_ids.has(tid):
		return {"ok": false, "reason": "ticket_used"}
	return {"ok": true, "tid": tid, "aid": String(p.get("aid", "")), "team": int(p.get("team", -1)),
		"role": String(p.get("role", "player"))}


func mark_used(tid: String) -> void:
	used_ticket_ids[tid] = true


func redeem(ticket_id: String, match_id: String, cb: Callable) -> void:
	_signed("POST", "/v1/servers/tickets/redeem", {"ticket_id": ticket_id, "match_id": match_id}, cb)


func post_started(match_id: String) -> void:
	_signed("POST", "/v1/matches/%s/started" % match_id, {}, func(_code: int, _d: Dictionary) -> void: pass)


func post_result(match_id: String, body: Dictionary, attempts: int = 5) -> void:
	## Idempotent on the service: safe to retry until acknowledged.
	_signed("POST", "/v1/matches/%s/result" % match_id, body, func(code: int, d: Dictionary) -> void:
		if code == 200:
			result_submitted.emit(true, d)
		elif code >= 500 or code == 0:
			if attempts > 1:
				get_tree().create_timer(2.0).timeout.connect(func() -> void: post_result(match_id, body, attempts - 1))
			else:
				result_submitted.emit(false, d)
		else:
			result_submitted.emit(false, d))


func _signed(method: String, path: String, body: Dictionary, cb: Callable) -> void:
	if not enabled:
		cb.call(0, {"error": "service_disabled"})
		return
	var body_bytes: PackedByteArray = JSON.stringify(body).to_utf8_buffer() if method != "GET" else PackedByteArray()
	var ts: String = str(int(Time.get_unix_time_from_system()))
	var hc := HashingContext.new()
	hc.start(HashingContext.HASH_SHA256)
	hc.update(body_bytes)
	var body_hash: String = hc.finish().hex_encode()
	var msg: String = "%s\n%s\n%s\n%s" % [method, path, ts, body_hash]
	var sig: String = Crypto.new().hmac_digest(HashingContext.HASH_SHA256, _secret, msg.to_utf8_buffer()).hex_encode()
	var headers := PackedStringArray(["Content-Type: application/json", "X-WR-Server: " + server_id,
		"X-WR-Timestamp: " + ts, "X-WR-Signature: " + sig])
	var req := HTTPRequest.new()
	req.timeout = 10.0
	add_child(req)
	req.request_completed.connect(func(result: int, code: int, _h: PackedStringArray, resp: PackedByteArray) -> void:
		var d: Dictionary = {}
		var parsed: Variant = JSON.parse_string(resp.get_string_from_utf8())
		if typeof(parsed) == TYPE_DICTIONARY:
			d = parsed
		req.queue_free()
		cb.call(code if result == HTTPRequest.RESULT_SUCCESS else 0, d))
	var m: int = HTTPClient.METHOD_POST if method == "POST" else HTTPClient.METHOD_GET
	var err: int = req.request_raw(base_url + path, headers, m, body_bytes)
	if err != OK:
		req.queue_free()
		cb.call(0, {"error": "request_failed"})
