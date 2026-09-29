extends Node
## End-to-end screen flow check (G11): boot -> splash -> main menu -> offline setup "Start"
## -> full offline match (local fighter driven by a bot via --autopilot-self) -> results ->
## "Main menu" -> main menu. Uses the real scenes and their own actions; fails on any engine
## error or a transition that does not happen in time.
##   godot --headless --fixed-fps 60 --path game res://tools/flow_test.tscn -- --autopilot-self [--json out.json]

class ErrLog extends Logger:
	var errors: Array[String] = []
	var mutex := Mutex.new()
	func _log_error(function: String, file: String, line: int, code: String, rationale: String, _editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		if error_type == Logger.ERROR_TYPE_WARNING:
			return
		mutex.lock()
		errors.append("%s:%d %s %s %s" % [file, line, function, code, rationale])
		mutex.unlock()
	func _log_message(_message: String, _error: bool) -> void:
		pass

var errlog := ErrLog.new()
var step: String = "boot"
var steps_done: Array[String] = []
var frames: int = 0
var step_frames: int = 0
var driver_attached: bool = false


func _ready() -> void:
	OS.add_logger(errlog)
	# The driver must survive scene changes, so it lives directly under the root.
	var parent: Node = get_parent()
	parent.remove_child.call_deferred(self)
	get_tree().root.add_child.call_deferred(self)
	# (when launched through boot.gd --flow-test, go straight to the splash to avoid a loop)
	get_tree().change_scene_to_file.call_deferred(Game.SCENE_SPLASH if Config.has("flow-test") else Game.SCENE_BOOT)


func _scene() -> String:
	var cs: Node = get_tree().current_scene
	return cs.scene_file_path if cs != null else ""


func _advance(next: String) -> void:
	steps_done.append(step)
	print("[flow] %s ok -> %s (frame %d)" % [step, next, frames])
	step = next
	step_frames = 0


func _process(_dt: float) -> void:
	frames += 1
	step_frames += 1
	match step:
		"boot":
			if _scene() == Game.SCENE_MENU:
				_advance("menu")
		"menu":
			if step_frames > 30:
				var s: Node = _find_script(get_tree().root, "offline_setup_screen.gd")
				if s == null:
					var mm: Node = get_tree().current_scene
					if mm.has_method("open_screen"):
						mm.call("open_screen", "offline")
					return
				s.call("start")
				_advance("match")
		"match":
			if _scene() == Game.SCENE_RESULTS:
				if Game.last_result.is_empty():
					_fail("results scene without Game.last_result")
				_advance("results")
		"results":
			if step_frames > 60:
				var b: Button = _find_button(get_tree().current_scene, "Main menu")
				if b == null:
					_fail("results screen has no 'Main menu' button")
					return
				b.pressed.emit()
				_advance("back_to_menu")
		"back_to_menu":
			if _scene() == Game.SCENE_MENU and step_frames > 30:
				_finish(true, "")
	var limit: int = 60 * 60 * 12 if step == "match" else 60 * 60
	if step_frames > limit:
		_fail("timeout in step '%s' (scene %s)" % [step, _scene()])


func _find_script(n: Node, file: String) -> Node:
	var sc: Script = n.get_script() as Script
	if sc != null and sc.resource_path.ends_with(file) and n.is_inside_tree() and (n as CanvasItem == null or (n as CanvasItem).is_visible_in_tree() or true):
		return n
	for c in n.get_children():
		var r: Node = _find_script(c, file)
		if r != null:
			return r
	return null


func _find_button(n: Node, text: String) -> Button:
	if n is Button and (n as Button).text.to_lower() == text.to_lower() and (n as Button).is_visible_in_tree():
		return n as Button
	for c in n.get_children():
		var r: Button = _find_button(c, text)
		if r != null:
			return r
	return null


func _fail(msg: String) -> void:
	_finish(false, msg)


func _finish(ok: bool, msg: String) -> void:
	if ok and not errlog.errors.is_empty():
		ok = false
		msg = "engine errors during the flow"
	var out := {"ok": ok, "message": msg, "steps": steps_done, "frames": frames, "errors": errlog.errors.slice(0, 20),
		"result": Game.last_result.get("result", {}), "awards": Game.last_result.get("awards", {}),
		"replay_path": Game.last_result.get("replay_path", "")}
	var jp: String = Config.get_arg("json", "")
	if jp != "":
		var f := FileAccess.open(jp, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(out, "  "))
			f.close()
	print("[flow] %s %s" % ["PASS" if ok else "FAIL", msg])
	for e in errlog.errors.slice(0, 10):
		print("[flow] error: " + e)
	set_process(false)
	get_tree().quit(0 if ok else 1)
