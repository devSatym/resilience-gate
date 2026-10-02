# Reproducible offline demo

This walkthrough demonstrates the repository's local contracts without
provisioning cloud infrastructure, contacting a Kubernetes cluster, spending
testnet funds, or claiming a release result. It is intentionally an **offline
demo**, not an evidence campaign.

## 1. Prepare a local test environment

Install Python 3.12, Docker Compose, Helm, Terraform, and `kubectl` with
Kustomize support. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -r signer/requirements.lock
```

The signer dependency install is included because the full hermetic suite
imports signer contracts. It does not start a signer, open a wallet, or contact
an RPC endpoint.

## 2. Exercise hermetic behavior

```bash
PYTHON=.venv/bin/python make test
PYTHON=.venv/bin/python make validate
python3 docs/diagrams/architecture.py --check
```

The default pytest configuration excludes `integration` and `live` markers.
The validation script checks source contracts, shell syntax, local Helm/Terraform
rendering, Kustomize rendering, and tests. It is allowed to fetch pinned
tooling dependencies when absent, but it does not apply infrastructure or run
`kubectl` against a cluster.

If a local tool is absent, install it rather than weakening the check. A failed
tool installation or validation result is a local setup issue—not a reason to
claim a pass.

## 3. Run the local service smoke check (optional)

```bash
make smoke-local
```

This starts the Compose Postgres/Redis/application stack, creates and resolves
a local URL, then checks that a temporary Redis loss preserves process
liveness and steady-state readiness. The script removes its Compose volumes on
exit. It deliberately uses the local unpaid configuration; it is not a Permit2
payment test, Kubernetes deployment, chaos experiment, or promotion test.

## 4. Inspect configuration without deploying it (optional)

Copy the example only if you need to see how public operator identifiers are
rendered:

```bash
cp platform_setup_scripts/config.env.example platform_setup_scripts/config.env
# Edit only local public identifiers. Do not put secret values in this file.
./platform_setup_scripts/bootstrap.sh --render-config
git diff -- kubernetes/
```

This writes public manifest substitutions into the working tree and exits. Do
not run bootstrap phases, apply Terraform, authenticate to a cloud account, or
create a testnet payment as part of this walkthrough. Discard or review the
rendered diff through the normal project workflow before continuing elsewhere.

## 5. Understand the live-evidence boundary

This walkthrough produces no live evidence. The separately completed owned-lab
campaign is documented in the [verification report](verification-report.md)
and [evidence index](evidence/README.md), but those records do not turn a later
offline run into release verification. Every new candidate needs fresh
sanitized metadata and artifacts for its exact source revision, rendered
revision, workload and runtime digests, target scope, traffic window,
scorecards, and cleanup checks.

Until that happens, the truthful demo conclusion is:

> The local source and offline checks can be reproduced; this walkthrough does
> not itself verify live Resilience Gate release behavior.
