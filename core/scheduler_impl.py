import heapq
from core.scheduler import Backend


class RoundRobinScheduler:
    def __init__(self, backends: list[Backend] | None = None):
        self._backends = backends or []

    def set_backends(self, backends: list[Backend]):
        self._backends = list(backends)

    def __iter__(self):
        if not self._backends:
            return
        while True:
            for backend in self._backends:
                yield backend


class WeightedRoundRobinScheduler:
    def __init__(self, backends: list[Backend] | None = None):
        self._backends = backends or []
        self._weighted: list[Backend] = []

    def set_backends(self, backends: list[Backend]):
        self._backends = list(backends)
        self._weighted = []
        for backend in backends:
            self._weighted.extend([backend] * backend.weight)

    def __iter__(self):
        if not self._weighted:
            return
        while True:
            yield from self._weighted


class LeastConnectionsScheduler:
    def __init__(self, backends: list[Backend] | None = None):
        self._backends = {b.url: b for b in (backends or [])}

    def set_backends(self, backends: list[Backend]):
        self._backends = {b.url: b for b in backends}

    def __iter__(self):
        if not self._backends:
            return
        while True:
            heap = [(b.active_connections, url) for url, b in self._backends.items()]
            heapq.heapify(heap)
            _, url = heap[0]
            yield self._backends[url]


class WeightedLeastConnectionsScheduler:
    def __init__(self, backends: list[Backend] | None = None):
        self._backends = {b.url: b for b in (backends or [])}

    def set_backends(self, backends: list[Backend]):
        self._backends = {b.url: b for b in backends}

    def __iter__(self):
        if not self._backends:
            return
        while True:
            heap = []
            for url, b in self._backends.items():
                if b.weight > 0:
                    ratio = b.active_connections / b.weight
                    heap.append((ratio, url))
            if not heap:
                return
            heapq.heapify(heap)
            _, url = heap[0]
            yield self._backends[url]


class LeastRequestsScheduler:
    def __init__(self, backends: list[Backend] | None = None):
        self._backends = {b.url: b for b in (backends or [])}

    def set_backends(self, backends: list[Backend]):
        self._backends = {b.url: b for b in backends}

    def __iter__(self):
        if not self._backends:
            return
        while True:
            heap = [(b.total_requests, url) for url, b in self._backends.items()]
            heapq.heapify(heap)
            _, url = heap[0]
            yield self._backends[url]
