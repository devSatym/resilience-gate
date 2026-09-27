# Production-like smoke evidence status

**Status: not collected.** Resilience Gate has not run a production-like smoke
test from this workspace. The `prod` name in this repository denotes a
testnet-only, production-like environment; it is not a mainnet or public
production release.

## Future smoke-test record

An approved manual smoke test must identify the promoted source revision,
rendered-branch revision, immutable workload and runtime digests, target
context, and exact stage approval boundary. It should retain sanitized
readiness, a bounded request/result summary, and a clear pass, fail, blocked,
or unavailable outcome. It must not bypass the staging verification contract
or turn an unverified manual patch into a release claim.

No such artifacts are present today, so no production-like release has been
verified.
