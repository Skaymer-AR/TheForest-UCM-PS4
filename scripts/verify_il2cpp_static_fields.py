#!/usr/bin/env python3
"""Check private IL2CPP dump.cs field identity against an expected field map.

This verifies that named fields belong to the expected managed types and are
declared static in a locally generated dump. It does not infer runtime values,
native class-pointer identity, or an offset that the dump does not provide.
Original inputs remain local.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_il2cpp import CLASS_RE, NAMESPACE_RE, read_metadata_info  # noqa: E402

FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_`]*$")
FIELD_OFFSET_RE = re.compile(r"//\s*(?:(?:offset|field offset)\s*:\s*)?(0x[0-9A-Fa-f]+)\b", re.I)


@dataclass(frozen=True)
class FieldRecord:
    type_name: str
    field_name: str
    is_static: bool
    declared_offset: int | None
    declaration: str


@dataclass
class ClassFrame:
    full_name: str
    end_depth: int
    awaiting_open: bool


def parse_dump_fields(text: str) -> list[FieldRecord]:
    fields: list[FieldRecord] = []
    class_stack: list[ClassFrame] = []
    namespace = ""
    brace_depth = 0
    for line in text.splitlines():
        while (class_stack and brace_depth < class_stack[-1].end_depth
               and not class_stack[-1].awaiting_open):
            class_stack.pop()
        namespace_match = NAMESPACE_RE.match(line)
        if namespace_match:
            namespace = namespace_match.group(1).strip()
        class_match = CLASS_RE.match(line)
        if class_match:
            name = class_match.group(1)
            parent = class_stack[-1].full_name if class_stack else namespace
            full_name = f"{parent}.{name}" if parent else name
            opens, closes = line.count("{"), line.count("}")
            class_stack.append(ClassFrame(full_name,
                                          brace_depth + max(1, opens - closes),
                                          opens == 0 and closes == 0))
        elif class_stack:
            declaration = line.split("//", 1)[0].strip()
            if declaration.endswith(";") and "(" not in declaration and not declaration.startswith("//"):
                left = declaration[:-1].split("=", 1)[0].strip()
                tokens = left.split()
                field_name = tokens[-1] if tokens else ""
                if FIELD_NAME_RE.fullmatch(field_name):
                    offset_match = FIELD_OFFSET_RE.search(line)
                    fields.append(FieldRecord(
                        class_stack[-1].full_name,
                        field_name,
                        "static" in tokens,
                        int(offset_match.group(1), 16) if offset_match else None,
                        declaration,
                    ))
        line_opens, line_closes = line.count("{"), line.count("}")
        if class_stack and class_stack[-1].awaiting_open and line_opens:
            class_stack[-1].awaiting_open = False
        brace_depth += line_opens - line_closes
        while (class_stack and brace_depth < class_stack[-1].end_depth
               and not class_stack[-1].awaiting_open):
            class_stack.pop()
    return fields


def _type_matches(record_type: str, expected: dict[str, object]) -> bool:
    exact = expected.get("type")
    if isinstance(exact, str):
        return record_type == exact
    suffix = expected.get("type_suffix")
    if isinstance(suffix, str):
        leaf = record_type.replace("+", ".").split(".")[-1]
        return leaf == suffix
    raise ValueError("each expected field must define 'type' or 'type_suffix'")


def verify_expected_fields(fields: list[FieldRecord], expected: dict[str, object],
                           metadata_version: int,
                           metadata_sha256: str | None = None) -> tuple[list[dict[str, object]], bool]:
    expected_version = expected.get("metadata_version")
    if expected_version is not None and expected_version != metadata_version:
        return ([{"field": "<metadata version>", "status": "mismatch",
                  "expected": expected_version, "actual": metadata_version}], False)
    expected_sha256 = expected.get("metadata_sha256")
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise ValueError("expected metadata_sha256 must be 64 hexadecimal characters")
        if metadata_sha256 is None or expected_sha256.lower() != metadata_sha256.lower():
            return ([{"field": "<metadata SHA-256>", "status": "mismatch",
                      "expected": expected_sha256,
                      "actual": metadata_sha256 or "not supplied"}], False)
    entries = expected.get("fields")
    if not isinstance(entries, list):
        raise ValueError("expected-field manifest must contain a 'fields' array")
    results: list[dict[str, object]] = []
    all_valid = True
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("field"), str):
            raise ValueError("each field expectation must be an object with a field name")
        field_name = item["field"]
        matches = [record for record in fields
                   if record.field_name == field_name and _type_matches(record.type_name, item)]
        if not matches:
            results.append({"type": item.get("type", item.get("type_suffix")),
                            "field": field_name, "status": "not found"})
            all_valid = False
            continue
        if len(matches) != 1:
            results.append({"type": item.get("type", item.get("type_suffix")),
                            "field": field_name, "status": "ambiguous",
                            "matches": [record.type_name for record in matches]})
            all_valid = False
            continue
        record = matches[0]
        expected_static = item.get("static")
        if not isinstance(expected_static, bool):
            raise ValueError(f"expected field {field_name} must specify a boolean 'static'")
        valid = record.is_static == expected_static
        expected_offset = item.get("dump_offset")
        offset_note = "not emitted by dump.cs"
        if expected_offset is not None:
            if not isinstance(expected_offset, str) or not expected_offset.startswith("0x"):
                raise ValueError(f"dump_offset for {field_name} must be a hexadecimal string")
            if record.declared_offset is None:
                valid = False
                offset_note = "expected offset but dump.cs contains none"
            elif record.declared_offset != int(expected_offset, 16):
                valid = False
                offset_note = f"mismatch: dump 0x{record.declared_offset:X}"
            else:
                offset_note = f"matches 0x{record.declared_offset:X}"
        results.append({
            "type": record.type_name,
            "field": record.field_name,
            "static": record.is_static,
            "declared_offset": record.declared_offset,
            "native_evidence_note": item.get("native_evidence", "not supplied"),
            "dump_offset_check": offset_note,
            "status": "verified" if valid else "mismatch",
        })
        all_valid = all_valid and valid
    return results, all_valid


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dump_cs(dump_cs: Path | None, binary: Path | None,
                 dumper: Path | None, metadata: Path) -> tuple[str, str]:
    if dump_cs is not None:
        return dump_cs.read_text(encoding="utf-8-sig", errors="replace"), "existing local dump.cs; pairing supplied by caller"
    if binary is None or dumper is None:
        raise ValueError("provide --dump-cs or both --binary and --dumper")
    if not dumper.is_file() or not binary.is_file():
        raise ValueError("local binary and dumper paths must both exist")
    with tempfile.TemporaryDirectory(prefix="theforest-field-check-") as temp_dir:
        result = subprocess.run([str(dumper), str(binary), str(metadata), temp_dir],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"local Il2CppDumper exited with status {result.returncode}")
        dump_paths = list(Path(temp_dir).rglob("dump.cs"))
        if not dump_paths:
            raise RuntimeError("Il2CppDumper produced no dump.cs")
        return dump_paths[0].read_text(encoding="utf-8-sig", errors="replace"), "generated locally from the supplied binary and metadata"


def render_report(metadata_version: int, metadata_sha256: str,
                  dump_provenance: str, results: list[dict[str, object]],
                  valid: bool) -> str:
    lines = [
        "# Offline IL2CPP static-field identity check",
        "",
        f"- Metadata version: `{metadata_version}`.",
        f"- Metadata SHA-256: `{metadata_sha256}`.",
        f"- Dump provenance: {dump_provenance}.",
        "- Local input paths and original binary contents are omitted.",
        "- This checks managed field identity/static declaration. It does not prove a native class-pointer RVA or a live field value.",
        "",
        "| Type | Field | Static | Dump offset | Native evidence note | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        offset = result.get("declared_offset")
        offset_text = f"0x{offset:X}" if isinstance(offset, int) else "—"
        lines.append(f"| `{result.get('type', '—')}` | `{result.get('field', '—')}` | "
                     f"{result.get('static', '—')} | {offset_text} | "
                     f"{result.get('native_evidence_note', '—')} | {result.get('status')} |")
        if result.get("matches"):
            lines.append(f"<!-- ambiguous types: {', '.join(result['matches'])} -->")
    lines.extend(["", f"**Result: {'PASS' if valid else 'FAIL'}**", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True,
                        help="private local global-metadata.dat")
    parser.add_argument("--expected", type=Path, required=True,
                        help="local JSON field manifest with metadata_version and fields")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dump-cs", type=Path, help="existing local Il2CppDumper dump.cs")
    source.add_argument("--binary", type=Path, help="local decrypted ELF/OELF; pair with --dumper")
    parser.add_argument("--dumper", type=Path,
                        help="local Il2CppDumper executable; required with --binary")
    parser.add_argument("--output", type=Path, help="write Markdown report locally")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata_info = read_metadata_info(args.metadata)
        expected = json.loads(args.expected.read_text(encoding="utf-8"))
        dump_text, provenance = load_dump_cs(args.dump_cs, args.binary,
                                             args.dumper, args.metadata)
        fields = parse_dump_fields(dump_text)
        results, valid = verify_expected_fields(fields, expected,
                                                metadata_info.version,
                                                _sha256(args.metadata))
        report = render_report(metadata_info.version, _sha256(args.metadata),
                               provenance, results, valid)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
        return 0 if valid else 1
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"verify-il2cpp-static-fields: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
