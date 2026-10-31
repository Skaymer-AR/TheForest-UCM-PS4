#!/usr/bin/env python3
"""Generate and validate a tiny, wholly synthetic Unity format-17 graph.

The fixture uses the release layouts for Unity 5.6 built-in types.  It contains
one GameObject, Transform and generic MonoBehaviour in a scene file, plus one
MonoScript in a separate dependency file.  No project/game assets are read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_unity_rewired_assets import Asset, monoscript  # noqa: E402

UNITY_VERSION = "5.6.6f2"
TARGET_PLATFORM = 31
SCENE_NAME = "Synthetic Menu Host"
ROUNDTRIP_NAME = "Synthetic Menu Host (AssetsTools.NET rewrite)"
SCENE_FILE = "synthetic_scene.assets"
LIBRARY_FILE = "synthetic_library.assets"
GAMEOBJECT_ID = 100
TRANSFORM_ID = 200
MONOBEHAVIOUR_ID = 300
MONOSCRIPT_ID = 900
MAX_FIXTURE_BYTES = 1 << 20


def _align(buf: bytearray, alignment: int) -> None:
    buf.extend(b"\0" * (-len(buf) % alignment))


def _string(value: str) -> bytes:
    raw = value.encode("utf-8")
    data = struct.pack("<i", len(raw)) + raw
    return data + b"\0" * (-len(data) % 4)


def _ptr(file_id: int, path_id: int) -> bytes:
    return struct.pack("<iq", file_id, path_id)


def _gameobject(name: str, components: list[tuple[int, int]]) -> bytes:
    return (struct.pack("<i", len(components)) +
            b"".join(_ptr(file_id, path_id)
                     for file_id, path_id in components) +
            struct.pack("<I", 0) + _string(name) + struct.pack("<HB", 0, 1))


def _transform(gameobject_id: int) -> bytes:
    # Unity 5.6 release layout: GameObject PPtr, Quaternion, position, scale,
    # child PPtr vector, parent PPtr.  The root has no children or parent.
    return (_ptr(0, gameobject_id) + struct.pack("<4f", 0, 0, 0, 1) +
            struct.pack("<3f", 1.25, -2.5, 3.75) +
            struct.pack("<3f", 1, 1, 1) + struct.pack("<i", 0) +
            _ptr(0, 0))


def _monobehaviour(gameobject_id: int, script_file_id: int,
                   script_path_id: int) -> bytes:
    # Generic Unity MonoBehaviour base only.  There is intentionally no
    # PlayMaker-specific payload or guessed 40-byte Fsm tail here.
    return (_ptr(0, gameobject_id) + b"\x01\0\0\0" +
            _ptr(script_file_id, script_path_id) + _string(""))


def _type_record(class_id: int, script_index: int = 0xFFFF) -> bytes:
    record = struct.pack("<iBH", class_id, 0, script_index)
    if class_id == 114:
        # ScriptID and old type hash are deliberately synthetic, deterministic
        # zero hashes.  They are identifiers in this fixture, not a Unity
        # Editor-generated compatibility hash.
        record += bytes(16)
    return record + bytes(16)


def _asset_bytes(objects: list[tuple[int, int, bytes]], *,
                 external_paths: list[str] | None = None,
                 script_types: list[tuple[int, int]] | None = None) -> tuple[bytes, dict[int, int]]:
    external_paths = external_paths or []
    script_types = script_types or []
    if len(objects) > 16 or len(external_paths) > 16 or len(script_types) > 16:
        raise ValueError("fixture count exceeds the strict test limit")
    types = list(dict.fromkeys(class_id for _, class_id, _ in objects))
    if any(class_id not in (1, 4, 114, 115) for class_id in types):
        raise ValueError("fixture contains an unsupported Unity class ID")
    if len({path_id for path_id, _, _ in objects}) != len(objects):
        raise ValueError("fixture object PathIDs must be unique")

    metadata = bytearray(20)  # serialized-file header placeholder
    metadata += UNITY_VERSION.encode("ascii") + b"\0"
    metadata += struct.pack("<iB", TARGET_PLATFORM, 0)  # no inline TypeTree
    metadata += struct.pack("<i", len(types))
    for class_id in types:
        script_index = 0 if class_id == 114 else 0xFFFF
        metadata += _type_record(class_id, script_index)

    metadata += struct.pack("<i", len(objects))
    object_offsets: dict[int, int] = {}
    object_data = bytearray()
    for path_id, class_id, payload in objects:
        if not payload or len(payload) > MAX_FIXTURE_BYTES:
            raise ValueError("object payload is empty or oversized")
        _align(metadata, 4)
        _align(object_data, 8)
        descriptor = len(metadata)
        object_offsets[path_id] = descriptor
        metadata += struct.pack("<qIIi", path_id, len(object_data),
                                len(payload), types.index(class_id))
        object_data += payload

    metadata += struct.pack("<i", len(script_types))
    for file_id, path_id in script_types:
        metadata += struct.pack("<i", file_id)
        _align(metadata, 4)
        metadata += struct.pack("<q", path_id)

    metadata += struct.pack("<i", len(external_paths))
    for index, path in enumerate(external_paths, start=1):
        if not path or "/" in path or "\\" in path or ".." in path:
            raise ValueError("external fixture path must be a safe basename")
        metadata += b"\0"  # empty virtual asset path
        metadata += bytes.fromhex("00112233445566778899aabbccddeeff")
        metadata += struct.pack("<i", 0)
        metadata += path.encode("utf-8") + b"\0"
    metadata += b"\0"  # empty user information

    data_offset = max(0x1000, (len(metadata) + 15) & ~15)
    file_size = data_offset + len(object_data)
    metadata[:16] = struct.pack(">IIII", len(metadata) - 20, file_size, 17,
                                data_offset)
    result = bytes(metadata).ljust(data_offset, b"\0") + bytes(object_data)
    if len(result) > MAX_FIXTURE_BYTES:
        raise ValueError("fixture exceeds the total size limit")
    return result, object_offsets


def build_fixture(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    library, library_offsets = _asset_bytes([
        (MONOSCRIPT_ID, 115,
         _string("SyntheticHost") + bytes(20) + _string("SyntheticHost") +
         _string("FixtureOnly") + _string("FixtureOnly.dll") + b"\0"),
    ])
    scene, scene_offsets = _asset_bytes([
        (GAMEOBJECT_ID, 1, _gameobject(
            SCENE_NAME, [(0, TRANSFORM_ID), (0, MONOBEHAVIOUR_ID)])),
        (TRANSFORM_ID, 4, _transform(GAMEOBJECT_ID)),
        (MONOBEHAVIOUR_ID, 114,
         _monobehaviour(GAMEOBJECT_ID, 1, MONOSCRIPT_ID)),
    ], external_paths=[LIBRARY_FILE], script_types=[(1, MONOSCRIPT_ID)])
    (output_dir / LIBRARY_FILE).write_bytes(library)
    (output_dir / SCENE_FILE).write_bytes(scene)
    return {
        "format": 17,
        "unity_version": UNITY_VERSION,
        "scene": SCENE_FILE,
        "library": LIBRARY_FILE,
        "object_ids": {
            "gameobject": GAMEOBJECT_ID,
            "transform": TRANSFORM_ID,
            "monobehaviour": MONOBEHAVIOUR_ID,
            "monoscript": MONOSCRIPT_ID,
        },
        "fixture_sha256": {
            SCENE_FILE: hashlib.sha256(scene).hexdigest(),
            LIBRARY_FILE: hashlib.sha256(library).hexdigest(),
        },
        "descriptor_offsets": {
            "scene": scene_offsets,
            "library": library_offsets,
        },
    }


def _read_transform(asset: Asset, path_id: int) -> dict[str, object]:
    data = asset.obj(path_id)
    if len(data) < 68:
        raise ValueError("truncated Transform payload")
    go_file, go_path = struct.unpack_from("<iq", data, 0)
    position = struct.unpack_from("<3f", data, 28)
    scale = struct.unpack_from("<3f", data, 40)
    child_count = struct.unpack_from("<i", data, 52)[0]
    if child_count < 0 or child_count > 16:
        raise ValueError("Transform child count outside fixture limit")
    father_at = 56 + child_count * 12
    if father_at + 12 > len(data):
        raise ValueError("Transform child vector exceeds its object")
    father = struct.unpack_from("<iq", data, father_at)
    return {
        "gameobject": (go_file, go_path),
        "position": position,
        "scale": scale,
        "children": child_count,
        "father": father,
    }


def validate_fixture(scene_path: Path, library_path: Path,
                     *, expected_name: str = SCENE_NAME) -> dict[str, object]:
    scene = Asset(scene_path)
    library = Asset(library_path)
    if scene.version != UNITY_VERSION or library.version != UNITY_VERSION:
        raise ValueError("fixture Unity version mismatch")
    if len(scene.objects) != 3 or len(library.objects) != 1:
        raise ValueError("fixture object count mismatch")
    if [scene.objects[GAMEOBJECT_ID].class_id,
            scene.objects[TRANSFORM_ID].class_id,
            scene.objects[MONOBEHAVIOUR_ID].class_id] != [1, 4, 114]:
        raise ValueError("fixture object class ID mismatch")
    if library.objects[MONOSCRIPT_ID].class_id != 115:
        raise ValueError("fixture dependency does not contain MonoScript")

    go = scene.gameobject(GAMEOBJECT_ID)
    if go["name"] != expected_name or not go["active"]:
        raise ValueError("GameObject name or active flag mismatch")
    expected_components = [(0, TRANSFORM_ID), (0, MONOBEHAVIOUR_ID)]
    if any(file_id != 0 or path_id not in scene.objects
           for file_id, path_id in go["components"]):
        raise ValueError("GameObject contains an unresolved component PPtr")
    if go["components"] != expected_components:
        raise ValueError("GameObject component PPtrs mismatch")

    transform = _read_transform(scene, TRANSFORM_ID)
    if transform["gameobject"] != (0, GAMEOBJECT_ID):
        raise ValueError("Transform GameObject PPtr is unresolved")
    if transform["children"] != 0 or transform["father"] != (0, 0):
        raise ValueError("root Transform hierarchy references are inconsistent")
    if transform["position"] != (1.25, -2.5, 3.75) or transform["scale"] != (1, 1, 1):
        raise ValueError("Transform scalar fields do not match fixture values")

    mb = scene.mono(MONOBEHAVIOUR_ID)
    if (mb["game_file"], mb["game_id"]) != (0, GAMEOBJECT_ID) or not mb["enabled"]:
        raise ValueError("MonoBehaviour base PPtr or enabled field is invalid")
    script_dependency = scene.external(mb["script_file"])
    if script_dependency is None:
        raise ValueError("MonoBehaviour script PPtr has an unresolved dependency index")
    if mb["script_id"] not in library.objects:
        raise ValueError("MonoBehaviour script PPtr has an unresolved external PathID")
    if mb["script_file"] != 1 or mb["script_id"] != MONOSCRIPT_ID:
        raise ValueError("MonoBehaviour script PPtr is invalid")
    if script_dependency != LIBRARY_FILE:
        raise ValueError("MonoBehaviour dependency index is unresolved")
    if scene.external(1) != LIBRARY_FILE:
        raise ValueError("scene external-file table mismatch")
    if monoscript(library.obj(MONOSCRIPT_ID)) != {
        "name": "SyntheticHost", "class_name": "SyntheticHost",
        "namespace": "FixtureOnly", "assembly": "FixtureOnly.dll",
    }:
        raise ValueError("external MonoScript fields mismatch")

    return {
        "format": 17,
        "unity_version": UNITY_VERSION,
        "gameobject": {"path_id": GAMEOBJECT_ID, "name": go["name"],
                       "components": go["components"]},
        "transform": {"path_id": TRANSFORM_ID,
                      "gameobject": transform["gameobject"],
                      "position": transform["position"],
                      "scale": transform["scale"],
                      "children": transform["children"],
                      "father": transform["father"]},
        "monobehaviour": {"path_id": MONOBEHAVIOUR_ID,
                          "gameobject": (mb["game_file"], mb["game_id"]),
                          "enabled": mb["enabled"],
                          "script": (mb["script_file"], mb["script_id"]),
                          "script_name": "SyntheticHost"},
        "external": LIBRARY_FILE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("output_dir", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("scene", type=Path)
    verify.add_argument("library", type=Path)
    verify.add_argument("--expected-name", default=SCENE_NAME)
    args = parser.parse_args()
    if args.command == "build":
        print(json.dumps(build_fixture(args.output_dir), sort_keys=True))
    else:
        print(json.dumps(validate_fixture(args.scene, args.library,
                                          expected_name=args.expected_name),
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
