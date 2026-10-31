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

from inspect_playmaker_fsm_assets import (  # noqa: E402
    Reader,
    parse_fsm_template_header,
)
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


def _validate_identity(identity: object) -> dict:
    if not isinstance(identity, dict):
        raise ValueError("invalid PlayMaker tail identity")
    allowed = {"path_id", "game_object", "fsm_name", "template_name",
               "start_state", "state_count", "identity_status"}
    if any(key not in allowed for key in identity):
        raise ValueError("invalid PlayMaker tail identity field")
    result = dict(identity)
    if "path_id" in result and (type(result["path_id"]) is not int or
                                  result["path_id"] < 0):
        raise ValueError("invalid PlayMaker tail path ID")
    for key in ("game_object", "fsm_name", "template_name", "start_state",
                "identity_status"):
        value = result.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 4096):
            raise ValueError("invalid PlayMaker tail identity string")
    if "state_count" in result and (type(result["state_count"]) is not int or
                                     not 0 <= result["state_count"] <= 128):
        raise ValueError("invalid PlayMaker tail state count")
    return result


def compare_tails(rows: list[tuple]) -> dict:
    if not isinstance(rows, list) or len(rows) > MAX_TAILS:
        raise ValueError("PlayMaker tail sample count outside bounds")
    hashes: dict[bytes, str] = {}
    samples_by_hash: dict[str, list[dict]] = {}
    tails: list[bytes] = []
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if not isinstance(row, tuple) or len(row) not in (3, 4):
            raise ValueError("invalid PlayMaker tail sample")
        asset_name, kind, tail = row[:3]
        identity = _validate_identity(row[3]) if len(row) == 4 else {}
        if (not isinstance(asset_name, str) or
                kind not in ("PlayMakerFSM", "FsmTemplate") or
                not isinstance(tail, bytes) or len(tail) != TAIL_SIZE):
            raise ValueError("invalid PlayMaker tail sample")
        digest = hashlib.sha256(tail).hexdigest()
        hashes[tail] = digest
        sample = {"asset": asset_name, "type": kind, **identity}
        samples_by_hash.setdefault(digest, []).append(sample)
        tails.append(tail)
        counts[(asset_name, kind)] += 1
    unique_hashes = sorted(set(hashes.values()))
    varying_offsets = [
        {"offset": offset,
         "distinct_byte_values": len({tail[offset] for tail in tails})}
        for offset in range(TAIL_SIZE)
        if len({tail[offset] for tail in tails}) > 1
    ]
    return {
        "tail_samples": len(rows),
        "distinct_tail_values": len(hashes),
        "distinct_tail_sha256": unique_hashes,
        "all_tail_bytes_equal": bool(rows) and len(hashes) == 1,
        "tail_sha256_groups": [
            {"sha256": digest, "count": len(samples_by_hash[digest]),
             "samples": samples_by_hash[digest]}
            for digest in unique_hashes
        ],
        "varying_byte_offsets": varying_offsets,
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
                # Decode only the verified stable prefix needed to identify the
                # FSM. The remaining Fsm fields, including the 40-byte tail,
                # remain untouched and are never emitted.
                reader = Reader(blob, 32)
                reader.take(12)  # usedInTemplate PPtr
                fsm_name, _ = reader.aligned_string()
                start_state, _ = reader.aligned_string()
                state_count = reader.count("Fsm.states", 128)
                try:
                    game_object = asset.gameobject(mono["game_id"])["name"]
                except (KeyError, ValueError):
                    game_object = None
                identity = {"path_id": path_id, "game_object": game_object,
                            "fsm_name": fsm_name, "start_state": start_state,
                            "state_count": state_count}
                tails.append((asset_name, "PlayMakerFSM", blob[-52:-12], identity))
            elif script["class_name"] == "FsmTemplate":
                if len(blob) < 32 + TAIL_SIZE:
                    raise ValueError("short hash-pinned FsmTemplate object")
                template_count += 1
                identity = {"path_id": path_id}
                try:
                    header = parse_fsm_template_header(blob)
                    identity.update({"template_name": header["name"],
                                     "fsm_name": header["fsm_name"],
                                     "start_state": header["start_state"],
                                     "state_count": header["state_count"]})
                except ValueError:
                    # The stable object boundary still locates the tail even
                    # when this bounded parser cannot decode the wrapper.
                    identity["identity_status"] = "header-unresolved"
                tails.append((asset_name, "FsmTemplate", blob[-TAIL_SIZE:], identity))
        if component_count or template_count:
            per_asset.append({"asset": asset_name,
                              "PlayMakerFSM": component_count,
                              "FsmTemplate": template_count})

    tail_summary = compare_tails(tails)
    return {
        "title": "The Forest PS4 CUSA12398 v1.15",
        "read_only": True,
        "hash_pinned_scene_and_sharedassets_scanned": 60,
        "hash_pinned_source_files_scanned": len(scan_paths),
        "hash_pinned_files_including_monoscript_source": len(scan_paths) + 1,
        "globalgamemanagers_used_for_monoscript_resolution": True,
        "resources_assets_scanned": resources_path is not None,
        "resources_assets_sha256_verified": resources_path is not None,
        "resources_assets_sha256": (manifest.get("resources.assets")
                                    if resources_path is not None else None),
        "resources_assets_hash_pinned_but_not_scanned":
            resources_path is None and "resources.assets" in manifest,
        "matched_objects_by_asset": per_asset,
        **tail_summary,
        "interpretation": (
            "Digest groups establish byte equality or difference only; neither "
            "equality nor correlation with an FSM identifies tail-field semantics."),
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
