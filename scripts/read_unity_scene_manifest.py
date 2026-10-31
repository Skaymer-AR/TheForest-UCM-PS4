#!/usr/bin/env python3
"""Read-only Unity 5.x BuildSettings scene manifest analyzer.

Accepts the PRIVATE Unity globalgamemanagers serialized file, validates its
header, and finds a length-prefixed scene-path array. Outputs derived JSON only.
It does not edit any asset, read DS4 bindings, or prove scene callbacks active.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

SCENE_PREFIX = b"Assets/Scenes/"
VERSION_RE = re.compile(rb"^[0-9]+\.[0-9]+\.[0-9]+[abfp][0-9]+$")


def read_header(data: bytes) -> dict[str, object]:
    if len(data) < 64:
        raise ValueError("serialized file is too short")
    metadata_bytes, file_size, fmt, data_offset = struct.unpack_from(">IIII", data)
    if file_size != len(data):
        raise ValueError("serialized file size does not match header")
    if not 9 <= fmt <= 22:
        raise ValueError("unsupported Unity serialized format")
    if metadata_bytes <= 0 or data_offset <= 0 or metadata_bytes > len(data) or data_offset >= len(data):
        raise ValueError("invalid Unity serialized header offsets")
    version = data[20:96].split(b"\0", 1)[0]
    if not VERSION_RE.fullmatch(version):
        raise ValueError("Unity Player version is not recognized")
    return {
        "serialized_format": fmt,
        "player_version": version.decode("ascii"),
        "endianness": data[16],
        "metadata_bytes": metadata_bytes,
        "data_offset": data_offset,
    }


def find_scene_list(data: bytes) -> tuple[int, list[str]]:
    matches: list[tuple[int, list[str]]] = []
    offset = 0
    while True:
        position = data.find(SCENE_PREFIX, offset)
        if position < 0:
            break
        array_offset = position - 8
        if array_offset >= 0:
            count, length = struct.unpack_from("<II", data, array_offset)
            if 2 <= count <= 128 and len(SCENE_PREFIX) <= length <= 256:
                cursor = array_offset + 4
                paths: list[str] = []
                try:
                    for _ in range(count):
                        if cursor + 4 > len(data):
                            raise ValueError("truncated scene path length")
                        size = struct.unpack_from("<I", data, cursor)[0]
                        cursor += 4
                        if not 13 <= size <= 256 or cursor + size > len(data):
                            raise ValueError("invalid scene path size")
                        path = data[cursor:cursor + size].decode("utf-8")
                        if not (path.startswith("Assets/Scenes/") and path.endswith(".unity")):
                            raise ValueError("invalid scene path")
                        paths.append(path)
                        cursor += (size + 3) & ~3
                except (ValueError, UnicodeDecodeError):
                    pass
                else:
                    if len(set(paths)) == count:
                        matches.append((array_offset, paths))
        offset = position + len(SCENE_PREFIX)
    if not matches:
        raise ValueError("no validated BuildSettings scene path array found")
    matches.sort(key=lambda item: len(item[1]), reverse=True)
    if len(matches) > 1 and len(matches[0][1]) == len(matches[1][1]):
        raise ValueError("ambiguous BuildSettings scene path arrays")
    return matches[0]


def analyze(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    report = read_header(data)
    position, scenes = find_scene_list(data)
    report.update({
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "scene_table_file_offset": f"0x{position:X}",
        "scene_count": len(scenes),
        "build_settings_scenes": [
            {"index": index, "path": scene} for index, scene in enumerate(scenes)
        ],
        "limits": "names only; no Rewired action map or active runtime callback proven",
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--globalgamemanagers", type=Path, required=True,
                        help="private extracted Unity Player globalgamemanagers file")
    parser.add_argument("--output", type=Path,
                        help="optional path for derived JSON; no game bytes are copied")
    args = parser.parse_args()
    try:
        output = json.dumps(analyze(args.globalgamemanagers), indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"unity-scene-manifest: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
