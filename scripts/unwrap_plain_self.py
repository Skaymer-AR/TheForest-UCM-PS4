#!/usr/bin/env python3
"""Inspect/unpack a supported *plaintext* PS4 SELF into a private analysis ELF.

No keys, decryption, signature verification, patching, execution or upload.
Encrypted/compressed/ambiguous layouts fail before an output file is created.
The output reconstructs file-backed ELF ranges; uncovered padding is zero.
Only a complete reference-file comparison proves preservation of padding too.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

SELF_HEADER = struct.Struct("<I4BIHHQHHI")
SELF_ENTRY = struct.Struct("<4Q")
ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
PROGRAM_HEADER = struct.Struct("<II6Q")
SELF_MAGIC = 0x1D3D154F
PT_SCE_VERSION = 0x6FFFFF01
MAX_ELF_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class Segment:
    kind: int
    flags: int
    offset: int
    vaddr: int
    filesz: int
    memsz: int


def checked_range(offset: int, size: int, limit: int, label: str) -> tuple[int, int]:
    if offset < 0 or size < 0 or offset > limit or size > limit - offset:
        raise ValueError(f"{label}: range is outside the permitted bytes")
    return offset, offset + size


def merged_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start == end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(end, merged[-1][1])
        else:
            merged.append((start, end))
    return merged


def unpack_plain_self(data: bytes, max_elf_bytes: int = MAX_ELF_BYTES) -> tuple[bytes, dict]:
    if len(data) < SELF_HEADER.size:
        raise ValueError("truncated SELF header")
    h = SELF_HEADER.unpack_from(data)
    if h[0] != SELF_MAGIC or h[3] != 1:
        raise ValueError("expected a little-endian PS4 SELF")
    header_size, meta_size, declared_size, count = h[6], h[7], h[8], h[9]
    if not 1 <= count <= 512:
        raise ValueError("invalid SELF entry count")
    if not header_size + meta_size <= declared_size <= len(data):
        raise ValueError("SELF header/meta/file size is inconsistent")
    elf_at = SELF_HEADER.size + count * SELF_ENTRY.size
    checked_range(SELF_HEADER.size, count * SELF_ENTRY.size, header_size, "SELF entries")
    checked_range(elf_at, ELF_HEADER.size, header_size, "embedded ELF header")
    eh = ELF_HEADER.unpack_from(data, elf_at)
    ident = eh[0]
    if ident[:7] != b"\x7fELF\x02\x01\x01" or eh[2] != 62 or eh[3] != 1:
        raise ValueError("expected an embedded little-endian x86-64 ELF64")
    if eh[8] != ELF_HEADER.size or eh[9] != PROGRAM_HEADER.size or not 1 <= eh[10] <= 256:
        raise ValueError("unsupported ELF/program header sizes or count")
    if eh[6] or eh[12]:
        raise ValueError("ELF section tables are unsupported; do not silently discard them")
    phoff, phnum = eh[5], eh[10]
    if phoff < ELF_HEADER.size:
        raise ValueError("ELF program headers overlap the ELF header")
    _, headers_end = checked_range(phoff, phnum * PROGRAM_HEADER.size,
                                   header_size - elf_at, "ELF program headers")
    segments: list[Segment] = []
    output_size = headers_end
    for i in range(phnum):
        p = PROGRAM_HEADER.unpack_from(data, elf_at + phoff + i * PROGRAM_HEADER.size)
        segment = Segment(p[0], p[1], p[2], p[3], p[5], p[6])
        _, end = checked_range(segment.offset, segment.filesz, max_elf_bytes,
                               f"program header {i}")
        output_size = max(output_size, end)
        segments.append(segment)
    output = bytearray(output_size)
    copied: list[tuple[int, int]] = []

    def copy_region(offset: int, payload: bytes, label: str) -> None:
        start, end = checked_range(offset, len(payload), len(output), label)
        for previous_start, previous_end in copied:
            overlap_start, overlap_end = max(start, previous_start), min(end, previous_end)
            if overlap_start < overlap_end:
                if output[overlap_start:overlap_end] != payload[overlap_start-start:overlap_end-start]:
                    raise ValueError(f"{label}: conflicting overlapping ELF ranges")
        output[start:end] = payload
        copied.append((start, end))

    headers = bytearray(data[elf_at:elf_at + headers_end])
    # Some FSELF headers retain e_shentsize/e_shstrndx from a removed table.
    # With BOTH e_shoff and e_shnum zero, normalize these descriptive fields;
    # disclose the change instead of implying that section bytes were recovered.
    struct.pack_into("<HHH", headers, 0x3A, 0, 0, 0)
    copy_region(0, headers, "ELF headers")
    seen: set[int] = set()
    entries = []
    last_payload_end = 0
    # Signed and block-size flags are descriptive. No digest/signature is verified.
    supported_flags = 1 | 4 | (1 << 11) | (15 << 12) | (0xFFFF << 20)
    for i in range(count):
        props, offset, stored_size, decoded_size = SELF_ENTRY.unpack_from(data, 32 + i * 32)
        _, end = checked_range(offset, stored_size, declared_size, f"SELF entry {i}")
        if not props & (1 << 11):
            continue  # digest/metadata entries are not ELF payloads
        if props & 2:
            raise ValueError(f"SELF entry {i} is encrypted; a platform-authorized decrypted copy is needed")
        if props & 8:
            raise ValueError(f"SELF entry {i} is compressed; this reader does not implement that codec")
        if props & ~supported_flags:
            raise ValueError(f"SELF entry {i} has unsupported data-layout flags")
        index = (props >> 20) & 0xFFFF
        if index >= phnum or index in seen:
            raise ValueError(f"SELF entry {i} has an invalid/duplicate program header index")
        p = segments[index]
        if stored_size != decoded_size or stored_size != p.filesz:
            raise ValueError(f"SELF entry {i} size differs from its ELF program header")
        if stored_size and offset < header_size + meta_size:
            raise ValueError(f"SELF entry {i} overlaps the SELF headers/metadata")
        payload = data[offset:end]
        copy_region(p.offset, payload, f"SELF entry {i}")
        seen.add(index)
        last_payload_end = max(last_payload_end, end)
        entries.append({"program_header": index, "file_offset": p.offset,
                        "size": p.filesz, "sha256": hashlib.sha256(payload).hexdigest()})
    if not seen:
        raise ValueError("no plaintext blocked ELF payloads")
    coverage = merged_ranges(copied)
    missing_versions = [i for i, p in enumerate(segments) if p.kind == PT_SCE_VERSION
                        and p.filesz and not any(a <= p.offset and p.offset+p.filesz <= b
                                                for a, b in coverage)]
    trailer_size = len(data) - declared_size
    if missing_versions:
        # Supported FSELF layout: exactly one version segment follows declared EOF.
        # Reject all ambiguous trailers; never fill missing bytes from a reference.
        if len(missing_versions) != 1:
            raise ValueError("ambiguous ELF version trailers")
        i = missing_versions[0]
        p = segments[i]
        if trailer_size != p.filesz or any(data[last_payload_end:declared_size]):
            raise ValueError("missing or ambiguous ELF version trailer")
        copy_region(p.offset, data[declared_size:], "ELF version trailer")
    elif trailer_size:
        raise ValueError("unexplained bytes after declared SELF file size")
    coverage = merged_ranges(copied)
    for i, p in enumerate(segments):
        if p.filesz and not any(a <= p.offset and p.offset+p.filesz <= b for a, b in coverage):
            raise ValueError(f"program header {i} has file-backed bytes missing from the SELF")
    gaps = []
    cursor = 0
    for start, end in coverage:
        if cursor < start:
            gaps.append([cursor, start])
        cursor = end
    result = bytes(output)
    return result, {"format": "plaintext PS4 SELF", "self_entry_count": count,
                    "self_sha256": hashlib.sha256(data).hexdigest(),
                    "elf_size": len(result), "elf_sha256": hashlib.sha256(result).hexdigest(),
                    "elf_program_headers": phnum, "payloads": entries,
                    "version_trailer_bytes": trailer_size, "zero_filled_gaps": gaps,
                    "absent_section_table_source_fields": {"e_shentsize": eh[11],
                                                           "e_shstrndx": eh[13]},
                    "cryptographic_signature_verified": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self", dest="source", type=Path, required=True)
    parser.add_argument("--reference-elf", type=Path)
    parser.add_argument("--output-elf", type=Path, help="optional PRIVATE new file; never overwrites")
    args = parser.parse_args(argv)
    try:
        output, report = unpack_plain_self(args.source.read_bytes())
        if args.reference_elf:
            reference = args.reference_elf.read_bytes()
            report["reference_sha256"] = hashlib.sha256(reference).hexdigest()
            report["reference_identical"] = output == reference
        if args.output_elf:
            # An existing source, reference, or prior output can never be replaced.
            with args.output_elf.open("xb") as target:
                target.write(output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, struct.error) as exc:
        print(f"plain-self: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
