import asyncio
import hashlib
import logging
import time
import aiohttp
from aiohttp import ClientSession
from core import (
    Backend,
    WeightedRoundRobinScheduler,
    RoundRobinScheduler,
    LeastConnectionsScheduler,
    WeightedLeastConnectionsScheduler,
    LeastRequestsScheduler,
    MetricsCollector,
)

logger = logging.getLogger(__name__)


class BackendPool:
    def __init__(
        self,
        health_check_interval: float = 5.0,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self.backends: dict[str, Backend] = {}
        self.scheduler = RoundRobinScheduler()
        self._scheduler_iter = None
        self._lock = asyncio.Lock()
        self._health_check_interval = health_check_interval
        self._health_check_task: asyncio.Task | None = None
        self._request_times: dict[str, list[float]] = {}
        self._total_requests: dict[str, int] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._source_hash = False
        self._period_map = {
            "5m": 300,
            "30m": 1800,
            "1h": 3600,
            "6h": 21600,
            "24h": 86400,
        }
        self.metrics = metrics or MetricsCollector()

    async def start_health_checks(self):
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def stop_health_checks(self):
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

    async def _health_check_loop(self):
        while True:
            await asyncio.sleep(self._health_check_interval)
            await self._health_check()

    async def _health_check(self):
        async with self._lock:
            backends_copy = list(self.backends.values())

        async with ClientSession() as session:
            for backend in backends_copy:
                start_time = time.time()
                try:
                    async with session.head(
                        backend.url, timeout=aiohttp.ClientTimeout(total=2)
                    ) as resp:
                        latency = (time.time() - start_time) * 1000
                        backend.healthy = resp.status < 500
                        await self.metrics.record_histogram(
                            "backend.health_check.latency.ms",
                            latency,
                            {"backend": backend.url},
                        )
                        await self.metrics.increment_counter(
                            "backend.health_check.total",
                            {
                                "backend": backend.url,
                                "status": "healthy" if backend.healthy else "unhealthy",
                            },
                        )
                        logger.debug(
                            f"Health check: {backend.url} - {'healthy' if backend.healthy else 'unhealthy'} ({resp.status})"
                        )
                except Exception as e:
                    latency = (time.time() - start_time) * 1000
                    backend.healthy = False
                    await self.metrics.record_histogram(
                        "backend.health_check.latency.ms",
                        latency,
                        {"backend": backend.url},
                    )
                    await self.metrics.increment_counter(
                        "backend.health_check.errors", {"backend": backend.url}
                    )
                    await self.metrics.increment_counter(
                        "backend.health_check.total",
                        {"backend": backend.url, "status": "error"},
                    )
                    logger.warning(f"Health check failed: {backend.url} - {e}")

    def _parse_period(self, period: str) -> int | None:
        return self._period_map.get(period)

    def _rebuild_scheduler(self):
        healthy_backends = [b for b in self.backends.values() if b.healthy]
        self.scheduler.set_backends(healthy_backends)
        self._scheduler_iter = iter(self.scheduler)

    async def record_request(self, backend_url: str):
        async with self._lock:
            if backend_url not in self._request_times:
                self._request_times[backend_url] = []
            self._request_times[backend_url].append(time.time())
            self._total_requests[backend_url] = (
                self._total_requests.get(backend_url, 0) + 1
            )

    async def get_stats(self, periods: list[str]) -> dict:
        async with self._lock:
            now = time.time()
            result = {}

            for period in periods:
                if period == "all":
                    total = sum(self._total_requests.values())
                    backends = {}
                    for url, count in self._total_requests.items():
                        percentage = (count / total * 100) if total > 0 else 0
                        backends[url] = {
                            "count": count,
                            "percentage": round(percentage, 1),
                        }
                    result["all"] = {"total": total, "backends": backends}
                else:
                    seconds = self._parse_period(period)
                    if seconds is None:
                        continue

                    cutoff = now - seconds
                    total = 0
                    backends = {}
                    for url, timestamps in self._request_times.items():
                        count = sum(1 for ts in timestamps if ts >= cutoff)
                        total += count
                        if count > 0:
                            percentage = (count / total * 100) if total > 0 else 0
                            backends[url] = {
                                "count": count,
                                "percentage": round(percentage, 1),
                            }
                    result[period] = {"total": total, "backends": backends}

            return result

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(3600)
            await self._cleanup_old_requests()

    async def _cleanup_old_requests(self):
        async with self._lock:
            max_age = self._period_map.get("24h", 86400)
            cutoff = time.time() - max_age
            for url, timestamps in self._request_times.items():
                self._request_times[url] = [ts for ts in timestamps if ts >= cutoff]

    async def start_stats_cleanup(self):
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_stats_cleanup(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def add(self, backend_url: str, weight: int = 1):
        async with self._lock:
            self.backends[backend_url] = Backend(backend_url, weight=weight)
            self._rebuild_scheduler()

    async def remove(self, backend_url: str):
        async with self._lock:
            self.backends.pop(backend_url, None)
            self._rebuild_scheduler()

    async def set_scheduler(self, algo: str):
        self._source_hash = False
        match algo:
            case "round_robin":
                self.scheduler = RoundRobinScheduler()
            case "weighted":
                self.scheduler = WeightedRoundRobinScheduler()
            case "least_conn":
                self.scheduler = LeastConnectionsScheduler()
            case "weighted_least_conn":
                self.scheduler = WeightedLeastConnectionsScheduler()
            case "least_requests":
                self.scheduler = LeastRequestsScheduler()
            case "source_hash":
                self._source_hash = True
            case _:
                raise ValueError(f"unknown scheduling algo: {algo}")
        self._rebuild_scheduler()

    async def select_backend(self):
        async with self._lock:
            healthy_backends = {k: v for k, v in self.backends.items() if v.healthy}
            if not healthy_backends:
                return None
            if self._scheduler_iter is None:
                self._rebuild_scheduler()
            try:
                backend = next(self._scheduler_iter)
            except StopIteration:
                self._rebuild_scheduler()
                backend = next(self._scheduler_iter)
            backend.active_connections += 1
            await self.metrics.set_gauge(
                "backend.active_connections",
                backend.active_connections,
                {"backend": backend.url},
            )
            return backend

    async def release(self, backend: Backend):
        async with self._lock:
            backend.active_connections -= 1
            backend.total_requests += 1
        await self.metrics.set_gauge(
            "backend.active_connections",
            backend.active_connections,
            {"backend": backend.url},
        )

    async def select_backend_by_ip(self, client_ip: str) -> Backend | None:
        async with self._lock:
            healthy_backends = [b for b in self.backends.values() if b.healthy]
            if not healthy_backends:
                return None
            sorted_backends = sorted(healthy_backends, key=lambda b: b.url)
            hash_val = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
            backend = sorted_backends[hash_val % len(sorted_backends)]
            backend.active_connections += 1
            await self.metrics.set_gauge(
                "backend.active_connections",
                backend.active_connections,
                {"backend": backend.url},
            )
            return backend

    async def show(self):
        async with self._lock:
            return {
                url: {
                    "weight": b.weight,
                    "active_connections": b.active_connections,
                    "healthy": b.healthy,
                }
                for url, b in self.backends.items()
            }
