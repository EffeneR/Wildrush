class_name OfflineSetupScreen
extends FighterSetupScreen
## Offline match setup: fighter, unlocked palette, bot difficulty and the team lineups
## (each team fields exactly one of every animal — spec §3 — so the nine other slots are the
## remaining species, played by clearly labelled bots). Start → SCENE_MATCH mode "offline".

const DIFFICULTIES: Array = [
	["easy", "Easy — slower reactions, simple decisions"],
	["normal", "Normal — balanced reactions and teamwork"],
	["hard", "Hard — quick reactions, coordinated rotations"],
]

var difficulty: UiCycler
var _ally_row: HBoxContainer
var _enemy_row: HBoxContainer


func build() -> void:
	title = "Play offline"
	subtitle = "Turf Shift · 5v5 against bots · Briarport"
	super.build()


func start_label() -> String:
	return "START MATCH"


func build_options(box: VBoxContainer) -> void:
	box.add_child(UiKit.label("BOT DIFFICULTY", &"Caption"))
	var idx: int = 1
	for i in range(DIFFICULTIES.size()):
		if DIFFICULTIES[i][0] == UiState.last_difficulty:
			idx = i
	difficulty = UiCycler.new(DIFFICULTIES, idx)
	difficulty.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	difficulty.value_changed.connect(func(_i: int, v: Variant) -> void: UiState.last_difficulty = String(v))
	box.add_child(difficulty)
	box.add_child(UiKit.label("LINEUP", &"Caption"))
	var grid := UiKit.grid(2, 14, 8)
	box.add_child(grid)
	var yl := UiKit.label("Your team", &"Dim")
	yl.custom_minimum_size = Vector2(110, 0)
	grid.add_child(yl)
	_ally_row = UiKit.hbox(8)
	grid.add_child(_ally_row)
	grid.add_child(UiKit.label("Opponents", &"Dim"))
	_enemy_row = UiKit.hbox(8)
	grid.add_child(_enemy_row)
	var note := UiKit.label("Every team fields one of each animal. Bots take the other nine slots and are always labelled BOT.", &"Small", true)
	box.add_child(note)


func on_fighter_changed() -> void:
	UiKit.clear_children(_ally_row)
	UiKit.clear_children(_enemy_row)
	_ally_row.add_child(_slot(fighter_id, "YOU", true))
	for fid in _allies():
		_ally_row.add_child(_slot(fid, "BOT", false))
	for fid in WR.FIGHTER_IDS:
		_enemy_row.add_child(_slot(fid, "BOT", false))


func _allies() -> Array[String]:
	var out: Array[String] = []
	for fid in WR.FIGHTER_IDS:
		if fid != fighter_id:
			out.append(fid)
	return out


func _slot(fid: String, tag: String, me: bool) -> Control:
	var v := UiKit.vbox(2)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var e := FighterEmblem.new()
	e.fighter_id = fid
	e.custom_minimum_size = Vector2(42, 42)
	e.ring_color = UiKit.ACCENT if me else Color(0, 0, 0, 0)
	v.add_child(e)
	var l := UiKit.label(tag, &"ChipLabel")
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.add_theme_color_override("font_color", UiKit.TEXT if me else UiKit.TEXT_FAINT)
	v.add_child(l)
	v.tooltip_text = "%s (%s)" % [UiKit.fighter_name(fid), "you" if me else "bot"]
	return v


func start() -> void:
	var params: Dictionary = {
		"mode": "offline", "fighter": fighter_id, "palette": palette,
		"difficulty": String(difficulty.value()),
		"allies": _allies(), "enemies": WR.FIGHTER_IDS.duplicate(),
		"seed": randi() % 1000000,
	}
	UiState.remember_match(params)
	UiKit.play("ui_lockin")
	Game.goto(Game.SCENE_MATCH, params)
