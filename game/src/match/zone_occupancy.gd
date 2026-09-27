class_name ZoneOccupancy
extends RefCounted
## Floor-relative occupancy volume for the active zone (D-006): vertical cylinder with
## enter/exit radius hysteresis and a vertical band measured at the fighter's feet, so a
## fighter on a bridge/roof above cannot capture and small jumps do not flicker.

var radius_enter: float = 9.0
var radius_exit: float = 9.35
var band_below: float = 0.6
var band_above: float = 2.6
var zones: Dictionary = {}          # id -> {"center": Vector3, "floor_y": float}
var _inside: Dictionary = {}        # entity_id -> bool (for the current zone)
var _zone: String = ""


func configure(rules: Dictionary, layout_zones: Array) -> void:
	var occ: Dictionary = rules.get("occupancy", {})
	radius_enter = float(occ.get("radius_enter", 9.0))
	radius_exit = float(occ.get("radius_exit", 9.35))
	band_below = float(occ.get("band_below", 0.6))
	band_above = float(occ.get("band_above", 2.6))
	for z in layout_zones:
		var c: Array = z["center"]
		zones[String(z["id"])] = {"center": Vector3(float(c[0]), float(c[1]), float(c[2])), "floor_y": float(z.get("floor_y", 0.0))}


func set_zone(zone_id: String) -> void:
	if zone_id != _zone:
		_zone = zone_id
		_inside.clear()


func is_inside(entity_id: int, feet: Vector3) -> bool:
	## Updates hysteresis state for entity and returns whether it occupies the active zone.
	if not zones.has(_zone):
		return false
	var z: Dictionary = zones[_zone]
	var c: Vector3 = z["center"]
	var fy: float = float(z["floor_y"])
	var in_band: bool = feet.y >= fy - band_below and feet.y <= fy + band_above
	var d: float = Vector2(feet.x - c.x, feet.z - c.z).length()
	var was: bool = bool(_inside.get(entity_id, false))
	var inside: bool = in_band and (d <= radius_enter or (was and d <= radius_exit))
	_inside[entity_id] = inside
	return inside


func forget(entity_id: int) -> void:
	## Knocked-out / removed fighters leave occupancy immediately.
	_inside.erase(entity_id)


func count_presence(fighters: Array) -> Array[int]:
	## fighters: Array of objects with entity_id, team, is_eligible_occupant(), feet_position().
	var presence: Array[int] = [0, 0]
	for f in fighters:
		if not f.is_eligible_occupant():
			forget(f.entity_id)
			continue
		if is_inside(f.entity_id, f.feet_position()):
			presence[f.team] += 1
	return presence
