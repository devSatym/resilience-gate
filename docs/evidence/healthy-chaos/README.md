# Healthy chaos-run evidence status

**Status: not collected.** There is no recorded passing chaos run for
Resilience Gate. No cloud, Kubernetes, or Radius testnet operation was run to
create this directory, and no release may cite it as evidence that chaos
verification passed.

## Required record for a future pass

A single bounded chaos-gate run must bind one run ID to the exact source
revision, chart/configuration revision, workload digest, signer digest, and
gate-runner digest under test. The submitted evidence must include:

- sanitized run metadata and target/context identity;
- a pre-fault readiness and traffic baseline;
- the bounded workflow result and fault timestamps for every configured
  experiment;
- scorecards for the PostgreSQL, Redis, and signer experiments, each carrying
  the same run ID and immutable workload digest;
- load and telemetry artifacts sufficient to review every scoring input; and
- cleanup logs that show the run-scoped workflow, load job, and lease were
  checked absent after completion.

The scorer is deliberately fail-closed: missing, malformed, non-finite,
insufficient, or stale telemetry is a failed evidence condition, not a zero or
a pass. A workflow exit alone is therefore not enough to establish a healthy
chaos result.

## What is absent now

There are currently no run metadata, scorecards, workflow statuses, Prometheus
responses, load summaries, or cleanup observations in this directory. A later
approved lab execution must add a new run-specific record rather than replacing
this status page or backfilling a claimed result.
