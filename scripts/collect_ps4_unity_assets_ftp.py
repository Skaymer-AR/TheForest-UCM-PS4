#!/usr/bin/env python3
"""Read-only PS4 FTP collector for six CUSA12398 v1.15 Unity serialized files.

No PRX, hooks, writes to PS4, save modification, key recovery or PKG rebuild.
Anonymous LAN FTP is not encrypted. Use only your own trusted local network.

Default is inventory only; downloading requires explicit --download.
The six pinned SHA-256 hashes are from previously verified retail assets.
Private assets remain LOCAL; never commit them to the repository.
"""
from __future__ import annotations

import argparse
import ftplib
import hashlib
import json
import os
import posixpath
import tempfile
from pathlib import Path

TITLE = "CUSA12398"
MOUNT_ROOT = "/mnt/sandbox/pfsmnt"
EXPECTED = {
    "globalgamemanagers.assets": "2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8",
    "sharedassets0.assets": "f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321",
    "sharedassets1.assets": "d227ee3ac409b21bb956c2457d19b248006c212f58ecd4fb396f34ffc2a6e815",
    "level0": "d2d1b170cb1494ecaba4616b1d46e9467fac007c60fe0ba18fa8924a0e0ee8aa",
    "level1": "cbfff68d57c3cadd304cead6c5486f9eb427c368b443bf4bfedff9d16172e790",
    "level2": "99fce056f65647f62ba52d9957317b4ed876e600f854f12e65a20897d37c396d",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ftp_basename(path: str) -> str:
    return posixpath.basename(path.rstrip("/"))


def inventory(ftp) -> dict[str, list[str]]:
    """Look only under observed CUSA12398 app/patch mounts and their Media dir.

    FTP NLST output varies between servers (basename or full path). Never
    infer an unlisted mount or explore arbitrary directories.
    """
    try:
        roots = ftp.nlst(MOUNT_ROOT)
    except ftplib.all_errors as exc:
        raise ValueError("Cannot list mounted game directories") from exc

    mounts: list[str] = []
    for entry in roots:
        name = ftp_basename(entry)
        if name in {TITLE + "-app0", TITLE + "-patch0"}:
            mounts.append(posixpath.join(MOUNT_ROOT, name))

    if not mounts:
        raise ValueError(
            "No active CUSA12398 app/patch mount in /mnt/sandbox/pfsmnt; "
            "the installed game must be mounted before an inventory can succeed"
        )

    available: dict[str, list[str]] = {name: [] for name in EXPECTED}
    # Patch assets can override base assets, but only matching hashes count.
    for mount in sorted(set(mounts), key=lambda x: (not x.endswith("-patch0"), x)):
        remote_media = posixpath.join(mount, "Media")
        try:
            entries = ftp.nlst(remote_media)
        except ftplib.all_errors:
            continue
        names = {ftp_basename(value) for value in entries}
        for name in EXPECTED:
            if name in names:
                available[name].append(posixpath.join(remote_media, name))
    return available


def retrieve_verified(ftp, remote: str, destination: Path, expected: str) -> dict:
    """Read remote bytes, hash them, and publish a verified file without overwrite.

    The temporary file is deleted on any mismatch or FTP interruption.
    Hard-link publication uses EXCL semantics: an existing local file cannot
    be overwritten even if another process creates it during transfer.
    """
    if destination.exists() or destination.is_symlink():
        actual = sha256_file(destination)
        if actual != expected:
            raise ValueError("Existing local file has unexpected SHA-256: " + destination.name)
        return {"file": destination.name, "status": "verified_existing", "sha256": actual}

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ucm-asset-", dir=str(destination.parent))
    temp = Path(tmp_name)
    size = 0
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as stream:
            def write(data: bytes) -> None:
                nonlocal size
                stream.write(data)
                digest.update(data)
                size += len(data)

            ftp.retrbinary("RETR " + remote, write, blocksize=1 << 18)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError("SHA-256 differs from pinned CUSA12398 v1.15 asset: " +
                             destination.name + " (observed " + actual + ")")
        try:
            os.link(temp, destination)
        except FileExistsError:
            if sha256_file(destination) != expected:
                raise ValueError("Concurrent destination file has wrong SHA-256: " +
                                 destination.name)
            return {"file": destination.name, "status": "verified_existing", "sha256": expected}
        return {"file": destination.name, "status": "downloaded", "bytes": size,
                "sha256": actual, "remote": remote}
    finally:
        temp.unlink(missing_ok=True)


def collect(ftp, destination: Path, download: bool) -> dict:
    sources = inventory(ftp)
    manifest = {"title": TITLE, "download_requested": download, "files": []}
    for name, candidates in sources.items():
        record = {"name": name, "sources": candidates,
                  "expected_sha256": EXPECTED[name]}
        if not download:
            record["status"] = "available" if candidates else "missing"
        elif not candidates:
            record["status"] = "missing"
        else:
            failures = []
            for source in candidates:
                try:
                    result = retrieve_verified(ftp, source, destination / name,
                                               EXPECTED[name])
                except (ValueError,) + ftplib.all_errors as exc:
                    failures.append({"remote": source, "error": str(exc)})
                    continue
                record.update(result)
                break
            else:
                record["status"] = "unverified"
                record["failures"] = failures
        manifest["files"].append(record)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True,
                        help="PS4 LAN IP; do not expose GoldHEN FTP to the internet")
    parser.add_argument("--port", type=int, default=2121)
    parser.add_argument("--output", type=Path, default=Path("private-unity-assets"),
                        help="private LOCAL directory; never push game assets to Git")
    parser.add_argument("--download", action="store_true",
                        help="explicitly download only six pinned assets; default is inventory")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        with ftplib.FTP(timeout=30) as ftp:
            ftp.connect(host=args.host, port=args.port)
            ftp.login()
            result = collect(ftp, args.output, args.download)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.download and any(item["status"] not in
                                 {"downloaded", "verified_existing"}
                                 for item in result["files"]):
            return 2
        return 0
    except (ValueError,) + ftplib.all_errors as exc:
        parser.exit(2, "ps4-unity-assets: %s\n" % exc)


if __name__ == "__main__":
    raise SystemExit(main())
