# Known limitations and non-claims

Resilience Gate is complete for its intended private, owned testnet-lab scope.
The final validation covered source, CI, deployment, paid staging traffic,
negative gating, healthy chaos, recovery, production-like promotion, cleanup,
and evidence hygiene. Completion within that scope does not remove the
following deliberate limits.

## Scope limits

- **Testnet only.** `prod` means a production-like Radius testnet environment.
  There is no mainnet, public-production, regulated-payment, custody, or
  compliance claim.
- **Single owned lab.** The verified topology is one zonal GKE Standard cluster
  with two nodes. Multi-cluster, multi-region, failover, and fleet management
  are outside the project.
- **Bounded chaos.** The gate verifies selected PostgreSQL, Redis, and signer
  pod-failure scenarios in sequence. It does not cover every network partition,
  node outage, control-plane event, data-corruption case, concurrent fault, or
  long-duration degradation.
- **Small observability footprint.** Prometheus, Loki, Alloy, and Grafana are
  sized for a lab. The design does not provide monitoring high availability,
  remote storage, backup restoration, retention compliance, or disaster
  recovery.
- **Single-node data dependencies per environment.** PostgreSQL and Redis use
  persistent storage but are not configured as highly available clusters.
- **Manual consequential promotions.** Staging and prod-like transitions need
  an operator. This improves reviewability but is slower than fully automated
  continuous delivery.

## Security and identity boundaries

- Secret values remain in GCP Secret Manager and are materialized by External
  Secrets Operator. The repository proves reference and access contracts, not
  organizational rotation policy, incident response, or independent secret
  audit.
- Workload Identity and GitHub OIDC avoid long-lived cloud keys in the normal
  path. They do not replace IAM review, GitHub protection rules, or GCP audit
  monitoring.
- Cosign and digest-qualified references prove the configured identity path for
  the recorded candidates. This project does not claim SLSA certification or
  an independently audited software-supply-chain program.
- The private-key signer narrows key exposure, but it is not a hardware wallet,
  HSM, threshold signer, custody system, or production key-management service.

## Payment consistency limits

Settlement and database persistence are not one distributed transaction. A
failure after successful settlement but before URL persistence needs deliberate
reconciliation by settlement identifier. The verified smoke observed
`402 → 201 → 302 → replay 409`; it does not prove every facilitator, RPC,
chain-reorganization, finality, or payer-funding failure mode.

Wallet identities, signatures, payment headers, and transaction identifiers
are deliberately removed from retained summaries. That protects privacy but
means public readers cannot independently inspect the private testnet
transaction from this repository.

## Evidence limits

- Evidence supports only the exact revisions, digests, contexts, windows, and
  scenarios named by each record.
- The detailed final bundles are retained outside Git by default. The
  repository contains selected historical sanitized records and a reviewed
  final summary, not every raw Kubernetes object.
- Screenshots are explanatory artifacts, not authoritative verdicts. The
  underlying status, scorecards, revisions, and cleanup records are the source
  of the claim.
- Live state can drift after the 2 October 2026 snapshot. A later code,
  dependency, controller, configuration, credential, or infrastructure change
  must repeat the relevant checks.

## What productionization would require

Moving beyond the project’s current purpose would be a new scope, not a small
configuration toggle. It would require decisions and testing for regional or
multi-cluster architecture, highly available data stores and telemetry,
backup/restore, SLOs and on-call response, network policy, independent security
review, key custody, payment reconciliation, capacity planning, cost controls,
and a production evidence-retention policy.

The current completion claim remains intentionally precise: the private
testnet release platform was implemented, deployed, and verified end to end.
