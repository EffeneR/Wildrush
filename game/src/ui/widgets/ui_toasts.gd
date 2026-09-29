class_name UiToasts
extends VBoxContainer
## Transient notifications (top-right): errors, invites, lobby notices. Each toast carries an
## icon + text so its meaning never depends on colour.
##   UiToasts.notify(self, "Invite sent to fox_fan", "ok")

const GROUP: StringName = &"wr_toasts"
const LIFETIME_S: float = 4.5
const MAX_TOASTS: int = 4


static func notify(context: Node, text: String, kind: String = "info") -> void:
	if context == null or not context.is_inside_tree():
		return
	var host: UiToasts = context.get_tree().get_first_node_in_group(GROUP) as UiToasts
	if host == null:
		var layer := CanvasLayer.new()
		layer.layer = 90
		layer.process_mode = Node.PROCESS_MODE_ALWAYS
		var scene_root: Node = context.get_tree().current_scene
		if scene_root == null:
			scene_root = context.get_tree().root
		scene_root.add_child(layer)
		host = UiToasts.new()
		layer.add_child(host)
	host.push(text, kind)


func _init() -> void:
	add_to_group(GROUP)
	set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	grow_horizontal = Control.GROW_DIRECTION_BEGIN
	offset_right = -24
	offset_top = 84
	offset_left = -24
	add_theme_constant_override("separation", 8)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	alignment = BoxContainer.ALIGNMENT_BEGIN


func push(text: String, kind: String) -> void:
	var col: Color = UiKit.TEXT
	var ic: String = "info"
	var cue: String = "ui_notify"
	match kind:
		"error":
			col = UiKit.ERR
			ic = "error"
			cue = "ui_error"
		"ok":
			col = UiKit.OK
			ic = "check"
		"warn":
			col = UiKit.WARN
			ic = "warning"
		"chat":
			ic = "chat"
			cue = "ui_chat"
	var p := UiKit.panel(&"Toast")
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.custom_minimum_size = Vector2(320, 0)
	var sb: StyleBoxFlat = (p.get_theme_stylebox("panel") as StyleBoxFlat).duplicate()
	sb.border_color = Color(col, 0.8)
	sb.border_width_left = 4
	p.add_theme_stylebox_override("panel", sb)
	var h := UiKit.hbox(10)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(UiKit.icon(ic, 20.0, col))
	var l := UiKit.label(text, &"", true)
	l.custom_minimum_size = Vector2(260, 0)
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(l)
	p.add_child(h)
	add_child(p)
	while get_child_count() > MAX_TOASTS:
		var old: Node = get_child(0)
		remove_child(old)
		old.queue_free()
	UiKit.play(cue)
	p.modulate.a = 0.0
	var tw: Tween = p.create_tween()
	tw.tween_property(p, "modulate:a", 1.0, 0.15)
	tw.tween_interval(LIFETIME_S)
	tw.tween_property(p, "modulate:a", 0.0, 0.4)
	tw.tween_callback(p.queue_free)
