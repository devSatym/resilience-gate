# No-target boundary evidence

**Status: collected as a manual direct staging boundary test.** This was not a
Kargo verification, Freight promotion, or release approval.

[`20261002-no-target-neg-notarget`](20261002-no-target-neg-notarget/) ran the
deployed gate runner against intentionally nonexistent Service
`rg-negative-no-target`. The runner acquired its Lease, found no ready
EndpointSlice address, and blocked with a refusal to inject a vacuous fault;
the log then records Lease cleanup.

This demonstrates the direct runner's target preflight for the supplied
service. It does not claim a pipeline block, fault injection, traffic,
telemetry scoring, payment behavior, or production behavior.
