from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Backend:
    url: str
    weight: int = 1
    active_connections: int = 0
    healthy: bool = True


class Scheduler(ABC):
    @abstractmethod
    def select(self, backends: dict[str, Backend]) -> Backend | None:
        pass
