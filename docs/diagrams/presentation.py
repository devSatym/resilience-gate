#!/usr/bin/env python3
"""Generate the reviewed README artwork using only Python's standard library.

SVGs are conceptual illustrations of the source contracts, never runtime proof.
Technology tiles are original pictograms, not downloaded vendor logos. This
file is their editable source; --check verifies every published vector asset.
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INK = "#edf5ff"
MUTED = "#a9bbd1"
TEAL = "#53e3c2"
VIOLET = "#af9bff"
BLUE = "#70b9ff"
AMBER = "#ffc776"
RED = "#ff8e9e"


class Canvas:
    def __init__(self, height: int, title: str, description: str, width: int = 1280):
        self.width = width
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f"<title id=\"title\">{escape(title)}</title>",
            f"<desc id=\"desc\">{escape(description)}</desc>",
            '<defs><linearGradient id="bg" x2="1" y2="1">'
            '<stop stop-color="#101d35"/><stop offset="1" stop-color="#07111f"/>'
            '</linearGradient><linearGradient id="accent" x2="1" y2="1">'
            f'<stop stop-color="{TEAL}"/><stop offset="1" stop-color="{BLUE}"/>'
            '</linearGradient><pattern id="grid" width="32" height="32" '
            'patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" '
            'fill="#476079" opacity=".23"/></pattern>',
            '<marker id="arrow" markerWidth="7" markerHeight="7" refX="6" '
            'refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" '
            'fill="#829db8"/></marker></defs>',
            f'<rect width="{width}" height="{height}" rx="22" fill="url(#bg)"/>',
            f'<rect width="{width}" height="{height}" rx="22" fill="url(#grid)"/>',
            '<g font-family="DejaVu Sans,Arial,sans-serif">',
        ]

    def add(self, value: str) -> None:
        self.parts.append(value)

    def text(self, x: int, y: int, value: str, size: int = 20, color: str = INK,
             weight: int = 400, anchor: str = "start") -> None:
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
                 f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>')

    def rect(self, x: int, y: int, w: int, h: int, fill: str = "#122139",
             stroke: str = "#2a3e58", radius: int = 16) -> None:
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                 f'rx="{radius}" fill="{fill}" stroke="{stroke}"/>')

    def line(self, x1: int, y1: int, x2: int, y2: int, arrow: bool = True,
             color: str = "#829db8", dashed: bool = False) -> None:
        self.add(f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" '
                 f'stroke="{color}" stroke-width="2"'
                 + (' stroke-dasharray="6 6"' if dashed else "")
                 + (' marker-end="url(#arrow)"' if arrow else "") + '/>')

    def pill(self, x: int, y: int, w: int, label: str, color: str = TEAL) -> None:
        self.rect(x, y, w, 32, fill="#10263a", stroke=color, radius=16)
        self.text(x + w // 2, y + 22, label, 14, color, 700, "middle")

    def heading(self, eyebrow: str, title: str, subtitle: str) -> None:
        self.text(50, 43, eyebrow.upper(), 14, TEAL, 700)
        self.text(50, 91, title, 34, INK, 700)
        self.text(50, 126, subtitle, 19, MUTED)

    def footer(self, y: int, label: str = "CONCEPTUAL SOURCE DIAGRAM · runtime evidence is linked separately") -> None:
        self.text(50, y, label, 13, MUTED)

    def card(self, x: int, y: int, w: int, h: int, label: str,
             title: str, lines: list[str], color: str = TEAL) -> None:
        self.rect(x, y, w, h)
        self.add(f'<rect x="{x}" y="{y+16}" width="3" height="{h-32}" rx="1" fill="{color}"/>')
        self.text(x + 21, y + 34, label.upper(), 13, color, 700)
        title_size = 23 if len(title) * 13 < w - 42 else 19
        self.text(x + 21, y + 69, title, title_size, INK, 700)
        for i, line in enumerate(lines):
            self.text(x + 21, y + 103 + i * 29, line, 17, MUTED)

    def finish(self) -> str:
        return "\n".join([*self.parts, "</g></svg>", ""])


def hero() -> str:
    c = Canvas(360, "Resilience Gate", "Chaos-verified Kubernetes releases: immutable artifacts, paid traffic, measured recovery, and evidence.")
    c.text(58, 59, "BUILD · PROMOTE · BREAK · RECOVER · PROVE", 16, TEAL, 700)
    c.text(53, 145, "RESILIENCE GATE", 66, INK, 700)
    c.text(58, 198, "Kubernetes releases that earn their promotion.", 28, INK)
    c.text(58, 235, "Immutable delivery. Paid testnet traffic. Measured failure and recovery.", 19, MUTED)
    c.pill(58, 280, 188, "GITOPS + CHAOS")
    c.pill(262, 280, 204, "x402 + PERMIT2", VIOLET)
    c.pill(482, 280, 222, "VERIFIED TESTNET", BLUE)
    c.add('<circle cx="1100" cy="173" r="113" fill="#0a2433" stroke="#25475b"/>')
    c.add('<circle cx="1100" cy="173" r="95" fill="none" stroke="#28536a" stroke-dasharray="5 10"/>')
    c.add('<path d="M1100 93L1164 120V170C1164 218 1138 247 1100 263C1062 247 1036 218 1036 170V120Z" '
          'fill="#102d41" stroke="url(#accent)" stroke-width="4"/>')
    c.add(f'<path d="M1062 174L1086 198L1139 144" fill="none" stroke="{TEAL}" '
          'stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>')
    for x, y, color in [(1006, 103, TEAL), (1190, 242, VIOLET), (1188, 85, BLUE)]:
        c.add(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
    return c.finish()


def architecture() -> str:
    c = Canvas(820, "Resilience Gate platform architecture", "GitHub Actions uses OIDC to publish Cosign-signed images. Kargo joins source and image identities, renders environment branches, and requests Argo CD reconciliation. Dev, staging and prod-like namespaces run on one two-node zonal GKE lab with Terraform, External Secrets, and observability.")
    c.heading("01 / platform architecture", "One release identity. Three environments.",
              "Git source + OCI digest → rendered Git → reconciled workload → verification record")
    xs = [50, 291, 532, 773, 1014]
    titles = ["GitHub Actions", "Artifact Registry", "Kargo Warehouse", "Rendered Git", "Argo CD"]
    labels = ["SOURCE + CI", "SIGNED ARTIFACTS", "CANDIDATE IDENTITY", "REVIEWABLE OUTPUT", "RECONCILIATION"]
    lines = [["Validate + build", "Keyless OIDC publish"], ["App · signer · gate", "Cosign + OCI digests"],
             ["Source + image Freight", "Stage eligibility"], ["env/dev · env/staging", "env/prod manifests"],
             ["Track env/* branches", "Apply desired revision"]]
    for i, x in enumerate(xs):
        c.card(x, 164, 216, 169, labels[i], titles[i], lines[i], [BLUE, VIOLET, TEAL, BLUE, AMBER][i])
        if i < 4:
            c.line(x + 218, 248, xs[i + 1] - 7, 248)
    c.rect(50, 365, 1180, 228, fill="#0a1b2d", stroke="#46617b")
    c.text(73, 401, "EXISTING GKE STANDARD LAB", 14, BLUE, 700)
    c.text(1208, 401, "1 zone · 2 nodes · e2-standard-4", 16, MUTED, anchor="end")
    c.line(1122, 334, 1122, 360)
    c.card(75, 425, 332, 145, "url-shortener-dev", "dev", ["1 app replica", "PostgreSQL + Redis"], BLUE)
    c.card(474, 425, 332, 145, "url-shortener-staging", "staging", ["2 app replicas + signer", "Paid load + serial pod faults"], VIOLET)
    c.card(873, 425, 332, 145, "url-shortener-prod", "prod-like", ["3 app replicas", "Readiness + liveness smoke"], TEAL)
    c.line(410, 490, 466, 490)
    c.line(809, 490, 865, 490)
    c.card(50, 625, 370, 137, "FOUNDATION", "Terraform + Workload Identity", ["GCP infrastructure + IAM"], BLUE)
    c.card(455, 625, 370, 137, "SECRET DELIVERY", "Secret Manager → ESO", ["Values stay outside Git"], VIOLET)
    c.card(860, 625, 370, 137, "FEEDBACK + VERDICT", "Prometheus · Loki · Grafana", ["Scoring + sanitized evidence"], TEAL)
    c.footer(798)
    return c.finish()


def promotion() -> str:
    c = Canvas(630, "Verified promotion flow", "An immutable Kargo Freight is automatically promoted into dev. Staging and prod-like promotion are manual. Staging checks readiness, paid traffic, serial dependency faults, telemetry and cleanup; prod requires staging-verified Freight and readiness and liveness. Each environment commits rendered YAML for Argo CD.")
    c.heading("02 / promotion contract", "A green pod is the beginning of the check.",
              "The same Freight advances only after the upstream verification succeeds.")
    c.rect(50, 161, 1180, 57, fill="#102c38", stroke="#315562")
    c.text(75, 197, "FREIGHT = source revision + application image digest", 21, TEAL, 700)
    c.text(1208, 197, "immutable candidate", 16, MUTED, anchor="end")
    c.card(50, 258, 358, 208, "01 / AUTOMATIC", "dev", ["Render env/dev", "Argo CD sync + service health", "Eligible for staging"], BLUE)
    c.card(461, 258, 358, 208, "02 / MANUAL", "staging", ["Render env/staging", "Readiness + chaos verdict", "Eligible for prod after PASS"], VIOLET)
    c.card(872, 258, 358, 208, "03 / MANUAL", "prod-like testnet", ["Render env/prod", "Readiness + liveness", "No paid load or chaos in smoke"], TEAL)
    c.line(412, 360, 451, 360)
    c.line(823, 360, 862, 360)
    c.rect(50, 497, 1180, 72, fill="#251e34", stroke="#654458")
    c.text(75, 527, "FAILED OR MISSING EVIDENCE", 14, RED, 700)
    c.text(75, 554, "The candidate does not become normally eligible for the downstream Stage.", 20, INK)
    c.footer(608)
    return c.finish()


def chaos() -> str:
    c = Canvas(724, "Inside the staging chaos gate", "Preflight proves ready target, release identity, paid traffic and an exclusive Lease. The runner measures PostgreSQL, Redis and signer pod failures in sequence, then validates telemetry and scores traffic, errors, latency, restarts and recovery. Successful Job completion also requires exact temporary resource cleanup. Grafana annotations are diagnostic.")
    c.heading("03 / staging verification", "Break a dependency. Measure the recovery.",
              "A bounded gate-runner Job binds every scorecard to the candidate and the experiment window.")
    c.card(50, 163, 1180, 125, "01 / PROVE THE PRECONDITIONS", "Target · release identity · paid traffic · exclusive Lease", ["Failed preflight exits before fault injection; telemetry is evaluated during scoring."], BLUE)
    c.line(640, 293, 640, 316)
    c.text(50, 339, "02 / SERIAL POD-FAILURE EXPERIMENTS", 14, VIOLET, 700)
    c.card(50, 359, 358, 129, "FIRST", "PostgreSQL", ["Fault → degradation → recovery"], VIOLET)
    c.card(461, 359, 358, 129, "THEN", "Redis", ["Fault → DB fallback → recovery"], VIOLET)
    c.card(872, 359, 358, 129, "THEN", "Permit2 signer", ["Fault → availability → recovery"], VIOLET)
    c.line(412, 418, 451, 418)
    c.line(823, 418, 862, 418)
    c.card(50, 524, 553, 129, "03 / FAIL-CLOSED SCORING", "Prometheus-backed scorecards", ["Traffic · 5xx · p95 · restarts · recovery"], AMBER)
    c.card(677, 524, 553, 129, "04 / CLEANUP BEFORE SUCCESS", "Verify exact resources are absent", ["Workflow · fault objects · load Job · Lease"], TEAL)
    c.line(609, 587, 666, 587)
    c.footer(697, "Successful Job exit requires scoring + cleanup · annotations are diagnostic · conceptual source diagram")
    return c.finish()


def payment() -> str:
    c = Canvas(768, "x402 and Permit2 payment sequence", "Client receives an HTTP402 challenge, obtains a Permit2 authorization from the isolated signer, and submits the signed request. App verifies then settles via the facilitator and persists a URL before HTTP201. GET redirects with302; replay of the same settlement is rejected with409. Settlement and database persistence are not atomic.")
    c.heading("04 / paid workload", "A real payment path inside the release test.",
              "Owned Radius testnet · server-owned payment terms · isolated signing boundary")
    lanes = [(50, "Client / k6", BLUE), (359, "Permit2 signer", VIOLET), (668, "FastAPI app", TEAL), (977, "Facilitator", AMBER)]
    for x, label, color in lanes:
        c.rect(x, 162, 253, 61)
        c.text(x + 126, 201, label, 22, color, 700, "middle")
        c.line(x + 126, 233, x + 126, 662, False, "#36506a", True)
    def exchange(y: int, start: int, end: int, label: str, color: str = INK) -> None:
        c.line(start, y, end, y)
        c.rect(min(start, end) + 10, y - 29, abs(end - start) - 20, 24, fill="#0b182a", stroke="#0b182a", radius=4)
        c.text((start + end) // 2, y - 10, label, 17, color, anchor="middle")
    exchange(276, 176, 794, "POST /shorten → 402 Payment Required", BLUE)
    exchange(337, 176, 485, "Get Permit2 authorization", VIOLET)
    exchange(398, 176, 794, "Retry with PAYMENT-SIGNATURE", BLUE)
    exchange(459, 794, 1103, "/verify → /settle", AMBER)
    c.pill(679, 481, 230, "PERSIST URL + AUDIT", TEAL)
    exchange(550, 794, 176, "201 Created after settlement + persistence", TEAL)
    exchange(611, 176, 794, "GET code → 302 redirect · replay → 409", BLUE)
    c.rect(50, 685, 1180, 42, fill="#251e34", stroke="#654458", radius=10)
    c.text(73, 712, "Consistency boundary: settlement and database persistence require reconciliation after partial failure.", 17, MUTED)
    c.footer(752)
    return c.finish()


SYMBOLS = {
    "python": ('<path d="M17 10H29V25H18C11 25 11 36 18 36H21M31 38H19V23H30C37 23 37 12 30 12H27"/>', BLUE),
    "kubernetes": ('<path d="M24 6L39 14V32L24 41L9 32V14Z"/><circle cx="24" cy="24" r="8"/><path d="M24 9V16M24 32V39M11 16L17 20M31 28L37 32M11 32L17 28M31 20L37 16"/>', BLUE),
    "terraform": ('<path d="M8 10L20 17V31L8 24ZM23 19L35 12V26L23 33ZM23 36L35 29V41L23 48Z"/>', VIOLET),
    "argo": ('<path d="M8 27C8 8 40 8 40 27V35H8Z"/><circle cx="18" cy="26" r="2"/><circle cx="30" cy="26" r="2"/><path d="M10 35V42M18 35V45M26 35V43M34 35V45M40 35V40"/>', AMBER),
    "kargo": ('<path d="M8 34L13 14L29 9L40 21L34 35Z"/><path d="M13 14L25 22L40 21M25 22L25 39M9 34L25 39L34 35"/>', TEAL),
    "prometheus": ('<path d="M10 35H38M13 40H35M18 45H30M14 30C7 24 16 19 17 11C17 17 26 16 24 5C36 18 40 25 34 30Z"/>', RED),
    "grafana": ('<path d="M39 16C24 -1 5 16 13 32C19 45 37 39 35 27C33 18 21 20 22 27C23 31 28 30 28 27M39 16L42 8M13 32L6 36M25 9L25 4"/>', AMBER),
    "chaos": ('<path d="M8 10H18V20H8ZM30 10H40V20H30ZM19 21H29V31H19ZM8 32H18V42H8ZM30 32H40V42H30Z"/>', VIOLET),
    "payments": ('<rect x="6" y="13" width="36" height="27" rx="5"/><path d="M7 22H41M12 32H20M25 7L30 2L35 7M30 2V14"/>', TEAL),
}


def icon(name: str, title: str) -> str:
    symbol, color = SYMBOLS[name]
    c = Canvas(96, title, f"Original presentation pictogram for {title}; not an official vendor logo.", 96)
    c.rect(1, 1, 94, 94, fill="#102039", stroke="#2e435e", radius=18)
    c.add(f'<g transform="translate(17 11) scale(1.3)" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{symbol}</g>')
    c.text(48, 84, title, 10, MUTED, 700, "middle")
    return c.finish()


def assets() -> dict[Path, str]:
    output = {ROOT / name: builder() for name, builder in {
        "readme-hero.svg": hero,
        "platform-architecture.svg": architecture,
        "promotion-flow.svg": promotion,
        "chaos-gate.svg": chaos,
        "payment-flow.svg": payment,
    }.items()}
    names = {"python": "PYTHON", "kubernetes": "KUBERNETES", "terraform": "TERRAFORM",
             "argo": "ARGO CD", "kargo": "KARGO", "prometheus": "PROMETHEUS",
             "grafana": "GRAFANA", "chaos": "CHAOS MESH", "payments": "x402 / PERMIT2"}
    output.update({ROOT / "icons" / f"stack-{name}.svg": icon(name, title) for name, title in names.items()})
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify generated assets without rewriting")
    args = parser.parse_args()
    mismatches = []
    for path, content in assets().items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                mismatches.append(path.relative_to(ROOT))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if mismatches:
        for path in mismatches:
            print(f"out of date: {path}")
        return 1
    print(f"{len(assets())} presentation SVGs {'are current' if args.check else 'generated'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
