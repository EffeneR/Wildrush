class_name PortraitCache
extends Node
## Fighter portrait textures (docs/UI_CONTRACT.md): res://assets/ui/portraits/<id>.png when the
## rendered file exists, otherwise a one-off runtime SubViewport capture of the fighter
## preview (bust framing). Captures run one at a time on a node under the scene root, so they
## survive scene changes; headless runs (no renderer) return no portrait and the UI keeps the
## vector species emblem.

signal portrait_ready(key: String, tex: Texture2D)

const DIR: String = "res://assets/ui/portraits/"
const SIZE: Vector2i = Vector2i(360, 440)

static var _cache: Dictionary = {}       # "fid:palette" -> Texture2D
static var _node: PortraitCache = null

var _queue: Array[String] = []
var _busy: bool = false


static func key(fid: String, pal: String) -> String:
	return "%s:%s" % [fid, pal]


static func instance() -> PortraitCache:
	if _node != null and is_instance_valid(_node):
		return _node
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null or tree.root == null:
		return null
	_node = PortraitCache.new()
	_node.name = "PortraitCache"
	tree.root.add_child.call_deferred(_node)
	return _node


static func get_portrait(fid: String, pal: String = "default") -> Texture2D:
	## Returns the portrait if known; otherwise schedules a capture (portrait_ready fires later)
	## and returns null.
	var k: String = key(fid, pal)
	if _cache.has(k):
		return _cache[k]
	var file: String = DIR + fid + ".png"
	if pal == "default" and ResourceLoader.exists(file):
		var t: Texture2D = load(file) as Texture2D
		_cache[k] = t
		return t
	if DisplayServer.get_name() == "headless":
		return null
	var n: PortraitCache = instance()
	if n != null and not n._queue.has(k):
		n._queue.append(k)
	return null


func _process(_delta: float) -> void:
	if _busy or _queue.is_empty():
		return
	var k: String = _queue.pop_front()
	if _cache.has(k):
		return
	_busy = true
	_capture(k)


func _capture(k: String) -> void:
	var parts: PackedStringArray = k.split(":")
	var fid: String = parts[0]
	var pal: String = parts[1] if parts.size() > 1 else "default"
	var vp := SubViewport.new()
	vp.own_world_3d = true
	vp.transparent_bg = true
	vp.size = SIZE
	vp.msaa_3d = Viewport.MSAA_4X
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(vp)
	var prev := FighterPreviewStage.build(vp, fid, pal, "bust")
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var img: Image = vp.get_texture().get_image()
	if img != null and not img.is_empty():
		var t: ImageTexture = ImageTexture.create_from_image(img)
		_cache[k] = t
		portrait_ready.emit(k, t)
	if prev != null:
		prev.queue_free()
	vp.queue_free()
	_busy = false
