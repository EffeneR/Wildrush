class_name MaxWidthContainer
extends Container
## Centres its children and caps their width (ultrawide-safe layouts: content stays readable
## at 3440x1440 while 16:9 uses the full width).

@export var max_width: float = 1720.0:
	set(v):
		max_width = v
		queue_sort()


func _notification(what: int) -> void:
	if what == NOTIFICATION_SORT_CHILDREN:
		var w: float = minf(size.x, max_width)
		var x: float = floorf((size.x - w) * 0.5)
		for c in get_children():
			if c is Control and (c as Control).visible:
				fit_child_in_rect(c as Control, Rect2(x, 0.0, w, size.y))


func _get_minimum_size() -> Vector2:
	var m := Vector2.ZERO
	for c in get_children():
		if c is Control and (c as Control).visible:
			var cm: Vector2 = (c as Control).get_combined_minimum_size()
			m.x = maxf(m.x, cm.x)
			m.y = maxf(m.y, cm.y)
	return m
