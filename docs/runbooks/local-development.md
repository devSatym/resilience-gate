# Local development and recovery checks

## Prerequisites

- Python 3.12
- Docker with Compose
- `curl`

Install the locked test tools and run the ordinary suite:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHON=.venv/bin/python make validate
```

Run `make smoke-local` to build the app, start Postgres and Redis, create a
short URL, validate its redirect header, stop Redis, verify `/livez` and
steady-state `/ready`, then start Redis again. The script always tears down the
Compose project and volumes.

## Expected health semantics

- `/livez` only proves the process is running; it never queries a dependency.
- `/ready` requires Postgres throughout the pod lifetime.
- Redis is required for the first successful readiness check only. After that,
  Redis loss must fall back to Postgres rather than trigger a restart loop.

If `/ready` remains unavailable, inspect `docker compose logs app postgres
redis`, correct the local configuration, and rerun the smoke test. Do not treat
a local smoke result as chaos-gate or release evidence.
