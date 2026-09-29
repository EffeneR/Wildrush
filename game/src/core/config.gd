extends Node
## Autoload "Config": command-line options (user args after `--`) and runtime roles.
## Dedicated server:  <bin> --headless -- --server --port 24610 [--match-id ..] [--mode casual]
##                     [--service-url ..] [--server-id ..] [--secret-file ..] [--expected-players N]
##                     [--private-password-file ..] [--allow-bots] [--replay-dir ..]
## Client:            <bin> -- [--connect host:port] [--ticket T] [--name N] [--offline-quick]
## Test drivers:      --autopilot <scenario> --seed N --log-json path --quit-after-s S

var args: Dictionary = {}
var is_server: bool = false
var is_headless: bool = false
var port: int = 24610
var bind_address: String = "*"
var match_id: String = ""
var mode: String = WR.MODE_CASUAL
var service_url: String = ""
var server_id: String = ""
var secret_file: String = ""
var expected_players: int = 10
var connect_to: String = ""
var ticket: String = ""
var player_name: String = ""
var autopilot: String = ""
var seed_value: int = 0
var log_json: String = ""
var quit_after_s: float = 0.0
var allow_bots: bool = false
var private_password: String = ""
var replay_dir: String = ""
var observer: bool = false
var fighter_pref: String = ""


func _init() -> void:
	parse(OS.get_cmdline_user_args())
	is_headless = DisplayServer.get_name() == "headless"


func parse(user_args: PackedStringArray) -> void:
	args.clear()
	var i: int = 0
	while i < user_args.size():
		var a: String = user_args[i]
		if a.begins_with("--"):
			var key: String = a.substr(2)
			var val: String = "true"
			if key.contains("="):
				val = key.get_slice("=", 1)
				key = key.get_slice("=", 0)
			elif i + 1 < user_args.size() and not user_args[i + 1].begins_with("--"):
				val = user_args[i + 1]
				i += 1
			args[key] = val
		i += 1
	is_server = args.has("server") or OS.has_feature("dedicated_server")   # exported server build runs as server
	port = clampi(int(args.get("port", "24610")), 1024, 65535)
	bind_address = String(args.get("bind", "*"))
	match_id = String(args.get("match-id", ""))
	mode = String(args.get("mode", WR.MODE_CASUAL if is_server else WR.MODE_OFFLINE))
	service_url = String(args.get("service-url", ""))
	server_id = String(args.get("server-id", ""))
	secret_file = String(args.get("secret-file", ""))
	expected_players = clampi(int(args.get("expected-players", "10")), 1, 10)
	connect_to = String(args.get("connect", ""))
	ticket = String(args.get("ticket", ""))
	player_name = String(args.get("name", ""))
	autopilot = String(args.get("autopilot", ""))
	seed_value = int(args.get("seed", "0"))
	log_json = String(args.get("log-json", ""))
	quit_after_s = float(args.get("quit-after-s", "0"))
	allow_bots = args.has("allow-bots")
	replay_dir = String(args.get("replay-dir", ""))
	observer = args.has("observer")
	fighter_pref = String(args.get("fighter", ""))
	var pw_file: String = String(args.get("private-password-file", ""))
	if pw_file != "" and FileAccess.file_exists(pw_file):
		private_password = FileAccess.get_file_as_string(pw_file).strip_edges()


func has(key: String) -> bool:
	return args.has(key)


func get_arg(key: String, default_value: String = "") -> String:
	return String(args.get(key, default_value))


func read_secret() -> String:
	if secret_file == "" or not FileAccess.file_exists(secret_file):
		return ""
	return FileAccess.get_file_as_string(secret_file).strip_edges()
