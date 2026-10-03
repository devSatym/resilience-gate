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

Development can automatically promote new Warehouse Freight, reconcile it,
and run service-health verification. The normal staging path accepts Freight
verified in development and remains manually promoted. The normal prod-like
path accepts Freight verified in staging and also remains manual. Its
readiness and liveness verification follows the upstream staging health and
chaos contracts. A separate manual Freight approval is an operator override,
not evidence that the upstream verification passed.

The Git credential is an ExternalSecret backed by the shared
`resilience-gate-secrets` ClusterSecretStore. Its value is never stored in
Git, CI variables, generated manifests, or command arguments. Kargo's
rendered-branch `git-push` is attributable to that restricted GitOps identity;
ordinary CI only publishes and signs candidate artifacts.

## Explicit operator actions

Phase 06 does not invoke a Kargo Promotion, force an Argo CD sync, create a
load-generation Job, install or run a Chaos Mesh experiment, or declare a
gate passed. A missing rendered branch, unavailable secret, unhealthy
Application, absent testnet funding, stale telemetry, or later chaos-gate
failure blocks the relevant later action instead of being bypassed here.

Before any manual testnet promotion, an operator must review the exact Freight
digest and chart-source revision, current rendered state, stage policy,
application health, and the evidence requirements documented by the later
gate and operations runbooks. The promotion creates a new rendered branch
commit; that output must then be linked to the requested Freight and observed
Argo CD reconciliation before claiming success.

The historical October 2 campaign exercised this path through all three
Stages, including a negative candidate that failed staging and a corrected
candidate that completed prod-like post-deploy verification. On October 3,
fresh `v1.0.0` Freight `d3b4380…` passed staging chaos verification and then
prod-like readiness/liveness. Its rendered revisions were `64d2dde` in staging
and `7d334d5` in prod; all three Stages ended on that same Freight. The
[verification report](../verification-report.md) records the full identities,
and the [screenshot gallery](../screenshots/README.md) labels the historical
and fresh windows separately.

These checks establish environment health and release verification for the
recorded candidate. Cosign verification occurs at CI publication; the current
Stages do not independently verify image signatures or consume the CI identity
artifact. That separate trust boundary is documented in
[artifact identity](artifact-identity.md).
