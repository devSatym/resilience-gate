from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.main import Settings, ShortenRequest, validate_destination_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" https://example.test/path ", "https://example.test/path"),
        ("http://example.test", "http://example.test"),
    ],
)
def test_accepts_absolute_http_urls(raw: str, expected: str) -> None:
    assert validate_destination_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["example.test", "ftp://example.test", "https:///missing-host", "https://u:p@example.test"],
)
def test_rejects_unsafe_or_relative_urls(raw: str) -> None:
    with pytest.raises(ValueError):
        validate_destination_url(raw)


def test_request_model_uses_url_validation() -> None:
    assert ShortenRequest(url="https://example.test").url == "https://example.test"
    with pytest.raises(ValidationError):
        ShortenRequest(url="not-a-url")


def test_settings_rejects_unusable_code_length(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_LENGTH", "2")
    with pytest.raises(ValueError, match="CODE_LENGTH"):
        Settings.from_env()
