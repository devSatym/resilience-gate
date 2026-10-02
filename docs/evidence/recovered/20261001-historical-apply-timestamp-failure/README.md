# Historical failed predecessor — 2026-10-01

**Outcome:** `fail`.

This retained predecessor is bound to AnalysisRun
`staging.01m3w75z7m23m5jjefxxwg05e9.5664b01` and gate Job
`7caf8b2e-c494-42a3-bcbc-48833f9573cb.chaos-verdict.1`. Its runner could not
obtain the workflow timestamps required to score PostgreSQL, Redis, and signer,
then recorded a failed verdict and run-scoped cleanup.

The failure is preserved to make the later
[fresh re-verification](../20261002-staging-recovery-fc2ef08d/) reviewable. It
is not a passing release result.

Reviewed artifacts:

- [`run-metadata.json`](run-metadata.json) — schema-validated identity; this
  predecessor used the earlier gate-runner digest.
- [`gate.log`](gate.log) — sanitized failure and cleanup output.
