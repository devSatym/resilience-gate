# Known limitations and non-claims

Resilience Gate is intentionally a small, testnet-only reference platform.
It now has narrow, named staging-testnet records, but those records do not
establish a complete live release system or a production-like release.

## Current verification gap

The repository records selected staging reconciliation, bounded dependency
fault/recovery scoring, cleanup, and direct fail-closed boundary behavior under
[`docs/evidence/`](evidence/README.md). It still lacks an owned dev baseline,
an intentionally degraded **pipeline-produced** candidate, and a
production-like smoke. There is also no release-wide assurance, provisioning
history, or teardown history. Offline tests, static rendering, and local
Compose checks do not close those remaining gaps.

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
- **Controller evidence is scoped.** The named staging records show that the
  selected controllers and runner path operated for those exact executions.
  They do not prove controller installation history, permissions, branch
  access, repository credentials, or reconciliation for every environment.
- **Digest policy still needs supply-chain operation.** A digest-qualified
  manifest does not prove that CI built, signed, retained, or deployed that
  artifact. Those facts need an identity record and live evidence.
- **Payment consistency remains distributed.** Settlement and database
  persistence are not one transaction. A failure after settlement may require
  deliberate reconciliation. One owned-testnet sequence observed
  `402 → signed 201 → replay 409`, but no separately versioned payment-evidence
  bundle is retained, so it is not a settlement, custody, or release claim.

## What would reduce these limits

An approved owned testnet lab should next collect new sanitized records for the
dev baseline, a deliberately degraded pipeline-produced candidate, and the
production-like smoke. Each must bind the same source/render/image identities
seen by the gate and verify that run-scoped resources were cleaned up. Only
then can a release document make a scoped verified claim.
