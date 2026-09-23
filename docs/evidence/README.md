# Evidence handling

This directory is for sanitized, reviewable evidence from an explicitly
approved Resilience Gate scenario in the owned testnet lab. It is never a
place for Kubernetes Secret contents, wallet keys, payment signatures,
authorization headers, cookies, raw configuration files, or mainnet claims.

The repository currently contains offline implementation and contract-test
results only. It does not yet record a cloud, Kubernetes, Radius testnet, or
production-like live run. A passing unit test, rendered manifest, accepted
Kargo request, or empty scenario directory is not evidence that a release gate
passed.

## Use the reviewed verification path

`scripts/validate-live.sh` defaults to `--plan`; it makes no Kubernetes,
Kargo, cloud, or testnet call. Its execute mode first verifies the exact
configured Kubernetes context and then asks Kargo to use a reviewed Stage
contract:

```bash
./scripts/validate-live.sh --plan --scenario chaos-gate

./scripts/validate-live.sh --execute \
  --acknowledge-owned-testnet-lab \
  --scenario chaos-gate \
  --config platform_setup_scripts/config.env
```

For a named candidate, use `--promotion-freight NAME` together with the
additional `--acknowledge-staging-promotion` confirmation. That creates a real
Kargo staging promotion; it does not create a direct `AnalysisRun`, Chaos Mesh
workflow, load Job, or patched workload. A `kargo` command returning zero only
means it accepted the request. It is not the verification verdict.

Scenario routing is fixed and recorded in metadata: `baseline` uses the dev
Stage and `url-shortener-dev`; `chaos-gate`, `regression-blocked`, and
`recovery` use staging and `url-shortener-staging`; `prod-smoke` uses the
production-like testnet Stage and `url-shortener-prod`. `regression-blocked`
requires a named pipeline-produced Freight so a deliberately bad candidate is
recorded as a candidate, not misrepresented as a release-pipeline success.

## Collect a sanitized bundle

The collector writes outside the repository by default and refuses to overwrite
a run ID. It reads only narrow, non-secret resources for the mapped Stage and
workload. Staging chaos scenarios additionally capture the signer,
load-generator, gate template, and exact AnalysisRun, gate Job/Pod, logs, and
scorecards named by the operator.

```bash
./scripts/collect-evidence.sh --plan \
  --scenario chaos-gate \
  --status pass \
  --run-id 20261001-staging-gate-01
```

After the relevant in-cluster objects have completed, collect their exact names
and immutable identities. Replace every placeholder below with observed data;
do not invent a digest or a pass status.

```bash
./scripts/collect-evidence.sh --collect \
  --acknowledge-owned-testnet-lab \
  --config platform_setup_scripts/config.env \
  --scenario chaos-gate \
  --status pass \
  --run-id 20261001-staging-gate-01 \
  --analysis-run <kargo-analysisrun-name> \
  --gate-job <chaos-gate-job-name> \
  --repository-revision <source-commit> \
  --chart-revision <rendered-chart-commit> \
  --release-image-digest <application-sha256-digest> \
  --gate-runner-image-digest <gate-runner-sha256-digest> \
  --signer-image-digest <signer-sha256-digest> \
  --loadgen-image-digest <loadgen-sha256-digest>
```

For a passing chaos/recovery record, the collector requires the exact
AnalysisRun and gate Job or Pod, then reads the three scorecards while the Job
Pod still exists. The scorecards live in the gate Pod's ephemeral result volume;
their absence blocks a complete pass claim. A failed, blocked, or unavailable
record may use `unavailable` only for identities genuinely not observable.

`--include /absolute/path/to/extract` may add a small local status or log
extract. The collector accepts regular files only, sanitizes them before
writing, and rejects a repository output path unless
`--allow-repository-output` is explicit. Review every artifact before manually
selecting sanitized files for this directory.

## Metadata and review rules

Every bundle has a `run-metadata.json` conforming to
[`schemas/run-metadata.schema.json`](../../schemas/run-metadata.schema.json).
It binds a run to its source and chart revisions, application, gate-runner,
signer, and load-generator digests, context, namespace, scenario, supplied
status, artifacts, and redaction categories. `repository_revision` is the
source/Freight revision supplied to the gate; `chart_revision` separately
records the observed rendered-branch revision. The collector uses
`scripts/evidence_utils.py` to replace risky fields rather than retaining their
values, then validates the resulting metadata without a cloud dependency.

- A `pass` metadata value is an operator-supplied claim that still needs review
  against the AnalysisRun status and all three scorecards.
- `blocked` and `unavailable` establish that the associated release claim was
  not proven; they are not passing outcomes.
- Never overwrite prior evidence. Give every execution a new run ID.
- Preserve the exact source, chart, gate, and runtime identities. Do not use a
  mutable image tag as evidence.
- Do not call a manually patched workload a fully verified release-pipeline
  test. Record it separately as a candidate or regression exercise.
- The sanitizer is a safety layer, not authorization to upload raw diagnostics.
  Review output for sensitive material before it enters Git.
