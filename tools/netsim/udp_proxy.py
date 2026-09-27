#!/usr/bin/env python3
"""Localhost network conditioner for WILDRUSH tests (D-013).

Relays real UDP datagrams between clients and a game server, adding per-direction delay,
jitter and random loss. Each client source address gets its own upstream socket, so ENet
sees ordinary independent peers. This is a LOCALHOST SIMULATION, not WAN verification.

  udp_proxy.py --listen 24700 --target 127.0.0.1:24610 --rtt-ms 100 --jitter-ms 5 --loss 0.03
Stats are printed as JSON on SIGTERM/SIGINT (and every --stats-every seconds).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import signal
import sys
import time


class Proxy:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.one_way = args.rtt_ms / 2000.0
        self.jitter = args.jitter_ms / 1000.0
        self.loss = args.loss
        self.rng = random.Random(args.seed)
        th, tp = args.target.split(":")
        self.target = (th, int(tp))
        self.clients: dict[tuple, asyncio.DatagramTransport] = {}
        self.listen_transport: asyncio.DatagramTransport | None = None
        self.stats = {"c2s": 0, "s2c": 0, "c2s_dropped": 0, "s2c_dropped": 0, "clients": 0,
                      "rtt_ms": args.rtt_ms, "jitter_ms": args.jitter_ms, "loss": args.loss}
        self.loop = asyncio.get_event_loop()

    def _delay(self) -> float:
        return max(0.0, self.one_way + self.rng.uniform(-self.jitter, self.jitter))

    def schedule(self, send, data: bytes, key: str) -> None:
        self.stats[key] += 1
        if self.rng.random() < self.loss:
            self.stats[key + "_dropped"] += 1
            return
        self.loop.call_later(self._delay(), send, data)

    async def start(self) -> None:
        proxy = self

        class Listen(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                proxy.listen_transport = transport

            def datagram_received(self, data, addr):
                up = proxy.clients.get(addr)
                if up is None:
                    proxy.loop.create_task(proxy._open_upstream(addr, data))
                    return
                proxy.schedule(lambda d, u=up: u.sendto(d), data, "c2s")

        await self.loop.create_datagram_endpoint(Listen, local_addr=("127.0.0.1", self.args.listen))

    async def _open_upstream(self, client_addr, first: bytes) -> None:
        proxy = self

        class Up(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                proxy.schedule(lambda d, a=client_addr: proxy.listen_transport.sendto(d, a), data, "s2c")

        if client_addr in self.clients:
            return
        transport, _ = await self.loop.create_datagram_endpoint(Up, remote_addr=self.target)
        self.clients[client_addr] = transport
        self.stats["clients"] = len(self.clients)
        self.schedule(lambda d, u=transport: u.sendto(d), first, "c2s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--rtt-ms", type=float, default=0.0)
    ap.add_argument("--jitter-ms", type=float, default=0.0)
    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--stats-every", type=float, default=0.0)
    ap.add_argument("--stats-file", default="")
    args = ap.parse_args()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    p = Proxy(args)
    loop.run_until_complete(p.start())

    def dump(*_a):
        s = json.dumps({"proxy_stats": p.stats, "time": time.time()})
        print(s, flush=True)
        if args.stats_file:
            with open(args.stats_file, "w") as fh:
                fh.write(s)

    def stop(*_a):
        dump()
        loop.stop()

    loop.add_signal_handler(signal.SIGTERM, stop)
    loop.add_signal_handler(signal.SIGINT, stop)
    if args.stats_every > 0:
        def tick():
            dump()
            loop.call_later(args.stats_every, tick)
        loop.call_later(args.stats_every, tick)
    print(json.dumps({"proxy": "ready", "listen": args.listen, "target": args.target}), flush=True)
    loop.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
