#!/usr/bin/env python3
"""Fail-closed file-tree diff for private PS4 package working copies.

This tool does not parse, decrypt, build, sign, or install PKGs. It compares an
original extracted tree with a candidate tree and proves that every added,
removed, or changed path is explicitly allowlisted. Reports contain paths,
sizes, and hashes only; never file contents or absolute root paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath

CHUNK_SIZE = 1024 * 1024


class AuditError(ValueError):
    pass


def normalize_relative(value: str) -> str:
    """Validate a repository-independent POSIX relative path."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise AuditError("paths must be non-empty POSIX relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise AuditError("path is absolute or contains a traversal segment")
    normalized = path.as_posix()
    if normalized != value:
        raise AuditError("path is not in normalized POSIX form")
    return normalized


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while True:
                block = stream.read(CHUNK_SIZE)
                if not block:
                    break
                size += len(block)
                digest.update(block)
    except OSError as exc:
        raise AuditError(f"file cannot be read: {path.name} ({exc.strerror})") from None
    return size, digest.hexdigest()


def inventory_tree(root: Path) -> dict[str, dict[str, object]]:
    """Inventory regular files and directories, rejecting ambiguous objects."""
    if root.is_symlink() or not root.is_dir():
        raise AuditError("tree root must be an existing, non-symlink directory")

    entries: dict[str, dict[str, object]] = {}
    folded: dict[str, str] = {}
    try:
        paths = sorted(root.rglob("*"), key=lambda item: item.as_posix())
    except OSError as exc:
        raise AuditError(f"tree cannot be enumerated ({exc.strerror})") from None
    for path in paths:
        rel = path.relative_to(root).as_posix()
        rel = normalize_relative(rel)
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise AuditError(f"path cannot be inspected: {rel} ({exc.strerror})") from None
        if stat.S_ISLNK(mode):
            raise AuditError(f"symlink is not allowed: {rel}")
        if stat.S_ISDIR(mode):
            entry: dict[str, object] = {"kind": "directory", "size": 0}
        elif stat.S_ISREG(mode):
            size, digest = _hash_file(path)
            entry = {"kind": "file", "size": size, "sha256": digest}
        else:
            raise AuditError(f"non-regular filesystem object is not allowed: {rel}")

        key = rel.casefold()
        if key in folded:
            raise AuditError(f"case-insensitive path collision: {folded[key]} and {rel}")
        folded[key] = rel
        entries[rel] = entry
    return entries


def _tree_digest(entries: dict[str, dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for name in sorted(entries):
        item = entries[name]
        record = "\0".join((name, str(item["kind"]), str(item["size"]),
                            str(item.get("sha256", "")))) + "\n"
        digest.update(record.encode("utf-8"))
    return digest.hexdigest()


def audit_trees(source_root: Path, candidate_root: Path,
                allow_changes: list[str] | None = None,
                required_paths: list[str] | None = None) -> dict:
    allowed = sorted(set(normalize_relative(x) for x in (allow_changes or [])))
    required = sorted(set(normalize_relative(x) for x in (required_paths or [])))
    source = inventory_tree(source_root)
    candidate = inventory_tree(candidate_root)

    missing_required = [p for p in required
                        if p not in source or p not in candidate
                        or source[p]["kind"] != "file"
                        or candidate[p]["kind"] != "file"]

    changes: list[dict[str, object]] = []
    for path in sorted(set(source) | set(candidate)):
        before = source.get(path)
        after = candidate.get(path)
        if before == after:
            continue
        if before is None:
            status = "added"
        elif after is None:
            status = "removed"
        else:
            status = "changed"
        changes.append({"path": path, "status": status,
                        "source": before, "candidate": after})

    unexpected = [row["path"] for row in changes if row["path"] not in allowed]
    passed = not missing_required and not unexpected
    return {
        "schema": 1,
        "result": "PASS" if passed else "FAIL",
        "source_tree": {"files": sum(x["kind"] == "file" for x in source.values()),
                        "directories": sum(x["kind"] == "directory" for x in source.values()),
                        "tree_sha256": _tree_digest(source)},
        "candidate_tree": {"files": sum(x["kind"] == "file" for x in candidate.values()),
                           "directories": sum(x["kind"] == "directory" for x in candidate.values()),
                           "tree_sha256": _tree_digest(candidate)},
        "allow_changes": allowed,
        "required_paths": required,
        "missing_required_paths": missing_required,
        "changes": changes,
        "unexpected_change_paths": unexpected,
        "limitations": [
            "file-tree comparison only; does not validate Unity object tables or PPtrs",
            "does not validate PKG cryptography, package-base compatibility, or installation",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("candidate_root", type=Path)
    parser.add_argument("--allow-change", action="append", default=[], metavar="RELATIVE_PATH",
                        help="exact path allowed to differ; may be repeated")
    parser.add_argument("--require", action="append", default=[], metavar="RELATIVE_PATH",
                        help="file that must exist in both trees; may be repeated")
    parser.add_argument("--output", type=Path,
                        help="write the metadata-only JSON report here")
    args = parser.parse_args(argv)

    try:
        report = audit_trees(args.source_root, args.candidate_root,
                             args.allow_change, args.require)
    except (AuditError, OSError) as exc:
        report = {"schema": 1, "result": "ERROR", "error": str(exc)}

    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"schema": 1, "result": "ERROR",
                              "error": f"cannot write report ({exc.strerror})"},
                             indent=2, sort_keys=True))
            return 2
    else:
        print(encoded, end="")
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
