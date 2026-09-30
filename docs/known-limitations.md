# Known limitations and non-claims

Resilience Gate is intentionally a small, testnet-only reference platform.
The source is useful for studying delivery and verification boundaries, but it
does not yet establish a live release system.

## Current verification gap

There is no recorded owned-lab execution for cloud provisioning, cluster
bootstrap, GitOps reconciliation, artifact publication, signer startup,
facilitator settlement, load generation, fault injection, telemetry scoring,
cleanup, recovery, or production-like smoke. Offline tests, static rendering,
and local Compose checks do not close this gap.

## Deliberate scope limits

- **Testnet only.** `prod` means a production-like testnet environment. There
  is no mainnet, public-production, financial-custody, or compliance claim.
- **No secret material in Git.** Secret values, wallet keys, authorization
  headers, and Kubernetes Secret data must remain outside this repository.
  That improves source hygiene but leaves secret-backend setup and rotation as
  live operational work.
- **Small observability footprint.** The configured Prometheus/Loki/Alloy
  stack is sized and structured for a bounded lab, not multi-zone high
  availability, backup restoration, retention compliance, or disaster
  recovery.
- **Bounded chaos scope.** The gate focuses on selected dependency-failure
  scenarios with a fixed time budget. It does not prove resilience to every
  network partition, node failure, data-corruption event, concurrent fault, or
  long-duration degradation.
- **Promotion contracts are not controller state.** Kargo and Argo CD manifests
  describe desired behavior. They do not prove controller installation,
  permissions, branch access, repository credentials, or reconciliation.
- **Digest policy still needs supply-chain operation.** A digest-qualified
  manifest does not prove that CI built, signed, retained, or deployed that
  artifact. Those facts need an identity record and live evidence.
- **Payment consistency remains distributed.** Settlement and database
  persistence are not one transaction. A failure after settlement may require
  deliberate reconciliation, and no live payment behavior is recorded here.

## What would reduce these limits

An approved owned testnet lab should first run the documented preflight and
bootstrap checks, then collect a new sanitized record for each required
baseline, negative scenario, recovery, and production-like smoke. Each record
must bind the same source/render/image identities seen by the gate and verify
that run-scoped resources were cleaned up. Only then can a release document
make a scoped verified claim.
