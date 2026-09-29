class_name HudScorebar
extends Control
## Top-centre match status: both team scores with progress to the target, match clock,
## active zone with its state (shape + colour + word), rotation countdown and the revealed
## next zone. Left side is always the viewer's team (team 0 for spectators/replays).

var m: Dictionary = {}
var left_team: int = 0
var target: int = 250
var regulation_s: float = 480.0
var zone_names: Dictionary = {}
var _pulse: float = 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	custom_minimum_size = Vector2(620, 96)


func update_state(p_m: Dictionary, dt: float) -> void:
	m = p_m
	_pulse += dt
	queue_redraw()


func _team_block(rect: Rect2, score: int, col: Color, right: bool, label: String) -> void:
	draw_rect(rect, Color(0.05, 0.06, 0.07, 0.8))
	var frac: float = clampf(float(score) / float(target), 0.0, 1.0)
	var bar := Rect2(rect.position + Vector2(0, rect.size.y - 7), Vector2(rect.size.x, 7))
	draw_rect(bar, Color(0, 0, 0, 0.6))
	if right:
		draw_rect(Rect2(Vector2(bar.end.x - bar.size.x * frac, bar.position.y), Vector2(bar.size.x * frac, bar.size.y)), col)
	else:
		draw_rect(Rect2(bar.position, Vector2(bar.size.x * frac, bar.size.y)), col)
	# warning marks at 200 / 230 / 245
	for w in [200, 230, 245]:
		var x: float = bar.size.x * float(w) / target
		var px: float = (bar.end.x - x) if right else (bar.position.x + x)
		draw_line(Vector2(px, bar.position.y - 2), Vector2(px, bar.end.y), Color(1, 1, 1, 0.35), 1.0)
	var f: Font = HudStyle.num_font()
	var s: String = str(score)
	var fs: int = 40
	var w2: Vector2 = f.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
	var sx: float = (rect.end.x - w2.x - 14) if right else (rect.position.x + 14)
	draw_string_outline(f, Vector2(sx, rect.position.y + 42), s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 6, Color(0, 0, 0, 0.8))
	draw_string(f, Vector2(sx, rect.position.y + 42), s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, col.lerp(Color.WHITE, 0.35))
	var lf: Font = HudStyle.body_font()
	var lw: Vector2 = lf.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13)
	var lx: float = (rect.position.x + 12) if right else (rect.end.x - lw.x - 12)
	draw_string(lf, Vector2(lx, rect.position.y + 20), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, HudStyle.INK_DIM)
	# shape tag so team identity never relies on colour alone
	var tagc := Vector2((rect.position.x + 12) if right else (rect.end.x - 12), rect.position.y + 34)
	if label == "ENEMY" or label == "TEAM B":
		draw_colored_polygon(PackedVector2Array([tagc + Vector2(0, -6), tagc + Vector2(6, 0), tagc + Vector2(0, 6), tagc + Vector2(-6, 0)]), col)
	else:
		draw_circle(tagc, 5.5, col)


func _draw() -> void:
	if m.is_empty():
		return
	var scores: Array = m.get("scores", [0, 0])
	var right_team: int = 1 - left_team
	var w: float = size.x
	var block_w: float = (w - 150.0) * 0.5
	var ally_lbl: String = "YOUR TEAM" if left_team == 0 or true else "TEAM A"
	var spectator: bool = bool(m.get("spectator", false))
	var left_col: Color = Settings.relation_color("ally")
	var right_col: Color = Settings.relation_color("enemy")
	_team_block(Rect2(Vector2(0, 0), Vector2(block_w, 56)), int(scores[left_team]), left_col, false, "TEAM A" if spectator else ally_lbl)
	_team_block(Rect2(Vector2(w - block_w, 0), Vector2(block_w, 56)), int(scores[right_team]), right_col, true, "TEAM B" if spectator else "ENEMY")
	# clock
	var clock_rect := Rect2(Vector2(block_w + 4, 0), Vector2(w - block_w * 2.0 - 8, 56))
	draw_rect(clock_rect, Color(0.03, 0.035, 0.04, 0.9))
	var f: Font = HudStyle.num_font()
	var sd: bool = bool(m.get("sd", false))
	var txt: String
	if bool(m.get("training", false)):
		txt = "TRAINING"
	elif sd:
		txt = "SUDDEN DEATH"
	else:
		txt = HudStyle.fmt_time(regulation_s - float(m.get("tick", 0)) / WR.TICK_RATE)
	var fs: int = 34 if not sd and not bool(m.get("training", false)) else 20
	var tw: Vector2 = f.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
	var tcol: Color = Color(1.0, 0.5, 0.35) if sd and fmod(_pulse, 1.0) < 0.5 else HudStyle.INK
	draw_string(f, Vector2(clock_rect.get_center().x - tw.x * 0.5, clock_rect.position.y + 30 + fs * 0.3), txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, tcol)
	if bool(m.get("training", false)):
		return
	# zone line
	var zone: String = String(m.get("zone", ""))
	var st: int = int(m.get("state", WR.ZoneState.NEUTRAL))
	var ctrl: int = int(m.get("ctrl", -1))
	var zcol: Color = Settings.relation_color("neutral")
	var zword: String = "NEUTRAL"
	match st:
		WR.ZoneState.CONTROLLED:
			var rel: String = "ally" if ctrl == left_team else "enemy"
			zcol = Settings.relation_color(rel)
			zword = ("ALLY CONTROL" if rel == "ally" else "ENEMY CONTROL") if not spectator else ("TEAM A CONTROL" if ctrl == 0 else "TEAM B CONTROL")
		WR.ZoneState.CONTESTED:
			zcol = Settings.relation_color("contested")
			zword = "CONTESTED"
	var line_y: float = 62.0
	var zr := Rect2(Vector2(w * 0.5 - 170, line_y), Vector2(340, 30))
	draw_rect(zr, Color(0.05, 0.06, 0.07, 0.8))
	var zc := Vector2(zr.position.x + 18, zr.position.y + 15)
	# zone state glyph: circle (neutral), filled circle (controlled), split circle (contested)
	match st:
		WR.ZoneState.CONTROLLED:
			draw_circle(zc, 8, zcol)
		WR.ZoneState.CONTESTED:
			draw_arc(zc, 8, 0, TAU, 24, zcol, 2.5, true)
			draw_line(zc - Vector2(6, -6), zc + Vector2(6, -6), zcol, 2.5)
			draw_line(zc - Vector2(6, 6), zc + Vector2(6, 6), zcol, 2.5)
		_:
			draw_arc(zc, 8, 0, TAU, 24, zcol, 2.5, true)
	var hf: Font = HudStyle.head_font()
	var zname: String = "%s · %s" % [zone, String(zone_names.get(zone, "")).to_upper()] if zone != "" else "—"
	draw_string(hf, Vector2(zr.position.x + 34, zr.position.y + 22), zname, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, HudStyle.INK)
	var bf: Font = HudStyle.body_font()
	var ww: Vector2 = bf.get_string_size(zword, HORIZONTAL_ALIGNMENT_LEFT, -1, 13)
	draw_string(bf, Vector2(zr.end.x - ww.x - 10, zr.position.y + 20), zword, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, zcol.lerp(Color.WHITE, 0.25))
	# rotation / next zone
	if not sd:
		var rot_s: float = float(m.get("rot", 0)) / WR.TICK_RATE
		var nxt: String = String(m.get("next", ""))
		var rtxt: String = ("NEXT: %s · %s in %s" % [nxt, String(zone_names.get(nxt, "")).to_upper(), HudStyle.fmt_time(rot_s)]) if nxt != "" else ("Zone shifts in %s" % HudStyle.fmt_time(rot_s))
		var rw: Vector2 = bf.get_string_size(rtxt, HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		var rcol: Color = Settings.relation_color("neutral") if nxt != "" else HudStyle.INK_DIM
		draw_string_outline(bf, Vector2(w * 0.5 - rw.x * 0.5, line_y + 50), rtxt, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, 5, Color(0, 0, 0, 0.85))
		draw_string(bf, Vector2(w * 0.5 - rw.x * 0.5, line_y + 50), rtxt, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, rcol)
