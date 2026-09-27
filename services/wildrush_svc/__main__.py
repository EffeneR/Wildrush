"""``python -m wildrush_svc [serve]`` — run the service with uvicorn (single process).

One process is required: the rate limiter is in-process and the matchmaker loop runs in
the application lifespan (it is additionally guarded by a PostgreSQL advisory lock).
"""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn
from pydantic import ValidationError

from .config import Settings
from .db import safe_url_for_logs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m wildrush_svc")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "check-config"])
    args = parser.parse_args(argv)
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        print(f"configuration error:\n{exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("wildrush_svc")
    if args.command == "check-config":
        print(f"bind={settings.bind} public_base_url={settings.public_base_url} db={safe_url_for_logs(settings)}")
        return 0
    from .app import create_app

    log.info("starting on %s (db %s)", settings.bind, safe_url_for_logs(settings))
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.bind_host,
        port=settings.bind_port,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_level=settings.log_level,
        server_header=False,
        access_log=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
