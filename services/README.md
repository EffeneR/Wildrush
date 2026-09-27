# WILDRUSH services — control service + allocator agent

Self-hostable control plane for WILDRUSH online play: accounts and sessions, profiles,
cosmetics and mastery, parties, casual/ranked queues with a background matchmaker, match
allocation onto allocator hosts, HMAC join tickets, private matches with join codes and
observers, idempotent server-submitted results with Glicko-2 ratings, match history,
server browser, health/version.

* HTTP contract: [`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md) (binding) — clarifications,
  additions and gap decisions: [`CONTRACT_NOTES.md`](CONTRACT_NOTES.md).
* Deployment (native + Docker Compose + Caddy TLS, UDP ports, backups):
  [`docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).
* Stack (D-014): Python 3.11, FastAPI 0.141.1 / Starlette 1.7.0, uvicorn 0.54.0,
  SQLAlchemy 2.1.1 + psycopg 3.3.6, Alembic 1.20.0, argon2-cffi 25.1.0, pydantic 2.13.5 /
  pydantic-settings 2.15.0, PostgreSQL 16. Exact pins: `requirements-runtime.txt`
  (runtime) and `requirements.txt` (runtime + tests).

## Architecture

```
game client ──HTTPS──▶ Caddy (TLS) ──▶ control service (FastAPI, 1 process) ──▶ PostgreSQL 16
                                          ▲   │ matchmaker loop (1 s, in lifespan)
          dedicated game servers ─signed──┘   │
          allocator agent (per host) ─signed──┘ poll/started/ended/heartbeat
               └─ starts real server processes: [binary, *extra, --headless, --, --server, --port N, ...]
```

| Module | Responsibility |
|---|---|
| `wildrush_svc/app.py` | app factory `create_app()`, lifespan (matchmaker task), body-size + no-store middleware |
| `wildrush_svc/config.py` | `Settings` from `WR_*` environment variables (pydantic-settings) |
| `wildrush_svc/models.py` | SQLAlchemy 2.x models (schema created **only** by Alembic) |
| `wildrush_svc/schemas.py` | request bodies, `extra="forbid"`, strict primitive types |
| `wildrush_svc/security.py` | argon2id, session tokens, request HMAC, join tickets |
| `wildrush_svc/auth.py` | bearer-session and server-signature dependencies, rate-limit buckets |
| `wildrush_svc/ratelimit.py` | in-process sliding-window limiter |
| `wildrush_svc/matchmaking.py` | **pure** grouping / team balancing / region selection |
| `wildrush_svc/matchmaker.py` | DB tick (advisory lock, `FOR UPDATE SKIP LOCKED`) + background loop |
| `wildrush_svc/rating.py`, `mastery.py` | Glicko-2 team variant; XP, levels, unlocks |
| `wildrush_svc/logic/*` | accounts, profile, parties, queue, allocation, tickets, private, results, history, servers, janitor |
| `wildrush_svc/routers/*` | thin HTTP layer: validation → one transaction → logic |
| `wildrush_svc/admin.py` | admin CLI |
| `allocator/agent.py` | allocator agent (standard library only) |
| `alembic/` | migrations (`0001_initial_schema`) |

Design rules: every request runs in one explicit transaction; all SQL goes through
SQLAlchemy with bound parameters; timestamps are timezone-aware UTC (`TIMESTAMPTZ`, session
time zone UTC); secrets and tokens are never logged; results are all-or-nothing
(`SELECT ... FOR UPDATE` on the match row + primary-key uniqueness of `match_results`).

## Quick start (native, loopback only)

```bash
tools/setup_env.sh                        # once: creates .venv with services/requirements.txt
services/scripts/dev_up.sh                # PostgreSQL 127.0.0.1:55432 + migrations + service 127.0.0.1:8080
services/scripts/dev_status.sh            # exit 0 when healthy
services/scripts/dev_allocator.sh start --dummy   # optional: allocator with the test stand-in server
WR_SERVER_BINARY=/abs/path/wildrush_server.x86_64 services/scripts/dev_allocator.sh start   # real export
services/scripts/dev_allocator.sh stop
services/scripts/dev_down.sh              # stops allocator, service, PostgreSQL (data kept in .run/pg)
```

`dev_up.sh` is idempotent: it initializes the cluster under `.run/pg` (as the `postgres`
system user when run as root), writes `.run/dev.env` (0600, random DB password), creates the
role/database, runs `alembic upgrade head`, starts uvicorn in the background (log
`.run/service.log`, pid `.run/service.pid`) and waits for `/healthz`.

Run the service by hand: `set -a; source .run/dev.env; set +a; cd services && ../.venv/bin/python -m wildrush_svc serve`.

## Tests

```bash
services/scripts/run_tests.sh                   # all tests; raw output -> evidence/services/pytest_latest.txt
services/scripts/run_tests.sh -m "not live"     # skip the multi-process end-to-end tests
services/scripts/run_tests.sh -k results -x     # any pytest arguments
```

Other checks (both write to `evidence/services/`):

```bash
services/scripts/smoke_dev_stack.sh          # dev_up -> status -> dummy allocator -> private match over HTTP -> stop
WR_CADDY_BIN=/path/to/caddy services/scripts/check_deploy_config.sh   # docker compose config + caddy validate (static)
```

The session fixture starts a **real, throw-away PostgreSQL 16 cluster** (initdb as the
`postgres` user when root, random free port on 127.0.0.1, temp directory removed afterwards)
and applies the migrations with Alembic. Set `WR_TEST_DATABASE_URL` to test against an
existing empty database instead. `tests/test_e2e_live.py` runs a real uvicorn server, the
allocator agent as a subprocess and dummy game-server processes that verify tickets and
talk UDP — no mocks in that loop.

Coverage: register/login/logout/expiry/rehash, profile & unlock validation, parties
(invite/accept/decline/kick/promote/leave, max 5, one party, expiry), queue & real counts,
matchmaker (unit + DB: ranked exactly 10, never bots; casual bot rules; parties kept
together; rating balance; region/latency; capacity), allocator flow & ticket security
(forged, wrong server, wrong match, expired, reused, concurrent redemption), results
(signature, wrong server, running-only, idempotent retransmit, conflict, bots in ranked,
invalid bodies without side effects, XP ×0.5 private, badges), Glicko-2 reference values,
history pagination/privacy, server browser staleness, heartbeat reconciliation, rate limits,
HMAC timestamp window, injection-style inputs, body limit, migrations (`alembic check`,
round trip, app never creates tables), admin CLI, allocator agent (config validation,
exact argv, SIGTERM→SIGKILL timeouts, shutdown cleanup).

## Migrations

```bash
cd services
export WR_DATABASE_URL=postgresql+psycopg://wildrush:...@127.0.0.1:55432/wildrush   # or source .run/dev.env
../.venv/bin/alembic upgrade head          # apply
../.venv/bin/alembic current               # show revision
../.venv/bin/alembic check                 # fails if models and migrations differ
../.venv/bin/alembic revision --autogenerate -m "describe change"   # new migration, then review it
```

The application never creates or alters tables itself (`tests/test_migrations.py`).

## Admin CLI

```bash
cd services   # with WR_DATABASE_URL (and optionally WR_DATABASE_PASSWORD_FILE) set
../.venv/bin/python -m wildrush_svc.admin add-server --id eu-1 --name "EU 1" --region eu
      # prints the secret ONCE; or: --write-secret-file /etc/wildrush/eu-1.secret (new 0600 file)
../.venv/bin/python -m wildrush_svc.admin list-servers      # never shows secrets
../.venv/bin/python -m wildrush_svc.admin disable-server --id eu-1
../.venv/bin/python -m wildrush_svc.admin enable-server --id eu-1
../.venv/bin/python -m wildrush_svc.admin rotate-secret --id eu-1 [--write-secret-file PATH]
```

## Allocator agent

`python -m allocator` (from `services/`) or `python services/allocator/agent.py`. Standard
library only, so it runs on a game-server host without the service's dependencies. It
heartbeats every 5 s, polls every 1 s, validates each allocation (UUIDs, mode, port range,
UDP port actually free) and starts the server with `subprocess.Popen` (no shell) using
exactly:

```
[WR_SERVER_BINARY, *WR_SERVER_EXTRA_ARGS_JSON, "--headless", "--", "--server", "--port", PORT,
 "--match-id", MATCH_ID, "--mode", casual|ranked|private, "--service-url", WR_SERVICE_URL,
 "--server-id", WR_SERVER_ID, "--secret-file", WR_SERVER_SECRET_FILE, "--expected-players", N]
```

Children run in their own session with a parent-death signal, `WR_*` variables stripped
from their environment, stdout/stderr in `WR_ALLOCATOR_LOG_DIR/<match_id>.log`. Exited
children are reaped and reported (`ended`); processes over `WR_MATCH_TIMEOUT_S` (1500 s)
get SIGTERM, then SIGKILL after `WR_KILL_GRACE_S` (10 s); SIGTERM/SIGINT to the agent
terminates all children the same way. `python -m allocator --check-config` validates the
environment and prints the argument vector it would use.

| Variable | Default | Meaning |
|---|---|---|
| `WR_SERVICE_URL` | required | control service base URL (https unless loopback / `WR_DEV_ALLOW_HTTP=1`) |
| `WR_SERVER_ID` | required | provisioned id |
| `WR_SERVER_SECRET_FILE` | required | file with the secret (chmod 600) |
| `WR_SERVER_BINARY` | required | absolute path of the exported Linux server |
| `WR_SERVER_EXTRA_ARGS_JSON` | `[]` | fixed engine args placed before `--headless`, e.g. `["--main-pack","/opt/wr/server.pck"]` |
| `WR_PORT_MIN` / `WR_PORT_MAX` | 24610 / 24699 | UDP range |
| `WR_PUBLIC_HOST` | required | address clients connect to |
| `WR_REGION` | required | must equal the provisioned region |
| `WR_MAX_MATCHES` | 4 | concurrent matches on this host |
| `WR_MATCH_TIMEOUT_S` | 1500 | hard per-process timeout |
| `WR_SERVER_NAME`, `WR_BUILD_ID`, `WR_PROTOCOL` | id, `unknown`, 1 | reported in heartbeats / server browser |
| `WR_POLL_INTERVAL_S`, `WR_HEARTBEAT_INTERVAL_S`, `WR_KILL_GRACE_S` | 1, 5, 10 | timing |
| `WR_ALLOCATOR_LOG_DIR`, `WR_PORT_CHECK_HOST`, `WR_HTTP_TIMEOUT_S` | tmp dir, `0.0.0.0`, 10 | misc |

## Service configuration (`WR_*`)

| Variable | Default | Meaning |
|---|---|---|
| `WR_DATABASE_URL` | required | `postgresql+psycopg://user[:pass]@host:port/db` |
| `WR_DATABASE_PASSWORD_FILE` | – | file whose content replaces the URL password (Docker secret) |
| `WR_BIND` | `127.0.0.1:8080` | listen address of `python -m wildrush_svc serve` |
| `WR_PUBLIC_BASE_URL` | `http://127.0.0.1:8080` | public URL; must be https unless loopback or `WR_DEV_ALLOW_HTTP=true` |
| `WR_FORWARDED_ALLOW_IPS` | `127.0.0.1,::1` | proxies whose `X-Forwarded-For` is trusted (client IP for rate limits) |
| `WR_TICKET_TTL_S` / `WR_SESSION_TTL_H` / `WR_INVITE_TTL_S` | 60 / 12 / 300 | lifetimes (contract values) |
| `WR_MATCHMAKER_ENABLED` / `WR_MATCHMAKER_INTERVAL_S` | true / 1.0 | background matchmaker |
| `WR_MM_MAX_LATENCY_MS` / `WR_MM_REGION_RELAX_S` / `WR_MM_CASUAL_BOT_WAIT_S` | 150 / 60 / 20 | matchmaking rules |
| `WR_SERVER_STALE_S` / `WR_ALLOCATION_TIMEOUT_S` / `WR_HOST_LOST_S` / `WR_MATCH_MAX_AGE_S` | 30 / 45 / 120 / 3600 | liveness |
| `WR_PRIVATE_ALLOC_WAIT_S` / `WR_PRIVATE_MAX_PLAYERS` / `WR_PRIVATE_MAX_OBSERVERS` | 20 / 10 / 10 | private matches |
| `WR_RATE_LIMIT_ENABLED` / `WR_SERVER_RATE_LIMIT_PER_MIN` | true / 1200 | rate limiting |
| `WR_MAX_BODY_BYTES` | 65536 | request body limit (413) |
| `WR_PROTOCOL_VERSION` / `WR_SERVICE_BUILD` | 1 / `dev` | `/v1/version` |
| `WR_LOG_LEVEL` / `WR_API_DOCS` | info / false | logging; `/docs` + `/v1/openapi.json` when true |

## Integration checklist for the game (lead)

1. Client: base URL from settings; refuse non-HTTPS except loopback; send
   `Content-Type: application/json`; `Authorization: Bearer <token>`; poll
   `GET /v1/queue/status` (≈1–2 s) and connect when `match.ticket` is non-null.
2. Dedicated server: parse the user args after `--`; read and strip the secret file; sign
   every service call (see CONTRACT_NOTES §1); call `/v1/matches/{id}/started` once
   listening; verify each ticket locally, then redeem it; submit the result once (retry on
   network errors with the same body, re-signed) and exit — the allocator reports `ended`.
3. Provision a server id per game-server host (`admin add-server`), start the allocator
   with `WR_SERVER_BINARY` pointing at the exported server.
