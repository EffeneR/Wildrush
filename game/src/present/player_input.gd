class_name PlayerInput
extends Node
## Samples the local player's bound actions into one InputFrame per simulation tick
## (Settings bindings, KB/M + gamepad). Press edges are captured from input events so taps
## shorter than a tick are never lost; they are consumed by the next sample.

const ACTION_BITS: Dictionary = {
	"attack_light": WR.BTN_LIGHT, "attack_heavy": WR.BTN_HEAVY, "jump": WR.BTN_JUMP, "dodge": WR.BTN_DODGE,
	"guard": WR.BTN_GUARD, "skill_q": WR.BTN_Q, "skill_e": WR.BTN_E, "skill_r": WR.BTN_R,
}

var rig: CameraRig = null
var enabled: bool = true
var _taps: int = 0
var _seq: int = 0


func _input(event: InputEvent) -> void:
	if not enabled or event.is_echo():
		return
	# Mouse buttons only count while the mouse is captured (clicking UI must not attack).
	if event is InputEventMouseButton and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	for action in ACTION_BITS.keys():
		if event.is_action_pressed(String(action)):
			_taps |= int(ACTION_BITS[action])


func sample() -> InputFrame:
	var f := InputFrame.new()
	_seq += 1
	f.seq = _seq
	if rig != null:
		f.yaw = rig.yaw
		f.pitch = rig.pitch
	if not enabled:
		_taps = 0
		return f
	var mv := Vector2(Input.get_action_strength("move_right") - Input.get_action_strength("move_left"),
		Input.get_action_strength("move_forward") - Input.get_action_strength("move_back"))
	if Input.get_connected_joypads().size() > 0:
		var raw := Vector2(Input.get_joy_axis(Input.get_connected_joypads()[0], JOY_AXIS_LEFT_X),
			-Input.get_joy_axis(Input.get_connected_joypads()[0], JOY_AXIS_LEFT_Y))
		var pad: Vector2 = Settings.apply_stick_deadzone(raw, "left")
		if pad.length() > mv.length():
			mv = pad
	f.move = mv.limit_length(1.0)
	var held: int = 0
	var captured: bool = Input.mouse_mode == Input.MOUSE_MODE_CAPTURED or DisplayServer.get_name() == "headless"
	for action in ACTION_BITS.keys():
		if Input.is_action_pressed(String(action)):
			if not captured and _is_mouse_only(String(action)):
				continue
			held |= int(ACTION_BITS[action])
	f.buttons = held
	f.taps = _taps
	_taps = 0
	return f


func _is_mouse_only(action: String) -> bool:
	for ev in InputMap.action_get_events(action):
		if not (ev is InputEventMouseButton):
			return false
	return true


func clear() -> void:
	_taps = 0
