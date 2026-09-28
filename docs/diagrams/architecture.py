#!/usr/bin/env python3
"""Maintain the conceptual Resilience Gate Mermaid architecture diagram.

The generated file describes repository intent only. It must never be used as
proof that a cluster, promotion, payment, or chaos run exists.
"""

from __future__ import annotations

import argparse
from pathlib import Path


DIAGRAM = """%% Conceptual source diagram for Resilience Gate. It is not a deployed-state
%% diagram or evidence of a successful promotion.
flowchart LR
  source[Reviewed source on main] --> identity[Revision and OCI digest]
  identity --> warehouse[Kargo Warehouse]
  warehouse --> dev[dev policy]
  dev --> staging[manual staging]
  staging --> gate[bounded chaos gate]
  gate --> prod[manual prod-like testnet]

  source --> render[Rendered env branches]
  render --> argo[Argo CD Applications]
  argo --> workload[Digest-pinned workload]

  workload -. metrics and logs when installed .-> telemetry[Prometheus, Loki, Grafana]
  telemetry -. score inputs .-> gate

  gate --> evidence[Sanitized evidence records]
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
