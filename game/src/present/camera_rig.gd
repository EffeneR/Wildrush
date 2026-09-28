class_name CameraRig
extends Node3D
## Third-person over-the-shoulder camera (spec §5/§11). Yaw/pitch come from mouse or right
## stick; the camera yaw is the player's input yaw (movement is camera-relative, D-006).
## A sphere cast against CAMERA_BLOCK keeps the camera out of walls. Shake is opt-in
## (accessibility: Settings access/camera_shake, default 0).

signal look_changed(yaw: float, pitch: float)

const PITCH_MIN: float = -0.95
const PITCH_MAX: float = 0.62
const DIST: float = 3.6
const DIST_GUARD: float = 3.2
const HEIGHT: float = 1.62
const SHOULDER: float = 0.55
const COLLISION_RADIUS: float = 0.22

var yaw: float = 0.0
var pitch: float = -0.18
var target: Node3D = null            # FighterView (render position)
var target_height: float = 1.7
var camera: Camera3D
var mouse_captured: bool = false
var input_enabled: bool = true
var free_look_speed: float = 12.0    # spectator free camera (m/s)
var spectator_free: bool = false
var _dist: float = DIST
var _shake: float = 0.0
var _shake_t: float = 0.0
var _focus: Vector3 = Vector3.ZERO
var _shoulder_side: float = 1.0
var _exclude: Array[RID] = []


func _ready() -> void:
	camera = Camera3D.new()
	camera.name = "Camera"
	camera.near = 0.05
	camera.far = 400.0
	add_child(camera)
	camera.current = true
	_apply_settings("display")
	Settings.changed.connect(_apply_settings)


func _apply_settings(section: String) -> void:
	if section == "display" and camera != null:
		camera.fov = clampf(float(Settings.get_value("display", "fov")), 60.0, 100.0)


func set_target(t: Node3D, height: float) -> void:
	target = t
	target_height = height
	if t != null:
		_focus = t.global_position + Vector3(0, HEIGHT * height / 1.7, 0)


func capture_mouse(on: bool) -> void:
	mouse_captured = on
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if on else Input.MOUSE_MODE_VISIBLE


func add_shake(amount: float) -> void:
	var scale: float = clampf(float(Settings.get_value("access", "camera_shake")), 0.0, 1.0)
	if bool(Settings.get_value("access", "reduced_effects")):
		scale *= 0.3
	_shake = clampf(_shake + amount * scale, 0.0, 1.0)


func _unhandled_input(event: InputEvent) -> void:
	if not input_enabled or not mouse_captured:
		return
	if event is InputEventMouseMotion:
		var m := event as InputEventMouseMotion
		var sens: float = float(Settings.get_value("controls", "mouse_sensitivity")) * 0.01
		var inv: float = -1.0 if bool(Settings.get_value("controls", "invert_y")) else 1.0
		yaw = wrapf(yaw - m.relative.x * sens, -PI, PI)
		pitch = clampf(pitch - m.relative.y * sens * inv, PITCH_MIN, PITCH_MAX)
		look_changed.emit(yaw, pitch)


func _process(dt: float) -> void:
	if input_enabled:
		var stick := Vector2(Input.get_action_strength("look_right") - Input.get_action_strength("look_left"),
			Input.get_action_strength("look_down") - Input.get_action_strength("look_up"))
		stick = Settings.apply_stick_deadzone(stick, "right")
		if stick.length() > 0.0:
			var ps: float = float(Settings.get_value("controls", "pad_sensitivity"))
			var inv: float = -1.0 if bool(Settings.get_value("controls", "invert_y")) else 1.0
			# response curve: fine aim near centre, fast turns at full tilt
			var curved: Vector2 = stick * stick.length()
			yaw = wrapf(yaw - curved.x * ps * dt, -PI, PI)
			pitch = clampf(pitch - curved.y * ps * 0.6 * dt * inv, PITCH_MIN, PITCH_MAX)
	if spectator_free:
		_free_fly(dt)
		return
	if target == null or not is_instance_valid(target):
		return
	var guard: bool = Input.is_action_pressed("guard") and input_enabled
	_dist = lerpf(_dist, DIST_GUARD if guard else DIST, 1.0 - exp(-6.0 * dt))
	var want_focus: Vector3 = target.global_position + Vector3(0, HEIGHT * target_height / 1.7, 0)
	# smooth vertical follow (landing / stairs), crisp horizontal follow
	_focus.x = want_focus.x
	_focus.z = want_focus.z
	_focus.y = lerpf(_focus.y, want_focus.y, 1.0 - exp(-12.0 * dt))
	var basis_yaw := Basis(Vector3.UP, yaw)
	var right: Vector3 = basis_yaw.x
	var dir: Vector3 = (basis_yaw * Basis(Vector3.RIGHT, pitch)).z   # camera looks along -z
	var pivot: Vector3 = _focus + right * SHOULDER * _shoulder_side * 0.6
	var desired: Vector3 = pivot + dir * _dist + right * SHOULDER * _shoulder_side * 0.4
	var final_pos: Vector3 = _collide(pivot, desired)
	global_position = final_pos
	var look_at_pt: Vector3 = final_pos - dir * 10.0
	if final_pos.distance_to(look_at_pt) > 0.01:
		look_at(look_at_pt, Vector3.UP)
	_apply_shake(dt)


func _collide(from: Vector3, to: Vector3) -> Vector3:
	var space: PhysicsDirectSpaceState3D = get_world_3d().direct_space_state
	if space == null:
		return to
	var shape := SphereShape3D.new()
	shape.radius = COLLISION_RADIUS
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.transform = Transform3D(Basis(), from)
	q.motion = to - from
	q.collision_mask = WR.LAYER_CAMERA_BLOCK
	q.exclude = _exclude
	var r: PackedFloat32Array = space.cast_motion(q)
	if r.size() == 2 and r[0] < 1.0:
		return from + (to - from) * maxf(0.0, r[0] - 0.02)
	return to


func _apply_shake(dt: float) -> void:
	if _shake <= 0.001:
		camera.position = Vector3.ZERO
		return
	_shake_t += dt * 40.0
	var s: float = _shake * _shake * 0.12
	camera.position = Vector3(sin(_shake_t * 1.3) * s, cos(_shake_t * 1.7) * s, 0.0)
	_shake = maxf(0.0, _shake - dt * 2.8)


func _free_fly(dt: float) -> void:
	var basis_full := Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch)
	var mv := Vector3(Input.get_action_strength("move_right") - Input.get_action_strength("move_left"), 0.0,
		Input.get_action_strength("move_back") - Input.get_action_strength("move_forward"))
	if Input.is_action_pressed("jump"):
		mv.y += 1.0
	if Input.is_action_pressed("dodge"):
		mv.y -= 1.0
	global_position += basis_full * mv * free_look_speed * dt
	global_position = global_position.clamp(Vector3(-75, -2, -60), Vector3(75, 40, 60))
	global_basis = basis_full


func aim_point() -> Vector3:
	## World point under the crosshair (for pings), up to 60 m.
	var space: PhysicsDirectSpaceState3D = get_world_3d().direct_space_state
	var from: Vector3 = camera.global_position
	var to: Vector3 = from - camera.global_basis.z * 60.0
	var q := PhysicsRayQueryParameters3D.create(from, to, WR.LAYER_WORLD | WR.LAYER_CAMERA_BLOCK)
	var hit: Dictionary = space.intersect_ray(q) if space != null else {}
	return hit["position"] if not hit.is_empty() else to
