# Evidence handling

This directory is for sanitized, reviewable evidence from an explicitly
approved Resilience Gate scenario in the owned testnet lab. It is never a
place for Kubernetes Secret contents, wallet keys, payment signatures,
authorization headers, cookies, raw configuration files, or mainnet claims.

The repository contains a small, sanitized set of versioned
**owned staging-testnet** records: one Kargo-managed chaos-gate pass, an earlier
failed predecessor and fresh re-verification, plus four manual direct boundary
tests. A later full validation campaign also completed baseline, paid smoke,
deliberate regression, corrected recovery, and production-like promotion. Its
detailed sanitized bundles remain outside Git by default; the reviewed result
is documented in the [verification report](../verification-report.md).

A passing unit test, rendered manifest, accepted Kargo request, or empty
scenario directory is not evidence that a release gate passed. Likewise, the
manual boundary records below are deliberately not described as Kargo
verification, Freight promotion, or release approval.

## Recorded evidence

Every tracked `run-metadata.json` below validates against the shared schema.
The per-run directories contain only a reviewed subset of the sanitized
collection: metadata, the relevant gate/scorer log, and scorecards for passing
gate runs. Kubernetes YAML is intentionally retained outside Git because even
sanitized manifests can expose unnecessary environment and secret-reference
detail.

| Record | Outcome and narrow meaning |
| --- | --- |
| [staging chaos gate](healthy-chaos/20261001-staging-gate-b8cc5caa/) | **Pass.** A Kargo-managed staging AnalysisRun completed the PostgreSQL, Redis, and signer fault/recovery scorecards and logged run-scoped cleanup. |
| [failed predecessor](recovered/20261001-historical-apply-timestamp-failure/) | **Fail.** The earlier gate runner could not obtain required workflow timestamps and failed closed before the subsequent re-verification. |
| [staging re-verification](recovered/20261002-staging-recovery-fc2ef08d/) | **Pass.** A fresh Kargo staging re-verification of the same release/render identity, using the corrected gate-runner digest, completed all three scorecards and cleanup. |
| [no target](no-target/20261002-no-target-neg-notarget/) | **Blocked.** A manually started direct runner test rejected an intentionally nonexistent Service before fault injection. |
| [load source error](loadgen-error/20261002-loadgen-source-error/) | **Fail.** A manually started direct runner test failed closed when an intentionally nonexistent load-source CronJob could not create its run-scoped load Job. |
| [missing telemetry](missing-telemetry/20261002-missing-telemetry-scorer/) | **Fail.** A scorer-only direct test treated a deliberately unreachable Prometheus endpoint as transport-error evidence. |
| [short deadline cleanup](timeout-cleanup/20261002-timeout-cleanup/) | **Fail.** A direct runner test with a one-second deadline invoked exact-object cleanup before its normal fault phase. |

The final campaign additionally recorded:

| Record | Outcome and narrow meaning |
| --- | --- |
| `baseline-20261002-031523` | **Pass.** Dev sustained bounded traffic with zero 5xx responses, 95 ms p95 latency, and ready PostgreSQL/Redis signals. |
| `paid-smoke-20261002-043614` | **Pass.** Staging observed `402 → 201 → 302 → replay 409` with a sanitized receipt and no payment identities emitted. |
| `regression-blocked-20261002-050844` | **Expected fail.** A pipeline-produced degraded candidate could not prove paid traffic and stopped before fault injection. |
| `recovery-20261002-052031` | **Pass.** A corrected staging candidate completed all three fault/recovery scorecards and cleanup. |
| `prod-smoke-20261002-060326` | **Pass.** Kargo promotion, Argo CD reconciliation, readiness, liveness, 3/3 app replicas, and stateful dependencies all passed. |

These final bundles are not silently represented by empty directories. Their
status pages point to the report, and their external retention boundary is
explicit.

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
AnalysisRun and gate Job or Pod, then reads all three scorecards. It first tries
the gate Pod's ephemeral result volume and, when a completed Pod can no longer
serve `exec`, recovers the emitted scorecards from the already-sanitized gate
log. Their absence blocks a complete pass claim. Failed or blocked records may
still retain the observed Job/Pod/log without inventing unavailable scorecards;
`unavailable` remains appropriate only for identities genuinely not observable.

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
- `fail`, `blocked`, and `unavailable` establish that the associated release
  claim was not proven; they are not passing outcomes.
- Never overwrite prior evidence. Give every execution a new run ID.
- Preserve the exact source, chart, gate, and runtime identities. Do not use a
  mutable image tag as evidence.
- Do not call a manually patched workload a fully verified release-pipeline
  test. Record it separately as a candidate or regression exercise.
- The sanitizer is a safety layer, not authorization to upload raw diagnostics.
  Review output for sensitive material before it enters Git.

## Final evidence audit

The completed campaign validated 16 metadata records and 238 retained files.
The final scan found no symlinks, raw-named artifacts, sensitive identity
patterns, or suspicious long encoded data. Wallet-key and secret-data
redactions were explicitly recorded where applicable. No raw bundle should be
copied into this directory without repeating that review.
