#!/usr/bin/env python3
"""Stress test the load balancer with concurrent requests."""

import argparse
import asyncio
import aiohttp
import time
import subprocess
import sys
import signal
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StressTest:
    def __init__(
        self,
        num_backends: int,
        num_requests: int,
        concurrency: int,
        lb_port: int,
    ):
        self.num_backends = num_backends
        self.num_requests = num_requests
        self.concurrency = concurrency
        self.lb_port = lb_port
        self.start_port = 8001
        self.processes: list[subprocess.Popen] = []
        self.latencies: list[float] = []

    def cleanup(self):
        """Kill all subprocesses."""
        for proc in self.processes:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.processes.clear()

    def start_fake_backends(self):
        """Start fake backend servers."""
        print(f"Starting {self.num_backends} fake backend servers...")
        for i in range(self.num_backends):
            port = self.start_port + i
            proc = subprocess.Popen(
                [sys.executable, "scripts/fake_server.py", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.processes.append(proc)
        time.sleep(0.5)

    def start_load_balancer(self):
        """Start the load balancer."""
        print(f"Starting load balancer on port {self.lb_port}...")
        proc = subprocess.Popen(
            [
                sys.executable,
                "main.py",
                "--port",
                str(self.lb_port),
                "--log-level",
                "ERROR",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(proc)
        time.sleep(2)

    def add_backends(self):
        """Add backends to the load balancer."""
        print(f"Adding {self.num_backends} backends...")
        for i in range(self.num_backends):
            port = self.start_port + i
            url = f"http://localhost:{port}"
            while True:
                try:
                    import urllib.request

                    req = urllib.request.Request(
                        f"http://localhost:{self.lb_port}/_control/add",
                        data=f'{{"url": "{url}"}}'.encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    urllib.request.urlopen(req, timeout=5)
                    break
                except Exception:
                    time.sleep(0.1)

    async def make_request(self, session: aiohttp.ClientSession, url: str):
        """Make a single request and record latency."""
        start = time.perf_counter()
        try:
            async with session.get(url) as resp:
                await resp.read()
                latency = time.perf_counter() - start
                self.latencies.append(latency)
        except Exception as e:
            self.latencies.append(None)

    async def run_test(self):
        """Run the stress test."""
        url = f"http://localhost:{self.lb_port}/"

        # Track throughput over time
        start_time = time.perf_counter()
        completed = 0
        last_report = 0
        interval = 0.5  # Report every 0.5s

        print("\nTime     Requests  RPS")
        print("-" * 30)

        async with aiohttp.ClientSession() as session:
            tasks = set()

            for _ in range(self.num_requests):
                # Control concurrency
                while len(tasks) >= self.concurrency:
                    done, tasks = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()

                task = asyncio.create_task(self.make_request(session, url))
                tasks.add(task)
                completed += 1

                # Report throughput
                elapsed = time.perf_counter() - start_time
                if elapsed - last_report >= interval:
                    rps = completed / elapsed
                    print(f"{elapsed:5.1f}s   {completed:>7}   {rps:>6.0f}")
                    last_report = elapsed

            # Wait for remaining tasks
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.perf_counter() - start_time

        # Calculate stats
        valid_latencies = [l for l in self.latencies if l is not None]
        error_count = len([l for l in self.latencies if l is None])

        return {
            "total_time": total_time,
            "completed": len(valid_latencies),
            "errors": error_count,
            "latencies": valid_latencies,
        }

    def print_results(self, results: dict):
        """Print the test results."""
        total_time = results["total_time"]
        completed = results["completed"]
        errors = results["errors"]
        latencies = results["latencies"]

        print()
        print("=" * 40)
        print("Results:")
        print(f"  Total time:  {total_time:.3f}s")
        print(f"  Completed:   {completed}")
        print(f"  Errors:      {errors}")
        print(f"  Avg RPS:     {completed / total_time:.0f} req/s")

        if latencies:
            latencies.sort()
            n = len(latencies)
            print()
            print("Latency:")
            print(f"  min:   {latencies[0] * 1000:.1f}ms")
            print(f"  p50:   {latencies[int(n * 0.50)] * 1000:.1f}ms")
            print(f"  p90:   {latencies[int(n * 0.90)] * 1000:.1f}ms")
            print(f"  p99:   {latencies[int(n * 0.99)] * 1000:.1f}ms")
            print(f"  max:   {latencies[-1] * 1000:.1f}ms")

    def run(self):
        """Run the full stress test."""
        try:
            self.start_fake_backends()
            self.start_load_balancer()
            self.add_backends()

            print(f"\n=== Stress Test ===")
            print(f"Backends:    {self.num_backends}")
            print(f"Requests:    {self.num_requests}")
            print(f"Concurrency: {self.concurrency}")
            print(f"Port:        {self.lb_port}")

            results = asyncio.run(self.run_test())
            self.print_results(results)

        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Stress test the load balancer")
    parser.add_argument(
        "backends",
        type=int,
        nargs="?",
        default=3,
        help="Number of backend servers (default: 3)",
    )
    parser.add_argument(
        "requests",
        type=int,
        nargs="?",
        default=10000,
        help="Total number of requests (default: 10000)",
    )
    parser.add_argument(
        "concurrency",
        type=int,
        nargs="?",
        default=100,
        help="Number of concurrent requests (default: 100)",
    )
    parser.add_argument(
        "port",
        type=int,
        nargs="?",
        default=8080,
        help="Load balancer port (default: 8080)",
    )
    args = parser.parse_args()

    test = StressTest(
        num_backends=args.backends,
        num_requests=args.requests,
        concurrency=args.concurrency,
        lb_port=args.port,
    )
    test.run()


if __name__ == "__main__":
    main()
