#!/usr/bin/env python3
"""Compare opaque PlayMaker Fsm tails in hash-pinned Unity assets.

This is a read-only source audit. It emits only asset names, counts and a
SHA-256 digest of the 40-byte tail; it never emits or writes commercial bytes.
The tail layout uses the already verified component/template boundaries and
does not claim that a matching tail's fields are semantically understood.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_unity_rewired_assets import Asset, monoscript  # noqa: E402

MAX_TAILS = 4096
TAIL_SIZE = 40


def load_hash_manifest(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8") as source:
            header = json.loads(source.readline())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read the derived source-hash manifest") from exc
    hashes = header.get("provenance", {}).get("asset_hashes")
    if (not isinstance(hashes, dict) or
            any(not isinstance(name, str) or not isinstance(value, str) or
                len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
                for name, value in hashes.items())):
        raise ValueError("derived source-hash manifest is malformed")
    return hashes


def compare_tails(rows: list[tuple[str, str, bytes]]) -> dict:
    if not isinstance(rows, list) or len(rows) > MAX_TAILS:
        raise ValueError("PlayMaker tail sample count outside bounds")
    hashes: dict[bytes, str] = {}
    counts: Counter[tuple[str, str]] = Counter()
    for asset_name, kind, tail in rows:
        if (not isinstance(asset_name, str) or
                kind not in ("PlayMakerFSM", "FsmTemplate") or
                not isinstance(tail, bytes) or len(tail) != TAIL_SIZE):
            raise ValueError("invalid PlayMaker tail sample")
        hashes[tail] = hashlib.sha256(tail).hexdigest()
        counts[(asset_name, kind)] += 1
    unique_hashes = sorted(set(hashes.values()))
    return {
        "tail_samples": len(rows),
        "distinct_tail_values": len(hashes),
        "distinct_tail_sha256": unique_hashes,
        "all_tail_bytes_equal": bool(rows) and len(hashes) == 1,
        "samples_by_asset_and_type": [
            {"asset": asset, "type": kind, "count": count}
            for (asset, kind), count in sorted(counts.items())
        ],
        "raw_tail_bytes_emitted": False,
    }


def inspect(levels_dir: Path, sharedassets_dir: Path,
            globalgamemanagers_path: Path, *, resources_path: Path | None = None,
            manifest_path: Path | None = None) -> dict:
    manifest = load_hash_manifest(
        manifest_path or ROOT / "docs/PLAYMAKER_ACTION_INSTANCE_INDEX_20261031.jsonl")
    global_name = "globalgamemanagers.assets"
    expected_global = manifest.get(global_name)
    global_data = globalgamemanagers_path.read_bytes()
    if hashlib.sha256(global_data).hexdigest() != expected_global:
        raise ValueError("globalgamemanagers asset does not match the pinned hash")
    global_asset = Asset(globalgamemanagers_path)
    scripts = {path_id: monoscript(global_asset.obj(path_id))
               for path_id in global_asset.ids(115)}

    scan_paths = []
    for index in range(30):
        scan_paths.append((f"level{index}", levels_dir / f"level{index}"))
    for index in range(30):
        scan_paths.append((f"sharedassets{index}.assets",
                           sharedassets_dir / f"sharedassets{index}.assets"))
    if resources_path is not None:
        scan_paths.append(("resources.assets", resources_path))

    per_asset = []
    tails = []
    for asset_name, path in scan_paths:
        expected = manifest.get(asset_name)
        if expected is None:
            raise ValueError("source-hash manifest has no pin for " + asset_name)
        if not path.is_file():
            raise ValueError("required hash-pinned asset is missing: " + asset_name)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Unity asset does not match its pinned hash: " + asset_name)
        asset = Asset(path)
        component_count = template_count = 0
        for path_id in asset.ids(114):
            mono = asset.mono(path_id)
            if asset.external(mono["script_file"]) != global_name:
                continue
            script = scripts.get(mono["script_id"])
            if not script or script["assembly"] != "PlayMaker.dll":
                continue
            blob = asset.obj(path_id)
            if script["class_name"] == "PlayMakerFSM" and script["name"] == "PlayMakerFSM":
                if len(blob) < 32 + TAIL_SIZE + 12:
                    raise ValueError("short hash-pinned PlayMakerFSM component")
                component_count += 1
                tails.append((asset_name, "PlayMakerFSM", blob[-52:-12]))
            elif script["class_name"] == "FsmTemplate":
                if len(blob) < 32 + TAIL_SIZE:
                    raise ValueError("short hash-pinned FsmTemplate object")
                template_count += 1
                tails.append((asset_name, "FsmTemplate", blob[-TAIL_SIZE:]))
        if component_count or template_count:
            per_asset.append({"asset": asset_name,
                              "PlayMakerFSM": component_count,
                              "FsmTemplate": template_count})

    tail_summary = compare_tails(tails)
    return {
        "title": "The Forest PS4 CUSA12398 v1.15",
        "read_only": True,
        "hash_pinned_scene_and_sharedassets_scanned": len(scan_paths),
        "globalgamemanagers_used_for_monoscript_resolution": True,
        "resources_assets_scanned": resources_path is not None,
        "resources_assets_hash_pinned_but_not_scanned":
            resources_path is None and "resources.assets" in manifest,
        "matched_objects_by_asset": per_asset,
        **tail_summary,
        "interpretation": (
            "Byte equality across these samples does not identify the tail fields; "
            "it only establishes an invariant byte sequence in the scanned objects."),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", type=Path, required=True,
                        help="directory containing level0 through level29")
    parser.add_argument("--sharedassets", type=Path, required=True,
                        help="directory containing sharedassets0 through sharedassets29")
    parser.add_argument("--globalgamemanagers", type=Path, required=True)
    parser.add_argument("--resources", type=Path,
                        help="optional pinned resources.assets copy")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "docs/PLAYMAKER_ACTION_INSTANCE_INDEX_20261031.jsonl")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = inspect(args.levels, args.sharedassets, args.globalgamemanagers,
                     resources_path=args.resources, manifest_path=args.manifest)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
