# Audio Production Contract

All audio is **original**, synthesized procedurally by scripts in `tools/audio/` (numpy/
scipy) — no samples from third parties, no human voice impersonation (animal-like
vocal sounds such as Bruno's bark are synthesized). Output lives in `game/assets/audio/`.

## Formats
* SFX: WAV, 44.1 kHz, 16-bit PCM, **mono** (positional), trimmed, 2 ms fade-in, short fade-out, peak ≤ −1 dBFS.
* Ambience & music: OGG Vorbis, 44.1 kHz, stereo, seamless loops (zero-crossing/crossfaded loop point), peak ≤ −1 dBFS.
* Variations are numbered `_01`, `_02` … and must differ audibly (pitch, envelope, noise seed, filter).

## Buses (created by the game: `Master`, `Music`, `SFX`, `UI`, `Ambience`)
Loudness guidance (RMS of the loud part): impacts −14 dBFS, swings −20, footsteps −24,
UI −20, ambience loops −28, music −22. Essential cues (hit, guard, parry, guard break, KO,
zone changes, score warnings) must stay distinguishable in a dense fight: give each a
distinct spectral signature (pitch region / transient shape).

## Cue list (cue id → files)
| Cue | Files | Notes |
|-----|-------|-------|
| foot_stone | `sfx/foot_stone_01..06.wav` | soft paw on stone |
| foot_wood | `sfx/foot_wood_01..06.wav` | hollow plank (bridges, docks) |
| foot_metal | `sfx/foot_metal_01..06.wav` | grate/plate (loading platforms) |
| foot_wet | `sfx/foot_wet_01..06.wav` | puddle splash-step |
| land_stone / land_wood / land_metal / land_wet | `sfx/land_<s>_01..03.wav` | jump landing |
| jump | `sfx/jump_01..03.wav` | push-off + cloth |
| dodge | `sfx/dodge_01..04.wav` | quick body whoosh + cloth flap |
| swing_light | `sfx/swing_light_01..05.wav` | short claw/paw whoosh |
| swing_heavy | `sfx/swing_heavy_01..03.wav` | longer, lower whoosh with wind-up |
| kick_whoosh | `sfx/kick_whoosh_01..04.wav` | leg swing |
| hit_light | `sfx/hit_light_01..05.wav` | short padded thump + small snap (non-graphic) |
| hit_heavy | `sfx/hit_heavy_01..04.wav` | deep thump + crack, compact |
| guard_block | `sfx/guard_block_01..05.wav` | forearm deflect: dull "thock" + short slide (NOT metallic) |
| guard_break | `sfx/guard_break_01..02.wav` | distinct crack + descending tone |
| parry | `sfx/parry_01..02.wav` | precise bright ring/flash (Scrap only) |
| knock_skid | `sfx/knock_skid_01..03.wav` | knockback slide / dust |
| body_fall | `sfx/body_fall_01..03.wav` | knockdown hitting the ground |
| grab | `sfx/grab_01..02.wav` | cloth grab |
| nyx_pounce_leap / nyx_pounce_land | `sfx/nyx_pounce_leap_01..02.wav`, `sfx/nyx_pounce_land_01..02.wav` | |
| nyx_crosscut | `sfx/nyx_crosscut_01..02.wav` | two sharp claw slashes |
| nyx_slip | `sfx/nyx_slip_01..02.wav` | quick sidestep swish |
| bruno_rush_start / bruno_rush_impact | `sfx/bruno_rush_start_01..02.wav`, `sfx/bruno_rush_impact_01..02.wav` | stomp; heavy shoulder impact |
| bruno_bark | `sfx/bruno_bark_01..03.wav` | synthesized dog bark (formant pulse), short and loud |
| bruno_stand_firm | `sfx/bruno_stand_firm_01..02.wav` | planted stomp + cloth tension |
| vex_feint | `sfx/vex_feint_01..02.wav` | wind-up swish that cuts off + tail flick |
| vex_sidewinder | `sfx/vex_sidewinder_01..02.wav` | curving whoosh |
| vex_tail_sweep | `sfx/vex_tail_sweep_01..02.wav` | low circular whoosh |
| hops_bound_takeoff / hops_bound_land | `sfx/hops_bound_takeoff_01..02.wav`, `sfx/hops_bound_land_01..02.wav` | springy launch; soft landing |
| hops_double_kick | `sfx/hops_double_kick_01..02.wav` | two snaps |
| hops_dropkick / hops_dropkick_crash | `sfx/hops_dropkick_01..02.wav`, `sfx/hops_dropkick_crash_01..02.wav` | |
| scrap_parry_stance | `sfx/scrap_parry_stance_01..02.wav` | short ready "tick" |
| scrap_leg_sweep | `sfx/scrap_leg_sweep_01..02.wav` | low sweep |
| scrap_turnabout | `sfx/scrap_turnabout_01..02.wav` | grab + swing |
| knockout | `sfx/knockout_01..02.wav` | soft thud + descending two-note chime (non-graphic) |
| respawn | `sfx/respawn_01.wav` | rising chime |
| spawn_protect_end | `sfx/spawn_protect_end_01.wav` | subtle tick |
| zone_activate | `ui/zone_activate.wav` | clear horn-like tone |
| zone_reveal | `ui/zone_reveal.wav` | soft 2-note chime |
| zone_ally | `ui/zone_ally.wav` | positive sting (ally took sole control) |
| zone_enemy | `ui/zone_enemy.wav` | tense sting (enemy took sole control) |
| zone_contested | `ui/zone_contested.wav` | pulsing alert |
| score_warning_1/2/3 | `ui/score_warning_1..3.wav` | escalating (200/230/245 pts) |
| countdown_tick / countdown_go | `ui/countdown_tick.wav`, `ui/countdown_go.wav` | match start |
| rotation_tick | `ui/rotation_tick.wav` | last 5 s before rotation |
| victory / defeat / sudden_death | `ui/victory.wav`, `ui/defeat.wav`, `ui/sudden_death.wav` | stings (2–4 s) |
| ui_hover / ui_select / ui_back / ui_error / ui_lockin / ui_ready / ui_match_found / ui_notify / ui_chat / ui_ping | `ui/<cue>.wav` | crisp, short |
| amb_harbor | `amb/amb_harbor.ogg` | 60 s loop: water lapping, distant synth gulls, light wind |
| amb_market | `amb/amb_market.ogg` | 60 s loop: fountain trickle, awnings flapping, soft murmur-like texture (no words) |
| amb_yard | `amb/amb_yard.ogg` | 60 s loop: distant clanks, chain creaks, wind |
| music_menu | `music/music_menu.ogg` | 60–90 s loop, restrained, dark esports mood |
| music_select | `music/music_select.ogg` | 30–60 s loop, tension |
| music_match | `music/music_match.ogg` | 90–120 s loop, driving but restrained, leaves room for SFX |
| music_results | `music/music_results.ogg` | 20–30 s |

## Manifest (consumed by `game/src/present/audio_director.gd`)
`game/assets/audio/audio_manifest.json`:
```json
{"cues": {"hit_light": {"files": ["sfx/hit_light_01.wav", "..."], "bus": "SFX", "volume_db": 0.0,
  "pitch_rand": 0.06, "max_voices": 6, "positional": true, "priority": 3, "loop": false}}}
```
`priority` 1–5 (5 = essential; the director steals lower-priority voices first).
