# Changelog

All notable changes to Resilience Gate are recorded here. Versions and tags are
created only after the associated evidence checkpoint is actually verified.

## Unreleased

### Added

- Focused Grafana dashboards for application traffic, payments, infrastructure,
  and release-gate evidence, with privacy-safe wallet-index labels.
- A reviewed screenshot gallery and architecture diagrams linked from the
  project README, plus an updated October 3 verification report.
- The original architecture, promotion and chaos-gate illustrations restored
  in the README, with earlier design labels distinguished from current runtime
  configuration.

### Fixed

- GKE CoreDNS monitoring now scrapes the kube-dns sidecar metrics endpoint.
- Grafana separates application restart evidence from dependency readiness,
  preventing a dependency fault from being mislabeled as an app restart.

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

These changes follow the immutable `v1.0.0` tag. A documentation update or a
later successful lab run does not move that tag or announce a new release.

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
