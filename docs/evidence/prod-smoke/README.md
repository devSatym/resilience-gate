# Production-like smoke evidence status

**Status: passed on 2 October 2026.** Resilience Gate completed a Kargo-managed
production-like testnet promotion and post-deploy smoke. The `prod` name still
denotes an owned testnet environment, never mainnet or public production.

## Recorded smoke result

Run `prod-smoke-20261002-060326` identifies the promoted source, rendered
revision, immutable workload, target context, Freight, Promotion, AnalysisRun,
and exact upstream staging boundary. Kargo reported the Promotion `Succeeded`;
the AnalysisRun, readiness metric, and liveness metric were `Successful`; Argo
CD was Synced/Healthy at the rendered revision; the app was 3/3 Ready and both
stateful dependencies were Ready.

The detailed sanitized bundle and cleanup receipt remain outside Git. The
[verification report](../../verification-report.md) records the reviewed
identities and result. This is a verified production-like **testnet** result,
not a mainnet or public-production release.
