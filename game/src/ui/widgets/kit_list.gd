class_name KitList
extends VBoxContainer
## Passive + Q/E/R skill descriptions of one fighter, straight from tuning data
## (FighterDef.passive_*, FighterDef.skill(slot) -> ActionDef name/desc/cooldown/stamina).

var compact: bool = false


func _init(p_compact: bool = false) -> void:
	compact = p_compact
	add_theme_constant_override("separation", 8 if compact else 12)


func show_fighter(fid: String) -> void:
	UiKit.clear_children(self)
	var d: FighterDef = UiKit.fighter_def(fid)
	if d == null:
		return
	_entry("P", d.passive_name, "Passive", d.passive_desc)
	for slot in ["q", "e", "r"]:
		var a: ActionDef = d.skill(slot)
		if a == null:
			continue
		var meta: String = "%s cooldown · %s stamina" % [_num(a.cooldown_s) + " s", _num(a.stamina)]
		_entry(slot.to_upper(), a.display_name, meta, a.desc)


static func _num(v: float) -> String:
	return str(int(v)) if is_equal_approx(v, round(v)) else "%.1f" % v


func _entry(key: String, name_text: String, meta: String, desc: String) -> void:
	var h := UiKit.hbox(12)
	var cap := UiKit.panel(&"KeyCap")
	cap.custom_minimum_size = Vector2(34, 30)
	cap.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	var kl := UiKit.label(key, &"Subheading")
	kl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if key == "P":
		kl.add_theme_color_override("font_color", UiKit.GOLD)
	cap.add_child(kl)
	h.add_child(cap)
	var v := UiKit.vbox(0)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var top := UiKit.hbox(10)
	var n := UiKit.label(name_text.to_upper(), &"Subheading")
	top.add_child(n)
	var m := UiKit.label(meta, &"Caption")
	m.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	top.add_child(m)
	v.add_child(top)
	var dl := UiKit.label(desc, &"Small", true)
	dl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if compact:
		dl.add_theme_font_size_override("font_size", 14)
	v.add_child(dl)
	h.add_child(v)
	add_child(h)
