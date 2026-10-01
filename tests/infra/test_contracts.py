"""Offline contracts for the portable GCP foundation.

These tests intentionally inspect configuration rather than contacting GCP. They
make dangerous regressions (such as a public registry or a hard-coded deployment
identity) visible in credential-free pull-request validation.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = REPOSITORY_ROOT / "gke_terraform"


def terraform_source(name: str) -> str:
    return (TERRAFORM_DIR / name).read_text(encoding="utf-8")


def variable_block(source: str, name: str) -> str:
    match = re.search(rf'variable "{re.escape(name)}" \{{(.*?)^\}}', source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"variable {name!r} is not declared")
    return match.group(1)


class TerraformInfrastructureContracts(unittest.TestCase):
    def test_backend_is_configured_at_init_time_with_a_safe_example(self) -> None:
        main = terraform_source("main.tf")
        backend_example = terraform_source("backend.hcl.example")

        self.assertIn('backend "gcs" {}', main)
        self.assertIn("REPLACE_WITH_YOUR_TERRAFORM_STATE_BUCKET", backend_example)
        self.assertNotIn("ajprojectplatform", main + backend_example)
        self.assertTrue((TERRAFORM_DIR / ".terraform.lock.hcl").is_file())

    def test_deployment_identity_inputs_have_no_personal_defaults(self) -> None:
        variables = terraform_source("variables.tf")
        source = "\n".join(path.read_text(encoding="utf-8") for path in TERRAFORM_DIR.glob("*.tf"))

        self.assertIn('variable "project_id"', variables)
        self.assertIn('variable "github_repository"', variables)
        self.assertIsNone(re.search(r"^\s*default\s*=", variable_block(variables, "project_id"), re.MULTILINE))
        self.assertIsNone(
            re.search(r"^\s*default\s*=", variable_block(variables, "github_repository"), re.MULTILINE)
        )
        self.assertNotIn("ajprojectplatform", source)
        self.assertNotIn("amoghjay", source)

    def test_registry_is_private_and_has_cleanup_rules(self) -> None:
        registry = terraform_source("registry.tf")
        source = "\n".join(path.read_text(encoding="utf-8") for path in TERRAFORM_DIR.glob("*.tf"))

        self.assertNotIn("allUsers", source)
        self.assertNotIn("allAuthenticatedUsers", source)
        self.assertIn('format        = "DOCKER"', registry)
        self.assertIn('tag_state  = "UNTAGGED"', registry)
        self.assertIn('action = "KEEP"', registry)

    def test_nodes_use_gke_metadata_for_workload_identity(self) -> None:
        gke = terraform_source("gke.tf")

        self.assertIn('workload_pool = "${var.project_id}.svc.id.goog"', gke)
        self.assertIn("workload_metadata_config", gke)
        self.assertIn('mode = "GKE_METADATA"', gke)
        self.assertIn('disable-legacy-endpoints = "true"', gke)

    def test_gke_monitoring_uses_current_supported_components(self) -> None:
        gke = terraform_source("gke.tf")
        monitoring = re.search(r"monitoring_config \{(.*?)^  \}", gke, re.MULTILINE | re.DOTALL)

        self.assertIsNotNone(monitoring)
        self.assertIn('enable_components = ["SYSTEM_COMPONENTS"]', monitoring.group(1))

    def test_cluster_initial_pool_uses_the_dedicated_node_identity(self) -> None:
        gke = terraform_source("gke.tf")
        cluster, _ = gke.split('resource "google_container_node_pool" "default"', 1)

        # remove_default_node_pool still creates a transient initial pool.
        # It must use the role-bound dedicated identity rather than a default
        # Compute Engine service account that modern projects leave unprivileged.
        self.assertIn('remove_default_node_pool = true', cluster)
        self.assertIn('service_account = google_service_account.gke_nodes.email', cluster)
        self.assertIn('logging_variant = "DEFAULT"', cluster)
        self.assertIn(
            'google_project_iam_member.gke_nodes_default_node_service_account,',
            cluster,
        )
        self.assertIn(
            'google_project_iam_member.gke_default_node_service_agent,',
            cluster,
        )
        self.assertIn(
            'google_project_iam_member.gke_service_agent,',
            cluster,
        )
        self.assertIn('node_config[0].resource_labels,', cluster)

    def test_gke_preserves_only_the_server_owned_provisioning_label(self) -> None:
        gke = terraform_source("gke.tf")
        cluster, node_pool = gke.split('resource "google_container_node_pool" "default"', 1)
        server_label = 'node_config[0].resource_labels["goog-gke-node-pool-provisioning-model"]'

        self.assertIn('node_config[0].resource_labels,', cluster)
        self.assertNotIn(server_label, cluster)
        self.assertIn(server_label, node_pool)
        self.assertNotIn("ignore_changes = [node_config[0].resource_labels]", gke)

    def test_gke_default_node_service_agent_binding_is_restored_declaratively(self) -> None:
        iam = terraform_source("iam.tf")

        self.assertIn('data "google_project" "current"', iam)
        self.assertIn('roles/container.serviceAgent', iam)
        self.assertIn(
            'service-${data.google_project.current.number}@container-engine-robot.iam.gserviceaccount.com',
            iam,
        )
        self.assertIn('roles/container.defaultNodeServiceAgent', iam)
        self.assertIn(
            'service-${data.google_project.current.number}@gcp-sa-gkenode.iam.gserviceaccount.com',
            iam,
        )
        self.assertIn('depends_on = [google_project_service.container]', iam)

    def test_gke_resources_use_the_pinned_endpoint_compatibility_provider(self) -> None:
        main = terraform_source("main.tf")
        gke = terraform_source("gke.tf")
        cluster, node_pool = gke.split('resource "google_container_node_pool" "default"', 1)

        self.assertIn('source  = "hashicorp/google-beta"', main)
        self.assertIn('version = "= 6.10.0"', main)
        self.assertIn('provider "google-beta"', main)
        self.assertIn('provider = google-beta', cluster)
        self.assertIn('provider = google-beta', node_pool)
        self.assertNotIn('private_endpoint_subnetwork', cluster)

    def test_github_publisher_is_bound_to_repository_ref_and_event(self) -> None:
        oidc = terraform_source("github-oidc.tf")

        self.assertIn('"attribute.repository" = "assertion.repository"', oidc)
        self.assertIn('"attribute.ref"        = "assertion.ref"', oidc)
        self.assertIn('"attribute.event_name" = "assertion.event_name"', oidc)
        self.assertIn("assertion.repository == '${var.github_repository}'", oidc)
        self.assertIn("assertion.ref == '${var.github_oidc_ref}'", oidc)
        self.assertIn("assertion.event_name in", oidc)
        self.assertIn("google_artifact_registry_repository_iam_member", oidc)

    def test_eso_and_kargo_use_distinct_least_privilege_identities(self) -> None:
        eso = terraform_source("eso.tf")
        kargo = terraform_source("kargo-identity.tf")
        outputs = terraform_source("outputs.tf")

        self.assertIn('account_id   = "external-secrets-sa"', eso)
        self.assertIn("roles/secretmanager.secretAccessor", eso)
        self.assertIn('account_id   = "kargo-gar-reader"', kargo)
        self.assertIn("roles/artifactregistry.reader", kargo)
        self.assertIn("kargo_workload_identity_binding", kargo)
        self.assertIn('output "eso_gcp_service_account_email"', outputs)
        self.assertIn('output "kargo_gcp_service_account_email"', outputs)

        eso_account = re.search(r'account_id\s*=\s*"([^"]+)"', eso)
        kargo_account = re.search(r'account_id\s*=\s*"([^"]+)"', kargo)
        self.assertIsNotNone(eso_account)
        self.assertIsNotNone(kargo_account)
        self.assertNotEqual(
            eso_account.group(1),
            kargo_account.group(1),
            "ESO and Kargo must never share a Google service account.",
        )


if __name__ == "__main__":
    unittest.main()
