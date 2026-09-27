# WILDRUSH Control Service — API Contract (v1)

Owner: `services/`. Consumers: game client (`game/src/online/`), dedicated server
(`game/src/net/server_service.gd`), allocator agent (`services/allocator/`).
All JSON, UTF-8. Times are RFC 3339 UTC strings unless stated. IDs are UUIDv4 strings
unless stated. Errors: `{"error": {"code": "<snake_case>", "message": "<human>"}}` with
an appropriate HTTP status. Unknown fields in requests are rejected (422).

Base: `/v1`. Dev binding `http://127.0.0.1:8080` (loopback only). Public deployments
MUST terminate TLS (Caddy in `services/deploy/docker-compose.yml`); the game client
refuses non-HTTPS URLs unless the host is `127.0.0.1`, `localhost` or `::1`.

## Authentication
* **Players**: `Authorization: Bearer <token>` (opaque 32-byte random, base64url; stored
  hashed with SHA-256; 12 h expiry; logout revokes).
* **Servers / allocator hosts**: request signing:
  * `X-WR-Server: <server_id>` (text id, `^[a-z0-9-]{3,40}$`)
  * `X-WR-Timestamp: <unix seconds>` (±60 s window)
  * `X-WR-Signature: hex(HMAC-SHA256(secret, METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + hex(SHA256(body))))`
    where PATH includes the query string, body is the raw request bytes ("" for GET).
  * Secrets are provisioned with `python -m wildrush_svc.admin add-server --id <id> --name <name> --region <r>`
    which prints the secret once. Stored server-side; never logged.

## Rate limits (per IP unless stated; 429 `rate_limited` with `Retry-After`)
login 10/min per IP and 10/min per username · register 5/min · party invites 20/min per
account · queue join/leave 20/min per account · all others 120/min per account.

## Accounts
| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/v1/auth/register` | `{"username": "^[A-Za-z0-9_]{3,16}$", "password": "8..128 chars", "display_name": "optional, 3..20 printable"}` | 201 `{"account_id", "username", "display_name"}`; 409 `username_taken` |
| POST | `/v1/auth/login` | `{"username", "password"}` | 200 `{"token", "expires_at", "account": {...me}}`; 401 `invalid_credentials` |
| POST | `/v1/auth/logout` | – | 204 |
| GET | `/v1/me` | – | 200 `{"account_id", "username", "display_name", "created_at", "rating": {"rating", "deviation", "games", "wins", "losses"}}` |

Passwords: argon2id via `argon2-cffi` `PasswordHasher()` defaults; rehash on login when
parameters change. Username uniqueness is case-insensitive.

## Profile, cosmetics, mastery
Fighters: `nyx`, `bruno`, `vex`, `hops`, `scrap`. Palettes: `default`, `dusk`, `ember`,
`frost` (unlocked at mastery levels 1, 3, 5, 7). Badges per fighter:
`<fighter>_initiate` (L2), `<fighter>_adept` (L4), `<fighter>_veteran` (L6),
`<fighter>_master` (L8), plus global `pack_debut` (first online match).
Mastery XP per match: 100 base + 50 win + 2 × points-while-controlling (cap 200) +
10 × KOs (cap 100). Level thresholds: `[0, 300, 800, 1500, 2400, 3500, 4800, 6300, 8000, 10000]`
(levels 1–10). Online mastery is only granted by server-submitted results.

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/v1/profile` | – | `{"display_name", "selected_badge", "badges": [..], "fighters": {"nyx": {"xp", "level", "palettes": [..], "selected_palette"}, ...}}` |
| PATCH | `/v1/profile` | `{"display_name"?, "selected_badge"?, "selected_palettes"?: {"nyx": "ember"}}` | updated profile; 409 `not_unlocked` |

## Parties (max 5 members; one party per account; leader-only actions noted)
| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/v1/parties` | – | 201 party; 409 `already_in_party` |
| GET | `/v1/parties/current` | – | `{"party_id", "leader_id", "members": [{"account_id", "username", "display_name"}], "invites": [{"invite_id", "to_username", "expires_at"}], "queue": {...}|null}`; 404 `no_party` |
| POST | `/v1/parties/current/invites` | `{"username"}` (leader) | 201 invite; 409 `party_full` / `already_in_party` / `already_invited`; 404 `no_such_user` |
| GET | `/v1/invites` | – | `[{"invite_id", "party_id", "from_username", "expires_at"}]` (pending, unexpired, addressed to me) |
| POST | `/v1/invites/{invite_id}/accept` | – | party; 409 `party_full`/`already_in_party`/`expired` |
| POST | `/v1/invites/{invite_id}/decline` | – | 204 |
| POST | `/v1/parties/current/leave` | – | 204 (leader leaving promotes the longest-standing member; empty party is deleted) |
| POST | `/v1/parties/current/kick` | `{"account_id"}` (leader) | 204 |
| POST | `/v1/parties/current/promote` | `{"account_id"}` (leader) | 204 |
Invites expire after 5 minutes. Joining/leaving a party removes it from any queue.

## Queue & matchmaking
| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/v1/queue` | `{"mode": "casual"|"ranked", "roster_prefs": ["nyx", ...] (0..5 unique), "region": "^[a-z0-9-]{2,20}$", "latency_ms": {"<region>": int}, "allow_bots": bool (casual only; ranked must be false)}` | 202 `{"state": "queued", ...}`; only the party leader (or solo player) may queue; the whole party enters |
| DELETE | `/v1/queue` | – | 204 |
| GET | `/v1/queue/status` | – | `{"state": "idle"|"queued"|"matched", "mode", "queued_seconds", "counts": {"casual": <players queued>, "ranked": <players queued>}, "match": null | {"match_id", "host", "port", "ticket", "team", "expires_at"}}` |

Matchmaker (runs every 1 s inside the service):
* Parties are never split and are always on one team (party size ≤ 5).
* **Ranked**: exactly 10 humans; teams of 5 built by greedy rating balancing over
  party blocks; region = common region with best max latency ≤ 150 ms (relaxed to any
  common region after 60 s).
* **Casual**: prefers 10 humans; after 20 s, if **every** queued party in the candidate
  group set `allow_bots`, forms a match with ≥ 1 human and fills the rest with bots
  (bots are labelled in-game). Otherwise waits.
* `roster_prefs` are forwarded to the game server as initial pick suggestions; final
  species selection is server-authoritative in character select.
* Counts are real numbers of queued players. No invented players.
On match formation: a `matches` row (state `allocating`), an allocation request for an
allocator host with a free port, and after the host reports `started`, one join ticket
per player (state `ready`), visible through `/v1/queue/status`.

## Join tickets
Format: `base64url(payload_json) + "." + base64url(HMAC-SHA256(server_secret, payload_b64))`
where payload = `{"tid", "mid", "aid", "sid", "team", "role": "player"|"observer", "exp": <unix>}`.
Expiry 60 s from issue. The game server verifies signature/sid/mid/exp locally, then
redeems it:
| POST | `/v1/servers/tickets/redeem` (server-signed) | `{"ticket_id", "match_id"}` | 200 `{"account_id", "username", "display_name", "team", "role", "roster_prefs", "palettes": {...}}`; 409 `ticket_used`; 410 `ticket_expired`; 404 |
Redemption is a single atomic `UPDATE ... WHERE redeemed_at IS NULL AND expires_at > now()`.
Reconnect: a player of a running match can request a fresh ticket:
| POST | `/v1/matches/{match_id}/rejoin` (player) | – | `{"host", "port", "ticket", "expires_at"}` if the player belongs to the match and it is `running` |

## Servers, allocator
| Method | Path | Auth | Body | Response |
|--------|------|------|------|----------|
| POST | `/v1/servers/heartbeat` | server | `{"name", "region", "host", "port_min", "port_max", "capacity", "build_id", "protocol", "status": "online"|"draining", "matches": [{"match_id", "port", "players", "state"}]}` | `{"ok": true}` |
| GET | `/v1/servers` | none | – | server browser: `[{"server_id", "name", "region", "host", "status", "capacity", "active_matches", "last_seen"}]` (only heartbeat < 30 s) |
| POST | `/v1/allocator/poll` | server | `{"free_ports": [int...]}` | `{"allocations": [{"allocation_id", "match_id", "mode", "port", "expected_players"}]}` |
| POST | `/v1/allocator/started` | server | `{"allocation_id", "match_id", "port", "pid"}` | `{"ok": true}` → match `ready`, tickets issued |
| POST | `/v1/allocator/ended` | server | `{"allocation_id", "match_id", "exit_code", "reason"}` | `{"ok": true}` (cancels match if no result was submitted) |
| POST | `/v1/matches/{match_id}/started` | server | `{}` | match `running` |

## Private matches (online)
| POST | `/v1/private` (player) | `{"region"}` | `{"match_id", "join_code" (8 chars), "host", "port", "ticket"}` (creator is lobby admin) |
| POST | `/v1/private/join` (player) | `{"join_code", "role": "player"|"observer"}` | `{"match_id", "host", "port", "ticket"}` |
Private matches are never rated; mastery XP still applies (reduced ×0.5).

## Results (server-signed, idempotent)
| POST | `/v1/matches/{match_id}/result` |
Body:
```json
{"match_id": "...", "winner_team": 0, "score": [250, 173], "duration_s": 402.5,
 "sudden_death": false, "ended_reason": "score_limit|time|sudden_death|forfeit",
 "players": [{"account_id": "...", "team": 0, "fighter": "nyx", "kos": 4,
              "knocked_out": 2, "damage_dealt": 1830, "control_seconds": 61,
              "abandoned": false, "afk": false}],
 "bots": [{"team": 1, "fighter": "hops"}], "replay_id": "optional"}
```
* First valid submission: 200 `{"applied": true, "rating_changes": {"<account_id>": {"before", "after"}}}`.
* Same body again: 200 `{"applied": false, "idempotent": true, ...same rating_changes}`.
* Different body for an already-finished match: 409 `result_conflict`.
* Only the server that the match was allocated to may submit; match must be `running`.
* Ranked matches with any bot entry are rejected (422 `bots_in_ranked`).
* Rating update + mastery + history rows are written in ONE transaction.

## History
| GET | `/v1/matches/history?limit=20&before=<iso>` (player) | `[{"match_id", "mode", "ended_at", "team", "fighter", "won", "score", "rating_delta"|null}]` |
| GET | `/v1/matches/{match_id}` (participant) | full stored result |

## Health / meta
| GET | `/healthz` | `{"ok": true, "db": "ok"}` (503 if DB down) |
| GET | `/v1/version` | `{"api": 1, "protocol": <int>, "service_build": "..."}` |
