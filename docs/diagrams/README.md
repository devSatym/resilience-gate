# Architecture artwork and sources

The README uses a cohesive set of local SVGs. They remain sharp when enlarged,
work in GitHub's light and dark themes, and can be regenerated without a
graphics service, vendor download, or Python package installation.

| Artwork | What it explains | Editable source |
| --- | --- | --- |
| [README banner](readme-hero.svg) | Project identity and release story | [`presentation.py`](presentation.py) |
| [Platform architecture](platform-architecture.svg) | CI, signed artifacts, Freight, rendered Git, Argo CD, and the fixed GKE lab | [`presentation.py`](presentation.py) |
| [Promotion flow](promotion-flow.svg) | Automatic dev, manual staging and prod-like promotion, and downstream eligibility | [`presentation.py`](presentation.py) |
| [Chaos gate](chaos-gate.svg) | Preconditions, serial faults, fail-closed scorecards, and cleanup before PASS | [`presentation.py`](presentation.py) |
| [Payment flow](payment-flow.svg) | The x402 challenge, isolated Permit2 signing, facilitator calls, persistence, and replay handling | [`presentation.py`](presentation.py) |
| [Architecture in Mermaid](architecture.mmd) | A compact, editable conceptual graph | [`architecture.py`](architecture.py) |
| [Technology tiles](icons/) | Original pictograms for the nine technologies featured in the README | [`presentation.py`](presentation.py) |

Regenerate and verify the vector assets from the repository root:

```bash
python3 docs/diagrams/presentation.py
python3 docs/diagrams/presentation.py --check
python3 docs/diagrams/architecture.py --check
python3 scripts/validate-docs.py
```

The generator uses Python's standard library. Layout, text, colors, paths, and
accessible titles/descriptions are reviewed source, not generated from a live
cluster. SVGs contain no scripts, fonts loaded from the network, or linked
external images. Technology tiles are original illustrations, not official
vendor logos; no third-party image assets are bundled.

The diagrams describe the repository contracts. They use one zonal GKE lab
with two `e2-standard-4` nodes, dev/staging/prod application replica counts of
1/2/3, the actual `resilience-gate` control namespace, and staging-only paid
chaos verification. Configuration details are in the
[Kubernetes architecture](../kubernetes-architecture.md). A diagram is not a
runtime verdict; exact results belong in the
[verification report](../verification-report.md) and
[reviewed screenshot gallery](../screenshots/README.md).

The old raster diagrams were retired during the October 3 presentation
refresh because they contained superseded cluster identifiers, node sizes,
namespaces, or replica counts. Their local originals were preserved in a
private recovery archive. The current SVG sources replace them completely.
