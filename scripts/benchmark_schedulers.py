#!/usr/bin/env python3
"""Benchmark scheduler implementations (old vs new)."""

import argparse
import os
import sys
import time
import random

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scheduler import Backend
from core.scheduler_impl import (
    RoundRobinScheduler,
    WeightedRoundRobinScheduler,
    LeastConnectionsScheduler,
)
from scripts.old_schedulers import (
    OldRoundRobinScheduler,
    OldWeightedRoundRobinScheduler,
    OldLeastConnectionsScheduler,
)
from scripts.old_schedulers import (
    OldRoundRobinScheduler,
    OldWeightedRoundRobinScheduler,
    OldLeastConnectionsScheduler,
)


def benchmark_old_rr(backends: dict[str, Backend], num_requests: int) -> float:
    """Benchmark old RoundRobin scheduler."""
    scheduler = OldRoundRobinScheduler()
    start = time.perf_counter()
    for _ in range(num_requests):
        scheduler.select(backends)
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_new_rr(backends: list[Backend], num_requests: int) -> float:
    """Benchmark new RoundRobin scheduler."""
    scheduler = RoundRobinScheduler(backends)
    scheduler.set_backends(backends)
    start = time.perf_counter()
    for _ in range(num_requests):
        next(iter(scheduler))
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_old_weighted(backends: dict[str, Backend], num_requests: int) -> float:
    """Benchmark old WeightedRoundRobin scheduler."""
    scheduler = OldWeightedRoundRobinScheduler()
    start = time.perf_counter()
    for _ in range(num_requests):
        scheduler.select(backends)
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_new_weighted(backends: list[Backend], num_requests: int) -> float:
    """Benchmark new WeightedRoundRobin scheduler."""
    scheduler = WeightedRoundRobinScheduler(backends)
    scheduler.set_backends(backends)
    start = time.perf_counter()
    for _ in range(num_requests):
        next(iter(scheduler))
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_old_lc(backends: dict[str, Backend], num_requests: int) -> float:
    """Benchmark old LeastConnections scheduler."""
    scheduler = OldLeastConnectionsScheduler()
    start = time.perf_counter()
    for _ in range(num_requests):
        scheduler.select(backends)
    elapsed = time.perf_counter() - start
    return elapsed


def benchmark_new_lc(backends: list[Backend], num_requests: int) -> float:
    """Benchmark new LeastConnections scheduler."""
    scheduler = LeastConnectionsScheduler(backends)
    scheduler.set_backends(backends)
    start = time.perf_counter()
    for _ in range(num_requests):
        next(iter(scheduler))
    elapsed = time.perf_counter() - start
    return elapsed


def run_benchmarks(num_requests: int, backend_counts: list[int]):
    """Run all benchmarks."""
    print(f"=== Scheduler Benchmark ({num_requests:,} requests) ===\n")

    for n_backends in backend_counts:
        # Create backends
        backends_dict = {
            f"http://backend{i}.local": Backend(
                f"http://backend{i}.local", weight=i + 1
            )
            for i in range(n_backends)
        }
        backends_list = list(backends_dict.values())

        # Set random active connections for least connections
        for b in backends_list:
            b.active_connections = random.randint(0, 10)

        print(f"{n_backends} backends:")

        # Round Robin
        old_time = benchmark_old_rr(backends_dict, num_requests)
        new_time = benchmark_new_rr(backends_list, num_requests)
        print(
            f"  RoundRobin (old):      {old_time:>7.4f}s   ({num_requests / old_time:>12,.0f} ops/s)"
        )
        print(
            f"  RoundRobin (new):      {new_time:>7.4f}s   ({num_requests / new_time:>12,.0f} ops/s)"
        )

        # Weighted Round Robin
        old_time = benchmark_old_weighted(backends_dict, num_requests)
        new_time = benchmark_new_weighted(backends_list, num_requests)
        print(
            f"  Weighted (old):        {old_time:>7.4f}s   ({num_requests / old_time:>12,.0f} ops/s)"
        )
        print(
            f"  Weighted (new):        {new_time:>7.4f}s   ({num_requests / new_time:>12,.0f} ops/s)"
        )

        # Least Connections
        old_time = benchmark_old_lc(backends_dict, num_requests)
        new_time = benchmark_new_lc(backends_list, num_requests)
        print(
            f"  LeastConn (old):       {old_time:>7.4f}s   ({num_requests / old_time:>12,.0f} ops/s)"
        )
        print(
            f"  LeastConn (new):       {new_time:>7.4f}s   ({num_requests / new_time:>12,.0f} ops/s)"
        )

        print()


def main():
    parser = argparse.ArgumentParser(description="Benchmark scheduler implementations")
    parser.add_argument(
        "--requests",
        type=int,
        default=100000,
        help="Number of requests to benchmark (default: 100000)",
    )
    parser.add_argument(
        "--backend-counts",
        type=str,
        default="3,10,50",
        help="Comma-separated list of backend counts to test (default: 3,10,50)",
    )
    args = parser.parse_args()

    backend_counts = [int(x.strip()) for x in args.backend_counts.split(",")]
    run_benchmarks(args.requests, backend_counts)


if __name__ == "__main__":
    main()
