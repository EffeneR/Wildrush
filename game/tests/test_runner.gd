extends Node
## Scene-based GDScript test runner (autoloads load normally).
## godot --headless --fixed-fps 60 --path game res://tests/test_runner.tscn -- [--filter s] [--json path]

class ErrorCounter extends Logger:
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

var results: Array = []
var total_checks: int = 0
var logger: ErrorCounter = null


func _ready() -> void:
	var filter: String = Config.get_arg("filter", "")
	var json_path: String = Config.get_arg("json", "")
	logger = ErrorCounter.new()
	OS.add_logger(logger)
	var scripts: Array[String] = []
	var dir := DirAccess.open("res://tests/unit")
	if dir != null:
		for fn in dir.get_files():
			if fn.begins_with("test_") and fn.ends_with(".gd"):
				scripts.append("res://tests/unit/" + fn)
	scripts.sort()
	var t0: int = Time.get_ticks_msec()
	var n_fail: int = 0
	for path in scripts:
		var sc: GDScript = load(path)
		if sc == null:
			results.append({"suite": path, "test": "<load>", "ok": false, "failures": ["script failed to load/parse"]})
			n_fail += 1
			continue
		var methods: Array[String] = []
		for m in sc.get_script_method_list():
			var mn: String = String(m["name"])
			if mn.begins_with("test_") and (filter == "" or (path + ":" + mn).contains(filter)):
				methods.append(mn)
		if methods.is_empty():
			continue
		methods.sort()
		for mn in methods:
			var inst: WRTest = sc.new()
			inst.name = "T"
			add_child(inst)
			await inst.before_each()
			var err_before: int = logger.errors.size()
			var ts: int = Time.get_ticks_msec()
			await inst.call(mn)
			await inst.after_each()
			var new_errors: Array = logger.errors.slice(err_before)
			var fails: Array = inst.failures.duplicate()
			for e in new_errors:
				fails.append("runtime error: " + String(e))
			var ok: bool = fails.is_empty()
			if not ok:
				n_fail += 1
			total_checks += inst.checks
			results.append({"suite": path.get_file(), "test": mn, "ok": ok, "failures": fails, "checks": inst.checks,
				"ms": Time.get_ticks_msec() - ts})
			print(("PASS " if ok else "FAIL ") + path.get_file() + ":" + mn + ("" if ok else "\n    " + "\n    ".join(fails)))
			inst.queue_free()
			await get_tree().physics_frame
	var summary := {"total": results.size(), "failed": n_fail, "passed": results.size() - n_fail, "checks": total_checks,
		"ms": Time.get_ticks_msec() - t0, "godot": Engine.get_version_info()["string"], "results": results}
	print("TESTS: %d passed, %d failed, %d checks, %d ms" % [summary["passed"], n_fail, total_checks, summary["ms"]])
	if json_path != "":
		var f := FileAccess.open(json_path, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(summary, "  "))
			f.close()
	get_tree().quit(1 if n_fail > 0 or results.is_empty() else 0)
