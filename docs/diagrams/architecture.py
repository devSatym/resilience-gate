#!/usr/bin/env python3
"""Maintain the conceptual Resilience Gate Mermaid architecture diagram.

The generated file describes repository intent only. It must never be used as
proof that a cluster, promotion, payment, or chaos run exists.
"""

from __future__ import annotations

import argparse
from pathlib import Path


DIAGRAM = """%% Conceptual source diagram for Resilience Gate. Live outcomes are recorded
%% separately; the diagram itself is not evidence.
flowchart LR
  developer[Developer] -->|push| ci[GitHub Actions]
  ci -->|OIDC publish and Cosign| registry[Artifact Registry]
  ci -->|source revision| warehouse[Kargo Warehouse]
  registry -->|OCI digest| warehouse

  warehouse --> dev[dev: auto and health]
  dev --> staging[staging: manual, health, chaos]
  staging --> prod[prod-like: manual and smoke]

  dev -->|render env/dev| argo[Argo CD]
  staging -->|render env/staging| argo
  prod -->|render env/prod| argo
  argo --> workloads[GKE workloads]

  terraform[Terraform] -->|GCP foundation| workloads
  secrets[GCP Secret Manager and ESO] --> workloads
  load[k6 and isolated Permit2 signer] -->|paid testnet traffic| workloads
  chaos[Chaos Mesh] -->|bounded dependency faults| workloads
  workloads --> telemetry[Prometheus, Loki, Grafana]
  telemetry --> scorer[Fail-closed scorer]
  scorer -->|PASS or FAIL| staging
  scorer --> evidence[Sanitized evidence]
"""

OUTPUT = Path(__file__).with_name("architecture.mmd")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if architecture.mmd does not match this source",
    )
    args = parser.parse_args()

    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None
    if args.check:
        if current != DIAGRAM:
            print(f"{OUTPUT} is out of date; run {Path(__file__).name}")
            return 1
        print(f"{OUTPUT} is current")
        return 0

    if current != DIAGRAM:
        OUTPUT.write_text(DIAGRAM, encoding="utf-8")
        print(f"wrote {OUTPUT}")
    else:
        print(f"{OUTPUT} is already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
