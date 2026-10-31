#!/usr/bin/env python3
"""Inventory likely Unity/PS4 asset paths without extracting or modifying game data.

Accepts a PkgUnpack --list text output and/or a directory of private extracts.
This is file/path triage, NOT a Unity scene parser or a version validator.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

LIST_ROW = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")
LEVEL_NAME = re.compile(r"^level\d+(?:\.assets)?$", re.IGNORECASE)
BUNDLE_EXTENSIONS = (".bundle", ".unity3d", ".assetbundle")
ASSET_EXTENSIONS = (".assets", ".ress", ".resource")
IMPORTANT_NAMES = {
    "globalgamemanagers", "globalgamemanagers.assets", "maindata",
    "resources.assets", "resources.resource", "boot.config",
    "data.unity3d", "level0",
}


@dataclass(frozen=True)
class Entry:
    path: str
    size: int | None


def normalized_path(raw: str) -> str:
    return raw.replace("\\", "/").lstrip("./")


def classify(path: str) -> str | None:
    """Return a triage class, never an assertion about serialized contents."""
    norm = normalized_path(path).lower()
    name = norm.split("/")[-1]
    if name == "boot.config" or name == "globalgamemanagers" or name == "globalgamemanagers.assets":
        return "player-config"
    if LEVEL_NAME.match(name) or name == "maindata":
        return "scene-candidate"
    if name in IMPORTANT_NAMES or name.endswith(ASSET_EXTENSIONS):
        return "serialized-asset-candidate"
    if name.endswith(BUNDLE_EXTENSIONS):
        return "bundle-candidate"
    if name.endswith((".json", ".xml", ".bytes", ".dat")) and "rewired" in norm:
        return "rewired-named-file"
    if "streamingassets/" in norm:
        return "streamingasset"
    if name.endswith(".res") or name.endswith(".ress") or name.endswith(".resource"):
        return "resource-sidecar"
    return None


def parse_listing(text: str) -> list[Entry]:
    result: list[Entry] = []
    for line in text.splitlines():
        match = LIST_ROW.match(line)
        if not match:
            continue
        size = int(match.group(1))
        filename = match.group(2).removesuffix("   (pkg entry)").strip()
        if filename and not filename.endswith("/"):
            result.append(Entry(normalized_path(filename), size))
    return result


def scan_directory(root: Path) -> list[Entry]:
    if not root.is_dir():
        raise ValueError("source directory does not exist")
    return [
        Entry(path.relative_to(root).as_posix(), path.stat().st_size)
        for path in sorted(root.rglob("*")) if path.is_file()
    ]


def report(entries: list[Entry]) -> str:
    unique = {e.path: e for e in entries}
    found = sorted(
        ((classify(e.path), e) for e in unique.values() if classify(e.path)),
        key=lambda pair: (pair[0], pair[1].path.lower())
    )
    lines = [
        "# The Forest PS4 — Unity asset inventory (read-only)",
        "",
        f"- Input paths: {len(unique)}; potential Unity/scene/resource paths: {len(found)}.",
        "- Filename heuristics only: no claim that scenes or Rewired actions are parsed.",
        "- Do not commit extracted proprietary assets; only this inventory is suitable for review.",
        "",
        "| Class | Size (bytes) | Relative path |",
        "| --- | ---: | --- |",
    ]
    for category, entry in found:
        safe = entry.path.replace("|", "\\|").replace("`", "\\`")
        lines.append(f"| {category} | {entry.size if entry.size is not None else '—'} | `{safe}` |")
    if not found:
        lines.append("| — | — | No matching filenames in supplied inputs |")
    lines.extend([
        "", "## Interpretation",
        "",
        "- A `globalgamemanagers` or `levelN` filename is a candidate, not confirmed Unity version or scene.",
        "- A Rewired-named file is NOT evidence of the DS4 action mapping; serialized object parsing is still required.",
        "- Exact Player version must be confirmed from recognized Unity serialization metadata or a compatible parser.",
        "- Candidate assets can later be extracted selectively to a private folder; no writes happen here.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing", type=Path, help="saved PkgUnpack --list output")
    parser.add_argument("--root", type=Path, help="private extracted-files directory")
    parser.add_argument("--output", type=Path, help="optional report path")
    opts = parser.parse_args()
    if not opts.root and not opts.listing:
        parser.error("provide --listing and/or --root")
    entries: list[Entry] = []
    try:
        if opts.listing:
            entries.extend(parse_listing(opts.listing.read_text(encoding="utf-8")))
        if opts.root:
            entries.extend(scan_directory(opts.root))
        rendered = report(entries)
        if opts.output:
            opts.output.parent.mkdir(parents=True, exist_ok=True)
            opts.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"asset-inventory: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
