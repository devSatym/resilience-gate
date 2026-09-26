# Baseline evidence status

**Status: not collected.** No Resilience Gate baseline has been run from this
workspace against an owned Kubernetes lab, Radius testnet, or production-like
environment. This directory intentionally contains no `run-metadata.json`,
load result, Prometheus export, or scorecard. Its presence is not a successful
baseline claim.

## What a future baseline must bind

One approved baseline run must use a new, unique run ID and record all of the
following before it can support a release claim:

- the full source revision, chart/configuration revision, and immutable
  application, signer, and gate-runner image digests actually selected;
- the owned target context and namespace, without credentials or Secret data;
- sanitized readiness and EndpointSlice observations made before traffic;
- a bounded load summary and the Prometheus query window used to assess it;
- the exact status returned by the run, plus every redaction category; and
- a cleanup record if the baseline starts temporary resources.

`run-metadata.json`, when collected, must conform to the shared
[`run-metadata` schema](../../../schemas/run-metadata.schema.json). A
repository render, unit-test result, or planned configuration is not a
substitute for any of these artifacts.

## Acceptance rule

A baseline may be labelled `pass` only when the recorded release identity is
complete, the target is demonstrably ready, the bounded traffic window is
present and interpretable, and no required evidence is absent, stale, or
redacted beyond review. Until those facts are recorded, the correct status is
not collected—not healthy.
