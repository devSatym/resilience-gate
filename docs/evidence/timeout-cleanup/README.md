# Short-deadline timeout-and-cleanup evidence

**Status: collected as a manual direct staging boundary test.** This was not a
Kargo verification, Freight promotion, or release approval, and it did not use
the normal gate timeout.

[`20261002-timeout-cleanup`](20261002-timeout-cleanup/) ran the deployed gate
runner with a deliberately shortened one-second Workflow deadline and an inert
temporary load source. It created its Workflow and run-scoped load Job, failed
before the normal 90-second baseline could reach any fault phase, then invoked
exact-object cleanup. The log records `FAIL` and cleanup; a post-run check
found no manual Job, temporary CronJob, Workflow, PodChaos, scoped load Job, or
Lease remaining.

This proves only the short-deadline cleanup path. It is not evidence of the
default timeout behavior, a naturally occurring Chaos Mesh timeout, injected
faults/recovery/scoring, real load/payment traffic, or Kargo verification.
