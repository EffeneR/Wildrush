extends Node
## Autoload "Game": high-level scene flow. Holds the match "host" (local offline host or
## network client) the presentation layer is bound to. UI never touches rule objects.
## Contract for screens: docs/UI_CONTRACT.md.

signal scene_changing(path: String)
signal session_started(session: ClientSession)
signal session_ended

const SCENE_BOOT: String = "res://scenes/boot.tscn"
const SCENE_SPLASH: String = "res://scenes/splash.tscn"
const SCENE_MENU: String = "res://scenes/main_menu.tscn"
const SCENE_MATCH: String = "res://scenes/match.tscn"
const SCENE_TRAINING: String = "res://scenes/match.tscn"      # same scene, params.mode = "training"
const SCENE_RESULTS: String = "res://scenes/results.tscn"
const SCENE_ONLINE_LOBBY: String = "res://scenes/online_lobby.tscn"
const SCENE_SERVER: String = "res://scenes/server.tscn"
const SCENE_REPLAY: String = "res://scenes/match.tscn"        # params.mode = "replay"

## Parameters for the next scene (set by menus / lobby before switching). See UI_CONTRACT.md.
var pending: Dictionary = {}
## Last finished match: {"result": <MatchSim.build_result()>, "my_entity": int, "mode": String,
## "fighter": String, "awards": Dictionary, "replay_path": String}
var last_result: Dictionary = {}
## Live online session (persists across lobby -> match -> results scenes).
var session: ClientSession = null


func goto(path: String, params: Dictionary = {}) -> void:
	pending = params
	scene_changing.emit(path)
	get_tree().call_deferred("change_scene_to_file", path)


func goto_menu(params: Dictionary = {}) -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	goto(SCENE_MENU, params)


func start_online_session(host: String, port: int, auth: Dictionary) -> int:
	## Opens a ClientSession to a dedicated server (auth: {name, ticket?, password?, observer?}).
	end_online_session()
	session = ClientSession.new()
	session.name = "Session"
	add_child(session)
	session_started.emit(session)
	return session.connect_to(host, port, auth)


func end_online_session() -> void:
	if session == null:
		return
	session.leave()
	session.queue_free()
	session = null
	session_ended.emit()


func quit_game() -> void:
	end_online_session()
	Settings.save_settings()
	get_tree().quit(0)
