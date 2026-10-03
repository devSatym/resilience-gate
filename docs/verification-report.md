# Owned-testnet verification report

**Recorded:** 3 October 2026; final screenshot audit at `17:26:01Z`

**Scope:** private, owned GCP and Radius testnet lab

**Validated platform source snapshot:** `7ea5e911aba159966b2a54657c501a8e643ee18f`

**Released application source:** `v1.0.0` at
`3b70835335462f1b6f9b1dd17ab20d1108724f89`

**Repository:** `devSatym/resilience-gate`

**Verdict:** complete and passing for the stated testnet scope

This report joins the October 2 historical validation campaign with the fresh
October 3 `v1.0.0` staging and prod-like verification. Each result names its
own source, runtime identity, and time window. The platform and application
release commits differ: three observability changes followed the release tag.
The recorded scope excludes mainnet, public production, custody, compliance,
high availability, backup restoration, and disaster recovery.

## Executive result

The complete intended path was exercised:

```text
source validation
  → dev baseline
  → staging paid smoke
  → deliberately degraded staging candidate blocked
  → corrected staging chaos re-verification
  → production-like testnet promotion
  → post-deploy readiness/liveness
  → residual-resource and evidence audit
```

Every positive gate required by the project completed successfully. The
historical negative candidate failed for its intended reason and remained
ineligible for the normal prod promotion path. On October 3, dev, staging, and
prod ended `Steady` and `Healthy` on the same release Freight. Temporary fault,
load, and Lease resources were removed. The existing two-node cluster was
neither created nor resized during that run.

The [screenshot gallery](screenshots/README.md) supplies reviewed visual context;
the identities, status, scorecards, and cleanup receipts below establish the
verification boundary.

## Source and CI validation

| Check | Result |
| --- | --- |
| Audited main source vs `origin/main` | Matched at `7ea5e911aba159966b2a54657c501a8e643ee18f` before the presentation update |
| Broad local validation | 231 passed, 1 intentionally deselected |
| Separately executed marked recovery contract | 1 passed locally; also passed in CI |
| Signer validation | 13 passed |
| Git diff integrity check | Passed |
| Private `.plan` exclusion | Confirmed ignored |
| Current platform GitHub validation | [37123284920](https://github.com/devSatym/resilience-gate/actions/runs/37123284920) — successful at `7ea5e91` |
| Release source GitHub validation | [36978412161](https://github.com/devSatym/resilience-gate/actions/runs/36978412161) — successful at `3b70835` |

The broad validation includes application contracts, Helm lint/rendering,
Terraform format and validation, committed shell syntax, Kustomize rendering,
GitOps contracts, chaos orchestration/scoring, evidence tooling, bootstrap
guards, load generation, and operations tooling. Docker Compose configuration
was also validated when Docker was available.

The one deselected local test is the marked Redis recovery integration
contract. It uses an in-process ASGI client and fake dependencies; the GitHub
validation workflow runs it separately with the `integration` marker, and it
passed in the current source run and a separate local execution. The optional
Compose smoke is a separate Docker exercise. The 231-test count remains
separate from this marked recovery check.

The five successful runs recorded by the earlier October 2 campaign were
`36967139887`, `36968064299`, `36969824094`, `36970004843`, and `36970539563`.
Later observability commits also passed validation runs `37002704536`,
`37111970767`, and `37123284920`.

## October 3 platform inventory

| Layer | Observed state |
| --- | --- |
| GKE | 2/2 nodes Ready; both `e2-standard-4` |
| Argo CD | 8/8 Applications `Synced` and `Healthy` |
| Kargo dev | `Steady`; latest verification `Successful` |
| Kargo staging | `Steady`; latest verification `Successful` |
| Kargo prod | `Steady`; latest verification `Successful` |
| All three current Freight references | `d3b4380d40e87e244162da80aae9eb90503be15d` (`hoping-warthog`) |
| Dev | 1/1 app Deployment, PostgreSQL 1/1, Redis 1/1; 3 Ready pods |
| Staging | app 2/2, signer 1/1, PostgreSQL 1/1, Redis 1/1; 5 Ready pods |
| Prod-like | app 3/3, PostgreSQL 1/1, Redis 1/1; 5 Ready pods |
| External Secrets | 9/9 Ready; ClusterSecretStore Ready |
| Secret inspection | No Secret data read during final audit |

The eight healthy Argo CD Applications were `root-app`, `observability`,
`chaos-mesh`, `chaos-jobs`, `chaos-gate`, `resilience-gate-dev`,
`resilience-gate-staging`, and `resilience-gate-prod`.

## Fresh release verification — 3 October 2026

The same immutable application release completed fresh staging verification,
then a separately authorized prod-like promotion using the existing fixed
cluster. Staging exercised paid traffic and three sequential pod failures;
prod exercised readiness and liveness without paid load or chaos.

| Shared release identity | Value |
| --- | --- |
| Tag and application source | `v1.0.0` / `3b70835335462f1b6f9b1dd17ab20d1108724f89` |
| Source/chart commit carried by Freight | `0a98c08ccab5fa7b05efcecf877c714e5c89f025` |
| Freight | `d3b4380d40e87e244162da80aae9eb90503be15d` (`hoping-warthog`) |
| Application digest | `sha256:ab88d89c20ccf1a79b9f47f90aa417ac0f54d7852c39b444b7fb788975fdd6a1` |

The Freight combines the recorded chart-source revision and release image.
Neither the application source commit nor the image digest should be inferred
from the platform snapshot or the rendered environment branch.

### Staging chaos verification — pass

| Identity or result | Value |
| --- | --- |
| Promotion | `staging.01m4134wftvmjnsgvvgzpbenbq.d3b4380` — `Succeeded` |
| AnalysisRun | `staging.01m4135pfqh94e76vzzn7fpbs4.d58be07` — `Successful` |
| Rendered `env/staging` revision | `64d2ddedb1493e0c59aef9ecad0ad0a2ff4196cf` |
| Gate Job | `e01beb57-aa6c-4f51-84e9-e91fd3382676.chaos-verdict.1` — succeeded |
| Analysis window | `2026-10-03T14:37:29Z`–`14:46:28Z` |
| PostgreSQL fault | `14:39:11Z` |
| Redis fault | `14:42:11Z` |
| Signer fault | `14:44:11Z` |
| Scorecards | PostgreSQL, Redis, and signer — all passed |
| Gate verdict | `GATE VERDICT: PASS` |
| Argo CD | `resilience-gate-staging` `Synced` / `Healthy` at `64d2dde` |

The gate proved meaningful paid traffic before fault injection, observed each
dependency failure and bounded recovery, and cleaned its exact run objects.
The load Job `loadgen-311c93f7-bfac-4ccb-a546-92cccb187b45` and Workflow
`chaos-gate-hcc49` were automatically removed. The source CronJob remained
suspended; no gate Lease, WorkflowNode, or PodChaos remained.

### Prod-like smoke verification — pass

| Identity or result | Value |
| --- | --- |
| Promotion | `prod.01m416e19hks7jnsbca6m49ae9.d3b4380` — `Succeeded` |
| AnalysisRun | `prod.01m416ezeke4d89a42wkqefzv9.d58be07` — `Successful` |
| Rendered `env/prod` revision | `7d334d5a05e747cabff59d28de75e73534afe578` |
| Promotion window | `2026-10-03T15:34:28Z`–`15:34:37Z` |
| Analysis window | `2026-10-03T15:34:59Z`–`15:35:29Z` |
| Metrics | `readiness` and `liveness` — both `Successful` |
| Argo CD | `resilience-gate-prod` `Synced` / `Healthy` at `7d334d5` |
| Workloads | application `3/3`; PostgreSQL `1/1`; Redis `1/1` |
| Isolation | no paid load, load Job, chaos object, or gate Lease |

All three Stages ended on the shared Freight above. This prod-like result is
an owned-testnet smoke verification, with staging chaos established upstream.

## Historical scenario results — 2 October 2026

The following campaign remains useful evidence of baseline, payment, failure,
and recovery behavior. Its candidates and rendered revisions differ from the
October 3 release verification and are retained with that distinction.

### Dev baseline — pass

Run `baseline-20261002-031523` exercised a 91-second bounded window against
`url-shortener-dev` and produced a passing scorecard:

| Signal | Observed | Bound |
| --- | ---: | ---: |
| Meaningful GET traffic | 44.89 requests | > 20 |
| Application 5xx | 0 | < 0.5 |
| GET p95 latency | 0.095 s | < 1.0 s |
| PostgreSQL readiness | 1 throughout 7 samples | = 1 |
| Redis readiness | 1 throughout 7 samples | = 1 |
| Immutable release identity | Present | Required |

An earlier failed baseline attempt was retained rather than overwritten. The
fresh successful run is the accepted result.

### Staging paid smoke — pass

Run `paid-smoke-20261002-043614` observed:

```text
unsigned request  → 402 challenge
signed settlement → 201 created
redirect          → 302
replay attempt    → 409 conflict
```

The receipt confirms a successful first settlement, an intentional application
record, all three bounded wallets above the configured floor, and no active
gate Workflow or run-scoped load Job afterward. Response bodies, payment
headers, wallet identities, signatures, and transaction identifiers were not
emitted into the retained receipt.

### Deliberately degraded candidate — correctly failed

Run `regression-blocked-20261002-050844` used pipeline-produced source
`86d6f17f20a53de34c2d81949016fdab1fd82d16` and rendered revision
`c6515a622eeae3850e749cae1833801827d3c915`.

The gate acquired its Lease and created the run-scoped load Job, but the
candidate did not prove paid traffic within 75 seconds. The gate failed before
fault injection, cleaned the load Job, and prevented a vacuous chaos pass. The
failure is the expected outcome for this negative candidate.

### Corrected staging recovery — pass

Run `recovery-20261002-052031` verified corrected source
`0a98c08ccab5fa7b05efcecf877c714e5c89f025` and rendered revision
`bc388eaff8ff294e1f59b3c417a18c6b96dd5d39`.

The Kargo-managed AnalysisRun completed the PostgreSQL, Redis, and signer
pod-failure scenarios. Each scorecard observed the dependency failure and its
bounded recovery, and the gate logged a passing verdict with exact-object
cleanup.

### Previous production-like promotion — pass

Kargo promoted Freight `89773faa71018568b4eef88317856536430a58b3` from the
verified staging path into `prod`:

| Identity or result | Value |
| --- | --- |
| Source revision | `0a98c08ccab5fa7b05efcecf877c714e5c89f025` |
| Rendered revision | `4d7ffb5a423cb80f49e5d84e97d7619813482439` |
| Promotion | `prod.01m3xk0q4myve9sfjsp9qj4n9t.89773fa` — `Succeeded` |
| AnalysisRun | `prod.01m3xk2fsdfzn53py0y7mkrg6y.e7171a5` — `Successful` |
| Readiness metric | `Successful` |
| Liveness metric | `Successful` |
| Argo CD | `Synced` and `Healthy` at the rendered revision |
| Application | 3/3 replicas Ready |
| Dependencies | PostgreSQL 1/1 and Redis 1/1 |

The previous application digest was
`sha256:a5beda836336de1677e27c3c2ff09a1ab27d9366040cd985c347d700de6f476b`.
It differs from the fresh `v1.0.0` application digest above.

## Fail-closed boundary coverage

In addition to the full promotion path, retained records exercise the following
negative behavior:

| Boundary | Verified response |
| --- | --- |
| No ready target | Blocked before fault injection and released the Lease. |
| Missing load source | Failed and entered exact-object cleanup. |
| Unreachable telemetry | Scorer emitted transport errors and a failing verdict. |
| One-second workflow deadline | Failed before normal fault phase and cleaned all run-scoped objects. |
| Historical missing workflow timestamps | Failed closed; later corrected with a fresh, linked re-verification. |
| Missing paid traffic | Degraded pipeline candidate failed before chaos could begin. |

These tests make absence and uncertainty visible; none is described as a
successful release result.

## Cleanup and steady-state audit

At completion there were no active Kargo Promotions or AnalysisRuns, gate
Jobs, or load Jobs. No run-scoped Workflow, WorkflowNode, PodChaos, or gate
Lease remained. Completed controller and Job history was retained where
available. The staging load-generator CronJob remained suspended. Prod
contained no load-generator CronJob.

The cleanup result is part of the verdict. It is not inferred from Job exit
status alone.

## Evidence audit and retention

The historical October 2 external evidence tree was audited as 16 schema-valid
metadata records and 238 retained files. That count describes the earlier
archive, not the two new October 3 bundles. Its audit found:

- zero symlinks;
- zero raw-named artifacts;
- no secret, wallet-address, payment-header, signature, or transaction-pattern
  matches after remediation;
- no suspicious long encoded data; and
- only reviewed redaction categories: `none`, `secret-data`, and
  `wallet-keys`.

The October 3 campaign produced **two new sanitized bundles containing 36
files**, identified by run IDs `v1-screenshot-20261003T143702Z` (staging chaos)
and `v1-prod-screenshot-20261003T153428Z` (prod smoke). Detailed bundles remain
in a private archive outside Git; selected historical records are versioned
under [`docs/evidence/`](evidence/). The
[evidence index](evidence/README.md) records the archive boundary.

The gallery contains **29 canonical screenshots and five companions**. All 34
accepted PNGs had their SHA-256 hashes rechecked at `2026-10-03T17:26:01Z`.
Captions distinguish fresh release verification from historical failure and
recovery views. Visible public project identifiers and reviewed usernames are
allowed; Secret values, wallet addresses, signatures, payment headers, and
transaction identifiers are excluded.

## Completion statement

Resilience Gate is fully implemented, deployed, and verified for its intended
private GCP and Radius testnet scope. A later source, dependency, controller,
configuration, credential, or infrastructure change invalidates this snapshot
until the relevant validation path is rerun.

The project remains intentionally outside mainnet and public production.
