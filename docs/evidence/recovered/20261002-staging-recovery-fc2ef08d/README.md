# Staging re-verification pass — 2026-10-02

**Outcome:** `pass` for a fresh Kargo staging re-verification.

This run follows the retained
[failed predecessor](../20261001-historical-apply-timestamp-failure/) and is
bound to AnalysisRun `staging.01m3x2psvxxngj38j0gnkch5rv.5664b01`, gate Job
`e1f39b47-8433-49bd-a05c-d0f469750568.chaos-verdict.1`, and workflow
`chaos-gate-2gfdx`. It uses the same recorded source/render/application identity
as the predecessor with the corrected gate-runner digest.

The gate log records PostgreSQL, Redis, and signer fault/recovery scorecards,
a `PASS` verdict, and cleanup of the workflow and run-scoped load Job. All three
scorecards pass: PostgreSQL has 6 checks, Redis 7, and signer 6.

Reviewed artifacts:

- [`run-metadata.json`](run-metadata.json) — schema-validated run and immutable
  identity.
- [`gate.log`](gate.log) — sanitized gate output and cleanup record.
- [`scorecards/`](scorecards/) — per-experiment scoring results.

This demonstrates corrected gate behavior for the exact staging candidate; it
does not establish a new candidate, a production-like promotion, or a full
release.
