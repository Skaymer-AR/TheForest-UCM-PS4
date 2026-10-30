#!/usr/bin/env python3
"""Offline PlayMakerGUI native callgraph gate for CUSA12398 v1.15.

Requires the verified PRIVATE plaintext IL2CPP ELF. Emits only callsite/RVA
metadata and never writes, loads or patches native code. It does not establish
a safe Unity callback registration or PRX unload protocol.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

ELF_SHA = "0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969"
METHOD_TABLE_OFFSET = 0x031738C0
METHODS = {
    "PlayMakerGUI.OnGUI": (31674, 0x0113FAF0, 0x011411F0),
    "PlayMakerGUI.DoEditGUI": (31677, 0x011411F0, 0x01141320),
    "PlayMakerGUI.CallOnGUI": (31675, 0x01141320, 0x01141550),
}
DIRECT = re.compile(r"^\s*([0-9a-f]+):.*?\bcallq?\s+0x([0-9a-f]+)\b", re.I)
INDIRECT = re.compile(r"^\s*([0-9a-f]+):.*?\bcallq?\s+\*([^\s]+)", re.I)
KNOWN_TARGETS = {
    0x019BC3F0: "UnityEngine.GUI.set_skin",
    0x019CC8D0: "UnityEngine.GUI.set_color",
    0x019CCB10: "UnityEngine.GUI.set_backgroundColor",
    0x019CCD50: "UnityEngine.GUI.set_contentColor",
    0x019BD1F0: "UnityEngine.GUI.DrawTexture",
    0x01141320: "PlayMakerGUI.CallOnGUI",
    0x011411F0: "PlayMakerGUI.DoEditGUI",
    0x0118D30: "collection enumerator (target not yet ABI-verified)",
}


def parse_calls(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, str]]]:
    direct, indirect = [], []
    for line in text.splitlines():
        m = DIRECT.search(line)
        if m:
            direct.append((int(m.group(1), 16), int(m.group(2), 16)))
        m = INDIRECT.search(line)
        if m:
            indirect.append((int(m.group(1), 16), m.group(2)))
    return direct, indirect


def inspect(elf_path: Path, llvm_objdump: str = "llvm-objdump") -> dict:
    elf = elf_path.read_bytes()
    if hashlib.sha256(elf).hexdigest() != ELF_SHA:
        raise ValueError("unexpected ELF SHA-256; refusing all fixed RVAs")
    for label, (method_idx, va, _) in METHODS.items():
        ptr_at = METHOD_TABLE_OFFSET + 8 * method_idx
        if ptr_at + 8 > len(elf) or struct.unpack_from("<Q", elf, ptr_at)[0] != va:
            raise ValueError("method pointer differs: " + label)
    result = {}
    for label, (_, start, stop) in METHODS.items():
        proc = subprocess.run([
            llvm_objdump, "-d", "--start-address=" + hex(start),
            "--stop-address=" + hex(stop), str(elf_path)
        ], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ValueError("disassembly failed: " + proc.stderr[:200])
        direct, indirect = parse_calls(proc.stdout)
        if not direct:
            raise ValueError("unrecognized disassembly/no calls: " + label)
        result[label] = {
            "start_va": hex(start), "end_va_exclusive": hex(stop),
            "direct_call_count": len(direct),
            "indirect_calls": [{"at_va":hex(at), "operand":op} for at,op in indirect],
            "identified_direct_calls": [
                {"at_va": hex(at), "target_va": hex(target), "method": KNOWN_TARGETS[target]}
                for at,target in direct if target in KNOWN_TARGETS
            ],
            "other_direct_call_count": sum(target not in KNOWN_TARGETS for _,target in direct),
        }
    ongui_targets = result["PlayMakerGUI.OnGUI"]["identified_direct_calls"]
    calls_to_dispatch = sum(e["method"] == "PlayMakerGUI.CallOnGUI" for e in ongui_targets)
    if calls_to_dispatch != 2:
        raise ValueError("expected two native OnGUI calls to CallOnGUI, found %d" % calls_to_dispatch)
    if not any(e["operand"] == "0x320(%rax)" for e in result["PlayMakerGUI.CallOnGUI"]["indirect_calls"]):
        raise ValueError("expected indirect dispatch not found in CallOnGUI")
    return {
        "title": "The Forest PS4 CUSA12398 1.15",
        "module_sha256": ELF_SHA,
        "methods": result,
        "limits": [
            "Existing native Unity GUI calls and virtual dispatch are static facts.",
            "Virtual target at 0x320(%rax) is not identified as a safe PRX subscription API.",
            "A verified IMGUI invocation context, Unity ABI, callback synchronization and PRX teardown remain missing.",
            "No hook installed, no binary patches, no console test and no PRX produced.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--llvm-objdump", default="llvm-objdump")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = json.dumps(inspect(args.module, args.llvm_objdump), indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report)
        else:
            print(report, end="")
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, "inspect-playmaker-dispatch: %s\n" % error)


if __name__ == "__main__":
    raise SystemExit(main())
