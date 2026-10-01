variable "project_id" {
  description = "GCP project ID that owns the Resilience Gate infrastructure."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID."
  }
}

variable "region" {
  description = "GCP region for regional resources, such as the subnet and Artifact Registry."
  type        = string
  default     = "us-central1"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "region must look like a GCP region, for example us-central1."
  }
}

variable "zone" {
  description = "GCP zone for the zonal Standard GKE cluster."
  type        = string
  default     = "us-central1-a"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]-[a-z]$", var.zone))
    error_message = "zone must look like a GCP zone, for example us-central1-a."
  }
}

variable "environment" {
  description = "Short environment label applied to infrastructure resources."
  type        = string
  default     = "development"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9_-]{0,61}$", var.environment))
    error_message = "environment must be a lowercase GCP-label-compatible value."
  }
}

variable "additional_labels" {
  description = "Additional GCP labels applied to supported resources."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = alltrue([
      for key, value in var.additional_labels :
      can(regex("^[a-z][a-z0-9_-]{0,62}$", key)) && can(regex("^[a-z0-9_-]{0,63}$", value))
    ])
    error_message = "additional_labels must use lowercase GCP-label-compatible keys and values."
  }
}

variable "cluster_name" {
  description = "Name of the zonal Standard GKE cluster."
  type        = string
  default     = "resilience-gate"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$", var.cluster_name))
    error_message = "cluster_name must be a valid GKE cluster name."
  }
}

variable "default_node_count" {
  description = "Steady-state node count for the default Standard GKE node pool."
  type        = number
  default     = 2
  nullable    = false

  validation {
    condition     = var.default_node_count >= 1 && var.default_node_count <= 10
    error_message = "default_node_count must be between 1 and 10."
  }
}

variable "default_machine_type" {
  description = "Machine type for the default GKE node pool."
  type        = string
  default     = "e2-standard-2"
  nullable    = false
}

variable "general_node_count" {
  description = "Node count for the general-purpose GKE node pool."
  type        = number
  default     = 2
  nullable    = false

  validation {
    condition     = var.general_node_count >= 1 && var.general_node_count <= 10
    error_message = "general_node_count must be between 1 and 10."
  }
}

variable "general_machine_type" {
  description = "Machine type for the general-purpose GKE node pool."
  type        = string
  default     = "e2-standard-4"
  nullable    = false
}

variable "node_disk_size_gb" {
  description = "Boot disk size for each default-pool node."
  type        = number
  default     = 50
  nullable    = false

  validation {
    condition     = var.node_disk_size_gb >= 20
    error_message = "node_disk_size_gb must be at least 20 GB."
  }
}

variable "deletion_protection" {
  description = "Whether Terraform must block accidental deletion of the GKE cluster."
  type        = bool
  default     = true
  nullable    = false
}

variable "subnet_ipv4_cidr" {
  description = "Primary IPv4 CIDR range for GKE nodes."
  type        = string
  default     = "10.10.0.0/20"
  nullable    = false

  validation {
    condition     = can(cidrnetmask(var.subnet_ipv4_cidr))
    error_message = "subnet_ipv4_cidr must be a valid IPv4 CIDR range."
  }
}

variable "pods_ipv4_cidr" {
  description = "Secondary IPv4 CIDR range allocated to GKE Pods."
  type        = string
  default     = "10.20.0.0/16"
  nullable    = false

  validation {
    condition     = can(cidrnetmask(var.pods_ipv4_cidr))
    error_message = "pods_ipv4_cidr must be a valid IPv4 CIDR range."
  }
}

variable "services_ipv4_cidr" {
  description = "Secondary IPv4 CIDR range allocated to GKE Services."
  type        = string
  default     = "10.30.0.0/20"
  nullable    = false

  validation {
    condition     = can(cidrnetmask(var.services_ipv4_cidr))
    error_message = "services_ipv4_cidr must be a valid IPv4 CIDR range."
  }
}

variable "registry_repository_id" {
  description = "Artifact Registry Docker repository ID for release images."
  type        = string
  default     = "resilience-gate"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$", var.registry_repository_id))
    error_message = "registry_repository_id must be a lowercase Artifact Registry repository ID."
  }
}

variable "registry_untagged_retention" {
  description = "How long an untagged Artifact Registry version is retained, as a protobuf duration (for example 1209600s)."
  type        = string
  default     = "1209600s"
  nullable    = false

  validation {
    condition     = can(regex("^[1-9][0-9]*s$", var.registry_untagged_retention))
    error_message = "registry_untagged_retention must be a positive duration in seconds, for example 1209600s."
  }
}

variable "registry_keep_most_recent_versions" {
  description = "Number of the most recent Artifact Registry versions protected from cleanup."
  type        = number
  default     = 20
  nullable    = false

  validation {
    condition     = var.registry_keep_most_recent_versions >= 1
    error_message = "registry_keep_most_recent_versions must be at least 1."
  }
}

variable "github_repository" {
  description = "Trusted GitHub repository in owner/repository format. This input is required; no repository is trusted by default."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use owner/repository format."
  }
}

variable "github_oidc_ref" {
  description = "Only this Git ref may use the GitHub Actions publishing identity."
  type        = string
  default     = "refs/heads/main"
  nullable    = false

  validation {
    condition     = can(regex("^refs/(heads|tags)/[A-Za-z0-9._/-]+$", var.github_oidc_ref))
    error_message = "github_oidc_ref must be a fully-qualified Git ref."
  }
}

variable "github_oidc_allowed_events" {
  description = "GitHub event names permitted to impersonate the publishing identity from github_oidc_ref."
  type        = list(string)
  default     = ["push", "workflow_dispatch"]
  nullable    = false

  validation {
    condition     = length(var.github_oidc_allowed_events) > 0 && alltrue([for event in var.github_oidc_allowed_events : can(regex("^[A-Za-z0-9_]+$", event))])
    error_message = "github_oidc_allowed_events must contain one or more GitHub event names."
  }
}

variable "eso_kubernetes_namespace" {
  description = "Namespace containing the External Secrets Operator Kubernetes service account."
  type        = string
  default     = "external-secrets"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.eso_kubernetes_namespace))
    error_message = "eso_kubernetes_namespace must be a Kubernetes DNS-label-compatible name."
  }
}

variable "eso_kubernetes_service_account" {
  description = "External Secrets Operator Kubernetes service account name."
  type        = string
  default     = "external-secrets"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.eso_kubernetes_service_account))
    error_message = "eso_kubernetes_service_account must be a Kubernetes DNS-label-compatible name."
  }
}

variable "kargo_kubernetes_namespace" {
  description = "Namespace containing the Kargo controller Kubernetes service account."
  type        = string
  default     = "kargo"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.kargo_kubernetes_namespace))
    error_message = "kargo_kubernetes_namespace must be a Kubernetes DNS-label-compatible name."
  }
}

variable "kargo_kubernetes_service_account" {
  description = "Kargo controller Kubernetes service account that reads release images."
  type        = string
  default     = "kargo-controller"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", var.kargo_kubernetes_service_account))
    error_message = "kargo_kubernetes_service_account must be a Kubernetes DNS-label-compatible name."
  }
}
