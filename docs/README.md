# Resilience Gate documentation

Explore the release platform through its architecture, contracts, and
observed results. The [root README](../README.md) is the visual overview;
this index leads into the implementation and operating detail.

## Choose a route

| You want to… | Start here |
| --- | --- |
| See the system and promotion boundaries | [Architecture diagrams](diagrams/README.md) → [Kubernetes architecture](kubernetes-architecture.md) |
| Inspect what actually ran | [34-image evidence gallery](screenshots/README.md) → [Verification report](verification-report.md) |
| Try it without cloud credentials or funds | [Offline demo](demo-walkthrough.md) → [Local development](runbooks/local-development.md) |
| Understand the release decision | [Promotion contract](design/promotion-contract.md) → [Failure model](design/failure-model.md) |
| Trace a paid request | [Payment contract](design/payment-contract.md) → [Testnet payment runbook](runbooks/testnet-payments.md) |
| Audit claims and retained artifacts | [Evidence handling](evidence/README.md) → [Screenshot manifest](screenshots/manifest.json) → [Known limitations](known-limitations.md) |

## Architecture and verified state

| Document | Purpose |
| --- | --- |
| [Architecture diagrams](diagrams/README.md) | Original illustrations and reviewed vector flows, with available source and regeneration instructions. |
| [Kubernetes architecture](kubernetes-architecture.md) | Component ownership, GitOps topology, promotion flow, observability, and failure boundaries. |
| [Configuration reference](configuration-reference.md) | Public settings, environment profiles, versions, namespaces, identity, and secret-reference rules. |
| [Verification report](verification-report.md) | Final owned-testnet validation snapshot, exact scope, outcomes, revisions, and evidence audit. |
| [Known limitations](known-limitations.md) | Explicit non-claims and remaining productionization limits. |
| [Offline demo](demo-walkthrough.md) | Reproduce source-level checks without cloud credentials, a cluster, or testnet funds. |
| [Publication review](presentation-readiness.md) | License, disclosure, visibility, and repository-hardening review. |
| [Lab retirement](lab-retirement.md) | October 4 deletion receipt, historical-evidence boundary, and mandatory recovery retention. |
| [Release guide](releases/README.md) | Versioning, source identity, validation, release assets and safe publishing. |
| [v1.1.0 notes](releases/v1.1.0.md) | Observability, evidence, repository improvements and release non-claims. |
| [Security policy](../SECURITY.md) | Confidential vulnerability reporting and sensitive-data handling. |

## Design contracts

| Document | Decision captured |
| --- | --- |
| [Artifact identity](design/artifact-identity.md) | OCI digests, Cosign identity, immutable promotion, and retention. |
| [Promotion contract](design/promotion-contract.md) | Kargo Freight, rendered branches, Argo CD ownership, and manual boundaries. |
| [Failure model](design/failure-model.md) | Fail-closed classification, measurement, cleanup, payment, and recovery behavior. |
| [Payment contract](design/payment-contract.md) | x402 v2 request flow, Permit2 signer boundary, settlement, replay, and consistency. |
| [x402 implementation status](design/x402-migration.md) | Implemented request path and bounded testnet verification status. |

## Operator runbooks

| Runbook | Use it for |
| --- | --- |
| [Local development](runbooks/local-development.md) | Python validation and local Compose recovery smoke. |
| [Lab lifecycle](runbooks/lab-lifecycle.md) | Read-only state, guarded bootstrap planning, and reviewed teardown. |
| [Load testing](runbooks/load-testing.md) | Bounded staging k6 traffic and result handling. |
| [Testnet payments](runbooks/testnet-payments.md) | One opt-in x402/Permit2 payment smoke. |
| [Chaos gate](runbooks/chaos-gate.md) | Kargo-managed verification, failure handling, and collection. |
| [Platform bootstrap](../platform_setup_scripts/README.md) | Phased GCP/GKE/controller setup and exact context checks. |
| [Script reference](../scripts/README.md) | Safe defaults and purpose of each operator entry point. |

## Evidence

The [gallery](screenshots/README.md) presents **29 canonical views and five
detail companions** from the reviewed 2–3 October 2026 capture campaign.
It separates the fresh `v1.0.0` deployment from historical failed,
recovery, and paid-request scenarios. The [manifest](screenshots/manifest.json)
binds every published image to its hash, capture time, observed window, and
visible proof.

The [evidence index](evidence/README.md) explains the tracked sanitized
records, private external archive, collection workflow, and review rules.
Evidence supports the exact candidate and run named in each record; use the
[verification report](verification-report.md) for the current documented
release snapshot.

The owned GCP lab was retired on **4 October 2026**. These records remain useful
for review, but do not indicate an active deployment or a new runtime verification
for `v1.1.0`. The [retirement receipt](lab-retirement.md) records the final scope.

## Documentation rules

- `prod` always means a production-like environment on the owned testnet.
- Never publish Secret data, wallet keys or addresses, payment headers,
  signatures, transaction identifiers, cookies, kubeconfigs, or raw cloud
  configuration.
- Separate source contracts from observed live results.
- Bind a live claim to immutable source, rendered, image, and runtime identity.
- Update the verification date and evidence links when behavior changes.
- Treat any local blog drafts or historical migration notes as editorial
  material, not canonical operator guidance.
