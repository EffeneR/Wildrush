extends Node
## Autoload "Game": high-level scene flow. Holds the match "host" (local offline host or
## network client) the presentation layer is bound to. UI never touches rule objects.

signal scene_changing(path: String)

const SCENE_BOOT: String = "res://scenes/boot.tscn"
const SCENE_MENU: String = "res://scenes/main_menu.tscn"
const SCENE_MATCH: String = "res://scenes/match.tscn"
const SCENE_TRAINING: String = "res://scenes/training.tscn"
const SCENE_SERVER: String = "res://scenes/server.tscn"
const SCENE_REPLAY: String = "res://scenes/replay_viewer.tscn"

## Parameters for the next match scene (set by menus / lobby before switching).
var pending: Dictionary = {}
var last_result: Dictionary = {}


func goto(path: String, params: Dictionary = {}) -> void:
	pending = params
	scene_changing.emit(path)
	get_tree().call_deferred("change_scene_to_file", path)


func goto_menu(params: Dictionary = {}) -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	goto(SCENE_MENU, params)


func quit_game() -> void:
	Settings.save_settings()
	get_tree().quit(0)
