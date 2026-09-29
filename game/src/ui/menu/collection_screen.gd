class_name CollectionScreen
extends MenuScreen
## Collection (docs/UI_CONTRACT.md §5): per fighter mastery level/XP (offline profile, plus the
## online profile when signed in), palettes (locked ones show their unlock level), badges,
## selected palette/badge (Profile.select_palette / select_badge), and lore (title, tagline,
## quote, passive and the three skills).

var fighter_id: String = "nyx"
var online_profile: Dictionary = {}
var _list_buttons: Array[Button] = []
var _group := ButtonGroup.new()
var _preview: FighterPreview
var _detail: VBoxContainer
var _pal_group := ButtonGroup.new()
var _loading_online: bool = false


func build() -> void:
	title = "Collection"
	subtitle = "Mastery, palettes, badges and lore"
	var root := UiKit.hbox(24)
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var list := UiKit.vbox(8)
	list.custom_minimum_size = Vector2(250, 0)
	root.add_child(list)
	list.add_child(UiKit.label("FIGHTERS", &"Caption"))
	for fid in WR.FIGHTER_IDS:
		var f: String = fid
		var b := Button.new()
		b.toggle_mode = true
		b.button_group = _group
		b.theme_type_variation = &"ValueButton"
		b.custom_minimum_size = Vector2(250, 64)
		b.focus_mode = Control.FOCUS_ALL
		b.name = "Fighter_" + fid
		UiKit.hover_focus(b)
		var h := UiKit.hbox(12)
		h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		h.offset_left = 10
		h.offset_right = -10
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var e := FighterEmblem.new()
		e.fighter_id = fid
		e.custom_minimum_size = Vector2(44, 44)
		e.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		h.add_child(e)
		var tv := UiKit.vbox(-4)
		tv.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		tv.mouse_filter = Control.MOUSE_FILTER_IGNORE
		tv.add_child(UiKit.label(UiKit.fighter_name(fid).to_upper(), &"Subheading"))
		var lv := UiKit.label("", &"Small")
		lv.name = "Level"
		tv.add_child(lv)
		h.add_child(tv)
		b.add_child(h)
		b.pressed.connect(func() -> void: select_fighter(f))
		b.focus_entered.connect(func() -> void:
			if f != fighter_id:
				select_fighter(f))
		list.add_child(b)
		_list_buttons.append(b)
	var ctrls: Array[Control] = []
	for b2 in _list_buttons:
		ctrls.append(b2)
	UiKit.chain_vertical(ctrls, true)
	list.add_child(UiKit.spacer(false, true))
	_preview = FighterPreview.new()
	_preview.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_preview.size_flags_stretch_ratio = 0.8
	_preview.custom_minimum_size = Vector2(320, 0)
	root.add_child(_preview)
	var right := UiKit.panel(&"PanelGlass")
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.custom_minimum_size = Vector2(560, 0)
	root.add_child(right)
	_detail = UiKit.vbox(12)
	var m := UiKit.margin(2, 2, 14, 2)
	m.add_child(_detail)
	right.add_child(UiKit.scroll(m))


func enter(params: Dictionary) -> void:
	if not params.get("back", false):
		var fid: String = UiState.last_fighter if WR.FIGHTER_IDS.has(UiState.last_fighter) else WR.FIGHTER_IDS[0]
		fighter_id = ""
		select_fighter(fid)
	else:
		_rebuild_detail()
	_refresh_levels()
	if Online.is_logged_in() and not _loading_online:
		_load_online()


func default_focus() -> Control:
	for b in _list_buttons:
		if b.button_pressed:
			return b
	return _list_buttons[0]


func _refresh_levels() -> void:
	for i in range(_list_buttons.size()):
		var fid: String = WR.FIGHTER_IDS[i]
		var l: Label = _list_buttons[i].find_child("Level", true, false) as Label
		if l != null:
			l.text = "Mastery %d" % Profile.fighter_level(fid)


func _load_online() -> void:
	_loading_online = true
	var r: Dictionary = await Online.profile_get()
	_loading_online = false
	if not is_inside_tree():
		return
	if bool(r["ok"]) and r["data"] is Dictionary:
		online_profile = r["data"]
		_rebuild_detail()


func select_fighter(fid: String) -> void:
	if fid == fighter_id:
		return
	fighter_id = fid
	UiState.last_fighter = fid
	for i in range(_list_buttons.size()):
		_list_buttons[i].set_pressed_no_signal(WR.FIGHTER_IDS[i] == fid)
	_preview.show_fighter(fid, Profile.selected_palette(fid), "select")
	_rebuild_detail()


func _rebuild_detail() -> void:
	var fo: Control = get_viewport().gui_get_focus_owner() if is_inside_tree() else null
	var fo_name: String = String(fo.name) if fo != null and _detail.is_ancestor_of(fo) else ""
	UiKit.clear_children(_detail)
	var d: FighterDef = UiKit.fighter_def(fighter_id)
	if d == null:
		return
	var head := UiKit.hbox(14)
	head.add_child(UiKit.label(d.display_name, &"Title"))
	var tl := UiKit.label(d.title.to_upper(), &"Subheading")
	tl.add_theme_color_override("font_color", UiKit.ACCENT_BRIGHT)
	tl.size_flags_vertical = Control.SIZE_SHRINK_END
	head.add_child(tl)
	_detail.add_child(head)
	_detail.add_child(UiKit.label("%s · %s" % [UiKit.species_label(fighter_id), d.role], &"Dim"))
	# mastery
	_detail.add_child(UiKit.label("MASTERY", &"Caption"))
	_detail.add_child(_mastery_row("Offline", Profile.fighter_xp(fighter_id)))
	var of: Dictionary = (online_profile.get("fighters", {}) as Dictionary).get(fighter_id, {}) if online_profile.get("fighters") is Dictionary else {}
	if not of.is_empty():
		_detail.add_child(_mastery_row("Online", int(of.get("xp", 0))))
	elif Online.is_logged_in():
		_detail.add_child(UiKit.label("Online mastery is loading…" if _loading_online else "Online mastery unavailable right now.", &"Small"))
	else:
		_detail.add_child(UiKit.label("Sign in (Play online → Account) to see your online mastery. Offline and online progress are kept separately.", &"Small", true))
	# palettes
	_detail.add_child(UiKit.label("PALETTES", &"Caption"))
	var pg := UiKit.grid(4, 8, 8)
	_detail.add_child(pg)
	var lvl: int = Profile.fighter_level(fighter_id)
	var sel_pal: String = Profile.selected_palette(fighter_id)
	for p in UiKit.palette_ids(fighter_id):
		var need: int = int(Profile.PALETTE_UNLOCK.get(p, 1))
		var pb := PaletteButton.new(fighter_id, p, lvl < need, need)
		pb.name = "Palette_" + p
		pb.button_group = _pal_group
		pb.button_pressed = p == sel_pal
		pb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		pb.custom_minimum_size = Vector2(120, 70)
		var pal: String = p
		pb.pressed.connect(func() -> void: _choose_palette(pal))
		pg.add_child(pb)
	# badges
	_detail.add_child(UiKit.label("BADGES", &"Caption"))
	var bg := UiKit.grid(2, 8, 8)
	_detail.add_child(bg)
	var have: Array[String] = Profile.badges()
	var selected: String = String(Profile.data.get("selected_badge", ""))
	for tier in UiKit.BADGE_TIERS:
		var bid: String = "%s_%s" % [fighter_id, tier]
		bg.add_child(_badge_button(bid, have.has(bid), selected == bid, "Mastery %d" % int(Profile.BADGE_UNLOCK.get(tier, 1))))
	bg.add_child(_badge_button("pack_debut", have.has("pack_debut"), selected == "pack_debut", "Finish a match"))
	if selected != "":
		var clr := UiKit.button("Clear badge", &"SmallButton", func() -> void:
			Profile.select_badge("")
			_rebuild_detail())
		clr.name = "ClearBadge"
		bg.add_child(clr)
	# lore
	_detail.add_child(UiKit.label("LORE & KIT", &"Caption"))
	_detail.add_child(UiKit.label(d.tagline, &"Subheading"))
	var q := UiKit.label("“%s”" % d.quote, &"Dim")
	_detail.add_child(q)
	var kit := KitList.new(false)
	kit.show_fighter(fighter_id)
	_detail.add_child(kit)
	if fo_name != "":
		var t: Control = _detail.find_child(fo_name, true, false) as Control
		if t != null:
			UiKit.focus.call_deferred(t)


func _mastery_row(label_text: String, xp: int) -> VBoxContainer:
	var v := UiKit.vbox(4)
	var lvl: int = Profile.level_for_xp(xp)
	var h := UiKit.hbox(10)
	h.add_child(UiKit.icon("star", 18.0, UiKit.GOLD))
	h.add_child(UiKit.label("%s  ·  Level %d" % [label_text.to_upper(), lvl], &"Subheading"))
	h.add_child(UiKit.spacer())
	var cap: int = Profile.LEVEL_XP.size()
	var lo: int = Profile.LEVEL_XP[lvl - 1]
	var txt: String = "Max level · %d XP" % xp
	var frac: float = 1.0
	if lvl < cap:
		var hi: int = Profile.LEVEL_XP[lvl]
		txt = "%d / %d XP" % [xp - lo, hi - lo]
		frac = float(xp - lo) / float(maxi(1, hi - lo))
	h.add_child(UiKit.label(txt, &"Small"))
	v.add_child(h)
	var bar := UiKit.progress(frac, 1.0, &"XpBar")
	bar.custom_minimum_size = Vector2(0, 8)
	v.add_child(bar)
	return v


func _badge_button(bid: String, owned: bool, selected: bool, how: String) -> Button:
	var b := Button.new()
	b.theme_type_variation = &"ValueButton"
	b.toggle_mode = true
	b.button_pressed = selected
	b.focus_mode = Control.FOCUS_ALL
	b.custom_minimum_size = Vector2(240, 56)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.name = "Badge_" + bid
	UiKit.hover_focus(b)
	var h := UiKit.hbox(10)
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	h.offset_left = 12
	h.offset_right = -10
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(UiKit.icon(UiKit.badge_icon_kind(bid), 24.0, UiKit.GOLD if owned else UiKit.TEXT_FAINT))
	var tv := UiKit.vbox(-3)
	tv.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	tv.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var n := UiKit.label(UiKit.badge_display(bid))
	n.add_theme_color_override("font_color", UiKit.TEXT if owned else UiKit.TEXT_FAINT)
	tv.add_child(n)
	var sub: String = ("Selected" if selected else "Earned") if owned else how
	tv.add_child(UiKit.label(sub.to_upper(), &"Caption"))
	h.add_child(tv)
	h.add_child(UiKit.spacer())
	if not owned:
		h.add_child(UiKit.icon("lock", 16.0, UiKit.TEXT_FAINT))
	elif selected:
		h.add_child(UiKit.icon("check", 18.0, UiKit.OK))
	b.add_child(h)
	b.pressed.connect(func() -> void:
		if not owned:
			b.set_pressed_no_signal(false)
			UiKit.play("ui_error")
			toast("%s unlocks with %s." % [UiKit.badge_display(bid), how.to_lower()], "info")
			return
		Profile.select_badge(bid)
		_sync_online({"selected_badge": bid})
		_rebuild_detail())
	return b


func _choose_palette(pal: String) -> void:
	if not Profile.unlocked_palettes(fighter_id).has(pal):
		UiKit.play("ui_error")
		toast("%s unlocks at mastery %d." % [UiKit.palette_display_name(fighter_id, pal), int(Profile.PALETTE_UNLOCK.get(pal, 1))], "info")
		_rebuild_detail()
		return
	Profile.select_palette(fighter_id, pal)
	_preview.set_palette(pal)
	var of: Dictionary = (online_profile.get("fighters", {}) as Dictionary).get(fighter_id, {}) if online_profile.get("fighters") is Dictionary else {}
	if (of.get("palettes", []) as Array).has(pal):
		_sync_online({"selected_palettes": {fighter_id: pal}})
	_rebuild_detail()


func _sync_online(changes: Dictionary) -> void:
	## Mirrors a cosmetic choice to the online profile when it is unlocked there too.
	if not Online.is_logged_in() or online_profile.is_empty():
		return
	if changes.has("selected_badge") and not (online_profile.get("badges", []) as Array).has(changes["selected_badge"]):
		return
	var r: Dictionary = await Online.profile_patch(changes)
	if is_inside_tree() and bool(r["ok"]) and r["data"] is Dictionary:
		online_profile = r["data"]
