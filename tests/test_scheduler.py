import pytest
from core.scheduler import Backend
from core.scheduler_impl import (
    RoundRobinScheduler,
    WeightedRoundRobinScheduler,
    LeastConnectionsScheduler,
)


class TestRoundRobinScheduler:
    def test_empty_backends(self):
        scheduler = RoundRobinScheduler()
        result = scheduler.select({})
        assert result is None

    def test_single_backend(self):
        scheduler = RoundRobinScheduler()
        backends = {"http://localhost:8001": Backend("http://localhost:8001")}
        result = scheduler.select(backends)
        assert result is not None
        assert result.url == "http://localhost:8001"

    def test_cycles_through_backends(self):
        scheduler = RoundRobinScheduler()
        backends = {
            "b1": Backend("b1"),
            "b2": Backend("b2"),
            "b3": Backend("b3"),
        }
        results = []
        for _ in range(6):
            result = scheduler.select(backends)
            assert result is not None
            results.append(result.url)
        assert results == ["b1", "b2", "b3", "b1", "b2", "b3"]


class TestWeightedRoundRobinScheduler:
    def test_empty_backends(self):
        scheduler = WeightedRoundRobinScheduler()
        result = scheduler.select({})
        assert result is None

    def test_single_backend(self):
        scheduler = WeightedRoundRobinScheduler()
        backends = {"http://localhost:8001": Backend("http://localhost:8001", weight=1)}
        result = scheduler.select(backends)
        assert result is not None

    def test_weight_respected(self):
        scheduler = WeightedRoundRobinScheduler()
        b1 = Backend("b1", weight=1)
        b2 = Backend("b2", weight=3)
        backends = {"b1": b1, "b2": b2}
        results = []
        for _ in range(20):
            result = scheduler.select(backends)
            assert result is not None
            results.append(result.url)
        assert results.count("b2") > results.count("b1")


class TestLeastConnectionsScheduler:
    def test_empty_backends(self):
        scheduler = LeastConnectionsScheduler()
        result = scheduler.select({})
        assert result is None

    def test_selects_least_connections(self):
        scheduler = LeastConnectionsScheduler()
        backends = {
            "b1": Backend("b1", active_connections=5),
            "b2": Backend("b2", active_connections=1),
            "b3": Backend("b3", active_connections=3),
        }
        result = scheduler.select(backends)
        assert result is not None
        assert result.url == "b2"

    def test_tiebreaker(self):
        scheduler = LeastConnectionsScheduler()
        backends = {
            "b1": Backend("b1", active_connections=1),
            "b2": Backend("b2", active_connections=1),
        }
        result = scheduler.select(backends)
        assert result is not None
