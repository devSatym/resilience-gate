# Security policy

## Maintenance scope

Security maintenance focuses on the latest source on `main` and the `v1.1.x`
release line. Older releases may receive fixes at the maintainer's discretion;
fixes and backports are not guaranteed. Reports are handled on a best-effort
basis, with no response or remediation SLA and no paid bug bounty.

Resilience Gate is an owned-testnet platform demonstration. The GCP lab was
retired on **4 October 2026**. Retained screenshots and verification records
describe their original candidates, revisions, and observation windows; they
do not establish the security of a later source revision or a running service.
See the [known limitations](docs/known-limitations.md) for the project's scope
and security boundaries.

## Report a vulnerability privately

Use GitHub's [private vulnerability reporting form](https://github.com/devSatym/resilience-gate/security/advisories/new).
Do not disclose a suspected vulnerability in a public issue or pull request.

Include the affected version or commit, component, security impact, and a
minimal sanitized reproduction. Describe the local environment and any
validation already performed. Source-level analysis or a local reproduction is
sufficient; reporting does not require a cloud deployment or paid traffic.

Never include passwords, access tokens, cloud credentials, kubeconfigs, Secret
values, wallet keys or addresses, payment headers or signatures, transaction
identifiers, cookies, raw Terraform state, or private configuration. Use
placeholders and sanitized excerpts even in a confidential report.

This policy does not authorize testing another person's infrastructure,
creating cloud resources, spending funds, sending paid traffic, injecting
faults, or accessing data without the owner's explicit authorization.

## Other reports and contributions

Use the repository's issue forms for non-sensitive bugs and feature requests.
Follow [CONTRIBUTING.md](CONTRIBUTING.md) for validation, evidence handling, and
review requirements. A historical successful gate is evidence for its recorded
candidate and run, not a general security certification.
