# Regression-blocked evidence status

**Status: collected as an expected failure on 2 October 2026.** A
pipeline-produced deliberately degraded candidate entered the staging
verification path and failed before fault injection because it could not prove
paid traffic within the configured 75-second startup window.

## Recorded negative-test result

Run `regression-blocked-20261002-050844` identifies the degraded source and
rendered revision, Kargo AnalysisRun, gate Job/Pod, sanitized gate log, and
cleanup. The gate acquired its Lease and created the load Job, then failed
closed before chaos because meaningful paid traffic was absent. The outcome is
`fail`, which is the correct passing result for this negative test objective.

Do not label a manually patched workload, a mutable tag, or a locally rendered
overlay as a verified pipeline regression. It must travel through the intended
testnet verification path before it can support that claim.

The detailed sanitized bundle remains outside Git; see the
[verification report](../../verification-report.md). Direct boundary tests in
sibling directories remain narrower than this pipeline-produced regression.
