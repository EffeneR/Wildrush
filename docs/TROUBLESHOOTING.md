# Troubleshooting

## Game client
| Symptom | Fix |
|---|---|
| Very low frame rate | Settings → Display: quality **low** or **competitive**, render scale 0.75, frame cap 60. Update GPU drivers (Vulkan 1.3). |
| Game does not start / Vulkan error | The client needs a Vulkan-capable GPU/driver. On Windows update the GPU driver; the Windows build also includes the console wrapper `WILDRUSH.console.exe` which prints the error. |
| Mouse controls the menu during a match | Click inside the game window to capture the mouse again (Esc releases it). |
| Controller not detected | Connect it before launching; check Settings → Controls → gamepad column. |
| Reset all settings | Delete `settings.cfg` in the user data folder (below) or use "Reset" in each settings tab. |

User data folder (settings, offline profile, replays):
* Windows `%APPDATA%\WILDRUSH\`
* Linux `~/.local/share/WILDRUSH/`

## Online
| Symptom | Fix |
|---|---|
| "The service URL must use HTTPS" | Public services must be `https://`. Plain `http://` is only allowed for `127.0.0.1`, `localhost`, `::1` (local testing). |
| Cannot connect to a private/dedicated server | The server's UDP port (default 24610, allocator range per host) must be reachable; open/forward it on the host's firewall/router. See `docs/DEPLOYMENT.md`. |
| "version_mismatch" when joining | Client and server builds differ; update both to the same release. |
| Disconnected mid-match | Rejoin from the Online screen within 90 s (your slot is reserved; ranked matches otherwise count it as abandoned). |
| Ranked queue never pops | Ranked needs exactly 10 humans in the same region; casual can fill with bots if everyone allows it. |

## Hosting
* Dedicated server: `wildrush_server.x86_64 --headless -- --port 24610 --mode private --allow-bots`
  (`--private-password-file`, `--observer-key`, `--autostart N` optional). Logs are JSON lines
  prefixed `[server]` on stdout.
* Control service + allocator: `services/README.md` and `docs/DEPLOYMENT.md`.

## Development
* "Could not find type X" after adding scripts or assets: run `godot --headless --path game --import`
  (rebuilds the class cache and imports new models/textures).
* Tests: `tools/verify.sh` (all gates) or the individual commands listed in `README.md`.
