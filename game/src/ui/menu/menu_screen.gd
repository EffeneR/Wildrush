class_name MenuScreen
extends Control
## Base class for main-menu sub-screens (switched inside main_menu.tscn without scene
## changes). The MainMenu owns navigation, the top bar, hints, settings and quit dialogs.

var menu: MainMenu = null
var screen_id: String = ""
var title: String = ""
var subtitle: String = ""
var built: bool = false


func _init() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


## Called once before the first `enter`.
func build() -> void:
	pass


## Called every time the screen becomes active.
func enter(_params: Dictionary) -> void:
	pass


## Called when the screen is hidden.
func exit() -> void:
	pass


func default_focus() -> Control:
	return UiKit.first_focusable(self)


## Return true when the screen consumed a back request (e.g. closed an inner panel).
func handle_back() -> bool:
	return false


func hints() -> Array:
	return [["accept", "Select"], ["back", "Back"]]


## Tab shortcuts etc.; return true when consumed.
func screen_input(_event: InputEvent) -> bool:
	return false


func toast(text: String, kind: String = "info") -> void:
	UiToasts.notify(self, text, kind)
