#!/usr/bin/env python3
"""Render reviewed, public GitOps identifiers from one local configuration.

The renderer intentionally has no cloud SDK dependency and never reads secret
values. Templates live under platform_setup_scripts/templates; generated paths
remain ordinary reviewable files. Operators must inspect and commit the public
diff before bootstrap can use it.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_CONFIG = SCRIPT_DIR / "config.env"
DEFAULT_TEMPLATE_ROOT = SCRIPT_DIR / "templates"

TEMPLATES = (
    Path("kubernetes/bootstrap/secrets/cluster-secret-store.yaml"),
    Path("kubernetes/bootstrap/secrets/external-secrets-argocd.yaml"),
    Path("kubernetes/argocd/root-app.yaml"),
    Path("kubernetes/bootstrap/observability.yaml"),
    Path("kubernetes/bootstrap/chaos-jobs.yaml"),
    Path("kubernetes/bootstrap/chaos-gate.yaml"),
    Path("kubernetes/jobs/radius-signer.yaml"),
    Path("kubernetes/kargo/credentials-git.yaml"),
    Path("kubernetes/kargo/warehouse.yaml"),
    Path("kubernetes/kargo/analysistemplate.yaml"),
    Path("kubernetes/kargo/stage-dev.yaml"),
    Path("kubernetes/kargo/stage-staging.yaml"),
    Path("kubernetes/kargo/stage-prod.yaml"),
    Path("kubernetes/apps/appproject.yaml"),
    Path("kubernetes/apps/applicationset.yaml"),
)
TOKEN = re.compile(r"\{\{\s*([A-Z][A-Z0-9_]*)\s*\}\}")
PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
REGION = re.compile(r"^[a-z]+-[a-z]+[0-9]$")
ZONE = re.compile(r"^[a-z]+-[a-z]+[0-9]-[a-z]$")
DNS_LABEL = re.compile(r"^[a-z]([-a-z0-9]{0,38}[a-z0-9])?$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BUCKET = re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
# A syntactically valid but intentionally unresolvable digest prevents a fresh
# lab bootstrap from becoming circular: the first gate image cannot be built in
# the new private registry until the platform is up. An operator replaces this
# sentinel with the signed CI digest, renders, reviews, and commits it before
# requesting a staging promotion.
UNRESOLVABLE_GATE_RUNNER_DIGEST = "sha256:" + "0" * 64
UNRESOLVABLE_SIGNER_DIGEST = "sha256:" + "0" * 64


class ConfigError(ValueError):
    """A local public configuration is incomplete or unsafe to render."""


def parse_config(path: Path) -> dict[str, str]:
    """Read simple quoted KEY=value public values without evaluating shell."""
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")

    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("SECRETS=") or line in {"(", ")"}:
            continue
        match = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$", line)
        if not match:
            # Non-public Bash constructs such as the body of SECRETS are
            # intentionally ignored. No values are evaluated by this program.
            continue
        key, raw_value = match.groups()
        try:
            words = shlex.split(raw_value, comments=True, posix=True)
        except ValueError as exc:
            raise ConfigError(f"invalid value on line {number} for {key}: {exc}") from exc
        if len(words) > 1:
            raise ConfigError(f"line {number}: {key} must have one scalar value")
        values[key] = words[0] if words else ""
    return values


def required(values: dict[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigError(f"{key} is required in config.env")
    return value


def make_context(values: dict[str, str]) -> dict[str, str]:
    project_id = required(values, "PROJECT_ID")
    github_repo = required(values, "GITHUB_REPO")
    region = values.get("REGION", "us-central1").strip() or "us-central1"
    zone = values.get("ZONE", f"{region}-a").strip() or f"{region}-a"
    cluster = values.get("CLUSTER_NAME", "resilience-gate").strip() or "resilience-gate"
    repository = values.get("GAR_REPO", "resilience-gate").strip() or "resilience-gate"
    bucket = values.get("TF_STATE_BUCKET", "").strip() or f"{project_id}-tf-state"
    gate_runner_digest = values.get("GATE_RUNNER_DIGEST", "").strip() or UNRESOLVABLE_GATE_RUNNER_DIGEST
    signer_digest = values.get("SIGNER_DIGEST", "").strip() or UNRESOLVABLE_SIGNER_DIGEST

    if not PROJECT_ID.fullmatch(project_id):
        raise ConfigError("PROJECT_ID is not a valid GCP project ID")
    if not REPOSITORY.fullmatch(github_repo):
        raise ConfigError("GITHUB_REPO must use owner/repository form")
    if not REGION.fullmatch(region) or not ZONE.fullmatch(zone) or not zone.startswith(f"{region}-"):
        raise ConfigError("REGION and ZONE must be a matching GCP region and zonal location")
    if not DNS_LABEL.fullmatch(cluster):
        raise ConfigError("CLUSTER_NAME is not a valid GKE DNS label")
    if not DNS_LABEL.fullmatch(repository):
        raise ConfigError("GAR_REPO is not a valid Artifact Registry repository ID")
    if not BUCKET.fullmatch(bucket):
        raise ConfigError("TF_STATE_BUCKET is not a valid GCS bucket name")
    if not DIGEST.fullmatch(gate_runner_digest):
        raise ConfigError("GATE_RUNNER_DIGEST must be a lowercase sha256 digest")
    if not DIGEST.fullmatch(signer_digest):
        raise ConfigError("SIGNER_DIGEST must be a lowercase sha256 digest")

    owner, repo_name = github_repo.split("/", 1)
    return {
        "PROJECT_ID": project_id,
        "REGION": region,
        "ZONE": zone,
        "CLUSTER_NAME": cluster,
        "GAR_REPO": repository,
        "TF_STATE_BUCKET": bucket,
        "GITHUB_REPO": github_repo,
        "GITHUB_OWNER": owner,
        "GITHUB_REPOSITORY_URL": f"https://github.com/{github_repo}.git",
        "GITHUB_REPOSITORY_NAME": repo_name,
        "GATE_RUNNER_DIGEST": gate_runner_digest,
        "SIGNER_DIGEST": signer_digest,
    }


def render(template: str, context: dict[str, str], source: Path) -> str:
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            missing.add(key)
            return match.group(0)
        return context[key]

    rendered = TOKEN.sub(replace, template)
    if missing:
        raise ConfigError(f"{source}: unsupported template token(s): {', '.join(sorted(missing))}")
    if TOKEN.search(rendered):
        raise ConfigError(f"{source}: unresolved template token")
    return rendered


def generated_files(template_root: Path, output_root: Path, context: dict[str, str]):
    for relative_path in TEMPLATES:
        template_path = template_root / relative_path.with_suffix(relative_path.suffix + ".tmpl")
        if not template_path.is_file():
            raise ConfigError(f"template missing: {template_path}")
        yield output_root / relative_path, render(template_path.read_text(encoding="utf-8"), context, template_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="local public config.env")
    parser.add_argument("--template-root", type=Path, default=DEFAULT_TEMPLATE_ROOT)
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write rendered public manifests")
    mode.add_argument("--check", action="store_true", help="fail if reviewed manifests are stale")
    mode.add_argument("--print-context", action="store_true", help="print only public rendering context")
    args = parser.parse_args(argv)

    try:
        context = make_context(parse_config(args.config))
        if args.print_context:
            print(json.dumps(context, indent=2, sort_keys=True))
            return 0

        stale: list[Path] = []
        for output_path, contents in generated_files(args.template_root, args.output_root, context):
            if args.write:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(contents, encoding="utf-8")
                print(f"rendered {output_path.relative_to(args.output_root)}")
            elif not output_path.is_file() or output_path.read_text(encoding="utf-8") != contents:
                stale.append(output_path)

        if stale:
            rendered = ", ".join(str(path.relative_to(args.output_root)) for path in stale)
            raise ConfigError(f"rendered manifests are stale: {rendered}; run make render-config and review the diff")
    except ConfigError as exc:
        print(f"render_config: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
