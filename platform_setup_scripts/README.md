# Platform bootstrap

These scripts bootstrap the prerequisite GKE controllers for Resilience Gate.
Each phase is safe to inspect locally and requires explicit operator input
before mutation. The private testnet lab has been provisioned and verified with
this workflow; a new environment must still establish its own result.

## Safe first run

```bash
cp platform_setup_scripts/config.env.example platform_setup_scripts/config.env
$EDITOR platform_setup_scripts/config.env
./platform_setup_scripts/bootstrap.sh --render-config
git diff -- kubernetes/
# Review and commit the public identifier diff through the normal PR process.
./platform_setup_scripts/bootstrap.sh
```

`config.env` is ignored. It supplies public target identifiers locally, while
the renderer writes the matching reviewable GitOps manifests. Secret values do
not go in `config.env`, generated manifests, terminal command arguments, or
Git; phase 02 prompts silently or streams from a source project through stdin.

## Phases currently available

| Phase | Purpose | Safety boundary |
| --- | --- | --- |
| 00 | Tools, ADC, target-project access | Read-only; optional exact-context assertion |
| 01 | Required APIs and Terraform state bucket | Refuses a state bucket owned by another project |
| 02 | Secret Manager named values | No values on disk; existing values stay unless `ROTATE_SECRETS=true` |
| 03 | Terraform plan and apply | Always saves a plan; no interactive input means no apply |
| 04 | Controller installation | Exact chart versions and persistent Kargo credentials |
| 05 | Secret store, repository credential, root app | Exact target context and rendered-manifest check |
| 06 | GitOps and Kargo configuration | Registers contracts only; does not start promotion, paid load, or chaos |

The orchestrator intentionally stops at phase 06. It registers only the
rendered-branch configuration required for later promotion. A production-like
testnet promotion, paid load generation, or chaos experiment remains an
explicit action with its own reviewed contract.

## Useful commands

```bash
./platform_setup_scripts/bootstrap.sh --dry-run
./platform_setup_scripts/bootstrap.sh --phase 3
PLAN_ONLY=true ./platform_setup_scripts/bootstrap.sh --phase 3
./platform_setup_scripts/bootstrap.sh --from 4
./platform_setup_scripts/bootstrap.sh --config /safe/path/config.env --render-config
```

Use `TF_AUTO_APPROVE=true` only after independently reviewing the saved plan.
Use `ROTATE_SECRETS=true` only when intentionally adding a new Secret Manager
version. Migration source credentials are passed with `--source-project` and
optionally `--source-account`; they are never persisted in the config file.

## Context contract

Kubernetes-mutating phases require exactly:

```text
gke_<PROJECT_ID>_<ZONE>_<CLUSTER_NAME>
```

Terraform obtains that context after a successful apply and verifies it before
later phases can use Helm or kubectl. A mismatched current context is a hard
failure, not a warning or implicit override.

## Verification status

The 2 October 2026 campaign verified the owned GKE cluster, controller
availability, ClusterSecretStore and ExternalSecrets, eight Synced/Healthy
Argo CD Applications, all three Kargo Stages, the staging chaos path, and the
production-like testnet promotion. See the
[verification report](../docs/verification-report.md).

A rendered diff, dry run, or local validation still does not establish a new
environment or a later release. Every bootstrap target needs its own read-only
verification and evidence.

Keep live results in the sanitized [evidence
directory](../docs/evidence/README.md), bound to the exact source and artifact
identities exercised in an approved owned testnet lab.
