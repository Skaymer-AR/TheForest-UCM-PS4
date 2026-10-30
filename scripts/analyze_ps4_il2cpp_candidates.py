#!/usr/bin/env python3
"""Read-only offline analysis of recovered CUSA12398 IL2CPP RVA candidates.

The script reads the checked-in evidence table and, optionally, a private
decrypted ELF64 image. It does not patch or upload files. Runtime addresses
from earlier console sessions are deliberately not accepted as an image base.
"""

from __future__ import annotations

import argparse
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "docs/PS4_IL2CPP_PRIOR_EVIDENCE.md"
FOCUS_METHODS = (
    "PS4Controller.Update",
    "TheForest.UI.VirtualCursor.LateUpdate",
    "TheForest.DebugConsole.OnGUI",
    "TheForest.DebugConsole.ToggleConsole",
    "TheForest.Tools.DllModLoader.Awake",
    "TheForest.Modding.UI.ModList.OnEnable",
)
ELF_MAGIC = b"\x7fELF"
ELFCLASS64 = 2
ELFDATA2LSB = 1
EM_X86_64 = 62
PT_LOAD = 1

TABLE_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*`(0x[0-9A-Fa-f]+)`\s*\|\s*(.*?)\s*\|\s*$"
)
CONFIRMED_BYTES_RE = re.compile(
    r"^-\s*`([^`]+)`:\s*RVA\s+\*\*`(0x[0-9A-Fa-f]+)`\*\*.*?"
    r"first 16 bytes:\s*`([0-9A-Fa-f ]{32,})`"
)
DISASM_RE = re.compile(
    r"^\s*([0-9A-Fa-f]+):\s+(.+?)\s*$"
)
HEX_BYTE_RE = re.compile(r"^[0-9A-Fa-f]{2}$")
IMMEDIATE_RE = re.compile(r"^(?:0x)?([0-9A-Fa-f]+)\b")
ON_GUI_CONFIRMED_PREFIX = bytes.fromhex(
    "55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 E4")
ON_GUI_REL32_STOLEN_PREFIX = bytes.fromhex("55 48 89 E5 41 57")


@dataclass(frozen=True)
class Candidate:
    name: str
    rva: int
    status: str
    confirmed_bytes: bytes | None = None


@dataclass(frozen=True)
class Segment:
    offset: int
    vaddr: int
    filesz: int
    memsz: int
    align: int
    flags: int


@dataclass(frozen=True)
class Instruction:
    address: int
    mnemonic: str
    operands: str


class Elf64Image:
    """Minimal ELF64 reader for x86-64 PT_LOAD address-to-file mapping."""

    def __init__(self, path: Path, image_base: int | None = None):
        self.path = path
        self.segments: list[Segment] = []
        with path.open("rb") as source:
            header = source.read(64)
            if len(header) < 64 or header[:4] != ELF_MAGIC:
                raise ValueError("input is not an ELF file; use a local decrypted ELF/OELF")
            if header[4] != ELFCLASS64 or header[5] != ELFDATA2LSB:
                raise ValueError("expected little-endian ELF64")
            fields = struct.unpack_from("<HHIQQQIHHHHHH", header, 16)
            (self.elf_type, self.machine, _version, _entry, phoff, _shoff,
             _flags, _ehsize, phentsize, phnum, *_rest) = fields
            if self.machine != EM_X86_64:
                raise ValueError(f"expected x86-64 ELF (e_machine 62), got {self.machine}")
            if phentsize < 56:
                raise ValueError("ELF program header entry is smaller than ELF64 standard")
            source.seek(0, 2)
            file_size = source.tell()
            if phoff + phentsize * phnum > file_size:
                raise ValueError("ELF program-header table extends beyond the file")
            source.seek(phoff)
            for _ in range(phnum):
                entry = source.read(phentsize)
                if len(entry) < 56:
                    raise ValueError("truncated ELF program header")
                p_type, p_flags, p_offset, p_vaddr, _paddr, p_filesz, p_memsz, p_align = \
                    struct.unpack_from("<IIQQQQQQ", entry, 0)
                if p_type == PT_LOAD and p_filesz:
                    if p_offset + p_filesz > file_size:
                        raise ValueError("ELF load segment extends beyond the file")
                    self.segments.append(Segment(p_offset, p_vaddr, p_filesz,
                                                 p_memsz, p_align, p_flags))
        if not self.segments:
            raise ValueError("ELF contains no file-backed PT_LOAD segments")
        if image_base is None:
            bases = []
            for segment in self.segments:
                alignment = segment.align if segment.align > 1 else 0x1000
                bases.append(segment.vaddr - (segment.vaddr % alignment))
            self.image_base = min(bases)
            self.image_base_source = "minimum aligned PT_LOAD p_vaddr"
        else:
            if image_base < 0:
                raise ValueError("ELF image base cannot be negative")
            self.image_base = image_base
            self.image_base_source = "explicit --image-base"

    def virtual_address(self, rva: int) -> int:
        return self.image_base + rva

    def file_offset(self, rva: int) -> int | None:
        address = self.virtual_address(rva)
        offsets = {
            segment.offset + address - segment.vaddr
            for segment in self.segments
            if segment.vaddr <= address < segment.vaddr + segment.filesz
        }
        if len(offsets) > 1:
            raise ValueError(f"RVA 0x{rva:X} maps to multiple ELF load segments")
        return next(iter(offsets)) if offsets else None

    def is_executable(self, rva: int) -> bool:
        """Return whether this RVA is in a file-backed PF_X PT_LOAD range."""
        address = self.virtual_address(rva)
        return any(segment.flags & 0x1
                   and segment.vaddr <= address < segment.vaddr + segment.filesz
                   for segment in self.segments)

    def read_rva(self, rva: int, length: int) -> bytes | None:
        offset = self.file_offset(rva)
        if offset is None:
            return None
        with self.path.open("rb") as source:
            source.seek(offset)
            return source.read(length)


def parse_evidence(path: Path) -> list[Candidate]:
    text = path.read_text(encoding="utf-8")
    signature_by_name: dict[str, tuple[int, bytes]] = {}
    for line in text.splitlines():
        match = CONFIRMED_BYTES_RE.match(line)
        if match:
            name, rva_text, byte_text = match.groups()
            signature_by_name[name] = (
                int(rva_text, 16), bytes.fromhex(byte_text)
            )

    candidates: list[Candidate] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| IL2CPP method | RVA | Validation status |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if candidates:
                break
            continue
        match = TABLE_ROW_RE.match(line)
        if not match:
            continue
        name, rva_text, status = match.groups()
        rva = int(rva_text, 16)
        signature = signature_by_name.get(name)
        signature_bytes = None
        if signature:
            sig_rva, signature_bytes = signature
            if sig_rva != rva:
                raise ValueError(f"signature RVA disagrees with table for {name}")
        candidates.append(Candidate(name, rva, status, signature_bytes))
    if not candidates:
        raise ValueError("no candidate RVA table found in evidence document")
    return candidates


def toggle_console_tailcall_target(signature: bytes,
                                   function_rva: int = 0x005CB6D0) -> int:
    """Decode the confirmed E9 rel32 at byte offset 10 of ToggleConsole."""
    if len(signature) < 15 or signature[:10] != bytes.fromhex(
            "31 F6 80 7F 5A 00 40 0F 94 C6") or signature[10] != 0xE9:
        raise ValueError("bytes do not match the recovered ToggleConsole branch signature")
    displacement = struct.unpack_from("<i", signature, 11)[0]
    return function_rva + 10 + 5 + displacement


def verify_confirmed_anchors(candidates: list[Candidate],
                             image: Elf64Image) -> list[str]:
    """Require both known PS4Debug prefixes to match before disassembly/xrefs."""
    anchors = [candidate for candidate in candidates
               if candidate.confirmed_bytes is not None]
    if len(anchors) < 2:
        raise ValueError("at least two recorded PS4Debug byte anchors are required")
    matched: list[str] = []
    for candidate in anchors:
        expected = candidate.confirmed_bytes
        assert expected is not None
        actual = image.read_rva(candidate.rva, len(expected))
        if actual != expected:
            actual_text = _hex(actual)
            raise ValueError(
                f"refusing disassembly: anchor {candidate.name} at RVA "
                f"0x{candidate.rva:X} does not match PS4Debug evidence "
                f"(local: {actual_text})"
            )
        matched.append(candidate.name)
    return matched


def parse_objdump_line(line: str) -> Instruction | None:
    address_match = DISASM_RE.match(line)
    if not address_match:
        return None
    address = int(address_match.group(1), 16)
    tokens = address_match.group(2).split()
    # GNU/LLVM objdump can include encoded bytes before the mnemonic.
    while tokens and HEX_BYTE_RE.match(tokens[0]):
        tokens.pop(0)
    if not tokens:
        return None
    mnemonic = tokens.pop(0).lower()
    return Instruction(address, mnemonic, " ".join(tokens))


def parse_disassembly(text: str) -> list[Instruction]:
    return [instruction for line in text.splitlines()
            if (instruction := parse_objdump_line(line)) is not None]


def direct_branch_target(instruction: Instruction) -> int | None:
    if instruction.mnemonic not in {"call", "callq", "jmp", "jmpq"}:
        return None
    match = IMMEDIATE_RE.match(instruction.operands)
    return int(match.group(1), 16) if match else None


def discover_objdump(value: str | None) -> str | None:
    if value:
        return value
    return shutil.which("objdump") or shutil.which("llvm-objdump")


def _objdump_base_args(objdump: str) -> list[str]:
    version = subprocess.run([objdump, "--version"], capture_output=True,
                             text=True, check=False).stdout.splitlines()
    first = version[0] if version else ""
    args = [objdump, "-d"]
    if "llvm" in first.lower():
        args.append("--x86-asm-syntax=intel")
    else:
        args.extend(["-M", "intel", "--no-show-raw-insn"])
    return args


def disassemble_window(objdump: str, binary: Path, address: int,
                       window_bytes: int) -> list[Instruction]:
    command = _objdump_base_args(objdump)
    command.extend([f"--start-address=0x{address:X}",
                    f"--stop-address=0x{address + window_bytes:X}",
                    str(binary)])
    result = subprocess.run(command, capture_output=True, text=True,
                            check=False)
    if result.returncode != 0:
        raise RuntimeError(f"objdump failed for window at 0x{address:X} "
                           f"(exit {result.returncode})")
    return parse_disassembly(result.stdout)


def scan_direct_xrefs(objdump: str, binary: Path,
                      target_addresses: dict[int, list[str]]) -> dict[int, list[int]]:
    """Find direct call/jump sites to candidate VAs in an offline full disassembly."""
    command = _objdump_base_args(objdump) + [str(binary)]
    # Discard stderr while streaming stdout so a verbose tool cannot fill the
    # second pipe and deadlock a whole-image scan.
    proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)
    assert proc.stdout is not None
    refs: dict[int, list[int]] = {address: [] for address in target_addresses}
    for line in proc.stdout:
        instruction = parse_objdump_line(line)
        if instruction is None:
            continue
        target = direct_branch_target(instruction)
        if target in refs:
            refs[target].append(instruction.address)
    returncode = proc.wait()
    if returncode != 0:
        raise RuntimeError(f"full objdump xref scan failed (exit {returncode})")
    return refs


def _hex(data: bytes | None) -> str:
    return " ".join(f"{byte:02X}" for byte in data) if data else "—"


def _candidate_status(candidate: Candidate, local_bytes: bytes | None) -> str:
    if candidate.confirmed_bytes is None:
        if "offline PRX prefix match reported" in candidate.status:
            if local_bytes is None:
                return "offline PRX prefix match reported; not confirmed by live PS4Debug"
            return "local bytes extracted; report claims PRX match; no per-method reference bytes stored"
        return "offline RVA candidate; no PS4 byte confirmation in evidence"
    if local_bytes is None:
        return "user-confirmed on PS4Debug; not re-read from a local ELF here"
    if local_bytes[:len(candidate.confirmed_bytes)] == candidate.confirmed_bytes:
        return "user-confirmed historically; local ELF first bytes MATCH"
    return "user-confirmed historically; local ELF first bytes MISMATCH"


def assess_local_imgui_detour(candidate: Candidate | None) -> dict[str, object]:
    """Read-only preflight for a method-local OnGUI detour; never emits a patch."""
    if candidate is None or candidate.name != "TheForest.DebugConsole.OnGUI":
        return {"anchor_match": False, "install_go": False,
                "reason": "TheForest.DebugConsole.OnGUI anchor is unavailable."}
    prefix = candidate.confirmed_bytes
    if prefix != ON_GUI_CONFIRMED_PREFIX:
        return {"anchor_match": False, "install_go": False,
                "reason": "The recorded PS4Debug entry prefix does not match the pinned anchor."}

    # The first six bytes are three complete, position-independent instructions.
    # A five-byte E9 transfer would therefore displace six bytes, if a relay
    # could be allocated within signed-rel32 range and patching were quiesced.
    # The 14-byte absolute-jump case needs 17 complete prologue bytes because
    # byte 13 starts a four-byte `and rsp, imm8` instruction; only 16 are known.
    return {
        "anchor_match": True,
        "method_scope_only": True,
        "rel32_transfer_bytes": 5,
        "rel32_stolen_bytes": len(ON_GUI_REL32_STOLEN_PREFIX),
        "rel32_stolen_instructions": ("push rbp", "mov rbp,rsp", "push r15"),
        "rel32_stolen_prefix": ON_GUI_REL32_STOLEN_PREFIX,
        "rel32_near_relay_required": True,
        "absolute_transfer_bytes": 14,
        "absolute_stolen_bytes_required": 17,
        "absolute_stolen_window_verified": False,
        "runtime_callback_active": "unverified; prior PS4Debug Instance read was NULL",
        "install_go": False,
        "reason": ("No runtime callback proof, Unity GUI call ABI, thread quiescence, "
                   "or safe teardown contract; this is analysis only."),
    }


def render_report(candidates: list[Candidate], image: Elf64Image | None = None,
                  focused: dict[str, tuple[bytes | None, list[Instruction]]] | None = None,
                  xrefs: dict[int, list[int]] | None = None,
                  window_bytes: int = 0) -> str:
    by_name = {candidate.name: candidate for candidate in candidates}
    output = [
        "# Offline PS4 IL2CPP candidate analysis",
        "",
        f"- Evidence rows: `{len(candidates)}`; source: "
        "`docs/PS4_IL2CPP_PRIOR_EVIDENCE.md`.",
        "- Analysis is read-only. No call, patch, hook, or runtime base is used.",
    ]
    if image:
        output.extend([
            f"- Local ELF image base: `0x{image.image_base:X}` "
            f"({image.image_base_source}); no prior-session RAM base used.",
        ])
    else:
        output.append("- No private ELF was supplied to this run; raw bytes and callsites are not rechecked.")
    output.extend([
        "",
        "## Candidate inventory",
        "",
        "| Method | RVA | Evidence status | Local bytes |",
        "| --- | ---: | --- | --- |",
    ])
    for candidate in candidates:
        local_bytes = image.read_rva(candidate.rva, 16) if image else None
        output.append(
            f"| `{candidate.name}` | `0x{candidate.rva:08X}` | "
            f"{_candidate_status(candidate, local_bytes)} | `{_hex(local_bytes)}` |"
        )

    output.extend([
        "",
        "## Focused methods and context",
        "",
        "| Method | RVA | Local file offset | Bytes/signature status |",
        "| --- | ---: | ---: | --- |",
    ])
    for name in FOCUS_METHODS:
        candidate = by_name.get(name)
        if candidate is None:
            output.append(f"| `{name}` | *not in evidence table* | — | — |")
            continue
        offset = image.file_offset(candidate.rva) if image else None
        local_bytes = image.read_rva(candidate.rva, 32) if image else None
        if candidate.confirmed_bytes is None:
            if "offline PRX prefix match reported" in candidate.status:
                signature_status = (
                    "reported PRX prefix match; not live-verified"
                    if local_bytes is None else
                    "local bytes extracted; expected per-method bytes not stored"
                )
            else:
                signature_status = "RVA candidate only; no verified bytes"
        elif local_bytes is None:
            signature_status = "historical PS4Debug 16-byte confirmation; no local comparison"
        elif local_bytes[:16] == candidate.confirmed_bytes:
            signature_status = "historical confirmation and local 16-byte MATCH"
        else:
            signature_status = "historical confirmation; local 16-byte MISMATCH"
        offset_text = f"0x{offset:X}" if offset is not None else "—"
        output.append(
            f"| `{name}` | `0x{candidate.rva:08X}` | `{offset_text}` | "
            f"{signature_status}; `{_hex(local_bytes)}` |"
        )

    ongui = by_name.get("TheForest.DebugConsole.OnGUI")
    toggle = by_name.get("TheForest.DebugConsole.ToggleConsole")
    if ongui and ongui.confirmed_bytes:
        output.extend([
            "",
            "## Confirmed entry-byte observations",
            "",
            "- `DebugConsole.OnGUI` matches the prior PS4Debug confirmation. The "
            "16-byte prefix decodes as `push rbp; mov rbp,rsp; push r15; push "
            "r14; push r13; push r12; push rbx; and rsp,...`; the final "
            "instruction is truncated in the recorded prefix. This establishes "
            "an entry-byte match, not the managed/native prototype or render-thread context.",
        ])
    if toggle and toggle.confirmed_bytes:
        destination = toggle_console_tailcall_target(toggle.confirmed_bytes,
                                                     toggle.rva)
        output.append(
            f"- `DebugConsole.ToggleConsole`: confirmed bytes use `RDI` as an "
            f"object pointer (`cmp byte ptr [rdi+0x5A],0`), set a boolean-like "
            f"value in `SIL`, then tail-jump by `E9 rel32` to RVA "
            f"`0x{destination:08X}`. The destination is derived from the "
            "confirmed displacement; its method identity and full ABI still "
            "need local disassembly. Never call this on a NULL object."
        )

    local_hook = assess_local_imgui_detour(ongui)
    output.extend([
        "",
        "## Localized IMGUI callback preflight",
        "",
        "- Best identified graphics candidate: `TheForest.DebugConsole.OnGUI` at `0x005C37B0`; its PS4 body calls Unity IMGUI, but runtime invocation is **unverified** and the previously read `Instance` was NULL.",
        "- A method-only detour would preserve the PKG and avoid global GNM/VideoOut/ScePad hooks. The confirmed entry prefix supports a 5-byte relative transfer over six complete prologue bytes (`push rbp; mov rbp,rsp; push r15`), conditional on a nearby relay. The 16-byte anchor does not verify the 17-byte window needed for a 14-byte absolute transfer.",
        f"- Installation verdict: **{'GO' if local_hook['install_go'] else 'NO-GO'}**. {local_hook['reason']}",
        "- A title-local patch remains insufficient to draw UCM until the callback is observed active and a Unity GUI renderer/ABI and nonblocking quiescent teardown are validated.",
    ])

    if focused is not None:
        output.extend([
            "",
            f"## Bounded disassembly windows ({window_bytes} bytes each)",
            "",
            "Each window is an address-centered slice, not a proven function extent. "
            "Only direct branch targets are listed; indirect calls, virtual dispatch, "
            "and references beyond the window are unresolved.",
            "",
        ])
        for name, (local_bytes, instructions) in focused.items():
            candidate = by_name[name]
            output.extend([f"### `{name}` at `0x{candidate.rva:08X}`", ""])
            if local_bytes is not None:
                output.append(f"Bytes: `{_hex(local_bytes)}`")
            branches = [instruction for instruction in instructions
                        if instruction.mnemonic in {"call", "callq", "jmp", "jmpq"}]
            if branches:
                for instruction in branches:
                    target = direct_branch_target(instruction)
                    if target is None:
                        target_text = "indirect/unresolved"
                    elif image and target >= image.image_base:
                        target_text = f"RVA 0x{target - image.image_base:08X}"
                    else:
                        target_text = f"0x{target:X}"
                    source_address = (instruction.address - image.image_base
                                      if image else instruction.address)
                    output.append(
                        f"- `0x{source_address:08X}` `"
                        f"{instruction.mnemonic} {instruction.operands}` → `{target_text}`")
            else:
                output.append("- No direct call/jump decoded in this window.")
            output.append("")

    if xrefs is not None and image is not None:
        output.extend([
            "## Direct incoming call/jump sites",
            "",
            "Source addresses are converted back to RVAs using the ELF image base. "
            "This scan does not resolve indirect or virtual calls.",
            "",
        ])
        names_by_address: dict[int, list[str]] = {}
        for candidate in candidates:
            names_by_address.setdefault(
                image.virtual_address(candidate.rva), []).append(candidate.name)
        for address, names in sorted(names_by_address.items()):
            sites = xrefs.get(address, [])
            formatted = ", ".join(f"`0x{site - image.image_base:08X}`" for site in sites)
            output.append(f"- `{', '.join(names)}` (`0x{address - image.image_base:08X}`): "
                          f"{formatted if formatted else 'no direct call/jump sites found'}")

    output.extend([
        "",
        "## ABI and integration conclusions",
        "",
        "- Only the recorded 16-byte entries for `DebugConsole.OnGUI` and "
        "`DebugConsole.ToggleConsole` are user-confirmed on PS4Debug. Other table "
        "rows remain offline RVA candidates until their local bytes are compared.",
        "- Method names and entry bytes do not establish a callable IL2CPP C ABI. "
        "The wrapper must check the complete function, argument/hidden-method "
        "parameters, object lifetime, and call context from the local disassembly.",
        "- `DebugConsole.OnGUI` is the strongest Unity GUI candidate, but the "
        "singleton was read as NULL. `PS4Controller.Update`, `VirtualCursor.LateUpdate`, "
        "`DllModLoader.Awake`, and `ModList.OnEnable` are only candidate Unity "
        "callbacks; none proves a safe external registration or render-thread entry.",
        "- `ModList.OnEnable` being reported as a short `ret`-style stub would "
        "make that entry unusable; confirm its exact local bytes before treating "
        "the RVA as an implemented callback.",
        "- Unity's native render-event route still needs a Unity-side caller. "
        "No global VideoOut/GNM/ScePad hook is added or re-enabled.",
        "",
    ])
    return "\n".join(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE,
                        help="recovered candidate table (default: repository doc)")
    parser.add_argument("--binary", type=Path,
                        help="private local decrypted ELF64 PRX/module; never copied")
    parser.add_argument("--image-base", type=lambda value: int(value, 0),
                        help="ELF link/image base, not a runtime PS4 address")
    parser.add_argument("--objdump", help="local GNU/LLVM objdump executable")
    parser.add_argument("--window-bytes", type=int, default=256,
                        help="bounded byte range per focus candidate (default 256)")
    parser.add_argument("--scan-xrefs", action="store_true",
                        help="disassemble the whole ELF to find direct call/jump sites")
    parser.add_argument("--output", type=Path,
                        help="write Markdown report here; default is stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.window_bytes < 1 or args.window_bytes > 4096:
            raise ValueError("--window-bytes must be between 1 and 4096")
        candidates = parse_evidence(args.evidence)
        image = Elf64Image(args.binary, args.image_base) if args.binary else None
        focused: dict[str, tuple[bytes | None, list[Instruction]]] | None = None
        xrefs: dict[int, list[int]] | None = None
        if image:
            verified = verify_confirmed_anchors(candidates, image)
            objdump = discover_objdump(args.objdump)
            if objdump:
                by_name = {candidate.name: candidate for candidate in candidates}
                focused = {}
                for name in FOCUS_METHODS:
                    candidate = by_name.get(name)
                    if not candidate:
                        continue
                    raw = image.read_rva(candidate.rva, 32)
                    instructions = disassemble_window(
                        objdump, args.binary, image.virtual_address(candidate.rva),
                        args.window_bytes)
                    focused[name] = (raw, instructions)
                if args.scan_xrefs:
                    targets: dict[int, list[str]] = {}
                    for candidate in candidates:
                        targets.setdefault(image.virtual_address(candidate.rva), []).append(candidate.name)
                    xrefs = scan_direct_xrefs(objdump, args.binary, targets)
            elif args.scan_xrefs:
                raise ValueError("--scan-xrefs requires local GNU or LLVM objdump")
            # The report only lists anchor comparison details in the normal
            # candidate table; retain this count in stderr for CLI provenance.
            print(f"verified local PS4Debug anchors: {len(verified)}",
                  file=sys.stderr)

        report = render_report(candidates, image, focused, xrefs,
                               args.window_bytes if focused is not None else 0)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
        return 0
    except (OSError, ValueError, RuntimeError, struct.error) as exc:
        print(f"analyze-ps4-il2cpp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
