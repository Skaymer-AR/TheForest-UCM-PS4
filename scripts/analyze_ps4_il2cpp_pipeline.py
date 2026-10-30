#!/usr/bin/env python3
"""Single-command, read-only PS4 IL2CPP v23 lifecycle/input analysis.

The command joins exact metadata method indices, the module method-pointer
table, optional local dump.cs field declarations, and bounded native
disassembly. It never scans/disassembles the whole ELF, executes game code,
or uploads/copies private inputs. Supplied instruction bytes and RIP-relative
comments are checked against the pinned module. Native type-reference slots
stay unresolved until the exact native registration mapping is independently
recovered and validated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_disassembly_report import Window, parse_windows  # noqa: E402
from analyze_il2cpp_lifecycle import analyze_window, render_report as render_cfg  # noqa: E402
from analyze_ps4_il2cpp_candidates import Elf64Image  # noqa: E402
from resolve_il2cpp_references import (  # noqa: E402
    DEFAULT_EVIDENCE,
    DEFAULT_PRIOR,
    DEFAULT_RESOLVED,
    load_symbols,
    resolve_references,
)
from verify_il2cpp_static_fields import (  # noqa: E402
    parse_dump_fields,
    verify_expected_fields,
)

METADATA_MAGIC = 0xFAB11BAF
METADATA_VERSION = 23
METADATA_SHA256 = "238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3"
MODULE_SHA256 = "0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969"
METHOD_POINTER_TABLE_OFFSET = 0x31738C0
ONDESTROY_EXPECTATIONS_PATH = ROOT / "docs/PS4_ONDESTROY_EXPECTATIONS.json"
METHOD_RECORD = struct.Struct("<I10iI4H")
TYPE_RECORD = struct.Struct("<II9iI8i8HII")
FIELD_RECORD = struct.Struct("<IiiI")
HEADER_PAIR_INDEX = {
    "string_literals": 0,
    "string_literal_data": 1,
    "strings": 2,
    "events": 3,
    "properties": 4,
    "methods": 5,
    "parameter_default_values": 6,
    "field_default_values": 7,
    "default_value_data": 8,
    "field_marshaled_sizes": 9,
    "parameters": 10,
    "fields": 11,
    "generic_parameters": 12,
    "generic_constraints": 13,
    "generic_containers": 14,
    "nested_types": 15,
    "interfaces": 16,
    "vtable_methods": 17,
    "interface_offsets": 18,
    "type_definitions": 19,
    "rgctx_entries": 20,
    "images": 21,
    "assemblies": 22,
    "metadata_usage_lists": 23,
    "metadata_usage_pairs": 24,
    "field_refs": 25,
    "referenced_assemblies": 26,
    "attribute_info": 27,
    "attribute_types": 28,
    "unresolved_virtual_types": 29,
    "unresolved_virtual_ranges": 30,
    "windows_runtime_type_names": 31,
}
HEADER_SIZE_V23 = 8 + 32 * 8
TYPE_ATTRIBUTE_INTERFACE = 0x20


@dataclass(frozen=True)
class TypeDefinition:
    index: int
    name: str
    namespace: str
    declaring_type: int
    flags: int
    field_start: int
    field_count: int
    method_start: int
    method_count: int

    @property
    def full_name(self) -> str:
        if self.namespace:
            return f"{self.namespace}.{self.name}"
        return self.name

    @property
    def is_interface(self) -> bool:
        return bool(self.flags & TYPE_ATTRIBUTE_INTERFACE)


@dataclass(frozen=True)
class MethodDefinition:
    definition_index: int
    name: str
    declaring_type: int
    method_index: int
    token: int
    parameter_count: int


@dataclass(frozen=True)
class FieldDefinition:
    index: int
    name: str
    declaring_type: int


@dataclass(frozen=True)
class MetadataV23:
    sha256: str
    sections: dict[str, tuple[int, int]]
    types: tuple[TypeDefinition, ...]
    methods: tuple[MethodDefinition, ...]
    fields: tuple[FieldDefinition, ...]
    strings: bytes

    def read_string(self, index: int) -> str:
        if index < 0 or index >= len(self.strings):
            raise ValueError(f"metadata string index 0x{index:X} is out of bounds")
        end = self.strings.find(b"\0", index)
        if end < 0:
            raise ValueError(f"metadata string at 0x{index:X} has no terminator")
        return self.strings[index:end].decode("utf-8", errors="replace")

    def find_types(self, selector: str) -> list[TypeDefinition]:
        return [item for item in self.types
                if item.full_name == selector or item.full_name.endswith("." + selector)
                or item.name == selector]

    def owned_fields(self, type_def: TypeDefinition) -> list[FieldDefinition]:
        return [field for field in self.fields
                if field.declaring_type == type_def.index]

    def methods_named(self, type_def: TypeDefinition, method_name: str) -> list[MethodDefinition]:
        return [method for method in self.methods
                if method.declaring_type == type_def.index and method.name == method_name]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_section(data: bytes, name: str) -> tuple[int, int]:
    pair_index = HEADER_PAIR_INDEX[name]
    offset, size = struct.unpack_from("<Ii", data, 8 + pair_index * 8)
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"metadata section {name} is outside the file")
    return offset, size


def _section_rows(data: bytes, section: tuple[int, int], record: struct.Struct,
                  name: str) -> list[tuple]:
    offset, size = section
    if size % record.size:
        raise ValueError(f"metadata section {name} size {size} is not a multiple of {record.size}")
    return [record.unpack_from(data, offset + index)
            for index in range(0, size, record.size)]


def parse_metadata_v23(data: bytes) -> MetadataV23:
    """Parse only the documented v23 string/type/method/field tables."""
    if len(data) < HEADER_SIZE_V23:
        raise ValueError(f"metadata v23 header is truncated (need {HEADER_SIZE_V23} bytes)")
    magic, version = struct.unpack_from("<Ii", data, 0)
    if magic != METADATA_MAGIC:
        raise ValueError(f"metadata magic mismatch: 0x{magic:08X}")
    if version != METADATA_VERSION:
        raise ValueError(f"expected IL2CPP metadata v23, received v{version}")
    sections = {name: _read_section(data, name) for name in
                ("strings", "methods", "fields", "type_definitions")}
    string_offset, string_size = sections["strings"]
    strings = data[string_offset:string_offset + string_size]

    raw_types = _section_rows(data, sections["type_definitions"], TYPE_RECORD,
                              "type_definitions")
    types: list[TypeDefinition] = []
    for index, row in enumerate(raw_types):
        # v23 layout: name, namespace, nine legacy indices, flags, eight
        # ranges/starts, eight ushort counts, bitfield, token.
        types.append(TypeDefinition(
            index=index,
            name=_read_metadata_string(strings, row[0]),
            namespace=_read_metadata_string(strings, row[1]),
            declaring_type=row[5],
            flags=row[11],
            field_start=row[12],
            method_start=row[13],
            method_count=row[20],
            field_count=row[22],
        ))

    raw_methods = _section_rows(data, sections["methods"], METHOD_RECORD, "methods")
    methods: list[MethodDefinition] = []
    for index, row in enumerate(raw_methods):
        methods.append(MethodDefinition(index, _read_metadata_string(strings, row[0]),
                                        row[1], row[6], row[11], row[15]))

    raw_fields = _section_rows(data, sections["fields"], FIELD_RECORD, "fields")
    fields = [FieldDefinition(index, _read_metadata_string(strings, row[0]), -1)
              for index, row in enumerate(raw_fields)]
    field_owners: list[FieldDefinition] = list(fields)
    for type_def in types:
        if type_def.field_start < 0 or type_def.field_count < 0:
            raise ValueError(f"type {type_def.full_name} has invalid field range")
        end = type_def.field_start + type_def.field_count
        if end > len(field_owners):
            raise ValueError(f"type {type_def.full_name} field range exceeds metadata table")
        for index in range(type_def.field_start, end):
            previous = field_owners[index]
            if previous.declaring_type != -1:
                raise ValueError(f"field index {index} belongs to multiple metadata types")
            field_owners[index] = FieldDefinition(previous.index, previous.name, type_def.index)

        if type_def.method_start < 0 or type_def.method_count < 0:
            raise ValueError(f"type {type_def.full_name} has invalid method range")
        if type_def.method_start + type_def.method_count > len(methods):
            raise ValueError(f"type {type_def.full_name} method range exceeds metadata table")

    for type_def in types:
        if type_def.declaring_type >= len(types):
            raise ValueError(f"type {type_def.full_name} has invalid declaring type")
        if type_def.declaring_type < -1:
            raise ValueError(f"type {type_def.full_name} has invalid declaring type")
    for method in methods:
        if method.declaring_type < 0 or method.declaring_type >= len(types):
            raise ValueError(f"method {method.name} has invalid declaring type")
        owner = types[method.declaring_type]
        if not owner.method_start <= method.definition_index < owner.method_start + owner.method_count:
            raise ValueError(f"method {method.name} is outside its declaring type range")
    return MetadataV23(_sha256(data), sections, tuple(types), tuple(methods),
                       tuple(field_owners), strings)


def _read_metadata_string(strings: bytes, index: int) -> str:
    if index < 0 or index >= len(strings):
        raise ValueError(f"metadata string index 0x{index:X} is out of bounds")
    end = strings.find(b"\0", index)
    if end < 0:
        raise ValueError(f"metadata string at 0x{index:X} has no terminator")
    return strings[index:end].decode("utf-8", errors="replace")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_method_rva(module: Path, image: Elf64Image, method: MethodDefinition,
                       table_offset: int = METHOD_POINTER_TABLE_OFFSET) -> tuple[int | None, bool]:
    """Read one v23 methodIndex entry and require executable file-backed code."""
    if method.method_index < 0:
        return None, False
    pointer_offset = table_offset + method.method_index * 8
    with module.open("rb") as stream:
        stream.seek(0, 2)
        file_size = stream.tell()
        if pointer_offset < 0 or pointer_offset + 8 > file_size:
            raise ValueError(f"method pointer index {method.method_index} is beyond module file")
        stream.seek(pointer_offset)
        pointer = struct.unpack("<Q", stream.read(8))[0]
    rva = int(pointer)
    return rva, image.file_offset(rva) is not None and image.is_executable(rva)


def inspect_static_slot(module: Path, image: Elf64Image,
                        slot_rva: int) -> dict[str, object]:
    """Report file bytes at a native data slot without calling them runtime state."""
    offset = image.file_offset(slot_rva)
    if offset is None:
        return {"slot_rva": slot_rva, "file_offset": None,
                "value": None, "status": "not file-backed in this ELF"}
    with module.open("rb") as stream:
        stream.seek(offset)
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"native type-reference slot 0x{slot_rva:X} is truncated")
    return {"slot_rva": slot_rva, "file_offset": offset,
            "value": struct.unpack("<Q", raw)[0],
            "status": "file image bytes only; runtime value not observed"}


def verify_window_bytes(image: Elf64Image, windows: list[Window]) -> int:
    """Require each supplied instruction byte sequence to match the pinned ELF."""
    verified = 0
    rip_pattern = re.compile(r"\[rip\s*([+-])\s*(0x[0-9a-f]+|[0-9a-f]+)?\s*\]", re.I)
    comment_pattern = re.compile(r"#\s*(?:0x)?([0-9a-f]+)\b", re.I)
    for window in windows:
        for instruction in window.instructions:
            if not instruction.raw_bytes:
                raise ValueError(f"window at 0x{window.rva:X} contains an instruction without bytes")
            if not image.is_executable(instruction.address):
                raise ValueError(f"instruction at RVA 0x{instruction.address:X} is not in an executable PT_LOAD")
            actual = image.read_rva(instruction.address, len(instruction.raw_bytes))
            if actual != instruction.raw_bytes:
                raise ValueError(f"instruction bytes mismatch at RVA 0x{instruction.address:X}")
            operand = instruction.operands.lower()
            rip = rip_pattern.search(operand)
            comment = comment_pattern.search(operand)
            if rip and comment:
                sign, displacement_text = rip.groups()
                displacement = int(displacement_text or "0", 16)
                target = instruction.address + len(instruction.raw_bytes)
                target += displacement if sign == "+" else -displacement
                noted_target = int(comment.group(1), 16)
                if target != noted_target:
                    raise ValueError(f"RIP-relative comment disagrees with instruction at RVA 0x{instruction.address:X}")
            verified += 1
    return verified


def _method_queries() -> tuple[tuple[str, str], ...]:
    return (
        ("TheForest.DebugConsole", "Awake"),
        ("TheForest.DebugConsole", "GetInstance"),
        ("TheForest.DebugConsole", "OnGUI"),
        ("TheForest.DebugConsole", "OnDestroy"),
        ("PS4Controller", "Update"),
        ("PS4Controller", "ProcessGamePads"),
        ("Rewired.ReInput", "get_players"),
    )


def _query_method_rows(metadata: MetadataV23, module: Path, image: Elf64Image,
                       table_offset: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for selector, method_name in _method_queries():
        matching_types = metadata.find_types(selector)
        candidates: list[tuple[TypeDefinition, MethodDefinition]] = []
        for type_def in matching_types:
            candidates.extend((type_def, method)
                              for method in metadata.methods_named(type_def, method_name))
        if not candidates:
            result.append({"selector": selector, "method": method_name,
                           "status": "not found in metadata"})
            continue
        for type_def, method in candidates:
            rva, file_backed = resolve_method_rva(module, image, method, table_offset)
            result.append({
                "selector": selector,
                "method": method.name,
                "type": type_def.full_name,
                "type_index": type_def.index,
                "definition_index": method.definition_index,
                "method_index": method.method_index,
                "token": method.token,
                "parameter_count": method.parameter_count,
                "rva": rva,
                "executable": file_backed,
                "status": "resolved" if rva is not None and file_backed else
                         "methodIndex has no executable file-backed RVA",
            })
    return result


def validate_pinned_on_destroy_identity(method_rows: list[dict[str, object]],
                                        metadata_sha256: str,
                                        module_sha256: str) -> None:
    """Fail closed if the original pinned files no longer resolve OnDestroy."""
    expectations = json.loads(ONDESTROY_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    if (metadata_sha256 != expectations["metadata_sha256"] or
            module_sha256 != expectations["module_sha256"]):
        return
    expected = expectations["method"]
    expected_values = (
        int(expected["definition_index"]), int(expected["method_index"]),
        int(expected["token"], 16), int(expected["rva"], 16),
    )
    matches = [row for row in method_rows
               if row.get("type") == expected["type"] and
               row.get("method") == expected["name"]]
    if len(matches) != 1:
        raise ValueError("pinned PS4 inputs must resolve exactly one DebugConsole.OnDestroy row")
    row = matches[0]
    actual = (int(row.get("definition_index", -1)),
              int(row.get("method_index", -1)), int(row.get("token", -1)),
              int(row.get("rva", -1)) if row.get("rva") is not None else -1)
    if actual != expected_values:
        raise ValueError("pinned PS4 DebugConsole.OnDestroy identity mismatch: "
                         f"expected {expected_values}, got {actual}")


def _metadata_type_candidates(metadata: MetadataV23) -> tuple[list[dict[str, object]], list[TypeDefinition]]:
    candidates: list[dict[str, object]] = []
    for type_def in metadata.find_types("CoopPeerStarter"):
        fields = [field.name for field in metadata.owned_fields(type_def)]
        candidates.append({"candidate_group": "possible DedicatedHost owner",
                           "type": type_def.full_name,
                           "type_index": type_def.index,
                           "field_present": "DedicatedHost" in fields,
                           "status": "metadata candidate only; native slot binding unresolved"})
    rewired_interfaces = [type_def for type_def in metadata.types
                          if type_def.namespace.startswith("Rewired") and type_def.is_interface]
    for type_def in rewired_interfaces:
        candidates.append({"candidate_group": "Rewired interface candidate pool",
                           "type": type_def.full_name,
                           "type_index": type_def.index,
                           "field_present": None,
                           "status": "interface candidate only; native slot binding unresolved"})
    return candidates, rewired_interfaces


def _on_destroy_assessment(method_rows: list[dict[str, object]],
                           windows: list[Window],
                           symbols: dict[int, set[str]],
                           store_sites: dict[int, str],
                           conditions: dict[int, str],
                           pinned_input: bool = False) -> str:
    matches = [row for row in method_rows
               if row.get("method") == "OnDestroy"
               and row.get("type") == "TheForest.DebugConsole"]
    if not matches:
        return ("UNRESOLVED: no `TheForest.DebugConsole.OnDestroy` row was produced "
                "from the supplied PS4 metadata.")
    row = matches[0]
    if row.get("status") != "resolved":
        return (f"UNRESOLVED: metadata row exists (`methodIndex` `{row.get('method_index')}`), "
                "but it has no executable, file-backed native RVA.")
    expectations = json.loads(ONDESTROY_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    expected_method = expectations["method"]
    expected_identity = (
        int(expected_method["definition_index"]),
        int(expected_method["method_index"]),
        int(expected_method["token"], 16),
        int(expected_method["rva"], 16),
    )
    actual_identity = (
        int(row.get("definition_index", -1)),
        int(row.get("method_index", -1)),
        int(row.get("token", -1)),
        int(row.get("rva", -1)),
    )
    rva = int(row["rva"])
    pinned_identity = pinned_input and actual_identity == expected_identity
    window = next((item for item in windows if item.rva == rva), None)
    if window is None:
        return (f"RVA `0x{rva:08X}` is resolved, but no bounded native body starts there; "
                "the Counters and Instance store instructions were not verified from this input.")

    instructions = {item.address: item for item in window.instructions}

    def normalized_store(site: int) -> tuple[str, str] | None:
        instruction = instructions.get(site)
        if instruction is None or instruction.mnemonic not in {"mov", "movq"}:
            return None
        operands = instruction.operands.split(",", 1)
        if len(operands) != 2:
            return None
        destination = re.sub(r"\s+", "", operands[0].lower())
        destination = destination.replace("qwordptr", "")
        source = re.sub(r"\s+", "", operands[1].lower())
        return destination, source

    def matches_store(site: int, field_offset: str, source_pattern: str) -> bool:
        parsed = normalized_store(site)
        if parsed is None:
            return False
        destination, source = parsed
        expected_destination = f"[rax+{int(field_offset, 16):#x}]"
        if destination != expected_destination:
            return False
        if source_pattern == "0":
            return source in {"0", "0x0"}
        return source == source_pattern

    if pinned_identity and rva == int(expected_method["rva"], 16):
        counters, instance = expectations["stores"]
        counters_match = matches_store(
            int(counters["rva"], 16), counters["static_fields_offset"],
            counters["source_pattern"])
        instance_match = matches_store(
            int(instance["rva"], 16), instance["static_fields_offset"],
            instance["source_pattern"])
        this_evidence = expectations["this_register_evidence"]
        this_move = instructions.get(int(this_evidence["rva"], 16))
        expected_this_instruction = re.sub(
            r"\s+", "", this_evidence["instruction"].lower())
        actual_this_instruction = (re.sub(r"\s+", "", this_move.mnemonic.lower() +
                                          this_move.operands.lower())
                                  if this_move else "")
        preserves_this = bool(
            this_move and actual_this_instruction == expected_this_instruction)
        counters_label = (
            f"`{counters['static_field']}` at `0x{int(counters['rva'], 16):08X}` "
            f"({counters['static_fields_offset']}) "
            f"{'matches' if counters_match else 'does not match'} `mov [rax + 0x8], 0`"
        )
        instance_source = ("`this` (R14 was saved from RDI at the recorded prologue site)"
                           if instance_match and preserves_this else
                           "R14 (origin not verified in this window)")
        instance_label = (
            f"`{instance['static_field']}` at `0x{int(instance['rva'], 16):08X}` "
            f"({instance['static_fields_offset']}) "
            f"{'matches' if instance_match else 'does not match'} `mov [rax + 0x10], r14`; "
            f"source resolves to {instance_source}"
        )
        if counters_match and instance_match:
            return ("Pinned PS4 instruction expectations: " + counters_label + "; " +
                    instance_label + ". The zero store targets Counters; the Instance "
                    "store writes a register value and is not an Instance clear. These "
                    "are observed instruction patterns, not proof that Unity invoked "
                    "OnDestroy or that the stored pointer remains a live Unity object.")
        return ("Pinned PS4 OnDestroy identity resolved, but its recorded store patterns "
                "were not both present at their expected RVAs: " + counters_label + "; " +
                instance_label + ". Do not infer Instance cleanup from this window.")

    local_stores = {site: label for site, label in store_sites.items()
                    if window.rva <= site < window.rva + window.size}
    local_conditions = {site: label for site, label in conditions.items()
                        if window.rva <= site < window.rva + window.size}
    cfg, _sinks, _guards = analyze_window(window, symbols, local_stores,
                                          local_conditions)
    incomplete = bool(cfg.fallthrough_gaps or cfg.external_branches or cfg.open_end)
    zero_stores = []
    for site, label in local_stores.items():
        if label not in {"DebugConsole.Instance", "TheForest.DebugConsole.Instance"}:
            continue
        instruction = instructions.get(site)
        if instruction is None:
            continue
        operands = instruction.operands.split(",", 1)
        source = operands[1].strip().lower() if len(operands) == 2 else ""
        if source in {"0", "0x0"}:
            zero_stores.append(site)
    if zero_stores and not incomplete:
        sites = ", ".join(f"`0x{site:08X}`" for site in zero_stores)
        return (f"The supplied instruction-level CFG has no decoded gaps, external branches, "
                f"or open end and contains an analyst-annotated direct zero store to "
                f"`DebugConsole.Instance` at {sites}. This supports a clear on that visible "
                "path. It does not prove exact function extent, runtime invocation, or that "
                "every path is represented.")
    if zero_stores:
        return ("A direct zero store to the analyst-annotated `DebugConsole.Instance` is visible, "
                "but the CFG window has gaps, an external branch, or an open end; cleanup "
                "conditions remain unresolved.")
    if local_stores:
        return ("An analyst-annotated store is visible, but no immediate zero source was proven "
                "in this body. It does not establish singleton cleanup.")
    return ("The supplied bounded body contains no analyst-annotated direct store to "
            "`DebugConsole.Instance`. This does not rule out an indirect helper or alias; "
            "cleanup remains unresolved.")


def _targeted_disassemble(objdump: str, module: Path, rva: int,
                          window_bytes: int) -> str:
    version = subprocess.run([objdump, "--version"], capture_output=True,
                             text=True, check=False).stdout.splitlines()
    first = version[0] if version else ""
    command = [objdump, "-d"]
    if "llvm" in first.lower():
        command.append("--x86-asm-syntax=intel")
    else:
        command.extend(["-M", "intel"])
    command.extend([f"--start-address=0x{rva:X}",
                    f"--stop-address=0x{rva + window_bytes:X}", str(module)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"targeted objdump failed at RVA 0x{rva:X} (exit {result.returncode})")
    return result.stdout


def collect_targeted_windows(method_rows: list[dict[str, object]], module: Path,
                             window_bytes: int, objdump: str | None = None) -> list[Window]:
    executable = objdump or shutil.which("llvm-objdump") or shutil.which("objdump")
    if not executable:
        raise RuntimeError("no local llvm-objdump or objdump found; pass --objdump")
    windows: list[Window] = []
    selected = {("TheForest.DebugConsole", "Awake"),
                ("TheForest.DebugConsole", "OnDestroy"),
                ("PS4Controller", "ProcessGamePads")}
    for row in method_rows:
        key = (row.get("selector"), row.get("method"))
        if key not in selected or row.get("status") != "resolved":
            continue
        rva = int(row["rva"])
        raw = _targeted_disassemble(executable, module, rva, window_bytes)
        label = f"{row['type']}.{row['method']}"
        text = f"{label} — RVA 0x{rva:08X} — ventana 0x{window_bytes:X} bytes\n{raw}"
        parsed = parse_windows(text)
        if parsed:
            windows.extend(parsed)
    return windows


def _render_method_table(rows: list[dict[str, object]]) -> list[str]:
    lines = ["| Managed method | TypeDef index | MethodDefinition index | methodIndex | Token | RVA | Status |",
             "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        if "rva" not in row:
            lines.append(f"| `{row['selector']}.{row['method']}` | — | — | — | — | — | {row['status']} |")
            continue
        rva = f"0x{int(row['rva']):08X}" if row["rva"] is not None else "—"
        lines.append(f"| `{row['type']}.{row['method']}` | `{row['type_index']}` | "
                     f"`{row['definition_index']}` | `{row['method_index']}` | "
                     f"`0x{int(row['token']):08X}` | `{rva}` | {row['status']} |")
    return lines


def render_pipeline_report(metadata: MetadataV23, module_sha256: str,
                           method_pointer_table_offset: int,
                           verified_instruction_count: int,
                           method_rows: list[dict[str, object]],
                           type_candidates: list[dict[str, object]],
                           rewired_interfaces: list[TypeDefinition],
                           type_slots: list[dict[str, object]],
                           windows: list[Window],
                           symbols: dict[int, set[str]],
                           dump_fields_report: tuple[list[dict[str, object]], bool] | None,
                           store_sites: dict[int, str], conditions: dict[int, str]) -> str:
    lines = [
        "# Unified offline PS4 IL2CPP lifecycle/input pipeline",
        "",
        f"- Metadata: v23, SHA-256 `{metadata.sha256}`.",
        f"- Module SHA-256 `{module_sha256}`; method pointer table file offset `0x{method_pointer_table_offset:X}`.",
        f"- Instruction byte sequences matched against the pinned ELF: `{verified_instruction_count}`.",
        "- Only targeted method windows are disassembled. No game code is executed or modified.",
        "- A metadata type name is not assigned to a native type-reference slot without a proven mapping.",
        "",
        "## MethodDefinition index and RVA resolution",
        "",
    ]
    lines.extend(_render_method_table(method_rows))
    lines.extend(["", "`MethodDefinition index` is the metadata row; `methodIndex` selects the v23 method-pointer table entry. The RVA is accepted only when it maps to an executable, file-backed PT_LOAD segment.",
                  "", "## Type metadata candidates (not native-slot resolutions)", "",
                  "| Candidate group | Metadata type candidate | TypeDef index | Field/interface evidence | Status |",
                  "| --- | --- | ---: | --- | --- |"])
    if type_candidates:
        for item in type_candidates:
            evidence = ("field DedicatedHost present" if item["field_present"] is True else
                        "field DedicatedHost absent" if item["field_present"] is False else
                        "interface flag set")
            lines.append(f"| {item['candidate_group']} | `{item['type']}` | `{item['type_index']}` | "
                         f"{evidence} | {item['status']} |")
    else:
        lines.append("| — | no matching type candidates in metadata | — | — | native slots unresolved |")
    lines.extend(["", f"- Rewired interface candidates in metadata: `{len(rewired_interfaces)}`. Their presence does not identify which interface is referenced by slot `0x33EF3E8`.",
                  "", "## Native type-reference slots and registration boundary", "",
                  "| Native slot RVA | 8-byte file-image value | Status |", "| ---: | ---: | --- |"])
    for slot in type_slots:
        value = "—" if slot["value"] is None else f"0x{int(slot['value']):016X}"
        lines.append(f"| `0x{int(slot['slot_rva']):08X}` | `{value}` | {slot['status']} |")
    lines.extend(["", "The v23 metadata tables identify TypeDef/field/interface candidates, but do not by themselves bind these native data-slot RVAs to a TypeDef. A binding requires this build's native metadata/code registration and the slot initializer or equivalent provenance. No PC-derived name or analyst-only type map is promoted to a verified PS4 mapping.",
                  "", "- Calls `0x004762D6` and `0x00476315` remain indirect until receiver type, interface offset, and concrete vtable target are tied to this module's metadata and native registration.",
                  "", "## Static field declaration check", ""])
    if dump_fields_report is None:
        lines.append("No local dump.cs supplied; metadata field ownership can be listed, but staticness is not asserted by this raw v23 parser.")
    else:
        results, valid = dump_fields_report
        lines.extend([f"- Local dump.cs comparison: **{'PASS' if valid else 'FAIL'}** against the pinned metadata version/hash.",
                      "| Managed type | Field | Static | Status |", "| --- | --- | --- | --- |"])
        for result in results:
            lines.append(f"| `{result.get('type', '—')}` | `{result.get('field', '—')}` | "
                         f"{result.get('static', '—')} | {result.get('status')} |")
    on_destroy_expectations = json.loads(
        ONDESTROY_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    pinned_on_destroy_input = (
        metadata.sha256 == on_destroy_expectations["metadata_sha256"] and
        module_sha256 == on_destroy_expectations["module_sha256"])
    lines.extend(["", "## DebugConsole.OnDestroy native writes", "",
                  _on_destroy_assessment(method_rows, windows, symbols,
                                         store_sites, conditions,
                                         pinned_input=pinned_on_destroy_input),
                  "", "Pinned identity expectations are recorded in `docs/PS4_ONDESTROY_EXPECTATIONS.json`. When the original PS4 input hashes are supplied, the pipeline checks the metadata definition index, methodIndex, token, executable RVA, and each supplied instruction byte against the module."])
    lines.extend(["", "## Native bounded windows", ""])
    if not windows:
        lines.append("No disassembly window supplied/generated. Method RVAs above are not proof that Unity invokes those methods.")
    else:
        references = resolve_references(windows, symbols)
        lines.extend(["### Direct and indirect references", "",
                      "| Source | Site RVA | Kind | Target / evidence |", "| --- | ---: | --- | --- |"])
        for ref in references:
            if ref.kind not in {"direct call/jump", "indirect call/jump"}:
                continue
            if ref.target_rva is None:
                target = ref.detail
            else:
                names = ", ".join(ref.target_names) or "unresolved direct target"
                target = f"0x{ref.target_rva:08X} ({names})"
            lines.append(f"| `{ref.source_name}` | `0x{ref.site_rva:08X}` | {ref.kind} | {target} |")
        for window in windows:
            local_stores = {site: label for site, label in store_sites.items()
                            if window.rva <= site < window.rva + window.size}
            local_conditions = {site: label for site, label in conditions.items()
                                if window.rva <= site < window.rva + window.size}
            lines.extend(["", f"### CFG: `{window.name}` (`0x{window.rva:08X}`)", "",
                          render_cfg(Path("private-bounded-window.txt"), window,
                                     symbols, local_stores, local_conditions)])
    lines.extend(["", "## Conclusion limits", "",
                  "- A resolved `OnDestroy` methodIndex/RVA identifies native code, not its runtime call or object lifetime. The two pinned stores are classified separately and do not establish an active Unity object.",
                  "- `0x33EB300` and `0x33EF3E8` are reported only as data/type-reference slots. Type candidates are metadata matches, not proof those slots point to those types.",
                  "- A vtable callsite is not a concrete method target without the receiver class and selected interface/vtable mapping.",
                  "- The pipeline is read-only. Metadata, module, dump.cs, and disassembly remain local; output omits source paths and instruction bytes.", ""])
    return "\n".join(lines)


def _parse_rva_annotations(entries: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    for entry in entries:
        match = re.fullmatch(r"(0x[0-9A-Fa-f]+)=(.+)", entry.strip())
        if not match:
            raise ValueError("annotations must use 0xRVA=Label")
        result[int(match.group(1), 16)] = match.group(2)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True,
                        help="private global-metadata.dat v23; never copied")
    parser.add_argument("--module", type=Path, required=True,
                        help=("private decrypted ELF64/OELF image for "
                              "Il2CppUserAssemblies.prx; SELF containers "
                              "cannot be RVA-mapped"))
    parser.add_argument("--method-pointer-table-offset", type=lambda v: int(v, 0),
                        default=METHOD_POINTER_TABLE_OFFSET)
    parser.add_argument("--expected-metadata-sha256", default=METADATA_SHA256)
    parser.add_argument("--expected-module-sha256", default=MODULE_SHA256)
    parser.add_argument("--dump-cs", type=Path,
                        help="optional private dump.cs for static field declarations")
    parser.add_argument("--static-fields", type=Path,
                        default=ROOT / "docs/PS4_STATIC_FIELD_EXPECTATIONS.json")
    parser.add_argument("--disassembly", type=Path,
                        help="optional private bounded llvm-objdump text windows")
    parser.add_argument("--disassemble-targeted", action="store_true",
                        help="disassemble only Awake, OnDestroy, and ProcessGamePads windows")
    parser.add_argument("--window-bytes", type=lambda v: int(v, 0), default=0x240,
                        help="bounded bytes per selected method; 0x240 covers OnDestroy through its next method")
    parser.add_argument("--objdump", help="local llvm-objdump/objdump executable")
    parser.add_argument("--store-site", action="append", default=[],
                        help="analyst-verified store annotation 0xRVA=Field.Name")
    parser.add_argument("--condition", action="append", default=[],
                        help="evidence-backed branch annotation 0xRVA=Condition")
    parser.add_argument("--output", type=Path, required=True,
                        help="local Markdown report; source paths are omitted")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata_bytes = args.metadata.read_bytes()
        metadata = parse_metadata_v23(metadata_bytes)
        # Reject encrypted SCE/SELF containers before hash comparison so the
        # caller gets the actionable format limitation, not a misleading
        # historical-image hash mismatch. This parses headers only.
        image = Elf64Image(args.module)
        module_sha = _hash_file(args.module)
        expected_metadata_sha = args.expected_metadata_sha256.lower()
        expected_module_sha = args.expected_module_sha256.lower()
        if metadata.sha256 != expected_metadata_sha:
            raise ValueError(f"metadata SHA-256 mismatch: expected {expected_metadata_sha}, got {metadata.sha256}")
        if module_sha != expected_module_sha:
            raise ValueError(f"module SHA-256 mismatch: expected {expected_module_sha}, got {module_sha}")
        if image.image_base != 0:
            raise ValueError("pinned PS4 module was expected to use PT_LOAD image base 0; refusing RVA/table interpretation")
        methods = _query_method_rows(metadata, args.module, image,
                                     args.method_pointer_table_offset)
        validate_pinned_on_destroy_identity(methods, metadata.sha256, module_sha)
        type_candidates, rewired_interfaces = _metadata_type_candidates(metadata)
        type_slots = [inspect_static_slot(args.module, image, slot)
                      for slot in (0x033EB300, 0x033EF3E8)]
        symbols, _provenance = load_symbols()
        for row in methods:
            if row.get("rva") is not None and row.get("type"):
                symbols.setdefault(int(row["rva"]), set()).add(f"{row['type']}.{row['method']}")

        dump_check = None
        if args.dump_cs:
            expected = json.loads(args.static_fields.read_text(encoding="utf-8"))
            dump_text = args.dump_cs.read_text(encoding="utf-8-sig", errors="replace")
            field_records = parse_dump_fields(dump_text)
            field_results, valid = verify_expected_fields(
                field_records, expected, METADATA_VERSION, metadata.sha256)
            dump_check = (field_results, valid)

        windows: list[Window] = []
        if args.disassembly:
            windows.extend(parse_windows(args.disassembly.read_text(encoding="utf-8")))
        if args.disassemble_targeted:
            windows.extend(collect_targeted_windows(methods, args.module,
                                                    args.window_bytes, args.objdump))
        # Deduplicate windows by method RVA, preferring the first local source.
        unique: dict[int, Window] = {}
        for window in windows:
            unique.setdefault(window.rva, window)
        verified_instruction_count = verify_window_bytes(image, list(unique.values()))
        report = render_pipeline_report(
            metadata, module_sha, args.method_pointer_table_offset,
            verified_instruction_count, methods, type_candidates, rewired_interfaces,
            type_slots, list(unique.values()), symbols, dump_check,
            _parse_rva_annotations(args.store_site),
            _parse_rva_annotations(args.condition))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        return 1 if dump_check is not None and not dump_check[1] else 0
    except (OSError, ValueError, struct.error, json.JSONDecodeError,
            RuntimeError) as exc:
        print(f"analyze-ps4-il2cpp-pipeline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
