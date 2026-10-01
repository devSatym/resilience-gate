# Kargo 1.3 discovers GAR revisions by impersonating a GSA with this exact,
# project-derived name. Keep it distinct from ESO and CI identities so the
# controller can read only this Kargo project's repository.
resource "google_service_account" "kargo_project_registry_reader" {
  project      = var.project_id
  account_id   = "kargo-project-resilience-gate"
  display_name = "Resilience Gate Kargo project registry reader"
  description  = "Kargo's project-specific identity for reading release images from the private Artifact Registry."
}

resource "google_artifact_registry_repository_iam_member" "kargo_project_registry_reader" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.kargo_project_registry_reader.email}"
}

resource "google_service_account_iam_member" "kargo_project_token_creator" {
  service_account_id = google_service_account.kargo_project_registry_reader.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "principal://iam.googleapis.com/projects/${data.google_project.current.number}/locations/global/workloadIdentityPools/${var.project_id}.svc.id.goog/subject/ns/${var.kargo_kubernetes_namespace}/sa/${var.kargo_kubernetes_service_account}"

  depends_on = [
    google_container_cluster.gke_cluster,
    google_project_service.iam_credentials,
  ]
}
