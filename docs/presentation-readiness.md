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

- The owner selected [Apache 2.0](../LICENSE) for the new source release.
  Preserve the [NOTICE](../NOTICE) and third-party attribution when distributing.
- Review the committed screenshots and diagrams at full size, including the
  visible project IDs, repository username, and system identities.
- Scan the full Git history for credentials or private material, not only the
  current tree. Ignored configuration and Terraform state remain local.
- Review remaining public-repository protection rules. GitHub reported `main`
  as unprotected at the 4 October review; no restriction was imposed on the
  owner's direct-merge workflow or machine-owned `env/*` branches.
- Recheck README badges, links, release visibility, and workflow results after
  documentation updates reach `main`.

## October 4 repository release review

- About description, documentation homepage and 20 implementation-related
  topics were populated.
- Apache 2.0 and an attribution notice were added following the owner's
  explicit licence choice; no older tag was rewritten.
- Secret scanning, secret push protection, dependency vulnerability alerts and
  private vulnerability reporting were enabled and checked through GitHub.
  Automatic dependency-fix PRs were not enabled.
- A [security policy](../SECURITY.md) and structured bug/enhancement issue forms
  were added, with a prohibition on publishing credentials or private evidence.
- The [v1.1.0 release](releases/v1.1.0.md) preserves the `v1.0.0` tag and its
  original runtime evidence. Current CI/release badges link to GitHub status.
- The [lab retirement](lab-retirement.md) is explicit: screenshots represent
  historical observations and mandatory cloud recovery records remain separate
  from deleted active resources.

The remaining security backlog includes full-history credential review,
branch protection, CODEOWNERS, immutable action pins, reproducible base images,
SBOM/provenance generation and ongoing vulnerability triage. Enabled scanning
is not evidence of a completed security audit. The licence was selected
explicitly by the owner, not inferred from public repository visibility.
