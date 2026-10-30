#!/usr/bin/env python3
"""Read-only exact-build PlayMakerGUI/Rewired native call-contract verifier.

Verifies a bounded set of exact instruction bytes and metadata method
definitions from the original title. No native invocation, patching,
console execution, external callback ABI or unload guarantee is implied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from analyze_ps4_il2cpp_pipeline import parse_metadata_v23
from inspect_aot_registration import NativeImage

ELF_SHA = "0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969"
META_SHA = "238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3"
METHOD_PTRS_VA = 0x0316F8C0
# Definition, declaring type, name, pointer index, native link VA, argc, slot.
METHODS = (
    (34351, "PlayMakerGUI", "CallOnGUI", 31675, 0x01141320, 1, None),
    (34075, "HutongGames.PlayMaker.FsmStateAction", "OnGUI",
     31277, 0x01130870, 0, 33),
    (68839, "HutongGames.PlayMaker.Actions.GUIButton", "OnGUI",
     57405, 0x02383D30, 0, 33),
    (20713, "UnityEngine.GUI", "Button", 17754, 0x019BE750, 3, None),
    (69012, "HutongGames.PlayMaker.Actions.GetButtonDown", "OnUpdate",
     57012, 0x025374D0, 0, 32),
    (40594, "Rewired.Player", "GetButtonDown", 37710, 0x00A25720, 1, None),
)
# Exact bounded instruction encodings, not reusable detours or patches.
SITES = {
    "virtual_methodinfo": (0x01141397, "488bb028030000"),
    "virtual_call": (0x0114139E, "ff9020030000"),
    "gui_rect_xy": (0x02383DDF, "c5f82845c0"),
    "gui_rect_wh": (0x02383DE4, "c5f8284dd0"),
    "gui_rdi_zero": (0x02383DE9, "31ff"),
    "gui_rcx_zero": (0x02383DEB, "31c9"),
    "gui_rsi": (0x02383DED, "4c89f6"),
    "gui_rdx": (0x02383DF0, "4c89fa"),
    "gui_button_call": (0x02383DF6, "e855a963ff"),
    "gui_callee_xmm1": (0x019BE766, "c5f8294da0"),
    "gui_callee_xmm0": (0x019BE76B, "c5f82945b0"),
    "gui_callee_rdx": (0x019BE770, "4889d3"),
    "gui_callee_rsi": (0x019BE773, "4989f6"),
    "rewired_static_player_ref": (0x02537567, "488b87a0000000"),
    "rewired_player_deref": (0x0253756E, "488b38"),
    "rewired_methodinfo_zero": (0x02537576, "31d2"),
    "rewired_button_name": (0x02537578, "4c89f6"),
    "rewired_getbuttondown_call": (0x0253757B, "e8a0e14efe"),
}
DIRECT_TARGETS = {
    "gui_button_call": 0x019BE750,
    "rewired_getbuttondown_call": 0x00A25720,
}


def verify_sites(read_va, sites=SITES, direct_targets=DIRECT_TARGETS):
    """Check exact instruction words and rel32 call destinations."""
    verified = []
    for name, (site, pattern) in sites.items():
        expected = bytes.fromhex(pattern)
        if read_va(site, len(expected)) != expected:
            raise ValueError("native instruction mismatch: " + name)
        if name in direct_targets:
            if (len(expected) != 5 or expected[0] != 0xE8 or
                    site + 5 + struct.unpack_from("<i", expected, 1)[0]
                    != direct_targets[name]):
                raise ValueError("native call target mismatch: " + name)
        verified.append(name)
    return verified


def verify_metadata(meta_bytes, image):
    meta = parse_metadata_v23(meta_bytes)
    method_off, _ = meta.sections["methods"]
    results = []
    for definition, owner, name, pointer_idx, va, argc, slot in METHODS:
        if definition >= len(meta.methods):
            raise ValueError("missing native method definition")
        method = meta.methods[definition]
        actual_owner = meta.types[method.declaring_type].full_name
        native_ptr = struct.unpack("<Q",
            image.read(METHOD_PTRS_VA + pointer_idx * 8, 8))[0]
        native_slot = struct.unpack_from("<H", meta_bytes,
                                         method_off + definition * 56 + 52)[0]
        if (actual_owner != owner or method.name != name or
                method.method_index != pointer_idx or
                method.parameter_count != argc or
                (slot is not None and native_slot != slot) or
                native_ptr != va or not image.executable(va)):
            raise ValueError("method signature/pointer mismatch: " + owner + "." + name)
        results.append({
            "method": owner + "." + name, "method_definition": definition,
            "method_pointer_index": pointer_idx, "link_va": hex(va),
            "managed_parameter_count": argc, "virtual_slot": slot,
        })
    return results


def inspect(module: bytes, metadata: bytes):
    if hashlib.sha256(module).hexdigest() != ELF_SHA:
        raise ValueError("wrong IL2CPP ELF SHA-256")
    if hashlib.sha256(metadata).hexdigest() != META_SHA:
        raise ValueError("wrong metadata SHA-256")
    image = NativeImage(module)
    methods = verify_metadata(metadata, image)
    for site, _ in SITES.values():
        if not image.executable(site):
            raise ValueError("instruction outside executable segment")
    sites = verify_sites(image.read)
    return {
        "title": "The Forest PS4 CUSA12398 v1.15",
        "verified_methods": methods,
        "verified_instruction_sites": len(sites),
        "verified_call_edges": {key: hex(value)
                                for key, value in DIRECT_TARGETS.items()},
        "evidence": [
            "Virtual FsmStateAction.OnGUI reads function at +0x320 and MethodInfo at +0x328 from an existing action vtable.",
            "Compiled GUIButton.OnGUI sends two Rect halves via XMM0/XMM1 to the three-parameter UnityEngine.GUI.Button overload.",
            "Compiled GetButtonDown.OnUpdate obtains a runtime Rewired.Player pointer and calls a one-parameter GetButtonDown overload.",
        ],
        "limits": [
            "No PRX callback registration surface or valid runtime action/Player ownership demonstrated.",
            "Exact external ABI, Unity GUI thread/context, lifecycle/quiescence and physical DS4 mapping remain unproven.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = json.dumps(
            inspect(args.module.read_bytes(), args.metadata.read_bytes()),
            indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result, encoding="utf-8")
        else:
            print(result, end="")
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(2, "playmaker-call-contract: %s\n" % exc)


if __name__ == "__main__":
    main()
