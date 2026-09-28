extends Node
## Autoload "AudioDirector": manifest-driven cues (docs/AUDIO_CONTRACT.md) with per-cue voice
## limits, a bounded positional/2D voice pool with priority stealing, and crossfaded music and
## ambience. Presentation only — never consulted by the simulation. Disabled on dedicated
## servers and headless test clients.

const MANIFEST_PATH: String = "res://assets/audio/audio_manifest.json"
const AUDIO_ROOT: String = "res://assets/audio/"
const POOL_3D: int = 40
const POOL_2D: int = 16
const MUSIC_DB: float = -3.0
const AMB_DB: float = -4.0

var enabled: bool = true
var cues: Dictionary = {}
var _streams: Dictionary = {}            # file path -> AudioStream
var _pool3d: Array[AudioStreamPlayer3D] = []
var _pool2d: Array[AudioStreamPlayer] = []
var _meta: Dictionary = {}               # player instance id -> {cue, prio, started}
var _rng := RandomNumberGenerator.new()
var _music: Array[AudioStreamPlayer] = []
var _music_idx: int = 0
var _music_track: String = ""
var _amb: Array[AudioStreamPlayer] = []
var _amb_idx: int = 0
var _amb_track: String = ""
var _last_play_ms: Dictionary = {}       # cue -> ms (de-duplicates identical cues in one frame)


func _ready() -> void:
	enabled = not Config.is_server and Config.autopilot == ""
	if not enabled:
		return
	_rng.randomize()
	var f := FileAccess.open(MANIFEST_PATH, FileAccess.READ)
	if f != null:
		var d: Variant = JSON.parse_string(f.get_as_text())
		if typeof(d) == TYPE_DICTIONARY:
			cues = (d as Dictionary).get("cues", {})
	if cues.is_empty():
		push_warning("AudioDirector: manifest missing or empty")
	var holder := Node3D.new()
	holder.name = "Voices3D"
	add_child(holder)
	for i in range(POOL_3D):
		var p := AudioStreamPlayer3D.new()
		p.bus = "SFX"
		p.unit_size = 7.0
		p.max_distance = 60.0
		p.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		p.attenuation_filter_cutoff_hz = 7000.0
		p.attenuation_filter_db = -12.0
		p.panning_strength = 1.0
		holder.add_child(p)
		_pool3d.append(p)
	for i in range(POOL_2D):
		var q := AudioStreamPlayer.new()
		q.bus = "UI"
		add_child(q)
		_pool2d.append(q)
	for i in range(2):
		var m := AudioStreamPlayer.new()
		m.bus = "Music"
		m.volume_db = -60.0
		add_child(m)
		_music.append(m)
		var a := AudioStreamPlayer.new()
		a.bus = "Ambience"
		a.volume_db = -60.0
		add_child(a)
		_amb.append(a)


func has_cue(cue: String) -> bool:
	return cues.has(cue)


func _stream(path: String) -> AudioStream:
	if _streams.has(path):
		return _streams[path]
	var full: String = AUDIO_ROOT + path
	var s: AudioStream = load(full) as AudioStream if ResourceLoader.exists(full) else null
	_streams[path] = s
	return s


func _pick_stream(c: Dictionary) -> AudioStream:
	var files: Array = c.get("files", [])
	if files.is_empty():
		return null
	return _stream(String(files[_rng.randi_range(0, files.size() - 1)]))


func _count_voices(cue: String) -> Array:
	var out: Array = []
	for p in _pool3d:
		if p.playing and String(_meta.get(p.get_instance_id(), {}).get("cue", "")) == cue:
			out.append(p)
	for q in _pool2d:
		if q.playing and String(_meta.get(q.get_instance_id(), {}).get("cue", "")) == cue:
			out.append(q)
	return out


func _acquire(pool: Array, prio: int) -> Node:
	var victim: Node = null
	var worst_prio: int = 1 << 30
	var oldest: int = 1 << 62
	for p in pool:
		if not p.playing:
			return p
		var m: Dictionary = _meta.get(p.get_instance_id(), {})
		var pp: int = int(m.get("prio", 0))
		var started: int = int(m.get("started", 0))
		if pp < worst_prio or (pp == worst_prio and started < oldest):
			worst_prio = pp
			oldest = started
			victim = p
	if victim != null and worst_prio <= prio:
		return victim   # steal a lower (or equal, older) priority voice
	return null


func play(cue: String, volume_offset_db: float = 0.0, pitch_scale: float = 1.0) -> void:
	## Non-positional cue (UI, announcements, the local player's own feedback).
	_play(cue, null, volume_offset_db, pitch_scale)


func ui(cue: String) -> void:
	_play(cue, null, 0.0, 1.0)


func play_at(cue: String, pos: Vector3, volume_offset_db: float = 0.0, pitch_scale: float = 1.0) -> void:
	_play(cue, pos, volume_offset_db, pitch_scale)


func _play(cue: String, pos: Variant, vol: float, pitch: float) -> void:
	if not enabled or not cues.has(cue):
		return
	var c: Dictionary = cues[cue]
	var now: int = Time.get_ticks_msec()
	if pos == null and now - int(_last_play_ms.get(cue, -1000)) < 25:
		return   # identical non-positional cue already started this frame
	_last_play_ms[cue] = now
	var prio: int = int(c.get("priority", 1))
	var live: Array = _count_voices(cue)
	var max_v: int = int(c.get("max_voices", 4))
	var player: Node = null
	if live.size() >= max_v:
		# per-cue limit: restart the oldest voice of this cue
		var oldest_t: int = 1 << 62
		for p in live:
			var st: int = int(_meta.get(p.get_instance_id(), {}).get("started", 0))
			if st < oldest_t:
				oldest_t = st
				player = p
	var positional: bool = pos != null and bool(c.get("positional", true))
	if player == null or (positional != (player is AudioStreamPlayer3D)):
		player = _acquire(_pool3d if positional else _pool2d, prio)
	if player == null:
		return
	var stream: AudioStream = _pick_stream(c)
	if stream == null:
		return
	var pr: float = float(c.get("pitch_rand", 0.0))
	var ps: float = pitch * (1.0 + _rng.randf_range(-pr, pr))
	var vdb: float = float(c.get("volume_db", 0.0)) + vol
	var bus: String = String(c.get("bus", "SFX"))
	if player is AudioStreamPlayer3D:
		var p3 := player as AudioStreamPlayer3D
		p3.stop()
		p3.stream = stream
		p3.bus = bus
		p3.volume_db = vdb
		p3.pitch_scale = ps
		p3.global_position = pos
		p3.play()
	else:
		var p2 := player as AudioStreamPlayer
		p2.stop()
		p2.stream = stream
		p2.bus = bus
		p2.volume_db = vdb
		p2.pitch_scale = ps
		p2.play()
	_meta[player.get_instance_id()] = {"cue": cue, "prio": prio, "started": now}


func stop_all_sfx() -> void:
	for p in _pool3d:
		p.stop()
	for q in _pool2d:
		q.stop()


# ------------------------------------------------------------------------------------------
# music & ambience (looped, crossfaded)
# ------------------------------------------------------------------------------------------
func music(track: String, fade_s: float = 1.2) -> void:
	if not enabled or track == _music_track:
		return
	_music_track = track
	_music_idx = _crossfade(_music, _music_idx, track, MUSIC_DB, fade_s)


func stop_music(fade_s: float = 1.0) -> void:
	_music_track = ""
	_music_idx = _crossfade(_music, _music_idx, "", MUSIC_DB, fade_s)


func ambience(track: String, fade_s: float = 2.0) -> void:
	if not enabled or track == _amb_track:
		return
	_amb_track = track
	_amb_idx = _crossfade(_amb, _amb_idx, track, AMB_DB, fade_s)


func stop_ambience(fade_s: float = 1.5) -> void:
	_amb_track = ""
	_amb_idx = _crossfade(_amb, _amb_idx, "", AMB_DB, fade_s)


func _crossfade(pair: Array[AudioStreamPlayer], idx: int, cue: String, base_db: float, fade_s: float) -> int:
	if pair.is_empty():
		return idx
	var old: AudioStreamPlayer = pair[idx]
	if old.playing:
		var t_out: Tween = create_tween()
		t_out.tween_property(old, "volume_db", -60.0, fade_s)
		t_out.tween_callback(old.stop)
	if cue == "" or not cues.has(cue):
		return idx
	var nidx: int = 1 - idx
	var p: AudioStreamPlayer = pair[nidx]
	var s: AudioStream = _pick_stream(cues[cue])
	if s == null:
		return idx
	if s is AudioStreamOggVorbis:
		(s as AudioStreamOggVorbis).loop = true
	elif s is AudioStreamWAV:
		(s as AudioStreamWAV).loop_mode = AudioStreamWAV.LOOP_FORWARD
	p.stream = s
	p.volume_db = -60.0
	p.play()
	var t_in: Tween = create_tween()
	t_in.tween_property(p, "volume_db", base_db + float(cues[cue].get("volume_db", 0.0)), fade_s)
	return nidx
