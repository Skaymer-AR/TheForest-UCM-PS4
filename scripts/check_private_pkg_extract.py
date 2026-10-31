#!/usr/bin/env python3
"""Read-only provenance check of private The Forest CUSA12398 v1.15 PKG extracts.

Runs locally (including Colab). Never writes/patches/exports game binaries.
Only prints fingerprints, detected container types and two known PS4 code anchors.
A matching ELF entry signature is NOT evidence of active Unity callbacks.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# Reuse the repository's RVA-to-ELF-segment mapping; do not assume RVA+0x4000.
from analyze_ps4_il2cpp_candidates import Elf64Image

KNOWN_METADATA_SHA = "238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3"
PREVIOUS_PRX_SHA = "0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969"
ANCHORS = (
    ("DebugConsole.OnGUI", 0x005C37B0, bytes.fromhex(
        "55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 E4")),
    ("DebugConsole.ToggleConsole", 0x005CB6D0, bytes.fromhex(
        "31 F6 80 7F 5A 00 40 0F 94 C6 E9 21 F1 FF FF 90")),
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def container_type(path: Path) -> str:
    with path.open("rb") as source:
        prefix = source.read(16)
    if prefix.startswith(b"\x7fELF"):
        return "decrypted ELF (test RVA mapping)"
    if prefix.startswith(bytes.fromhex("4f153d1d")):
        return "SCE/SELF container (RVA mapping not possible without a decrypted ELF)"
    if prefix.startswith(b"OELF"):
        return "OELF/nonstandard container (RVA mapping not verified)"
    return "unrecognized header (do not assume ELF)"


def previous_elf_comparison(path: Path, sha: str) -> str:
    """Compare like-for-like only; raw SELF and historical ELF hashes differ by design."""
    if not container_type(path).startswith("decrypted ELF"):
        return "NOT COMPARABLE (current input is not a decrypted ELF64)"
    return "SAME" if sha == PREVIOUS_PRX_SHA else "DIFFERENT"


def choose_one(root: Path, basename: str) -> Path:
    matches = sorted(p for p in root.rglob("*") if p.is_file()
                     and p.name.lower() == basename.lower())
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {basename}, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="private TheForest_Extraidos directory")
    args = parser.parse_args()
    root = args.root
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    try:
        eboot = choose_one(root, "eboot.bin")
        prx = choose_one(root, "Il2CppUserAssemblies.prx")
        meta = sorted(p for p in root.rglob("*")
                      if p.is_file() and p.name == "global-metadata.dat")
        if not meta:
            raise ValueError("global-metadata.dat not found")
        print("The Forest PS4 CUSA12398 1.15 | private read-only evidence")
        for name, path in (("eboot", eboot), ("IL2CPP PRX", prx)):
            sha = digest(path)
            print(f"{name}: {path.relative_to(root)}")
            print(f"  size={path.stat().st_size} sha256={sha}")
            print(f"  type={container_type(path)}")
            if name == "IL2CPP PRX":
                print("  historical ELF SHA comparison:",
                      previous_elf_comparison(path, sha))
        for path in meta:
            sha = digest(path)
            print(f"metadata: {path.relative_to(root)}")
            print(f"  size={path.stat().st_size} sha256={sha}")
            print("  historical metadata SHA:",
                  "SAME" if sha == KNOWN_METADATA_SHA else "DIFFERENT")
        if len({digest(p) for p in meta}) != 1:
            print("WARNING: metadata copies are not identical")

        if container_type(prx).startswith("decrypted ELF"):
            try:
                elf = Elf64Image(prx)
                print("ELF image base:", hex(elf.image_base))
                for name, rva, expected in ANCHORS:
                    observed = elf.read_rva(rva, len(expected))
                    result = "MATCH" if observed == expected else "MISMATCH"
                    print(f"anchor {name} at RVA 0x{rva:X}: {result}")
                    if observed is not None:
                        print("  observed bytes:", observed.hex(" "))
            except (OSError, ValueError) as exc:
                print(f"ELF RVA verification not available: {exc}")
        else:
            print("anchor checks: SKIPPED (input is not a decrypted ELF64)")
        print("VERDICT: evidence only; does not validate a live callback, ABI, or hook.")
        return 0
    except (ValueError, OSError) as exc:
        print(f"extract-check: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

