class_name WR
extends RefCounted
## Global constants and enums shared by simulation, networking and presentation.
## See docs/DECISIONS.md (D-003 .. D-013).

const TICK_RATE: int = 60
const TICK_DT: float = 1.0 / 60.0
const PROTOCOL_VERSION: int = 3
const BUILD_ID: String = "wildrush-1.0.0"
const TEAM_SIZE: int = 5
const NUM_TEAMS: int = 2
const FIGHTER_IDS: Array[String] = ["nyx", "bruno", "vex", "hops", "scrap"]

# Physics layers (bit values). Names mirror project.godot [layer_names].
const LAYER_WORLD: int = 1
const LAYER_FIGHTERS: int = 2
const LAYER_BARRIER_VS_TEAM1: int = 4   # placed at team 0's spawn, collides with team 1
const LAYER_BARRIER_VS_TEAM0: int = 8   # placed at team 1's spawn, collides with team 0
const LAYER_BLOCKER: int = 16           # invisible water/perimeter blockers (not camera)
const LAYER_CAMERA_BLOCK: int = 32
const LAYER_PERCH: int = 64

# Input buttons (held bitmask)
const BTN_LIGHT: int = 1
const BTN_HEAVY: int = 2
const BTN_JUMP: int = 4
const BTN_DODGE: int = 8
const BTN_GUARD: int = 16
const BTN_Q: int = 32
const BTN_E: int = 64
const BTN_R: int = 128
const BTN_ALL_SIM: int = 255

# Control effects (victim-side states)
enum Ctrl { NONE, FLINCH, STAGGER, KNOCKDOWN, GETUP, GRABBED, GUARD_BREAK, BLOCKSTUN, LANDING }

# Hit effects (attacker-side data)
enum Effect { FLINCH, STAGGER, KNOCKDOWN, INTERRUPT, GRAB, REDIRECT }

# Match phases
enum Phase { WAITING, CHARACTER_SELECT, COUNTDOWN, LIVE, SUDDEN_DEATH, FINISHED }

# Zone presentation state
enum ZoneState { INACTIVE, NEUTRAL, CONTROLLED, CONTESTED }

# Game modes
const MODE_OFFLINE: String = "offline"
const MODE_TRAINING: String = "training"
const MODE_PRIVATE: String = "private"
const MODE_CASUAL: String = "casual"
const MODE_RANKED: String = "ranked"

static func secs_to_ticks(s: float) -> int:
	return int(round(s * TICK_RATE))

static func ticks_to_secs(t: int) -> float:
	return float(t) / float(TICK_RATE)

static func effect_from_string(s: String) -> int:
	match s:
		"flinch": return Effect.FLINCH
		"stagger": return Effect.STAGGER
		"knockdown": return Effect.KNOCKDOWN
		"interrupt": return Effect.INTERRUPT
		"grab": return Effect.GRAB
		"redirect": return Effect.REDIRECT
	push_error("unknown effect '%s'" % s)
	return Effect.FLINCH

static func other_team(team: int) -> int:
	return 1 - team

static func barrier_layer_for_spawn_of(team: int) -> int:
	## Barrier placed at `team`'s spawn blocks the opposing team.
	return LAYER_BARRIER_VS_TEAM1 if team == 0 else LAYER_BARRIER_VS_TEAM0

static func fighter_collision_mask(team: int) -> int:
	## Fighters collide with world, blockers and the barrier at the ENEMY spawn.
	var enemy_spawn_barrier: int = barrier_layer_for_spawn_of(other_team(team))
	return LAYER_WORLD | LAYER_BLOCKER | enemy_spawn_barrier
