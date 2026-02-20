import pytest
from core.scheduler import Backend
from core.scheduler_impl import (
    RoundRobinScheduler,
    WeightedRoundRobinScheduler,
    LeastConnectionsScheduler,
)


def iter_n(scheduler, n):
    """Take first n items from an iterator."""
    result = []
    it = iter(scheduler)
    for _ in range(n):
        try:
            result.append(next(it))
        except StopIteration:
            break
    return result


class TestRoundRobinScheduler:
    def test_empty_backends(self):
        scheduler = RoundRobinScheduler()
        scheduler.set_backends([])
        result = iter_n(scheduler, 3)
        assert result == []

    def test_single_backend(self):
        scheduler = RoundRobinScheduler()
        scheduler.set_backends([Backend("b1")])
        result = iter_n(scheduler, 1)
        assert len(result) == 1
        assert result[0].url == "b1"

    def test_cycles_through_backends(self):
        scheduler = RoundRobinScheduler()
        scheduler.set_backends([Backend("b1"), Backend("b2"), Backend("b3")])
        results = iter_n(scheduler, 6)
        assert [b.url for b in results] == ["b1", "b2", "b3", "b1", "b2", "b3"]


class TestWeightedRoundRobinScheduler:
    def test_empty_backends(self):
        scheduler = WeightedRoundRobinScheduler()
        scheduler.set_backends([])
        result = iter_n(scheduler, 3)
        assert result == []

    def test_single_backend(self):
        scheduler = WeightedRoundRobinScheduler()
        scheduler.set_backends([Backend("b1", weight=1)])
        result = iter_n(scheduler, 1)
        assert len(result) == 1

    def test_weight_respected(self):
        scheduler = WeightedRoundRobinScheduler()
        scheduler.set_backends([Backend("b1", weight=1), Backend("b2", weight=3)])
        results = iter_n(scheduler, 8)
        b2_count = sum(1 for b in results if b.url == "b2")
        b1_count = sum(1 for b in results if b.url == "b1")
        assert b2_count > b1_count

    def test_deterministic_cycle(self):
        scheduler = WeightedRoundRobinScheduler()
        scheduler.set_backends([Backend("b1", weight=2), Backend("b2", weight=1)])
        results = iter_n(scheduler, 6)
        assert [b.url for b in results] == ["b1", "b1", "b2", "b1", "b1", "b2"]


class TestLeastConnectionsScheduler:
    def test_empty_backends(self):
        scheduler = LeastConnectionsScheduler()
        scheduler.set_backends([])
        result = iter_n(scheduler, 3)
        assert result == []

    def test_selects_least_connections(self):
        scheduler = LeastConnectionsScheduler()
        b1 = Backend("b1", active_connections=5)
        b2 = Backend("b2", active_connections=1)
        b3 = Backend("b3", active_connections=3)
        scheduler.set_backends([b1, b2, b3])
        result = iter_n(scheduler, 1)
        assert len(result) == 1
        assert result[0].url == "b2"
