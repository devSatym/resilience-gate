resource "google_project_service" "secret_manager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

# ESO reads Secret Manager through Workload Identity. It has no service-account
# key and is intentionally separate from the Kargo registry-reader identity.
resource "google_service_account" "external_secrets" {
  project      = var.project_id
  account_id   = "external-secrets-sa"
  display_name = "Resilience Gate External Secrets"
  description  = "Reads Secret Manager values for External Secrets Operator through Workload Identity."
}

resource "google_project_iam_member" "external_secrets_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.external_secrets.email}"

  depends_on = [google_project_service.secret_manager]
}

resource "google_service_account_iam_member" "eso_workload_identity_binding" {
  service_account_id = google_service_account.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.eso_kubernetes_namespace}/${var.eso_kubernetes_service_account}]"

  # GKE creates the workload-identity pool with the cluster. Waiting for it
  # prevents a first-apply race while the pool is becoming available.
  depends_on = [google_container_cluster.gke_cluster]
}
