#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

NUM_BACKENDS=${1:-3}
NUM_REQUESTS=${2:-1000}
LB_PORT=${3:-8080}

START_PORT=8001

cleanup() {
    echo "Cleaning up..."
    pkill -f "fake_server.py" 2>/dev/null || true
    pkill -f "main.py" 2>/dev/null || true
    exit 0
}
trap cleanup EXIT INT TERM

echo "Starting $NUM_BACKENDS fake backend servers..."
for ((i=0; i<NUM_BACKENDS; i++)); do
    port=$((START_PORT + i))
    python scripts/fake_server.py "$port" &
done

sleep 1

echo "Starting load balancer on port $LB_PORT..."
python main.py --port $LB_PORT &
sleep 3

echo "Adding backends..."
for ((i=0; i<NUM_BACKENDS; i++)); do
    port=$((START_PORT + i))
    curl -s -X POST "http://localhost:$LB_PORT/_control/add" \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"http://localhost:$port\", \"weight\": 1}" > /dev/null || {
        echo "Failed to add backend localhost:$port"
        exit 1
    }
done

echo "Running $NUM_REQUESTS requests..."
python -c "
import urllib.request

counts = {}
for i in range($NUM_REQUESTS):
    try:
        resp = urllib.request.urlopen('http://localhost:$LB_PORT/')
        body = resp.read().decode()
        counts[body] = counts.get(body, 0) + 1
    except:
        pass

print()
print('Results:')
print('========')
for i in range($NUM_BACKENDS):
    port = $START_PORT + i
    print(f'Port {port}: {counts.get(str(port), 0)} requests')

total = sum(counts.values())
print()
print(f'Total: {total} / $NUM_REQUESTS requests')
"
