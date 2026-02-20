from .scheduler import Scheduler, Backend
from itertools import cycle
import random


class RoundRobinScheduler(Scheduler):
    def __init__(self) -> None:
        self._cycle = None

    def select(self, backends: dict[str, Backend]):
        if not backends:
            return None
        if not self._cycle:
            self._cycle = cycle(backends.values())
        return next(self._cycle)


class WeightedRoundRobinScheduler(Scheduler):
    def select(self, backends: dict[str, Backend]):
        if not backends:
            return None

        weighted = []

        for backend in backends.values():
            weighted.extend([backend] * backend.weight)

        return random.choice(weighted)


class LeastConnectionsScheduler(Scheduler):
    def select(self, backends: dict[str, Backend]):
        if not backends:
            return None
        return min(backends.values(), key=lambda b: b.active_connections)
