#!/usr/bin/env python3
"""Check local documentation links, reviewed screenshots, and vector artwork.

This check is offline and read-only. It uses the standard library and never
contacts GitHub, Kubernetes, cloud APIs, or a payment service.
"""

from __future__ import annotations

import hashlib
import json
import re
import runpy
import struct
import subprocess
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


class References(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if value and key in {"href", "src"}:
                self.links.append(value)
            if value and key in {"id", "name"}:
                self.ids.add(value)


def prose(text: str) -> str:
    return re.sub(r"^([`~]{3,}).*?^\1\s*$", "", text, flags=re.MULTILINE | re.DOTALL)


def anchors(path: Path) -> set[str]:
    body = prose(path.read_text(encoding="utf-8"))
    html = References()
    html.feed(body)
    counts: Counter[str] = Counter()
    result = set(html.ids)
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", body, re.MULTILINE):
        title = re.sub(r"<[^>]*>", "", match.group(1)).lower()
        slug = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        suffix = f"-{counts[slug]}" if counts[slug] else ""
        counts[slug] += 1
        result.add(slug + suffix)
    return result


def check_links() -> int:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    files = sorted({ROOT / name for name in result.stdout.splitlines()})
    count = 0
    for path in files:
        body = prose(path.read_text(encoding="utf-8"))
        html = References()
        html.feed(body)
        links = [*html.links, *re.findall(r"\]\(<?([^\s)>]+)>?(?:\s+\"[^\"]*\")?\)", body),
                 *re.findall(r"^\s*\[[^\]]+\]:\s*<?([^\s>]+)>?", body, re.MULTILINE)]
        for link in links:
            target = urlsplit(link)
            if target.scheme or target.netloc:
                continue
            if "<" in link or ">" in link:
                continue
            count += 1
            resolved = (path.parent / unquote(target.path)).resolve() if target.path else path
            if not resolved.exists():
                fail(f"{path.relative_to(ROOT)}: missing link {link}")
            elif target.fragment and resolved.suffix == ".md":
                if unquote(target.fragment) not in anchors(resolved):
                    fail(f"{path.relative_to(ROOT)}: missing anchor {link}")
    print(f"checked {count} local references in {len(files)} Markdown files")
    return len(files)


def check_screenshots() -> None:
    directory = ROOT / "docs/screenshots"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    captures = manifest["captures"]
    expected_ids = {f"{i:02}" for i in range(1, 30)} | {"04b", "05b", "12b", "14b", "17b"}
    if {entry["id"] for entry in captures} != expected_ids or len(captures) != 34:
        fail("screenshot manifest must contain exactly 29 canonical captures and 5 companions")
    if manifest.get("canonical_count") != 29 or manifest.get("companion_count") != 5:
        fail("screenshot manifest summary counts are inconsistent")
    listed = set()
    gallery = (directory / "README.md").read_text(encoding="utf-8")
    seen_hashes = set()
    for entry in captures:
        path = (directory / entry["file"]).resolve()
        if not path.is_relative_to(directory.resolve()) or path.is_symlink():
            fail(f"unsafe screenshot path: {entry['file']}")
            continue
        listed.add(path)
        if not path.is_file():
            fail(f"missing reviewed screenshot: {entry['file']}")
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            fail(f"reviewed screenshot bytes changed: {entry['file']}")
        if digest in seen_hashes:
            fail(f"duplicate screenshot bytes: {entry['file']}")
        seen_hashes.add(digest)
        if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
            fail(f"invalid PNG: {entry['file']}")
        else:
            width, height = struct.unpack(">II", data[16:24])
            if width < 400 or height < 200:
                fail(f"unexpectedly small screenshot: {entry['file']}")
        if entry["file"] not in gallery:
            fail(f"accepted screenshot missing from gallery: {entry['file']}")
        if entry.get("sensitive_content_review") != "passed" or entry.get("caption_review") != "approved":
            fail(f"screenshot review incomplete: {entry['file']}")
    actual = {path.resolve() for path in directory.rglob("*.png")}
    if actual != listed:
        fail("PNG inventory does not match the reviewed screenshot manifest")
    print(f"checked {len(captures)} screenshot hashes, dimensions, captions, and inventory")


def check_artwork() -> None:
    generator = runpy.run_path(str(ROOT / "docs/diagrams/presentation.py"))
    for path, expected in generator["assets"]().items():
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            fail(f"presentation artwork out of date: {path.relative_to(ROOT)}")
    files = sorted((ROOT / "docs/diagrams").rglob("*.svg"))
    for path in files:
        tree = ElementTree.parse(path)
        root = tree.getroot()
        if not root.attrib.get("viewBox") or root.attrib.get("role") != "img":
            fail(f"missing accessible SVG frame: {path.relative_to(ROOT)}")
        tags = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}
        if not {"title", "desc"}.issubset(tags) or tags & {"script", "foreignObject", "image"}:
            fail(f"unexpected or inaccessible SVG content: {path.relative_to(ROOT)}")
        for element in root.iter():
            for key, value in element.attrib.items():
                if key.rsplit("}", 1)[-1] == "href" and not value.startswith("#"):
                    fail(f"external SVG resource: {path.relative_to(ROOT)}")
    print(f"checked {len(files)} accessible SVGs and deterministic source regeneration")


def main() -> int:
    try:
        check_links()
        check_screenshots()
        check_artwork()
    except (OSError, KeyError, ValueError, ElementTree.ParseError) as error:
        fail(str(error))
    for error in ERRORS:
        print(f"ERROR: {error}", file=sys.stderr)
    if ERRORS:
        return 1
    print("documentation presentation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
