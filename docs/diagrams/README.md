# Architecture artwork and sources

The root README displays the project's three original architecture PNGs,
restored unchanged at the owner's request. Its banner, technology tiles and
payment-flow illustration use local SVGs. The editable vector alternatives
remain available alongside the original artwork.

## Original illustrations displayed in the README

| Artwork | Role |
| --- | --- |
| [Original platform architecture](01-platform-architecture.png) | Initial platform overview |
| [Original promotion flow](02-promotion-flow.png) | Initial staged delivery overview |
| [Original chaos gate](03-chaos-gate.png) | Initial paid-load and fault-verification overview |

These PNGs are design illustrations, not runtime evidence. Embedded
project/cluster names, node sizes, namespaces, replica counts and the Promtail
label reflect an earlier configuration. The
[current architecture](../kubernetes-architecture.md) and
[verification report](../verification-report.md) document the deployed topology
and exact results. No editable source or regeneration claim is made for the
original PNGs.

## Editable vector artwork

The SVGs can be regenerated without a graphics service, vendor download, or
Python package installation.

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
external images. The generated technology tiles are original illustrations,
not official vendor logos; the vector set does not bundle third-party images.
The inherited PNGs contain vendor marks and are not covered by that claim.

The vector diagram alternatives describe the repository contracts. They use
one zonal GKE lab with two `e2-standard-4` nodes, 1/2/3 application replicas
in dev/staging/prod, the actual `resilience-gate` control namespace, and staging-only paid
chaos verification. Configuration details are in the
[Kubernetes architecture](../kubernetes-architecture.md). A diagram is not a
runtime verdict; exact results belong in the
[verification report](../verification-report.md) and
[reviewed screenshot gallery](../screenshots/README.md).

The three original PNGs were briefly archived during the October 3 presentation
refresh, then restored for the root README. Their earlier configuration labels
are explicitly distinguished from the current vector alternatives and runtime
evidence.
