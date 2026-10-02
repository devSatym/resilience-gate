# Contributing to Resilience Gate

## Branch and commit policy

Use a short-lived branch for one coherent change. Branch names follow the
roadmap style, for example `feat/09-observability` or `fix/gate-cleanup`.
Target `main`; do not use a permanent development branch.

Use Conventional Commit subjects:

```text
<type>(<optional scope>): <imperative summary>
```

Common types are `feat`, `fix`, `docs`, `test`, `build`, `ci`, and `chore`.
Keep each commit independently reviewable and runnable. Do not create empty
or backdated commits merely to satisfy a count.

## Validation and safety

Run `./scripts/validate.sh` and focused tests before opening a pull request.
Pull requests must not include secrets, local configuration, cloud state,
generated environment branches, or fabricated evidence.

Documentation that changes a live verification claim must link the exact run,
revision, and evidence boundary. Do not update badges or status language from
expected configuration alone.

`env/dev`, `env/staging`, and `env/prod` are machine-owned rendered branches.
Never merge them into `main` or between each other. Cloud-facing changes require
an explicit review of target project, identity, digest, and fail-closed gate
behavior.

## Evidence

Only an owned testnet lab may generate release evidence. Record the source,
chart, gate-runner, and workload image identities with every run. A missing,
stale, malformed, or incomplete record blocks a release claim.
