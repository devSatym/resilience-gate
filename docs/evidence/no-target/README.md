# No-target evidence status

**Status: not collected.** No approved lab run has tested the case where the
target Service has no ready EndpointSlice endpoint.

## Expected safety behavior to verify

The gate should inspect the selected target before it creates a fault workflow.
If it cannot find a ready endpoint, it must stop with a clear blocked or failed
outcome and must not inject a fault into an ambiguous target. A future record
needs the sanitized EndpointSlice observation, selected namespace/service,
release identity, gate output, and cleanup verification.

This directory contains no such observation today. It is a collection contract,
not proof that target selection has been exercised live.
