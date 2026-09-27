# Reference Manifest

Source: user upload `game_references.zip` (16 PNG files), extracted unmodified to
`references/`. The images are private inputs and are **git-ignored** (not uploaded);
this manifest records paths, sizes and SHA-256 so a later session can verify it is using
the same files. If `references/` is empty in a fresh checkout, re-extract the archive
there (file names contain `#U2014`, the zip's encoding of an em dash).

| # | Reference | Path | Size (px) | SHA-256 (prefix) | Intended use |
|---|-----------|------|-----------|------------------|--------------|
| 1 | Game logo | `references/game logo.png` | 1086×815 | `97e266a698c3de78` | Brand lockup: WILDRUSH wordmark with claw slash, five heads, tagline "FIVE ANIMALS. ONE PACK."; source of in-game logo cut-out (D-017); menu/loading palette (charcoal, bone white, crimson, amber). |
| 2 | NYX — The Cat | `references/NYX #U2014 The Cat.png` | 768×1152 | `fd4a28fbdaa8023d` | Anatomy, face, tabby pattern, cropped charcoal/crimson jacket, red scarf & sash, cargo trousers, wrist wraps, feet, long striped tail; skill poses Pounce/Crosscut/Slip; crown emblem. |
| 3 | BRUNO — The Dog | `references/BRUNO #U2014 The Dog.png` | 917×965 | `88185bef56e5df19` | Fawn dog anatomy, folded ears, cream muzzle; navy/black hooded sleeveless vest with cobalt panels, charcoal cargo shorts, blue wraps, knee pads, short curled tail; Shoulder Rush/Warning Bark/Stand Firm poses; dog emblem. |
| 4 | VEX — The Fox | `references/VEX #U2014 The Fox.png` | 917×965 | `5e6d4549c8158d0c` | Rust fox anatomy, cream cheeks, dark lower limbs; dark-plum cropped jacket with copper shoulder panel, charcoal trousers, fingerless gloves, big white-tipped tail; False Start/Sidewinder/Tail Sweep poses; fox emblem. |
| 5 | HOPS — The Rabbit | `references/HOPS #U2014 The Rabbit.png` | 917×965 | `5d32c985fae0926c` | Off-white rabbit anatomy, long ears, long feet; teal cropped hooded jacket, charcoal athletic top/shorts, mint waistband, ankle wraps, small tail; Bound/Double Kick/Dropkick poses; rabbit emblem. |
| 6 | SCRAP — The Raccoon | `references/SCRAP #U2014 The Raccoon.png` | 815×1086 | `83ef35691ba449db` | Grey raccoon anatomy, mask, rounded ears; slate hooded sleeveless vest with amber straps, cropped cargo trousers, knee/elbow pads, wrist wraps, ringed tail; Catch & Turn/Leg Sweep/Turnabout poses; raccoon emblem. |
| 7 | Arena top-down map | `references/Arena top-down map.png` | 1086×815 | `8e603d79d0616ce0` | District composition: Canal Court (west, canals/bridges/boats), Market Square (centre, fountain, stalls, trees), Loading Yard (east, cranes, crates, containers); route/flank/chokepoint language; legend styling for the in-game minimap. |
| 8 | Arena aerial 3D overview | `references/Arena aerial 3D overview.png` | 1086×815 | `c865d814b4e6a65a` | Massing and materials: terracotta roofs, brick/stone quay walls, arches over water, lamp posts, trees; warm evening/daylight mood; outer city backdrop. |
| 9 | Canal Court gameplay environment | `references/Canal Court gameplay environment.png` | 1254×706 | `1cf8810b6f08c6ec` | Stone deck with puddles, low walls with ivy, short stairs, brick arches, banner posts, barrels, canal behind balustrade; warm clear daylight. |
| 10 | Market Square gameplay environment | `references/Market Square gameplay environment.png` | 1254×706 | `77a41306bfdce497` | Open plaza, central fountain with lion statues, peripheral red/green canopy stalls, planters with trees, arches ("NORTH ALLEY"/"NORTH PASS"), stairs, banners, lanterns. |
| 11 | Loading Yard gameplay environment | `references/Loading Yard gameplay environment.png` | 1254×706 | `d68fb29b562d7f77` | Industrial paving with drain grates, yellow crane (background), crate stacks with tarps, concrete barriers with logo, ramps/stairs, hazard stripes. |
| 12 | Third-person gameplay camera reference | `references/Third-person gameplay camera reference.png` | 1152×768 | `38175cb2d49ce6c8` | Only the bottom-right panel informs camera framing (behind/above, full body visible, readable melee distance). The collage's alternative map is NOT used (see audit). |
| 13 | Gameplay HUD reference | `references/Gameplay HUD reference.png` | 1152×768 | `77d4a265dec1b3e2` | HUD hierarchy: team portrait rows top, score/clock centre, A/B/C diamonds, zone status + next-zone countdown, minimap top-right, player vitals bottom-left, Q/E/R bottom-centre, dodge/jump bottom-right, chat left. |
| 14 | Character selection screen | `references/Character selection screen.png` | 1152×768 | `8075251c7f1138e1` | Layout: title + timer top-centre, large fighter preview centre, bio/stats left, Q/E/R card right, five fighter cards bottom, enemy slots, Lock In button bottom-right, step indicator. |
| 15 | Territory state reference | `references/Territory state reference.png` | 1152×768 | `b0ffcadd643a96e6` | Five zone states (inactive grey, neutral gold, ally blue, enemy red, contested purple/crossed-swords), floor ring indicators, minimap icons, top-centre A/B/C widget. |
| 16 | Combat feedback / hit effect reference | `references/Combat feedback -  hit effect reference.png` | 1152×768 | `eebc1d96048db3c7` | Readability language for light hit, heavy hit, guard, guard break, parry, knockback, directional hit indicator, low-health vignette, stamina bar, status icon above head, KO feedback. |

Full SHA-256 values: see `evidence/references_sha256.txt`.
