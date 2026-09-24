# Owned testnet lab lifecycle

**Status: operational contract, not provisioning history.** The commands in
this runbook are designed for the owned Resilience Gate testnet lab. The
repository contains no record that a project, cluster, controller, or release
has been created or successfully destroyed.

`platform_setup_scripts/config.env` is ignored local operator input. It may
contain public project, registry, and cluster identifiers, but never Secret
values, wallet keys, payment signatures, or copied cloud credentials. Render
and review public manifest changes before any mutating bootstrap phase.

## Inspect the current lab

The default lab command is `status`; it delegates to the read-only verifier.
It requires the configured exact Kubernetes context and does not create,
delete, patch, promote, or execute workloads.

```bash
./scripts/lab-ops.sh \
  --config platform_setup_scripts/config.env \
  status
```

`./scripts/lab-ops.sh --help` and `status` are safe ways to inspect the command
surface. For narrower Kubernetes checks, run the verifier directly:

```bash
./platform_setup_scripts/07-verify.sh \
  --config platform_setup_scripts/config.env \
  --scope gate
```

An observed healthy resource state is not evidence of a completed promotion,
chaos run, payment, or release gate. Record actual live results separately
under the sanitized evidence process.

## Review bootstrap work without applying it

Use `bootstrap-plan` to run the existing completed bootstrap workflow with its
dry-run guard enabled:

```bash
./scripts/lab-ops.sh \
  --config platform_setup_scripts/config.env \
  bootstrap-plan
```

This is planning and review assistance, not approval to create infrastructure.
Review rendered manifests, the intended project and cluster identity, and any
saved Terraform plan before separately invoking the guarded bootstrap workflow.
The bootstrap orchestrator currently stops after phase 06; verification is a
separate read-only command, not a bootstrap phase.

## Review a scoped teardown plan

Before a teardown, create and inspect a fresh Terraform destroy plan:

```bash
./scripts/lab-ops.sh \
  --config platform_setup_scripts/config.env \
  destroy-plan
```

`destroy-plan` may read Terraform configuration and remote state to calculate
the result, but it does not apply a deletion. It retains Terraform's normal
state lock with a bounded wait, so do not start it alongside another
infrastructure operation. A plan is a point-in-time review artifact, not
consent to delete the lab. Do not reuse an old plan after the configuration or
state has changed.

## Destroy only an owned lab

Teardown is intentionally difficult to trigger. It is allowed only when all
of the following are true:

- the target project is an owned Resilience Gate **testnet** lab;
- the exact project identifier has been reviewed against `config.env`;
- a current destroy plan has been reviewed;
- no candidate, evidence collection, or payment exercise still needs the lab;
- an operator is present at an interactive terminal.

The destructive command needs both non-interactive acknowledgements and an
interactive retype of the exact configured project ID:

```bash
./scripts/lab-ops.sh \
  --config platform_setup_scripts/config.env \
  destroy \
  --apply \
  --confirm-project "<exact-PROJECT_ID>" \
  --acknowledge-owned-testnet-lab-destruction
```

After the command validates those guards, it creates a fresh saved Terraform
destroy plan and applies that exact plan. It does not substitute a bare
`terraform destroy`, issue `gcloud` deletes, issue `kubectl delete`, or bypass
resource-protection controls. If there is no TTY, the project does not match,
or the retyped value differs, it must stop without applying the plan.

Do not pipe a confirmation, automate this command, or weaken its checks to
make a cleanup job run unattended. Resolve any failed deletion or retained
resource through the reviewed infrastructure configuration, then record what
actually happened. The absence of a local error alone does not prove all cloud
resources are gone.

## Suggested sequence

1. Render and review public configuration, then use `bootstrap-plan`.
2. Run `status` and the relevant read-only verifier scope.
3. Use the Kargo and evidence runbooks for an explicitly approved testnet
   candidate; do not treat lifecycle status as a gate verdict.
4. Preserve sanitized evidence before considering teardown.
5. Review `destroy-plan`, then use the guarded interactive `destroy` command
   only for an owned testnet lab.
