class_name SimContext
extends RefCounted
## Per-tick context handed to fighter logic, behaviours and the combat resolver.

var tick: int = 0
var fighters: Array = []                 # Array[FighterBody] (all, incl. absent)
var space: PhysicsDirectSpaceState3D = null
var events: Array[Dictionary] = []
var predicting: bool = false             # client-side prediction: no authoritative outcomes
var perch_ledges: Array = []             # [{a: Vector3, b: Vector3, normal: Vector3}]
var fall_recovery_y: float = -12.0
var training: bool = false
var rewind_provider: Callable = Callable()   # func(attacker: FighterBody) -> int ticks (server lag comp)
var spawn_volumes: Dictionary = {}       # team -> AABB (protected spawn volume)


func emit(ev: Dictionary) -> void:
	if predicting and not ev.get("predictable", false):
		return
	ev["tick"] = tick
	events.append(ev)


func enemies_of(f: FighterBody) -> Array:
	var out: Array = []
	for o in fighters:
		if o != f and o.team != f.team and o.can_be_hit():
			out.append(o)
	return out


func rewind_ticks(attacker: FighterBody) -> int:
	if rewind_provider.is_valid():
		return int(rewind_provider.call(attacker))
	return 0


func ray_blocked(from: Vector3, to: Vector3, mask: int = WR.LAYER_WORLD) -> bool:
	if space == null:
		return false
	var q := PhysicsRayQueryParameters3D.create(from, to, mask)
	q.collide_with_areas = false
	q.hit_back_faces = true
	var r: Dictionary = space.intersect_ray(q)
	return not r.is_empty()


func capsule_free_at(feet: Vector3, radius: float, height: float, mask: int) -> bool:
	## True if a fighter capsule placed with its feet at `feet` overlaps no static geometry.
	if space == null:
		return true
	var shape := CapsuleShape3D.new()
	shape.radius = radius
	shape.height = height
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.transform = Transform3D(Basis.IDENTITY, feet + Vector3(0, height * 0.5 + 0.03, 0))
	q.collision_mask = mask
	q.collide_with_areas = false
	return space.intersect_shape(q, 1).is_empty()


func ground_below(p: Vector3, max_drop: float = 1.2) -> Variant:
	## Returns the floor Vector3 under p within max_drop, or null.
	if space == null:
		return Vector3(p.x, 0.0, p.z)
	var q := PhysicsRayQueryParameters3D.create(p + Vector3(0, 0.5, 0), p - Vector3(0, max_drop, 0), WR.LAYER_WORLD)
	var r: Dictionary = space.intersect_ray(q)
	if r.is_empty():
		return null
	return r["position"]
