#!/usr/bin/env python3
"""Build an instruction-level CFG report for a private IL2CPP method window.

The input disassembly, method map, and optional annotations are read locally.
This tool never executes or modifies game code and does not treat an RVA as a
valid call target. It reports incomplete edges when the supplied window ends.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_disassembly_report import (  # noqa: E402
    Instruction,
    Window,
    direct_target,
    parse_windows,
)
from resolve_il2cpp_references import (  # noqa: E402
    DEFAULT_EVIDENCE,
    DEFAULT_PRIOR,
    DEFAULT_RESOLVED,
    load_symbols,
    parse_full_image_disassembly,
)

DESTROY_RVA = 0x02176930
CONDITIONAL_BRANCHES = {
    "ja", "jae", "jb", "jbe", "jc", "jcxz", "jecxz", "jrcxz", "je", "jg",
    "jge", "jl", "jle", "jna", "jnae", "jnb", "jnbe", "jnc", "jne", "jng",
    "jnge", "jnl", "jnle", "jno", "jnp", "jns", "jnz", "jo", "jp", "jpe",
    "jpo", "js", "jz",
}
RET_MNEMONICS = {"ret", "retq", "retf"}
BRANCH_TARGET_RE = re.compile(r"^(?:0x)?([0-9A-Fa-f]+)\b")
ANNOTATION_RE = re.compile(r"^(0x[0-9A-Fa-f]+)=(.+?)\s*$")


@dataclass(frozen=True)
class FlowEdge:
    source: int
    target: int
    kind: str


@dataclass(frozen=True)
class Sink:
    rva: int
    name: str
    kind: str


@dataclass(frozen=True)
class GuardPath:
    branch_rva: int
    branch_mnemonic: str
    flag_expression: str
    sink_name: str
    route: str
    destination: int | None


@dataclass(frozen=True)
class ControlFlowGraph:
    instructions: tuple[Instruction, ...]
    edges: tuple[FlowEdge, ...]
    external_branches: tuple[tuple[int, int | None, str], ...]
    fallthrough_gaps: tuple[tuple[int, int], ...]
    open_end: bool


def _branch_target(instruction: Instruction) -> int | None:
    target = direct_target(instruction)
    if target is not None:
        return target
    match = BRANCH_TARGET_RE.match(instruction.operands)
    return int(match.group(1), 16) if match else None


def _contiguous_next(instruction: Instruction,
                     address_map: dict[int, Instruction]) -> int | None:
    if not instruction.raw_bytes:
        return None
    next_rva = instruction.address + len(instruction.raw_bytes)
    return next_rva if next_rva in address_map else None


def build_cfg(window: Window, end_rva: int | None = None) -> ControlFlowGraph:
    """Build conservative instruction-level edges from direct x86 branches."""
    end = window.rva + window.size if end_rva is None else min(end_rva, window.rva + window.size)
    instructions = tuple(item for item in window.instructions
                         if window.rva <= item.address < end)
    address_map = {item.address: item for item in instructions}
    edges: list[FlowEdge] = []
    external: list[tuple[int, int, str]] = []
    gaps: list[tuple[int, int]] = []
    for index, instruction in enumerate(instructions):
        next_rva = _contiguous_next(instruction, address_map)
        mnemonic = instruction.mnemonic.lower()
        if mnemonic in CONDITIONAL_BRANCHES:
            target = _branch_target(instruction)
            if target is not None:
                if target in address_map:
                    edges.append(FlowEdge(instruction.address, target,
                                          f"taken {mnemonic}"))
                else:
                    external.append((instruction.address, target, f"taken {mnemonic}"))
            else:
                external.append((instruction.address, None,
                                 f"taken {mnemonic}; target unresolved"))
            if next_rva is not None:
                edges.append(FlowEdge(instruction.address, next_rva,
                                      f"fallthrough {mnemonic}"))
            elif index + 1 < len(instructions):
                gaps.append((instruction.address, instructions[index + 1].address))
        elif mnemonic in {"jmp", "jmpq"}:
            target = _branch_target(instruction)
            if target is not None:
                if target in address_map:
                    edges.append(FlowEdge(instruction.address, target, "jump"))
                else:
                    external.append((instruction.address, target, "jump"))
            else:
                external.append((instruction.address, None, "indirect jump; target unresolved"))
        elif mnemonic in RET_MNEMONICS:
            continue
        elif next_rva is not None:
            edges.append(FlowEdge(instruction.address, next_rva,
                                  "call-return" if mnemonic in {"call", "callq"} else "next"))
        elif index + 1 < len(instructions):
            gaps.append((instruction.address, instructions[index + 1].address))
    open_end = bool(instructions and instructions[-1].mnemonic.lower() not in
                    RET_MNEMONICS | {"jmp", "jmpq"})
    return ControlFlowGraph(instructions, tuple(edges), tuple(external),
                            tuple(gaps), open_end)


def _reachable(start: int, destinations: set[int],
               edges_by_source: dict[int, list[FlowEdge]]) -> bool:
    pending = deque([start])
    visited: set[int] = set()
    while pending:
        current = pending.popleft()
        if current in destinations:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(edge.target for edge in edges_by_source.get(current, []))
    return False


def _validate_store(instruction: Instruction) -> bool:
    if not instruction.mnemonic.lower().startswith("mov"):
        return False
    destination = instruction.operands.split(",", 1)[0].lower()
    return "ptr [" in destination or destination.startswith("[")


def _parse_annotations(entries: list[str] | None) -> dict[int, str]:
    result: dict[int, str] = {}
    for entry in entries or []:
        match = ANNOTATION_RE.match(entry)
        if not match:
            raise ValueError("annotations must use 0xRVA=label")
        rva_text, label = match.groups()
        result[int(rva_text, 16)] = label
    return result


def _nearest_flag_writer(instructions: tuple[Instruction, ...], index: int) -> str:
    for instruction in reversed(instructions[max(0, index - 5):index]):
        if instruction.mnemonic.lower() in {"cmp", "test", "comiss", "ucomiss", "comisd", "ucomisd"}:
            return f"{instruction.mnemonic} {instruction.operands}".strip()
        if instruction.mnemonic.lower() in {"add", "sub", "and", "or", "xor", "inc", "dec", "call", "callq"}:
            return "flag source not resolved in this block"
    return "flag source not resolved in this block"


def _instruction_map(cfg: ControlFlowGraph) -> dict[int, Instruction]:
    return {instruction.address: instruction for instruction in cfg.instructions}


def analyze_window(window: Window, symbols: dict[int, set[str]],
                   store_sites: dict[int, str] | None = None,
                   annotations: dict[int, str] | None = None,
                   end_rva: int | None = None) -> tuple[ControlFlowGraph, list[Sink], list[GuardPath]]:
    store_sites = store_sites or {}
    annotations = annotations or {}
    cfg = build_cfg(window, end_rva)
    sinks: list[Sink] = []
    instruction_map = _instruction_map(cfg)
    for instruction in cfg.instructions:
        target = direct_target(instruction)
        if instruction.mnemonic.lower() in {"call", "callq", "jmp", "jmpq"} and target is not None:
            names = symbols.get(target, set())
            if target == DESTROY_RVA or any(name.endswith("Object.Destroy") for name in names):
                sinks.append(Sink(instruction.address, "UnityEngine.Object.Destroy", "call"))
    for site_rva, label in store_sites.items():
        instruction = instruction_map.get(site_rva)
        if instruction is None:
            raise ValueError(f"annotated store site 0x{site_rva:X} is outside the selected method window")
        if not _validate_store(instruction):
            raise ValueError(f"annotated store site 0x{site_rva:X} is not a recognizable memory-destination MOV")
        sinks.append(Sink(site_rva, label, "store"))

    edges_by_source: dict[int, list[FlowEdge]] = {}
    for edge in cfg.edges:
        edges_by_source.setdefault(edge.source, []).append(edge)
    guards: list[GuardPath] = []
    incomplete = bool(cfg.fallthrough_gaps or cfg.external_branches or cfg.open_end)
    for index, instruction in enumerate(cfg.instructions):
        if instruction.mnemonic.lower() not in CONDITIONAL_BRANCHES:
            continue
        # Any internal instruction gap can hide a fallthrough route. In a
        # partial CFG, do not turn an omitted path into an unreachable claim.
        if incomplete:
            continue
        outgoing = edges_by_source.get(instruction.address, [])
        for sink in sinks:
            destinations = {sink.rva}
            taken = next((edge for edge in outgoing if edge.kind.startswith("taken")), None)
            fallthrough = next((edge for edge in outgoing if edge.kind.startswith("fallthrough")), None)
            taken_reaches = taken is not None and _reachable(taken.target, destinations, edges_by_source)
            fallthrough_reaches = fallthrough is not None and _reachable(fallthrough.target, destinations, edges_by_source)
            if taken_reaches == fallthrough_reaches:
                continue
            route = "taken" if taken_reaches else "fallthrough"
            destination = (taken.target if taken_reaches and taken else
                           fallthrough.target if fallthrough_reaches and fallthrough else None)
            flag_expression = annotations.get(
                instruction.address,
                annotations.get(instruction.address - 1,
                                _nearest_flag_writer(cfg.instructions, index)))
            guards.append(GuardPath(instruction.address,
                                    instruction.mnemonic.lower(), flag_expression,
                                    sink.name, route, destination))
    return cfg, sinks, guards


def _window_source_name(window: Window, symbols: dict[int, set[str]]) -> str:
    names = symbols.get(window.rva)
    return ", ".join(sorted(names)) if names else window.name


def render_report(source: Path, window: Window, symbols: dict[int, set[str]],
                  store_sites: dict[int, str], annotations: dict[int, str],
                  end_rva: int | None = None) -> str:
    cfg, sinks, guards = analyze_window(window, symbols, store_sites,
                                        annotations, end_rva)
    incomplete = bool(cfg.fallthrough_gaps or cfg.external_branches or cfg.open_end)
    edges_by_source: dict[int, list[FlowEdge]] = {}
    for edge in cfg.edges:
        edges_by_source.setdefault(edge.source, []).append(edge)
    lines = [
        "# Offline IL2CPP method control-flow report",
        "",
        f"- Input: `{source.name}`; method: `{_window_source_name(window, symbols)}` (`0x{window.rva:08X}`).",
        "- This is an instruction-level CFG from a private bounded window. Only in-window direct edges are followed.",
        "- No code, flags, objects, or game memory are modified or executed.",
        "",
        "## Direct control-flow edges",
        "",
        "| Block/branch RVA | Edge | Target RVA |", "| ---: | --- | ---: |",
    ]
    for source_rva, successors in sorted(edges_by_source.items()):
        instruction = next(item for item in cfg.instructions if item.address == source_rva)
        if instruction.mnemonic.lower() in CONDITIONAL_BRANCHES | {"jmp", "jmpq"}:
            for edge in successors:
                lines.append(f"| `0x{source_rva:08X}` | {edge.kind} | `0x{edge.target:08X}` |")
    if not any(instruction.mnemonic.lower() in CONDITIONAL_BRANCHES | {"jmp", "jmpq"}
               for instruction in cfg.instructions):
        lines.append("| — | no direct branch in supplied window | — |")

    lines.extend(["", "## Lifecycle sinks", "",
                  "| Site RVA | Kind | Sink | Reachable from method entry |", "| ---: | --- | --- | --- |"])
    reachable_from_entry: set[int] = set()
    if cfg.instructions:
        pending = deque([cfg.instructions[0].address])
        while pending:
            current = pending.popleft()
            if current in reachable_from_entry:
                continue
            reachable_from_entry.add(current)
            pending.extend(edge.target for edge in edges_by_source.get(current, []))
    for sink in sinks:
        state = "yes" if sink.rva in reachable_from_entry else "not proven in this window"
        lines.append(f"| `0x{sink.rva:08X}` | {sink.kind} | `{sink.name}` | {state} |")
    if not sinks:
        lines.append("| — | — | no Destroy call or annotated store site | — |")

    lines.extend(["", "## Branches that select a sink path", "",
                  "| Branch RVA | Condition instruction/annotation | Sink | Path | Next RVA |",
                  "| ---: | --- | --- | --- | ---: |"])
    for guard in guards:
        lines.append(f"| `0x{guard.branch_rva:08X}` `{guard.branch_mnemonic}` | `{guard.flag_expression}` | "
                     f"`{guard.sink_name}` | {guard.route} | `{_fmt(guard.destination)}` |")
    if not guards:
        reason = ("branch guard withheld: incomplete CFG (see unresolved edges/gaps/open end)"
                  if incomplete else
                  "no branch has a unique in-window route to a sink")
        lines.append(f"| — | {reason} | — | — | — |")

    lines.extend(["", "## Missing instruction adjacency", "",
                  "| Site RVA | Next supplied instruction |", "| ---: | ---: |"])
    if cfg.fallthrough_gaps:
        for site, next_rva in cfg.fallthrough_gaps:
            lines.append(f"| `0x{site:08X}` | `0x{next_rva:08X}` |")
    else:
        lines.append("| — | — | no internal disassembly gap detected |")
    end_state = ("open; final supplied instruction is not ret/jmp"
                 if cfg.open_end else
                 "terminal ret/jmp observed")
    lines.append(f"\n- Window end: {end_state}.")

    lines.extend(["", "## Unresolved edges and limits", "",
                  "| Site RVA | Unresolved target | Kind |", "| ---: | ---: | --- |"])
    if cfg.external_branches:
        for site, target, kind in cfg.external_branches:
            lines.append(f"| `0x{site:08X}` | `{_fmt(target)}` | {kind}; target is outside the supplied window or unresolved |")
    else:
        lines.append("| — | — | no direct branch leaves this window |")
    lines.extend([
        "",
        "- A target outside the window is not treated as reachable or unreachable; provide the callee/continuation window to extend the graph.",
        "- Guard attribution is withheld whenever the CFG has an unresolved branch, an internal gap, or an open window end.",
        "- Store annotations identify a site supplied by the analyst; the tool verifies only that it is a memory-destination MOV.",
        "- Guard labels and metadata field names are not inferred from register use. Supply evidence-backed annotations when necessary.",
        "- Window completeness, method boundaries, native ABI, runtime callback execution, and object lifetime remain separate validation questions.",
        "",
    ])
    return "\n".join(lines)


def _fmt(rva: int | None) -> str:
    return "—" if rva is None else f"0x{rva:08X}"


def _parse_named_rvas(entries: list[str] | None) -> dict[int, str]:
    return _parse_annotations(entries)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disassembly", type=Path,
                        help="private local disassembly with bounded method windows")
    parser.add_argument("--method-rva", required=True, type=lambda value: int(value, 0),
                        help="exact method RVA to analyze")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--resolved", type=Path, default=DEFAULT_RESOLVED)
    parser.add_argument("--prior", type=Path, default=DEFAULT_PRIOR)
    parser.add_argument("--symbols", type=Path,
                        help="optional local method map: 0xRVA Fully.Qualified.Method")
    parser.add_argument("--store-site", action="append", default=[],
                        help="annotate a verified store instruction as 0xRVA=Field.Name")
    parser.add_argument("--condition", action="append", default=[],
                        help="annotate a conditional branch as 0xRVA=Guard.Name")
    parser.add_argument("--raw-size", type=lambda value: int(value, 0),
                        help="window byte size when input is raw llvm-objdump output without method headers")
    parser.add_argument("--output", type=Path,
                        help="write Markdown report locally; default is stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_text = args.disassembly.read_text(encoding="utf-8")
        try:
            windows = parse_windows(input_text)
        except ValueError:
            if args.raw_size is None:
                raise
            symbols, _ = load_symbols(args.evidence, args.resolved,
                                      args.prior, args.symbols)
            parsed = tuple(instruction for instruction in parse_full_image_disassembly(input_text)
                           if args.method_rva <= instruction.address < args.method_rva + args.raw_size)
            if not parsed or parsed[0].address != args.method_rva:
                raise ValueError(f"raw disassembly has no instruction at method RVA 0x{args.method_rva:X}")
            name = ", ".join(sorted(symbols.get(args.method_rva, set()))) or "raw method window"
            windows = [Window(name, args.method_rva, args.raw_size, parsed)]
        window = next((item for item in windows if item.rva == args.method_rva), None)
        if window is None:
            raise ValueError(f"no supplied method window starts at RVA 0x{args.method_rva:X}")
        symbols, _ = load_symbols(args.evidence, args.resolved,
                                  args.prior, args.symbols)
        symbols.setdefault(DESTROY_RVA, set()).add("UnityEngine.Object.Destroy")
        # Store only method names in the symbol map. This line provides the
        # destructive sink RVA even if the resolved helper table is partial.
        store_sites = _parse_named_rvas(args.store_site)
        annotations = _parse_named_rvas(args.condition)
        report = render_report(args.disassembly, window, symbols,
                               store_sites, annotations)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
        return 0
    except (OSError, ValueError) as exc:
        print(f"analyze-il2cpp-lifecycle: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
