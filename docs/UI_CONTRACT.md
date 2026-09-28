# UI Contract (menus, screens, online client)

Owner of this contract: integration lead. The match presentation (arena visuals, fighter
views, camera, HUD, pause overlay, VFX, replay viewer, spectator view) is owned by the
integration lead in `game/src/present/` and `scenes/match.tscn`. Everything else a player
navigates — the screens below — lives in `game/src/ui/` and `game/scenes/` and must follow
this contract so the pieces meet.

## Global rules
* Godot 4.7.2, **typed GDScript only**, no .NET, no editor-only features at runtime. The project
  warns on untyped declarations, so type everything.
* Every screen works with **mouse, keyboard and gamepad**: set a sensible initial focus
  (`grab_focus()` on the primary action), explicit `focus_neighbor_*` where automatic
  neighbours fail, `ui_cancel` (Esc / B / Circle) goes back, and nothing requires a mouse.
* Layout must hold at 1280×720, 1600×900, 1920×1080, 2560×1440 and ultrawide 3440×1440
  (anchors/containers, no absolute pixel positions for content). `Settings` display/ui_scale
  and access/hud_scale are applied globally/HUD-side; don't fight them.
* Visual language: dark, restrained esports look. Theme: `res://assets/ui/wildrush_theme.tres`
  (extend it rather than overriding per-node where possible). Colour is always paired with
  a shape, icon or label (colour-vision support); use `Settings.relation_color(relation)` for
  ally/enemy/neutral/contested/inactive colours, never hard-coded team colours.
* Sounds: `AudioDirector.ui("ui_hover" | "ui_select" | "ui_back" | "ui_error" | "ui_lockin" |
  "ui_ready" | "ui_match_found" | "ui_notify" | "ui_chat" | "ui_ping")`; music:
  `AudioDirector.music("music_menu" | "music_select" | "music_results")`.
* Text: no placeholder copy ("Lorem", "TODO", "Coming soon") in shipped screens. Disabled
  features must not appear as buttons.
* All player-facing text comes from real data: fighter names/titles/taglines/skills from
  `Tuning.fighter(id)` (`FighterDef`: `display_name`, `species`, `title`, `role`, `tagline`,
  `quote`, `passive_name`, `passive_desc`, `skill(slot)` → `ActionDef` with `display_name`,
  `desc`, `cooldown_s`, `stamina`), palettes from `FighterDef.palettes`.

## Scene flow (autoload `Game`, `game/src/core/game_flow.gd`)
| Constant | Scene | Owner |
|---|---|---|
| `SCENE_SPLASH` | `res://scenes/splash.tscn` — logo sting, then main menu (skippable) | UI |
| `SCENE_MENU` | `res://scenes/main_menu.tscn` — hub with sub-screens (below) | UI |
| `SCENE_MATCH` | `res://scenes/match.tscn` — offline, training, online, replay (by `mode`) | lead |
| `SCENE_RESULTS` | `res://scenes/results.tscn` — reads `Game.last_result` | UI |
| `SCENE_ONLINE_LOBBY` | `res://scenes/online_lobby.tscn` — private lobby + character select bound to `Game.session` | UI |

Navigate only with `Game.goto(scene, params)` / `Game.goto_menu(params)`; params arrive in
`Game.pending`. `Game.goto_menu({"screen": "history"})` opens a main-menu sub-screen directly.

### Match params (`Game.pending` for `SCENE_MATCH`)
```
{"mode": "offline" | "training" | "online" | "replay",
 "fighter": "nyx", "palette": "default",            # offline/training: the local player's pick
 "difficulty": "easy" | "normal" | "hard",          # bots (offline)
 "allies": ["bruno","vex","hops","scrap"],          # optional; 4 ids, duplicates allowed across teams only
 "enemies": ["nyx","bruno","vex","hops","scrap"],   # optional; 5 ids
 "seed": 1234,                                       # optional
 "training": {"dummy_behaviour": "idle"|"guard"|"attack"|"dodge", "dummies": 3},  # training only
 "replay_path": "user://replays/<file>.wrr"}         # replay only
```
Online matches take everything from `Game.session` (`mode: "online"`).

### Results (`Game.last_result`)
```
{"result": {"match_id", "mode", "winner_team", "score": [a, b], "duration_s", "sudden_death",
            "ended_reason", "players": [row], "bots": [row], "seed", "build"},
 "my_entity": 3, "my_team": 0, "mode": "offline", "fighter": "vex",
 "awards": {"xp": 240, "level_before": 2, "level_after": 3, "unlocked": ["dusk"]},   # offline: Profile.award_offline_match
 "replay_path": "user://replays/....wrr"}
row = {"entity", "team", "fighter", "name", "account_id", "kos", "knocked_out", "damage_dealt",
       "control_seconds", "abandoned", "afk", "bot"}
```
Results screen: winner banner (victory/defeat from `my_team`), score, duration, sudden-death
flag, per-team table (fighter, name, KOs, KO'd, damage, control seconds, bot/afk/abandoned
tags), mastery progress bar + unlocks, buttons: *Play again* (same params, offline),
*Watch replay* (if `replay_path`), *Main menu*. For online private matches: *Back to lobby*
(if `Game.session` is still connected) — the server returns to its lobby automatically.

## Main menu sub-screens (inside `main_menu.tscn`, switched without scene changes)
1. **Home**: Play Offline, Training, Play Online, Collection, History & Replays, Settings,
   Credits, Quit (with confirmation). Shows local profile name + selected badge, build id.
2. **Offline setup**: fighter select (5 cards with 3D preview), palette (only unlocked, via
   `Profile.unlocked_palettes(fid)`), bot difficulty, ally/enemy composition (auto-fill or
   choose), Start → `SCENE_MATCH`.
3. **Training setup**: fighter + palette + dummy behaviour/count → `SCENE_MATCH` mode training.
4. **Online**: account panel (register / login / logout, HTTPS enforcement message), party
   panel (create, invite by username, accept/decline invites, leave, members), queue panel
   (casual / ranked, party size rules, queue timer, cancel, *match found* → accept), private
   match (create via service or **direct connect** host:port + optional password), server
   browser (from `GET /v1/servers` when available). When a ticket/assignment arrives:
   `Game.start_online_session(host, port, {"name": display_name, "ticket": ticket})` then
   `Game.goto(SCENE_ONLINE_LOBBY)`.
5. **Collection**: per fighter: mastery level/XP bar (`Profile.fighter_level/fighter_xp`, and the
   online profile when logged in), palettes (locked ones shown locked with their unlock level),
   badges, selected palette/badge (persisted via `Profile.select_palette/select_badge`), lore
   text (title, tagline, quote, passive + three skills with descriptions).
6. **History & Replays**: offline history from `Profile.data["history"]`; online history
   (`GET /v1/history`) when logged in; replay files in `user://replays/` (list, size, date,
   play → `Game.goto(Game.SCENE_MATCH, {"mode": "replay", "replay_path": p})`, delete with
   confirmation).
7. **Settings**: a reusable `res://scenes/ui/settings_panel.tscn` (root script
   `SettingsPanel`, emits `closed`), tabs: Display (window mode, resolution, vsync, frame cap,
   render scale, quality preset, brightness, FOV), Audio (5 buses), Controls (mouse/pad
   sensitivity, invert Y, deadzones, **full rebinding** for KB/M and pad using
   `Settings.rebind()` with conflict prompt → swap or cancel, reset to defaults),
   Accessibility (colour mode with live swatch preview, reduced effects, camera shake,
   HUD scale, damage numbers), Gameplay/Online (player name, service URL with HTTPS check).
   The match scene instances this panel inside its pause overlay, so it must work as an
   overlay on top of a running 3D scene and must not change scenes itself.
8. **Credits**: team/tools/licences from `docs/LICENSE_MANIFEST.md` content (Godot MIT,
   Blender GPL tooling note, fonts' licences if any are added), original-asset statement.

## Online lobby (`online_lobby.tscn`, bound to `Game.session: ClientSession`)
Signals: `status_changed(status, detail)`, `welcomed(info)`, `lobby_updated(lobby)`,
`match_setup_received(info)`, `chat_received(msg)`, `server_notice(msg)`, `results_received(r)`.
Lobby payload: `{"t": "lobby", "stage": 0 LOBBY | 1 SELECT | 2 MATCH | 3 RESULTS | 4 CLOSING,
"roster": {"teams": [[{"pid","name","slot","fighter","locked","ready","bot","connected"}], [...]],
"swaps": [[from_pid, to_pid]], "allow_bots", "bot_difficulty"}, "admin": pid, "mode",
"select_left_s", "observers_allowed", "expected"}`; me = `session.info["pid"]`.
Requests via `session.request(d)`: `{"t":"pick","f":id}`, `{"t":"lock"}`,
`{"t":"swap_req","slot":i}`, `{"t":"swap_answer","from":pid,"accept":bool}`,
`{"t":"ready","v":bool}`, `{"t":"chat","text":s,"team":bool}`, `{"t":"rematch","v":bool}`,
admin: `{"t":"admin","cmd":"set_team"|"kick"|"bots"|"observers"|"start"|"return_lobby","args":{...}}`
(`set_team {pid, team}`, `kick {pid}`, `bots {enabled, difficulty}`, `observers {allowed}`,
`start {force}`). Errors arrive as `server_notice({"t":"error","for":t,"code":c})` — show
them in a toast. Stage SELECT = character select with timer; duplicates are allowed across
teams, not within a team (`taken` error). On `match_setup_received` →
`Game.goto(Game.SCENE_MATCH, {"mode": "online"})`. Leaving → `Game.end_online_session()`.

## Online client (autoload `Online`, `game/src/online/online_client.gd`)
HTTP client for `docs/API_CONTRACT.md` (+ deviations in `services/CONTRACT_NOTES.md`).
* Base URL from `Settings.get_value("online", "service_url")`; **refuse non-HTTPS** unless the host
  is `127.0.0.1`, `localhost` or `::1` (return an error the UI shows).
* Bearer token kept in memory; never written to disk unless the player ticks "remember me"
  (then `user://session.cfg`, token only, never the password).
* Async API with signals or `await`: `register`, `login`, `logout`, `me`, `profile_get/patch`,
  `party_create/current/invite/invites/accept/decline/leave/kick`, `queue_join/status/leave/accept`,
  `ticket_get`, `private_create/join`, `servers_list`, `history`. Every call returns
  `{"ok": bool, "status": int, "data": Variant, "error": {"code","message"}}`.
* Poll queue/party status at ≤1 Hz while visible; respect 429 `Retry-After`.

## Fighter previews (owned by lead, `game/src/present/fighter_view.gd`)
`FighterView.create_preview(fighter_id: String, palette: String) -> FighterView` returns a
Node3D (model or procedural stand-in until GLBs land) with `play_clip(name)` (`"idle"`,
`"select"`, `"victory"`, `"run"`) and `set_palette(palette)`. Put it in a `SubViewport` with
its own `World3D`, a `Camera3D`, a key/rim light and a floor disc for the select screens.
Portrait textures: `res://assets/ui/portraits/<id>.png` (rendered from the final models; if a
file is missing, fall back to a runtime SubViewport capture of the preview).

## Verification (gate G11)
`game/tools/ui_screenshots.gd` (+ `.tscn`): opens every screen/sub-screen (and key states:
rebinding prompt, conflict prompt, lobby with 10 players, results victory/defeat, online
errors) at 1280×720, 1920×1080 and 3440×1440, saves PNGs to `evidence/ui/`, and fails on any
engine error or on Controls clipped outside the viewport. Run under Xvfb with lavapipe:
`xvfb-run -s "-screen 0 3440x1440x24" $GODOT_BIN --path game res://tools/ui_screenshots.tscn`.
