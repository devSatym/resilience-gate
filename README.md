# Resilience Gate — Chaos-Verified Kubernetes Release Platform

Resilience Gate is a testnet-only reference platform for releasing a Kubernetes
workload only after it has survived measured, bounded dependency failures.

This repository is being rebuilt as a clean, auditable implementation. Its
private local planning material is intentionally excluded from Git; the public
history itself remains the reviewable record of why each change was made.
Implementation proceeds deliberately: local behavior, health, payments,
infrastructure, delivery, observability, promotion, chaos, scoring, and
release evidence are introduced in that order.

## Status

The initial history establishes project governance only. It does **not** claim
that a cloud environment, payment flow, chaos gate, or production-like release
has been validated. Each later milestone must carry executable tests and
evidence appropriate to its scope.

## Principles

- Keep deployment identities and secrets out of source control.
- Treat rendered environment branches as machine-owned outputs, never as a
  source of truth to merge back into `main`.
- Fail closed when release evidence is absent, stale, malformed, or ambiguous.
- Keep the portfolio environment on testnet; live evidence must be collected
  only from an owned lab.
- Use small Conventional Commits and reviewable short-lived branches.

## Repository map

- `app/` — FastAPI URL-shortener workload.
- `signer/` — isolated Permit2 signing service.
- `helm/` and `kubernetes/` — workload, observability, GitOps, and chaos
  definitions.
- `gke_terraform/` — configurable GCP foundation.
- `platform_setup_scripts/` — guarded bootstrap and lab operations.
- `docs/` — contracts, runbooks, architecture, and verifiable evidence.

The tracked contribution policy defines the ongoing delivery discipline.

## Local development

The first milestone is a local, unpaid URL-shortener. Use Python 3.12 and the
locked development dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHON=.venv/bin/python make validate
```

To exercise real Postgres and Redis locally, run `make smoke-local`. This is a
local functional check only; it is not payment, chaos, or release evidence.
