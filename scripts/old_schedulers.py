"""Old scheduler implementations for comparison."""

import os
import sys
import random

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scheduler import Backend


class OldRoundRobinScheduler:
    def __init__(self):
        self._cycle = None

    def select(self, backends: dict[str, Backend]):
        if not backends:
            return None
        if not self._cycle:
            from itertools import cycle

            self._cycle = cycle(backends.values())
        return next(self._cycle)


class OldWeightedRoundRobinScheduler:
    def select(self, backends: dict[str, Backend]):
        if not backends:
            return None
        weighted = []
        for backend in backends.values():
            weighted.extend([backend] * backend.weight)
        return random.choice(weighted)


class OldLeastConnectionsScheduler:
    def select(self, backends: dict[str, Backend]):
        if not backends:
            return None
        return min(backends.values(), key=lambda b: b.active_connections)
