class_name TrainingDummy
extends BotBrain
## Training-sandbox dummy controller (not a competitive bot): idle, guard (frontal guard
## toward the player), attack (steps in and throws light strings) or dodge (dodges the
## player's strikes). It may read sim state directly because it never plays real matches.

var behaviour: String = "idle"
var _next_attack: int = 0


func think(sim: MatchSim, f: FighterBody) -> InputFrame:
	seq += 1
	var inp := InputFrame.new()
	inp.seq = seq
	inp.yaw = f.st.yaw
	var target: FighterBody = null
	var best: float = INF
	for o in sim.fighters:
		if o.team != f.team and o.st.alive and not o.is_dummy:
			var d: float = o.global_position.distance_to(f.global_position)
			if d < best:
				best = d
				target = o
	if target == null or behaviour == "idle":
		return inp
	var to: Vector3 = target.global_position - f.global_position
	to.y = 0.0
	if to.length() > 0.01:
		inp.yaw = MathX.yaw_from_dir(to.normalized())
	match behaviour:
		"guard":
			inp.buttons = WR.BTN_GUARD
		"attack":
			if best > 1.7:
				inp.move = Vector2(0, 1)
			elif sim.tick >= _next_attack:
				inp.buttons = WR.BTN_LIGHT
				inp.taps = WR.BTN_LIGHT
				_next_attack = sim.tick + 40
		"dodge":
			if target.st.act != null and best < 3.0 and target.st.act.kind != "counter" and f.st.act == null:
				inp.buttons = WR.BTN_DODGE
				inp.taps = WR.BTN_DODGE
				inp.move = Vector2(1, 0) if (seq / 60) % 2 == 0 else Vector2(-1, 0)
	return inp
