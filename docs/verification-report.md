# Owned-testnet verification report

**Recorded:** 2 October 2026

**Scope:** private, owned GCP and Radius testnet lab

**Platform source snapshot:** `343f4723a30e7bfc93b47423af3d838e53e3b6ba`

**Repository:** `devSatym/resilience-gate`

**Verdict:** complete and passing for the stated testnet scope

This report reconciles source validation, CI, GKE runtime state, Argo CD,
Kargo, baseline traffic, paid testnet behavior, negative gate behavior,
healthy chaos, recovery, production-like promotion, cleanup, and evidence
hygiene. It does not claim mainnet, public-production, compliance, financial
custody, high availability, backup restoration, or disaster recovery.

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
negative candidate failed for its intended reason and did not progress through
the normal promotion path. Temporary verification resources were removed.

## Source and CI validation

| Check | Result |
| --- | --- |
| Main source vs `origin/main` | Matched at `343f4723a30e7bfc93b47423af3d838e53e3b6ba` |
| Broad local validation | 230 passed, 1 deselected |
| Signer validation | 13 passed |
| Git diff integrity check | Passed |
| Private `.plan` exclusion | Confirmed ignored |
| Final GitHub validation runs | 5/5 passed |

The broad validation includes application contracts, Helm lint/rendering,
Terraform format and validation, committed shell syntax, Kustomize rendering,
GitOps contracts, chaos orchestration/scoring, evidence tooling, bootstrap
guards, load generation, and operations tooling. Docker Compose configuration
was also validated when Docker was available.

The five final successful GitHub run IDs were `36967139887`, `36968064299`,
`36969824094`, `36970004843`, and `36970539563`.

## Live platform inventory

| Layer | Observed state |
| --- | --- |
| GKE | 2/2 nodes Ready; both `e2-standard-4` |
| Argo CD | 8/8 Applications `Synced` and `Healthy` |
| Kargo dev | `Steady`; latest verification `Successful` |
| Kargo staging | `Steady`; latest verification `Successful` |
| Kargo prod | `Steady`; latest verification `Successful` |
| Dev | 1/1 app Deployment, PostgreSQL 1/1, Redis 1/1; 3 Ready pods |
| Staging | app 2/2, signer 1/1, PostgreSQL 1/1, Redis 1/1; 5 Ready pods |
| Prod-like | app 3/3, PostgreSQL 1/1, Redis 1/1; 5 Ready pods |
| External Secrets | 9/9 Ready; ClusterSecretStore Ready |
| Secret inspection | No Secret data read during final audit |

The eight healthy Argo CD Applications were `root-app`, `observability`,
`chaos-mesh`, `chaos-jobs`, `chaos-gate`, `resilience-gate-dev`,
`resilience-gate-staging`, and `resilience-gate-prod`.

## Scenario results

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

### Production-like promotion — pass

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

The immutable image digest is preserved in the sanitized evidence bundle but
is intentionally not repeated in recruiter-facing documentation.

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

At completion there were no active Kargo Promotions or AnalysisRuns and no
run-scoped Workflow, WorkflowNode, PodChaos, Job, or Lease resources in dev,
staging, or prod. The staging load-generator CronJob remained suspended. Prod
contained no load-generator CronJob.

The cleanup result is part of the verdict. It is not inferred from Job exit
status alone.

## Evidence audit

The final external evidence tree contained 16 schema-valid metadata records and
238 retained files. The audit found:

- zero symlinks;
- zero raw-named artifacts;
- no secret, wallet-address, payment-header, signature, or transaction-pattern
  matches after remediation;
- no suspicious long encoded data; and
- only reviewed redaction categories: `none`, `secret-data`, and
  `wallet-keys`.

The detailed sanitized bundles remain outside Git by default. Selected earlier
records are versioned under [`docs/evidence/`](evidence/); the
[evidence index](evidence/README.md) explains the retention boundary.

## Completion statement

Resilience Gate is fully implemented, deployed, and verified for its intended
private GCP and Radius testnet scope. A later source, dependency, controller,
configuration, credential, or infrastructure change invalidates this snapshot
until the relevant validation path is rerun.

The project remains intentionally outside mainnet and public production.
