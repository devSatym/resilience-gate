resource "google_project_service" "artifact_registry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

# The repository is intentionally private. Reader access is granted only to the
# dedicated node and Kargo identities declared elsewhere in this configuration.
resource "google_artifact_registry_repository" "app_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.registry_repository_id
  description   = "Private release images for Resilience Gate"
  format        = "DOCKER"

  labels = local.common_labels

  cleanup_policies {
    id     = "delete-untagged-after-retention"
    action = "DELETE"

    condition {
      tag_state  = "UNTAGGED"
      older_than = var.registry_untagged_retention
    }
  }

  cleanup_policies {
    id     = "keep-most-recent-versions"
    action = "KEEP"

    most_recent_versions {
      keep_count = var.registry_keep_most_recent_versions
    }
  }

  depends_on = [google_project_service.artifact_registry]
}

# GKE nodes can pull from this repository only; they do not receive project-wide
# Artifact Registry access. The resource reference also orders the IAM grant
# after repository creation on a fresh apply.
resource "google_artifact_registry_repository_iam_member" "gke_nodes_gar_reader" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.gke_nodes.email}"
}
