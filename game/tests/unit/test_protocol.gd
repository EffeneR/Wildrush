extends WRTest
## Protocol codec, validation and RPC surface (D-013, G8 unit level).


func test_rpc_surface_matches_on_both_roles() -> void:
	## Server and client run the same autoload script at /root/Net, so paths and signatures match.
	var net: Node = get_node("/root/Net")
	assert_true(net != null, "/root/Net exists")
	for m in ["c_input", "c_msg", "s_snapshot", "s_msg"]:
		assert_true(net.has_method(m), "RPC method " + m)
	var cfg: Variant = (net.get_script() as Script).get_rpc_config()   # RPCs declared with @rpc in the script
	assert_true(typeof(cfg) == TYPE_DICTIONARY and (cfg as Dictionary).size() >= 4, "RPC configs registered")
	if typeof(cfg) == TYPE_DICTIONARY:
		var d: Dictionary = cfg
		assert_eq(int(d["s_msg"]["rpc_mode"]), MultiplayerAPI.RPC_MODE_AUTHORITY, "server->client RPCs are authority-only")
		assert_eq(int(d["s_snapshot"]["rpc_mode"]), MultiplayerAPI.RPC_MODE_AUTHORITY)
		assert_eq(int(d["c_input"]["transfer_mode"]), MultiplayerPeer.TRANSFER_MODE_UNRELIABLE_ORDERED, "inputs unreliable-ordered")
		assert_eq(int(d["c_msg"]["transfer_mode"]), MultiplayerPeer.TRANSFER_MODE_RELIABLE, "lifecycle reliable")
		assert_ne(int(d["c_input"]["channel"]), int(d["s_snapshot"]["channel"]), "movement channels separated")


func test_input_codec_roundtrip_and_limits() -> void:
	var frames: Array = []
	for i in range(4):
		var f := InputFrame.new()
		f.seq = 1000 + i
		f.move = Vector2(0.5, -1.0)
		f.yaw = 1.234
		f.buttons = WR.BTN_LIGHT | WR.BTN_GUARD
		f.taps = WR.BTN_LIGHT
		frames.append(f)
	var data: PackedByteArray = Protocol.encode_inputs(frames)
	assert_eq(data.size(), 1 + 4 * InputFrame.WIRE_SIZE, "4 redundant frames")
	var dec: Array = Protocol.decode_inputs(data)
	assert_eq(dec.size(), 4)
	var d0: InputFrame = dec[0]
	assert_eq(d0.seq, 1000)
	assert_near(d0.yaw, 1.234, 0.001)
	assert_eq(d0.buttons, WR.BTN_LIGHT | WR.BTN_GUARD)
	assert_eq(d0.taps, WR.BTN_LIGHT)
	# malformed: wrong length, too many frames, empty
	assert_eq(Protocol.decode_inputs(data.slice(0, data.size() - 1)).size(), 0, "truncated rejected")
	var b := StreamPeerBuffer.new()
	b.put_u8(5)
	for i in range(5):
		InputFrame.new().encode(b)
	assert_eq(Protocol.decode_inputs(b.data_array).size(), 0, "more than 4 frames rejected")
	assert_eq(Protocol.decode_inputs(PackedByteArray()).size(), 0, "empty rejected")


func test_input_sanitize_nan_and_ranges() -> void:
	var f := InputFrame.new()
	f.move = Vector2(NAN, INF)
	f.yaw = NAN
	f.pitch = INF
	f.buttons = 0xFFFF
	f.sanitize()
	assert_eq(f.move, Vector2.ZERO, "NaN move neutralised")
	assert_eq(f.yaw, 0.0)
	assert_eq(f.pitch, 0.0)
	assert_eq(f.buttons, WR.BTN_ALL_SIM, "unknown button bits stripped")
	var g := InputFrame.new()
	g.move = Vector2(5, 5)
	g.sanitize()
	assert_near(g.move.length(), 1.0, 1e-5, "move clamped to unit length")


func test_client_message_validation_rejects_forgeries() -> void:
	assert_false(Protocol.validate_client_msg({"t": "damage", "target": 0, "amount": 999}), "forged damage type")
	assert_false(Protocol.validate_client_msg({"t": "score", "team": 0, "points": 250}), "forged score type")
	assert_false(Protocol.validate_client_msg({"t": "pick", "f": "wolf"}), "unknown fighter")
	assert_false(Protocol.validate_client_msg({"t": "pick", "f": "nyx", "entity": 3}), "extra fields")
	assert_false(Protocol.validate_client_msg({"t": "chat", "text": "x".repeat(500), "team": false}), "oversize chat")
	assert_false(Protocol.validate_client_msg({"t": "ping", "pos": Vector3(NAN, 0, 0), "kind": "enemy"}), "NaN ping")
	assert_false(Protocol.validate_client_msg({"t": "ping", "pos": Vector3(1, 0, 1), "kind": "nuke"}), "unknown ping kind")
	assert_false(Protocol.validate_client_msg({"t": "swap_req", "slot": 99}), "slot out of range")
	assert_true(Protocol.validate_client_msg({"t": "pick", "f": "nyx"}))
	assert_true(Protocol.validate_client_msg({"t": "chat", "text": "on my way", "team": true}))
	assert_true(Protocol.validate_client_msg({"t": "ping", "pos": Vector3(1, 0, 1), "kind": "enemy"}))
	assert_eq(Protocol.unpack(PackedByteArray([1, 2, 3])).size(), 0, "garbage bytes rejected")
	var big := PackedByteArray()
	big.resize(4096)
	assert_eq(Protocol.unpack(big).size(), 0, "oversize payload rejected")
	assert_eq(Protocol.sanitize_chat("hi\u0007there\n"), "hithere", "control characters stripped")


func test_snapshot_roundtrip() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "nyx", "bruno", 2.0)
	var a: FighterBody = p[0]
	await hold(sim, {a.entity_id: frame(PI, 0, Vector2(0, 1)), p[1].entity_id: frame(0.0)}, 10)
	var fs: Array = [Protocol.fighter_view_state(a, 0, true, sim.tick), Protocol.fighter_view_state(p[1], 0, false, sim.tick)]
	var own := {"packed": a.st.to_packed(), "pos": a.global_position, "vel": a.velocity, "on_floor": true}
	var m: Dictionary = sim.snapshot_match()
	var data: PackedByteArray = Protocol.encode_snapshot(sim.tick, 77, 2, m, [{"e": 0, "alive": true, "respawn_s": 0}], fs, own)
	var s: Dictionary = Protocol.decode_snapshot(data)
	assert_eq(int(s["tick"]), sim.tick)
	assert_eq(int(s["ack"]), 77)
	assert_eq((s["fighters"] as Array).size(), 2)
	assert_near(((s["fighters"][0]["pos"]) as Vector3).distance_to(a.global_position), 0.0, 0.002, "position mm precision")
	assert_true(s.has("own"), "own state decoded")
	var restored := FighterState.new()
	restored.from_dict(s["own"], a.def)
	assert_eq(restored.health, a.st.health)
	assert_eq(restored.stamina, a.st.stamina)
	assert_eq(restored.last_input_seq, a.st.last_input_seq)
	print("snapshot bytes: %d (2 fighters + own state %d)" % [data.size(), (own["packed"] as PackedByteArray).size()])
	assert_lt(float(data.size()), 700.0, "compact snapshot")


func test_feint_is_disguised_in_snapshots() -> void:
	var sim: MatchSim = await make_sim()
	var p: Array = spawn_pair(sim, "vex", "bruno", 3.0)
	var v: FighterBody = p[0]
	await hold(sim, {v.entity_id: frame(PI), p[1].entity_id: frame(0.0)}, 3)
	await run(sim, 1, func(_i: int) -> Dictionary: return {v.entity_id: frame(PI, WR.BTN_Q), p[1].entity_id: frame(0.0)})
	var vs: Dictionary = Protocol.fighter_view_state(v, 1, false, sim.tick)
	assert_eq(Protocol.clip_name(int(vs["clip"])), "heavy", "opponents see the heavy wind-up during a feint")


func test_untrusted_bytes_prevalidated_without_engine_errors() -> void:
	## Everything a client can legitimately send passes; malformed input is rejected silently.
	for m in [{"t": "pick", "f": "nyx"}, {"t": "chat", "text": "héllo · ok", "team": true},
			{"t": "ping", "pos": Vector3(1.5, 0, -3.25), "kind": "enemy"}, {"t": "admin", "cmd": "bots", "args": {"enabled": true, "difficulty": "hard"}},
			{"t": "swap_answer", "from": 3, "accept": false}, {"t": "ready", "v": true}]:
		var b: PackedByteArray = Protocol.pack(m)
		assert_true(Protocol.valid_variant_bytes(b), "valid: %s" % str(m))
		assert_eq(Protocol.unpack(b), m, "round trip: %s" % str(m))
	var good: PackedByteArray = Protocol.pack({"t": "chat", "text": "abc", "team": false})
	assert_false(Protocol.valid_variant_bytes(good.slice(0, good.size() - 3)), "truncated")
	assert_false(Protocol.valid_variant_bytes(PackedByteArray([1, 2, 3, 4, 5, 6, 7])), "garbage")
	assert_false(Protocol.valid_variant_bytes(var_to_bytes(Color(1, 0, 0))), "unsupported type")
	assert_false(Protocol.valid_variant_bytes(var_to_bytes({"t": PackedByteArray([1, 2])})), "unsupported nested type")
	var bad_utf8 := PackedByteArray([27, 0, 0, 0, 1, 0, 0, 0, 4, 0, 0, 0, 1, 0, 0, 0, 116, 0, 0, 0, 4, 0, 0, 0, 2, 0, 0, 0, 0xC3, 0x28, 0, 0])
	assert_false(Protocol.valid_variant_bytes(bad_utf8), "invalid UTF-8 in a string")
	var deep: Variant = {"t": "x"}
	for i in range(8):
		deep = {"t": "x", "n": deep}
	assert_false(Protocol.valid_variant_bytes(var_to_bytes(deep)), "nesting depth limited")
	var many: Dictionary = {"t": "x"}
	for i in range(100):
		many["k%d" % i] = i
	assert_false(Protocol.valid_variant_bytes(var_to_bytes(many)), "entry count limited")
