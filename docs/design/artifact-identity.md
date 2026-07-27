# Artifact identity and immutable delivery policy

**Status:** design and CI contract. It defines what a promotable artifact must
look like; it does not claim that an image has been built, signed, published,
or deployed.

## Core rule

An OCI digest is the deployable identity:

```text
<registry>/<repository>/<image>@sha256:<64-lowercase-hex-characters>
```

A tag is only a human- and tooling-friendly pointer. Tags can be moved, deleted,
or reused; a digest identifies the manifest bytes selected at publication time.
Every promotion, rendered manifest, gate run, and evidence record therefore
uses a digest-qualified reference. A mutable tag is never enough to identify a
release.

This rule applies to the application, signer, load generator where applicable,
and gate-runner image. Packaging gate scripts in the gate-runner image means the
gate itself is also versioned by an image digest instead of a mutable
ConfigMap.

## Identity record

Before an artifact is promotable, CI records an immutable identity tuple. The
exact storage mechanism can evolve, but all fields are required:

```json
{
  "schemaVersion": 1,
  "source": {
    "repository": "<configured-owner/repository>",
    "revision": "<full-git-commit-sha>"
  },
  "image": {
    "repository": "<configured-OCI-repository>",
    "digest": "sha256:<manifest-or-index-digest>",
    "reference": "<configured-OCI-repository>@sha256:<digest>"
  },
  "signature": {
    "scheme": "cosign-keyless",
    "subject": "<digest-qualified-reference>",
    "verified": true
  },
  "build": {
    "workflow": "<trusted-workflow-identity>",
    "run": "<CI-run-identifier>"
  }
}
```

For a multi-platform image, the recorded digest is the OCI index/manifest-list
digest that Kubernetes pulls. The policy does not silently substitute a
platform-specific child digest after signing.

## Publication sequence

1. Pull requests run deterministic validation and image build checks without
   cloud credentials and do not publish a promotable image.
2. A trusted execution from the configured repository and protected ref runs
   the required tests before it receives registry-write credentials through
   GitHub OIDC. No static service-account key is used.
3. CI builds and pushes the image, then captures the build action's emitted
   digest. It must not reconstruct identity from a tag lookup.
4. CI signs that exact digest with keyless Cosign and verifies the signature
   against the expected GitHub issuer, repository, workflow identity, and
   protected ref.
5. CI publishes the identity record only after verification succeeds. A
   failure at any prior step leaves the artifact non-promotable.

Verification policy must be exact enough to reject signatures from another
repository, a fork, an untrusted ref, or an unexpected workflow. A broad
regular expression that accepts any GitHub identity is not an adequate trust
policy.

## Tag policy

| Reference | Permitted purpose | Never permitted purpose |
|---|---|---|
| `sha-<short-source-sha>` | Discovery hint and operator convenience | Deployment identity or proof of content |
| `latest` | Local convenience only, if published at all | Promotion, Kargo Freight, gate input, or evidence |
| `pr-<number>` | Ephemeral CI/debug label | Publication as promotable Freight |
| `buildcache` | Build-cache transport | Runtime deployment |
| `@sha256:…` | Deployment, signature subject, promotion, and evidence | Replacement by a mutable tag |

Kargo may discover a candidate through a constrained `sha-…` tag, but it must
resolve and carry the OCI digest into Freight and rendered environment
manifests. Re-tagging a `sha-…` label after discovery cannot change the version
already selected for a promotion.

## Manifest and promotion requirements

A rendered workload must contain the digest-qualified image reference. Helm,
Kustomize, or a promotion step may accept repository and digest as separate
inputs, but the final Kubernetes manifest must be equivalent to:

```yaml
image: <registry>/<repository>/<image>@sha256:<digest>
```

The promotion record binds at least:

- full source revision;
- application image digest;
- chart/configuration revision;
- gate-runner digest when a chaos gate participates; and
- verified signature identity.

Staging and production-like promotion must reject a candidate when any binding
is absent, malformed, mutable, or inconsistent with the signed identity
record. A later retag, registry cleanup, or Git branch movement must not alter
the manifest already under verification.

## Retention and recovery

Registry cleanup may remove unreferenced images, but it must retain artifacts
needed by active rendered manifests, pending candidates, and recorded evidence.
Build caches and mutable convenience tags receive no such protection. If an
image required to reproduce a recorded result is unavailable, the evidence is
incomplete rather than implicitly satisfied by rebuilding from the same source.

An emergency override is a privileged, auditable operation. It records the
reason, actor, old and new digest-qualified references, and verification result;
it does not change the rule that the runtime reference itself is immutable.

## Evidence boundary

A successful build, signature verification, or manifest render is not a live
release claim. Live testnet evidence is recorded separately only after the
referenced source, chart, gate, and runtime digests are actually exercised in
the owned lab.
