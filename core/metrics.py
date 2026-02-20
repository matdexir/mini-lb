import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Counter:
    value: int = 0

    def add(self, value: int = 1):
        self.value += value


@dataclass
class Histogram:
    values: list[float] = field(default_factory=list)
    _sum: float = 0.0
    _count: int = 0

    def record(self, value: float):
        self.values.append(value)
        self._sum += value
        self._count += 1

    @property
    def sum(self) -> float:
        return self._sum

    @property
    def count(self) -> int:
        return self._count

    def percentiles(self, *percentiles: float) -> dict[str, float]:
        if not self.values:
            return {f"p{int(p)}": 0.0 for p in percentiles}
        sorted_values = sorted(self.values)
        result = {}
        for p in percentiles:
            idx = int(len(sorted_values) * p / 100)
            result[f"p{int(p)}"] = sorted_values[min(idx, len(sorted_values) - 1)]
        return result


@dataclass
class Gauge:
    value: float = 0.0

    def set(self, value: float):
        self.value = value

    def inc(self, value: float = 1.0):
        self.value += value

    def dec(self, value: float = 1.0):
        self.value -= value


class MetricsCollector:
    def __init__(self) -> None:
        self._counters: dict[str, dict[tuple, Counter]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        self._histograms: dict[str, dict[tuple, Histogram]] = defaultdict(
            lambda: defaultdict(Histogram)
        )
        self._gauges: dict[str, dict[tuple, Gauge]] = defaultdict(
            lambda: defaultdict(Gauge)
        )
        self._lock = asyncio.Lock()

    def _make_labels_key(self, labels: dict[str, str]) -> tuple:
        return tuple(sorted(labels.items()))

    async def increment_counter(
        self, name: str, labels: dict[str, str] | None = None, value: int = 1
    ):
        labels = labels or {}
        key = self._make_labels_key(labels)
        async with self._lock:
            self._counters[name][key].add(value)

    async def record_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ):
        labels = labels or {}
        key = self._make_labels_key(labels)
        async with self._lock:
            self._histograms[name][key].record(value)

    async def set_gauge(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ):
        labels = labels or {}
        key = self._make_labels_key(labels)
        async with self._lock:
            self._gauges[name][key].set(value)

    async def inc_gauge(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ):
        labels = labels or {}
        key = self._make_labels_key(labels)
        async with self._lock:
            self._gauges[name][key].inc(value)

    async def dec_gauge(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ):
        labels = labels or {}
        key = self._make_labels_key(labels)
        async with self._lock:
            self._gauges[name][key].dec(value)

    async def get_metrics(self) -> dict[str, Any]:
        async with self._lock:
            result = {
                "counters": {},
                "histograms": {},
                "gauges": {},
            }

            for name, by_labels in self._counters.items():
                result["counters"][name] = {}
                for labels, counter in by_labels.items():
                    result["counters"][name][dict(labels)] = counter.value

            for name, by_labels in self._histograms.items():
                result["histograms"][name] = {}
                for labels, hist in by_labels.items():
                    result["histograms"][name][dict(labels)] = {
                        "count": hist.count,
                        "sum": round(hist.sum, 3),
                        "min": min(hist.values) if hist.values else 0,
                        "max": max(hist.values) if hist.values else 0,
                        **hist.percentiles(50, 90, 95, 99),
                    }

            for name, by_labels in self._gauges.items():
                result["gauges"][name] = {}
                for labels, gauge in by_labels.items():
                    result["gauges"][name][dict(labels)] = gauge.value

            return result

    async def export_prometheus(self) -> str:
        async with self._lock:
            lines = []

            for name, by_labels in self._counters.items():
                metric_name = f"lb_{name.replace('.', '_')}"
                for labels, counter in by_labels.items():
                    labels_str = (
                        ",".join(f'{k}="{v}"' for k, v in labels) if labels else ""
                    )
                    suffix = f"{{{labels_str}}}" if labels_str else ""
                    lines.append(f"{metric_name}_total{suffix} {counter.value}")

            for name, by_labels in self._histograms.items():
                metric_name = f"lb_{name.replace('.', '_')}"
                for labels, hist in by_labels.items():
                    labels_str = (
                        ",".join(f'{k}="{v}"' for k, v in labels) if labels else ""
                    )
                    suffix = f"{{{labels_str}}}" if labels_str else ""
                    if hist.count > 0:
                        lines.append(f"{metric_name}_sum{suffix} {round(hist.sum, 3)}")
                        lines.append(f"{metric_name}_count{suffix} {hist.count}")
                        for p, v in hist.percentiles(50, 90, 95, 99).items():
                            lines.append(f"{metric_name}_{p}{suffix} {v}")

            for name, by_labels in self._gauges.items():
                metric_name = f"lb_{name.replace('.', '_')}"
                for labels, gauge in by_labels.items():
                    labels_str = (
                        ",".join(f'{k}="{v}"' for k, v in labels) if labels else ""
                    )
                    suffix = f"{{{labels_str}}}" if labels_str else ""
                    lines.append(f"{metric_name}{suffix} {gauge.value}")

            return "\n".join(lines)

    async def reset(self):
        async with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._gauges.clear()
