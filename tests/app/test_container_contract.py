"""Regression contracts for the application image runtime identity."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "app" / "Dockerfile"


def test_application_image_uses_a_numeric_non_root_identity() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "addgroup --gid 10001 --system app" in source
    assert "adduser --uid 10001 --system --ingroup app app" in source
    assert "COPY --chown=10001:10001 . ./app/" in source
    assert "USER 10001:10001" in source
