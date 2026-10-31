#!/usr/bin/env python3
"""Package only synthetic Unity Editor outputs for later hosted validation.

The archive intentionally excludes the Unity log, Editor/install files,
licenses, credentials, classdata.tpk, and anything not named by the validated
Unity report. It can contain one Editor run or two runs for exact comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_unity_editor_probe import _safe_file, validate_editor_report  # noqa: E402

ARCHIVE_MANIFEST = "probe-archive-manifest.json"
ARCHIVE_KIND = "theforest-ucm-unity56-editor-probe"
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_ENTRY_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 128


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or "\\" in value or path.is_absolute() or
            any(part in ("", ".", "..") for part in path.parts) or
            path.as_posix() != value):
        raise ValueError("unsafe archive path")
    return path.as_posix()


def _artifact_paths(root: Path, report: dict) -> list[str]:
    paths = {"unity-editor-report.json"}
    for variant in report["variants"]:
        for role, directory, suffix in (
            ("scene", "scenes", ".unity"),
            ("prefab", "prefabs", ".prefab"),
            ("bundle", "bundles", ""),
        ):
            relative = _safe_relative(variant[role + "Path"])
            item = PurePosixPath(relative)
            if len(item.parts) != 2 or item.parts[0] != directory:
                raise ValueError(f"{role} artifact is outside the expected {directory}/ directory")
            expected_name = {
                "scene": variant["name"] + ".unity",
                "prefab": variant["name"] + ".prefab",
                "bundle": "ucm-probe-" + variant["name"],
            }[role]
            if item.name != expected_name:
                raise ValueError(f"{role} artifact name does not match its probe variant")
            if suffix and not item.name.endswith(suffix):
                raise ValueError(f"{role} artifact has an unexpected file extension")
            paths.add(relative)
            if role in ("scene", "prefab"):
                paths.add(relative + ".meta")
    for relative in paths:
        path = _safe_file(root, relative)
        cursor = root.resolve()
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("symlink artifacts are not accepted")
        if not path.is_file():
            raise ValueError("probe artifact is not a regular file")
        if path.stat().st_size <= 0 or path.stat().st_size > MAX_ENTRY_BYTES:
            raise ValueError("probe artifact exceeds the per-file size limit")
    return sorted(paths)


def _run_manifest(name: str, root: Path) -> tuple[dict, dict[str, bytes]]:
    report = validate_editor_report(root)
    paths = _artifact_paths(root, report)
    files = {}
    entries = []
    total = 0
    for relative in paths:
        data = _safe_file(root, relative).read_bytes()
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("probe output exceeds the total uncompressed size limit")
        archive_path = name + "/" + relative
        files[archive_path] = data
        entries.append({"path": archive_path, "bytes": len(data), "sha256": _sha256(data)})
    return ({"name": name, "unityVersion": report["unityVersion"],
             "buildTarget": report["buildTarget"], "files": entries}, files)


def package(first: Path, archive: Path, repeat: Path | None = None) -> str:
    first = first.resolve()
    archive = archive.resolve()
    if first == archive.parent or first in archive.parents:
        raise ValueError("archive output must be outside the Editor output directory")
    runs = []
    payload: dict[str, bytes] = {}
    first_row, first_files = _run_manifest("run-a", first)
    runs.append(first_row)
    payload.update(first_files)
    if repeat is not None:
        repeat = repeat.resolve()
        if repeat == first:
            raise ValueError("repeat output must be a distinct run directory")
        if repeat == archive.parent or repeat in archive.parents:
            raise ValueError("archive output must be outside both Editor output directories")
        second_row, second_files = _run_manifest("run-b", repeat)
        if first_row["unityVersion"] != second_row["unityVersion"] or \
                first_row["buildTarget"] != second_row["buildTarget"]:
            raise ValueError("repeat output must use the same Unity version and build target")
        runs.append(second_row)
        payload.update(second_files)

    manifest = {
        "schemaVersion": 1,
        "kind": ARCHIVE_KIND,
        "syntheticOnly": True,
        "runCount": len(runs),
        "runs": runs,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    payload[ARCHIVE_MANIFEST] = manifest_bytes
    if len(payload) > MAX_ENTRIES:
        raise ValueError("probe archive exceeds the file-count limit")

    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=False) as zipped:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            zipped.writestr(info, payload[name], compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=9)
    size = archive.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        archive.unlink(missing_ok=True)
        raise ValueError("compressed probe archive exceeds 50 MiB; do not add it to the PR")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    sidecar.write_text(digest + "  " + archive.name + "\n", encoding="ascii")
    return digest


def extract(archive: Path, destination: Path, expected_sha256: str) -> dict:
    archive = archive.resolve()
    destination = destination.resolve()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected archive SHA-256 must be 64 lowercase hex digits")
    if not archive.is_file() or archive.stat().st_size <= 0 or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("archive is missing, empty, or exceeds 50 MiB")
    archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if archive_digest != expected_sha256:
        raise ValueError("archive SHA-256 differs from the supplied digest")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("extraction destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive, "r") as zipped:
        infos = zipped.infolist()
        if not infos or len(infos) > MAX_ENTRIES:
            raise ValueError("archive file count is outside the safe limit")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("archive has duplicate member names")
        for info in infos:
            relative = _safe_relative(info.filename)
            if info.is_dir() or info.flag_bits & 0x1:
                raise ValueError("directories and encrypted archive members are not accepted")
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG):
                raise ValueError("non-regular archive member rejected")
            if info.file_size <= 0 or info.file_size > MAX_ENTRY_BYTES:
                raise ValueError("archive member exceeds the per-file size limit")
            if info.compress_size and info.file_size > info.compress_size * 200:
                raise ValueError("archive member compression ratio exceeds the safe limit")
            _safe_relative(relative)
        if ARCHIVE_MANIFEST not in names:
            raise ValueError("probe archive manifest is missing")
        if zipped.getinfo(ARCHIVE_MANIFEST).file_size > 1024 * 1024:
            raise ValueError("archive manifest exceeds the size limit")

        manifest_bytes = zipped.read(ARCHIVE_MANIFEST)
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if (manifest.get("schemaVersion") != 1 or manifest.get("kind") != ARCHIVE_KIND or
                manifest.get("syntheticOnly") is not True):
            raise ValueError("archive manifest is not the expected synthetic probe schema")
        runs = manifest.get("runs")
        if (not isinstance(runs, list) or len(runs) != manifest.get("runCount") or
                len(runs) not in (1, 2)):
            raise ValueError("archive must contain one or two declared Editor runs")
        expected_members = {ARCHIVE_MANIFEST}
        declared = {}
        for expected_name, row in zip(("run-a", "run-b"), runs):
            if row.get("name") != expected_name or row.get("unityVersion") != "5.6.6f2":
                raise ValueError("archive run metadata has an unexpected name or Unity version")
            entries = row.get("files")
            if not isinstance(entries, list) or not entries:
                raise ValueError("archive run has no declared files")
            for entry in entries:
                member = _safe_relative(entry.get("path", ""))
                if not member.startswith(expected_name + "/"):
                    raise ValueError("archive run member has an unexpected prefix")
                if member in declared:
                    raise ValueError("archive manifest contains duplicate file paths")
                if (not isinstance(entry.get("bytes"), int) or entry["bytes"] <= 0 or
                        not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", ""))):
                    raise ValueError("archive manifest file digest or size is invalid")
                expected_members.add(member)
                declared[member] = entry
        if set(names) != expected_members:
            raise ValueError("archive contains missing or unlisted files")

        total = 0
        for member, entry in declared.items():
            data = zipped.read(member)
            total += len(data)
            info = zipped.getinfo(member)
            if (len(data) != entry["bytes"] or len(data) != info.file_size or
                    _sha256(data) != entry["sha256"]):
                raise ValueError("archive payload size/hash differs from its manifest")
            if total > MAX_TOTAL_BYTES:
                raise ValueError("archive exceeds total uncompressed size limit")
            target = destination.joinpath(*PurePosixPath(member).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    package_parser = commands.add_parser("package")
    package_parser.add_argument("first_run", type=Path)
    package_parser.add_argument("archive", type=Path)
    package_parser.add_argument("--repeat-run", type=Path)
    extract_parser = commands.add_parser("extract")
    extract_parser.add_argument("archive", type=Path)
    extract_parser.add_argument("destination", type=Path)
    extract_parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "package":
            digest = package(args.first_run, args.archive, args.repeat_run)
            print("Synthetic Unity probe archive written: " + str(args.archive.resolve()))
            print("SHA-256: " + digest)
            print("Only report-listed scenes, prefabs, .meta files, and AssetBundles were included.")
        else:
            manifest = extract(args.archive, args.destination, args.sha256)
            print("Synthetic Unity probe archive integrity: PASS")
            print("Editor runs present: " + str(manifest["runCount"]))
            print("Unity execution is NOT verified by archive extraction.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError,
            UnicodeError, RuntimeError, zipfile.BadZipFile) as exc:
        print("Unity probe archive rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
