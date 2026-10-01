resource "google_container_cluster" "gke_cluster" {
  provider = google-beta

  project  = var.project_id
  name     = var.cluster_name
  location = var.zone

  network    = google_compute_network.gke_vpc.self_link
  subnetwork = google_compute_subnetwork.gke_subnet.self_link

  # A separately managed pool makes the cluster a Standard cluster and lets the
  # node identity and Workload Identity metadata mode be explicit.
  remove_default_node_pool = true
  initial_node_count       = 1

  # GKE creates this initial pool before removing it, so it must not fall back
  # to the Compute Engine default service account. Modern projects can leave
  # that account without the role GKE requires for node creation.
  node_config {
    service_account = google_service_account.gke_nodes.email

    # Avoid serializing an empty logging variant object for the transient
    # initial pool by declaring GKE's documented default explicitly.
    logging_variant = "DEFAULT"
  }

  # After bootstrap, the separately managed pool below is authoritative. The
  # provider mirrors that pool through this create-time node_config, so do not
  # let two resources manage its labels.
  lifecycle {
    ignore_changes = [
      node_config[0].resource_labels,
    ]
  }

  deletion_protection   = var.deletion_protection
  enable_shielded_nodes = true
  networking_mode       = "VPC_NATIVE"

  release_channel {
    channel = "REGULAR"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = local.cluster_secondary_range
    services_secondary_range_name = local.svc_secondary_range
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    # WORKLOADS is a legacy monitoring component that GKE no longer accepts
    # for current releases. The platform's Prometheus stack continues to
    # collect workload metrics; keep GKE's supported system metrics enabled.
    enable_components = ["SYSTEM_COMPONENTS"]
  }

  resource_labels = local.common_labels

  depends_on = [
    google_project_service.compute,
    google_project_service.container,
    google_project_iam_member.gke_nodes_default_node_service_account,
    google_project_iam_member.gke_service_agent,
    google_project_iam_member.gke_default_node_service_agent,
  ]
}

# The general pool is the steady-state capacity for all workloads. Its node
# identity and Workload Identity configuration are explicit and durable.
resource "google_container_node_pool" "general" {
  provider = google-beta

  project    = var.project_id
  name       = "general-pool"
  location   = var.zone
  cluster    = google_container_cluster.gke_cluster.name
  node_count = var.general_node_count

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type    = var.general_machine_type
    disk_size_gb    = var.node_disk_size_gb
    image_type      = "COS_CONTAINERD"
    service_account = google_service_account.gke_nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    metadata = {
      disable-legacy-endpoints = "true"
    }

    shielded_instance_config {
      enable_integrity_monitoring = true
      enable_secure_boot          = true
    }

    labels = {
      role = "default"
    }

    resource_labels = local.common_labels
  }

  lifecycle {
    ignore_changes = [
      node_config[0].resource_labels["goog-gke-node-pool-provisioning-model"],
    ]
  }

  depends_on = [
    google_project_iam_member.gke_nodes_default_node_service_account,
    google_project_iam_member.gke_nodes_log_writer,
    google_project_iam_member.gke_nodes_metric_writer,
    google_project_iam_member.gke_nodes_monitoring_viewer,
  ]
}
