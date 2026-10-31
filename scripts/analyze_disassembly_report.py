#!/usr/bin/env python3
"""Summarize bounded x86-64 disassembly windows without game binaries.

This read-only importer accepts a text disassembly supplied by the user. It
does not execute instructions, load the original ELF, patch code, or upload the
input. Its output deliberately reports direct edges only and treats each
window as partial unless a ret/tail-jump ends the visible body.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_ps4_il2cpp_candidates import (  # noqa: E402
    DEFAULT_EVIDENCE,
    parse_evidence,
)


HEADER_RE = re.compile(
    r"^(.+?)\s+—\s+RVA\s+(0x[0-9A-Fa-f]+)\s+—\s+ventana\s+"
    r"(0x[0-9A-Fa-f]+)\s+bytes\s*$"
)
LINE_RE = re.compile(r"^\s*([0-9A-Fa-f]+):\s*(.*?)\s*$")
BYTE_RE = re.compile(r"^[0-9A-Fa-f]{2}$")
TARGET_RE = re.compile(r"^(?:0x)?([0-9A-Fa-f]+)\b")
RET_MNEMONICS = {"ret", "retq", "retf"}
JMP_MNEMONICS = {"jmp", "jmpq"}


@dataclass(frozen=True)
class Instruction:
    address: int
    raw_bytes: bytes
    mnemonic: str
    operands: str


@dataclass(frozen=True)
class Window:
    name: str
    rva: int
    size: int
    instructions: tuple[Instruction, ...]


@dataclass(frozen=True)
class Edge:
    source_name: str
    source_rva: int
    site_rva: int
    mnemonic: str
    target_rva: int
    target_name: str


def parse_instruction(line: str) -> Instruction | None:
    match = LINE_RE.match(line)
    if not match:
        return None
    address = int(match.group(1), 16)
    tokens = match.group(2).split()
    raw_tokens: list[str] = []
    while tokens and BYTE_RE.fullmatch(tokens[0]):
        raw_tokens.append(tokens.pop(0))
    if not tokens:
        return None
    mnemonic = tokens.pop(0).lower()
    return Instruction(address, bytes.fromhex(" ".join(raw_tokens)),
                       mnemonic, " ".join(tokens))


def parse_windows(text: str) -> list[Window]:
    windows: list[Window] = []
    current_name: str | None = None
    current_rva = 0
    current_size = 0
    current_instructions: list[Instruction] = []

    def finish() -> None:
        if current_name is None:
            return
        ordered = sorted(current_instructions, key=lambda instruction: instruction.address)
        if not ordered or ordered[0].address != current_rva:
            raise ValueError(f"window {current_name} does not start with an instruction at its RVA")
        for instruction in ordered:
            if not current_rva <= instruction.address < current_rva + current_size:
                raise ValueError(f"instruction 0x{instruction.address:X} is outside window {current_name}")
        windows.append(Window(current_name, current_rva, current_size, tuple(ordered)))

    for line in text.splitlines():
        header = HEADER_RE.match(line.strip())
        if header:
            finish()
            current_name = header.group(1).strip()
            current_rva = int(header.group(2), 16)
            current_size = int(header.group(3), 16)
            if current_size == 0:
                raise ValueError(f"window {current_name} has zero size")
            current_instructions = []
            continue
        if current_name is not None:
            instruction = parse_instruction(line)
            if instruction:
                current_instructions.append(instruction)
    finish()
    if not windows:
        raise ValueError("no disassembly windows found")
    starts = [window.rva for window in windows]
    if len(starts) != len(set(starts)):
        raise ValueError("duplicate disassembly window start RVA")
    return windows


def direct_target(instruction: Instruction) -> int | None:
    if instruction.mnemonic not in {"call", "callq", "jmp", "jmpq"}:
        return None
    match = TARGET_RE.match(instruction.operands)
    return int(match.group(1), 16) if match else None


def contiguous_prefix(window: Window, limit: int = 32) -> bytes:
    result = bytearray()
    expected_address = window.rva
    for instruction in window.instructions:
        if instruction.address != expected_address or not instruction.raw_bytes:
            break
        result.extend(instruction.raw_bytes)
        expected_address += len(instruction.raw_bytes)
        if len(result) >= limit:
            break
    return bytes(result[:limit])


def verify_included_anchors(windows: list[Window],
                            candidates: list[Candidate]) -> dict[str, str]:
    by_rva = {window.rva: window for window in windows}
    status: dict[str, str] = {}
    for candidate in candidates:
        if candidate.confirmed_bytes is None:
            continue
        window = by_rva.get(candidate.rva)
        if window is None:
            status[candidate.name] = "no incluido en el desensamblado recibido"
            continue
        prefix = contiguous_prefix(window, len(candidate.confirmed_bytes))
        if prefix != candidate.confirmed_bytes:
            raise ValueError(f"el prefijo recibido no coincide con el anclaje conocido: {candidate.name}")
        status[candidate.name] = "coincide con la firma PS4Debug registrada"
    return status


def _body_instructions(window: Window, candidate_rvas: list[int]) -> list[Instruction]:
    """Stop at the next known method RVA, ret, or an external tail jump."""
    end = window.rva + window.size
    later = [rva for rva in candidate_rvas
             if window.rva < rva < end]
    if later:
        end = min(end, min(later))
    body: list[Instruction] = []
    for instruction in window.instructions:
        if instruction.address >= end:
            break
        body.append(instruction)
        if instruction.mnemonic in RET_MNEMONICS:
            break
        if instruction.mnemonic in JMP_MNEMONICS:
            target = direct_target(instruction)
            if target is None or not window.rva <= target < end:
                break
    return body


def build_edges(windows: list[Window], candidates: list[Candidate]) -> list[Edge]:
    candidate_names: dict[int, list[str]] = {}
    for candidate in candidates:
        candidate_names.setdefault(candidate.rva, []).append(candidate.name)
    section_names = {window.rva: window.name for window in windows}
    all_starts = sorted(set(candidate_names) | set(section_names))
    edges: list[Edge] = []
    for window in windows:
        body = _body_instructions(window, all_starts)
        source_names = candidate_names.get(window.rva, [window.name])
        for instruction in body:
            target = direct_target(instruction)
            if target is None or target not in candidate_names and target not in section_names:
                continue
            target_names = candidate_names.get(target, [section_names[target]])
            for source_name in source_names:
                for target_name in target_names:
                    edges.append(Edge(source_name, window.rva, instruction.address,
                                      instruction.mnemonic, target, target_name))
    return edges


def _entry_behavior(window: Window, candidate_rvas: list[int]) -> str:
    body = _body_instructions(window, candidate_rvas)
    if body and body[0].mnemonic in RET_MNEMONICS:
        return "ret inmediato; sin cuerpo de método en este build"
    return "cuerpo no trivial o ventana parcial; no se infiere límite exacto"


def render_report(source: Path, windows: list[Window],
                  candidates: list[Candidate]) -> str:
    anchor_status = verify_included_anchors(windows, candidates)
    edges = build_edges(windows, candidates)
    candidate_rvas = sorted({candidate.rva for candidate in candidates})
    by_start = {window.rva: window for window in windows}
    output = [
        "# Findings from supplied PS4 IL2CPP disassembly windows",
        "",
        f"- Input: `{source.name}`; bounded windows parsed: `{len(windows)}`.",
        "- Read-only text analysis. The input is not executed or uploaded; no game binary is needed.",
        "- Windows are not assumed to be exact function extents. Direct call/jump edges are emitted only before a visible `ret`, tail jump, or next known candidate RVA.",
        "",
        "## Included hardware-confirmed anchors",
        "",
        "| Method | Status |",
        "| --- | --- |",
    ]
    for name, status in sorted(anchor_status.items()):
        output.append(f"| `{name}` | {status} |")
    output.extend([
        "",
        "## Direct edges between known methods/windows",
        "",
        "| Source | Site RVA | Instruction | Target |",
        "| --- | ---: | --- | --- |",
    ])
    if edges:
        for edge in sorted(edges, key=lambda item: (item.source_rva, item.site_rva,
                                                     item.target_rva, item.mnemonic)):
            output.append(
                f"| `{edge.source_name}` | `0x{edge.site_rva:08X}` | "
                f"`{edge.mnemonic}` | `{edge.target_name}` (`0x{edge.target_rva:08X}`) |"
            )
    else:
        output.append("| — | — | — | No direct edges between parsed method starts |")
    output.extend([
        "",
        "## Entry and ABI observations",
        "",
        "| Window | RVA | Observed entry behavior |",
        "| --- | ---: | --- |",
    ])
    for window in windows:
        entry = _entry_behavior(window, candidate_rvas)
        output.append(f"| `{window.name}` | `0x{window.rva:08X}` | {entry} |")

    output.extend([
        "",
        "## Limits",
        "",
        "- This parser does not identify unnamed callees, imports, vtables, Unity API symbols, or ScePad ownership.",
        "- An x86-64 register pattern is evidence about argument flow, not a complete IL2CPP prototype or proof that a call is safe.",
        "- The report has selected windows only; it cannot establish a complete incoming xref graph or prove a callback is invoked at runtime.",
        "- No hook, Unity API call, framebuffer access, or controller read is implemented by this tool.",
        "",
    ])
    return "\n".join(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disassembly", type=Path,
                        help="private local text disassembly; never copied or uploaded")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE,
                        help="checked-in candidate table (default: repository evidence)")
    parser.add_argument("--output", type=Path,
                        help="write summary here; default is stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        windows = parse_windows(args.disassembly.read_text(encoding="utf-8"))
        candidates = parse_evidence(args.evidence)
        report = render_report(args.disassembly, windows, candidates)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
        return 0
    except (OSError, ValueError) as exc:
        print(f"analyze-disassembly-report: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
