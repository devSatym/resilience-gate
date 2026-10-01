#!/usr/bin/env python3
"""Sanitize and validate evidence without depending on a cloud SDK.

The live-run scripts deliberately keep raw command output out of the repository.
This small standard-library helper is their single place for redaction and for
the run-metadata contract. It is intentionally conservative: a line that looks
like it may carry a credential is replaced as a whole instead of trying to
preserve a possibly sensitive value.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCENARIOS = {"baseline", "chaos-gate", "regression-blocked", "recovery", "prod-smoke"}
SCENARIO_NAMESPACES = {
    "baseline": "url-shortener-dev",
    "chaos-gate": "url-shortener-staging",
    "regression-blocked": "url-shortener-staging",
    "recovery": "url-shortener-staging",
    "prod-smoke": "url-shortener-prod",
}
STATUSES = {"pass", "fail", "blocked", "unavailable"}
REDACTIONS = {"credentials", "secret-data", "wallet-keys", "authorization-headers", "none"}
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
REVISION_PATTERN = re.compile(r"^(?:[0-9a-f]{7,64}|unavailable)$")
DIGEST_PATTERN = re.compile(r"^(?:sha256:[0-9a-f]{64}|unavailable)$")
RELATIVE_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
SCORECARD_SCHEMA_VERSION = "resilience-gate.scorecard/v1"

# Keep this list broad on purpose. The utility is used for evidence, not for
# diagnostics where retaining a field name is more valuable than safety.
SENSITIVE_FIELD = re.compile(
    r"(?ix)\b("
    r"authorization|proxy-authorization|cookie|set-cookie|"
    r"password|passwd|secret|token|credential|"
    r"api[-_ ]?key|access[-_ ]?key|client[-_ ]?secret|"
    r"private[-_ ]?key|wallet[-_ ]?(?:key|seed)|mnemonic|"
    r"x-payment|payment[-_ ]?signature"
    r")\b\s*[:=]"
)
BEARER_VALUE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
PRIVATE_HEX = re.compile(r"(?<![0-9a-fA-F])0x[0-9a-fA-F]{64}(?![0-9a-fA-F])")
LONG_BASE64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{80,}={0,2}(?![A-Za-z0-9+/=])")
KUBERNETES_SECRET_KIND = re.compile(r"^\s*kind\s*:\s*['\"]?secret['\"]?\s*(?:#.*)?$", re.IGNORECASE)
YAML_DOCUMENT_SEPARATOR = re.compile(r"^---\s*(?:#.*)?$")
YAML_SENSITIVE_DATA_BLOCK = re.compile(r"^([ \t]*)(?:data|stringData):\s*(?:#.*)?$", re.IGNORECASE)


class ContractError(ValueError):
    """Raised when evidence cannot safely satisfy the public contract."""


def category_for(line: str) -> str:
    lowered = line.lower()
    if any(token in lowered for token in ("authorization", "bearer", "basic ", "cookie", "x-payment", "payment-signature")):
        return "authorization-headers"
    if any(token in lowered for token in ("wallet", "mnemonic", "private-key", "private_key", "private key")):
        return "wallet-keys"
    if "secret" in lowered or re.search(r"\bdata\b\s*[:=]", lowered):
        return "secret-data"
    return "credentials"


def sanitize_document(lines: list[str], categories: set[str]) -> list[str]:
    """Sanitize one YAML-like document without allowing short secret values through."""

    # A Kubernetes Secret is never useful evidence in raw form. Detect the
    # document before processing individual values so short base64 data cannot
    # evade the generic long-base64 detector.
    if any(KUBERNETES_SECRET_KIND.match(line.rstrip("\r\n")) for line in lines):
        categories.add("secret-data")
        return ["[REDACTED: Kubernetes Secret document]\n"]

    cleaned: list[str] = []
    inside_pem = False
    data_block_indent: int | None = None

    for raw_line in lines:
        line = raw_line
        content = line.rstrip("\r\n")

        # `stringData` is Secret-only and `data` is often Secret data. Treat a
        # bare YAML block conservatively, including short values on following
        # lines, rather than retaining something that looks harmless in base64.
        data_block_match = YAML_SENSITIVE_DATA_BLOCK.match(content)
        if data_block_match:
            data_block_indent = len(data_block_match.group(1).expandtabs(2))
            categories.add("secret-data")
            cleaned.append("[REDACTED: secret-data]\n")
            continue
        if data_block_indent is not None:
            indentation = len(line) - len(line.lstrip(" \t"))
            if not content.strip() or content.lstrip().startswith("#") or indentation > data_block_indent:
                categories.add("secret-data")
                cleaned.append("[REDACTED: secret-data]\n")
                continue
            data_block_indent = None

        if "-----BEGIN " in line and "PRIVATE KEY-----" in line:
            inside_pem = True
            categories.add("credentials")
            cleaned.append("[REDACTED: credentials]\n")
            continue
        if inside_pem:
            categories.add("credentials")
            cleaned.append("[REDACTED: credentials]\n")
            if "-----END " in line and "PRIVATE KEY-----" in line:
                inside_pem = False
            continue

        if SENSITIVE_FIELD.search(line):
            category = category_for(line)
            categories.add(category)
            cleaned.append(f"[REDACTED: {category}]\n")
            continue

        def redact_bearer(match: re.Match[str]) -> str:
            categories.add("authorization-headers")
            return "<REDACTED authorization>"

        def redact_url_credentials(match: re.Match[str]) -> str:
            categories.add("credentials")
            return f"{match.group(1)}<REDACTED>@"

        def redact_private_hex(_match: re.Match[str]) -> str:
            categories.add("wallet-keys")
            return "0x<REDACTED wallet key>"

        def redact_base64(_match: re.Match[str]) -> str:
            categories.add("secret-data")
            return "<REDACTED encoded data>"

        line = BEARER_VALUE.sub(redact_bearer, line)
        line = URL_CREDENTIALS.sub(redact_url_credentials, line)
        line = PRIVATE_HEX.sub(redact_private_hex, line)
        line = LONG_BASE64.sub(redact_base64, line)
        cleaned.append(line)

    return cleaned


def sanitize_text(source: str) -> tuple[str, list[str]]:
    """Return redacted text and the categories that were removed.

    YAML documents are separated before line processing so an entire Kubernetes
    Secret document can be removed. PEM blocks and risky standalone fields are
    then handled conservatively within the other documents.
    """

    categories: set[str] = set()
    cleaned: list[str] = []
    document: list[str] = []
    for line in source.splitlines(keepends=True):
        if YAML_DOCUMENT_SEPARATOR.match(line.rstrip("\r\n")):
            cleaned.extend(sanitize_document(document, categories))
            cleaned.append(line)
            document = []
        else:
            document.append(line)
    cleaned.extend(sanitize_document(document, categories))
    return "".join(cleaned), sorted(categories) or ["none"]


def read_text(path: str) -> str:
    if path == "-":
        payload = sys.stdin.buffer.read()
    else:
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.is_file():
            raise ContractError(f"input must be a regular file: {candidate}")
        payload = candidate.read_bytes()
    if len(payload) > 5 * 1024 * 1024:
        raise ContractError("evidence input exceeds the 5 MiB safety limit")
    return payload.decode("utf-8", errors="replace")


def sanitize(args: argparse.Namespace) -> int:
    text = read_text(args.input)
    cleaned, categories = sanitize_text(text)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(cleaned, encoding="utf-8")
    if args.report:
        Path(args.report).write_text("\n".join(categories) + "\n", encoding="utf-8")
    return 0


def extract_scorecard(args: argparse.Namespace) -> int:
    """Recover one complete scorecard from sanitized gate-container logs.

    Kubernetes prefixes multi-container logs with pod and container metadata.
    Scorecards themselves are emitted as one JSON object per line, so scan from
    the first JSON-object marker rather than assuming an unprefixed log line.
    Requiring exactly one structurally complete match prevents a stale or
    ambiguous log excerpt from being presented as evidence.
    """

    matches: list[dict[str, Any]] = []
    for line in read_text(args.input).splitlines():
        marker = line.find("{")
        if marker < 0:
            continue
        try:
            payload = json.loads(line[marker:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema_version") != SCORECARD_SCHEMA_VERSION:
            continue
        if payload.get("experiment") != args.experiment:
            continue
        if payload.get("verdict") not in {"pass", "fail"}:
            continue
        checks = payload.get("checks")
        release = payload.get("release")
        if not isinstance(checks, list) or not checks:
            continue
        if not isinstance(release, dict) or any(
            not isinstance(release.get(field), str) or not release[field]
            for field in ("revision", "image_digest", "run_id")
        ):
            continue
        matches.append(payload)

    if len(matches) != 1:
        raise ContractError(
            f"expected exactly one complete {args.experiment} scorecard in the sanitized log; "
            f"found {len(matches)}"
        )

    destination = Path(args.output)
    if destination.is_symlink():
        raise ContractError(f"scorecard output must not be a symlink: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(matches[0], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def expect_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be a string")
    return value


def expect_pattern(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    string = expect_string(value, name)
    if not pattern.fullmatch(string):
        raise ContractError(f"{name} has an invalid format")
    return string


def validate_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ContractError("run metadata must be a JSON object")

    required = {
        "schema_version",
        "run_id",
        "scenario",
        "status",
        "collected_at",
        "repository_revision",
        "chart_revision",
        "release_image_digest",
        "gate_runner_image_digest",
        "signer_image_digest",
        "loadgen_image_digest",
        "namespace",
        "cluster_context",
        "evidence",
    }
    missing = required - metadata.keys()
    unexpected = set(metadata) - required
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected: {', '.join(sorted(unexpected))}")
        raise ContractError("run metadata fields are invalid (" + "; ".join(details) + ")")

    if metadata["schema_version"] != "1.0":
        raise ContractError("schema_version must be 1.0")
    expect_pattern(metadata["run_id"], "run_id", RUN_ID_PATTERN)
    if metadata["scenario"] not in SCENARIOS:
        raise ContractError("scenario is not supported")
    if metadata["status"] not in STATUSES:
        raise ContractError("status is not supported")
    collected_at = expect_string(metadata["collected_at"], "collected_at")
    try:
        datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("collected_at must be an ISO-8601 timestamp") from error
    for field in (
        "repository_revision",
        "chart_revision",
    ):
        expect_pattern(metadata[field], field, REVISION_PATTERN)
    for field in (
        "release_image_digest",
        "gate_runner_image_digest",
        "signer_image_digest",
        "loadgen_image_digest",
    ):
        expect_pattern(metadata[field], field, DIGEST_PATTERN)
    expected_namespace = SCENARIO_NAMESPACES[metadata["scenario"]]
    if metadata["namespace"] != expected_namespace:
        raise ContractError(f"namespace must be {expected_namespace} for {metadata['scenario']}")
    cluster_context = expect_string(metadata["cluster_context"], "cluster_context")
    if not 1 <= len(cluster_context) <= 200 or "\n" in cluster_context:
        raise ContractError("cluster_context must be one non-empty line")

    evidence = metadata["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {"files", "redactions"}:
        raise ContractError("evidence must contain only files and redactions")
    files = evidence["files"]
    if not isinstance(files, list) or not files:
        raise ContractError("evidence.files must be a non-empty array")
    if len(files) != len(set(files)):
        raise ContractError("evidence.files must not contain duplicates")
    for item in files:
        item = expect_pattern(item, "evidence.files entry", RELATIVE_FILE_PATTERN)
        if ".." in item.split("/") or "//" in item:
            raise ContractError("evidence.files entry must be a safe relative path")
    redactions = evidence["redactions"]
    if not isinstance(redactions, list) or not redactions:
        raise ContractError("evidence.redactions must be a non-empty array")
    if len(redactions) != len(set(redactions)) or any(item not in REDACTIONS for item in redactions):
        raise ContractError("evidence.redactions contains an unsupported category")
    if "none" in redactions and len(redactions) != 1:
        raise ContractError("none cannot be combined with an actual redaction category")
    return metadata


def load_schema(path: str) -> None:
    try:
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"could not read JSON schema: {error}") from error
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractError("run-metadata schema must declare JSON Schema Draft 2020-12")
    if schema.get("properties", {}).get("schema_version", {}).get("const") != "1.0":
        raise ContractError("run-metadata schema must require schema_version 1.0")


def validate(args: argparse.Namespace) -> int:
    if args.schema:
        load_schema(args.schema)
    try:
        payload = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"could not read run metadata: {error}") from error
    validate_metadata(payload)
    return 0


def write_metadata(args: argparse.Namespace) -> int:
    metadata = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "scenario": args.scenario,
        "status": args.status,
        "collected_at": args.collected_at,
        "repository_revision": args.repository_revision,
        "chart_revision": args.chart_revision,
        "release_image_digest": args.release_image_digest,
        "gate_runner_image_digest": args.gate_runner_image_digest,
        "signer_image_digest": args.signer_image_digest,
        "loadgen_image_digest": args.loadgen_image_digest,
        "namespace": args.namespace,
        "cluster_context": args.cluster_context,
        "evidence": {
            "files": args.file,
            "redactions": sorted(set(args.redaction)) or ["none"],
        },
    }
    validate_metadata(metadata)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    redact = commands.add_parser("sanitize", help="write a sanitized text copy")
    redact.add_argument("--input", required=True, help="regular file path or - for stdin")
    redact.add_argument("--output", required=True)
    redact.add_argument("--report", help="write one redaction category per line")
    redact.set_defaults(handler=sanitize)

    scorecard = commands.add_parser(
        "extract-scorecard", help="recover one complete scorecard from sanitized gate logs"
    )
    scorecard.add_argument("--input", required=True, help="sanitized gate log file")
    scorecard.add_argument(
        "--experiment",
        required=True,
        choices=("postgres-pod-failure", "redis-pod-failure", "signer-pod-failure"),
    )
    scorecard.add_argument("--output", required=True)
    scorecard.set_defaults(handler=extract_scorecard)

    validation = commands.add_parser("validate", help="validate run metadata")
    validation.add_argument("--metadata", required=True)
    validation.add_argument("--schema", help="also verify the repository schema declaration")
    validation.set_defaults(handler=validate)

    metadata = commands.add_parser("write-metadata", help="write validated run metadata")
    metadata.add_argument("--output", required=True)
    metadata.add_argument("--run-id", required=True)
    metadata.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    metadata.add_argument("--status", required=True, choices=sorted(STATUSES))
    metadata.add_argument("--collected-at", required=True)
    metadata.add_argument("--repository-revision", required=True)
    metadata.add_argument("--chart-revision", required=True)
    metadata.add_argument("--release-image-digest", required=True)
    metadata.add_argument("--gate-runner-image-digest", required=True)
    metadata.add_argument("--signer-image-digest", required=True)
    metadata.add_argument("--loadgen-image-digest", required=True)
    metadata.add_argument("--namespace", required=True)
    metadata.add_argument("--cluster-context", required=True)
    metadata.add_argument("--file", action="append", default=[])
    metadata.add_argument("--redaction", action="append", default=[])
    metadata.set_defaults(handler=write_metadata)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.handler(args)
    except ContractError as error:
        print(f"evidence utility: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
