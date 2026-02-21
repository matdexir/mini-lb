from dataclasses import dataclass


@dataclass
class Backend:
    url: str
    weight: int = 1
    active_connections: int = 0
    healthy: bool = True
    total_requests: int = 0
