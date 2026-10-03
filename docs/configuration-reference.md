# Configuration reference

This reference describes the reviewed, non-secret configuration surface for
Resilience Gate. Secret values are intentionally excluded. The active private
lab is configured locally through ignored files and GCP Secret Manager.

## Platform topology

| Setting | Reviewed value or policy |
| --- | --- |
| Cloud | Google Cloud Platform |
| Cluster type | Zonal GKE Standard |
| Region / zone | `us-central1` / `us-central1-a` |
| Cluster name | `resilience-gate` |
| General node pool | 2 × `e2-standard-4`, 50 GiB boot disks |
| Node image | `COS_CONTAINERD` |
| Upgrade policy | Auto-repair, auto-upgrade, surge 1, unavailable 0 |
| Workload identity | GKE Workload Identity enabled |
| Registry | Artifact Registry repository `resilience-gate` |
| Repository | `https://github.com/devSatym/resilience-gate.git` |
| Terraform state | Versioned GCS backend supplied at init time |
| Deletion protection | Enabled by default |

The GCP project identifier and project number are environment-specific public
operator inputs and are not repeated in canonical documentation. Terraform
validates all topology inputs before planning.

## Environment profiles

| Environment | App replicas | PDB | Placement | Verification | Promotion |
| --- | ---: | --- | --- | --- | --- |
| `dev` | 1 | Disabled | No anti-affinity or spread requirement | Service readiness | Automatic |
| `staging` | 2 | `minAvailable: 1` | Preferred anti-affinity and topology spread | Service readiness + paid-traffic chaos gate | Manual |
| `prod` | 3 | `minAvailable: 2` | Preferred anti-affinity and topology spread | Post-deploy readiness + liveness | Manual |

Every environment uses PostgreSQL and standalone Redis with persistent storage.
The `prod` name is testnet-only and never authorizes a mainnet deployment.

## Resource profiles

| Workload | Requests | Limits |
| --- | --- | --- |
| Dev app | 50m CPU, 64 MiB | 200m CPU, 256 MiB |
| Staging app | 100m CPU, 128 MiB | 500m CPU, 512 MiB |
| Prod app | 200m CPU, 256 MiB | 1 CPU, 1 GiB |
| Permit2 signer | 100m CPU, 192 MiB | 500m CPU, 512 MiB |
| k6 load generator | 250m CPU, 256 MiB | 1 CPU, 1 GiB |
| Chaos gate runner | 100m CPU, 128 MiB | 500m CPU, 512 MiB |

Application and gate containers run as non-root users, drop Linux capabilities,
disable privilege escalation, use read-only root filesystems, and opt out of
service-account tokens unless Kubernetes API access is required.

## Payment profile

| Setting | Value |
| --- | --- |
| Network | Radius testnet, CAIP-2 `eip155:72344` |
| Facilitator | Radius testnet x402 facilitator |
| Transfer scheme | x402 v2 exact payment with Permit2 |
| Payment amount | `1000` atomic token units |
| App timeout | 10 seconds |
| Signer authorization deadline | Maximum 300 seconds |
| Load wallets | Maximum 3 bounded testnet payer identities |

Addresses, wallet identities, transaction identifiers, signatures, and payment
headers are deliberately omitted from documentation and evidence summaries.

## Load and chaos bounds

The committed CronJob is always suspended and also uses an impossible schedule
as a second guard. Operators create one uniquely named Job from its template.

| Setting | Default bound |
| --- | --- |
| Load profile | Arrival rate |
| Arrival rate | 60 iterations per minute |
| Virtual users | Maximum 3 |
| Duration | Maximum 10 minutes |
| Load Job deadline | 780 seconds |
| Gate Job deadline | 1,320 seconds |
| Cleanup verification | 120 seconds |
| Chaos order | Warm-up → PostgreSQL → Redis → signer → settle/cleanup |

The gate requires ready endpoints, exclusive Lease ownership, a suspended
source CronJob, valid immutable identity, proven paid traffic, valid telemetry,
observed dependency failure, observed recovery, and verified cleanup.

## Observability profile

- Prometheus retention: 7 days, bounded by 8 GB, backed by a 10 GiB PVC.
- Loki: single-binary filesystem mode, 72-hour retention, 10 GiB PVC.
- Alloy: one Kubernetes-API log collector replica.
- Grafana: four UTC dashboards loaded through labeled ConfigMaps; credentials
  supplied by External Secrets:
  - `resilience-gate-app` — HTTP health, latency, dependencies, and cache;
  - `resilience-gate-chaos` — fault windows, recovery, restarts, and scoped logs;
  - `resilience-gate-runtime` — replicas, pod readiness, resources, and scrapes;
  - `resilience-gate-payments` — x402, facilitator, and signer signals.
- Wallet readiness panels aggregate only by `wallet_index`; address labels and
  raw balances are intentionally excluded from the displayed series.
- Application ServiceMonitors are restricted to dev, staging, and prod
  namespaces and selected by the `release: observability` label.

This is intentionally a small-lab profile, not a highly available monitoring
service or disaster-recovery design.

## Controller versions

| Component | Pinned version |
| --- | --- |
| cert-manager chart | `v1.16.2` |
| Argo CD chart | `7.7.11` |
| Argo Rollouts chart | `2.43.1` |
| External Secrets chart | `1.3.2` |
| Kargo chart | `1.3.0` |
| Chaos Mesh chart | `2.8.2` |
| kube-prometheus-stack dependency | `91.4.0` |
| Loki dependency | `7.3.0` |
| Alloy dependency | `1.12.1` |
| PostgreSQL dependency | `18.5.7` |
| Redis dependency | `25.3.5` |
| k6 runtime | `0.54.0` image pinned by digest |

The lock files and immutable container digests remain the source of truth.
Review compatibility and rerun validation before changing a version.

## Local public configuration

Create the ignored operator file from the example:

```bash
make config
$EDITOR platform_setup_scripts/config.env
make render-config
git diff -- kubernetes/
```

The file supplies public values such as project, repository, region, zone,
cluster, registry, state bucket, and reviewed signer/gate-runner digests. It
contains secret *names*, never secret values.

## Secret delivery

GCP Secret Manager is the backing store. External Secrets Operator uses GKE
Workload Identity through the `resilience-gate-secrets` ClusterSecretStore.
The referenced categories are:

- Git repository credentials;
- Grafana admin credentials;
- per-environment database and Redis connection material;
- per-environment service-wallet address material;
- staging testnet RPC configuration; and
- staging signer payer keys.

Do not place those values in Terraform variables, Helm values, `config.env`,
shell history, evidence, screenshots, or Git. The canonical names are defined
by `platform_setup_scripts/config.env.example` and the ExternalSecret
manifests.

## Rendered and runtime identity

Committed environment values contain safe placeholder registries and digests.
Kargo replaces them using Freight, renders plain Kubernetes YAML, commits it to
`env/<stage>`, and asks Argo CD to synchronize the exact rendered commit. The
running Deployment must remain digest-qualified.

The image tag `sha-<source>` is a discovery hint only. OCI digest, full source
revision, rendered revision, and runtime image ID are the identities used for
verification and evidence.
