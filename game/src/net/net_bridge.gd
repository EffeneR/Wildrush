extends Node
## Autoload "Net" at /root/Net. The SAME node with the SAME RPC signatures exists on the
## dedicated server and on clients, so RPC paths always match (D-013). Game logic lives in
## handlers (ServerMain on the server, ClientSession on clients); this node only moves bytes,
## authenticates, counts traffic and enforces coarse per-peer rate limits.

signal client_connected
signal client_failed(reason: String)
signal client_disconnected
signal peer_joined(id: int)
signal peer_left(id: int)

const USER_CHANNELS: int = 4
const MAX_INPUT_PPS: int = 120        # input packets per second per peer
const MAX_MSG_PPS: int = 25           # reliable messages per second per peer
# ENet drops a peer whose reliable traffic goes unacknowledged. The engine default (5 s) is
# shorter than a loading hitch on slow machines; 12 s tolerates stalls, 30 s is the hard cap.
const PEER_TIMEOUT_LIMIT: int = 32
const PEER_TIMEOUT_MIN_MS: int = 12000
const PEER_TIMEOUT_MAX_MS: int = 30000

var smp: SceneMultiplayer = null
var peer: ENetMultiplayerPeer = null
var role: String = ""                 # "" | "server" | "client"
var server_handler: Object = null
var client_handler: Object = null
var auth_payload: Dictionary = {}
var admitted: bool = false            # client: the server admitted us (authentication done on both sides)
var stats: Dictionary = {"in_bytes": 0, "out_bytes": 0, "in_packets": 0, "out_packets": 0, "dropped": 0}
var _rate: Dictionary = {}            # peer -> {"sec": int, "inp": int, "msg": int}
var _raw_peers: Dictionary = {}       # ENet-level connections that currently exist (server)


func start_server(port: int, max_clients: int, bind_addr: String = "*") -> int:
	close()
	peer = ENetMultiplayerPeer.new()
	peer.set_bind_ip(bind_addr)
	var err: int = peer.create_server(port, max_clients, USER_CHANNELS)
	if err != OK:
		push_error("Net: cannot create server on %s:%d (%s)" % [bind_addr, port, error_string(err)])
		peer = null
		return err
	_setup_smp(true)
	role = "server"
	# track raw connections so we never address a peer ENet has already dropped
	peer.peer_connected.connect(func(pid: int) -> void: _raw_peers[pid] = true)
	peer.peer_disconnected.connect(func(pid: int) -> void: _raw_peers.erase(pid))
	return OK


func start_client(host: String, port: int, payload: Dictionary) -> int:
	close()
	auth_payload = payload
	peer = ENetMultiplayerPeer.new()
	var err: int = peer.create_client(host, port, USER_CHANNELS)
	if err != OK:
		peer = null
		client_failed.emit("cannot create client: " + error_string(err))
		return err
	_setup_smp(false)
	role = "client"
	return OK


func _setup_smp(server: bool) -> void:
	smp = SceneMultiplayer.new()
	smp.server_relay = false            # clients can never address each other through the server
	smp.allow_object_decoding = false   # never decode objects from the network
	smp.auth_timeout = 15.0
	smp.auth_callback = _on_auth_server if server else _on_auth_client
	get_tree().set_multiplayer(smp)
	smp.multiplayer_peer = peer
	smp.peer_authenticating.connect(_on_peer_authenticating)
	smp.peer_authentication_failed.connect(_on_auth_failed)
	smp.peer_connected.connect(_on_peer_connected)
	smp.peer_disconnected.connect(_on_peer_disconnected)
	if not server:
		smp.connection_failed.connect(func() -> void: client_failed.emit("connection failed"))
		smp.server_disconnected.connect(func() -> void:
			role = ""
			admitted = false
			client_disconnected.emit())


func close() -> void:
	if peer != null:
		peer.close()
	peer = null
	if smp != null:
		smp.multiplayer_peer = null
	smp = null
	role = ""
	admitted = false
	_rate.clear()
	_raw_peers.clear()


func is_active() -> bool:
	return peer != null and peer.get_connection_status() != MultiplayerPeer.CONNECTION_DISCONNECTED


func disconnect_peer(id: int) -> void:
	if smp != null and role == "server" and _raw_peers.has(id):
		smp.disconnect_peer(id)


func rtt_ms(id: int) -> float:
	## Server-measured round trip time (ENet), used for bounded lag compensation (D-012).
	if peer == null or (role == "server" and not _raw_peers.has(id)):
		return 0.0
	var p: ENetPacketPeer = peer.get_peer(id)
	if p == null:
		return 0.0
	return p.get_statistic(ENetPacketPeer.PEER_ROUND_TRIP_TIME)


# ------------------------------------------------------------------------------------------
# authentication
# ------------------------------------------------------------------------------------------
func _apply_timeouts(id: int) -> void:
	if peer == null or (role == "server" and not _raw_peers.has(id)):
		return
	var pp: ENetPacketPeer = peer.get_peer(id)
	if pp != null:
		pp.set_timeout(PEER_TIMEOUT_LIMIT, PEER_TIMEOUT_MIN_MS, PEER_TIMEOUT_MAX_MS)


func _on_peer_authenticating(id: int) -> void:
	_apply_timeouts(id)
	if role == "client" and id == 1:
		smp.send_auth(1, var_to_bytes(auth_payload))


func _on_auth_server(id: int, data: PackedByteArray) -> void:
	if data.size() > Protocol.MAX_MSG_BYTES or not Protocol.valid_variant_bytes(data):
		disconnect_peer(id)
		return
	var v: Variant = bytes_to_var(data)
	if typeof(v) != TYPE_DICTIONARY or server_handler == null:
		disconnect_peer(id)
		return
	server_handler.authenticate(id, v)


func accept_auth(id: int, reply: Dictionary) -> void:
	if smp == null:
		return
	smp.send_auth(id, var_to_bytes(reply))
	smp.complete_auth(id)


func reject_auth(id: int, reason: String) -> void:
	if smp == null:
		return
	smp.send_auth(id, var_to_bytes({"ok": false, "reason": reason}))
	# give the reply a moment to flush, then drop the peer
	get_tree().create_timer(0.2).timeout.connect(func() -> void: disconnect_peer(id))


func _on_auth_client(id: int, data: PackedByteArray) -> void:
	var v: Variant = bytes_to_var(data) if data.size() <= Protocol.MAX_MSG_BYTES else null
	if typeof(v) != TYPE_DICTIONARY:
		client_failed.emit("bad auth reply")
		close()
		return
	var d: Dictionary = v
	if bool(d.get("ok", false)):
		if client_handler != null and client_handler.has_method("on_auth_reply"):
			client_handler.on_auth_reply(d)
		smp.complete_auth(id)
	else:
		client_failed.emit(String(d.get("reason", "rejected")))
		close()


func _on_auth_failed(id: int) -> void:
	if role == "server" and server_handler != null and server_handler.has_method("on_auth_failed"):
		server_handler.on_auth_failed(id)


func _on_peer_connected(id: int) -> void:
	if role == "client" and id == 1:
		admitted = true
		client_connected.emit()
	elif role == "server":
		peer_joined.emit(id)
		if server_handler != null:
			server_handler.on_peer_connected(id)


func _on_peer_disconnected(id: int) -> void:
	_rate.erase(id)
	if role == "server":
		peer_left.emit(id)
		if server_handler != null:
			server_handler.on_peer_disconnected(id)


func _allow(id: int, kind: String, limit: int) -> bool:
	var sec: int = Time.get_ticks_msec() / 1000
	var r: Dictionary = _rate.get(id, {"sec": sec, "inp": 0, "msg": 0})
	if int(r["sec"]) != sec:
		r = {"sec": sec, "inp": 0, "msg": 0}
	r[kind] = int(r[kind]) + 1
	_rate[id] = r
	if int(r[kind]) > limit:
		stats["dropped"] = int(stats["dropped"]) + 1
		if server_handler != null and server_handler.has_method("on_violation"):
			server_handler.on_violation(id, "rate_" + kind)
		return false
	return true


# ------------------------------------------------------------------------------------------
# RPC endpoints (identical on both sides)
# ------------------------------------------------------------------------------------------
@rpc("any_peer", "call_remote", "unreliable_ordered", 1)
func c_input(data: PackedByteArray) -> void:
	if role != "server" or server_handler == null:
		return
	var id: int = multiplayer.get_remote_sender_id()
	stats["in_bytes"] = int(stats["in_bytes"]) + data.size()
	stats["in_packets"] = int(stats["in_packets"]) + 1
	if not _allow(id, "inp", MAX_INPUT_PPS):
		return
	server_handler.on_input(id, data)


@rpc("any_peer", "call_remote", "reliable", 0)
func c_msg(data: PackedByteArray) -> void:
	if role != "server" or server_handler == null:
		return
	var id: int = multiplayer.get_remote_sender_id()
	stats["in_bytes"] = int(stats["in_bytes"]) + data.size()
	stats["in_packets"] = int(stats["in_packets"]) + 1
	if not _allow(id, "msg", MAX_MSG_PPS):
		return
	var d: Dictionary = Protocol.unpack(data)
	if d.is_empty() or not Protocol.validate_client_msg(d):
		stats["dropped"] = int(stats["dropped"]) + 1
		if server_handler.has_method("on_violation"):
			server_handler.on_violation(id, "bad_msg")
		return
	server_handler.on_msg(id, d)


@rpc("authority", "call_remote", "unreliable_ordered", 2)
func s_snapshot(data: PackedByteArray) -> void:
	if role != "client" or client_handler == null:
		return
	stats["in_bytes"] = int(stats["in_bytes"]) + data.size()
	stats["in_packets"] = int(stats["in_packets"]) + 1
	client_handler.on_snapshot(data)


@rpc("authority", "call_remote", "reliable", 0)
func s_msg(data: PackedByteArray) -> void:
	if role != "client" or client_handler == null:
		return
	stats["in_bytes"] = int(stats["in_bytes"]) + data.size()
	stats["in_packets"] = int(stats["in_packets"]) + 1
	var v: Variant = bytes_to_var(data) if data.size() <= 262144 else null
	if typeof(v) == TYPE_DICTIONARY:
		client_handler.on_server_msg(v)


# ------------------------------------------------------------------------------------------
# senders
# ------------------------------------------------------------------------------------------
func send_inputs(frames: Array) -> void:
	if role != "client" or smp == null or not admitted:
		return
	var data: PackedByteArray = Protocol.encode_inputs(frames)
	_count_out(data)
	c_input.rpc_id(1, data)


func send_msg(d: Dictionary) -> void:
	if role != "client" or smp == null or not admitted:
		return
	var data: PackedByteArray = Protocol.pack(d)
	_count_out(data)
	c_msg.rpc_id(1, data)


func send_raw_msg(data: PackedByteArray) -> void:
	## Test hook: sends arbitrary bytes on the message channel (used by security tests).
	if role == "client" and smp != null and admitted:
		c_msg.rpc_id(1, data)


func send_raw_input(data: PackedByteArray) -> void:
	if role == "client" and smp != null and admitted:
		c_input.rpc_id(1, data)


func _peer_ok(id: int) -> bool:
	## True only while the ENet peer is fully connected (disconnect signals can lag behind).
	if peer == null or (role == "server" and not _raw_peers.has(id)):
		return false
	var pp: ENetPacketPeer = peer.get_peer(id)
	return pp != null and pp.get_state() == ENetPacketPeer.STATE_CONNECTED


func send_snapshot(id: int, data: PackedByteArray) -> void:
	if role != "server" or smp == null or not _peer_ok(id):
		return
	_count_out(data)
	s_snapshot.rpc_id(id, data)


func send_to(id: int, d: Dictionary) -> void:
	if role != "server" or smp == null or not _peer_ok(id):
		return
	var data: PackedByteArray = var_to_bytes(d)
	_count_out(data)
	s_msg.rpc_id(id, data)


func _count_out(data: PackedByteArray) -> void:
	stats["out_bytes"] = int(stats["out_bytes"]) + data.size()
	stats["out_packets"] = int(stats["out_packets"]) + 1
