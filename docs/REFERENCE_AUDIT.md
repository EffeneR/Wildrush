# Reference Audit

Every one of the 16 references was opened and inspected visually (not only by file
name). Priority: written spec > character sheets > environment references > schematic
map styling > incidental text in generated images. This document records what is
used, what is ignored, and how each conflict is resolved.

## A. Mandatory conflict resolutions (spec §2)

| # | Conflict (where seen) | Resolution in WILDRUSH |
|---|------------------------|------------------------|
| A1 | Weapons/shooting/shields: HUD ref shows a cannon-like prop at left; combat ref "Guard (Block)" shows a glowing **energy shield disc**; Bruno "Stand Firm" art implies a barrier. | No guns, ammo, weapon inventory, or shields of any kind. Guard is a forearm block: brief contact-deflection spark **at the forearms** (VFX `guard_deflect`). Stand Firm is a planted stance with a wider guard arc — no shield mesh, no persistent energy effect. Decorative cannon props are not placed. |
| A2 | Numbered rounds: HUD ref "ROUND 1". | One continuous Turf Shift match (480 s regulation + sudden death). No round counter exists anywhere in UI or data. |
| A3 | Multiple simultaneous objectives: map legends show A/B/C together; HUD shows three diamonds. | Exactly one active territory at a time (rotation B→A→C). The A/B/C widget shows inactive zones in grey; only the active zone has scoring presentation (floor ring, beam, HUD status). |
| A4 | Slow motion/shake/blur: combat ref lists "Slow motion (brief)" for parry, "Stronger screen shake" for heavy, "Motion blur" for knockback. | No global time-scale changes, ever. Camera shake optional, default **off**. No motion blur. Hit-stop is cosmetic only (render-side pose hold ≤ 50 ms, never alters sim/input timing) and disabled under Reduced Effects. |
| A5 | Universal parry: combat ref panel 5 "Parry — perfectly timed block" presented as generic. | Parry exists only as Scrap's Q "Catch & Turn". Other fighters have guard only. The combat-reference parry flash styling is used for Scrap's parry VFX. |
| A6 | Camera reference collage (#12) shows a **different arena layout** (north/south spawns, ring roads, domed pavilion) plus aerial and three environment thumbnails. | Only the bottom-right in-game camera panel is used (framing: behind/above, full body, readable melee spacing). The collage's map is not built and is not a separate map. Its sample score "240 / 12:14 / 180" is ignored. |
| A7 | Asymmetric spawns: maps #7/#8 put Blue spawn far west (next to A) and Red spawn far east (next to C). | Spawns moved to mirrored north/south plazas at (0,0,−48) and (0,0,+48) with two separated exits each (D-007, spec §7). Canal Court stays west (A ≈ (−42,0,0)), Market Square centre (B ≈ (0,0,0)), Loading Yard east (C ≈ (42,0,0)). Travel-time fairness is measured (`evidence/arena/travel_times.json`). The references' 50 m scale bar is not treated as proof of any distance. |
| A8 | Water: "Open water. Open fights." (#7); canals everywhere. | Water is scenery outside fighting surfaces. Canal edges have balustrades/low walls; the few open quay edges drop onto a shallow **walkable** canal-side ledge with stairs back up — no swimming, no ring-outs, no lethal water. Puddles are cosmetic (surface-aware footstep sound only). |
| A9 | Decorative text as rules: captions ("Capture progress starts when a team is inside", "Stay in the zone", sample scores 2–1, cooldown rings, invented logos, slogans on banners, "3" level badge, 250/250 HP for Nyx). | Not rules. No capture-progress bar exists (control is immediate, D-006). HP values come from the spec (Nyx 220). Cooldown display is our own radial + numeric timer. Banner slogans are set dressing only. Player level badges are not shown. |

## B. Additional conflicts found during inspection

| # | Observation | Resolution |
|---|-------------|------------|
| B1 | Nyx sheet "Slip — 1. Evade: *Disappear*". | No invisibility/teleport: Slip is a visible lateral evade with a brief optional counter-swipe window. |
| B2 | Character-select roles "Assassin / Brawler / Skirmisher / Mobility / Support". | Spec roles used: Nyx agile duelist, Bruno frontline bruiser, Vex deceptive counterfighter, Hops mobile striker, Scrap technical disruptor. |
| B3 | Character-select "PLAY PREVIEW" video panel. | Replaced by a real in-engine skill demonstration: the animated 3D preview plays the selected skill clip on demand. No fake video. |
| B4 | Combat ref "Elimination feedback" uses a **skull** icon and greyscale body. | Non-graphic KO: a stylised "KO" star-burst badge, fighter collapses/sits and fades; no skull, no gore. |
| B5 | Combat ref "Status icons" shows "Stunned" with orbiting stars. | Status icons exist for real effects only (Guard Broken, Knocked Down, Control Resist, Spawn Protected, Stand Firm, Grabbed). |
| B6 | HUD ref shows health "250/250" and a separate blue bar "120/120". | Health (per spec) + stamina (100). No mana/energy/ultimate meter. |
| B7 | Logo: the dog head resembles a wolf. | Brand lockup retained unchanged as supplied; the in-game Bruno model is unmistakably a dog (folded ears, rounded skull, fawn coat). |
| B8 | Vex back view shows copper on both shoulder areas. | Spec wins: copper panel on Vex's **anatomical right** shoulder only. |
| B9 | Hops sheet: cropped top exposing abdomen, very short shorts. | Nonsexualised sporting look: full-coverage charcoal athletic top reaching the waistband, mid-thigh shorts, mint waistband. |
| B10 | Nyx sheet: cropped jacket over bare midriff. | Charcoal fitted under-top covers the torso; jacket stays cropped; no exaggerated features. |
| B11 | Bruno/Scrap knee pads look like hard armour. | Soft padded knee (Bruno) and elbow/knee (Scrap) pads — fabric material, no armour plates. |
| B12 | HUD ref text chat names use each animal's clothing color. | Chat/markers use team relationship colours (ally blue / enemy red), not clothing colours. |
| B13 | HUD ref minimap shows enemy icons. | Minimap shows enemies only when legitimately observed/heard by the team or pinged (server-filtered, D-013). |
| B14 | Territory ref "Capture progress is paused" / progress bars. | No capture progress. Contested = scoring paused; UI shows a crossed-claws icon with diagonal stripe pattern (colour-blind safe) + "CONTESTED" label. |
| B15 | Scrap skill illustrations use grey mannequin opponents. | Illustration device only; Turnabout/Leg Sweep work on any fighter. |
| B16 | Bruno "Warning Bark" art shows large concentric blue sonic rings. | Short (5 m), 60° cone, restrained VFX: a few thin arcs that fade within 0.25 s; no giant rings, no screen-covering effect. |
| B17 | Map legend "Short Ledge (jumpable)", "Stairs (up)". | Arena includes explicit short ledges that are Nyx Perch shortcuts; every ledge route also has an ordinary stair/ramp route (spec §7). |
| B18 | Environment refs place the WILDRUSH logo on banners and walls. | Banners use the claw-mark emblem + neutral slogans as set dressing; the logo is not a gameplay element. |

## C. What each reference is used for (summary)
See `docs/REFERENCE_MANIFEST.md` for per-image intended uses. Character sheets drive
silhouette, proportions, colour palettes and skill poses; environment refs drive kit
pieces, materials, props and lighting; UI refs drive layout hierarchy and colour
language only — no reference image is pasted into the game as a screenshot/backdrop.
