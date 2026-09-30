# Resilience Gate — Chaos-Verified Kubernetes Release Platform

Resilience Gate is a testnet-only reference platform for a Kubernetes workload
that is designed to advance through a release path only after bounded,
measured dependency-failure checks. It combines a FastAPI URL shortener, an
isolated Permit2 signer, digest-oriented delivery configuration, GitOps,
observability, and a fail-closed chaos-gate design.

## Verification status

The repository contains implementation and configuration contracts plus
credential-free/local validation paths. It does **not** contain a recorded
cloud deployment, Kubernetes reconciliation, Radius testnet payment,
chaos-gate result, recovery exercise, or production-like smoke result.

Accordingly:

- this is **not** an evidence-backed v1.0 release;
- no image, signature, rendered branch, or dashboard in the repository is
  proof of a live promotion; and
- empty evidence directories mean *not collected*, never *passed*.

Any future verified claim must identify the exact source revision, rendered
revision, workload digest, relevant signer/gate-runner digests, target scope,
sanitized observations, and cleanup result. See
[evidence handling](docs/evidence/README.md).

## What the source is designed to demonstrate

- A FastAPI URL shortener with separate process liveness, dependency readiness,
  Prometheus metrics, cache fallback, and x402 v2 payment handling.
- A separate Permit2-signing service that keeps private keys outside the
  application and load client boundary.
- Helm workload configuration that accepts testnet-only payment settings,
  external secret references, hardened pod defaults, and immutable image
  digests.
- Kargo/Argo CD configuration for digest-bound rendered environment branches:
  automatic development policy and manual staging/production-like transitions.
- A bounded staging chaos-gate design that rejects missing targets, competing
  runs, invalid telemetry, and unverified cleanup rather than reporting a
  false pass.
- Pinned Prometheus, Loki, and Alloy chart configuration, dashboards, and
  ServiceMonitor contracts for a small testnet lab.

These are source-level statements. Their operational behavior still needs an
approved owned-lab execution and sanitized evidence.

## Reproduce the offline checks

Prerequisites for the broad local validation path are Python 3.12, Docker
Compose, Helm, Terraform, and `kubectl` with Kustomize support. None of the
commands below needs cloud credentials or contacts a Kubernetes cluster.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -r signer/requirements.lock

# Hermetic/default tests. Integration and live markers remain excluded.
PYTHON=.venv/bin/python make test

# Shell, Helm, Terraform, Kustomize, and test validation.
PYTHON=.venv/bin/python make validate

# Optional local Compose smoke: Postgres + Redis + unpaid URL shortening.
make smoke-local
```

`make validate` may download pinned Helm/Terraform dependencies when they are
not cached, but it is a local render/validation path; it does not apply
Terraform, invoke bootstrap, or mutate a cluster. `make smoke-local` is also
not a payment, chaos, promotion, or release test.

For an ordered walk-through of those boundaries, see
[the reproducible demo](docs/demo-walkthrough.md).

## Configuration and safety boundaries

Platform bootstrap uses ignored local public configuration rather than committed
account or repository identity:

```bash
cp platform_setup_scripts/config.env.example platform_setup_scripts/config.env
# Fill public identifiers locally, then render only for review.
./platform_setup_scripts/bootstrap.sh --render-config
```

Rendering writes reviewable manifests and may change the working tree. Review
that diff before any later bootstrap step. Do not place secret values, wallet
keys, authorization headers, or a target context credential in Git. Bootstrap
and live testnet operations are intentionally outside the offline demo and
require separate operator authorization.

## Repository map

- `app/` — URL-shortener service and x402 protocol handling.
- `signer/` — isolated Permit2 authorization service.
- `helm/` — workload and observability chart configuration.
- `kubernetes/` — GitOps, Kargo, and bounded-chaos manifest contracts.
- `gke_terraform/` — configurable GCP foundation; no state is included here.
- `platform_setup_scripts/` — guarded, operator-driven bootstrap phases.
- `docs/` — architecture, contracts, limitations, runbooks, and sanitized
  evidence status.

Read [the architecture](docs/kubernetes-architecture.md),
[known limitations](docs/known-limitations.md), and
[the changelog](CHANGELOG.md) before treating a source configuration as an
operational claim.
