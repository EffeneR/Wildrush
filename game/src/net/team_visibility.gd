class_name TeamVisibility
extends RefCounted
## What each team may legitimately know about enemy positions (D-013, spec §10–§11):
## line of sight from any living teammate (≤ 70 m), hearing range (≤ 14 m), or a valid ping,
## with a short memory. Used to filter snapshots (anti-wallhack), for the minimap, for dead
## players spectating allies, and as the perception source for bots.

const LOS_RANGE: float = 70.0
const HEAR_RANGE: float = 14.0
const MEMORY_TICKS: int = 30
const PING_TICKS: int = 180

var last_seen: Array = [{}, {}]      # team -> {enemy_entity: tick}
var last_pos: Array = [{}, {}]       # team -> {enemy_entity: Vector3} (remembered position)
var pinged_until: Array = [{}, {}]   # team -> {enemy_entity: tick}


func update(tick: int, fighters: Array, space: PhysicsDirectSpaceState3D) -> void:
	for team in range(2):
		for e: FighterBody in fighters:
			if e.team == team or not e.present or not e.st.alive:
				continue
			var seen: bool = false
			for t: FighterBody in fighters:
				if t.team != team or not t.present or not t.st.alive:
					continue
				var d: float = t.global_position.distance_to(e.global_position)
				if d <= HEAR_RANGE:
					seen = true
					break
				if d > LOS_RANGE or space == null:
					continue
				var eye: Vector3 = t.head_position()
				for target in [e.chest_position(), e.head_position(), e.global_position + Vector3(0, 0.3, 0)]:
					var q := PhysicsRayQueryParameters3D.create(eye, target, WR.LAYER_WORLD)
					if space.intersect_ray(q).is_empty():
						seen = true
						break
				if seen:
					break
			if seen:
				last_seen[team][e.entity_id] = tick
				last_pos[team][e.entity_id] = e.global_position


func visible_to(team: int, entity_id: int, tick: int) -> bool:
	if team < 0:
		return true   # authorised observers / replays see everything
	if tick - int(last_seen[team].get(entity_id, -100000)) <= MEMORY_TICKS:
		return true
	return tick <= int(pinged_until[team].get(entity_id, -1))


func mark_pinged(team: int, entity_id: int, tick: int) -> void:
	pinged_until[team][entity_id] = tick + PING_TICKS


func remembered(team: int, entity_id: int) -> Variant:
	return last_pos[team].get(entity_id)


func forget(entity_id: int) -> void:
	for team in range(2):
		last_seen[team].erase(entity_id)
		pinged_until[team].erase(entity_id)
