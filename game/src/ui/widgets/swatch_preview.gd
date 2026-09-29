class_name SwatchPreview
extends HBoxContainer
## Live preview of the relation colours for the selected colour-vision mode. Every swatch pairs
## its colour with a distinct shape and a label (ally circle, enemy diamond, neutral square,
## contested hatched hexagon, inactive hollow ring).

const ITEMS: Array = [["ally", "Ally"], ["enemy", "Enemy"], ["neutral", "Neutral"], ["contested", "Contested"],
	["inactive", "Inactive"]]


class Swatch extends Control:
	var relation: String = "ally"

	func _init(r: String) -> void:
		relation = r
		custom_minimum_size = Vector2(46, 46)
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var c: Color = Settings.relation_color(relation)
		var ctr: Vector2 = size * 0.5
		var r: float = minf(size.x, size.y) * 0.42
		match relation:
			"ally":
				draw_circle(ctr, r, c, true, -1.0, true)
			"enemy":
				draw_colored_polygon(PackedVector2Array([ctr + Vector2(0, -r), ctr + Vector2(r, 0), ctr + Vector2(0, r), ctr + Vector2(-r, 0)]), c)
			"neutral":
				draw_rect(Rect2(ctr - Vector2(r, r) * 0.8, Vector2(r, r) * 1.6), c)
			"contested":
				var pts := PackedVector2Array()
				for i in range(6):
					var a: float = TAU * float(i) / 6.0
					pts.append(ctr + Vector2(cos(a), sin(a)) * r)
				draw_colored_polygon(pts, Color(c, 0.35))
				var ally: Color = Settings.relation_color("ally")
				var enemy: Color = Settings.relation_color("enemy")
				for k in range(-3, 4):
					var off: float = float(k) * r * 0.32
					draw_line(ctr + Vector2(off - r * 0.6, r * 0.6), ctr + Vector2(off + r * 0.6, -r * 0.6), ally if k % 2 == 0 else enemy, 3.0, true)
				pts.append(pts[0])
				draw_polyline(pts, c, 2.0, true)
			"inactive":
				draw_arc(ctr, r * 0.9, 0.0, TAU, 40, c, 4.0, true)


var _swatches: Array[Swatch] = []


func _ready() -> void:
	add_theme_constant_override("separation", 22)
	for it in ITEMS:
		var col := UiKit.vbox(6)
		var sw := Swatch.new(String(it[0]))
		sw.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		col.add_child(sw)
		_swatches.append(sw)
		var l := UiKit.label(String(it[1]).to_upper(), &"Caption")
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		col.add_child(l)
		add_child(col)
	Settings.changed.connect(_on_changed)


func _on_changed(section: String) -> void:
	if section == "access":
		refresh()


func refresh() -> void:
	for s in _swatches:
		s.queue_redraw()
