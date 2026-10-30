#!/usr/bin/env python3
"""Read-only Sony DS4 hardware element IDs in Unity 5.6.6f2 Rewired assets.

Element IDs are NOT Rewired action IDs, OrbisPad masks or live input proof.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
from inspect_unity_rewired_assets import Asset, monoscript

PRINTABLE = re.compile(rb"[a-zA-Z0-9 -]{2,32}\Z")
UUID = re.compile(rb"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)
EXPECTED_IDS = {
    "Left Stick X": 0, "Left Stick Y": 1,
    "Right Stick X": 2, "Right Stick Y": 3,
    "L2": 4, "R2": 5, "Cross": 6, "Circle": 7,
    "Square": 8, "Triangle": 9, "L1": 10, "R1": 11,
    "Share": 12, "Options": 13, "PS Button": 14,
    "Touchpad Button": 15, "Left Stick Button": 16,
    "Right Stick Button": 17, "D-Pad Up": 18,
    "D-Pad Right": 19, "D-Pad Down": 20,
    "D-Pad Left": 21, "Left Stick": 22, "Right Stick": 23,
}


def extract_elements(blob: bytes) -> dict[str, int]:
    start = blob.find(b"Left Stick X")
    stop = blob.find(b"Wireless Controller")
    if start < 8 or stop <= start or stop > 10000:
        raise ValueError("Sony DS4 element table not identified")
    items: dict[str, int] = {}
    for pos in range(start, stop, 4):
        if pos < 8:
            continue
        element_id, size = struct.unpack_from("<II", blob, pos - 8)
        if not (0 <= element_id <= 64 and 2 <= size <= 32 and pos + size <= stop):
            continue
        raw = blob[pos:pos + size]
        if not PRINTABLE.fullmatch(raw):
            continue
        padding = blob[pos + size:(pos + size + 3) & ~3]
        if any(padding):
            continue
        name = raw.decode("ascii")
        if name in EXPECTED_IDS:
            if name in items and items[name] != element_id:
                raise ValueError("conflicting DS4 element IDs")
            items[name] = element_id
    if items != EXPECTED_IDS:
        missing = sorted(set(EXPECTED_IDS) - set(items))
        mismatch = {key: (items[key], EXPECTED_IDS[key]) for key in items
                    if key in EXPECTED_IDS and items[key] != EXPECTED_IDS[key]}
        raise ValueError(f"DS4 element table differs: missing={missing}; mismatch={mismatch}")
    return items


def inspect(root: Path) -> dict:
    scripts_asset = Asset(root / "globalgamemanagers.assets")
    shared = Asset(root / "sharedassets0.assets")
    scripts = {pid: monoscript(scripts_asset.obj(pid))
               for pid in scripts_asset.ids(115)}
    matching = []
    for pid in shared.ids(114):
        mb = shared.mono(pid)
        if shared.external(mb["script_file"]) != "globalgamemanagers.assets":
            continue
        script = scripts.get(mb["script_id"])
        if not script or (script["class_name"], script["namespace"]) != (
            "HardwareJoystickMap", "Rewired.Data.Mapping"
        ):
            continue
        data = shared.obj(pid)
        if b"SonyDualShock4" in data[:128]:
            matching.append((pid, data))
    if len(matching) != 1:
        raise ValueError("expected one unambiguous Sony DS4 hardware profile")
    pid, data = matching[0]
    elements = extract_elements(data)
    guids = sorted({m.group().decode("ascii").lower() for m in UUID.finditer(data)})
    if len(guids) != 2:
        raise ValueError("expected two hardware GUIDs")
    return {
        "unity_version": shared.version,
        "hardware_object_id": pid,
        "sharedassets_sha256": hashlib.sha256(shared.data).hexdigest(),
        "hardware_profile": "SonyDualShock4",
        "guid_identifiers": guids,
        "element_ids": {name: elements[name] for name in EXPECTED_IDS},
        "limitations": [
            "hardware element ID != Rewired action ID",
            "hardware element ID != OrbisPad button mask",
            "no proof of live Player assignment or map selection",
            "no Unity AOT retail bootstrap or PS4 hardware test"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = json.dumps(inspect(args.assets_root), indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            print(report, end="")
        return 0
    except (OSError, ValueError, KeyError, struct.error) as exc:
        parser.exit(2, f"inspect-ds4-hardware: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
