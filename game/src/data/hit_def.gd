class_name HitDef
extends Resource
## One hit window of an action (D-011). Times are integer sim ticks relative to the
## action start (or to a behaviour phase start when `rel` is set). Path keys are
## action-local positions of the hit sphere centre: [[time_s, Vector3], ...].

@export var index: int = 0
@export var t0: int = 0
@export var t1: int = 0
@export var t0_s: float = 0.0
@export var t1_s: float = 0.0
@export var radius: float = 0.3
@export var path: Array = []
@export var damage: float = 0.0
@export var guard_damage: float = 0.0
@export var knockback: float = 0.0
@export var knock_up: float = 0.0
@export var stun_ticks: int = 0
@export var effect: int = WR.Effect.FLINCH
@export var low: bool = false
@export var parryable: bool = true
@export var unblockable: bool = false
@export var follow: bool = false
@export var rel: String = ""
@export var limb: String = ""
@export var kb_radial: bool = false
@export var push_along_motion: bool = false


func local_pos_at(t_s: float) -> Vector3:
	return MathX.sample_keys(path, t_s)


static func from_dict(d: Dictionary, idx: int, default_limb: String) -> HitDef:
	var h := HitDef.new()
	h.index = idx
	h.t0_s = float(d.get("t0", 0.0))
	h.t1_s = float(d.get("t1", 0.0))
	h.t0 = WR.secs_to_ticks(h.t0_s)
	h.t1 = WR.secs_to_ticks(h.t1_s)
	h.radius = float(d.get("r", 0.3))
	var keys: Array = []
	for k in d.get("path", []):
		keys.append([float(k[0]), Vector3(float(k[1]), float(k[2]), float(k[3]))])
	h.path = keys
	h.damage = float(d.get("dmg", 0.0))
	h.guard_damage = float(d.get("gdmg", 0.0))
	h.knockback = float(d.get("kb", 0.0))
	h.knock_up = float(d.get("kb_up", 0.0))
	h.stun_ticks = WR.secs_to_ticks(float(d.get("stun_s", 0.0)))
	h.effect = WR.effect_from_string(String(d.get("effect", "flinch")))
	h.low = bool(d.get("low", false))
	h.parryable = bool(d.get("parryable", true))
	h.unblockable = bool(d.get("unblockable", false))
	h.follow = bool(d.get("follow", false))
	h.rel = String(d.get("rel", ""))
	h.limb = String(d.get("limb", default_limb))
	h.kb_radial = bool(d.get("kb_radial", false))
	h.push_along_motion = bool(d.get("push_along_motion", false))
	return h
