extends SceneTree
## Regenerates res://assets/ui/wildrush_theme.tres from UiThemeBuilder (reproducible theme).
##   $GODOT_BIN --headless --path game --script res://tools/build_ui_theme.gd

const OUT: String = "res://assets/ui/wildrush_theme.tres"


func _init() -> void:
	var theme: Theme = UiThemeBuilder.build()
	var err: int = ResourceSaver.save(theme, OUT)
	if err != OK:
		push_error("build_ui_theme: save failed (%d)" % err)
		quit(1)
		return
	print("build_ui_theme: wrote %s (%d type variations)" % [OUT, UiThemeBuilder.VARIATIONS.size()])
	quit(0)
