#!/usr/bin/env python3
"""Read-only discovery and SHA-256 verification of original Unity assets in ZIPs.

Without --extract-dir, reads ZIP members in bounded chunks and produces a
metadata-only JSON report. No game asset bytes are printed or committed.
With --extract-dir, only files with the six pinned hashes are published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import stat
import tempfile
import zipfile
from pathlib import Path

from collect_ps4_unity_assets_ftp import EXPECTED

MAX_ENTRY_SIZE = 1 << 30
MAX_ARCHIVE_ENTRIES = 100000
CHUNK_SIZE = 1 << 20


def recognized_member(info: zipfile.ZipInfo) -> str | None:
    name = info.filename.replace("\\", "/")
    segments = name.split("/")
    if (name.startswith("/") or any(s in ("", ".", "..") for s in segments)
            or info.is_dir() or (info.external_attr >> 16) & 0o170000 == stat.S_IFLNK):
        return None
    if segments[-1] not in EXPECTED:
        return None
    if len(segments) == 1 or "Media" in segments[:-1]:
        return segments[-1]
    return None


def audit_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo,
                 expected: str, output: Path | None, name: str) -> dict:
    item = {"name": name, "member": info.filename,
            "uncompressed_bytes": info.file_size}
    if info.flag_bits & 1:
        item["status"] = "encrypted"
        return item
    if info.file_size > MAX_ENTRY_SIZE:
        item["status"] = "too_large"
        return item

    digest = hashlib.sha256()
    observed = 0
    temporary = None
    stream_out = None
    try:
        if output is not None:
            output.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".ucm-zip-", dir=str(output))
            temporary = Path(temp_name)
            stream_out = os.fdopen(fd, "wb")

        with archive.open(info, "r") as inp:
            while True:
                chunk = inp.read(CHUNK_SIZE)
                if not chunk:
                    break
                observed += len(chunk)
                if observed > MAX_ENTRY_SIZE or observed > info.file_size:
                    raise ValueError("uncompressed stream exceeds declared bounds")
                digest.update(chunk)
                if stream_out is not None:
                    stream_out.write(chunk)
        if observed != info.file_size:
            raise ValueError("uncompressed size differs from ZIP index")
        sha = digest.hexdigest()
        item["sha256"] = sha
        if sha != expected:
            item["status"] = "hash_mismatch"
            return item
        item["status"] = "verified"
        if stream_out is not None:
            stream_out.close()
            stream_out = None
            target = output / name
            try:
                os.link(temporary, target)
            except FileExistsError:
                if not target.is_file() or hash_file(target) != expected:
                    raise ValueError("local destination exists with a different hash")
                item["status"] = "verified_existing"
            else:
                item["status"] = "extracted_verified"
        return item
    except (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile) as exc:
        item["status"] = "read_error"
        item["error"] = str(exc)
        return item
    finally:
        if stream_out is not None:
            stream_out.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(part)
    return digest.hexdigest()


def inspect_zip(path: Path, output: Path | None = None) -> dict:
    record: dict = {"archive": path.name, "candidates": [], "status": "scanned"}
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            record["entries"] = len(infos)
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("ZIP has too many entries")
            for info in infos:
                name = recognized_member(info)
                if name is None:
                    continue
                record["candidates"].append(
                    audit_member(z, info, EXPECTED[name], output, name))
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        record["status"] = "archive_error"
        record["error"] = str(exc)
    return record


def inspect_all(paths: list[Path], output: Path | None = None) -> dict:
    reports = [inspect_zip(path, output) for path in paths]
    verified = {row["name"] for rep in reports for row in rep["candidates"]
                if row["status"] in ("verified", "extracted_verified",
                                      "verified_existing")}
    return {"archives": reports, "expected_files": list(EXPECTED),
            "verified_files": sorted(verified),
            "missing_files": sorted(set(EXPECTED) - verified),
            "all_six_verified": len(verified) == len(EXPECTED)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_files", nargs="+", type=Path)
    parser.add_argument("--extract-dir", type=Path,
                        help="private local destination; disabled by default")
    args = parser.parse_args(argv)
    report = inspect_all(args.zip_files, args.extract_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["all_six_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
