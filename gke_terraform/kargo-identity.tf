# Kargo only needs to discover and read private image revisions. Keep this
# identity separate from ESO (Secret Manager) and CI (writer) to preserve
# least privilege and make its Kubernetes annotation explicit for bootstrap.
resource "google_service_account" "kargo_registry_reader" {
  project      = var.project_id
  account_id   = "kargo-gar-reader"
  display_name = "Resilience Gate Kargo registry reader"
  description  = "Reads release images from the private Artifact Registry through Workload Identity."
}

resource "google_artifact_registry_repository_iam_member" "kargo_registry_reader" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.kargo_registry_reader.email}"
}

resource "google_service_account_iam_member" "kargo_workload_identity_binding" {
  service_account_id = google_service_account.kargo_registry_reader.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.kargo_kubernetes_namespace}/${var.kargo_kubernetes_service_account}]"

  depends_on = [google_container_cluster.gke_cluster]
}
