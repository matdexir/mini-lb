# Load Balancer

A simple HTTP load balancer built with aiohttp.

## Features

- Multiple scheduling algorithms:
  - Round Robin
  - Weighted Round Robin
  - Least Connections
- Backend management via REST API control endpoints
- Automatic health checks (checks every 5 seconds)

## Usage

```bash
# Install dependencies
uv sync

# Run the server (default port 8080)
python main.py

# Or specify a different port
python main.py --port 9000

# With custom log level and optional log file
python main.py --port 8080 --log-level DEBUG
python main.py --port 8080 --log-level INFO --log-file /var/log/lb.log

# Run tests
pytest

# Integration test script
bash scripts/test_lb.sh [num_backends] [num_requests] [lb_port]

# Examples:
bash scripts/test_lb.sh           # 3 backends, 1000 requests, port 8080
bash scripts/test_lb.sh 5 5000    # 5 backends, 5000 requests, port 8080
bash scripts/test_lb.sh 2 100 9000  # 2 backends, 100 requests, port 9000
```

## Control Endpoints

- `POST /_control/add` - Add a backend (`{"url": "http://localhost:8001", "weight": 1}`)
- `POST /_control/remove` - Remove a backend (`{"url": "http://localhost:8001"}`)
- `POST /_control/scheduler` - Set scheduler algorithm (`{"algorithm": "round_robin|weighted|least_conn"}`)
- `GET /_control/list` - List all backends (includes `healthy` status)
- `GET /_control/stats` - Get request distribution stats (optional `?periods=5m,30m,1h,6h,24h,all`)

## Example

```bash
# Add backends
curl -X POST http://localhost:8080/_control/add \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:8001"}'

curl -X POST http://localhost:8080/_control/add \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:8002", "weight": 2}'

# Set algorithm
curl -X POST http://localhost:8080/_control/scheduler \
  -H "Content-Type: application/json" \
  -d '{"algorithm": "weighted"}'

# List backends
curl http://localhost:8080/_control/list

# Get stats (all periods)
curl "http://localhost:8080/_control/stats"

# Get stats for specific periods
curl "http://localhost:8080/_control/stats?periods=5m,30m,all"

# Proxy requests
curl http://localhost:8080/
```
