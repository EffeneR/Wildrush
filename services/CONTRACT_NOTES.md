# Contract notes — control service (for the integration lead)

`docs/API_CONTRACT.md` (v1) is implemented as written. This file records (1) exact wire-format
details the contract leaves implicit, (2) backward-compatible **additions**, and (3) the
smallest sensible decisions taken where the contract has gaps. No contract field, path,
status code or error code was removed or renamed.

Reference code for the game-server side (Python, standard library only):
`services/tests/fixtures/dummy_game_server.py` (request signing, local ticket verification,
redeem, started, result + retransmit) and `wildrush_svc/security.py`.

## 1. Wire formats (clarifications)

* **Times**: RFC 3339 UTC, second precision: `2026-09-27T13:42:00Z`. Query parameter
  `before` accepts any ISO 8601 datetime (naive = UTC).
* **Request bodies** must carry `Content-Type: application/json` (FastAPI strict content
  type); otherwise the body is not parsed and the request fails with 422.
* **Numbers**: integer fields of result bodies (`team`, `winner_team`, `kos`,
  `knocked_out`, `score`) also accept integral floats such as `4.0` (Godot's JSON parser
  turns every number into a float); strings, booleans and fractional values are 422.
  `latency_ms` values may be fractional (rounded to whole ms). Booleans must be JSON
  booleans.
* **base64url** everywhere = RFC 4648 §5 alphabet **without `=` padding**.
* **Session token**: base64url of 32 random bytes = 43 characters. Stored as
  hex(SHA-256(token ASCII)). Absolute 12 h lifetime from login (not sliding).
* **Server secret**: 43-character URL-safe string printed once by `admin add-server`.
  The HMAC key is the **ASCII bytes of that string exactly as printed** (do not
  base64-decode it). Secret files may end with a newline: strip whitespace when reading.
* **Request signing**: `hex(HMAC-SHA256(secret, METHOD "\n" PATH "\n" TIMESTAMP "\n" hex(SHA256(body))))`
  * METHOD upper-case; PATH = the request target exactly as sent (raw path, plus `?` and
    the raw query string when present); TIMESTAMP = decimal unix seconds, the same string
    as the `X-WR-Timestamp` header; body = the exact bytes sent (empty for GET:
    `e3b0c442...b855`). Signature hex is compared case-insensitively.
  * The service URL must be `scheme://host[:port]` with **no path prefix** (a proxy that
    rewrites paths would break signatures).
  * A retransmission must be **re-signed** with a fresh timestamp (window ±60 s).
* **Join ticket** `payload_b64 "." sig_b64`:
  * payload = compact JSON `{"tid","mid","aid","sid","team","role","exp"}` (in that key
    order, ASCII). `exp` = integer unix seconds (issue time + 60 s).
  * `team`: `0`/`1` for casual/ranked players; **`-1` = unassigned** (private-match players
    — the lobby admin assigns teams in-game — and all observers).
  * `sig = HMAC-SHA256(secret, payload_b64 as ASCII)`; verify against the **received**
    `payload_b64` bytes (never re-serialize the JSON).
  * Game-server checks before redeeming: HMAC (constant-time compare), `sid` == own server
    id, `mid` == own `--match-id`, `exp` > now. Then `POST /v1/servers/tickets/redeem`
    with `{"ticket_id": tid, "match_id": mid}`. The service is the single-use authority.

## 2. Error codes

Envelope always `{"error": {"code", "message"}}`. Generic codes: `validation_error` (422,
includes unknown fields and malformed JSON), `unauthorized` (401, missing/invalid/expired/
revoked bearer token, `WWW-Authenticate: Bearer`), `rate_limited` (429 + `Retry-After`),
`payload_too_large` (413, body > 64 KiB), `not_found` / `method_not_allowed` (unknown
route / method), `conflict` (409, lost a race on a unique constraint — retry),
`db_unavailable` (503), `internal_error` (500).

| Endpoint | Codes (beyond the generic ones) |
|---|---|
| POST /v1/auth/register | 409 `username_taken` |
| POST /v1/auth/login | 401 `invalid_credentials` (unknown user and wrong password are indistinguishable) |
| PATCH /v1/profile | 409 `not_unlocked`; 422 for unknown palette/badge/fighter names or `display_name: null` |
| POST /v1/parties | 409 `already_in_party`, 409 `already_in_match` |
| GET /v1/parties/current, POST .../leave | 404 `no_party` |
| POST /v1/parties/current/invites | 403 `not_leader`; 404 `no_party`, `no_such_user`; 409 `party_full`, `already_in_party`, `already_invited`, `too_many_invites` |
| POST /v1/invites/{id}/accept | 404 `invite_not_found`; 409 `expired`, `already_in_party`, `party_full`, `already_in_match` |
| POST /v1/invites/{id}/decline | 404 `invite_not_found` |
| POST /v1/parties/current/kick | 403 `not_leader`; 404 `not_in_party`; 409 `cannot_kick_self` |
| POST /v1/parties/current/promote | 403 `not_leader`; 404 `not_in_party` |
| POST /v1/queue | 403 `not_leader`; 409 `already_queued`, `already_in_match`; 422 `bots_in_ranked` |
| DELETE /v1/queue | 409 `already_matched` |
| POST /v1/matches/{id}/rejoin | 404 `match_not_found` (also: not a participant); 409 `match_not_running` |
| POST /v1/private | 409 `already_queued`, `already_hosting`; 503 `no_server_available`, `allocation_timeout`, `allocation_failed` |
| POST /v1/private/join | 404 `invalid_join_code`; 409 `match_not_ready`, `match_full`, `already_queued` |
| GET /v1/matches/{id} | 404 `match_not_found` (also for non-participants) |
| server-signed (all) | 401 `server_auth_required` (missing/malformed headers), 401 `timestamp_skew` (outside ±60 s), 401 `invalid_signature` (unknown or disabled server, bad signature) |
| POST /v1/servers/heartbeat | 409 `region_mismatch` |
| POST /v1/allocator/started | 404 `allocation_not_found`; 409 `allocation_cancelled` (stop the process), `port_mismatch`, `not_assigned`, `no_host` |
| POST /v1/allocator/ended | 404 `allocation_not_found` |
| POST /v1/matches/{id}/started | 404 `match_not_found`; 403 `wrong_server`; 409 `invalid_state` |
| POST /v1/servers/tickets/redeem | 404 `ticket_not_found` (unknown ticket, other match **or other server**); 409 `ticket_used`, `match_closed`; 410 `ticket_expired` |
| POST /v1/matches/{id}/result | 404 `match_not_found`; 403 `wrong_server`; 409 `match_not_running`, `result_conflict`; 422 `bots_in_ranked`, `invalid_result`, `match_id_mismatch` |

## 3. Backward-compatible additions

* `POST /v1/auth/login` → `account` is exactly the `GET /v1/me` object.
* `GET /v1/profile` fighters also carry `next_level_xp` (null at level 10).
* `POST /v1/parties/current/invites` 201 body: `{"invite_id","party_id","to_username","from_username","expires_at"}`.
* Party `queue` object: `{"state": "queued"|"matched", "mode", "region", "allow_bots",
  "queued_seconds" (null when matched), "match_id" (null when queued)}` or `null`.
* `POST /v1/queue` 202 body = the `GET /v1/queue/status` object.
* `GET /v1/queue/status` → `match` also has `"mode"` and `"state"`
  (`allocating`|`ready`|`running`). While `allocating`, `host`, `port`, `ticket`,
  `expires_at` are `null` ("match found, starting server"). `ticket` becomes `null` once it
  was redeemed (reconnect via `/rejoin`). An expired, never-redeemed ticket is replaced by
  a fresh one on the next status call while the match is `ready`/`running`.
  `queued_seconds` is an integer (null unless queued); `mode` is null when idle.
* Redeem response also has `"selected_badge"`, `"lobby_admin"` (true for the private-match
  creator) and `"mode"`. `palettes` = selected palette per fighter (all five fighters).
* Rejoin response also has `"match_id"`, `"team"`, `"role"`.
* Private create/join responses also have `"expires_at"` and `"role"`; both return **200**.
* Result response also has `"mastery_changes": {account_id: {"fighter","xp_gained","xp","level","badges_unlocked"}}`.
  An idempotent replay returns the stored object plus `applied:false, idempotent:true`
  (same content; JSON key order may differ). `rating_changes` is `{}` for casual/private.
* `GET /v1/matches/{id}` → `{"match_id","mode","state","region","created_at","started_at",
  "ended_at","result": <stored canonical body>|null,"rating_changes","mastery_changes"}`.
* History items also carry `xp_gained`; `fighter` is `null` for a ranked no-show (see §4
  Results). Server-browser items also carry `build_id`, `protocol`.
* `POST /v1/matches/{id}/started` → `{"ok": true, "state": "running"}`.
* `GET /healthz` when the DB is down: 503 `{"ok": false, "db": "unavailable", "error": {...}}`.
* Admin CLI extras: `enable-server`, `rotate-secret`, and `--write-secret-file PATH`
  (creates a new 0600 file instead of printing the secret).

## 4. Decisions on gaps

**Rate limits.** Implemented exactly as listed. Not specified, therefore chosen:
server-signed endpoints 1200/min per server id (`WR_SERVER_RATE_LIMIT_PER_MIN`; all game
servers of a host share its id); unauthenticated endpoints and failed player/server auth
120/min per IP. Requests failing validation still count. The limiter is in-process: run
exactly one service process (the `serve` entry point does); a restart resets windows.

**Parties.** `already_in_party` on invite = the invitee is in *any* party (including this
one). Pending invites do not reserve seats (accept → `party_full` at 5); max 10 pending
invites per party. Accepting an expired invite → 409 `expired`; declining one → 204 no-op.
Kicking yourself → 409 `cannot_kick_self`; promoting yourself → 204 no-op. Creating or
joining a party also removes that player's solo queue entry.

**Queue.** `roster_prefs`, `latency_ms`, `allow_bots` are optional (default `[]`, `{}`,
`false`). Any member of a queued party may `DELETE /v1/queue` (removes the whole party);
204 when not queued; 409 `already_matched` once a match exists. Only the leader's
`roster_prefs` exist in the contract, so other party members' `roster_prefs` are `[]`.

**Matchmaker.**
* Region: a party's candidate regions are the keys of `latency_ms` plus its own `region`
  (latency 0 if unmeasured). It accepts region R if latency ≤ 150 ms, or — after it has
  waited ≥ 60 s — if R is a candidate at all. The match region is the common accepted
  region with free server capacity that minimizes the group's maximum latency.
* A match is only formed when an allocator host of that region is enabled, `online`,
  heartbeated < 30 s ago and has free capacity. Otherwise players keep waiting and the
  counts keep showing the real queue.
* Casual bot fill: a bot group contains only parties that set `allow_bots` **and** have
  each waited ≥ 20 s; parties that did not opt in are never pulled into a bot match (they
  keep waiting). Humans are spread to balance team sizes, bots fill both teams to 5.
  `expected_players` = humans; the game server adds `10 - expected_players` bots.
* Teams: party blocks, largest first, each onto the team with the lower rating total (only
  placements that keep the remaining blocks packable). Team 0/1 labelling is arbitrary.
* Ranked uses exactly 10 humans, 5 per team, zero bots, always.

**Private matches.** `POST /v1/private` blocks until the allocator reports `started`
(≤ `WR_PRIVATE_ALLOC_WAIT_S`, default 20 s); on timeout the attempt is cancelled (503
`allocation_timeout`). One active private match per creator (`already_hosting`) protects
allocator capacity. Join codes: 8 characters from `ABCDEFGHJKMNPQRSTUVWXYZ23456789`,
case-insensitive. Up to 10 players and 10 observers. Joining works while `ready`/`running`.
Private allocations have `expected_players = 1` (the admin). The service cannot stop a
private server process: the game server should exit when its lobby is empty/idle; the
allocator kills anything older than `WR_MATCH_TIMEOUT_S` (1500 s).

**Allocation lifecycle.** The host is chosen at match formation; the port is chosen at
poll time from `free_ports` ∩ the host's heartbeat range. Assigned-but-unconfirmed
allocations are handed out again on later polls (the agent de-duplicates by
`allocation_id`). Not `started` within 45 s (`WR_ALLOCATION_TIMEOUT_S`) → match cancelled.
`ended` without a result → match `cancelled`, players back to `idle` (no automatic
re-queue; the client should say "match cancelled" and let them queue again).
Heartbeat: `region` must equal the provisioned region; `name` replaces the display name;
`matches` reconciles state — allocations started > 20 s ago that the host no longer lists
are ended and their unfinished matches cancelled (covers allocator restarts). The agent
reports `players = expected_players` (it cannot observe live player counts). The janitor
cancels ready/running matches whose host has been silent for 120 s, and matches older
than 3600 s.

**Match start / rejoin.** Recommended: the game server calls
`POST /v1/matches/{id}/started` as soon as it listens and has loaded the match, so that
`/rejoin` works during character select (rejoin is running-only, as specified) and the
result can be submitted later (results require `running`).

**Redeem.** A ticket of another server or another match is reported as 404
`ticket_not_found` (no information leak). Redemption is the single atomic
`UPDATE ... WHERE redeemed_at IS NULL AND expires_at > :now RETURNING ...`, with `:now`
bound from the service clock instead of SQL `now()` (same semantics; lets tests control
time). Redeeming for a match that is no longer ready/running → 409 `match_closed`.

**Results.**
* Checks, in order: 401 signature → 422 schema → 422 `match_id_mismatch` (body vs URL) →
  404 match → 403 allocated server → (already finished: idempotent 200 / 409
  `result_conflict`) → 409 `match_not_running` → 422 semantic checks → apply.
* Idempotency compares a canonical form (sorted keys, players sorted by `account_id`, bots
  by `(team, fighter)`, numbers normalized), so a retransmission with different key order
  is still "the same body".
* `invalid_result` when: duplicate players; more than 5 fighters (humans + bots) on a team;
  a species twice on one team; a player who is not a *player* participant of the match;
  casual/ranked player on another team than assigned. List each fighter slot once: a
  human whose slot was taken over by a bot (AFK, D-015) is listed as that human with
  `afk: true`, not additionally as a bot.
* **Ranked no-shows**: the server only learns account ids through ticket redemption, so it
  lists the players it saw (with `abandoned`/`afk` flags as observed). Matched ranked
  players missing from the result are rated as abandoned (a loss), earn 0 XP and get a
  history row with `fighter: null`; `rating_changes` always covers all 10 matched players.
  Casual/private players missing from a result get nothing.
* `winner_team` must be 0 or 1 (draws are not representable; Turf Shift always resolves).
* Rating (ranked only): Glicko-2 (τ = 0.5, RD clamped 30…350); each player vs. a composite
  opponent (opposing team's mean rating, RMS deviation); one rating period per match;
  **abandoned players are scored as a loss**.
* Mastery (all modes): points-while-controlling = `floor(control_seconds)` (1 point per
  second of sole control, D-006). **Abandoned or AFK players earn 0 XP**; private ×0.5
  (floored). Every result (idempotently) grants all tier badges up to the new level plus
  `pack_debut` to every listed player.

**Ticket lifetime settings.** `WR_TICKET_TTL_S` (default 60) and `WR_SESSION_TTL_H`
(default 12) exist for operations; keep the contract values in production.

## 5. Open points (not blocking)

* Per-member roster preferences for party members would need a new endpoint.
* Observers exist for private matches only (the contract defines no observer tickets for
  queue matches).
