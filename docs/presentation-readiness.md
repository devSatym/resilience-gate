# Publication review

Resilience Gate has a documented release, reproducible local checks, reviewed
architecture diagrams, and a captioned screenshot gallery. GitHub reported
the repository as public during the 4 October 2026 documentation review;
this update did not change its visibility. Publication does not change the
owned-testnet scope or the [known limitations](known-limitations.md).

## Presentation package

| Reader goal | Start here |
| --- | --- |
| Understand the project quickly | [Root README](../README.md) |
| See how the platform fits together | [Architecture](kubernetes-architecture.md) and [diagram sources](diagrams/README.md) |
| See release, failure, recovery, and payment behavior | [Screenshot gallery](screenshots/README.md) |
| Check exact candidates and results | [Verification report](verification-report.md) |
| Reproduce local checks | [Demo walkthrough](demo-walkthrough.md) |
| Understand operational boundaries | [Known limitations](known-limitations.md) and [runbooks](runbooks/) |

The October 3 report identifies the validated platform source, tagged
application source, Freight chart source, immutable image, rendered revisions,
and AnalysisRuns separately. Historical charts and negative candidates retain
their dates; they are not relabeled as fresh release results. Detailed sanitized
run bundles remain in a private external archive.

## Owner publication and disclosure review

- Choose whether public reuse is permitted and, if so, select a license. No
  license has been chosen on the owner's behalf.
- Review the committed screenshots and diagrams at full size, including the
  visible project IDs, repository username, and system identities.
- Scan the full Git history for credentials or private material, not only the
  current tree. Ignored configuration and Terraform state remain local.
- Decide whether to enable public-repository protection rules and security
  features. GitHub reported `main` as unprotected at the 4 October review.
- Recheck README badges, links, release visibility, and workflow results after
  documentation updates reach `main`.

The security backlog includes dependency alerts/scanning, a security policy,
CODEOWNERS, immutable action pins, reproducible base images, and
SBOM/provenance generation. These are disclosed engineering follow-ups; the
presentation update does not assert that they have been implemented.
