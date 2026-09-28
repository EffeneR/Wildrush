# WILDRUSH — Deployment Guide (control service, allocators, game servers)

**Status: deployment package prepared; public deployment not performed.** Nothing has been
exposed to the internet, no DNS/TLS certificate/firewall/router was changed, and no paid
infrastructure was provisioned. See [Verification status](#verification-status) for exactly
what was executed in the authoring environment and what is BLOCKED.

Contents: [Components](#components-and-ports) · [Native development](#1-native-development-loopback-only) ·
[Native production](#2-native-production-linux-host) · [Docker Compose](#3-container-deployment-docker-compose) ·
[Secrets](#4-secrets-handling) · [TLS](#5-tls) · [Game-server hosts & UDP ports](#6-game-server-hosts-allocators-and-udp-ports-24610-24699) ·
[Backups](#7-backups-and-restore) · [Operations](#8-operations) · [Verification status](#verification-status)

## Components and ports

| Component | Default binding | Public? | Notes |
|---|---|---|---|
| Control service (FastAPI/uvicorn, `python -m wildrush_svc serve`) | `127.0.0.1:8080` | never directly | one process; behind Caddy in production |
| PostgreSQL 16 | dev `127.0.0.1:55432`; compose: internal network only | never | holds password hashes and server secrets |
| Caddy (TLS reverse proxy) | compose: `${WR_HTTP_BIND:-127.0.0.1}:80/443` | only if you set `WR_HTTP_BIND=0.0.0.0` / open the firewall | automatic HTTPS (ACME) |
| Allocator agent (`python -m allocator`) | outbound HTTPS only | no inbound port | one per game-server host |
| Dedicated game servers (exported Godot server) | UDP `24610–24699` (one port per match) | yes, on game-server hosts | ENet, D-013 |

The game client refuses non-HTTPS service URLs unless the host is `127.0.0.1`, `localhost`
or `::1`, so any non-local deployment needs TLS (section 5).

## 1. Native development (loopback only)

```bash
tools/setup_env.sh                              # .venv incl. services/requirements.txt
services/scripts/dev_up.sh                      # PostgreSQL + migrations + service (idempotent)
services/scripts/dev_status.sh                  # exit 0 = healthy
services/scripts/dev_allocator.sh start --dummy # optional local allocator (test stand-in server)
WR_SERVER_BINARY=/abs/path/to/exported/server services/scripts/dev_allocator.sh start
services/scripts/dev_down.sh
```

State lives in `.run/` (git-ignored): `.run/pg` (cluster, owned by the `postgres` user when
the script runs as root), `.run/dev.env` (0600, random DB password), `.run/service.{log,pid}`,
`.run/allocator/` (dev server secret, agent log, per-match logs). The dev allocator uses
server id `dev-local`, region `local`, public host `127.0.0.1` (clients connect via
loopback), UDP 24610–24699. The allocator's fixed command line has no bind-address
argument: the game server chooses its bind address (bind 127.0.0.1 in local-only setups).

## 2. Native production (Linux host)

Example layout: service user `wildrush`, code in `/opt/wildrush`, config in `/etc/wildrush`.

1. **PostgreSQL 16** (distribution package). Keep `listen_addresses = 'localhost'` unless the
   database is on another host (then use TLS + `scram-sha-256` and a firewall rule):
   ```bash
   sudo -u postgres createuser --pwprompt wildrush
   sudo -u postgres createdb --owner wildrush wildrush
   ```
2. **Code + venv** (Python 3.11):
   ```bash
   sudo useradd --system --home /opt/wildrush --shell /usr/sbin/nologin wildrush
   sudo install -d -o wildrush -g wildrush /opt/wildrush
   # copy the repository's services/ directory to /opt/wildrush/services
   sudo -u wildrush python3.11 -m venv /opt/wildrush/venv
   sudo -u wildrush /opt/wildrush/venv/bin/pip install -r /opt/wildrush/services/requirements-runtime.txt
   ```
3. **Configuration** — `/etc/wildrush/service.env` (root:wildrush, mode 0640) and the DB
   password in `/etc/wildrush/pg_password` (root:wildrush, mode 0640):
   ```ini
   WR_DATABASE_URL=postgresql+psycopg://wildrush@127.0.0.1:5432/wildrush
   WR_DATABASE_PASSWORD_FILE=/etc/wildrush/pg_password
   WR_BIND=127.0.0.1:8080
   WR_PUBLIC_BASE_URL=https://wildrush.example.org
   WR_FORWARDED_ALLOW_IPS=127.0.0.1
   WR_SERVICE_BUILD=1.0.0
   ```
4. **Migrations** (before first start and after every upgrade):
   ```bash
   sudo -u wildrush bash -c 'set -a; . /etc/wildrush/service.env; set +a;
     cd /opt/wildrush/services && /opt/wildrush/venv/bin/alembic upgrade head'
   ```
5. **systemd unit** `/etc/systemd/system/wildrush-control.service`:
   ```ini
   [Unit]
   Description=WILDRUSH control service
   After=network-online.target postgresql.service
   Wants=network-online.target

   [Service]
   User=wildrush
   Group=wildrush
   WorkingDirectory=/opt/wildrush/services
   EnvironmentFile=/etc/wildrush/service.env
   ExecStart=/opt/wildrush/venv/bin/python -m wildrush_svc serve
   Restart=on-failure
   RestartSec=3
   NoNewPrivileges=true
   ProtectSystem=strict
   ProtectHome=true
   PrivateTmp=true

   [Install]
   WantedBy=multi-user.target
   ```
   `sudo systemctl daemon-reload && sudo systemctl enable --now wildrush-control`.
   Run exactly **one** service process (in-process rate limiter; the matchmaker loop is
   additionally guarded by a PostgreSQL advisory lock).
6. **Caddy** (distribution package) with `services/deploy/Caddyfile`, replacing
   `reverse_proxy service:8080` by `reverse_proxy 127.0.0.1:8080`, and `WR_DOMAIN` set in
   Caddy's environment (e.g. systemd drop-in `Environment=WR_DOMAIN=wildrush.example.org`).

## 3. Container deployment (Docker Compose)

Files: `services/Dockerfile`, `services/deploy/docker-compose.yml`, `services/deploy/Caddyfile`,
`services/.env.example`, optional `services/deploy/allocator.compose.yml`.

```bash
cd services/deploy
umask 077; openssl rand -hex 32 > secrets/pg_password.txt     # Docker secret, git-ignored
cp ../.env.example ../.env                                    # edit WR_DOMAIN, WR_PUBLIC_BASE_URL
docker compose --env-file ../.env up -d --build               # db -> migrate -> service -> caddy
docker compose --env-file ../.env ps
docker compose --env-file ../.env logs -f service
```

* `db` (`postgres:16.15-trixie`, pinned by digest) keeps data in the `pgdata` volume, sits
  on the `internal: true` backend network and publishes no port.
* `migrate` runs `alembic upgrade head` once per `up`; `service` starts only after it
  succeeded. Upgrades: `git pull` → `docker compose --env-file ../.env up -d --build`.
* `service` reads the DB password from the Docker secret (`WR_DATABASE_PASSWORD_FILE`) and
  trusts `X-Forwarded-For` only from Caddy's network (`172.30.80.0/24`).
* `caddy` (`caddy:2.11.4-alpine`, pinned by digest) binds **`127.0.0.1` by default**. To serve
  the public: point DNS `WR_DOMAIN` at the host, open TCP 80/443 (and UDP 443 for HTTP/3) in
  the host firewall, set `WR_HTTP_BIND=0.0.0.0` in `services/.env`, re-run `up -d`.
* Admin CLI inside the stack:
  ```bash
  docker compose --env-file ../.env run --rm service python -m wildrush_svc.admin add-server --id eu-1 --name "EU 1" --region eu
  docker compose --env-file ../.env run --rm service python -m wildrush_svc.admin list-servers
  ```

## 4. Secrets handling

* No secret is committed: `services/.gitignore` excludes `services/.env` and
  `services/deploy/secrets/*`; `.env.example` contains placeholders only; `.run/` is
  git-ignored; `.dockerignore` keeps `.env`, `deploy/` and tests out of image builds.
* **Database password**: Docker secret `pg_password` (compose) or
  `WR_DATABASE_PASSWORD_FILE` / a 0640 environment file (native). Never on a command line.
* **Server secrets** (one per allocator host): created by `admin add-server`, printed once
  (or written to a new 0600 file with `--write-secret-file`). The service stores them in
  the `servers` table because it must compute HMACs (request verification, ticket
  signing): treat database dumps as secret material. Rotate with `admin rotate-secret`
  (the old secret stops working immediately; update the host's secret file and restart
  its allocator), revoke with `admin disable-server`.
* **Session tokens** are stored only as SHA-256 hashes; passwords as argon2id hashes.
* Logs never contain passwords, tokens, secrets or tickets (uvicorn access logs show paths
  only; none of the API paths carry credentials).

## 5. TLS

* Public control traffic must be HTTPS: Caddy obtains and renews certificates
  automatically (ACME/Let's Encrypt) for `WR_DOMAIN`; requirements: public DNS A/AAAA record
  and inbound TCP 80+443 to Caddy. Caddy redirects HTTP to HTTPS and sends HSTS.
* The service itself speaks plain HTTP on loopback / the private compose network only and
  refuses a non-loopback `http://` `WR_PUBLIC_BASE_URL` unless `WR_DEV_ALLOW_HTTP=true`
  (never set that on a public host). The allocator likewise refuses a non-loopback
  `http://` `WR_SERVICE_URL`.
* Game traffic (ENet/UDP) is not TLS; its integrity is protected by the server-bound,
  single-use, 60 s HMAC join tickets (D-013).

## 6. Game-server hosts, allocators and UDP ports 24610–24699

**Instructions only — nothing here was applied to any machine.**

1. **Provision** a server id per host (on the control-service host):
   ```bash
   python -m wildrush_svc.admin add-server --id eu-1 --name "EU 1" --region eu --write-secret-file eu-1.secret
   ```
   Copy the file to the game-server host as `/etc/wildrush/allocator.secret`
   (owner: the allocator user, mode 0600) over a secure channel, then delete the copy.
2. **Install** the exported Linux dedicated server (e.g. `/opt/wildrush/server/`) and
   Python 3.11 (the agent uses only the standard library; copy `services/allocator/`).
3. **Open the UDP range** `24610–24699` inbound on that host (only what `WR_PORT_MIN/MAX`
   covers; one port per concurrent match, `WR_MAX_MATCHES` ≤ range size), for example:
   ```bash
   sudo ufw allow 24610:24699/udp comment 'WILDRUSH game servers'
   # or nftables:
   sudo nft add rule inet filter input udp dport 24610-24699 accept
   ```
   Behind a home/office router you would additionally need a UDP port-forward of the same
   range to the host — do this only if you intend to host publicly. Cloud hosts: add the
   range to the security group / firewall policy. No TCP port is needed on game-server
   hosts (the agent only makes outbound HTTPS requests).
4. **Run the allocator** (systemd example `/etc/systemd/system/wildrush-allocator.service`):
   ```ini
   [Unit]
   Description=WILDRUSH allocator agent
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=wildrush-game
   WorkingDirectory=/opt/wildrush/services
   Environment=WR_SERVICE_URL=https://wildrush.example.org
   Environment=WR_SERVER_ID=eu-1
   Environment=WR_SERVER_SECRET_FILE=/etc/wildrush/allocator.secret
   Environment=WR_SERVER_BINARY=/opt/wildrush/server/wildrush_server.x86_64
   Environment=WR_PUBLIC_HOST=game-eu-1.example.org
   Environment=WR_REGION=eu
   Environment=WR_PORT_MIN=24610
   Environment=WR_PORT_MAX=24699
   Environment=WR_MAX_MATCHES=4
   Environment=WR_MATCH_TIMEOUT_S=1500
   ExecStart=/usr/bin/python3.11 -m allocator
   KillMode=mixed
   TimeoutStopSec=30
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```
   `python3.11 -m allocator --check-config` (same environment) validates the settings and
   prints the exact server command line. The agent starts each match as
   `[binary, *WR_SERVER_EXTRA_ARGS_JSON, --headless, --, --server, --port N, --match-id ..., --mode ..., --service-url ..., --server-id ..., --secret-file ..., --expected-players N]`,
   SIGTERMs processes older than `WR_MATCH_TIMEOUT_S` (SIGKILL 10 s later) and stops all of
   them on shutdown (`KillMode=mixed` lets the agent do this itself).
   Container alternative: `services/deploy/allocator.compose.yml` (host networking).
5. Verify: the host appears in `GET https://<domain>/v1/servers` within a few seconds
   (heartbeat every 5 s; entries older than 30 s are hidden).

## 7. Backups and restore

The database is the only stateful component (accounts, ratings, history, server secrets).

```bash
# native (as the postgres user)
pg_dump --format=custom --file=/var/backups/wildrush/wildrush-$(date -u +%Y%m%dT%H%M%SZ).dump wildrush
# compose
docker compose --env-file ../.env exec -T db pg_dump -U wildrush --format=custom wildrush > wildrush-$(date -u +%Y%m%dT%H%M%SZ).dump
```

* Encrypt dumps at rest (e.g. `age`/`gpg`) and restrict access: they contain server
  secrets and password hashes. Keep several generations (e.g. 7 daily + 4 weekly) off-host.
* Restore into an empty database, then start the service (migrations are idempotent):
  ```bash
  createdb --owner wildrush wildrush_restore
  pg_restore --no-owner --role=wildrush --dbname=wildrush_restore wildrush-YYYYmmddTHHMMSSZ.dump
  ```
  Compose: stop `service`, restore into the `db` container with
  `docker compose ... exec -T db pg_restore -U wildrush --clean --if-exists -d wildrush < file.dump`,
  then `docker compose ... up -d`.
* Test restores regularly. After restoring an old backup, rotate server secrets if the
  backup may have leaked.

## 8. Operations

* Health: `GET /healthz` → `{"ok": true, "db": "ok"}` (503 when the database is down);
  `GET /v1/version` → API/protocol/build. The container image has a Docker `HEALTHCHECK`.
* Logs: service → stdout/journal; allocator → stdout/journal plus one file per match in
  `WR_ALLOCATOR_LOG_DIR`.
* Scaling: one control-service process handles the target scale (tens of concurrent
  matches); add game capacity by adding allocator hosts (`WR_MAX_MATCHES` each).
* Draining a host: stop its allocator (it reports `draining`, stops its matches and
  reports them ended) or `admin disable-server --id ...` (rejects its signed requests).

## Verification status

Executed in the authoring container (Ubuntu 24.04, no Docker daemon, no public network
exposure), 2026-09-27:

| Check | Result | Evidence |
|---|---|---|
| Service test suite on real PostgreSQL 16.13 (incl. live uvicorn + allocator subprocess + dummy game servers over UDP) | PASS | `evidence/services/pytest_latest.txt` (`services/scripts/run_tests.sh`) |
| Native dev stack: `dev_up.sh` (first run + idempotent re-run), `dev_status.sh`, `dev_allocator.sh start --dummy` + private match + `stop`, `dev_down.sh`, restart with persisted data | PASS | `services/scripts/smoke_dev_stack.sh` → `evidence/services/dev_stack_smoke_latest.txt` (loopback only: 127.0.0.1:8080 / 127.0.0.1:55432) |
| `docker compose config` for `docker-compose.yml` and `allocator.compose.yml` (static validation; Caddy ports default to 127.0.0.1) | PASS | `services/scripts/check_deploy_config.sh` → `evidence/services/deploy_checks_latest.txt` (Docker Compose v5.1.1 CLI) |
| `caddy validate` of `deploy/Caddyfile` with the official Caddy 2.11.4 binary (sha512 verified) | PASS | same script with `WR_CADDY_BIN=/path/to/caddy` |
| Caddy TLS termination in front of the dev service on loopback (Caddy internal CA, ports 18443/18080) | PASS (localhost smoke test, not a deployment) | HTTP/2 200 on `/healthz`, HTTP→HTTPS 308 |
| `docker build` / `docker compose up` | **BLOCKED** — no Docker daemon in the authoring environment | – |
| Public TLS certificate (ACME), public DNS, public UDP reachability, WAN tests | **NOT RUN** — no public deployment authorized | – |
| Allocator with the real exported Godot server binary | **NOT RUN** — export pending (lead); verified with the stand-in `services/tests/fixtures/dummy_game_server.py` | – |
