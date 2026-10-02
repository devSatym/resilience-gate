# Telemetry-transport scorer boundary test — 2026-10-02

**Outcome:** `fail`.

This manually created scorer-only direct Job ran the PostgreSQL scorecard
against deliberately unreachable loopback endpoint `http://127.0.0.1:1`. It is
not a Kargo verification, a Workflow/load/fault exercise, or a promotion. Five
telemetry checks failed with `query_transport_error` / connection refused, and
the final scorecard verdict was `fail`.

Reviewed artifacts:

- [`run-metadata.json`](run-metadata.json) — schema-validated identity and
  `fail` status.
- [`scorer.log`](scorer.log) — sanitized failed scorecard output.

It demonstrates fail-closed handling for the supplied unreachable endpoint;
it does not represent an outage of shared Prometheus or real cluster telemetry.
