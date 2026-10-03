# Artifact identity and immutable delivery contract

**Status:** implemented CI and promotion contract, exercised by the owned
testnet validation campaign. The recorded result binds source, rendered
revision, digest-qualified runtime images, and gate identities. A new candidate
must produce a new identity and verification record.

CI verifies Cosign signatures at publication. Kargo and Argo CD consume
digest-qualified images, but the current lab has no admission controller or
promotion step that re-verifies those signatures. `main` is the allowed
publication ref; GitHub branch protection is not enabled on the current
private repository plan. These are separate trust boundaries.

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

After a successful publication and signature verification, CI records an
immutable identity tuple. All fields below are required by the CI record:

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
2. A trusted execution from the configured repository and allowed `main` ref runs
   the required tests before it receives registry-write credentials through
   GitHub OIDC. No static service-account key is used.
3. CI builds and pushes the image, then captures the build action's emitted
   digest. It must not reconstruct identity from a tag lookup.
4. CI signs that exact digest with keyless Cosign and verifies the signature
   against the expected GitHub issuer, repository, workflow identity, and
   allowed ref.
5. CI publishes the identity record only after verification succeeds. A
   signing failure produces no verified record, although the preceding push
   may already have placed an image and discovery tag in the registry.

Verification policy must be exact enough to reject signatures from another
repository, a fork, an untrusted ref, or an unexpected workflow. A broad
regular expression that accepts any GitHub identity is not an adequate trust
policy.

The configured OIDC trust and exact Cosign workflow identity constrain the
publication path. They do not enforce code review or protected-branch rules.
An owner review is needed before changing repository visibility or widening
that trust boundary.

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

The reviewed release evidence binds at least:

- full source revision;
- application image digest;
- chart/configuration revision;
- gate-runner digest when a chaos gate participates; and
- verified signature identity.

Kargo carries the selected application digest and chart-source revision into
rendered manifests; staging gate evidence records the configured runtime
digests separately. Stage eligibility also depends on upstream verification.
A later retag or Git branch movement cannot replace the digest already selected
for that promotion.

The current Warehouse discovers `sha-*` images without checking Cosign or
requiring the CI identity artifact. No Kubernetes admission policy verifies
signatures at pull/deploy time. Consequently, the record establishes what CI
signed and verified for the reviewed candidate; it is not a cluster-wide
unsigned-image rejection policy. Enforcing the signed identity as a prerequisite
to discovery and deployment is a future hardening step.

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
release claim. The completed testnet campaign separately exercised and recorded
the referenced source, rendered revision, gate, and runtime identities. See the
[verification report](../verification-report.md). Future artifacts remain
unverified until they repeat that path.
