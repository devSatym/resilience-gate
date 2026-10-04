# Owned-lab retirement — 4 October 2026

The owner authorized irreversible deletion of the Resilience Gate GCP lab and
its data. Active lab resources were removed through the authenticated GCP CLI;
Terraform was reconciled before the remote backend was deleted. A separate
read-only audit checked cloud inventory and the preserved unrelated resources.

This is a retirement receipt, not a new chaos test or production certification.
The [verification report](verification-report.md) and
[screenshot gallery](screenshots/README.md) retain their October 2–3 candidate,
digest and time-window boundaries. There is no active hosted lab demo.

## Deletion scope

| Resource group | Final observed result |
| --- | --- |
| GKE and compute | Lab cluster, node pool, both node VMs/boot disks, instance group/template and lab firewalls removed. |
| Workload storage | All eight resolved lab PersistentVolume disks deleted, including databases and telemetry data. |
| Lab networking | Dedicated subnet and VPC removed; no lab address, router or load-balancer objects remain. |
| Artifact Registry | Dedicated image repository and stored images deleted. Historical digests remain identity records, not downloadable cloud assets. |
| Secret Manager | All 26 lab secrets and versions deleted, including three cloud-stored wallet-key copies. Values were not printed or exported. |
| IAM | Four dedicated service accounts deleted; seven project grants removed; parent-scoped registry and service-account bindings removed with their parents. |
| GitHub federation | Lab pool/provider deleted and inactive, subject to Google's recovery window. |
| Terraform | Original 30 managed entries reconciled to zero resources and zero outputs, serial 17. A private final-state receipt was retained locally. |
| Remote backend | All live/noncurrent state and lock object generations removed and bucket deleted from live inventory; recovery retention below remains. |

The repository, local screenshots, sanitized evidence and private backups were
preserved. Unrelated InfraRun/TerraRun services, repositories, identities and
state buckets were outside scope and remained intact. Shared project APIs were
left enabled intentionally (`disable_on_destroy=false`); the GCP project and
Google-managed GKE workload pool were not deleted.

## Mandatory recovery retention

Active-resource deletion is **not immediate permanent purge of every recovery
record**. The final deep audit observed:

- The deleted Terraform backend bucket's scheduled hard-delete time is
  **11 October 2026, 10:22:36 UTC / 15:52:36 IST**.
- The inactive GitHub workload-identity pool's recovery expiry is
  **3 November 2026, 10:10:15 UTC / 15:40:15 IST**. Deleted service accounts
  also have Google's normal recovery window.

The backend's future soft-delete policy was cleared before recursive removal.
Nevertheless, Google retains a deleted bucket until at least its latest
retained object's hard-delete time. The exact retained object identities were
not inspected: that would require restoring the deleted bucket. No restore was
performed, and an earlier hypothesis that this was an older bucket generation
was disproved by direct API metadata.

These are the scheduled times observed at retirement, not an assertion that a
later purge has already occurred. Google does not provide early hard purge of
these soft-deleted bucket records. See
[retained-bucket behavior](https://docs.cloud.google.com/storage/docs/use-soft-deleted-buckets),
[non-retroactive policy changes](https://docs.cloud.google.com/storage/docs/soft-delete),
and [identity recovery](https://docs.cloud.google.com/iam/docs/manage-workload-identity-pools-providers).

Historical audit logs and billing records were not erased. Unrelated services
and retained data can still appear in project billing; this receipt makes no
zero-whole-project-cost claim.

## Reproduction after retirement

Use the [offline walkthrough](demo-walkthrough.md) and
[local-development runbook](runbooks/local-development.md) for source checks.
A new live deployment requires new explicit owner authorization, configuration,
identities, secrets, registry, Terraform backend and scoped validation. Neither
publishing `v1.1.0` nor viewing historical screenshots recreates the lab.
