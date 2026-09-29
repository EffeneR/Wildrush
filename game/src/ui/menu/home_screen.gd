class_name HomeScreen
extends MenuScreen
## Home: Play Offline, Training, Play Online, Collection, History & Replays, Settings, Credits,
## Quit (confirmed). Shows the local profile (name, selected badge, record) and build id.

const ITEMS: Array = [
	["offline", "Play offline", "A full 5v5 Turf Shift match against bots on Briarport."],
	["training", "Training", "Practise moves and skills against configurable dummies."],
	["online", "Play online", "Account, party, casual and ranked queues, private matches."],
	["collection", "Collection", "Mastery, palettes, badges and fighter lore."],
	["history", "History & replays", "Your recent matches and recorded replays."],
	["settings", "Settings", "Display, audio, controls, accessibility and online service."],
	["credits", "Credits", "Team, tools and licences."],
	["quit", "Quit", "Close WILDRUSH."],
]

var _buttons: Array[Button] = []
var _desc: Label
var _preview: FighterPreview
var _name: Label
var _badge_row: HBoxContainer
var _stats: HBoxContainer
var _feature_label: Label
var _feature_fid: String = ""


func build() -> void:
	title = "Home"
	var root := UiKit.hbox(40)
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var left := UiKit.vbox(6)
	left.custom_minimum_size = Vector2(560, 0)
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.size_flags_stretch_ratio = 0.9
	root.add_child(left)
	var logo := WordmarkLogo.new()
	logo.font_size = 104
	left.add_child(logo)
	left.add_child(UiKit.gap(18))
	var list := UiKit.vbox(0)
	left.add_child(list)
	for it in ITEMS:
		var arr: Array = it
		var id: String = String(arr[0])
		var b := UiKit.button(String(arr[1]).to_upper(), &"MenuItem", func() -> void: _activate(id))
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.custom_minimum_size = Vector2(420, 50)
		b.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		b.focus_entered.connect(func() -> void: _desc.text = String(arr[2]))
		b.name = "Menu_" + id
		list.add_child(b)
		_buttons.append(b)
	var ctrls: Array[Control] = []
	for b in _buttons:
		ctrls.append(b)
	UiKit.chain_vertical(ctrls, true)
	left.add_child(UiKit.gap(10))
	_desc = UiKit.label("", &"Dim")
	_desc.custom_minimum_size = Vector2(0, 24)
	left.add_child(_desc)
	left.add_child(UiKit.spacer(false, true))
	# right: featured fighter + profile card
	var right := UiKit.vbox(10)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(right)
	_feature_label = UiKit.label("", &"Caption")
	_feature_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	right.add_child(_feature_label)
	_preview = FighterPreview.new()
	_preview.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(_preview)
	var card := UiKit.panel(&"PanelGlass")
	right.add_child(card)
	var ch := UiKit.hbox(24)
	card.add_child(ch)
	var who := UiKit.vbox(2)
	who.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	who.add_child(UiKit.label("LOCAL PROFILE", &"Caption"))
	_name = UiKit.label("", &"Heading")
	who.add_child(_name)
	_badge_row = UiKit.hbox(8)
	who.add_child(_badge_row)
	ch.add_child(who)
	_stats = UiKit.hbox(28)
	_stats.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ch.add_child(_stats)


func enter(_params: Dictionary) -> void:
	_refresh()


func default_focus() -> Control:
	return _buttons[0] if not _buttons.is_empty() else null


func hints() -> Array:
	return [["accept", "Select"], ["back", "Quit"]]


func _refresh() -> void:
	_name.text = String(Profile.data.get("display_name", "Player"))
	UiKit.clear_children(_badge_row)
	var badge: String = String(Profile.data.get("selected_badge", ""))
	if badge != "":
		_badge_row.add_child(UiKit.icon(UiKit.badge_icon_kind(badge), 18.0, UiKit.GOLD))
		_badge_row.add_child(UiKit.label(UiKit.badge_display(badge), &"Dim"))
	else:
		_badge_row.add_child(UiKit.label("No badge selected — earn badges through fighter mastery.", &"Small"))
	UiKit.clear_children(_stats)
	var totals: Dictionary = Profile.data.get("totals", {})
	var matches: int = int(totals.get("matches", 0))
	var wins: int = int(totals.get("wins", 0))
	_stats.add_child(UiKit.key_value("Matches", str(matches)))
	_stats.add_child(UiKit.key_value("Wins", str(wins)))
	# featured fighter: highest mastery (ties: roster order); first launch shows Nyx
	var best: String = WR.FIGHTER_IDS[0]
	var best_xp: int = -1
	for fid in WR.FIGHTER_IDS:
		var xp: int = Profile.fighter_xp(fid)
		if xp > best_xp:
			best_xp = xp
			best = fid
	_stats.add_child(UiKit.key_value("Top mastery", "%s  LV %d" % [UiKit.fighter_name(best), Profile.fighter_level(best)]))
	if best != _feature_fid:
		_feature_fid = best
		_preview.show_fighter(best, Profile.selected_palette(best), "idle")
	else:
		_preview.set_palette(Profile.selected_palette(best))
	var d: FighterDef = UiKit.fighter_def(best)
	if d != null:
		_feature_label.text = "%s — %s" % [d.display_name, d.title.to_upper()]


func _activate(id: String) -> void:
	match id:
		"settings":
			menu.open_settings()
		"quit":
			menu.confirm_quit()
		_:
			menu.open_screen(id)
