# Controls

Every gameplay action can be rebound in **Settings → Controls** (keyboard/mouse and gamepad
separately; conflicts offer a swap). Sensitivity, invert-Y and stick deadzones are there too.

## Default bindings
| Action | Keyboard & mouse | Gamepad (Xbox / PlayStation) |
|---|---|---|
| Move | W A S D | Left stick |
| Camera | Mouse | Right stick |
| Light attack (combo up to 3) | Left mouse | X / □ |
| Heavy attack | Right mouse | Y / △ |
| Skill Q | Q | LB / L1 |
| Skill E | E | RB / R1 |
| Skill R | R | RT / R2 |
| Guard (hold) | F | LT / L2 |
| Dodge | Shift | B / ○ |
| Jump | Space | A / ✕ |
| Ping (tap = contextual, hold = wheel) | Middle mouse | D-pad ↑ |
| Quick chat "On my way" / "Need help" | — | D-pad ← / → |
| Scoreboard (hold) | Tab | View |
| Text chat (online) | Enter | — |
| Menu / pause | Esc | Menu |

While knocked out, Light/Heavy attack cycle the ally you spectate.
Training: F1 idle · F2 guard · F3 attack · F4 dodge dummies · F5 reset.
Replays: Space play/pause · ←/→ seek 5 s · F free camera (hold right mouse to look) · Tab follow next.

## Combat basics
* **Stamina** (yellow bar) pays for dodges (25), heavies (15) and blocked hits. It regenerates
  after 0.9 s without spending; holding guard pauses regeneration.
* **Guard** blocks strikes from the front 120°; a guard at 0 stamina breaks (long stagger).
* **Dodge** has invulnerability during its first 0.2 s; repeated control effects on you build
  **Resist** (shown on the HUD), which shortens further stuns.
* Score by being the **only team** inside the active zone (1 point/s). Zones shift B → A → C
  every 60 s; the next zone is revealed 15 s early. First to 250 or the higher score after
  8 minutes wins; a tie goes to sudden death.

## Fighters
| Fighter | Passive | Q | E | R |
|---|---|---|---|---|
| Nyx (cat, duelist) | Perch — climb marked ledges | Pounce | Crosscut | Slip (+ counter) |
| Bruno (dog, frontline) | Grounded — resists displacement | Shoulder Rush | Warning Bark | Stand Firm |
| Vex (fox, trickster) | Light Steps — faster strafing | False Start | Sidewinder | Tail Sweep |
| Hops (rabbit, skirmisher) | Lightfoot — no landing slowdown | Bound | Double Kick | Dropkick |
| Scrap (raccoon, counter-fighter) | Quick Recovery — shorter stuns | Catch & Turn | Leg Sweep | Turnabout |

Full numbers per skill: `game/data/tuning/fighters/<id>.json`; in game: Collection and the
character-select kit panel.
