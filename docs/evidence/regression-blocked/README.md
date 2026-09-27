# Regression-blocked evidence status

**Status: not collected.** No intentionally degraded candidate has been
deployed or evaluated from this workspace. This directory does not prove that
the promotion gate rejected a regression.

## Future negative-test record

An approved regression exercise should identify the deliberately degraded
candidate by source revision and immutable digest, state the reviewed reason it
is expected to be rejected, and preserve the gate result, relevant scorecards,
sanitized telemetry, and run-scoped cleanup record. Its outcome must be
recorded as `fail` or `blocked` as applicable; a blocked regression is useful
negative evidence only when the blocking reason is explicit and reviewable.

Do not label a manually patched workload, a mutable tag, or a locally rendered
overlay as a verified pipeline regression. It must travel through the intended
testnet verification path before it can support that claim.
