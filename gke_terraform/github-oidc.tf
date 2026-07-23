resource "google_project_service" "iam_credentials" {
  project            = var.project_id
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}

# Security Token Service exchanges a GitHub OIDC token for short-lived Google
# credentials. No JSON service-account key is created or stored.
resource "google_project_service" "sts" {
  project            = var.project_id
  service            = "sts.googleapis.com"
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "github_pool" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions"
  description               = "OIDC trust boundary for the configured GitHub repository."

  depends_on = [
    google_project_service.iam_credentials,
    google_project_service.sts,
  ]
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Actions OIDC"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.event_name" = "assertion.event_name"
  }

  # Repository, ref, and triggering event are all part of the provider trust
  # policy. A token from a fork, pull-request ref, or unrelated workflow event
  # cannot impersonate the publishing service account.
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == '${var.github_oidc_ref}' && assertion.event_name in ${jsonencode(var.github_oidc_allowed_events)}"
}

resource "google_service_account" "github_actions" {
  project      = var.project_id
  account_id   = "github-actions-sa"
  display_name = "Resilience Gate GitHub publisher"
  description  = "Publishes release images to the private Artifact Registry through GitHub OIDC."
}

# CI can publish only to the application repository, not every registry in the
# project. The WIF binding below further narrows who may impersonate this SA.
resource "google_artifact_registry_repository_iam_member" "github_actions_gar_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_service_account_iam_member" "github_oidc_binding" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_repository}"
}
