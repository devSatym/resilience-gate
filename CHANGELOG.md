# Changelog

All notable changes to Resilience Gate are recorded here. Versions and tags are
created only after the associated evidence checkpoint is actually verified.

## Unreleased

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

### Verification status

- No released version is declared by this file.
- The final source audit recorded 230 project tests and 13 signer tests passing,
  plus five successful GitHub validation runs.
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
- No v1.0 tag, mainnet status, or public-production claim is declared. The
  verified result is scoped to the exact private testnet candidate and snapshot.

Future candidate or platform changes must repeat the relevant validation and
sanitized evidence process before a later versioned release is announced.
