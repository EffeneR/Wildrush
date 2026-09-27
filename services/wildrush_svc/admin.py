"""Admin CLI.

    python -m wildrush_svc.admin add-server --id eu-1 --name "EU 1" --region eu [--write-secret-file PATH]
    python -m wildrush_svc.admin list-servers
    python -m wildrush_svc.admin disable-server --id eu-1
    python -m wildrush_svc.admin enable-server --id eu-1
    python -m wildrush_svc.admin rotate-secret --id eu-1 [--write-secret-file PATH]

Reads ``WR_DATABASE_URL`` (and optional ``WR_DATABASE_PASSWORD_FILE``) from the environment.
The server secret is printed exactly once (or written to a new 0600 file) and never logged.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .clock import iso_utc
from .config import Settings
from .db import create_db_engine, create_sessionmaker
from .logic import servers


def _write_secret_file(path: str, secret: str) -> None:
    target = Path(path)
    if target.exists():
        raise servers.ProvisioningError(f"refusing to overwrite existing file {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(secret + "\n")


def _report_secret(args: argparse.Namespace, secret: str, settings: Settings) -> None:
    if args.write_secret_file:
        print(f"server {args.id}: secret written to {args.write_secret_file} (mode 0600)")
    else:
        print(f"server {args.id} secret (shown once; put it in the allocator's WR_SERVER_SECRET_FILE):")
        print(secret)
    print(f"allocator: WR_SERVICE_URL={settings.public_base_url} WR_SERVER_ID={args.id}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m wildrush_svc.admin")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add-server", help="provision a server id and print its secret once")
    add.add_argument("--id", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--region", required=True)
    add.add_argument("--write-secret-file", default=None, help="write the secret to a new 0600 file instead of stdout")
    sub.add_parser("list-servers", help="list provisioned servers (never shows secrets)")
    dis = sub.add_parser("disable-server")
    dis.add_argument("--id", required=True)
    ena = sub.add_parser("enable-server")
    ena.add_argument("--id", required=True)
    rot = sub.add_parser("rotate-secret", help="issue a new secret (old one stops working)")
    rot.add_argument("--id", required=True)
    rot.add_argument("--write-secret-file", default=None)
    args = parser.parse_args(argv)

    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        print(f"configuration error:\n{exc}", file=sys.stderr)
        return 2
    engine = create_db_engine(settings)
    sessions = create_sessionmaker(engine)
    now = datetime.now(timezone.utc)
    try:
        if args.command in ("add-server", "rotate-secret"):
            with sessions.begin() as db:
                if args.command == "add-server":
                    secret = servers.add_server(
                        db, server_id=args.id, name=args.name, region=args.region, now=now
                    )
                else:
                    secret = servers.rotate_secret(db, args.id)
                if args.write_secret_file:
                    # Written before commit: if the file cannot be created nothing changes.
                    _write_secret_file(args.write_secret_file, secret)
            _report_secret(args, secret, settings)
        elif args.command == "list-servers":
            with sessions.begin() as db:
                rows = servers.list_all(db)
                header = f"{'id':<24} {'name':<20} {'region':<10} {'enabled':<8} {'status':<9} {'host':<24} {'cap':>4} {'active':>6}  last_heartbeat"
                print(header)
                for s in rows:
                    print(
                        f"{s.id:<24} {s.name[:20]:<20} {s.region:<10} {str(s.enabled):<8} {s.status:<9} "
                        f"{(s.host or '-')[:24]:<24} {s.capacity:>4} {s.active_matches:>6}  {iso_utc(s.last_heartbeat_at) or '-'}"
                    )
        elif args.command in ("disable-server", "enable-server"):
            with sessions.begin() as db:
                servers.set_enabled(db, args.id, args.command == "enable-server")
            print(f"server {args.id}: {'enabled' if args.command == 'enable-server' else 'disabled'}")
    except servers.ProvisioningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
