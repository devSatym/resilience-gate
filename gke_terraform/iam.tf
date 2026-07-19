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
