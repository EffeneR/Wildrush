class_name BotBrain
extends RefCounted
## Server-side bot controller. Produces the same InputFrame a human would send; uses only
## fair observations (see src/bots/bot_perception.gd). Full implementation: bot_ai.gd.

var difficulty: String = "normal"
var seq: int = 0


func think(_sim: MatchSim, _f: FighterBody) -> InputFrame:
	seq += 1
	var inp := InputFrame.new()
	inp.seq = seq
	return inp
