class_name InputFrame
extends RefCounted
## One tick of player intent (D-013). Clients send these — never positions, damage or scores.
## Wire format per frame (12 bytes): u32 seq, i8 move.x, i8 move.y, u16 yaw, i8 pitch, u16 buttons,
## u8 taps (buttons newly pressed this frame; lets the server merge presses of trimmed frames).

const WIRE_SIZE: int = 12

var seq: int = 0
var move: Vector2 = Vector2.ZERO   # x = right, y = forward (camera relative), |move| <= 1
var yaw: float = 0.0               # camera yaw (radians, D-003)
var pitch: float = 0.0             # camera pitch (cosmetic / spectators)
var buttons: int = 0               # WR.BTN_* held bits
var taps: int = 0                  # WR.BTN_* bits pressed on this frame


func copy() -> InputFrame:
	var c := InputFrame.new()
	c.seq = seq
	c.move = move
	c.yaw = yaw
	c.pitch = pitch
	c.buttons = buttons
	c.taps = taps
	return c


func held(bit: int) -> bool:
	return (buttons & bit) != 0


func sanitize() -> void:
	## Server-side clamp of every field (malformed values including NaN are neutralised).
	if not is_finite(move.x) or not is_finite(move.y):
		move = Vector2.ZERO
	if move.length() > 1.0:
		move = move.normalized()
	if not is_finite(yaw):
		yaw = 0.0
	yaw = wrapf(yaw, -PI, PI)
	if not is_finite(pitch):
		pitch = 0.0
	pitch = clampf(pitch, -1.4, 1.4)
	buttons &= WR.BTN_ALL_SIM
	taps &= WR.BTN_ALL_SIM


func encode(buf: StreamPeerBuffer) -> void:
	buf.put_u32(seq & 0xFFFFFFFF)
	buf.put_8(int(round(clampf(move.x, -1.0, 1.0) * 127.0)))
	buf.put_8(int(round(clampf(move.y, -1.0, 1.0) * 127.0)))
	buf.put_u16(int(round((wrapf(yaw, -PI, PI) + PI) / TAU * 65535.0)) & 0xFFFF)
	buf.put_8(int(round(clampf(pitch, -1.4, 1.4) / 1.4 * 127.0)))
	buf.put_u16(buttons & 0xFFFF)
	buf.put_u8(taps & 0xFF)


static func decode(buf: StreamPeerBuffer) -> InputFrame:
	## Returns null if the buffer is too short. Values are range-limited by construction.
	if buf.get_available_bytes() < WIRE_SIZE:
		return null
	var f := InputFrame.new()
	f.seq = buf.get_u32()
	f.move = Vector2(float(buf.get_8()) / 127.0, float(buf.get_8()) / 127.0)
	f.yaw = float(buf.get_u16()) / 65535.0 * TAU - PI
	f.pitch = float(buf.get_8()) / 127.0 * 1.4
	f.buttons = buf.get_u16()
	f.taps = buf.get_u8()
	f.sanitize()
	return f


func quantized() -> InputFrame:
	## The exact value the server will see after encode/decode (used by client prediction).
	var b := StreamPeerBuffer.new()
	encode(b)
	b.seek(0)
	return decode(b)
