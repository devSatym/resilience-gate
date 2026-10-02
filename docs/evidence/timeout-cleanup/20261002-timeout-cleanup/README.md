# Short-deadline timeout-and-cleanup direct boundary test — 2026-10-02

**Outcome:** `fail`.

This manually created direct Job ran the deployed staging gate runner with a
deliberately shortened one-second Workflow deadline and inert temporary load
source. It is not Kargo verification or a promotion. The runner created a
Workflow and run-scoped load Job, failed before its normal 90-second baseline
could reach a fault phase, then invoked exact-object cleanup.

A post-run check found no manual Job, temporary CronJob, Workflow, PodChaos,
scoped load Job, or Lease remaining.

Reviewed artifacts:

- [`run-metadata.json`](run-metadata.json) — schema-validated identity and
  `fail` status.
- [`gate.log`](gate.log) — sanitized timeout and cleanup output.

This is short-deadline cleanup evidence only. It is not default timeout
behavior, a naturally occurring Chaos Mesh timeout, injected faults/recovery,
real load/payment traffic, or Kargo verification.
