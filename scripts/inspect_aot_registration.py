#!/usr/bin/env python3
"""Read-only v23 AOT registration consistency and proposed-host presence check.

Accepts a private ELF and metadata, explicit link-time initializer VA and
method-table file offset. Recognizes one bounded x64 generated initializer
shape; never invokes the registrar, creates objects, patches, or uploads.
Presence of registered methods does not prove Unity will create/call a host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from analyze_ps4_il2cpp_pipeline import parse_metadata_v23, TYPE_RECORD
from unwrap_plain_self import checked_range, ELF_HEADER, PROGRAM_HEADER

CODE_FIELDS = ("methods", "reverse_pinvoke", "generic_methods", "invokers",
               "attributes", "unresolved_virtual_calls", "interop")
METADATA_FIELDS = ("generic_classes", "generic_instances", "generic_method_table",
                   "types", "method_specs", "field_offsets", "type_definition_sizes",
                   "metadata_usages")
HOST_METHODS = (".ctor", "Bootstrap", "Awake", "Update", "OnGUI", "OnDestroy")


class NativeImage:
    """Map link-time virtual addresses, including PS4's file-backed SCE_RELRO."""
    def __init__(self, data: bytes):
        if len(data) < 64:
            raise ValueError("truncated ELF")
        self.data = data
        h = ELF_HEADER.unpack_from(data)
        if h[0][:7] != b"\x7fELF\x02\x01\x01" or h[2] != 62 or h[9] != 56:
            raise ValueError("expected little-endian x86-64 ELF64")
        checked_range(h[5], h[10]*56, len(data), "program header table")
        self.segments = []
        for i in range(h[10]):
            p = PROGRAM_HEADER.unpack_from(data, h[5]+i*56)
            if p[0] in (1, 0x61000010) and p[5]:
                checked_range(p[2], p[5], len(data), "memory segment")
                self.segments.append((p[2], p[3], p[5], p[1]))
        if not self.segments:
            raise ValueError("no file-backed memory segments")

    def file_offset(self, va: int, size: int) -> int:
        candidates = {off+va-base for off, base, length, _ in self.segments
                      if base <= va and size <= length and va-base <= length-size}
        if len(candidates) != 1:
            raise ValueError(f"link-time address 0x{va:X} is not uniquely file-backed")
        return candidates.pop()

    def virtual_address(self, offset: int, size: int) -> int:
        candidates = {base+offset-off for off, base, length, _ in self.segments
                      if off <= offset and size <= length and offset-off <= length-size}
        if len(candidates) != 1:
            raise ValueError("method table file range is not uniquely memory-backed")
        return candidates.pop()

    def read(self, va: int, size: int) -> bytes:
        offset = self.file_offset(va, size)
        return self.data[offset:offset+size]

    def executable(self, va: int) -> bool:
        return any(flags & 1 and base <= va < base+length
                   for _, base, length, flags in self.segments)


def read_pairs(image: NativeImage, va: int, names: tuple[str, ...]) -> dict:
    values = struct.unpack("<"+"Q"*(2*len(names)), image.read(va, 16*len(names)))
    result = {}
    for i, name in enumerate(names):
        count, pointer = values[2*i:2*i+2]
        if count > 2_000_000:
            raise ValueError(f"{name}: implausible registration count")
        if count:
            image.read(pointer, 1)  # existence only; element sizes differ by array
        result[name] = {"count": count, "pointer": pointer}
    return result


def inspect_registration(data: bytes, metadata_data: bytes, initializer_va: int,
                         method_table_offset: int,
                         host_type: str = "TheForest.UCM.UltimateMenuHost",
                         required_methods: tuple[str, ...] = HOST_METHODS) -> dict:
    image = NativeImage(data)
    metadata = parse_metadata_v23(metadata_data)
    if not image.executable(initializer_va):
        raise ValueError("registration initializer is not executable file-backed code")
    code = image.read(initializer_va, 26)
    if code[:3] != b"\x48\x8d\x3d" or code[7:10] != b"\x48\x8d\x35" or \
            code[14:17] != b"\x48\x8d\x15" or code[21] != 0xE9:
        raise ValueError("initializer does not match the supported three-LEA/tail-jump shape")
    targets = [initializer_va+off+7+struct.unpack_from("<i", code, off+3)[0]
               for off in (0, 7, 14)]
    registrar = initializer_va+26+struct.unpack_from("<i", code, 22)[0]
    if not image.executable(registrar):
        raise ValueError("registration tail target is not executable file-backed code")
    code_reg = read_pairs(image, targets[0], CODE_FIELDS)
    meta_reg = read_pairs(image, targets[1], METADATA_FIELDS)
    image.read(targets[2], 1)
    method_count = code_reg["methods"]["count"]
    if method_count == 0:
        raise ValueError("empty native method table")
    table_va = image.virtual_address(method_table_offset, method_count*8)
    if table_va != code_reg["methods"]["pointer"]:
        raise ValueError("code registration does not reference the supplied method table")
    pointers = struct.unpack("<"+"Q"*method_count, image.read(table_va, method_count*8))
    positive_indices = [m.method_index for m in metadata.methods if m.method_index >= 0]
    if positive_indices and max(positive_indices) >= method_count:
        raise ValueError("metadata methodIndex exceeds the native method table")
    for name in ("field_offsets", "type_definition_sizes"):
        if meta_reg[name]["count"] != len(metadata.types):
            raise ValueError(f"{name} count does not match TypeDefinitions")
        image.read(meta_reg[name]["pointer"], len(metadata.types)*8)
    types_count = meta_reg["types"]["count"]
    image.read(meta_reg["types"]["pointer"], types_count*8)
    offset, size = metadata.sections["type_definitions"]
    for at in range(offset, offset+size, TYPE_RECORD.size):
        row = TYPE_RECORD.unpack_from(metadata_data, at)
        for native_index in row[3:8]:
            if native_index < -1 or native_index >= types_count:
                raise ValueError("TypeDefinition native TypeIndex exceeds registered Il2CppTypes")
    owner = [t for t in metadata.types if t.full_name == host_type]
    host_rows = []
    if len(owner) == 1:
        for name in required_methods:
            methods = [m for m in metadata.methods_named(owner[0], name) if m.parameter_count == 0]
            valid = len(methods) == 1 and 0 <= methods[0].method_index < method_count
            pointer = pointers[methods[0].method_index] if valid else None
            host_rows.append({"method": name, "unique_zero_parameter_definition": len(methods) == 1,
                              "executable_native_body": pointer is not None and image.executable(pointer),
                              "link_va": pointer})
    host_passed = len(owner) == 1 and bool(required_methods) and \
        all(row["executable_native_body"] for row in host_rows)
    invalid = sum(not image.executable(pointers[index]) for index in positive_indices)
    return {"module_sha256": hashlib.sha256(data).hexdigest(),
            "metadata_sha256": metadata.sha256, "metadata_version": 23,
            "type_definition_count": len(metadata.types), "method_definition_count": len(metadata.methods),
            "initializer_link_va": initializer_va, "registrar_target_link_va": registrar,
            "code_registration_link_va": targets[0], "metadata_registration_link_va": targets[1],
            "code_generation_options_link_va": targets[2], "code_registration": code_reg,
            "metadata_registration": meta_reg,
            "referenced_native_method_indices": len(positive_indices),
            "referenced_methods_without_executable_body": invalid,
            "host_type": host_type, "host_type_definition_count": len(owner),
            "host_methods": host_rows, "host_native_presence_passed": host_passed,
            "runtime_component_creation_or_invocation_checked": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--initializer-va", type=lambda s:int(s, 0), required=True,
                        help="ELF link-time VA; never an ASLR/runtime address")
    parser.add_argument("--method-table-file-offset", type=lambda s:int(s, 0), required=True)
    parser.add_argument("--host-type", default="TheForest.UCM.UltimateMenuHost")
    parser.add_argument("--require-host", action="store_true", help="exit 3 if proposed host is absent/incomplete")
    args = parser.parse_args(argv)
    try:
        report = inspect_registration(args.module.read_bytes(), args.metadata.read_bytes(),
                                      args.initializer_va, args.method_table_file_offset, args.host_type)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3 if args.require_host and not report["host_native_presence_passed"] else 0
    except (OSError, ValueError, struct.error) as exc:
        print(f"aot-registration: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
