# Release guide

[v1.1.0 — observability and evidence](v1.1.0.md)
· [Changelog](../../CHANGELOG.md)
· [GitHub releases](https://github.com/devSatym/resilience-gate/releases)

Versions identify source snapshots; live evidence identifies its own exact
candidate, chart, rendered revision, image digest, runtime and execution window.
Never transfer a historical pass to a later source release automatically.

## Publishing checklist

1. Review the source delta and choose a semantic version. Keep existing tags
   unchanged. Confirm the worktree is clean and the target is the intended
   reviewed `main` commit, not a machine-owned `env/*` branch.
2. Update the changelog, release notes, limitations and lab status. Review all
   evidence for credentials, wallet data, raw cloud state and private material.
3. Run offline validation and the marked local recovery check:

   ```bash
   PYTHON=.venv/bin/python make validate
   .venv/bin/python -m pytest -m integration tests/integration/test_local_recovery.py
   ```

   If an existing `.terraform` cache references an unavailable backend, isolate
   validation from that cache; do not restore or recreate remote state:

   ```bash
   TF_DATA_DIR="$(mktemp -d -t resilience-gate-validation.XXXXXX)" \
     PYTHON=.venv/bin/python make validate
   ```

4. Merge and push the reviewed documentation branch. Wait for all jobs in
   `Validate local API` to pass at the **exact final source commit**. Do not
   invoke image-publication workflows against deleted cloud resources.
5. Create an annotated version tag at that exact validated commit and push only
   that tag. Inspect its peeled commit on GitHub before publishing.
6. Build release assets from explicitly selected **tracked files** at the tag,
   not from a working-directory archive. Include a checksum and verify the ZIP
   inventory; never include ignored configuration, Terraform state, raw evidence,
   wallet keys or credential-bearing identity files.
7. Publish with `gh release create --verify-tag`, an explicit title, reviewed
   notes, source/CI links and assets. Set the appropriate latest/prerelease status.
8. Recheck the remote tag, release, asset names/checksums and repository links.

## Current workflow boundary

At `v1.1.0`, the four workflows filter push events to `main`; none subscribes
to tag pushes or release publication. Documentation-only updates trigger local
validation and Docker builds. Application/signer/gate input changes on `main`
or manual image-workflow dispatch can attempt GAR/OIDC/Cosign publication.
Re-audit these triggers before every future release; this is not a permanent
guarantee about later workflow versions.

The [retired lab](../lab-retirement.md) is not recreated by a release. Any new
live deployment or paid testnet campaign requires separate explicit approval
and its own evidence. The owner selected [Apache 2.0](../../LICENSE) for this
source release; older tags were not rewritten. Protection policies remain
owner decisions.
