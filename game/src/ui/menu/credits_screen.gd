class_name CreditsScreen
extends MenuScreen
## Credits (docs/UI_CONTRACT.md §8): team, tools and licences from res://data/credits.json,
## plus the Godot Engine licence and third-party notices reported by the engine itself.
## One focusable text column: D-pad / arrows / page keys / wheel scroll it.

const SOURCE: String = "res://data/credits.json"

var text: RichTextLabel


func build() -> void:
	title = "Credits"
	subtitle = "Team, tools and licences"
	var mw := MaxWidthContainer.new()
	mw.max_width = 1180.0
	mw.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(mw)
	var p := UiKit.panel(&"PanelGlass")
	mw.add_child(p)
	text = RichTextLabel.new()
	text.bbcode_enabled = true
	text.scroll_active = true
	text.focus_mode = Control.FOCUS_ALL
	text.selection_enabled = false
	text.fit_content = false
	text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	text.name = "CreditsText"
	p.add_child(text)
	text.text = compose()


func enter(_params: Dictionary) -> void:
	text.scroll_to_line(0)


func hints() -> Array:
	return [["updown", "Scroll"], ["back", "Back"]]


func default_focus() -> Control:
	return text


func screen_input(event: InputEvent) -> bool:
	var sb: VScrollBar = text.get_v_scroll_bar()
	if event.is_action_pressed("ui_down", true):
		sb.value += 60.0
		return true
	if event.is_action_pressed("ui_up", true):
		sb.value -= 60.0
		return true
	return false


static func _esc(s: String) -> String:
	return s.replace("[", "[lb]")


static func compose() -> String:
	var out: PackedStringArray = PackedStringArray()
	var head: Font = UiKit.FONT_DISPLAY_XBOLD
	var d: Dictionary = {}
	if FileAccess.file_exists(SOURCE):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SOURCE))
		if parsed is Dictionary:
			d = parsed
	var accent: String = UiKit.ACCENT_BRIGHT.to_html(false)
	var dim: String = UiKit.TEXT_DIM.to_html(false)
	out.append("[center][font_size=64][font=%s]%s[/font][/font_size]\n[font_size=20][color=#%s]%s[/color][/font_size]\n[font_size=15][color=#%s]%s[/color][/font_size][/center]\n" % [
		head.resource_path, _esc(String(d.get("title", "WILDRUSH"))), accent, _esc(String(d.get("tagline", "Five animals. One pack."))).to_upper(),
		dim, "%s · Godot %s" % [WR.BUILD_ID, String(Engine.get_version_info()["string"])]])
	for sec in d.get("sections", []):
		var s: Dictionary = sec
		out.append("\n[font_size=30][font=%s][color=#%s]%s[/color][/font][/font_size]" % [UiKit.FONT_DISPLAY.resource_path, accent, _esc(String(s.get("heading", ""))).to_upper()])
		for line in s.get("lines", []):
			out.append(_esc(String(line)))
	for lic in d.get("licences", []):
		var l: Dictionary = lic
		out.append("\n[font_size=26][font=%s]%s[/font][/font_size]" % [UiKit.FONT_DISPLAY.resource_path, _esc(String(l.get("name", ""))).to_upper()])
		out.append("[font_size=14][color=#%s]%s[/color][/font_size]" % [dim, _esc(String(l.get("text", "")))])
	# the engine's own licence and third-party notices (required attribution)
	out.append("\n[font_size=30][font=%s][color=#%s]GODOT ENGINE[/color][/font][/font_size]" % [UiKit.FONT_DISPLAY.resource_path, accent])
	out.append("[font_size=14][color=#%s]%s[/color][/font_size]" % [dim, _esc(Engine.get_license_text())])
	out.append("\n[font_size=26][font=%s]THIRD-PARTY COMPONENTS IN GODOT[/font][/font_size]" % UiKit.FONT_DISPLAY.resource_path)
	var lic_used: Dictionary = {}
	for comp in Engine.get_copyright_info():
		var c: Dictionary = comp
		var lines: PackedStringArray = PackedStringArray()
		for part in c.get("parts", []):
			var pd: Dictionary = part
			for cr in pd.get("copyright", []):
				lines.append("© " + String(cr))
			var ln: String = String(pd.get("license", ""))
			if ln != "":
				lines.append("Licence: " + ln)
				for token in ln.replace("(", " ").replace(")", " ").split(" ", false):
					if token != "or" and token != "and":
						lic_used[token] = true
		out.append("[b]%s[/b]\n[font_size=14][color=#%s]%s[/color][/font_size]" % [_esc(String(c.get("name", ""))), dim, _esc("\n".join(lines))])
	var infos: Dictionary = Engine.get_license_info()
	for k in infos.keys():
		if not lic_used.has(String(k)):
			continue
		out.append("\n[b]%s[/b]\n[font_size=13][color=#%s]%s[/color][/font_size]" % [_esc(String(k)), dim, _esc(String(infos[k]))])
	return "\n".join(out)
