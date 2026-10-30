#!/usr/bin/env python3
"""Resolve method references from private, bounded PS4 IL2CPP disassembly.

The input is read locally and is never copied into the repository or uploaded.
This tool reports only references visible in the supplied windows. It does not
infer that a callback is active, resolve an indirect call without a mapping,
or execute/patch game code.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_disassembly_report import (  # noqa: E402
    Instruction,
    Window,
    direct_target,
    parse_instruction,
    parse_windows,
)
from analyze_ps4_il2cpp_candidates import (  # noqa: E402
    DEFAULT_EVIDENCE,
    parse_evidence,
)

DEFAULT_RESOLVED = ROOT / "docs/PS4_IL2CPP_OFFLINE_RESOLVED.md"
DEFAULT_PRIOR = ROOT / "docs/PS4_IL2CPP_PRIOR_EVIDENCE.md"
RESOLVED_ROW_RE = re.compile(r"^\|\s*`(0x[0-9A-Fa-f]+)`\s*\|\s*`([^`]+)`\s*\|")
RIP_COMMENT_RE = re.compile(r"\[rip(?:\s*[+-]\s*(?:0x)?[0-9a-f]+)?\].*?#\s*(?:0x)?([0-9a-f]+)", re.I)
EXTRA_SYMBOL_RE = re.compile(r"^(0x[0-9A-Fa-f]+)\s+(.+?)\s*$")
TYPE_SYMBOL_RE = re.compile(r"^(0x[0-9A-Fa-f]+)\s+(.+?)\s*$")
BRANCH_TARGET_RE = re.compile(r"^(?:0x)?([0-9A-Fa-f]+)\b")
BRANCH_MNEMONICS = {"jmp", "jmpq", "je", "jz", "jne", "jnz", "ja", "jae",
                     "jb", "jbe", "jc", "jcxz", "jecxz", "jrcxz", "jg",
                     "jge", "jl", "jle", "jna", "jnae", "jnb", "jnbe",
                     "jnc", "jng", "jnge", "jnl", "jnle", "jno", "jnp",
                     "jns", "jnz", "jo", "jp", "jpe", "jpo", "js"}
METHODS_OF_INTEREST = (
    "TheForest.DebugConsole.Awake",
    "TheForest.DebugConsole.OnDestroy",
    "TheForest.DebugConsole.GetInstance",
    "TheForest.DebugConsole.ShowConsole",
    "TheForest.DebugConsole.OnGUI",
    "PS4Controller.ProcessGamePads",
    "Rewired.ReInput.get_players",
)


@dataclass(frozen=True)
class Symbol:
    name: str
    rva: int
    provenance: str


@dataclass(frozen=True)
class Reference:
    source_name: str
    source_rva: int
    site_rva: int
    kind: str
    target_rva: int | None
    target_names: tuple[str, ...]
    detail: str


def _add_symbol(symbols: dict[int, set[str]], provenance: dict[int, set[str]],
                rva: int, name: str, source: str) -> None:
    symbols.setdefault(rva, set()).add(name)
    provenance.setdefault(rva, set()).add(source)


def load_symbols(evidence: Path = DEFAULT_EVIDENCE,
                 resolved: Path = DEFAULT_RESOLVED,
                 prior: Path = DEFAULT_PRIOR,
                 extra: Path | None = None) -> tuple[dict[int, set[str]], dict[int, set[str]]]:
    """Load method names already resolved from metadata, without game binaries."""
    symbols: dict[int, set[str]] = {}
    provenance: dict[int, set[str]] = {}
    for candidate in parse_evidence(evidence):
        _add_symbol(symbols, provenance, candidate.rva, candidate.name,
                    "candidate table; offline prefix evidence")

    for line in resolved.read_text(encoding="utf-8").splitlines():
        match = RESOLVED_ROW_RE.match(line)
        if match:
            rva_text, name = match.groups()
            _add_symbol(symbols, provenance, int(rva_text, 16), name,
                        "resolved helper table")

    # These two Unity API names are joined from the PS4 disassembly's direct
    # targets and the resolved OnGUI callsite table in the checked-in report.
    _add_symbol(symbols, provenance, 0x019BD860,
                "UnityEngine.GUI.get_color", "PS4 OnGUI callsite table")
    _add_symbol(symbols, provenance, 0x019BC470,
                "UnityEngine.GUIUtility.CheckOnGUI", "PS4 OnGUI callsite table")

    # This DebugConsole entry is recorded in the prior PS4 evidence, but it
    # was not part of the set of 42 candidate rows.
    prior_text = prior.read_text(encoding="utf-8")
    awake = re.search(r"DebugConsole\.Awake` RVA `?(0x[0-9A-Fa-f]+)", prior_text)
    if awake:
        _add_symbol(symbols, provenance, int(awake.group(1), 16),
                    "TheForest.DebugConsole.Awake", "prior PS4 evidence")

    if extra is not None:
        for line_number, raw_line in enumerate(extra.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = EXTRA_SYMBOL_RE.match(line)
            if not match:
                raise ValueError(f"invalid extra symbol on line {line_number}; expected '0xRVA Name'")
            rva_text, name = match.groups()
            _add_symbol(symbols, provenance, int(rva_text, 16), name,
                        f"user-supplied local symbol map:{line_number}")
    return symbols, provenance


def _window_symbol(window: Window, symbols: dict[int, set[str]]) -> str:
    names = symbols.get(window.rva)
    return ", ".join(sorted(names)) if names else window.name


def _rip_data_target(instruction: Instruction) -> int | None:
    match = RIP_COMMENT_RE.search(instruction.operands)
    return int(match.group(1), 16) if match else None


def _data_access_kind(instruction: Instruction) -> str:
    operands = instruction.operands.split(",", 1)
    first = operands[0].strip().lower() if operands else ""
    if instruction.mnemonic.startswith("lea"):
        return "address-of"
    if "[rip" in first:
        if instruction.mnemonic.startswith(("mov", "stos")):
            return "write"
        if instruction.mnemonic.startswith(("xchg", "add", "sub", "and", "or", "xor", "inc", "dec")):
            return "read-modify-write"
    return "read"


def load_type_symbols(path: Path | None) -> dict[int, set[str]]:
    """Load local mappings from a native IL2CPP type-reference slot RVA to type name."""
    result: dict[int, set[str]] = {}
    if path is None:
        return result
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = TYPE_SYMBOL_RE.match(line)
        if not match:
            raise ValueError(f"invalid type map on line {line_number}; expected '0xRVA Namespace.Type'")
        rva_text, type_name = match.groups()
        result.setdefault(int(rva_text, 16), set()).add(type_name)
    return result


def _indirect_call_detail(window: Window, instruction_index: int,
                          type_symbols: dict[int, set[str]]) -> str:
    instruction = window.instructions[instruction_index]
    detail = instruction.operands
    if instruction.mnemonic not in {"call", "callq"}:
        return detail
    if "[rcx]" not in instruction.operands.lower():
        return detail
    lookback = window.instructions[max(0, instruction_index - 64):instruction_index]
    has_interface_vtable_entry = any(
        item.mnemonic.startswith("lea")
        and "[rax + rcx + 0x110]" in item.operands.lower()
        for item in lookback
    )
    has_method_info_slot = any(
        item.mnemonic.startswith("mov")
        and item.operands.lower().replace(" ", "").startswith("rsi,qwordptr[rcx+0x8]")
        for item in lookback
    )
    if not (has_interface_vtable_entry and has_method_info_slot):
        return detail

    type_ref = None
    for item in reversed(lookback):
        if (item.mnemonic.startswith("mov")
                and item.operands.lower().replace(" ", "").startswith("rsi,qwordptr[rip")
                and (target := _rip_data_target(item)) is not None):
            type_ref = target
            break
    if type_ref is None:
        return "IL2CPP interface/vtable dispatch; interface type reference not present in this window"
    names = type_symbols.get(type_ref, set())
    type_label = ", ".join(sorted(names)) if names else "unresolved metadata type"
    return f"IL2CPP interface/vtable dispatch; type-ref slot 0x{type_ref:08X} ({type_label})"


def resolve_references(windows: list[Window], symbols: dict[int, set[str]],
                       type_symbols: dict[int, set[str]] | None = None) -> list[Reference]:
    references: list[Reference] = []
    type_symbols = type_symbols or {}
    method_starts = sorted(set(symbols) | {window.rva for window in windows})
    for window in windows:
        source_name = _window_symbol(window, symbols)
        end_rva = window.rva + window.size
        later_methods = [rva for rva in method_starts
                         if window.rva < rva < end_rva]
        if later_methods:
            end_rva = min(later_methods)
        for instruction_index, instruction in enumerate(window.instructions):
            if instruction.address >= end_rva:
                continue
            target = direct_target(instruction)
            if instruction.mnemonic in {"call", "callq", "jmp", "jmpq"}:
                if target is None:
                    references.append(Reference(source_name, window.rva,
                                                instruction.address, "indirect call/jump",
                                                None, (), _indirect_call_detail(
                                                    window, instruction_index, type_symbols)))
                else:
                    names = tuple(sorted(symbols.get(target, set())))
                    references.append(Reference(source_name, window.rva,
                                                instruction.address, "direct call/jump",
                                                target, names, instruction.mnemonic))
            elif instruction.mnemonic in BRANCH_MNEMONICS:
                branch_target = target
                if branch_target is None:
                    match = BRANCH_TARGET_RE.match(instruction.operands)
                    branch_target = int(match.group(1), 16) if match else None
                if branch_target is not None:
                    references.append(Reference(source_name, window.rva,
                                                instruction.address, "branch",
                                                branch_target, tuple(sorted(symbols.get(branch_target, set()))),
                                                instruction.mnemonic))
            data_target = _rip_data_target(instruction)
            if data_target is not None:
                references.append(Reference(source_name, window.rva,
                                            instruction.address, "rip-relative data",
                                            data_target, (),
                                            f"{_data_access_kind(instruction)}: {instruction.mnemonic} {instruction.operands}"))
    return references


def parse_full_image_disassembly(text: str) -> list[Instruction]:
    """Parse a raw objdump text stream without assigning guessed caller names."""
    return [instruction for line in text.splitlines()
            if (instruction := parse_instruction(line)) is not None]


def resolve_full_image_xrefs(instructions: list[Instruction],
                              symbols: dict[int, set[str]]) -> list[Reference]:
    """Find direct call/jump sites targeting any known method RVA."""
    references: list[Reference] = []
    for instruction in instructions:
        target = direct_target(instruction)
        if target is None or target not in symbols:
            continue
        references.append(Reference("caller unresolved in symbol map", 0,
                                    instruction.address, "incoming direct xref",
                                    target, tuple(sorted(symbols[target])),
                                    instruction.mnemonic))
    return references


def render_full_image_report(source: Path, instructions: list[Instruction],
                             symbols: dict[int, set[str]]) -> str:
    references = resolve_full_image_xrefs(instructions, symbols)
    lines = [
        "# Full-module IL2CPP direct xrefs — offline scan",
        "",
        f"- Input: `{source.name}`; parsed instructions: {len(instructions)}.",
        "- The input is assumed to be a complete module disassembly supplied locally; this tool cannot verify its completeness or module identity.",
        "- Caller names are intentionally left unresolved unless a separate function-boundary map is available.",
        "- Only direct `call`/`jmp` sites whose targets match known method RVAs are emitted. Indirect dispatch is not guessed.",
        "",
        "## Incoming references to known method RVAs",
        "",
        "| Target method | Target RVA | Callsite RVA | Operation |",
        "| --- | ---: | ---: | --- |",
    ]
    if references:
        for ref in sorted(references, key=lambda item: (item.target_rva or 0,
                                                         item.site_rva)):
            for name in ref.target_names:
                lines.append(f"| `{name}` | `0x{ref.target_rva:08X}` | "
                             f"`0x{ref.site_rva:08X}` | {ref.detail} |")
    else:
        lines.append("| — | — | — | no direct references to known methods in parsed input |")
    lines.extend([
        "",
        "## Limits",
        "",
        "- An empty result does not prove a method has no callers: the dump may be incomplete, indirect, or use a different address domain.",
        "- A caller site does not prove the call executes at runtime.",
        "- This scan does not resolve RIP-relative data fields, function ABI, vtables, callbacks, or live Unity object state.",
        "- No original disassembly lines or bytes are copied into this report; no game code is executed or modified.",
        "",
    ])
    return "\n".join(lines)


def _fmt_rva(rva: int | None) -> str:
    return "—" if rva is None else f"0x{rva:08X}"


def render_report(source: Path, windows: list[Window],
                  symbols: dict[int, set[str]],
                  provenance: dict[int, set[str]],
                  type_symbols: dict[int, set[str]] | None = None) -> str:
    references = resolve_references(windows, symbols, type_symbols)
    names_at_start = {window.rva: _window_symbol(window, symbols) for window in windows}
    lines = [
        "# Offline IL2CPP reference map — bounded windows",
        "",
        f"- Input: `{source.name}`; windows parsed: {len(windows)}.",
        "- The private input is read locally; this report does not include its instructions or binary data.",
        "- Coverage is limited to the supplied windows. Missing edges mean ‘not observed here’, not ‘no reference exists’.",
        "- Direct calls/jumps are resolved only when the target RVA has a known method name. Indirect calls remain unresolved unless independently mapped.",
        "",
        "## Requested method coverage",
        "",
        "| Method | RVA | Window supplied | Evidence in this run |",
        "| --- | ---: | --- | --- |",
    ]
    by_name: dict[str, list[int]] = {}
    for rva, names in symbols.items():
        for name in names:
            by_name.setdefault(name, []).append(rva)
    for name in METHODS_OF_INTEREST:
        rvas = sorted(by_name.get(name, []))
        if not rvas:
            lines.append(f"| `{name}` | — | no | method name not in loaded evidence |")
            continue
        for rva in rvas:
            supplied = "yes" if rva in names_at_start else "no"
            lines.append(f"| `{name}` | `{_fmt_rva(rva)}` | {supplied} | "
                         f"{'; '.join(sorted(provenance.get(rva, set())))} |")

    direct = [ref for ref in references if ref.kind == "direct call/jump"]
    lines.extend(["", "## Direct call and jump references", "",
                  "| Source window | Site RVA | Operation | Target RVA | Resolved target |",
                  "| --- | ---: | --- | ---: | --- |"])
    for ref in sorted(direct, key=lambda item: (item.source_rva, item.site_rva)):
        target_names = ", ".join(f"`{name}`" for name in ref.target_names) or "unresolved symbol"
        lines.append(f"| `{ref.source_name}` | `{_fmt_rva(ref.site_rva)}` | {ref.detail} | "
                     f"`{_fmt_rva(ref.target_rva)}` | {target_names} |")
    if not direct:
        lines.append("| — | — | — | — | no direct calls/jumps parsed |")

    indirect = [ref for ref in references if ref.kind == "indirect call/jump"]
    lines.extend(["", "## Indirect call sites requiring a target map", "",
                  "| Source window | Site RVA | Operand |", "| --- | ---: | --- |"])
    for ref in sorted(indirect, key=lambda item: (item.source_rva, item.site_rva)):
        lines.append(f"| `{ref.source_name}` | `{_fmt_rva(ref.site_rva)}` | `{ref.detail}` |")
    if not indirect:
        lines.append("| — | — | no indirect call/jump in supplied windows |")

    branches = [ref for ref in references if ref.kind == "branch"]
    lines.extend(["", "## Conditional branch targets", "",
                  "| Source window | Site RVA | Branch | Target RVA |", "| --- | ---: | --- | ---: |"])
    for ref in sorted(branches, key=lambda item: (item.source_rva, item.site_rva)):
        lines.append(f"| `{ref.source_name}` | `{_fmt_rva(ref.site_rva)}` | {ref.detail} | `{_fmt_rva(ref.target_rva)}` |")
    if not branches:
        lines.append("| — | — | — | — | no branch targets parsed |")

    data = [ref for ref in references if ref.kind == "rip-relative data"]
    lines.extend(["", "## RIP-relative data references", "",
                  "| Source window | Site RVA | Data RVA | Access heuristic |", "| --- | ---: | ---: | --- |"])
    for ref in sorted(data, key=lambda item: (item.source_rva, item.site_rva)):
        lines.append(f"| `{ref.source_name}` | `{_fmt_rva(ref.site_rva)}` | `{_fmt_rva(ref.target_rva)}` | `{ref.detail}` |")
    if not data:
        lines.append("| — | — | — | no annotated RIP-relative references parsed |")

    lines.extend([
        "",
        "## Interpretation limits",
        "",
        "- `call [register]` or `call [object+offset]` has no resolved target in a disassembly window; a vtable/interface map from the matching metadata and receiver type is required.",
        "- RIP-relative data addresses are reported as addresses only. The tool does not label a field as a singleton, infer object lifetime, or decide whether a branch destroys an object.",
        "- Branch targets are a control-flow inventory, not a complete CFG. A complete function body and instruction boundary validation are required to establish branch conditions.",
        "- A compiled Unity callback name does not prove Unity invokes it. This report cannot establish a live component, render-thread context, ABI safety, or input ownership.",
        "- No IL2CPP method is invoked, no game memory is accessed, and no hook/provider is generated.",
        "",
    ])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disassembly", type=Path,
                        help="private local text dump with bounded method windows")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--resolved", type=Path, default=DEFAULT_RESOLVED)
    parser.add_argument("--prior", type=Path, default=DEFAULT_PRIOR)
    parser.add_argument("--symbols", type=Path,
                        help="optional private TSV-like file: '0xRVA Fully.Qualified.Method'")
    parser.add_argument("--types", type=Path,
                        help="optional private TSV-like map: '0xTYPE_REF_SLOT_RVA Fully.Qualified.Type'")
    parser.add_argument("--full-image", action="store_true",
                        help="treat input as a raw complete objdump stream and find incoming direct xrefs")
    parser.add_argument("--output", type=Path,
                        help="write report locally; default is stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_text = args.disassembly.read_text(encoding="utf-8")
        symbols, provenance = load_symbols(args.evidence, args.resolved,
                                           args.prior, args.symbols)
        type_symbols = load_type_symbols(args.types)
        if args.full_image:
            instructions = parse_full_image_disassembly(input_text)
            report = render_full_image_report(args.disassembly, instructions, symbols)
        else:
            windows = parse_windows(input_text)
            report = render_report(args.disassembly, windows, symbols, provenance,
                                   type_symbols)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
        return 0
    except (OSError, ValueError) as exc:
        print(f"resolve-il2cpp-references: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
