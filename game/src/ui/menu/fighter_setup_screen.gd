class_name FighterSetupScreen
extends MenuScreen
## Shared fighter + palette selection with a large animated 3D preview and the fighter's kit.
## Subclasses add their mode options (`build_options`) and the start action (`start`).

var fighter_id: String = "nyx"
var palette: String = "default"
var cards: Array[FighterCard] = []
var palette_buttons: Array[PaletteButton] = []
var start_button: Button
var preview: FighterPreview
var _card_group := ButtonGroup.new()
var _pal_group := ButtonGroup.new()
var _pal_row: HBoxContainer
var _kit: KitList
var _name: Label
var _title_l: Label
var _tagline: Label
var _quote: Label
var _options: VBoxContainer


func build() -> void:
	var root := UiKit.hbox(28)
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	# left: preview + identity
	var left := Control.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.size_flags_stretch_ratio = 0.95
	left.mouse_filter = Control.MOUSE_FILTER_IGNORE
	left.custom_minimum_size = Vector2(420, 0)
	root.add_child(left)
	preview = FighterPreview.new()
	preview.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	preview.offset_bottom = -120
	left.add_child(preview)
	var ident := UiKit.vbox(0)
	ident.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	ident.offset_top = -126
	ident.grow_vertical = Control.GROW_DIRECTION_BEGIN
	ident.mouse_filter = Control.MOUSE_FILTER_IGNORE
	left.add_child(ident)
	var name_row := UiKit.hbox(14)
	_name = UiKit.label("", &"Title")
	_name.add_theme_font_size_override("font_size", 58)
	name_row.add_child(_name)
	_title_l = UiKit.label("", &"Subheading")
	_title_l.size_flags_vertical = Control.SIZE_SHRINK_END
	_title_l.add_theme_color_override("font_color", UiKit.ACCENT_BRIGHT)
	name_row.add_child(_title_l)
	ident.add_child(name_row)
	_tagline = UiKit.label("", &"Dim")
	ident.add_child(_tagline)
	_quote = UiKit.label("", &"Small")
	ident.add_child(_quote)
	# right: selection + kit + options
	var right := UiKit.panel(&"PanelGlass")
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.custom_minimum_size = Vector2(600, 0)
	root.add_child(right)
	var rv := UiKit.vbox(10)
	right.add_child(rv)
	var col := UiKit.vbox(12)
	var sc := UiKit.scroll(UiKit.margin(2, 2, 14, 2))
	(sc.get_child(0) as MarginContainer).add_child(col)
	rv.add_child(sc)
	col.add_child(UiKit.label("CHOOSE YOUR FIGHTER", &"Caption"))
	var crow := UiKit.hbox(8)
	col.add_child(crow)
	for fid in WR.FIGHTER_IDS:
		var c := FighterCard.new(fid, true)
		c.button_group = _card_group
		c.custom_minimum_size = Vector2(104, 138)
		var f: String = fid
		c.pressed.connect(func() -> void: select_fighter(f))
		c.focus_entered.connect(func() -> void:
			if f != fighter_id:
				select_fighter(f))
		crow.add_child(c)
		cards.append(c)
	col.add_child(UiKit.label("PALETTE", &"Caption"))
	_pal_row = UiKit.hbox(8)
	col.add_child(_pal_row)
	_options = UiKit.vbox(10)
	col.add_child(_options)
	build_options(_options)
	col.add_child(UiKit.label("KIT", &"Caption"))
	_kit = KitList.new(true)
	col.add_child(_kit)
	var foot := UiKit.hbox(12)
	rv.add_child(foot)
	foot.add_child(UiKit.spacer())
	start_button = UiKit.button(start_label(), &"PrimaryButton", start)
	start_button.custom_minimum_size = Vector2(260, 52)
	foot.add_child(start_button)


## Mode-specific options (difficulty, lineup / dummies).
func build_options(_box: VBoxContainer) -> void:
	pass


func start_label() -> String:
	return "START"


func start() -> void:
	pass


func enter(params: Dictionary) -> void:
	if params.get("back", false):
		return
	var fid: String = UiState.last_fighter if WR.FIGHTER_IDS.has(UiState.last_fighter) else WR.FIGHTER_IDS[0]
	for c in cards:
		c.set_level(Profile.fighter_level(c.fighter_id))
		c.set_palette(Profile.selected_palette(c.fighter_id))
	select_fighter(fid, true)
	UiKit.music("music_select")


func exit() -> void:
	UiKit.music("music_menu")


func default_focus() -> Control:
	for c in cards:
		if c.fighter_id == fighter_id:
			return c
	return start_button


func hints() -> Array:
	return [["accept", "Select"], ["back", "Back"]]


func select_fighter(fid: String, force: bool = false) -> void:
	if fid == fighter_id and not force:
		return
	fighter_id = fid
	UiState.last_fighter = fid
	for c in cards:
		c.set_pressed_no_signal(c.fighter_id == fid)
		c.set_state("")
	var d: FighterDef = UiKit.fighter_def(fid)
	if d != null:
		_name.text = d.display_name
		_title_l.text = d.title.to_upper()
		_tagline.text = "%s · %s — %s" % [UiKit.species_label(fid), d.role, d.tagline]
		_quote.text = "“%s”" % d.quote
	_kit.show_fighter(fid)
	_build_palettes()
	preview.show_fighter(fid, palette, "select")
	on_fighter_changed()


func on_fighter_changed() -> void:
	pass


func _build_palettes() -> void:
	UiKit.clear_children(_pal_row)
	palette_buttons.clear()
	var unlocked: Array[String] = Profile.unlocked_palettes(fighter_id)
	palette = Profile.selected_palette(fighter_id)
	for p in UiKit.palette_ids(fighter_id):
		if not unlocked.has(p):
			continue   # setup screens list only unlocked palettes (Collection shows locked ones)
		var pb := PaletteButton.new(fighter_id, p)
		pb.button_group = _pal_group
		pb.button_pressed = p == palette
		var pal: String = p
		pb.pressed.connect(func() -> void: select_palette(pal))
		_pal_row.add_child(pb)
		palette_buttons.append(pb)
	if palette_buttons.size() == 1:
		var note := UiKit.label("More palettes unlock at mastery 3, 5 and 7.", &"Small")
		note.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		_pal_row.add_child(note)


func select_palette(pal: String) -> void:
	palette = pal
	Profile.select_palette(fighter_id, pal)
	preview.set_palette(pal)
	for c in cards:
		if c.fighter_id == fighter_id:
			c.set_palette(pal)
