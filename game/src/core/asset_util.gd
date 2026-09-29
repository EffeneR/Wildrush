class_name AssetUtil
extends RefCounted
## Helpers for optional, pipeline-produced assets (character GLBs, arena chunks) that may be
## present on disk before Godot has imported them.


static func imported(path: String) -> bool:
	## True only when `path` has been imported (its .import remap target exists). A bare
	## .import sidecar written by an external pipeline is not enough.
	var imp: String = path + ".import"
	if not FileAccess.file_exists(imp):
		return false
	var cf := ConfigFile.new()
	if cf.load(imp) != OK:
		return false
	var dest: String = String(cf.get_value("remap", "path", ""))
	if dest == "":
		# multi-target remaps (path.s3tc etc.)
		for k in cf.get_section_keys("remap") if cf.has_section("remap") else PackedStringArray():
			if String(k).begins_with("path."):
				dest = String(cf.get_value("remap", k, ""))
				break
	return dest != "" and FileAccess.file_exists(dest)
