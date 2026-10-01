terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.22"
    }
    # v6.11+ always serializes control-plane endpoint fields that this GKE API
    # target rejects. Limit the compatibility provider to the two GKE
    # resources below; the rest of the foundation remains on the current GA
    # provider.
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "= 6.10.0"
    }
  }

  # Backend settings cannot use Terraform variables. Supply them at init time,
  # for example: terraform init -backend-config=backend.hcl.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  network_name            = "${var.cluster_name}-vpc"
  subnetwork_name         = "${var.cluster_name}-subnet"
  cluster_secondary_range = "${var.cluster_name}-pods"
  svc_secondary_range     = "${var.cluster_name}-services"

  # Keep ownership labels stable even when callers supply extra labels.
  common_labels = merge(
    var.additional_labels,
    {
      application = "resilience-gate"
      environment = var.environment
      managed_by  = "terraform"
    },
    var.additional_labels,
  )
}

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "container" {
  project            = var.project_id
  service            = "container.googleapis.com"
  disable_on_destroy = false
}
