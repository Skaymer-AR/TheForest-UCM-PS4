#!/usr/bin/env python3
"""Offline report for locally generated Il2CppDumper dump.cs files.

This script does not upload, copy into the repository, or commit game files.
When given --binary it invokes the locally supplied Il2CppDumper executable
with the original paths and writes its temporary output outside the project.
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


METADATA_MAGIC = 0xFAB11BAF
TARGET_CLASSES = (
    "TheForest.Tools.DllModLoader",
    "TheForest.Modding.UI.ModList",
    "Cheats.CheatsBridge",
    "TheForest.UI.VirtualCursor",
    "TheForest.DebugConsole",
)

NAMESPACE_RE = re.compile(r"^\s*//\s*Namespace:\s*(.*?)\s*$")
CLASS_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|sealed|abstract|partial|unsafe|new)\s+)*"
    r"(?:class|struct|interface|enum)\s+([A-Za-z_][A-Za-z0-9_`]*)(?:\s*<[^>]*>)?"
)
RVA_RE = re.compile(
    r"//\s*RVA:\s*(0x[0-9A-Fa-f]+)"
    r"(?:\s+Offset:\s*(0x[0-9A-Fa-f]+))?"
    r"(?:\s+VA:\s*(0x[0-9A-Fa-f]+))?"
)


@dataclass(frozen=True)
class MetadataInfo:
    version: int
    size: int


@dataclass(frozen=True)
class CandidateMethod:
    class_name: str
    managed_signature: str
    rva: int
    file_offset: int | None
    va: int | None


@dataclass
class _ClassFrame:
    full_name: str
    end_depth: int
    awaiting_open: bool


def read_metadata_info(path: Path) -> MetadataInfo:
    """Validate only the stable magic/version prefix; do not parse game data."""
    with path.open("rb") as metadata:
        prefix = metadata.read(8)
        metadata.seek(0, 2)
        size = metadata.tell()
    if len(prefix) != 8:
        raise ValueError("global-metadata.dat is shorter than its 8-byte header")
    magic, version = struct.unpack("<Ii", prefix)
    if magic != METADATA_MAGIC:
        raise ValueError(
            f"metadata magic mismatch: expected 0x{METADATA_MAGIC:08X}, "
            f"received 0x{magic:08X}"
        )
    if version <= 0:
        raise ValueError(f"invalid metadata version {version}")
    return MetadataInfo(version=version, size=size)


def _matching_target(class_name: str) -> str | None:
    for target in TARGET_CLASSES:
        if class_name == target or class_name.endswith("." + target):
            return target
    # Some dumps qualify the nested PC bridge as Cheats+CheatsBridge.
    if class_name.endswith("Cheats+CheatsBridge"):
        return "Cheats.CheatsBridge"
    return None


def parse_dump_cs(path: Path) -> tuple[list[str], list[CandidateMethod]]:
    """Read class/method declarations and RVA comments from a local dump.cs."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    found_classes: set[str] = set()
    methods: list[CandidateMethod] = []
    class_stack: list[_ClassFrame] = []
    namespace = ""
    brace_depth = 0
    pending_rva: tuple[int, int | None, int | None] | None = None

    for line in text.splitlines():
        stripped = line.strip()
        while (class_stack and brace_depth < class_stack[-1].end_depth and
               not class_stack[-1].awaiting_open):
            class_stack.pop()

        namespace_match = NAMESPACE_RE.match(line)
        if namespace_match:
            namespace = namespace_match.group(1).strip()

        class_match = CLASS_RE.match(line)
        if class_match:
            name = class_match.group(1)
            parent = class_stack[-1].full_name if class_stack else namespace
            full_name = f"{parent}.{name}" if parent else name
            found_classes.add(full_name)
            target = _matching_target(full_name)
            if target:
                found_classes.add(target)
            # dump.cs normally puts '{' on the declaration line. Treat a
            # brace on the following line as the class body too.
            opens = line.count("{")
            closes = line.count("}")
            end_depth = brace_depth + max(1, opens - closes)
            class_stack.append(_ClassFrame(full_name, end_depth,
                                           opens == 0 and closes == 0))
            pending_rva = None
        else:
            rva_match = RVA_RE.search(line)
            if rva_match:
                pending_rva = (
                    int(rva_match.group(1), 16),
                    int(rva_match.group(2), 16) if rva_match.group(2) else None,
                    int(rva_match.group(3), 16) if rva_match.group(3) else None,
                )
            elif pending_rva and stripped and not stripped.startswith("//") and not stripped.startswith("["):
                if class_stack and "(" in stripped and ")" in stripped:
                    full_name = class_stack[-1].full_name
                    if _matching_target(full_name):
                        declaration = stripped.split("//", 1)[0].strip()
                        declaration = re.sub(r"\s*\{.*$", "", declaration).rstrip()
                        methods.append(CandidateMethod(
                            class_name=full_name,
                            managed_signature=declaration,
                            rva=pending_rva[0],
                            file_offset=pending_rva[1],
                            va=pending_rva[2],
                        ))
                pending_rva = None

        line_opens = line.count("{")
        line_closes = line.count("}")
        if class_stack and class_stack[-1].awaiting_open and line_opens:
            class_stack[-1].awaiting_open = False
        brace_depth += line_opens - line_closes
        while (class_stack and brace_depth < class_stack[-1].end_depth and
               not class_stack[-1].awaiting_open):
            class_stack.pop()

    matched = sorted({target for name in found_classes if (target := _matching_target(name))})
    return matched, methods


def invoke_dumper(dumper: Path, binary: Path, metadata: Path) -> tuple[list[str], list[CandidateMethod]]:
    """Run a local Il2CppDumper command and parse its temporary dump.cs."""
    if not dumper.is_file():
        raise ValueError(f"local Il2CppDumper executable not found: {dumper}")
    with tempfile.TemporaryDirectory(prefix="theforest-il2cpp-") as temp_dir:
        output_dir = Path(temp_dir)
        result = subprocess.run(
            [str(dumper), str(binary), str(metadata), str(output_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"local Il2CppDumper exited with status {result.returncode}; "
                "check its local output and confirm the executable is decrypted"
            )
        dumps = list(output_dir.rglob("dump.cs"))
        if not dumps:
            raise RuntimeError("Il2CppDumper completed but produced no dump.cs")
        # Keep only parsed declarations in memory; the temporary dump and all
        # dumper output are removed when this context exits.
        return parse_dump_cs(dumps[0])


def render_report(metadata: MetadataInfo,
                  found_classes: Iterable[str],
                  methods: Iterable[CandidateMethod]) -> str:
    found = set(found_classes)
    rows = list(methods)
    output = [
        "# Offline IL2CPP integration candidates",
        "",
        f"- Metadata header: valid; version `{metadata.version}`; "
        f"size `{metadata.size}` bytes.",
        "- Input paths and original binary contents are omitted from this report.",
        "- Method signatures below are managed declarations from the local dump; "
        "they are not native x86-64 ABI prototypes.",
        "",
        "| Target class | Managed method declaration | RVA | File offset | VA |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for target in TARGET_CLASSES:
        target_rows = [m for m in rows if _matching_target(m.class_name) == target]
        if not target_rows:
            status = "class present; no RVA methods captured" if target in found else "not found in dump"
            output.append(f"| `{target}` | *{status}* | — | — | — |")
            continue
        for method in target_rows:
            rva = f"0x{method.rva:X}" if method.rva else "0x0 (no body)"
            offset = f"0x{method.file_offset:X}" if method.file_offset is not None else "—"
            va = f"0x{method.va:X}" if method.va is not None else "—"
            declaration = method.managed_signature.replace("|", "\\|")
            output.append(
                f"| `{method.class_name}` | `{declaration}` | `{rva}` | `{offset}` | `{va}` |"
            )
    output.extend([
        "",
        "## Interpretation",
        "",
        "A nonzero RVA is only a candidate address in the exact local executable "
        "passed to the dumper. Confirm its module, bytes, prologue, call convention, "
        "hidden IL2CPP parameters, and thread/lifetime context with an offline "
        "disassembly before considering integration.",
        "No method in this report is proof that a GoldHEN PRX can register or call "
        "a Unity callback safely.",
        "",
    ])
    return "\n".join(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True,
                        help="local global-metadata.dat; never copied or uploaded")
    parser.add_argument("--dump-cs", type=Path,
                        help="existing local Il2CppDumper dump.cs")
    parser.add_argument("--binary", type=Path,
                        help="local decrypted ELF/OELF; used only with --dumper")
    parser.add_argument("--dumper", type=Path,
                        help="local Il2CppDumper executable; no download is performed")
    parser.add_argument("--output", type=Path,
                        help="write Markdown report here; default is stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata = read_metadata_info(args.metadata)
        if args.dump_cs and (args.binary or args.dumper):
            raise ValueError("use either --dump-cs or --binary with --dumper")
        if args.dump_cs:
            if not args.dump_cs.is_file():
                raise ValueError(f"local dump.cs not found: {args.dump_cs}")
            found, methods = parse_dump_cs(args.dump_cs)
        elif args.binary and args.dumper:
            if not args.binary.is_file():
                raise ValueError(f"local executable not found: {args.binary}")
            found, methods = invoke_dumper(args.dumper, args.binary,
                                           args.metadata)
        else:
            raise ValueError("provide --dump-cs or both --binary and --dumper")

        report = render_report(metadata, found, methods)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"analyze-il2cpp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
