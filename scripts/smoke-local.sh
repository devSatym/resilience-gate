#!/usr/bin/env bash
# Exercise the Compose stack end to end. Requires Docker and curl.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

cleanup() {
  docker compose down --volumes --remove-orphans
}
trap cleanup EXIT

docker compose up --build --detach

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error http://localhost:8000/ready >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "local app did not become ready" >&2
    exit 1
  fi
  sleep 2
done

created=$(curl --fail --silent --show-error \
  --header 'content-type: application/json' \
  --data '{"url":"https://example.test/smoke"}' \
  http://localhost:8000/shorten)
code=$(printf '%s' "$created" | python3 -c 'import json,sys; print(json.load(sys.stdin)["code"])')
redirect_headers=$(curl --silent --show-error --dump-header - --output /dev/null \
  "http://localhost:8000/$code")
printf '%s\n' "$redirect_headers" | grep --quiet --ignore-case \
  '^location: https://example\.test/smoke'

# Redis is an optimisation after initial readiness. Its temporary loss must
# preserve process liveness and steady-state readiness while URL resolution
# falls back to Postgres.
docker compose stop redis
curl --fail --silent --show-error http://localhost:8000/livez >/dev/null
curl --fail --silent --show-error http://localhost:8000/ready >/dev/null
docker compose start redis

echo "local smoke test passed"
