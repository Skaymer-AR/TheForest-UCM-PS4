#!/usr/bin/env python3
"""Read-only Unity 5.6.6f2 OnGUI host inventory for a specific PS4 ELF.

Resolves serialized MonoBehaviour->MonoScript->IL2CPP method pointers, then
walks the Transform parent chain to detect objects inactive in their hierarchy.
No patching, PRX building, or claim of a runtime callback is made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from inspect_unity_rewired_assets import Asset, monoscript

EXPECTED_ELF_SHA256 = "0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969"
EXPECTED_METADATA_SHA256 = "238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3"
METHOD_TABLE_OFFSET = 0x031738C0
TYPE_DEF_SIZE = 104
METHOD_DEF_SIZE = 56
NAMES = (
    "string_literals", "string_literal_data", "strings", "events", "properties",
    "methods", "parameter_defaults", "field_defaults", "default_value_data",
    "marshaled_sizes", "parameters", "fields", "generic_parameters",
    "generic_constraints", "generic_containers", "nested_types", "interfaces",
    "vtables", "interface_offsets", "types", "rgctx", "images", "assemblies",
    "metadata_usage_lists", "metadata_usage_pairs", "field_refs",
    "referenced_assemblies", "attributes", "attribute_types",
    "unresolved_virtual_parameter_types",
    "unresolved_virtual_parameter_ranges", "windows_runtime_types",
)


def read_ongui_methods(raw: bytes) -> dict[str, tuple[int, int]]:
    """Fully bounds-check metadata before resolving OnGUI method indices."""
    if len(raw) < 8 + 8 * len(NAMES):
        raise ValueError("metadata header truncated")
    if struct.unpack_from("<II", raw) != (0xFAB11BAF, 23):
        raise ValueError("expected IL2CPP metadata version 23")
    sections = {}
    for i, name in enumerate(NAMES):
        offset, size = struct.unpack_from("<II", raw, 8 + 8 * i)
        if offset < 8 + 8 * len(NAMES) or offset + size > len(raw):
            raise ValueError("invalid metadata section bounds: " + name)
        sections[name] = (offset, size)

    type_off, type_size = sections["types"]
    method_off, method_size = sections["methods"]
    string_off, string_size = sections["strings"]
    if type_size % TYPE_DEF_SIZE or method_size % METHOD_DEF_SIZE:
        raise ValueError("inconsistent metadata entry size")
    if string_size == 0:
        raise ValueError("metadata strings absent")

    def name_at(index: int) -> str:
        if index >= string_size:
            raise ValueError("string index out of bounds")
        pos = string_off + index
        end = raw.find(b"\0", pos, string_off + string_size)
        if end < 0:
            raise ValueError("unterminated metadata name")
        return raw[pos:end].decode("utf-8")

    result: dict[str, tuple[int, int]] = {}
    total_methods = method_size // METHOD_DEF_SIZE
    for type_idx in range(type_size // TYPE_DEF_SIZE):
        at = type_off + TYPE_DEF_SIZE * type_idx
        name_idx, namespace_idx = struct.unpack_from("<II", raw, at)
        method_start = struct.unpack_from("<i", raw, at + 52)[0]
        method_count = struct.unpack_from("<H", raw, at + 80)[0]
        if method_count == 0:
            continue
        if method_start < 0 or method_start + method_count > total_methods:
            raise ValueError("method range outside table")
        full = name_at(name_idx)
        namespace = name_at(namespace_idx)
        if namespace:
            full = namespace + "." + full
        for method_idx in range(method_start, method_start + method_count):
            pos = method_off + METHOD_DEF_SIZE * method_idx
            method_name_idx = struct.unpack_from("<I", raw, pos)[0]
            # Reading only the name avoids guessing method semantics.
            if name_at(method_name_idx) != "OnGUI":
                continue
            native_idx = struct.unpack_from("<i", raw, pos + 24)[0]
            if native_idx < 0:
                continue
            if full in result:
                raise ValueError("ambiguous OnGUI method definition: " + full)
            result[full] = (method_idx, native_idx)
    return result


def read_exec_mapping(elf: bytes, va: int, size: int) -> int:
    """Map a link-time VA only if fully inside an executable PT_LOAD."""
    if (len(elf) < 64 or elf[:4] != b"\x7fELF" or elf[4:6] != b"\x02\x01"):
        raise ValueError("not an x86-64 little-endian ELF")
    phoff = struct.unpack_from("<Q", elf, 32)[0]
    ent_size, ent_count = struct.unpack_from("<HH", elf, 54)
    if ent_size != 56 or ent_count < 1 or phoff + ent_size * ent_count > len(elf):
        raise ValueError("invalid ELF program header table")
    for i in range(ent_count):
        at = phoff + i * ent_size
        kind, flags = struct.unpack_from("<II", elf, at)
        file_off, vaddr, _, filesz, _ = struct.unpack_from("<QQQQQ", elf, at + 8)
        if kind != 1 or not flags & 1:
            continue
        if va >= vaddr and va + size <= vaddr + filesz:
            offset = file_off + va - vaddr
            if offset + size > len(elf):
                raise ValueError("ELF segment extends beyond input")
            return offset
    raise ValueError("native method is not in an executable segment")


def native_method(elf: bytes, method_index: int) -> dict[str, object]:
    if method_index < 0 or METHOD_TABLE_OFFSET + 8 * (method_index + 1) > len(elf):
        raise ValueError("method index beyond native pointer table")
    va = struct.unpack_from("<Q", elf, METHOD_TABLE_OFFSET + 8 * method_index)[0]
    offset = read_exec_mapping(elf, va, 32)
    prefix = elf[offset:offset + 32]
    return {
        "method_index": method_index,
        "elf_link_va": "0x%08X" % va,
        "prefix32_sha256": hashlib.sha256(prefix).hexdigest(),
        "elf_file_offset": "0x%08X" % offset,
    }


def transform_parent(scene: Asset, transform_id: int) -> tuple[int, int] | None:
    obj = scene.objects.get(transform_id)
    if obj is None or obj.class_id != 4:
        raise ValueError("missing plain Transform; RectTransform not assumed")
    data = scene.obj(transform_id)
    if len(data) < 68:
        raise ValueError("short Transform")
    children = struct.unpack_from("<i", data, 52)[0]
    if children < 0 or children > 100000 or 56 + 12 * children + 12 > len(data):
        raise ValueError("invalid Transform child vector")
    fid, pid = struct.unpack_from("<iq", data, 56 + children * 12)
    return (fid, pid) if fid or pid else None


def ancestry(scene: Asset, game_id: int) -> dict[str, object]:
    """No 'active' verdict when the hierarchy cannot be resolved."""
    nodes: list[dict[str, object]] = []
    visited: set[int] = set()
    current = game_id
    while True:
        if current in visited:
            raise ValueError("Transform hierarchy cycle")
        visited.add(current)
        obj = scene.objects.get(current)
        if obj is None or obj.class_id != 1:
            raise ValueError("unresolved GameObject in hierarchy")
        go = scene.gameobject(current)
        nodes.append({"gameobject_id": current, "name": go["name"], "active": go["active"]})
        transforms = [
            pid for file_id, pid in go["components"]
            if file_id == 0 and pid in scene.objects and scene.objects[pid].class_id == 4
        ]
        if len(transforms) != 1:
            raise ValueError("expected one plain Transform per inspected GameObject")
        parent = transform_parent(scene, transforms[0])
        if parent is None:
            break
        if parent[0] != 0:
            raise ValueError("parent Transform external to scene")
        parent_transform = scene.objects.get(parent[1])
        if parent_transform is None or parent_transform.class_id != 4:
            raise ValueError("parent Transform reference unresolved")
        parent_data = scene.obj(parent[1])
        if len(parent_data) < 12:
            raise ValueError("parent Transform lacks GameObject reference")
        file_id, parent_game_id = struct.unpack_from("<iq", parent_data)
        if file_id != 0 or parent_game_id == 0:
            raise ValueError("parent GameObject reference invalid")
        current = parent_game_id
    return {"chain": nodes, "active_in_serialized_hierarchy": all(n["active"] for n in nodes)}


def inspect(root: Path, module: Path, metadata: Path) -> dict[str, object]:
    elf = module.read_bytes()
    raw_meta = metadata.read_bytes()
    if hashlib.sha256(elf).hexdigest() != EXPECTED_ELF_SHA256:
        raise ValueError("IL2CPP ELF SHA mismatch; method table offsets cannot be reused")
    if hashlib.sha256(raw_meta).hexdigest() != EXPECTED_METADATA_SHA256:
        raise ValueError("IL2CPP metadata SHA mismatch; method definitions cannot be reused")
    methods = read_ongui_methods(raw_meta)
    scripts_asset = Asset(root / "globalgamemanagers.assets")
    scripts = {pid: monoscript(scripts_asset.obj(pid)) for pid in scripts_asset.ids(115)}
    scenes: dict[str, object] = {}
    for filename in ("level1", "level2"):
        scene = Asset(root / filename)
        found = []
        for component_id in scene.ids(114):
            mb = scene.mono(component_id)
            if scene.external(mb["script_file"]) != "globalgamemanagers.assets":
                continue
            script = scripts.get(mb["script_id"])
            if not script:
                continue
            full_name = script["namespace"] + "." + script["class_name"] if script["namespace"] else script["class_name"]
            native = methods.get(full_name)
            if native is None:
                continue
            entry = {
                "script": full_name, "component_id": component_id,
                "component_enabled": mb["enabled"],
                "method_definition_index": native[0],
                "native": native_method(elf, native[1]),
            }
            try:
                if mb["game_file"] != 0:
                    raise ValueError("external GameObject reference")
                entry["hierarchy"] = ancestry(scene, mb["game_id"])
            except (ValueError, KeyError) as exc:
                entry["hierarchy"] = {"unknown": str(exc)}
            found.append(entry)
        scenes[filename] = found
    return {
        "target": "CUSA12398 v1.15",
        "unity_player": "5.6.6f2",
        "module_sha256": EXPECTED_ELF_SHA256,
        "metadata_sha256": EXPECTED_METADATA_SHA256,
        "scenes": scenes,
        "proof_limitations": [
            "active serialized hierarchy is not runtime callback confirmation",
            "ELF link VA is not a PS4 ASLR address",
            "the script cannot install or validate a native hook",
            "a safe, reversible invocation and teardown mechanism remains unproven",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True, help="private historical IL2CPP ELF")
    parser.add_argument("--metadata", type=Path, required=True, help="private original global-metadata.dat")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = json.dumps(inspect(args.assets_root, args.module, args.metadata),
                          indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(data, encoding="utf-8")
        else:
            print(data, end="")
        return 0
    except (ValueError, OSError, struct.error, UnicodeError) as exc:
        parser.exit(2, f"ongui-scene-hosts: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
