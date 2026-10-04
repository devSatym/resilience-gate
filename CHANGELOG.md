# Changelog

All notable changes to Resilience Gate are recorded here. Versions and tags are
created only after the associated evidence checkpoint is actually verified.

## Unreleased

No unreleased changes recorded.

## 1.1.0 — 2026-10-04

[GitHub release](https://github.com/devSatym/resilience-gate/releases/tag/v1.1.0)
· [Release notes](docs/releases/v1.1.0.md)
· [Compare with v1.0.0](https://github.com/devSatym/resilience-gate/compare/v1.0.0...v1.1.0)

### Added

- Apache 2.0 licence and project attribution notice, selected by the owner;
  third-party dependencies retain their original licences.
- Focused Grafana dashboards for application traffic, payments, infrastructure,
  and release-gate evidence, with privacy-safe wallet-index labels.
- A reviewed screenshot gallery and architecture diagrams linked from the
  project README, plus an updated October 3 verification report.
- The original architecture, promotion and chaos-gate illustrations restored
  in the README, with earlier design labels distinguished from current runtime
  configuration.
- Offline documentation checks for links, screenshot hashes and review status,
  and accessible SVG artwork generated from deterministic sources.
- A security reporting policy, structured bug/enhancement issue forms, and
  release guidance. Repository topics and documentation entry points now
  describe the implemented platform.
- An explicit lab-retirement receipt separating historical verification from
  the active-resource deletion and mandatory cloud recovery-retention records.

### Fixed

- GKE CoreDNS monitoring now scrapes the kube-dns sidecar metrics endpoint.
- Grafana separates application restart evidence from dependency readiness,
  preventing a dependency fault from being mislabeled as an app restart.
- Payment panels and chaos-log queries now match implemented metric names and
  the gate runner's namespace/container labels.

### Verified

- Source snapshot `7ea5e91` passed 231 project tests, 13 signer tests, and the
  full local platform validation. The marked local recovery integration check
  also passed in [GitHub validation run 37123284920](https://github.com/devSatym/resilience-gate/actions/runs/37123284920).
- On 3 October 2026, release Freight `d3b4380...` completed a fresh staging
  chaos verification and a separately approved prod-like readiness/liveness
  verification. Dev, staging, and prod ended on the same Freight.
- The current campaign produced two sanitized evidence bundles and 34 reviewed
  screenshots. Historical October 2 failure and recovery evidence remains
  explicitly labeled. See the [verification report](docs/verification-report.md)
  and [screenshot gallery](docs/screenshots/README.md).
- Presentation snapshot `2420ff4` passed all three jobs in
  [CI run 37188456168](https://github.com/devSatym/resilience-gate/actions/runs/37188456168).
  The published release's exact source and subsequent CI receipt are recorded
  in its GitHub release notes.

These changes follow the unchanged `v1.0.0` tag. The October 3 live verification
used the `v1.0.0` application; it is not evidence of a `v1.1.0` deployment or
new image publication. The GCP lab was retired on October 4. GitHub secret
scanning, push protection, dependency vulnerability alerts and private reporting
were enabled during this repository review; enabling them is not a completed
independent security audit.

## 1.0.0 — 2026-10-02

[GitHub release](https://github.com/devSatym/resilience-gate/releases/tag/v1.0.0)
at source commit `3b70835335462f1b6f9b1dd17ab20d1108724f89`.

### Added

- Source contracts for the URL-shortener, x402/Permit2 signer, immutable image
  identity, Helm delivery, GitOps/Kargo promotion, observability, and bounded
  chaos scoring.
- Guarded platform bootstrap configuration that renders public operator
  identifiers for review while keeping local configuration and secret values
  out of Git.
- Evidence-status templates for baseline, chaos, blocked-path, recovery, and
  production-like smoke scenarios.
- Architecture, failure-model, limitations, and offline-demo documentation.
- A completed owned-testnet verification campaign covering dev baseline,
  staging paid traffic, negative regression gating, corrected chaos/recovery,
  production-like promotion, cleanup, and evidence hygiene.
- A canonical documentation index, configuration reference, and final
  verification report.

### Verified scope

- The October 2 verification campaign recorded 230 project tests and 13 signer
  tests passing at its audited platform snapshot, followed by successful
  validation and image-publication workflows for the tagged release source.
- The private lab snapshot recorded two Ready `e2-standard-4` GKE nodes, eight
  Synced/Healthy Argo CD Applications, and successful latest verification for
  all three Kargo Stages.
- Dev baseline, paid staging smoke, deliberately degraded candidate rejection,
  corrected staging chaos/recovery, and production-like readiness/liveness
  verification all completed. See the
  [verification report](docs/verification-report.md).
- Four direct boundary tests additionally record fail-closed behavior for no
  target, unavailable load source, telemetry transport error, and shortened
  timeout/cleanup.
- `v1.0.0` is an owned-testnet release. It makes no mainnet or public-production
  claim; every verified result is scoped to its recorded candidate and snapshot.

Future candidate or platform changes must repeat the relevant validation and
sanitized evidence process before a later versioned release is announced.
