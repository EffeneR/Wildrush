extends Node
## Boot router: dedicated server, headless test client, or the game UI.


func _ready() -> void:
	await get_tree().process_frame
	if Config.is_server:
		get_tree().change_scene_to_file("res://scenes/server.tscn")
	elif Config.has("flow-test") and ResourceLoader.exists("res://tools/flow_test.tscn"):
		# verification builds only (tools/ is excluded from the player-facing Windows export)
		get_tree().change_scene_to_file("res://tools/flow_test.tscn")
	elif Config.autopilot != "":
		get_tree().change_scene_to_file("res://scenes/test_client.tscn")
	elif ResourceLoader.exists(Game.SCENE_MENU):
		get_tree().change_scene_to_file("res://scenes/splash.tscn" if ResourceLoader.exists("res://scenes/splash.tscn") else Game.SCENE_MENU)
	else:
		push_error("main menu scene missing")
		get_tree().quit(1)
