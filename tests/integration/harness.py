"""Process harness for WILDRUSH multi-process integration tests.

Launches REAL processes: the Godot dedicated server, N Godot client processes (each a real
client identity driven by a seeded autopilot script), and optionally the UDP netsim proxy.
Logs are preserved under evidence/<area>/<run>/.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "game"


def _paths() -> dict:
    env = {}
    p = ROOT / ".toolchain" / "paths.env"
    for line in p.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


PATHS = _paths()
GODOT = PATHS["GODOT_BIN"]
PYTHON = PATHS.get("PYTHON_BIN", sys.executable)


def free_udp_port(start: int = 24610, end: int = 24699) -> int:
    for p in range(start, end + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError("no free UDP port")


@dataclass
class Proc:
    name: str
    popen: subprocess.Popen
    log_path: Path
    jsonl: Path | None = None

    def alive(self) -> bool:
        return self.popen.poll() is None

    def stop(self, timeout: float = 10.0) -> int:
        if self.alive():
            self.popen.send_signal(signal.SIGTERM)
            try:
                self.popen.wait(timeout)
            except subprocess.TimeoutExpired:
                self.popen.kill()
                self.popen.wait(5)
        return self.popen.returncode

    def json_lines(self) -> list[dict]:
        out = []
        if self.jsonl and self.jsonl.exists():
            for line in self.jsonl.read_text().splitlines():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out

    def server_events(self) -> list[dict]:
        out = []
        if self.log_path.exists():
            for line in self.log_path.read_text(errors="replace").splitlines():
                if line.startswith("[server] "):
                    try:
                        out.append(json.loads(line[9:]))
                    except json.JSONDecodeError:
                        pass
        return out

    def errors(self) -> list[str]:
        if not self.log_path.exists():
            return []
        errs = []
        for line in self.log_path.read_text(errors="replace").splitlines():
            if ("ERROR" in line or "SCRIPT ERROR" in line) and "RID allocations" not in line and "leaked at exit" not in line:
                errs.append(line)
        return errs


@dataclass
class Run:
    area: str
    name: str
    procs: list[Proc] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.dir = ROOT / "evidence" / self.area / self.name
        self.dir.mkdir(parents=True, exist_ok=True)

    def _spawn(self, name: str, args: list[str], jsonl: bool = False, cwd: Path | None = None) -> Proc:
        log = self.dir / f"{name}.log"
        jl = self.dir / f"{name}.jsonl" if jsonl else None
        fh = open(log, "w")
        env = dict(os.environ)
        p = subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT, cwd=str(cwd or GAME), env=env)
        proc = Proc(name, p, log, jl)
        self.procs.append(proc)
        return proc

    def server(self, port: int, extra: list[str] | None = None, name: str = "server") -> Proc:
        args = [GODOT, "--headless", "--path", str(GAME), "--", "--server", "--port", str(port)] + (extra or [])
        return self._spawn(name, args)

    def client(self, name: str, host: str, port: int, scenario: str = "fight", seed: int = 1,
               extra: list[str] | None = None) -> Proc:
        jl = self.dir / f"{name}.jsonl"
        args = [GODOT, "--headless", "--path", str(GAME), "--", "--autopilot", scenario, "--connect", f"{host}:{port}",
                "--name", name, "--seed", str(seed), "--log-json", str(jl)] + (extra or [])
        return self._spawn(name, args, jsonl=True)

    def proxy(self, listen: int, target_port: int, rtt_ms: float, loss: float, jitter_ms: float = 0.0,
              name: str = "proxy") -> Proc:
        stats = self.dir / f"{name}_stats.json"
        args = [PYTHON, str(ROOT / "tools" / "netsim" / "udp_proxy.py"), "--listen", str(listen), "--target",
                f"127.0.0.1:{target_port}", "--rtt-ms", str(rtt_ms), "--loss", str(loss), "--jitter-ms", str(jitter_ms),
                "--stats-file", str(stats)]
        return self._spawn(name, args, cwd=ROOT)

    def wait_all(self, procs: list[Proc], timeout: float) -> None:
        t0 = time.time()
        for p in procs:
            left = max(1.0, timeout - (time.time() - t0))
            try:
                p.popen.wait(left)
            except subprocess.TimeoutExpired:
                pass

    def cleanup(self) -> None:
        for p in reversed(self.procs):
            p.stop()

    def write_result(self, result: dict) -> Path:
        path = self.dir / "result.json"
        path.write_text(json.dumps(result, indent=2))
        return path
