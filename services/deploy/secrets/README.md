# deploy/secrets (git-ignored)

Files referenced by `docker-compose.yml` / `allocator.compose.yml` as Docker secrets. Create
them on the deployment host only, readable by the deploying user only:

| File | Content | Create with |
|------|---------|-------------|
| `pg_password.txt` | PostgreSQL password for role `wildrush` | `umask 077; openssl rand -hex 32 > pg_password.txt` |
| `allocator.secret` | server secret printed by `admin add-server` (allocator hosts only) | `docker compose ... run --rm service python -m wildrush_svc.admin add-server ...` |

Never commit these files, paste them into tickets/chats, or bake them into images.
