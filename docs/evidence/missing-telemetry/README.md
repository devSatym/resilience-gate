# Missing-telemetry evidence status

**Status: not collected.** No live Prometheus outage, empty query result, or
stale-series condition has been exercised in an owned lab from this workspace.

## Expected safety behavior to verify

The scorer's contract is fail-closed: an empty series, malformed response,
non-finite value, insufficient range coverage, or stale sample must prevent a
passing verdict. A future exercise must retain the sanitized query result or
error, the query window and expression, the affected release/run identity, and
the final blocked or failed result.

The absence of telemetry must never be converted to a numeric zero, a quiet
dashboard, or a success assertion. This page documents the test case; it is
not evidence that the test case has run.
