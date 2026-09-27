class_name ActionDef
extends Resource
## Data for one attack / skill / counter (D-011). Loaded from game/data/tuning/fighters/*.json.

@export var id: String = ""
@export var fighter_id: String = ""
@export var display_name: String = ""
@export var kind: String = "light"          # light | heavy | skill | counter
@export var slot: String = ""               # q | e | r for skills
@export var behavior: String = "generic"
@export var limb: String = ""
@export var clip: String = ""
@export var desc: String = ""
@export var stamina: float = 0.0
@export var cooldown_ticks: int = 0
@export var cooldown_s: float = 0.0
@export var grounded_only: bool = false
@export var air: bool = false
@export var total_ticks: int = 0
@export var startup_ticks: int = 0
@export var turn_table: Array = []          # [[tick:int, rate_rad_per_tick:float], ...]
@export var move_keys: Array = []           # [[time_s, Vector3], ...] cumulative action-local offset
@export var hits: Array[HitDef] = []
@export var cancels: Array = []             # [[from_tick, to_tick, PackedStringArray], ...]
@export var params: Dictionary = {}
@export var clips: Dictionary = {}          # name -> [clip, duration_s]
@export var tags: PackedStringArray = PackedStringArray()


func param(name: String, default_value: Variant = 0.0) -> Variant:
	return params.get(name, default_value)


func pticks(name: String, default_s: float = 0.0) -> int:
	## A behaviour parameter given in seconds, converted to ticks.
	return WR.secs_to_ticks(float(params.get(name, default_s)))


func turn_rate_at(tick: int) -> float:
	## Max yaw change per tick at action tick `tick` (radians). Default: locked.
	var rate: float = 0.0
	for entry in turn_table:
		if tick >= int(entry[0]):
			rate = float(entry[1])
	return rate


func can_cancel_into(tick: int, what: String) -> bool:
	for c in cancels:
		if tick >= int(c[0]) and tick <= int(c[1]) and (c[2] as PackedStringArray).has(what):
			return true
	return false


func first_active_tick() -> int:
	var best: int = 1 << 30
	for h in hits:
		if h.rel == "":
			best = mini(best, h.t0)
	return startup_ticks if best == 1 << 30 else best


static func from_dict(action_id: String, fighter_id: String, d: Dictionary) -> ActionDef:
	var a := ActionDef.new()
	a.id = action_id
	a.fighter_id = fighter_id
	a.display_name = String(d.get("name", action_id))
	a.kind = String(d.get("kind", "light"))
	a.slot = String(d.get("slot", ""))
	a.behavior = String(d.get("behavior", "generic"))
	a.limb = String(d.get("limb", ""))
	a.clip = String(d.get("clip", ""))
	a.desc = String(d.get("desc", ""))
	a.stamina = float(d.get("stamina", 0.0))
	a.cooldown_s = float(d.get("cooldown_s", 0.0))
	a.cooldown_ticks = WR.secs_to_ticks(a.cooldown_s)
	a.grounded_only = bool(d.get("grounded_only", false))
	a.air = bool(d.get("air", false))
	a.total_ticks = WR.secs_to_ticks(float(d.get("total_s", 0.0)))
	a.startup_ticks = WR.secs_to_ticks(float(d.get("startup_s", 0.0)))
	for tr in d.get("turn", []):
		a.turn_table.append([WR.secs_to_ticks(float(tr[0])), deg_to_rad(float(tr[1])) / WR.TICK_RATE])
	for k in d.get("move", []):
		a.move_keys.append([float(k[0]), Vector3(float(k[1]), float(k[2]), float(k[3]))])
	var i: int = 0
	for hd in d.get("hits", []):
		a.hits.append(HitDef.from_dict(hd, i, a.limb))
		i += 1
	for c in d.get("cancels", []):
		a.cancels.append([WR.secs_to_ticks(float(c[0])), WR.secs_to_ticks(float(c[1])), PackedStringArray(c[2])])
	a.params = d.get("params", {})
	a.clips = d.get("clips", {})
	if a.startup_ticks == 0 and not a.hits.is_empty():
		a.startup_ticks = a.first_active_tick()
	return a
