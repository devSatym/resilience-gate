# Baseline evidence status

**Status: passed on 2 October 2026.** Run `baseline-20261002-031523`
completed against the owned dev namespace. Its detailed sanitized bundle is
retained outside Git; the reviewed measurements are published in the
[verification report](../../verification-report.md).

## What the recorded baseline bound

The accepted run used a unique ID and recorded:

- the full source revision, chart/configuration revision, and immutable
  application, signer, and gate-runner image digests actually selected;
- the owned target context and namespace, without credentials or Secret data;
- sanitized readiness and EndpointSlice observations made before traffic;
- a bounded load summary and the Prometheus query window used to assess it;
- the exact status returned by the run, plus every redaction category; and
- a cleanup record if the baseline starts temporary resources.

Its `run-metadata.json` conforms to the shared
[`run-metadata` schema](../../../schemas/run-metadata.schema.json). A
repository render, unit-test result, or planned configuration is not a
substitute for any of these artifacts.

## Accepted result

The 91-second scorecard observed 44.89 meaningful requests, zero application
5xx responses, 95 ms p95 latency, and ready PostgreSQL and Redis signals. All
six checks passed. An earlier failed attempt remains separate and was not
overwritten. Future candidates return to not-collected status until they run a
fresh baseline.
