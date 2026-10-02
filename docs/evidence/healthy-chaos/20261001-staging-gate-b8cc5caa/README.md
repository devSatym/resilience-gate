# Staging chaos-gate pass — 2026-10-01

**Outcome:** `pass` for the recorded Kargo staging chaos-gate verification.

The record is bound to AnalysisRun
`staging.01m3w93zc6ddewce35bzy8d2t4.5664b01`, gate Job
`d4371b40-f8cb-4b93-a8eb-007f416aa0bb.chaos-verdict.1`, and workflow
`chaos-gate-fkh9p`. The gate log records PostgreSQL, Redis, and signer
experiments, a `PASS` verdict, and cleanup of its workflow and run-scoped load
Job.

All three scorecards are `pass`: PostgreSQL has 6 checks, Redis has 7, and
signer has 6. Each binds the same immutable release revision and image digest
as this run's metadata.

Reviewed artifacts:

- [`run-metadata.json`](run-metadata.json) — schema-validated staging identity
  and selected immutable revisions/digests.
- [`gate.log`](gate.log) — sanitized gate output and cleanup record.
- [`scorecards/`](scorecards/) — per-experiment, fail-closed scoring results.

This is scoped staging-testnet evidence only. It is not a baseline,
regression-path, production-like smoke, mainnet, or general release claim.
