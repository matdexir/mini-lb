# AGENTS.md - Developer Guidelines

This file provides guidelines for agents working on this codebase.

## Project Overview

A simple HTTP load balancer built with aiohttp. It supports multiple scheduling algorithms (Round Robin, Weighted Round Robin, Least Connections) and includes automatic health checks.

## Development Commands

### Setup
```bash
# Install all dependencies (including dev)
uv sync

# Install only runtime dependencies
uv sync --no-dev
```

### Running the Application
```bash
# Run with default port (8080)
python main.py

# Run with custom port
python main.py --port 9000

# Or using module syntax
python -m main --port 8080

# With custom log level (DEBUG, INFO, WARNING, ERROR) and optional log file
python main.py --port 8080 --log-level DEBUG
python main.py --port 8080 --log-level INFO --log-file /var/log/lb.log
```

### Testing
```bash
# Run all tests
pytest

# Run all tests with verbose output
pytest -v

# Run a single test file
pytest tests/test_scheduler.py

# Run a single test class
pytest tests/test_scheduler.py::TestRoundRobinScheduler

# Run a single test
pytest tests/test_scheduler.py::TestRoundRobinScheduler::test_single_backend

# Run tests matching a pattern
pytest -k "test_empty"
```

### Code Quality
```bash
# Syntax check all Python files
python -m py_compile main.py backend_pool.py core/*.py tests/*.py

# Check imports are valid
python -c "from main import *"
```

## Code Style Guidelines

### General Principles
- Python 3.14+ required
- Use async/await for I/O-bound operations (aiohttp)
- Keep functions focused and small
- Use descriptive variable names

### Imports
- Standard library first, then third-party, then local
- Use explicit relative imports within packages (`from .module import ...`)
- Avoid wildcard imports (`from module import *`)
- Group: stdlib, third-party, local, blank line between groups

```python
# Correct
import asyncio
import logging
import aiohttp
from aiohttp import ClientSession, web
from core import Scheduler, Backend

# Wrong
from core import *
import asyncio, aiohttp, logging
```

### Type Hints
- Always use type hints for function arguments and return types
- Use Python 3.14+ union syntax (`X | None`) over `Optional[X]`
- Use `dict[str, T]` over `Dict[str, T]`

```python
# Correct
async def select_backend(self) -> Backend | None:
    pass

def __init__(self, health_check_interval: float = 5.0) -> None:
    pass

# Avoid
async def select_backend(self):
    pass
```

### Naming Conventions
- Classes: `PascalCase` (e.g., `BackendPool`, `RoundRobinScheduler`)
- Functions/methods: `snake_case` (e.g., `select_backend`, `add_backend`)
- Private methods: prefix with underscore (e.g., `_health_check`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_PORT`)
- Variables: `snake_case` (e.g., `backend_pool`, `active_connections`)

### Dataclasses
Use `@dataclass` for simple data containers:

```python
from dataclasses import dataclass

@dataclass
class Backend:
    url: str
    weight: int = 1
    active_connections: int = 0
    healthy: bool = True
```

### Iterator-Based Schedulers
Schedulers implement the iterator protocol - they are infinite iterators that yield backends:

```python
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
```

- Each scheduler is an infinite iterator
- Use `set_backends()` to update the backend list
- BackendPool creates/resets the iterator when backends change
- Handle empty backends by returning early (not infinite loop)

### Async Patterns
- Always use `async def` for async functions
- Use `asyncio.Lock()` for thread-safe operations
- Properly handle task cancellation:

```python
async def stop_health_checks(self):
    if self._health_check_task:
        self._health_check_task.cancel()
        try:
            await self._health_check_task
        except asyncio.CancelledError:
            pass
```

- Create sessions (ClientSession) within the async context where needed
- Always close sessions in finally blocks

### Error Handling
- Use specific exception types when possible
- Return appropriate HTTP status codes in web handlers
- Use the logging module for error logging:

```python
import logging
logger = logging.getLogger(__name__)

# Web handler error handling
try:
    async with client_session.request(...) as resp:
        body = await resp.read()
        return web.Response(body=body, status=resp.status, headers=resp.headers)
except Exception as e:
    logger.error(f"Proxy error for {backend.url}: {e}")
    return web.Response(text=str(e), status=502)
```

### Match Statements
Use pattern matching for enum-like logic:

```python
async def set_scheduler(self, algo: str):
    match algo:
        case "round_robin":
            self.scheduler = RoundRobinScheduler()
        case "weighted":
            self.scheduler = WeightedRoundRobinScheduler()
        case "least_conn":
            self.scheduler = LeastConnectionsScheduler()
        case _:
            raise ValueError(f"unknown scheduling algo: {algo}")
```

### Testing
- Use pytest with class-based test organization
- Test classes should inherit from nothing (just plain classes)
- Use descriptive test names: `test_<what_is_being_tested>`
- Always handle None cases in tests:

```python
def test_single_backend(self):
    scheduler = RoundRobinScheduler()
    backends = {"url": Backend("url")}
    result = scheduler.select(backends)
    assert result is not None  # Always check for None first
    assert result.url == "url"
```

### Logging
The project uses Python's standard `logging` module:

```python
import logging

logger = logging.getLogger(__name__)

# Log levels: DEBUG, INFO, WARNING, ERROR
logger.info(f"Load balancer running on http://127.0.0.1:{port}")
logger.warning(f"Health check failed: {backend.url}")
logger.error(f"Proxy error for {backend.url}: {e}")
```

CLI options for logging:
- `--log-level`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `--log-file`: Optional file path for logging (logs to stderr by default)
- 4-space indentation (no tabs)
- Maximum line length: 88 characters (ruff default)
- Use blank lines sparingly to separate logical sections
- Use f-strings for string formatting:

```python
print(f"Load balancer running on http://127.0.0.1:{port}")
```

### File Structure
```
lb/
├── main.py                 # Entry point, web server setup
├── backend_pool.py        # Backend management logic
├── core/
│   ├── __init__.py       # Exports
│   ├── scheduler.py      # Abstract Scheduler, Backend dataclass
│   └── scheduler_impl.py # Scheduler implementations
├── tests/
│   └── test_scheduler.py # Unit tests
├── scripts/
│   ├── test_lb.sh       # Integration test script
│   └── fake_server.py   # Helper for testing
├── pyproject.toml       # Project configuration
├── README.md            # User documentation
├── LICENSE              # MIT License
└── AGENTS.md           # Developer guidelines for agents
```

### Control Endpoints
The load balancer exposes these control endpoints:
- `POST /_control/add` - Add backend (`{"url": "...", "weight": 1}`)
- `POST /_control/remove` - Remove backend (`{"url": "..."}`)
- `POST /_control/scheduler` - Set algorithm (`{"algorithm": "round_robin|weighted|least_conn"}`)
- `GET /_control/list` - List backends with health status
- `GET /_control/stats` - Get request distribution stats (`?periods=5m,30m,1h,6h,24h,all`)

## Common Tasks

### Adding a New Scheduler
1. Create class in `core/scheduler_impl.py` inheriting from `Scheduler`
2. Implement `select()` method
3. Add import to `core/__init__.py`
4. Add case in `backend_pool.py::set_scheduler()`
5. Add tests in `tests/test_scheduler.py`

### Adding a New Control Endpoint
1. Define async handler in `main.py`
2. Register with `app.router.add_post()` or `add_get()`
3. Test with curl
