# Telemetry-transport boundary evidence

**Status: collected as a scorer-only manual direct staging test.** This was not
a Kargo verification, Freight promotion, full chaos-gate run, or release
approval.

[`20261002-missing-telemetry-scorer`](20261002-missing-telemetry-scorer/) ran
the PostgreSQL scorer against deliberately unreachable loopback endpoint
`http://127.0.0.1:1`. Five telemetry-dependent checks emitted
`query_transport_error` / connection-refused failures; the immutable release
identity check passed, and the final scorecard verdict was `fail`.

It proves that the scorer fails closed for this supplied transport failure. It
does not simulate an outage of shared Prometheus, establish a real cluster
telemetry gap, exercise a Workflow/load/fault/cleanup path, or reject a
promotion.
