#!/usr/bin/env python3
"""Post a Grafana region annotation over the gate-run window, tagged
`chaos-gate` + `verdict:pass|fail`, so the dashboard shows the verdict inline.

Non-fatal by design: the gate verdict must never depend on annotation success,
so any problem prints a note and exits 0.

Auth prefers admin basic-auth (GRAFANA_USER/GRAFANA_PASSWORD): Grafana here has
no PVC, so restarts wipe service-account tokens, while the admin user is
re-seeded from the ESO-synced secret on every start. Falls back to a Bearer
token (GRAFANA_TOKEN); skips if neither is set. Uses stdlib urllib — the gate
image has no curl.
"""
import argparse
import base64
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone


def _to_ms(iso: str | None) -> int | None:
    """Convert a Kubernetes RFC3339 timestamp (including fractional seconds)."""
    try:
        if not iso:
            return None
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict", required=True, choices=["pass", "fail"])
    ap.add_argument("--failed", default="", help="comma-sep experiment names that failed")
    ap.add_argument("--start", default="", help="run start, ISO8601 Z (workflow .status.startTime)")
    ap.add_argument("--end", default="", help="run end, ISO8601 Z (workflow .status.endTime)")
    ap.add_argument("--workflow", default="", help="workflow name, for the annotation text")
    a = ap.parse_args(argv)

    url = os.environ.get("GRAFANA_URL", "http://observability-grafana.monitoring.svc").rstrip("/")
    user = os.environ.get("GRAFANA_USER", "admin").strip()
    password = os.environ.get("GRAFANA_PASSWORD", "").strip()
    token = os.environ.get("GRAFANA_TOKEN", "").strip()
    if password:
        authz = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    elif token:
        authz = f"Bearer {token}"
    else:
        print(">> annotate: no GRAFANA_PASSWORD or GRAFANA_TOKEN — skipping (annotation is optional)")
        return 0

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start = _to_ms(a.start) or now_ms
    end = _to_ms(a.end) or now_ms
    if end <= start:                       # point/garbage window — pad to 1s so it renders
        end = start + 1000

    text = f"chaos-gate {a.verdict.upper()}"
    if a.verdict == "fail" and a.failed:
        text += f" — failed: {a.failed}"
    if a.workflow:
        text += f" ({a.workflow})"

    body = json.dumps({
        "time": start,
        "timeEnd": end,
        "tags": ["chaos-gate", f"verdict:{a.verdict}"],
        "text": text,
    }).encode()
    req = urllib.request.Request(
        url + "/api/annotations", data=body, method="POST",
        headers={"Authorization": authz, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f">> annotate: posted ({r.status}) — {text}")
    except Exception as e:                  # noqa: BLE001 — non-fatal on purpose
        print(f"!! annotate failed (non-fatal): {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
