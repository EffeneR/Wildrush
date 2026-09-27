class_name Protocol
extends RefCounted
## Wire protocol (D-013). Client→server: input packets (binary) and small validated
## Dictionary messages. Server→client: binary snapshots and Dictionary messages.
## Protocol/build identity is checked during SceneMultiplayer authentication.

const MAX_INPUT_BYTES: int = 96
const MAX_MSG_BYTES: int = 1024
const MAX_CHAT_CHARS: int = 120
const INPUT_REDUNDANCY: int = 4
const SNAPSHOT_EVERY: int = 3            # 60 Hz / 3 = 20 Hz
const INTERP_DELAY_TICKS: int = 6        # 100 ms

const PING_KINDS: Array[String] = ["attack", "defend", "help", "enemy", "on_my_way"]
const CLIENT_MSG_TYPES: Array[String] = ["pick", "swap_req", "swap_answer", "lock", "ready", "chat", "ping",
	"rematch", "admin", "leave", "spectate"]

# snapshot fighter flags
const F_ALIVE: int = 1
const F_PRESENT: int = 2
const F_GUARD: int = 4
const F_PROTECTED: int = 8
const F_GROUNDED: int = 16
const F_CR: int = 32
const F_BOT: int = 64
const F_STANCE: int = 128

static var _clips: PackedStringArray = PackedStringArray()
static var _clip_index: Dictionary = {}


static func clip_table() -> PackedStringArray:
	if _clips.is_empty():
		var names: Dictionary = {}
		for n in ["idle", "walk_f", "walk_b", "walk_l", "walk_r", "run_f", "run_b", "run_l", "run_r", "turn_l", "turn_r",
				"jump_start", "jump_air", "jump_fall", "jump_land", "dodge_f", "dodge_b", "dodge_l", "dodge_r",
				"guard_enter", "guard_hold", "guard_exit", "guard_block", "guard_break", "light_s", "light_l", "light_r",
				"light_air", "heavy", "hit_front", "hit_back", "hit_heavy", "stagger", "knockdown", "getup", "grabbed",
				"knockout", "respawn", "victory", "defeat", "perch_climb"]:
			names[n] = true
		for fid in WR.FIGHTER_IDS:
			var d: FighterDef = Tuning.fighter(fid)
			if d == null:
				continue
			for a in d.actions.values():
				var ad: ActionDef = a
				if ad.clip != "":
					names[ad.clip] = true
				for c in ad.clips.values():
					if c is Array and not (c as Array).is_empty():
						names[String(c[0])] = true
		var arr: Array = names.keys()
		arr.sort()
		_clips = PackedStringArray(arr)
		for i in range(_clips.size()):
			_clip_index[_clips[i]] = i
	return _clips


static func clip_id(name: String) -> int:
	clip_table()
	return int(_clip_index.get(name, 0xFFFF))


static func clip_name(id: int) -> String:
	var t: PackedStringArray = clip_table()
	return t[id] if id >= 0 and id < t.size() else ""


# ------------------------------------------------------------------------------------------
# inputs (client -> server, unreliable ordered, redundant)
# ------------------------------------------------------------------------------------------
static func encode_inputs(frames: Array) -> PackedByteArray:
	var b := StreamPeerBuffer.new()
	var n: int = mini(frames.size(), INPUT_REDUNDANCY)
	b.put_u8(n)
	for i in range(frames.size() - n, frames.size()):
		(frames[i] as InputFrame).encode(b)
	return b.data_array


static func decode_inputs(data: PackedByteArray) -> Array:
	## Returns [] for malformed payloads (wrong size, too many frames).
	if data.size() < 1 or data.size() > MAX_INPUT_BYTES:
		return []
	var b := StreamPeerBuffer.new()
	b.data_array = data
	var n: int = b.get_u8()
	if n < 1 or n > INPUT_REDUNDANCY or data.size() != 1 + n * InputFrame.WIRE_SIZE:
		return []
	var out: Array = []
	for i in range(n):
		var f: InputFrame = InputFrame.decode(b)
		if f == null:
			return []
		out.append(f)
	return out


# ------------------------------------------------------------------------------------------
# dictionary messages
# ------------------------------------------------------------------------------------------
static func pack(d: Dictionary) -> PackedByteArray:
	return var_to_bytes(d)


static func unpack(data: PackedByteArray) -> Dictionary:
	## Safe decode: size-limited, no object decoding, must be a Dictionary with a String "t".
	if data.size() < 4 or data.size() > MAX_MSG_BYTES:
		return {}
	var v: Variant = bytes_to_var(data)
	if typeof(v) != TYPE_DICTIONARY:
		return {}
	var d: Dictionary = v
	if typeof(d.get("t")) != TYPE_STRING:
		return {}
	return d


static func validate_client_msg(d: Dictionary) -> bool:
	var t: String = String(d.get("t", ""))
	if not CLIENT_MSG_TYPES.has(t):
		return false
	for k in d.keys():
		if typeof(k) != TYPE_STRING:
			return false
	match t:
		"pick":
			return typeof(d.get("f")) == TYPE_STRING and WR.FIGHTER_IDS.has(String(d["f"])) and d.size() == 2
		"swap_req":
			return typeof(d.get("slot")) == TYPE_INT and int(d["slot"]) >= 0 and int(d["slot"]) < WR.TEAM_SIZE and d.size() == 2
		"swap_answer":
			return typeof(d.get("from")) == TYPE_INT and typeof(d.get("accept")) == TYPE_BOOL and d.size() == 3
		"lock", "leave":
			return d.size() == 1
		"ready", "rematch":
			return typeof(d.get("v")) == TYPE_BOOL and d.size() == 2
		"spectate":
			return typeof(d.get("e")) == TYPE_INT and d.size() == 2
		"chat":
			return typeof(d.get("text")) == TYPE_STRING and String(d["text"]).length() <= MAX_CHAT_CHARS \
				and typeof(d.get("team")) == TYPE_BOOL and d.size() == 3
		"ping":
			if typeof(d.get("pos")) != TYPE_VECTOR3 or typeof(d.get("kind")) != TYPE_STRING or d.size() != 3:
				return false
			var p: Vector3 = d["pos"]
			return MathX.is_finite_vec3(p) and absf(p.x) < 200.0 and absf(p.y) < 50.0 and absf(p.z) < 200.0 \
				and PING_KINDS.has(String(d["kind"]))
		"admin":
			return typeof(d.get("cmd")) == TYPE_STRING and typeof(d.get("args")) == TYPE_DICTIONARY and d.size() == 3 \
				and String(d["cmd"]).length() <= 24
	return false


static func sanitize_chat(text: String) -> String:
	var out: String = ""
	for ch in text:
		var c: int = ch.unicode_at(0)
		if c >= 32 and c != 127:
			out += ch
	return out.strip_edges().substr(0, MAX_CHAT_CHARS)


# ------------------------------------------------------------------------------------------
# snapshots (server -> client, unreliable ordered)
# ------------------------------------------------------------------------------------------
static func encode_snapshot(server_tick: int, ack_seq: int, qdepth: int, m: Dictionary, roster: Array,
		fighters: Array, own: Dictionary) -> PackedByteArray:
	## roster: [{e, alive, respawn_s}] for ALL fighters (public status);
	## fighters: visible fighters with full presentation state; own: local reconciliation state.
	var b := StreamPeerBuffer.new()
	b.put_u8(1)
	b.put_u32(server_tick)
	b.put_u32(ack_seq)
	b.put_u8(clampi(qdepth, 0, 255))
	b.put_u8(int(m.get("phase", 0)))
	b.put_u32(int(m.get("tick", 0)))
	b.put_u16(int(m["scores"][0]))
	b.put_u16(int(m["scores"][1]))
	b.put_u8(_zone_idx(String(m.get("zone", ""))))
	b.put_u8(_zone_idx(String(m.get("next", ""))))
	b.put_u8(int(m.get("state", 0)))
	b.put_8(int(m.get("ctrl", -1)))
	b.put_u32(int(m.get("rot", 0)))
	b.put_u8((1 if bool(m.get("sd", false)) else 0) | (2 if bool(m.get("final", false)) else 0))
	b.put_u32(int(m.get("countdown_until", -1)) & 0xFFFFFFFF)
	b.put_u8(roster.size())
	for r in roster:
		b.put_u8(int(r["e"]))
		b.put_u8(1 if bool(r["alive"]) else 0)
		b.put_u8(clampi(int(r["respawn_s"]), 0, 255))
	b.put_u8(fighters.size())
	for f in fighters:
		b.put_u8(int(f["e"]))
		b.put_u8(int(f["flags"]))
		var p: Vector3 = f["pos"]
		b.put_32(int(round(p.x * 1000.0)))
		b.put_32(int(round(p.y * 1000.0)))
		b.put_32(int(round(p.z * 1000.0)))
		b.put_u16(int(round((wrapf(float(f["yaw"]), -PI, PI) + PI) / TAU * 65535.0)) & 0xFFFF)
		var v: Vector3 = f["vel"]
		b.put_16(clampi(int(round(v.x * 100.0)), -32767, 32767))
		b.put_16(clampi(int(round(v.y * 100.0)), -32767, 32767))
		b.put_16(clampi(int(round(v.z * 100.0)), -32767, 32767))
		b.put_u16(clampi(int(round(float(f["hp"]) * 10.0)), 0, 65535))
		b.put_u8(clampi(int(round(float(f["st"]))), 0, 255))
		b.put_u16(int(f["clip"]) & 0xFFFF)
		b.put_u16(clampi(int(round(float(f["ct"]) * 1000.0)), 0, 65535))
		b.put_u8(int(f["ctrl"]))
	if own.is_empty():
		b.put_u16(0)
	else:
		var ob: PackedByteArray = var_to_bytes(own)
		b.put_u16(ob.size())
		b.put_data(ob)
	return b.data_array


static func decode_snapshot(data: PackedByteArray) -> Dictionary:
	if data.size() < 40:
		return {}
	var b := StreamPeerBuffer.new()
	b.data_array = data
	if b.get_u8() != 1:
		return {}
	var s: Dictionary = {}
	s["tick"] = b.get_u32()
	s["ack"] = b.get_u32()
	s["qdepth"] = b.get_u8()
	var m: Dictionary = {}
	m["phase"] = b.get_u8()
	m["tick"] = b.get_u32()
	m["scores"] = [b.get_u16(), b.get_u16()]
	m["zone"] = _zone_name(b.get_u8())
	m["next"] = _zone_name(b.get_u8())
	m["state"] = b.get_u8()
	m["ctrl"] = b.get_8()
	m["rot"] = b.get_u32()
	var fl: int = b.get_u8()
	m["sd"] = (fl & 1) != 0
	m["final"] = (fl & 2) != 0
	var cu: int = b.get_u32()
	m["countdown_until"] = -1 if cu == 0xFFFFFFFF else cu
	s["match"] = m
	var rn: int = b.get_u8()
	var roster: Array = []
	for i in range(rn):
		if b.get_available_bytes() < 3:
			return {}
		roster.append({"e": b.get_u8(), "alive": b.get_u8() == 1, "respawn_s": b.get_u8()})
	s["roster"] = roster
	var n: int = b.get_u8()
	var fs: Array = []
	for i in range(n):
		if b.get_available_bytes() < 33:
			return {}
		var f: Dictionary = {}
		f["e"] = b.get_u8()
		f["flags"] = b.get_u8()
		f["pos"] = Vector3(float(b.get_32()) / 1000.0, float(b.get_32()) / 1000.0, float(b.get_32()) / 1000.0)
		f["yaw"] = float(b.get_u16()) / 65535.0 * TAU - PI
		f["vel"] = Vector3(float(b.get_16()) / 100.0, float(b.get_16()) / 100.0, float(b.get_16()) / 100.0)
		f["hp"] = float(b.get_u16()) / 10.0
		f["st"] = float(b.get_u8())
		f["clip"] = b.get_u16()
		f["ct"] = float(b.get_u16()) / 1000.0
		f["ctrl"] = b.get_u8()
		fs.append(f)
	s["fighters"] = fs
	if b.get_available_bytes() >= 2:
		var olen: int = b.get_u16()
		if olen > 0 and b.get_available_bytes() >= olen:
			var res: Array = b.get_data(olen)
			var v: Variant = bytes_to_var(res[1])
			if typeof(v) == TYPE_DICTIONARY:
				s["own"] = v
	return s


static func _zone_idx(z: String) -> int:
	match z:
		"A": return 0
		"B": return 1
		"C": return 2
	return 255


static func _zone_name(i: int) -> String:
	match i:
		0: return "A"
		1: return "B"
		2: return "C"
	return ""


static func fighter_view_state(f: FighterBody, viewer_team: int, full: bool, tick: int) -> Dictionary:
	## Presentation state of a fighter as sent in snapshots. Feints show their display clip.
	var clip: String = "idle"
	var ct: float = 0.0
	if f.st.alive and f.st.act != null:
		var an: Array = Behaviors.of(f.st.act).anim(f)
		clip = String(an[0])
		ct = float(an[1])
	var flags: int = 0
	if f.st.alive:
		flags |= F_ALIVE
	if f.present:
		flags |= F_PRESENT
	if f.st.guarding:
		flags |= F_GUARD
	if f.st.spawn_protected:
		flags |= F_PROTECTED
	if f.st.grounded:
		flags |= F_GROUNDED
	if f.st.has_cr(tick):
		flags |= F_CR
	if f.is_bot:
		flags |= F_BOT
	if f.st.act != null and Behaviors.of(f.st.act).is_guarding(f):
		flags |= F_STANCE
	return {"e": f.entity_id, "flags": flags, "pos": f.global_position, "yaw": f.st.yaw, "vel": f.velocity,
		"hp": f.st.health, "st": f.st.stamina if (full or f.team == viewer_team) else 0.0,
		"clip": clip_id(clip), "ct": ct, "ctrl": f.st.ctrl}
