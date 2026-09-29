class_name FighterPreview
extends Control
## Animated 3D fighter preview for select/collection screens (docs/UI_CONTRACT.md "Fighter
## previews"): FighterView.create_preview() inside a SubViewport with its own World3D, camera,
## key/rim lights and a floor disc (FighterPreviewStage). The viewport renders at the
## control's physical pixel size (crisp at any resolution/UI scale), transparent background.
## Mouse drag turns the model.

@export var fighter_id: String = "nyx"
@export var palette: String = "default"
## "full" frames the whole body, "bust" frames head and shoulders.
@export var framing: String = "full"
@export var show_stage: bool = true

var stage: FighterPreviewStage = null
var _vp: SubViewport = null
var _tex: TextureRect = null
var _dragging: bool = false


func _ready() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_PASS
	_vp = SubViewport.new()
	_vp.name = "PreviewViewport"
	_vp.own_world_3d = true
	_vp.transparent_bg = true
	_vp.msaa_3d = Viewport.MSAA_4X
	_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_vp.size = Vector2i(64, 64)
	add_child(_vp)
	_tex = TextureRect.new()
	_tex.texture = _vp.get_texture()
	_tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_tex.stretch_mode = TextureRect.STRETCH_SCALE
	_tex.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_tex)
	stage = FighterPreviewStage.build(_vp, fighter_id, palette, framing, show_stage)
	resized.connect(_fit)
	visibility_changed.connect(_on_visibility)
	_fit()


func show_fighter(fid: String, pal: String = "default", clip: String = "select") -> void:
	fighter_id = fid
	palette = pal
	if stage != null:
		stage.set_fighter(fid, pal, clip)


func set_palette(pal: String) -> void:
	palette = pal
	if stage != null:
		stage.set_palette(pal)


func play_clip(clip: String) -> void:
	if stage != null:
		stage.play_clip(clip)


func set_accent(c: Color) -> void:
	if stage != null:
		stage.set_accent(c)


func _physical_scale() -> float:
	var s: float = get_global_transform_with_canvas().get_scale().x
	var vp: Viewport = get_viewport()
	if vp != null:
		s *= vp.get_final_transform().get_scale().x
	return clampf(s, 0.25, 4.0)


func _fit() -> void:
	if _vp == null:
		return
	var px: Vector2 = size * _physical_scale()
	var w: int = clampi(int(round(px.x)), 16, 2560)
	var h: int = clampi(int(round(px.y)), 16, 2560)
	if _vp.size != Vector2i(w, h):
		_vp.size = Vector2i(w, h)


func _on_visibility() -> void:
	if _vp != null:
		_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS if is_visible_in_tree() else SubViewport.UPDATE_DISABLED
	if is_visible_in_tree():
		_fit.call_deferred()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		_dragging = (event as InputEventMouseButton).pressed
	elif event is InputEventMouseMotion and _dragging and stage != null:
		stage.set_yaw(stage.yaw + (event as InputEventMouseMotion).relative.x * 0.012)
