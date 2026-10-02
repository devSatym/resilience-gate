# Healthy chaos-run evidence

**Status: collected for one owned staging-testnet run.** This is a narrow
Kargo-managed staging chaos-gate result, not a production-like or general
release claim.

## Recorded pass

[`20261001-staging-gate-b8cc5caa`](20261001-staging-gate-b8cc5caa/) records
the successful staging AnalysisRun
`staging.01m3w93zc6ddewce35bzy8d2t4.5664b01`. Its gate Job created bounded
workflow `chaos-gate-fkh9p`, recorded all three dependency-failure scorecards
as `pass`, and logged cleanup of its workflow and run-scoped load Job.

The record binds the Kargo-selected source revision, rendered revision, and
immutable application, gate-runner, signer, and load-generator digests. It
includes the sanitized gate log and scorecards for PostgreSQL (6 checks), Redis
(7 checks), and signer (6 checks). Each scorecard records that its target was
observed unavailable and recovered within its bounded window.

This pass supports only that recorded staging identity and scenario. It does
not replace baseline evidence, a deliberately degraded pipeline regression,
or a production-like smoke test.
