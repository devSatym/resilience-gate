resource "google_compute_network" "gke_vpc" {
  project                 = var.project_id
  name                    = local.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "gke_subnet" {
  project                  = var.project_id
  name                     = local.subnetwork_name
  ip_cidr_range            = var.subnet_ipv4_cidr
  region                   = var.region
  network                  = google_compute_network.gke_vpc.id
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = local.cluster_secondary_range
    ip_cidr_range = var.pods_ipv4_cidr
  }

  secondary_ip_range {
    range_name    = local.svc_secondary_range
    ip_cidr_range = var.services_ipv4_cidr
  }

  depends_on = [google_project_service.compute]
}
