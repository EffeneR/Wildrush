"""Throw-away PostgreSQL cluster for tests (real server, never a mock).

* Runs initdb/pg_ctl as the ``postgres`` system user when executed as root (PostgreSQL
  refuses to run as root), otherwise as the current user.
* Binds 127.0.0.1 on a random free port; Unix socket in a private directory.
* ``fsync=off`` etc. for speed: this cluster is disposable test data only.
"""

from __future__ import annotations

import os
import pwd
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PG_BIN = "/usr/lib/postgresql/16/bin"


def _pg_bin() -> Path:
    candidate = Path(os.environ.get("WR_PG_BIN", DEFAULT_PG_BIN))
    if (candidate / "initdb").exists():
        return candidate
    found = shutil.which("pg_config")
    if found:
        out = subprocess.run([found, "--bindir"], capture_output=True, text=True, check=True).stdout.strip()
        if (Path(out) / "initdb").exists():
            return Path(out)
    raise RuntimeError("PostgreSQL binaries not found; set WR_PG_BIN")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class PgCluster:
    root: Path
    port: int
    user: str
    password: str
    database: str
    run_as: str | None
    bin_dir: Path

    @property
    def url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@127.0.0.1:{self.port}/{self.database}"

    @property
    def datadir(self) -> Path:
        return self.root / "data"

    @property
    def sockdir(self) -> Path:
        return self.root / "sock"

    def _cmd(self, *args: str) -> list[str]:
        if self.run_as:
            return ["runuser", "-u", self.run_as, "--", *args]
        return list(args)

    def run(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(self._cmd(*args), capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"command failed ({proc.returncode}): {' '.join(args)}\n{proc.stdout}\n{proc.stderr}"
            )
        return proc

    def psql(self, sql: str) -> str:
        superuser = self.run_as or pwd.getpwuid(os.getuid()).pw_name
        return self.run(
            str(self.bin_dir / "psql"), "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-h", str(self.sockdir), "-p", str(self.port), "-U", superuser, "-d", "postgres",
            "-c", sql,
        ).stdout

    def stop(self) -> None:
        try:
            self.run(str(self.bin_dir / "pg_ctl"), "-D", str(self.datadir), "-m", "fast", "-w", "-t", "60", "stop")
        finally:
            shutil.rmtree(self.root, ignore_errors=True)


def start_cluster(prefix: str = "wr-pgtest-") -> PgCluster:
    bin_dir = _pg_bin()
    run_as = "postgres" if os.geteuid() == 0 else None
    root = Path(tempfile.mkdtemp(prefix=prefix))
    (root / "sock").mkdir()
    if run_as:
        pw = pwd.getpwnam(run_as)
        for p in (root, root / "sock"):
            os.chown(p, pw.pw_uid, pw.pw_gid)
    os.chmod(root, 0o700)
    os.chmod(root / "sock", 0o700)
    cluster = PgCluster(
        root=root,
        port=free_port(),
        user="wildrush_test",
        password=secrets.token_hex(16),
        database="wildrush_test",
        run_as=run_as,
        bin_dir=bin_dir,
    )
    superuser = run_as or pwd.getpwuid(os.getuid()).pw_name
    cluster.run(
        str(bin_dir / "initdb"), "-D", str(cluster.datadir), "-U", superuser, "-E", "UTF8",
        "--locale=C", "--auth-local=trust", "--auth-host=scram-sha-256",
    )
    options = (
        f"-c listen_addresses=127.0.0.1 -p {cluster.port} -c unix_socket_directories={cluster.sockdir} "
        "-c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200"
    )
    cluster.run(
        str(bin_dir / "pg_ctl"), "-D", str(cluster.datadir), "-l", str(root / "postgres.log"),
        "-o", options, "-w", "-t", "60", "start",
    )
    deadline = time.monotonic() + 30
    while True:
        try:
            cluster.psql("SELECT 1")
            break
        except RuntimeError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)
    cluster.psql(f"CREATE ROLE {cluster.user} LOGIN PASSWORD '{cluster.password}'")
    cluster.psql(f"CREATE DATABASE {cluster.database} OWNER {cluster.user}")
    return cluster
