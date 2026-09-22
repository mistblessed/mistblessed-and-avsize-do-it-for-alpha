"""Open-loop HTTP arrivals using Locust's C-backed client; not a closed-loop RPS claim."""
# ruff: noqa: E402
from gevent import monkey

monkey.patch_all()

import argparse
import json
import math
import os
import platform
import statistics
import time
import uuid
from collections import Counter
from pathlib import Path

import gevent
from dotenv import load_dotenv
from gevent.pool import Pool
from locust.contrib.fasthttp import FastHttpSession
from locust.event import EventHook


def run(args: argparse.Namespace) -> dict:
    load_dotenv(args.env_file)
    headers = {"Authorization": "Bearer " + os.environ[args.key_env]}
    session = FastHttpSession(args.url, EventHook(), None, insecure=False,
                              concurrency=args.connections, network_timeout=10, connection_timeout=10)
    status: Counter = Counter()
    timings: list[float] = []
    scheduler_lag: list[float] = []
    pool = Pool(args.max_pending)
    pairs = completed = wrong_roundtrips = dropped = 0
    deadline = time.perf_counter() + 45
    while True:
        ready = session.get("/health/ready", allow_redirects=False)
        if ready.status_code == 200:
            break
        if time.perf_counter() >= deadline:
            raise SystemExit("Service did not become ready; load was not started")
        gevent.sleep(.5)
    warm = session.post("/process", json={"payload": "Email: warmup@example.org", "payload_id": uuid.uuid4().hex},
                        headers=headers, allow_redirects=False)
    if warm.status_code != 200:
        raise SystemExit("Authenticated warmup failed; load was not started")
    cpu_start = time.process_time()
    start = time.perf_counter()

    def send(payload: str, identifier: str) -> str | None:
        for attempt in range(3):
            before = time.perf_counter()
            try:
                with gevent.Timeout(10):
                    response = session.post("/process", json={"payload": payload, "payload_id": identifier},
                                            headers=headers, allow_redirects=False)
                    status[str(response.status_code)] += 1
                    if response.status_code == 200:
                        body = response.json()
                        timings.append(time.perf_counter() - before)
                        return body["result"] if isinstance(body.get("result"), str) else None
                    timings.append(time.perf_counter() - before)
                    if response.status_code and response.status_code != 429 and response.status_code < 500:
                        return None
                    delay = min(float(response.headers.get("Retry-After", "0.1")), 5)
            except (gevent.Timeout, ValueError, KeyError):
                status["transport_or_format_error"] += 1
                timings.append(time.perf_counter() - before)
                delay = .1
            if attempt < 2:
                gevent.sleep(delay)
        return None

    def pair(index: int) -> None:
        nonlocal completed, wrong_roundtrips
        identifier = uuid.uuid4().hex
        text = f"Клиент: Иванов Иван Иванович; Email: synthetic{index}@example.org; PIN: 1234;"
        if args.long_every and index % args.long_every == 0:
            text = "слово " * 100_000 + text
        masked = send(text, identifier)
        if masked is None:
            return
        restored = send(masked, identifier)
        if restored == text:
            completed += 1
        elif restored is not None:
            wrong_roundtrips += 1

    try:
        for i in range(int(args.rps * args.seconds / 2)):
            due = start + i * 2 / args.rps
            gevent.sleep(max(0, due - time.perf_counter()))
            scheduler_lag.append(max(0, time.perf_counter() - due))
            if pool.full():
                dropped += 1
            else:
                pool.spawn(pair, i)
                pairs += 1
        pool.join(raise_error=True)
    finally:
        session.client.clientpool.close()
    elapsed = time.perf_counter() - start
    def percentile(values: list[float], percent: float) -> float:
        values = sorted(values)
        return values[max(0, math.ceil(len(values) * percent) - 1)] if values else 0
    return {"generator": "Locust FastHttpSession/gevent; open-loop pair arrivals",
            "host": platform.platform(), "python": platform.python_version(), "cpu_count": os.cpu_count(),
            "server_hardware": "Record separately; generator may be a different machine",
            "target_primary_rps": args.rps, "scheduled_seconds": args.seconds,
            "elapsed_including_drain": elapsed, "scheduled_pairs": pairs,
            "completed_pairs": completed, "wrong_roundtrips": wrong_roundtrips,
            "generator_dropped_pairs": dropped, "status_counts": dict(status),
            "successful_http_rps_including_drain": status["200"] / elapsed,
            "attempt_rps_including_retries": sum(status.values()) / elapsed,
            "latency_seconds": {"mean": statistics.mean(timings) if timings else 0,
                                "p50": percentile(timings, .5), "p95": percentile(timings, .95),
                                "p99": percentile(timings, .99), "max": max(timings, default=0)},
            "scheduler_lag_p95_seconds": percentile(scheduler_lag, .95),
            "generator_cpu_seconds": time.process_time() - cpu_start,
            "long_input_every_n_pairs": args.long_every,
            "note": "Latencies include failures and connection wait; throughput includes drain. Lexical tokens are not verified model tokens."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--key-env", default="DEMO_API_KEY")
    parser.add_argument("--rps", type=int, default=100)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--connections", type=int, default=64)
    parser.add_argument("--max-pending", type=int, default=512)
    parser.add_argument("--long-every", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.rps, args.seconds, args.connections, args.max_pending) < 1:
        parser.error("Rates, duration, and limits must be positive")
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
