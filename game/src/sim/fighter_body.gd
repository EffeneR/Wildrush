class_name FighterBody
extends CharacterBody3D
## Authoritative physical fighter (spec §5: CharacterBody3D, fixed 60 Hz). Holds no visuals;
## presentation lives in src/present/fighter_view.gd and reads this state.

var def: FighterDef
var st: FighterState = FighterState.new()
var entity_id: int = -1
var team: int = 0
var slot: int = 0
var player_name: String = ""
var account_id: String = ""
var is_bot: bool = false
var is_dummy: bool = false
var palette: String = "default"
var present: bool = true            # false while a disconnected human's reservation is pending
var shape_node: CollisionShape3D
var capsule: CapsuleShape3D
# Hurtbox history for bounded lag compensation (D-012): ring of [tick, feet_pos].
var history: Array = []
const HISTORY_LEN: int = 32


func setup(fdef: FighterDef, p_team: int, p_entity: int) -> void:
	def = fdef
	team = p_team
	entity_id = p_entity
	name = "F%d_%s" % [entity_id, def.id]
	capsule = CapsuleShape3D.new()
	capsule.radius = def.hurt_radius
	capsule.height = def.height
	shape_node = CollisionShape3D.new()
	shape_node.shape = capsule
	shape_node.position = Vector3(0, def.height * 0.5, 0)
	add_child(shape_node)
	collision_layer = WR.LAYER_FIGHTERS
	collision_mask = WR.fighter_collision_mask(team)
	motion_mode = CharacterBody3D.MOTION_MODE_GROUNDED
	up_direction = Vector3.UP
	floor_max_angle = Tuning.floor_max_angle
	floor_snap_length = Tuning.floor_snap_length
	floor_stop_on_slope = true
	floor_constant_speed = true
	floor_block_on_wall = true
	max_slides = 4
	safe_margin = 0.002
	reset_vitals()


func reset_vitals() -> void:
	st.alive = true
	st.health = def.health
	st.stamina = Tuning.stamina_max
	st.clear_action()
	st.ctrl = WR.Ctrl.NONE
	st.guarding = false
	st.knock_left = 0
	st.knock_vel = Vector3.ZERO
	st.cd_ready = {"q": 0, "e": 0, "r": 0, "dodge": 0}
	st.chain_count = 0
	st.buf_btn = 0
	st.cr_until = -1
	velocity = Vector3.ZERO


func feet_position() -> Vector3:
	return global_position


func chest_position() -> Vector3:
	return global_position + Vector3(0, def.height * 0.68, 0)


func head_position() -> Vector3:
	return global_position + Vector3(0, def.height * 0.9, 0)


func is_eligible_occupant() -> bool:
	return present and st.alive and not is_dummy


func can_be_hit() -> bool:
	return present and st.alive


func hurt_segment_at(feet: Vector3) -> Array:
	## Body hurt capsule axis (feet+r .. crown-r) and radius. Ears/tail/clothing excluded.
	var r: float = def.hurt_radius
	return [feet + Vector3(0, r, 0), feet + Vector3(0, def.height - r, 0), r]


func record_history(tick: int) -> void:
	history.append([tick, global_position])
	if history.size() > HISTORY_LEN:
		history.pop_front()


func position_at_tick(tick: int) -> Vector3:
	## Server-owned history lookup; clamps to the oldest/newest recorded sample.
	if history.is_empty():
		return global_position
	for i in range(history.size() - 1, -1, -1):
		if int(history[i][0]) <= tick:
			return history[i][1]
	return history[0][1]


func forward() -> Vector3:
	return MathX.yaw_forward(st.yaw)


func apply_yaw() -> void:
	rotation = Vector3(0, st.yaw, 0)
