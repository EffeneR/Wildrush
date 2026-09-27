# WILDRUSH — Complete Godot + Blender Build Directive (MASTER SPEC)

> Canonical copy of the owner's build directive, preserved verbatim so it survives
> context compaction and session interruption. This file is the highest-priority
> reference (see Reference priority in §2). Implementation decisions that interpret
> it live in `docs/DECISIONS.md`; progress lives in `PROJECT_STATE.md`; acceptance
> status lives in `docs/ACCEPTANCE_MATRIX.md`.

---

You are the implementation lead for WILDRUSH. Build the actual game in this workspace using Godot and Blender. Act as the gameplay engineer, technical artist, animator, multiplayer engineer, UI developer, audio implementer, and QA engineer.

This is an execution request, not a request for a plan, tutorial, scaffold, or proposal. The deliverable is the complete, polished, self-hostable WILDRUSH 1.0 defined below. A prototype, MVP, mock multiplayer system, static menu, or collection of unexecuted generation scripts is not an acceptable final deliverable.

Work through internal stages, but continue from each stage into the next without asking whether to proceed. Make bounded implementation decisions yourself. Preserve the scope. Do not substitute an easier genre or stop after proving the core mechanic.

Never claim a feature, asset, test, export, deployment, or visual review succeeded unless it actually did. If a permission, missing capability, session limit, or inaccessible dependency prevents completion, preserve resumable state and report the exact blocker. Do not silently redefine "complete."

## 1. Workspace, permissions, and toolchain

Inspect the workspace before changing anything. Preserve existing user files and reference images. Work inside the project directory, with generated artifacts in clearly identified subdirectories. Do not overwrite originals, delete unrelated files, disable protections, publish publicly, purchase assets, upload private references, or provision paid infrastructure.

Detect the operating system, GPU, available memory, disk space, Godot, Blender, Python, Git, and available automation tools. Resolve actual executable paths rather than assuming commands are on PATH. Windows is the primary client target; Linux is the dedicated-server deployment target.

Verify installed versions and consult matching official documentation. Choose a stable Godot 4.x release, matching export templates, and a compatible stable Blender release, preferably LTS. Pin the versions actually used in `toolchain.lock.json`. Do not mix unstable documentation with older installed APIs. Prefer the standard Godot build and typed GDScript, without adding a .NET dependency.

Use Blender Python/background execution for reproducible asset creation and export. Use an available Blender integration when it improves the result, but do not make a specific MCP plugin mandatory. Use Godot command-line import, tests, exports, and real rendered inspection. Check command return codes and output files.

Download missing free dependencies only from official sources when existing permissions allow it. Keep dependencies project-local where feasible. Record licenses and checksums where available. For actions outside granted permissions, report the specific requirement; never bypass the restriction.

Keep this complete specification in `docs/MASTER_SPEC.md`. Create a short `CLAUDE.md` pointing to it, plus `PROJECT_STATE.md`, `docs/DECISIONS.md`, and an acceptance matrix. These must survive compaction and session interruption.

## 2. Inspect and use all sixteen references

Find the supplied images under `references/` or the existing user-provided reference directory. Extensions, punctuation, and spaces may vary. Inspect the actual images, not only filenames. Create a manifest with their real paths and intended uses:

1. Game logo.
2. NYX — The Cat.
3. BRUNO — The Dog.
4. VEX — The Fox.
5. HOPS — The Rabbit.
6. SCRAP — The Raccoon.
7. Arena top-down map.
8. Arena aerial 3D overview.
9. Canal Court gameplay environment.
10. Market Square gameplay environment.
11. Loading Yard gameplay environment.
12. Third-person gameplay camera reference.
13. Gameplay HUD reference.
14. Character selection screen.
15. Territory state reference.
16. Combat feedback / hit effect reference.

Use the character sheets for anatomy, clothing, materials, silhouettes, and skill poses. Use the environment images for architecture and atmosphere. Use the interface images for visual hierarchy, not as screenshots pasted over the game.

Reference priority: this written specification > final character sheets > environment references > schematic map styling > incidental text in generated images.

Create `docs/REFERENCE_AUDIT.md`. Resolve these known conflicts explicitly:

* No shooting, ammunition, weapon inventory, physical shields, or guns, regardless of accidental imagery.
* One continuous territory-control match, not numbered tactical rounds.
* Exactly one active territory; no simultaneous three-point domination.
* No global slow motion, heavy mandatory camera shake, or mandatory motion blur.
* Scrap's timed parry is his skill, not an extra universal ability silently assigned to everyone.
* The camera reference includes a collage and alternative map layout. Do not turn the game into that collage or treat it as a separate map.
* Original left-to-right spawn placement gives unequal access to outer objectives. Apply the explicit symmetric-spawn correction in section 7.
* Water is scenery outside fighting surfaces, not an unexplained swimming mechanic or lethal objective.
* Decorative captions, sample scores, cooldown rings, and invented logos are not additional game rules.

Preserve the title WILDRUSH and tagline "Five animals. One pack." Do not redesign the brand or add unrelated characters.

## 3. Complete release scope

Build a desktop third-person, skill-based, unarmed 5v5 animal arena fighter. The player controls an animal directly, not a squad and not a top-down avatar.

The complete release includes five finished playable fighters, fifteen implemented character skills, their five passives, one finished Briarport arena containing three territory areas, polished combat and animation, real online multiplayer, self-hostable services, private matches, casual and ranked queues, parties, competent bots, training, complete menus, settings, match results, persistence, cosmetic mastery rewards, spectator tools, and recorded-match playback.

Each team has exactly one cat, dog, fox, rabbit, and raccoon. Both teams use the same five-character roster. Character slots are server-controlled; simultaneous selections cannot produce duplicates. Players may swap before lock-in but not during a live match.

Training is a supported separate sandbox. Regular matches always use two five-slot teams. Offline and explicitly bot-enabled casual/private play may fill missing slots with clearly labeled bots. Ranked matches require ten human players; never disguise bots as humans.

This release does not include an open world, campaign, extra maps, additional species, mobile/console builds, blockchain, betting, cash prizes, real-money store, battle pass, voice chat, or third-party platform integration. Do not expand into these systems or show fake buttons for them. This defines the complete product boundary, not permission to omit requirements inside it.

## 4. Match rules: Turf Shift

Implement these rules as authoritative data-driven logic with automated tests:

* Two teams of five. Eight-minute regulation. First team to 250 points wins immediately.
* A = Canal Court, B = Market Square, C = Loading Yard.
* Start with B. Rotate B → A → C → B every 60 seconds.
* The upcoming location is revealed 15 seconds before activation. A countdown to rotation remains visible throughout.
* Only the active territory can score. An inactive territory remains physically traversable.
* A team earns one point per second when at least one living, eligible teammate occupies the active ground-level zone and no eligible opponent contests it.
* More teammates never multiply scoring speed. Eliminations do not directly award points.
* Empty active zone = neutral. Both teams present = contested, with scoring paused. Sole occupancy = that team's control. No separate capture-progress mechanic and no unattended persistent ownership.
* Territory occupancy uses a defined floor-relative volume. A fighter on a rooftop or bridge above it cannot capture through geometry. Normal small jumps inside the volume do not create exploitable scoring flicker.
* At eight minutes, the higher score wins. If tied, continue with the current territory until the next uncontested scoring tick. Keep ordinary respawns; freeze further territory rotation during sudden death.
* Knockout is non-graphic. Remove the fighter from occupancy immediately. Respawn after ten seconds at a safe team spawn with restored resources.
* Brief spawn protection ends on offensive action or leaving the protected spawn volume. Enemy entry into the protected spawn is blocked.
* Server clock governs scoring, cooldowns, knockouts, rotation, and victory. Resolve simultaneous events in a documented order. Match completion happens once.

Include reconnect handling, match abandonment rules, AFK handling, rematch, and return-to-lobby flow. Disconnected humans retain a short reconnect reservation. Bot replacement is permitted only where the mode explicitly allows it, never silently in ranked.

## 5. Movement, camera, and shared combat

Use a responsive CharacterBody3D-based controller with a fixed 60 Hz authoritative simulation. Keep visual interpolation separate from simulation. Control acceleration, deceleration, floor snapping, slope limits, step handling, falling, and recovery explicitly.

Default controls, all remappable:
WASD movement; mouse camera and facing; left mouse light attack; right mouse heavy attack; Space jump; Shift directional dodge; F frontal guard; Q/E/R character skills; Tab scoreboard; middle mouse contextual ping; Enter text chat; Escape menu. Do not overload Shift with sprint. Controller support must have a complete equivalent mapping and configurable deadzones.

Camera: behind and slightly above the fighter, full feet visible during ordinary movement, restrained shoulder offset, approximately 4–5 metres follow distance. Start around 75 degrees vertical FOV at 16:9, then verify actual framing and expose a sensible adjustment range. Use collision-aware camera retraction, smoothing without input lag, and protection against viewing through walls. Do not use cinematic angles or forced camera spins. No hard target lock or attack homing after commitment.

Every fighter has directional light attacks, one heavy attack, jump, dodge, guard, three skills, health, and stamina. Ear tips, tails, cosmetic clothing, and decorative fur are not damage targets. No headshot multipliers, random critical hits, or account-level damage bonuses.

Implement explicit states and transitions for locomotion, startup, active frames, recovery, guard, dodge, hit reaction, control effects, knockout, and respawn. Define interruption rules and cancel windows. Buffer input briefly without allowing queued attacks to fire long after intent changed.

Each attack has data for startup, active duration, recovery, stamina, cooldown, movement curve, damage, guard damage, displacement, hit volume, interruption rules, and allowed cancel windows. Windows use simulation time, not render frames.

Starting shared tuning: 100 stamina; dodge costs 25; heavy attack costs 15; stamina regenerates at 24/second after 0.9 seconds without spending, but not while holding guard. Health regenerates at 18/second after six seconds without attacking or receiving damage. Begin around 18 damage per light strike and 38 per heavy strike, then tune against complete skill kits.

Use a limited frontal guard arc, reduced movement while guarding, stamina consumption on blocked hits, and a brief punishable guard break. Guard does not protect the back. Give dodge a short explicitly defined evasion window, not permanent invulnerability.

Generate swept melee volumes during active windows to avoid tunneling. Prevent hits through walls, repeated damage from one strike, and accidental friendly damage. Follow-through may hit multiple opponents only when the attack's volume genuinely intersects them.

A missed committed attack remains punishable. There are no long guaranteed damage chains or instant unavoidable kills. Repeated hard control grants a short, visible control-resistance window, not full damage immunity. Teammates cannot body-block one another into an inescapable trap.

Action movement belongs to the authoritative simulation. Animation illustrates the movement rather than secretly adding independent displacement. Bake reusable local hit-volume trajectories or equivalent explicit curves so headless hit detection does not depend on a rendered skeleton or GPU.

## 6. Fighter identities and all skills

Match the supplied final sheets. Every character needs a distinct face, silhouette, stance, locomotion, attacks, defense, and skill animations. Sharing a skeleton convention is allowed; recoloring the same mesh five times is not.

Initial health / movement speed, adjustable only with documented balance evidence: Nyx 220 / 7.2 m/s; Bruno 280 / 6.6; Vex 220 / 7.0; Hops 230 / 7.6; Scrap 260 / 6.8. Use comparable body heights: Nyx 1.70 m, Bruno 1.77, Vex 1.73, Hops 1.67 excluding ears, Scrap 1.63. These are fictional game proportions.

### Nyx — cat / agile duelist

Lean female grey tabby, amber eyes, pale muzzle, pointed ears, charcoal-and-crimson cropped jacket, short red scarf, dark trousers, wrapped wrists, visible feline feet, long striped tail. No bulky armor or exaggerated sexual features.

Passive Perch: scramble onto designated short ledges, with valid landing checks. These are shortcuts; other animals retain an ordinary route to objectives.

Q Pounce: aimed, committed forward leap with a claw strike. No homing. Wall collision stops it; missing leaves landing recovery.

E Crosscut: two compact diagonal claw strikes. Separate active windows; the second is not guaranteed against a successful defense.

R Slip: short lateral evasion with a brief optional counter-swipe input window. No invisibility or teleportation; timing and direction matter.

### Bruno — dog / frontline bruiser

Compact male fawn dog, cream muzzle and throat, folded ears, strong shoulders and forearms, navy sleeveless vest with cobalt upper-back panel, charcoal shorts, blue wraps, soft knee pads, short tail. Clearly a dog, not a wolf or bear.

Passive Grounded: reduced displacement from light pushes, without immunity to major control.

Q Shoulder Rush: committed shoulder charge with limited steering, short displacement on contact, wall handling, and punishable miss recovery.

E Warning Bark: telegraphed short cone that interrupts eligible exposed actions and gives modest displacement. Respect walls and control resistance; no long stun or ranged damage beam.

R Stand Firm: planted defensive stance with stronger frontal protection and reduced movement. Cannot attack freely during it. No physical or persistent energy shield.

### Vex — fox / deceptive counterfighter

Lean male rust-orange fox, cream cheeks, dark lower limbs, amber eyes, narrow muzzle, dark-plum cropped jacket, copper panel on his anatomical right shoulder, charcoal trousers, large white-tipped tail. No scarf.

Passive Light Steps: slightly better strafing speed without faster attack timelines.

Q False Start: convincing attack preparation that cancels into a chosen sidestep. The feint deals no damage; any brief afterimage is cosmetic.

E Sidewinder: player-directed curved approach ending in a strike. No automatic move behind the target and no passing through walls or opponents.

R Tail Sweep: low rotational sweep with modest damage and short displacement. Readable preparation; not a giant spinning area attack.

### Hops — rabbit / mobile striker

Athletic female off-white rabbit, subtle grey markings, long consistent ears, teal jacket, charcoal athletic top and shorts, mint waistband, powerful thighs, elongated rabbit feet, ankle wraps, small visible tail. Nonsexualized sporting appearance.

Passive Lightfoot: better momentum retention after ordinary landings, without removing committed attack recovery.

Q Bound: powerful directional leap with bounded air control and a readable landing. No automatic damage or invulnerability.

E Double Kick: two timed close-range kicks with separate contacts and clear hip motion. Accurate spacing matters.

R Dropkick: committed forward aerial kick that displaces on contact and has substantial miss recovery. Define grounded activation and prevent infinite chained air movement.

### Scrap — raccoon / technical disruptor

Compact male grey raccoon, rounded ears, dark face mask, strong forearms, slate sleeveless vest with muted amber accents, cropped trousers, wrist wraps, soft elbow pads, thick ringed tail. No gadgets or engineering equipment.

Passive Quick Recovery: slightly faster return to stance after ordinary displacement; no immunity to damage or major knockdowns.

Q Catch & Turn: narrow timed parry against eligible melee strikes, redirecting the attacker slightly. Failure leaves exposure. This is Scrap's specific counter, not a universal perfect block.

E Leg Sweep: short-range low attack producing a brief knockdown when not properly defended. Recovery and control resistance prevent repeated lockdown.

R Turnabout: brief contact grapple that repositions and immediately releases an opponent. Nearby attacks can interrupt it; validate free landing space and never pull through a wall.

Assign explicit tuned values to every passive and skill in data resources. Distinguish startup, damage, reach, duration, cooldown, and stamina costs. Every skill requires actual gameplay, animation, sound, VFX, UI cooldown state, bot usage, networking, and automated behavioral tests.

## 7. Briarport arena: coherent and fair

Build one integrated 3D arena, not three disconnected scenes. Preserve the waterfront brick-and-stone district, shallow puddles, restrained ivy, banners, terracotta roofs, market stalls, industrial loading equipment, and warm clear daylight of the references.

Use a canonical approximately 144 m east–west by 112 m north–south playable footprint. Godot Y is up; X runs east–west; Z runs north–south. Put A around (-42, 0, 0), B around (0, 0, 0), C around (42, 0, 0). Put mirrored team spawns around (0, 0, -48) and (0, 0, 48), each with separated exits.

This intentionally corrects the original asymmetric west/east spawns while retaining Canal Court west, Market Square center, and Loading Yard east. Document the correction. Do not claim the original generated scale bar proves these distances.

Use parallel north/south connecting routes and clear objective approaches. Start with 4–6 m main passages, 2.5–3.5 m flanks, and approximately 9 m objective radii. Adjust geometry through navigation and camera tests rather than forcing unusable proportions.

Canal Court: broad dry stone fighting deck, low walls, bridges, short stairs, surrounding canals and shallow puddles. Water and boats are outside the main fighting surface. No lethal ring-outs or mandatory swimming.

Market Square: open plaza, fixed peripheral stalls, columns, modest central fountain or landmark, multiple approaches and clean flanks. Do not fill the scoring space with obstacles.

Loading Yard: broad loading platforms, short ramps, restrained cargo cover, industrial paving, overhead crane outside active collision routes, several entrances. No moving lethal crane hazards.

Keep decorative high rooftops inaccessible unless explicitly designed as a route. No high perch may score through floors. Every objective is reachable by every animal without a species-specific skill. Ordinary paths and special traversal links need proper navigation and collision.

Compare shortest ordinary travel times from both spawn exits to all objectives for each species. Target within 10% team-side difference. Check for spawn trapping, too-narrow melee spaces, unreachable islands, fall loops, and camera obstruction. Generate an updated overhead render from the actual built map.

## 8. Blender asset and animation production

Create real editable Blender assets and usable Godot imports. Execute generation scripts; do not merely write them. Save source `.blend` files, rigged `.glb` exports, textures, materials, and source scripts. Export through a tested glTF pipeline and inspect the result inside Godot.

Characters need sculpted/modelled species-specific forms, UVs, controlled fur detail, appropriate materials, normalized skin weights, clean joint deformation, articulated paw-hands, proper feet, facial features, and flexible tails. Use optimized fur textures/cards or restrained geometry, not costly offline hair simulation at runtime.

Primitive meshes may be intermediate construction tools, but final fighters cannot look like assemblies of capsules and spheres. Do not use reference posters as billboard characters, flat environment backdrops, or one-texture substitutes for modelled anatomy.

Use compatible bone naming where useful, with species-specific proportions and extra ear, jaw, and tail bones. Keep skeleton scale clean and verify coordinate conversion. Use local baked animation tracks supported by the chosen export pipeline. Check for rest-pose drift, broken weighting, mirrored clothing, floating feet, and disconnected tails.

Produce locomotion in multiple directions, idle, turn, jump/takeoff/apex/landing, directional dodges, guard enter/hold/exit, guard break, light combo, heavy attack, hit reactions, knockdown/recovery, knockout, respawn, victory, and all skill clips with preparation/action/recovery. Add facial and ear motion where it improves readability.

Use AnimationPlayer/AnimationTree with appropriate state transitions and blending. Tail and ear secondary motion must be cosmetic and bounded. Do not let shared resource state make one fighter's animation control every instance.

Build a modular environment kit, clean collisions, reusable materials, LODs, and suitable occlusion. Prefer modest per-character material counts and 1K–2K textures where sufficient. Starting character budgets around 25–45k triangles at highest gameplay LOD are targets to profile, not an excuse for poor silhouettes.

Render front/back character comparisons and skill poses in Blender, then capture the same assets in Godot. Inspect both; a good Blender render does not prove a correct game import. Fix visible problems and preserve comparison images.

Any external asset must be legally reusable and recorded with source, license, attribution, and modifications. Use free/local assets or original creation within existing permissions. Do not assume a paid generator or undisclosed API is available.

## 9. Real multiplayer and complete self-hosted services

Use authoritative Godot dedicated match servers and ENet for real-time gameplay. Offline matches use the same authoritative rules locally. Never implement "multiplayer" as bots with player-like names or a fake matchmaking timer.

Clients send validated input intentions, not trusted damage, health, score, or final position. The server controls ownership, movement limits, attack validity, cooldowns, hit results, stamina, control effects, occupancy, respawns, and match completion.

Implement local movement prediction, numbered inputs, authoritative acknowledgements, reconciliation, remote snapshot interpolation, action-event IDs, reconnect snapshots, and duplicate/out-of-order handling. Start with 60 Hz simulation and approximately 20 Hz snapshots; measure bandwidth and tune. Separate reliable lifecycle events from frequent movement traffic.

Ensure server/client RPC paths and signatures match. Use stable entity IDs, protocol/build compatibility checks, payload limits, rate limits, and strict sender/character ownership checks. Reject impossible movement, malformed values including NaN, forged outcomes, reused match tickets, and attacks outside valid windows.

Implement bounded lag compensation for melee using server-owned position/hurtbox history. Never accept arbitrary client rewind timestamps or roll back the whole match. Define defender dodge/guard timing and wall checks consistently; test compensation at latency rather than granting unlimited reach.

Build a small real control service using Python, a maintained web framework, and PostgreSQL. Pin dependencies and verify their official APIs. Provide migrations, configuration, tests, native development scripts, and Docker Compose deployment. Do not require an external paid service.

Required service functions: account registration/login, secure password hashing using a maintained library, expiring sessions, profiles, party invitations and leadership, server registration/health, casual and ranked queues, match allocation, short-lived server-bound join tickets, authoritative results, ratings, match history, and cosmetic/mastery persistence.

Use HTTPS for public control traffic, secrets outside source, parameterized database access, and authenticated server result submission. Rating updates are transactional and idempotent: retransmitting results cannot grant additional rating. Local/offline progress cannot manufacture ranked results.

Parties have at most five members and stay on one team. Matchmaking considers queue type, roster preferences, region/latency, and rating. Do not invent waiting users; show actual queue state. A self-hosted match allocator must start real exported server processes with validated fixed arguments and a configured port range, then clean them up safely.

Default development services to local bindings. Provide deployment configuration and UDP-port instructions; do not automatically expose ports, alter router settings, or claim a worldwide service is deployed. Prepare deployable infrastructure without spending money or inventing credentials.

Unconfigured online services must produce a clear connection state while offline play remains usable. This is operational configuration, not permission to leave the backend unimplemented.

## 10. Bots, training, and competitive tools

Bots run server-side and use the same input, stamina, cooldown, collision, and hit rules as humans. They must navigate all objectives, anticipate rotations, maintain spacing, guard, dodge, punish recovery, use their actual species skills, retreat, and cooperate.

Difficulty changes reaction delay, decision quality, and coordination, not damage cheats or hidden knowledge. Use visible/heard observations and remembered positions rather than constant knowledge through walls. Provide recovery from stuck navigation and failed traversal.

Training includes move lists, input hints, stamina/cooldown display, configurable plain training dummies, guard/parry practice, skill demonstrations, and reset controls. Training overrides are explicitly unavailable in real matches.

Include private lobby administration, team assignment, bot settings, ready checks, match start, spectating, and rematches. Dead players spectate allies without receiving privileged enemy information. Observer privileges belong only to authorized private-match observers.

Record authoritative match snapshots and events with version metadata. Build an actual replay list and viewer with pause, seek, speed adjustment, follow camera, and free camera. Replay must not depend on perfectly deterministic physics re-simulation. Do not expose post-match observer information as a live competitive advantage.

## 11. Complete UI, progression, and accessibility

Build actual Godot Control-based interfaces, not flattened images with invisible hit regions. Match the supplied dark esports visual language, strong typography, restrained highlights, and prominent animal previews. Extract or recreate reusable icons cleanly; retain the supplied brand.

Finish boot/loading, main menu, offline play, online queue, account/profile, party panel, server browser/direct connection, private lobby, character selection, gameplay HUD, scoreboard, knockout/respawn, settings, training, results, match history/replays, collection/mastery, credits, and quit confirmation.

Every visible control has a real implemented action or an honest state explanation. No fictitious friends, currencies, tournaments, season news, unlocks, ping, or player counts. No dead Store button.

Character selection displays five team slots, unique species reservations, ready state, timer, full animated 3D preview, passive and Q/E/R descriptions. Server validates all selections and swaps.

HUD displays actual health, stamina, three skill cooldowns/availability, five teammates and five opponents, point totals, eight-minute match clock, active territory, rotation countdown, next location when revealed, minimap, contextual pings, and useful status feedback. No ammo, weapon slots, round counter, or ultimate meter.

Minimap shows geometry, allies, objectives, and enemies only when legitimately observed or pinged. Derive it from the real arena. Avoid omniscient enemy radar. Above-character markers use team relationship, not each animal's base clothing color.

Territory states: inactive grey, neutral gold, ally blue, enemy red, contested distinct combined/patterned treatment. Pair color with shapes and labels. Exactly one zone has active scoring presentation.

Settings include resolution, window mode, render scale, quality presets, VSync/frame cap, brightness, FOV, sensitivity/inversion, key rebinding/conflict handling, controller deadzones, audio buses, UI scale, color-vision options, reduced effects, and optional camera shake. Save and restore settings robustly.

Support keyboard/mouse and controller navigation, focus states, ultrawide-safe layout, and common 720p/1080p/1440p resolutions. No clipped HUD or unreadable text.

Persist profile, cosmetics, mastery, settings, and match history. Include a small finished set of earned palette variants and profile badges for each fighter. Cosmetic selection never changes collision, damage, movement, or readability. Separate offline progression from authenticated online records.

## 12. Audio and visual feedback

Implement surface-aware footsteps, attacks, movement skills, body impacts, guarding, parry, guard break, territory changes, score warnings, knockout, respawn, menu navigation, and restrained ambience/music. Use original or properly licensed audio; do not impersonate real people for voices.

Use positional sound for combat and movement, separate volume buses, voice limiting, and sensible attenuation. Dense fights must not overwhelm essential cues.

Light hit = small contact flash and short sound. Heavy hit = stronger but compact impact. Guard = brief contact deflection at the forearms, not a summoned shield. Guard break = distinct broken-guard icon and reaction. Scrap's parry = precise flash/sound. Knockback = readable motion and restrained dust.

No global time-scale changes in multiplayer, giant energy rings, screen-covering effects, gore, or forced cinematic finishers. Camera shake defaults low or off and can be disabled. Cosmetic hit-stop, if used, must not change simulation or input timing.

Deduplicate predicted and confirmed feedback so one hit does not play twice. Pool frequent effects and limit simultaneous particles/audio voices.

## 13. Engineering structure and performance

Use clear modules for input/controller, combat/state, abilities/data, animation, network transport/prediction, match rules, objectives, bots/navigation, UI, audio, persistence, services, and tooling. Avoid one giant script or dependencies between UI and authoritative rules.

Suggested layout: `game/`, `blender/`, `services/`, `tools/`, `tests/`, `references/`, `docs/`, `builds/`, `evidence/`. `game/project.godot` is the real project entry. Keep source assets outside runtime imports except their exported products. Use version control with small local checkpoints; do not publish remotely.

Create idempotent scripts for environment setup, asset build, import, test, local service startup, server startup, client startup, and release export. Properly quote paths with spaces. Use explicit working directories, timeouts, logs, and nonzero failure exits. Never turn a failed step into an unconditional success.

Profile ten fighters in active combat with the full arena, audio, HUD, and networking. Target stable 60 FPS at 1080p on the available supported machine, with a competitive preset targeting 120 FPS where hardware allows. Record actual CPU/GPU, renderer, settings, average frame time, tail frame times, and memory. Do not fabricate performance.

Use real-time-friendly lighting, LODs, batching/instancing where appropriate, texture budgets, occlusion, pooled VFX, and bounded AI work. Avoid allocating or searching the full scene tree every physics frame. Validate both graphical clients and headless servers after optimization.

The server must not require rendering, audio hardware, shader compilation, or visual-only resources to simulate attacks. Keep necessary collision and combat data when stripping visuals from server exports.

## 14. Verification and release gates

Write executable checks before declaring systems complete. Use the installed versions' supported command-line options. Build a single verification entry point that runs asset checks, game imports, automated tests, service tests, exports, and integration checks, preserving raw logs and machine-readable results.

Required checks:

1. Clean import/export without missing files, parse errors, broken scripts, or unexplained runtime errors.
2. Five distinct rigged models, valid materials, all required animations, working transitions, and fifteen non-placeholder skills.
3. Per-skill behavior: startup, cooldown, stamina, hit validity, miss recovery, wall interaction, interruption, and control resistance.
4. Match rules: one active zone, empty/contested behavior, correct scoring, rotation/reveal timing, overtime, respawn, and one-time victory/result submission.
5. Map navigation: both teams reach every objective; ordinary access does not require special skills; travel-time comparison; no persistent stuck loops or capture through floors.
6. Real dedicated server plus multiple client processes; include a ten-client protocol test, not only ten bots in one process.
7. Latency/loss simulation at approximately 0, 50, 100, and 150 ms RTT and up to 3% loss. Check prediction, reconciliation, duplicate hits, guard timing, cooldown consistency, and reconnect. Clearly separate localhost simulation from real WAN verification.
8. Security negatives: forged damage/score, wrong ownership, duplicate/reused tickets, invalid payloads, selection races, result replay, and unauthorized spectator access.
9. End-to-end service flow: account → party/queue → allocation → real server join → match result → saved history/rating. Ranked test uses ten real client identities, not bots masquerading as users.
10. Offline complete-match flow and bot matches through all three zones, plus at least a 20-minute soak at normal simulation speed to identify crashes, leaks, and stuck states.
11. Real UI interaction and screenshot checks for menus, character selection, gameplay, scoreboard, settings, respawn, results, and replay. Inspect rendered screenshots instead of trusting scene existence.
12. Fresh exported build launched outside the editor and from a different working directory. Verify packaged assets, save paths, controls, online/offline behavior, and shutdown.

Use repeatable seeds for scenarios, not claims of deterministic network physics. Screenshot evidence must come from the built game. Never relabel supplied concept images as game captures. Record exact commands, exit codes, timings, and evidence paths.

Iterate on visual comparison: species accuracy, clothing, foot contact, animation continuity, camera framing, environment coherence, HUD legibility, effect size, and crowded-fight readability. Passing logic tests alone does not prove these.

Do not delete, weaken, or skip failing checks to claim success. A test that cannot run is BLOCKED/NOT RUN with a reason, not PASS. Any unresolved core failure means the completion gate is not satisfied.

## 15. Execution process and final handoff

First inspect the references and toolchain, write the canonical decisions, and establish the acceptance matrix. Then implement the integrated systems, assets, services, UI, and build automation, repeatedly running relevant checks. Internal greyboxes and temporary assets are allowed only while working; replace them before final delivery.

Use parallel subagents only when actually available, with non-overlapping responsibilities and explicit interfaces. Keep one owner for integration. Do not assume unlimited agents, tokens, runtime, permissions, or external services.

Avoid long status essays and avoid repeatedly asking me to approve ordinary design choices. Continue implementing within granted permissions. After each major step, update project state with completed files, test evidence, failures, and the next exact action.

Before compaction or a session limit, save enough state to resume without rebuilding everything. Do not say you will continue autonomously after execution has stopped. Resume from saved state when execution resumes; the complete release scope remains unchanged.

Deliver the editable Godot project; editable Blender sources and generation scripts; game-ready models, rigs, animations, textures, audio, and UI assets; tested Windows client export; headless server exports and service code; local launchers; native and container deployment instructions; database migrations; `.env.example` without secrets; tests; evidence; license manifest; controls guide; and troubleshooting documentation.

Provide `README.md` with exact commands to launch offline play, start local services, host/join a match, open training, run tests, rebuild assets, and export releases. State whether each platform was actually run-tested or only exported.

The final response must name actual artifact paths, executed verification results, measured performance, and any remaining blockers or deviations. Never announce "complete" while quietly listing unfinished required systems. If external deployment has not been authorized or performed, say "deployment package prepared; public deployment not performed."

Begin by inspecting the actual workspace and all sixteen references. Then build WILDRUSH. Do not stop after the plan.
