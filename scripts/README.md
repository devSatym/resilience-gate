# Operator and validation scripts

Every cloud-facing entry point defaults to a read-only or plan mode where
practical. Paid traffic, promotion, evidence collection, and teardown require
explicit acknowledgements and exact target checks.

## Quick reference

| Script | Default behavior | Mutating behavior |
| --- | --- | --- |
| `validate.sh` | Runs credential-free source validation. | None. |
| `smoke-local.sh` | Builds and exercises the local unpaid Compose stack, then removes it. | Local containers and disposable volumes only. |
| `run-loadgen.sh` | Prints and validates a no-network load plan. | `--execute` creates one bounded staging Job after preflight. |
| `validate-live.sh` | Prints the reviewed scenario plan. | `--execute` requests the selected Kargo Stage verification/promotion path. |
| `collect-evidence.sh` | Prints the collection plan. | `--collect` reads scoped objects and writes a sanitized local bundle. |
| `lab-ops.sh` | `status` runs read-only verification. | Guarded bootstrap or destructive Terraform workflows require separate flags and confirmations. |
| `test-payment-flow.sh` | Refuses to run without opt-in. | Performs one real testnet settlement smoke. |
| `score-baseline.py` | Scores a supplied bounded Prometheus window. | None; reads telemetry and writes the requested scorecard. |
| `evidence_utils.py` | Library/CLI support for sanitization and schema-safe evidence. | Writes only the requested sanitized output. |
| `xk6-contract-smoke.js` | Source contract fixture for load-generator validation. | None in ordinary validation. |

## Source validation

```bash
PYTHON=.venv/bin/python ./scripts/validate.sh
# or
PYTHON=.venv/bin/python make validate
```

The script checks Helm dependencies and rendering for all environments,
Terraform format/init/validation, committed shell syntax, gate-runner inputs,
committed Kustomizations, the broad pytest suite, signer tests, and Docker
Compose configuration when Docker is available. It does not apply Terraform,
contact Kubernetes, promote Freight, start paid load, or inject chaos.

## Local recovery smoke

```bash
make smoke-local
```

The smoke starts PostgreSQL, Redis, and the application; creates and resolves a
URL; temporarily stops Redis; verifies liveness and steady-state readiness;
restarts Redis; and removes the Compose project and volumes. It is unpaid and
is not Kubernetes or release evidence.

## Bounded staging load

Review first:

```bash
./scripts/run-loadgen.sh --plan \
  --profile arrival-rate \
  --duration 10m \
  --vus 3 \
  --arrival-rate 60 \
  --arrival-time-unit 1m
```

Execution requires the script's explicit mode and target checks. It verifies
the source CronJob remains suspended, application/signer/ExternalSecret
readiness, then creates one uniquely named Job. The canonical k6 program is
[`kubernetes/jobs/scripts/loadgen.js`](../kubernetes/jobs/scripts/loadgen.js).
It requests signatures from the isolated signer, submits paid testnet traffic,
and checks redirects without following the external destination.

Results are copied to `/tmp/resilience-gate-loadgen/` by default. See the
[load-testing runbook](../docs/runbooks/load-testing.md).

## Kargo verification

```bash
./scripts/validate-live.sh --plan --scenario baseline
./scripts/validate-live.sh --plan --scenario chaos-gate
./scripts/validate-live.sh --plan --scenario regression-blocked
./scripts/validate-live.sh --plan --scenario recovery
./scripts/validate-live.sh --plan --scenario prod-smoke
```

Scenario routing is fixed:

| Scenario | Stage | Namespace |
| --- | --- | --- |
| `baseline` | `dev` | `url-shortener-dev` |
| `chaos-gate` | `staging` | `url-shortener-staging` |
| `regression-blocked` | `staging` | `url-shortener-staging` |
| `recovery` | `staging` | `url-shortener-staging` |
| `prod-smoke` | `prod` | `url-shortener-prod` |

Execute mode asks Kargo to use the reviewed Stage contract. A successful CLI
request means only that Kargo accepted it; the AnalysisRun verdict and cleanup
must still be observed.

## Evidence collection

```bash
./scripts/collect-evidence.sh --plan \
  --scenario chaos-gate \
  --status pass \
  --run-id <unique-run-id>
```

Collection writes outside the repository by default, refuses to overwrite a
run ID, reads only scenario-scoped resources, sanitizes risky values, and
validates `run-metadata.json`. A pass for chaos/recovery requires the exact
AnalysisRun, gate Job/Pod, all three scorecards, immutable identity, and
cleanup result. Review the [evidence guide](../docs/evidence/README.md) before
selecting any file for Git.

## Testnet payment smoke

```bash
RUN_TESTNET_PAYMENTS=1 \
BASE_URL=http://localhost:8000 \
SIGNER_URL=http://localhost:8080 \
./scripts/test-payment-flow.sh
```

The expected sequence is unsigned `402`, signed `201`, then replay `409`. The
tool is excluded from CI because it can spend testnet tokens. Use the
[payment runbook](../docs/runbooks/testnet-payments.md) and never place payer
keys in the command line or shell environment.

## Lab lifecycle

```bash
./scripts/lab-ops.sh status
./scripts/lab-ops.sh bootstrap-plan
./scripts/lab-ops.sh destroy-plan
```

`status` is read-only. Planning commands may read cloud/Terraform state but do
not apply it. Destruction requires the exact project identifier, explicit
owned-testnet acknowledgement, `--apply`, and an interactive retype. See the
[lab lifecycle runbook](../docs/runbooks/lab-lifecycle.md).
