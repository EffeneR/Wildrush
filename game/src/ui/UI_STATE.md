# UI workstream state (screens + online client)

Owner: UI/screens engineer. Binding spec: `docs/UI_CONTRACT.md`. Lead owns match presentation
(`game/src/present/`, `scenes/match.tscn`). This file survives interruption: update after
each milestone (what exists, what is verified, next step).

## File map
| Deliverable | Path | Status |
|---|---|---|
| UI kit (palette, fonts, factories, focus, sounds, formatting) | `src/ui/ui_kit.gd`, `src/ui/ui_state.gd` | written |
| Widgets | `src/ui/widgets/*` (UiIcon, FighterEmblem, FighterPreview(+Stage), PortraitCache, FighterCard, PaletteButton, KitList, UiModal, UiToasts, UiCycler, UiTabs, UiHintBar, MaxWidthContainer, MenuBackground, WordmarkLogo, SwatchPreview) | written |
| Theme (generated) | `src/ui/ui_theme_builder.gd` + `tools/build_ui_theme.gd` → `assets/ui/wildrush_theme.tres` | built (30 variations) |
| Fonts | `assets/ui/fonts/` Barlow/Barlow Condensed (OFL) + DejaVu Sans fallback; `SOURCES.md` has URLs + SHA-256 | added |
| Splash | `scenes/splash.tscn`, `src/ui/splash.gd` | written |
| Main menu + sub-screens | `scenes/main_menu.tscn`, `src/ui/main_menu.gd`, `src/ui/menu/*` (home, offline, training, online, collection, history, credits) | written |
| Settings overlay | `scenes/ui/settings_panel.tscn`, `src/ui/settings_panel.gd` | written |
| Results | `scenes/results.tscn`, `src/ui/results_screen.gd` | written |
| Online lobby | `scenes/online_lobby.tscn`, `src/ui/online_lobby.gd` | written |
| Online autoload | `src/online/online_client.gd` | written |
| Credits/licence source | `data/credits.json` | written |
| Screenshot tool | `tools/ui_screenshots.gd/.tscn` → `evidence/ui/` | NOT STARTED |

## Verified (commands + results)
- Baseline before UI work: `$GODOT_BIN --headless --fixed-fps 60 --path game res://tests/test_runner.tscn` → 73 passed.
- Theme build: `$GODOT_BIN --headless --path game --script res://tools/build_ui_theme.gd` → wrote theme.

## Next step
Parse check of all new scripts, headless smoke run of each scene, then screenshot tool.
