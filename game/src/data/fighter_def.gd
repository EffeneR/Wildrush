class_name FighterDef
extends Resource
## Static definition of one fighter (spec §6). Loaded from game/data/tuning/fighters/<id>.json.

@export var id: String = ""
@export var display_name: String = ""
@export var species: String = ""
@export var title: String = ""
@export var role: String = ""
@export var tagline: String = ""
@export var quote: String = ""
@export var health: float = 220.0
@export var move_speed: float = 7.0
@export var height: float = 1.7
@export var hurt_radius: float = 0.34
@export var jump_velocity: float = 5.2
@export var strafe_mult: float = 0.88
@export var backpedal_mult: float = 0.74
@export var style: Dictionary = {}
@export var passive_id: String = ""
@export var passive_name: String = ""
@export var passive_desc: String = ""
@export var passive_params: Dictionary = {}
@export var light_ids: Dictionary = {}     # s / l / r / air -> action id
@export var heavy_id: String = ""
@export var skill_ids: Dictionary = {}     # q / e / r -> action id
@export var actions: Dictionary = {}       # action id -> ActionDef
@export var palettes: Dictionary = {}


func action(action_id: String) -> ActionDef:
	return actions.get(action_id) as ActionDef


func skill(slot: String) -> ActionDef:
	return actions.get(skill_ids.get(slot, "")) as ActionDef


func passive_param(name: String, default_value: Variant = 0.0) -> Variant:
	return passive_params.get(name, default_value)


static func from_dict(d: Dictionary, shared: Dictionary) -> FighterDef:
	var f := FighterDef.new()
	f.id = String(d["id"])
	f.display_name = String(d.get("display_name", f.id.to_upper()))
	f.species = String(d.get("species", ""))
	f.title = String(d.get("title", ""))
	f.role = String(d.get("role", ""))
	f.tagline = String(d.get("tagline", ""))
	f.quote = String(d.get("quote", ""))
	f.health = float(d.get("health", 220.0))
	f.move_speed = float(d.get("move_speed", 7.0))
	f.height = float(d.get("height", 1.7))
	f.hurt_radius = float(d.get("hurt_radius", shared.get("hurtbox", {}).get("default_radius", 0.34)))
	f.jump_velocity = float(d.get("jump_velocity", shared["movement"]["jump_velocity"]))
	f.strafe_mult = float(d.get("strafe_mult", shared["movement"]["strafe_mult"]))
	f.backpedal_mult = float(d.get("backpedal_mult", shared["movement"]["backpedal_mult"]))
	f.style = d.get("style", {})
	var p: Dictionary = d.get("passive", {})
	f.passive_id = String(p.get("id", ""))
	f.passive_name = String(p.get("name", ""))
	f.passive_desc = String(p.get("desc", ""))
	f.passive_params = p.get("params", {})
	f.light_ids = d.get("light", {})
	f.heavy_id = String(d.get("heavy", ""))
	f.skill_ids = d.get("skills", {})
	var acts: Dictionary = d.get("actions", {})
	for aid in acts.keys():
		f.actions[aid] = ActionDef.from_dict(String(aid), f.id, acts[aid])
	f.palettes = d.get("palettes", {})
	return f
