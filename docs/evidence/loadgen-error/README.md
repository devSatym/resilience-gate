# Load-generation error evidence status

**Status: not collected.** No live load-generator startup or runtime failure
has been induced or captured for Resilience Gate.

## Expected safety behavior to verify

Before chaos begins, a future run must show that its bounded load job started
and produced usable traffic. If the job cannot start, exits unexpectedly, or
does not yield the required traffic, the gate must block rather than score a
quiet system as healthy. The evidence should include the job identity, sanitized
status/log extract, release identity, gate outcome, and verified cleanup.

A local unit test or a rendered CronJob does not establish this behavior in a
cluster. Until a reviewed lab run is recorded, no load-generation resilience
claim is supported here.
