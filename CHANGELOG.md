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

### Verification status

- No released version is declared by this file.
- No cloud, Kubernetes, Radius testnet, chaos, recovery, or production-like
  run is recorded as passing.
- No v1.0 tag or evidence-backed release claim should be inferred from the
  source changes above.

When an approved lab run exists, its sanitized evidence must be reviewed and
linked here with the tested revisions and digest-qualified artifacts before a
versioned release is announced.
