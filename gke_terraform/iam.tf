# Nodes use this dedicated identity instead of the default Compute Engine
# service account. Workloads receive their own identities through Workload
# Identity, so this identity deliberately has no Secret Manager access.
resource "google_service_account" "gke_nodes" {
  project      = var.project_id
  account_id   = "gke-node-sa"
  display_name = "Resilience Gate GKE nodes"
  description  = "Least-privilege identity for GKE nodes: cluster operation, telemetry, and private image pulls."
}

resource "google_project_iam_member" "gke_nodes_default_node_service_account" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# GKE 1.33+ uses a Google-managed node service agent for node logging and
# monitoring. The GKE API normally creates and binds it when enabled, but the
# binding can be removed independently and then makes cluster creation fail.
# Derive its stable project-number address instead of hard-coding a target.
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_iam_member" "gke_service_agent" {
  project = var.project_id
  role    = "roles/container.serviceAgent"
  member  = "serviceAccount:service-${data.google_project.current.number}@container-engine-robot.iam.gserviceaccount.com"

  depends_on = [google_project_service.container]
}

resource "google_project_iam_member" "gke_default_node_service_agent" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAgent"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-gkenode.iam.gserviceaccount.com"

  depends_on = [google_project_service.container]
}

resource "google_project_iam_member" "gke_nodes_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}
