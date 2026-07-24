output "cluster_name" {
  value       = google_container_cluster.gke_cluster.name
  description = "Name of the Standard GKE cluster."
}

output "cluster_endpoint" {
  value       = google_container_cluster.gke_cluster.endpoint
  description = "Control-plane endpoint of the GKE cluster."
  sensitive   = true
}

output "cluster_location" {
  value       = google_container_cluster.gke_cluster.location
  description = "Zone containing the GKE cluster."
}

output "vpc_name" {
  value       = google_compute_network.gke_vpc.name
  description = "Name of the dedicated VPC network."
}

output "gar_repository_url" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app_repo.repository_id}"
  description = "Private Artifact Registry Docker repository URL."
}

output "gke_node_service_account_email" {
  value       = google_service_account.gke_nodes.email
  description = "Dedicated Google service account used by GKE nodes."
}

output "workload_identity_provider" {
  value       = google_iam_workload_identity_pool_provider.github_provider.name
  description = "GitHub OIDC provider resource name for google-github-actions/auth."
}

output "github_actions_service_account_email" {
  value       = google_service_account.github_actions.email
  description = "Google service account that GitHub Actions may impersonate to publish images."
}

output "eso_gcp_service_account_email" {
  value       = google_service_account.external_secrets.email
  description = "Google service account to annotate on the External Secrets Operator Kubernetes service account."
}

output "eso_kubernetes_service_account_annotation" {
  value = {
    "iam.gke.io/gcp-service-account" = google_service_account.external_secrets.email
  }
  description = "Annotation map for the configured External Secrets Operator Kubernetes service account."
}

output "kargo_gcp_service_account_email" {
  value       = google_service_account.kargo_registry_reader.email
  description = "Google service account to annotate on the Kargo controller Kubernetes service account."
}

output "kargo_kubernetes_service_account_annotation" {
  value = {
    "iam.gke.io/gcp-service-account" = google_service_account.kargo_registry_reader.email
  }
  description = "Annotation map for the configured Kargo controller Kubernetes service account."
}
