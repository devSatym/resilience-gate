# Promotion failure model and trade-offs

**Status: design contract.** This is a model for interpreting a future
Resilience Gate run, not a record that any promotion, fault, payment, or
recovery has occurred.

## Claim state is narrower than deployment state

A candidate can be rendered, built, signed, or even reconciled without being a
verified release. The meaningful states are deliberately separate:

```text
source reviewed
  -> immutable identity recorded
  -> environment render reviewed
  -> target reconciled and healthy
  -> bounded chaos evidence complete
  -> production-like smoke complete
  -> evidence-backed claim
```

Failure at any arrow leaves the later claim unestablished. In particular, a
unit-test pass cannot replace an owned-lab run, and a manually patched
workload cannot represent the normal promotion path.

## Classification rules

| Classification | Meaning | May support a passing release claim? |
| --- | --- | --- |
| `pass` | All required live evidence for the named scenario is complete and internally consistent. | Only for that exact identity and scope. |
| `fail` | A scored condition or verified action did not meet its contract. | No. It can be valuable negative evidence. |
| `blocked` | A safety precondition was not met: for example, no target, active lock, unavailable load, or unresolved configuration. | No. A block is not a healthy result. |
| `unavailable` | The scenario was not run because the necessary owned lab or dependency was unavailable. | No. It records absence honestly. |
| not collected | No run metadata or artifacts exist at all. | No. This is the current status for the final evidence scenarios. |

The shared run-metadata schema has a deliberate, limited scenario vocabulary.
Subcases such as missing telemetry, no target, load failure, and cleanup
timeout should be described in their run artifacts and scenario status rather
than fabricated as schema-valid successful runs.

## Boundary failures and expected handling

### Identity boundary

The source revision, chart/configuration revision, rendered branch revision,
and digest-qualified image identity must describe the same candidate. A tag,
branch name, or dashboard screenshot alone is insufficient because each may
move independently. If any binding is absent or differs, stop and record a
blocked/invalid result instead of selecting a replacement artifact.

### Environment boundary

The bootstrap design requires rendered public configuration and an exact target
context. A context match protects against an accidental operator target but
does not turn the target into a validated lab. Secrets remain external to the
repository; a successful render does not mean their backing values exist or
are correct.

### Workload boundary

Process liveness, readiness, and dependency availability answer different
questions. The URL shortener keeps `/livez` process-only while `/ready`
requires its readiness dependencies. A ready result before fault injection is
therefore necessary but does not prove resilience during a fault.

### Measurement boundary

The scorer treats collection defects as safety defects. Empty time series,
invalid response shapes, non-finite samples, insufficient coverage, and stale
samples all block a pass. This intentionally makes telemetry outages visible,
but it also means an observability issue can halt promotion even if the
application would otherwise appear healthy.

### Fault and cleanup boundary

The gate design scopes workflows, jobs, and its Lease by run identity. A
missing ready target or a competing run stops before fault injection. On every
exit path, only objects identified for that run are cleaned, then checked
absent. If cleanup is uncertain, the gate must retain a failing result for
human investigation rather than allowing a future run to sweep broadly.

### Payment boundary

The application validates client headers and facilitator responses, while the
signer keeps key material at a dedicated service boundary. This narrows the
exposure surface but cannot make an unfunded wallet, unavailable facilitator,
or post-settlement database failure disappear. A future incident record must
distinguish those conditions rather than misclassifying them as an application
or chaos success.

## Chosen trade-offs

| Choice | Benefit | Cost or non-goal |
| --- | --- | --- |
| Testnet-only environments | Limits financial and blast-radius scope. | No mainnet or production-service assurance. |
| Manual staging and production-like transitions | Makes consequential moves explicit and reviewable. | Slower than a fully automatic pipeline. |
| Bounded, sequential chaos workflow | Keeps a failure run attributable and cleanable. | Does not explore every dependency combination or long-duration outage. |
| Strict telemetry validity | Prevents a quiet monitoring failure from producing a false pass. | Telemetry availability itself becomes a promotion dependency. |
| Digest-pinned rendering | Makes a candidate reproducible after tag movement. | Requires registry retention and accurate identity capture. |
| External secret references | Keeps secret values out of Git and rendered public configuration. | Correctness of the secret backend is still a live operational dependency. |
| Single-node-style observability settings | Fits a small learning/testnet lab. | Not a high-availability, backup, or disaster-recovery solution. |

## Recovery standard

Recovery is a new claim, not an edit to an old result. A valid recovery record
needs a linked failed or blocked predecessor, an explicit corrective revision,
new immutable identities, and a separate complete run. Reusing old traffic,
scorecards, or cleanup output would hide a change in the candidate and is not
acceptable evidence.
