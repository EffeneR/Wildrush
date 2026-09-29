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
var _preload_pending: Array[String] = []
var _preloaded: Array[Resource] = []   # keeps background-loaded match assets cached


func _ready() -> void:
	if not Config.is_server and Config.autopilot == "":
		preload_match_assets()


func preload_match_assets() -> void:
	## Loads the heavy match assets (fighter models, arena art chunks) on worker threads while
	## the player is in menus, so starting a match never blocks the main thread for seconds
	## (which would stall rendering and, online, the network connection).
	if not _preload_pending.is_empty() or not _preloaded.is_empty():
		return
	var paths: Array[String] = []
	for fid in WR.FIGHTER_IDS:
		var gp: String = "res://assets/characters/%s/%s.glb" % [fid, fid]
		if AssetUtil.imported(gp):
			paths.append(gp)
	var art: String = "res://assets/arena/arena_art.json"
	if FileAccess.file_exists(art):
		var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(art))
		if typeof(d) == TYPE_DICTIONARY:
			for ch in (d as Dictionary).get("chunks", []):
				var cp: String = String(ch.get("path", ""))
				if cp.begins_with("res://") and AssetUtil.imported(cp):
					paths.append(cp)
	for p in paths:
		if ResourceLoader.load_threaded_request(p, "", true) == OK:
			_preload_pending.append(p)


func _process(_dt: float) -> void:
	if _preload_pending.is_empty():
		return
	for p in _preload_pending.duplicate():
		var st: int = ResourceLoader.load_threaded_get_status(p)
		if st == ResourceLoader.THREAD_LOAD_LOADED:
			var r: Resource = ResourceLoader.load_threaded_get(p)
			if r != null:
				_preloaded.append(r)
			_preload_pending.erase(p)
		elif st == ResourceLoader.THREAD_LOAD_FAILED or st == ResourceLoader.THREAD_LOAD_INVALID_RESOURCE:
			push_warning("preload failed: " + p)
			_preload_pending.erase(p)


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
