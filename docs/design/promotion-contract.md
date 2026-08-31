# Rendered-branch promotion contract

Resilience Gate uses Kargo to turn a reviewed source revision and an OCI image
digest into rendered manifests on `env/dev`, `env/staging`, and `env/prod`.
This contract applies only to the owned Radius testnet chain. It does not
authorize a mainnet or production-network release.

## Identity and ordering

`platform_setup_scripts/06-gitops-and-kargo.sh` first checks that all public
repository and registry identifiers were rendered from the ignored local
`config.env` and reviewed in Git. It then applies resources in this order:

1. Kargo Project, which owns the `resilience-gate` namespace.
2. The ExternalSecret that supplies Git credentials from Secret Manager.
3. Project policy, reusable health analyses, and the dev/staging/prod Stage
   contracts.
4. The scoped Argo CD AppProject and ApplicationSet, which register the
   destination Applications before Kargo can request their sync.
5. The Warehouse, which may begin discovering digest-backed Freight only after
   the destinations exist.

The Warehouse discovers CI `sha-*` labels but Kargo writes the Freight's OCI
digest into rendered values. Mutable deployment tags are never used as the
workload identity.

## Promotion boundaries

Development may auto-promote after its normal service-health verification.
Staging accepts Freight only from development and remains manually promoted.
The production-like testnet Stage accepts Freight only from staging, remains
manual, and carries an explicit deferred-activation annotation until the later
immutable chaos-gate integration is reviewed.

The Git credential is an ExternalSecret backed by the shared
`resilience-gate-secrets` ClusterSecretStore. Its value is never stored in
Git, CI variables, generated manifests, or command arguments. Kargo's
rendered-branch `git-push` is attributable to that restricted GitOps identity;
ordinary CI only publishes and signs candidate artifacts.

## Explicitly deferred actions

Phase 06 does not invoke a Kargo Promotion, force an Argo CD sync, create a
load-generation Job, install or run a Chaos Mesh experiment, or declare a
gate passed. A missing rendered branch, unavailable secret, unhealthy
Application, absent testnet funding, stale telemetry, or later chaos-gate
failure blocks the relevant later action instead of being bypassed here.

Before any manual testnet promotion, an operator must review the exact Freight
digest, rendered branch commit, stage policy, application health, and the
evidence requirements documented by the later gate and operations runbooks.
