import asyncio
import time
import aiohttp
from aiohttp import ClientSession
from core import (
    Scheduler,
    Backend,
    WeightedRoundRobinScheduler,
    RoundRobinScheduler,
    LeastConnectionsScheduler,
)


class BackendPool:
    def __init__(self, health_check_interval: float = 5.0) -> None:
        self.backends: dict[str, Backend] = {}
        self.scheduler: Scheduler = RoundRobinScheduler()
        self._lock = asyncio.Lock()
        self._health_check_interval = health_check_interval
        self._health_check_task: asyncio.Task | None = None
        self._request_times: dict[str, list[float]] = {}
        self._total_requests: dict[str, int] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._period_map = {
            "5m": 300,
            "30m": 1800,
            "1h": 3600,
            "6h": 21600,
            "24h": 86400,
        }

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
                try:
                    async with session.head(
                        backend.url, timeout=aiohttp.ClientTimeout(total=2)
                    ) as resp:
                        backend.healthy = resp.status < 500
                except Exception:
                    backend.healthy = False

    def _parse_period(self, period: str) -> int | None:
        return self._period_map.get(period)

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

    async def remove(self, backend_url: str):
        async with self._lock:
            self.backends.pop(backend_url, None)

    async def set_scheduler(self, algo: str):
        match algo:
            case "round_robin":
                self.scheduler = RoundRobinScheduler()
            case "weighted":
                self.scheduler = WeightedRoundRobinScheduler()
            case "least_conn":
                self.scheduler = LeastConnectionsScheduler()
            case _:
                raise ValueError(f"unkonw scheduling algo: {algo}")

    async def select_backend(self):
        async with self._lock:
            healthy_backends = {k: v for k, v in self.backends.items() if v.healthy}
            if not healthy_backends:
                return None
            backend = self.scheduler.select(healthy_backends)
            if backend:
                backend.active_connections += 1
            return backend

    async def release(self, backend: Backend):
        async with self._lock:
            backend.active_connections -= 1

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
