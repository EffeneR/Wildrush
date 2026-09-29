class_name UiState
extends RefCounted
## Menu state that must survive scene changes (static script variables live as long as the
## script): parameters of the last match started from the menus ("Play again"), remembered
## selections and the last open online tab.

static var last_match_params: Dictionary = {}
static var last_fighter: String = ""
static var last_difficulty: String = "normal"
static var training_behaviour: String = "idle"
static var training_dummies: int = 3
static var online_tab: int = 0
static var queue_mode: String = "casual"
static var allow_bots: bool = false
static var private_join_code: String = ""
static var last_direct: String = "127.0.0.1:24610"


static func remember_match(params: Dictionary) -> void:
	last_match_params = params.duplicate(true)
	if params.has("fighter"):
		last_fighter = String(params["fighter"])
