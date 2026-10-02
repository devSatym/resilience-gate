# Chaos-gate verification runbook

**Status: verified operating procedure.** The final owned-testnet campaign used
this path for baseline, deliberately degraded staging, corrected chaos/recovery,
and production-like smoke. Historical and final status are indexed under
[evidence](../evidence/README.md); a later candidate still needs a fresh run.

Use this runbook only for the explicitly owned Resilience Gate testnet lab. A
namespace named `prod` is a production-like testnet boundary, never a mainnet
or public-production target.

## Verify the configured platform first

`07-verify.sh` is a read-only prerequisite check. It loads the supplied local
configuration, requires the exact configured GKE context, and inspects public
Kubernetes resource state. It does not read Secret values, promote Freight,
sync an application, create a Job, run a workflow, or contact the testnet.

```bash
./platform_setup_scripts/07-verify.sh \
  --config platform_setup_scripts/config.env \
  --scope all
```

The available scopes keep an investigation narrow:

| Scope | Intended checks |
| --- | --- |
| `platform` | Platform namespaces and controller/secret-store readiness signals. |
| `gitops` | Reviewed Argo CD and Kargo configuration objects. |
| `gate` | The scoped chaos-gate identity and verification configuration. |
| `all` | All of the above; this is the default scope. |

A context mismatch is a hard stop. Do not work around it by changing the
current context implicitly or by supplying a different namespace. Correct the
operator configuration and rerun the read-only check instead.

A zero exit status means only that the script's current resource checks
completed successfully. It does not prove that controllers reconciled a
candidate, that telemetry is valid, that a chaos workflow ran, or that a
release is promotable.

## Select the right verification path

First review the no-network plan for the intended scenario:

```bash
./scripts/validate-live.sh --plan --scenario chaos-gate
```

The scenario determines the reviewed Kargo Stage and namespace:

| Scenario | Stage and namespace | Verification contract |
| --- | --- | --- |
| `baseline` | `dev` / `url-shortener-dev` | Normal service-health verification. |
| `chaos-gate`, `regression-blocked`, `recovery` | `staging` / `url-shortener-staging` | Service-health and the bounded chaos gate. |
| `prod-smoke` | `prod` / `url-shortener-prod` | Production-like testnet post-deploy health check. |

Only an approved operator may request the real Kargo verification path, and
only after reviewing the target, Freight, current context, and testnet budget:

```bash
./scripts/validate-live.sh --execute \
  --acknowledge-owned-testnet-lab \
  --scenario chaos-gate \
  --config platform_setup_scripts/config.env
```

For a named staging candidate, `--promotion-freight` additionally requires
`--acknowledge-staging-promotion`. The runner requests the Kargo Stage contract;
it does not directly create an AnalysisRun, Chaos Mesh workflow, load Job, or
patched workload. Acceptance of that request is not a passing gate verdict.

Never represent a manually patched workload as a fully verified release
pipeline result. Record it separately as a candidate or regression exercise.

## Collect evidence only after the observed result

After a real bounded run, use the collector's plan mode first, then collect
only the exact objects and immutable identities that were observed. Keep raw
diagnostics and Secret material out of the repository.

```bash
./scripts/collect-evidence.sh --plan \
  --scenario chaos-gate \
  --status unavailable \
  --run-id <new-run-id>
```

See [evidence handling](../evidence/README.md) for the required metadata,
sanitization rules, and collection command. Do not fill a `pass` status from
expectation: it needs the completed AnalysisRun, scorecards, and verified
run-scoped cleanup for that particular run ID.

## Failure handling

Stop when the verifier reports a failed prerequisite, Kargo rejects a request,
the gate blocks or fails, telemetry is absent or stale, or cleanup cannot be
verified. Preserve sanitized observations, record `fail`, `blocked`, or
`unavailable` as appropriate, and investigate the failed layer before retrying.
Do not broaden the fault scope, load budget, wallet funding, or target
environment to turn a failed result into a pass.
