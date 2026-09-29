class_name HudRosterStrip
extends HBoxContainer
## Five teammates and five opponents under the score bar (spec §11): animal emblem ringed by
## team relation, dimmed with a respawn countdown while knocked out. Knockouts/respawns are
## public match events, so this shows no hidden positional information.

var host: MatchHost = null
var left_team: int = 0
var _cells: Dictionary = {}          # e -> {"emblem": FighterEmblem, "label": Label}


func setup(p_host: MatchHost, p_left_team: int) -> void:
	host = p_host
	left_team = p_left_team
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_theme_constant_override("separation", 6)
	alignment = BoxContainer.ALIGNMENT_CENTER
	var ents: Array = host.fighter_info.keys()
	ents.sort()
	for team in [left_team, 1 - left_team]:
		for e in ents:
			if int(host.fighter_info[e]["team"]) != team:
				continue
			var v := VBoxContainer.new()
			v.mouse_filter = Control.MOUSE_FILTER_IGNORE
			v.add_theme_constant_override("separation", 0)
			var em := FighterEmblem.new()
			em.fighter_id = String(host.fighter_info[e]["fighter"])
			em.custom_minimum_size = Vector2(30, 30)
			em.mouse_filter = Control.MOUSE_FILTER_IGNORE
			v.add_child(em)
			var l := HudStyle.label("", 12, HudStyle.INK, HudStyle.num_font(), 4)
			l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			l.custom_minimum_size = Vector2(30, 14)
			v.add_child(l)
			add_child(v)
			_cells[int(e)] = {"emblem": em, "label": l}
		if team == left_team:
			var gap := Control.new()
			gap.custom_minimum_size = Vector2(150, 0)
			gap.mouse_filter = Control.MOUSE_FILTER_IGNORE
			add_child(gap)
	refresh()


func refresh() -> void:
	if host == null:
		return
	var rows: Dictionary = {}
	for r in host.roster():
		rows[int(r["e"])] = r
	for e in _cells.keys():
		var c: Dictionary = _cells[e]
		var r: Dictionary = rows.get(e, {})
		var alive: bool = bool(r.get("alive", true))
		var em: FighterEmblem = c["emblem"]
		var rel: String = host.relation_of(int(e))
		em.ring_color = Settings.relation_color("ally" if rel == "self" else rel)
		em.dimmed = not alive
		var l: Label = c["label"]
		if not alive:
			l.text = str(int(ceil(float(r.get("respawn_s", 0.0)))))
			l.add_theme_color_override("font_color", Color(1.0, 0.6, 0.5))
		elif int(e) == host.local_entity:
			l.text = "YOU"
			l.add_theme_color_override("font_color", Color(1.0, 0.9, 0.6))
		else:
			l.text = ""
