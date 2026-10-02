# Resilience Gate documentation

This directory is the canonical guide to the platform. Start with the
[root README](../README.md) for the project overview, then use this index to
move from architecture to implementation contracts, operations, and evidence.

## Architecture and verified state

| Document | Purpose |
| --- | --- |
| [Kubernetes architecture](kubernetes-architecture.md) | Component ownership, GitOps topology, promotion flow, observability, and failure boundaries. |
| [Configuration reference](configuration-reference.md) | Public settings, environment profiles, versions, namespaces, identity, and secret-reference rules. |
| [Verification report](verification-report.md) | Final owned-testnet validation snapshot, exact scope, outcomes, revisions, and evidence audit. |
| [Known limitations](known-limitations.md) | Explicit non-claims and remaining productionization limits. |
| [Offline demo](demo-walkthrough.md) | Reproduce source-level checks without cloud credentials, a cluster, or testnet funds. |

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

The [evidence index](evidence/README.md) explains what is retained in Git, what
is retained outside Git, how sanitization works, and which conclusions each
record supports. Evidence is scoped to the exact candidate and run. A
successful historical record does not automatically validate a later change.

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
