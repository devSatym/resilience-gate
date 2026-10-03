# Retired screenshot assets

The October 3 presentation refresh retains only the 34 reviewed captures in
[`manifest.json`](manifest.json). Eighteen earlier assets and six duplicate
root-level aliases were removed from the repository after their replacements
were accepted. Their original bytes remain in a private recovery archive.

| Retired visual | Current replacement or retirement reason |
| --- | --- |
| `argocd-app-of-apps-tiles.png` | 08: current Argo CD applications overview |
| `argocd-chaos-jobs-tree.png` | 09 and 29: actual staging/prod application resource trees; the platform overview remains in 08 |
| `chaos-gate-dashboard-full.png` | 17 and 17b: readable metrics and evidence split views |
| `chaos-gate-fail-verdict-band.png` | 22: exact historical FAIL annotation and interval |
| `chaos-gate-logs-degradation.png` | 17b: scoped degradation, verdict, and cleanup logs |
| `chaos-gate-pass-verdict-band.png` | 21: exact historical PASS annotation and interval |
| `chaos-gate-verdict-pass-log.png` | 16 and 17b: independent PASS verdict with cleanup |
| `env-staging-rendered-p1.png` | 14 and 14b: fresh digest-pinned content and render commit |
| `grafana-staging-dashboard.png` | Removed mislabeled duplicate of the old FAIL verdict image; replaced by 17, 17b, and 22 with precise captions |
| `k6-loadgen-startup.png` | 15 and 16: bounded startup and privacy-safe completion summary |
| `kargo-analysisrun-passed.png` | 11: fresh staging AnalysisRun and successful metrics |
| `kargo-manual-approval-modal.png` | 13: actual Kargo v1.3 ineligible-Freight selection; no unsupported approval-modal claim |
| `kargo-pipeline-freight-timeline.png` | 10: final release Freight aligned across three Stages |
| `kargo-stages-staging-failed.png` | 12 and 12b: exact failed historical AnalysisRun and metrics |
| `payment-flow-p2.png` | [Editable payment architecture](../diagrams/payment-flow.svg), explicitly conceptual rather than screenshot evidence |
| `payment-money-shot.png` | 23 and 24: payment telemetry plus the sanitized HTTP sequence |
| `payment-settlement-panels.png` | 23: reviewed historical settlement metrics |
| `signer-permit2-panels.png` | 25: address-removed signer and wallet-index readiness |

The six duplicate aliases were `argocd-app-of-apps-tiles-p1.png`,
`kargo-manual-approval-modal-p1.png`, `kargo-pipeline-freight-timeline-p1.png`,
`kargo-stages-staging-failed-p1.png`, `payment-flow-p2.png`, and
`payment-money-shot-p2.png` at the screenshot-directory root. They are covered
by the same replacements above. No current Markdown reference depends on a
retired image.
