extends Node3D
## In-engine lineup of all five fighters (G2 evidence, Godot side of the Blender-vs-Godot
## comparison): imported GLB models with the game's palette shader and animation player,
## in the arena's lighting, each playing a clip. Saves a PNG and quits.
##   xvfb-run -a -s "-screen 0 1920x1080x24" godot --path game --resolution 1920x1080 res://tools/roster_lineup.tscn -- --out PATH [--clip idle] [--palette default]

var _t: float = 0.0
var _saved: bool = false


func _ready() -> void:
	var arena := ArenaView.new()
	add_child(arena)
	arena.build(ArenaLayout.load_file())
	var clip: String = Config.get_arg("clip", "idle")
	var palette: String = Config.get_arg("palette", "default")
	var c: Vector3 = arena.layout.zone_center("B") + Vector3(0, 0, 6.0)
	var i: int = 0
	for fid in WR.FIGHTER_IDS:
		var v := FighterView.new()
		v.setup(Tuning.fighter(fid), palette, "self", false)
		add_child(v)
		v.global_position = c + Vector3(-4.0 + 2.0 * i, 0.0, 0.0)
		v.rotation.y = PI   # face the camera (south)
		v.play_clip(clip)
		var l := Label3D.new()
		l.text = "%s  %s" % [Tuning.fighter(fid).display_name, "(GLB)" if v.rig == null else "(stand-in)"]
		l.pixel_size = 0.004
		l.font_size = 48
		l.outline_size = 10
		l.position = Vector3(0, -0.15, 0.6)
		l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		v.add_child(l)
		i += 1
	var cam := Camera3D.new()
	add_child(cam)
	cam.fov = 40.0
	cam.global_position = c + Vector3(0, 1.3, 9.5)
	cam.look_at(c + Vector3(0, 0.95, 0), Vector3.UP)
	cam.current = true


func _process(dt: float) -> void:
	_t += dt
	if _t > 6.0 and not _saved:
		_saved = true
		var out: String = Config.get_arg("out", "user://roster_lineup.png")
		get_viewport().get_texture().get_image().save_png(out)
		print("[lineup] saved " + out)
		get_tree().quit(0)
