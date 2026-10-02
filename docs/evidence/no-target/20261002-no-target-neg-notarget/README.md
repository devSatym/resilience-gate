# No-target direct boundary test — 2026-10-02

**Outcome:** `blocked`.

This manually created direct Job ran the deployed staging gate runner against
intentionally nonexistent Service `rg-negative-no-target`. It is annotated as a
manual boundary test, not created by Kargo and not a promotion or verification
result. The runner acquired its Lease, found no ready endpoint, refused a
vacuous fault, and released the Lease.

Reviewed artifacts:

- [`run-metadata.json`](run-metadata.json) — schema-validated identity and
  `blocked` status.
- [`gate.log`](gate.log) — sanitized preflight and cleanup output.

No Workflow, load Job, fault, traffic, telemetry score, or payment flow is
claimed for this test.
