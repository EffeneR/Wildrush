class_name TrainingSetupScreen
extends FighterSetupScreen
## Training setup: fighter + palette + dummy behaviour/count → SCENE_MATCH mode "training".

const BEHAVIOURS: Array = [
	["idle", "Idle — dummies stand still"],
	["guard", "Guard — dummies hold a frontal guard"],
	["attack", "Attack — dummies throw light attacks"],
	["dodge", "Dodge — dummies evade your attacks"],
]

var behaviour: UiCycler
var dummies: UiCycler


func build() -> void:
	title = "Training"
	subtitle = "Separate sandbox · configurable dummies"
	super.build()


func start_label() -> String:
	return "START TRAINING"


func build_options(box: VBoxContainer) -> void:
	box.add_child(UiKit.label("DUMMY BEHAVIOUR", &"Caption"))
	var bi: int = 0
	for i in range(BEHAVIOURS.size()):
		if BEHAVIOURS[i][0] == UiState.training_behaviour:
			bi = i
	behaviour = UiCycler.new(BEHAVIOURS, bi)
	behaviour.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	behaviour.value_changed.connect(func(_i: int, v: Variant) -> void: UiState.training_behaviour = String(v))
	box.add_child(behaviour)
	box.add_child(UiKit.label("DUMMIES", &"Caption"))
	var opts: Array = []
	for n in range(1, 6):
		opts.append([n, "%d dumm%s" % [n, "y" if n == 1 else "ies"]])
	dummies = UiCycler.new(opts, clampi(UiState.training_dummies, 1, 5) - 1)
	dummies.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	dummies.value_changed.connect(func(_i: int, v: Variant) -> void: UiState.training_dummies = int(v))
	box.add_child(dummies)
	var note := UiKit.label("Training is a separate sandbox: dummies and training overrides never appear in real matches.", &"Small", true)
	box.add_child(note)


func start() -> void:
	var params: Dictionary = {
		"mode": "training", "fighter": fighter_id, "palette": palette,
		"training": {"dummy_behaviour": String(behaviour.value()), "dummies": int(dummies.value())},
	}
	UiState.remember_match(params)
	UiKit.play("ui_lockin")
	Game.goto(Game.SCENE_MATCH, params)
