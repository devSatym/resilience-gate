# Platform bootstrap

These scripts bootstrap the prerequisite GKE controllers for Resilience Gate.
They make no claim that an environment is already provisioned; each phase is
safe to inspect locally and requires explicit operator input before mutation.

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

The orchestrator intentionally stops at phase 05. It does not apply future
promotion, chaos, or production activation resources before their roadmap
phases are implemented and reviewed.

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
