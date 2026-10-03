# Production-like smoke evidence status

**Status: passed on 3 October 2026.** Resilience Gate completed a fresh Kargo-managed
production-like testnet promotion and post-deploy smoke. The `prod` name still
denotes an owned testnet environment, never mainnet or public production.

## Fresh `v1.0.0` smoke result

| Identity or result | Recorded value |
| --- | --- |
| Bundle run ID | `v1-prod-screenshot-20261003T153428Z` |
| Application release | `v1.0.0` / `3b70835335462f1b6f9b1dd17ab20d1108724f89` |
| Freight | `d3b4380d40e87e244162da80aae9eb90503be15d` (`hoping-warthog`) |
| Source/chart revision in Freight | `0a98c08ccab5fa7b05efcecf877c714e5c89f025` |
| Rendered `env/prod` revision | `7d334d5a05e747cabff59d28de75e73534afe578` |
| Application digest | `sha256:ab88d89c20ccf1a79b9f47f90aa417ac0f54d7852c39b444b7fb788975fdd6a1` |
| Promotion | `prod.01m416e19hks7jnsbca6m49ae9.d3b4380` — `Succeeded` |
| AnalysisRun | `prod.01m416ezeke4d89a42wkqefzv9.d58be07` — `Successful` |
| Verification window | `2026-10-03T15:34:59Z`–`15:35:29Z` |
| Metrics | `readiness` and `liveness` — both `Successful` |
| Argo CD | `Synced` / `Healthy` at `7d334d5` |
| Workloads | application `3/3`; PostgreSQL `1/1`; Redis `1/1` |

The upstream staging AnalysisRun
`staging.01m4135pfqh94e76vzzn7fpbs4.d58be07` verified this same Freight with
all three fault/recovery scorecards passing. The prod smoke requested no paid
load or chaos, left no run-scoped load Job or gate Lease, and kept the existing
two-node cluster unchanged.

## Historical smoke

The earlier run `prod-smoke-20261002-060326` passed for Freight `89773faa...`
and rendered revision `4d7ffb5...`. It is a separate historical candidate,
not the current `v1.0.0` smoke result.

The detailed sanitized bundle and cleanup receipt are retained in a private
external evidence archive. The
[verification report](../../verification-report.md) records the reviewed
identities and result. This is a verified production-like **testnet** result,
not a mainnet or public-production release. The
[screenshot gallery](../../screenshots/README.md) includes the current prod
resource tree and final Freight alignment.
