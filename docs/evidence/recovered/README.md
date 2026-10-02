# Recovery evidence

**Status: collected as a scoped staging re-verification.** The chronology
links a retained failed gate record to a fresh Kargo-managed re-verification;
it is not a new application candidate or a production-like promotion.

## Linked records

1. [`20261001-historical-apply-timestamp-failure`](20261001-historical-apply-timestamp-failure/)
   preserves the failed predecessor. Its gate runner could not obtain the
   workflow timestamps needed to score PostgreSQL, Redis, and signer, recorded
   `FAIL`, and entered run-scoped cleanup.
2. [`20261002-staging-recovery-fc2ef08d`](20261002-staging-recovery-fc2ef08d/)
   is a separate fresh Kargo staging re-verification. It uses the same recorded
   source/render/application identity with the corrected gate-runner digest,
   generated its own workflow and scorecards, passed all three experiments, and
   logged cleanup.

The second record demonstrates the corrected gate behavior for that same
staging candidate. It does not claim a new source candidate, baseline,
regression exercise, production-like smoke, or broadly verified release.
