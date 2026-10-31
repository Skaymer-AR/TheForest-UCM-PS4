#!/usr/bin/env python3
"""Inventory serialized PlayMaker action names without editing Unity assets.

The scanner validates the ActionData action-name/per-action metadata prefix and
the enclosing FsmState header. It deliberately marks the rest of ActionData as
partial when a specialized array or parameter encoding is unsupported. It is
not an asset writer or a runtime registration mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_playmaker_fsm_assets import (  # noqa: E402
    MAX_ACTIONS,
    MAX_COMPONENT_BYTES,
    MAX_PARAMETERS,
    MAX_STRING_BYTES,
    Reader,
    TypeResolver,
    _aligned_cstring,
    _parse_transition,
    _public_json,
    encode_action_data,
    parse_action_data,
    parse_fsm_template_header,
)
from inspect_unity_rewired_assets import Asset, monoscript  # noqa: E402

TARGET_ACTION_NAMES = (
    "GUIBox", "GUILabel", "GUIButton", "GUILayoutButton",
    "GetButtonDown", "SendEvent",
)
ACTION_PREFIX = "HutongGames.PlayMaker.Actions."
TARGET_ACTIONS = {ACTION_PREFIX + name for name in TARGET_ACTION_NAMES}
MAX_STATE_HEADER_BYTES = 1 << 16


def _ascii_text(value: str, maximum: int, *, allow_empty: bool = False) -> bool:
    return (len(value) <= maximum and (allow_empty or bool(value)) and
            all(" " <= char <= "~" for char in value))


def parse_actiondata_prefix(data: bytes, offset: int) -> dict | None:
    """Validate ActionData's action-name and per-action arrays at one offset."""
    if offset < 0 or offset % 4 or len(data) > MAX_COMPONENT_BYTES:
        return None
    try:
        reader = Reader(data, offset)
        action_count = reader.count("ActionData actionNames", MAX_ACTIONS)
        if not action_count:
            return None
        action_names = []
        name_offsets = []
        for _ in range(action_count):
            name, name_offset = reader.aligned_string()
            # PlayMaker ActionData can contain title-specific/custom action
            # names alongside standard namespace-qualified AOT actions. Only
            # the target action itself must exactly match a known type.
            if not _ascii_text(name, MAX_STRING_BYTES):
                return None
            action_names.append(name)
            name_offsets.append(name_offset)
        matching = [index for index, name in enumerate(action_names)
                    if name in TARGET_ACTIONS]
        if not matching:
            return None

        custom_count = reader.count("ActionData customNames", MAX_ACTIONS)
        if custom_count != action_count:
            return None
        custom_names = [reader.aligned_string()[0] for _ in range(custom_count)]
        if any(not _ascii_text(value, MAX_STRING_BYTES, allow_empty=True)
               for value in custom_names):
            return None

        enabled = reader.bool_array("ActionData actionEnabled", MAX_ACTIONS)
        is_open = reader.bool_array("ActionData actionIsOpen", MAX_ACTIONS)
        if len(enabled) != action_count or len(is_open) != action_count:
            return None
        start_count = reader.count("ActionData actionStartIndex", MAX_ACTIONS)
        if start_count != action_count:
            return None
        start_indices = [reader.i32() for _ in range(start_count)]
        if (not start_indices or start_indices[0] != 0 or
                any(value < 0 or value > MAX_PARAMETERS for value in start_indices) or
                any(left > right for left, right in zip(start_indices, start_indices[1:]))):
            return None
        hash_count = reader.count("ActionData actionHashCodes", MAX_ACTIONS)
        if hash_count != action_count:
            return None
        hash_codes = [reader.u32() for _ in range(hash_count)]
        return {
            "offset": offset, "prefix_size": reader.pos - offset,
            "action_names": action_names, "action_name_offsets": name_offsets,
            "custom_names": custom_names, "enabled": enabled, "is_open": is_open,
            "start_indices": start_indices, "hash_codes_u32": hash_codes,
            "matching_action_indices": matching,
        }
    except (ValueError, struct.error):
        return None


def _parse_state_header(data: bytes, offset: int, expected_end: int) -> dict | None:
    try:
        reader = Reader(data, offset)
        name, name_offset = reader.aligned_string()
        description, description_offset = reader.aligned_string()
        if (not _ascii_text(name, 128) or
                not _ascii_text(description, 1024, allow_empty=True)):
            return None
        color_index = reader.i32()
        rect = [reader.f32() for _ in range(4)]
        if abs(color_index) > 10_000 or any(abs(value) > 1e7 for value in rect):
            return None
        flags = {
            "breakpoint": reader.bool32("FsmState.isBreakpoint"),
            "sequence": reader.bool32("FsmState.isSequence"),
            "hide_unused": reader.bool32("FsmState.hideUnused"),
        }
        count = reader.count("FsmState.transitions", 256)
        transitions = []
        for _ in range(count):
            transition = _parse_transition(reader)
            if (not _ascii_text(transition["event"], 128, allow_empty=True) or
                    not _ascii_text(transition["to_state"], 128, allow_empty=True)):
                return None
            transitions.append({key: transition[key] for key in (
                "event", "is_system_event", "is_global", "to_state",
                "link_style", "link_constraint", "color_index")})
        if reader.pos != expected_end:
            return None
        return {
            "name": name, "name_offset": name_offset,
            "description": description, "description_offset": description_offset,
            "offset": offset, "color_index": color_index, "rect": rect,
            **flags, "transitions": transitions,
        }
    except (ValueError, struct.error):
        return None


def find_state_header(data: bytes, actiondata_offset: int) -> list[dict]:
    """Find state headers that end exactly at a validated ActionData prefix."""
    if len(data) > MAX_COMPONENT_BYTES:
        return []
    begin = max(32, actiondata_offset - MAX_STATE_HEADER_BYTES) & ~3
    matches = []
    for offset in range(begin, actiondata_offset, 4):
        # Cheap byte-level filter before the bounded structured parse.
        if offset + 8 > actiondata_offset:
            continue
        name_length = struct.unpack_from("<i", data, offset)[0]
        if not 1 <= name_length <= 128:
            continue
        name_end = offset + 4 + name_length
        if name_end > actiondata_offset:
            continue
        name_bytes = data[offset + 4:name_end]
        if any(value < 0x20 or value > 0x7E for value in name_bytes):
            continue
        header = _parse_state_header(data, offset, actiondata_offset)
        if header is not None:
            matches.append(header)
    return matches


def _classify_script(asset: Asset, mono: dict, global_scripts: dict[int, dict],
                     local_scripts: dict[int, dict], ggm_name: str) -> dict | None:
    script_file = mono["script_file"]
    if script_file == 0:
        return local_scripts.get(mono["script_id"])
    external = asset.external(script_file)
    if external and Path(external).name.lower() == ggm_name.lower():
        return global_scripts.get(mono["script_id"])
    return None


def _object_identity(asset: Asset, path_id: int, script: dict, mono: dict,
                     blob: bytes) -> dict:
    class_name = script["class_name"]
    identity = {
        "object_class": class_name,
        "path_id": path_id,
        "game_object_path_id": mono["game_id"],
        "game_object_name": None,
        "fsm_name": None,
        "template_name": None,
        "template_header_status": None,
    }
    if mono["game_id"] in asset.objects:
        try:
            identity["game_object_name"] = asset.gameobject(mono["game_id"])["name"]
        except (ValueError, KeyError, struct.error):
            pass
    if class_name == "PlayMakerFSM":
        identity["fsm_name"] = Reader(blob, 44).aligned_string()[0]
    else:
        try:
            header = parse_fsm_template_header(blob)
            identity["template_name"] = header["name"]
            identity["fsm_name"] = header["fsm_name"]
            identity["template_header_status"] = "decoded"
        except (ValueError, struct.error) as exc:
            try:
                template_name, _ = _aligned_cstring(blob, 32)
                identity["template_name"] = "".join(
                    char for char in template_name if " " <= char <= "~")
            except (ValueError, UnicodeDecodeError):
                pass
            identity["template_header_status"] = "partial: " + str(exc)
    return identity


def _decode_full_action_data(blob: bytes, prefix: dict) -> tuple[dict | None, str | None]:
    try:
        reader = Reader(blob, prefix["offset"])
        action_data = parse_action_data(reader, salvage_unknown_parameters=True)
        if (action_data["action_names"] != prefix["action_names"] or
                action_data["enabled"] != prefix["enabled"] or
                action_data["is_open"] != prefix["is_open"] or
                action_data["start_indices"] != prefix["start_indices"] or
                action_data["hash_codes_u32"] != prefix["hash_codes_u32"]):
            return None, "full ActionData disagrees with validated prefix"
        encoded = encode_action_data(action_data)
        if encoded != blob[prefix["offset"]:reader.pos]:
            return None, "ActionData encode/decode round-trip mismatch"
        return action_data, None
    except (ValueError, struct.error) as exc:
        return None, str(exc)


def _target_action_parameters(action_data: dict | None, prefix: dict,
                              action_index: int) -> list[dict] | None:
    if action_data is None:
        return None
    start = prefix["start_indices"][action_index]
    end = (prefix["start_indices"][action_index + 1]
           if action_index + 1 < len(prefix["start_indices"])
           else len(action_data["parameters"]))
    if not start <= end <= len(action_data["parameters"]):
        return None
    return action_data["parameters"][start:end]


def scan(globalgamemanagers: Path, asset_paths: list[Path], *,
         module_path: Path | None = None, metadata_path: Path | None = None) -> dict:
    if (module_path is None) != (metadata_path is None):
        raise ValueError("module and metadata must be supplied together")
    ggm = Asset(globalgamemanagers)
    global_scripts = {path_id: monoscript(ggm.obj(path_id))
                      for path_id in ggm.ids(115)}
    resolver = None
    if module_path and metadata_path:
        resolver = TypeResolver(module_path.read_bytes(), metadata_path.read_bytes())

    rows = []
    object_counts: Counter[str] = Counter()
    raw_string_counts: Counter[str] = Counter()
    unmapped_raw_occurrences = []
    parse_errors = []
    files = [globalgamemanagers, *asset_paths]
    for path in files:
        asset = Asset(path)
        local_scripts = {path_id: monoscript(asset.obj(path_id))
                         for path_id in asset.ids(115)}
        asset_hash = hashlib.sha256(asset.data).hexdigest()
        for path_id in asset.ids(114):
            try:
                mono = asset.mono(path_id)
                script = _classify_script(asset, mono, global_scripts,
                                          local_scripts, globalgamemanagers.name)
                if (script is None or script["assembly"] != "PlayMaker.dll" or
                        script["class_name"] not in ("PlayMakerFSM", "FsmTemplate")):
                    continue
                blob = asset.obj(path_id)
                if len(blob) > MAX_COMPONENT_BYTES:
                    parse_errors.append({"asset": path.name, "path_id": path_id,
                                         "error": "PlayMaker object exceeds scanner byte limit"})
                    continue
                identity = _object_identity(asset, path_id, script, mono, blob)
                object_counts[script["class_name"]] += 1
                for name in TARGET_ACTION_NAMES:
                    raw_string_counts[name] += blob.count((ACTION_PREFIX + name).encode("ascii"))

                candidates = []
                for offset in range(32, len(blob) - 8, 4):
                    action_count = struct.unpack_from("<i", blob, offset)[0]
                    if not 1 <= action_count <= MAX_ACTIONS:
                        continue
                    first_length = struct.unpack_from("<i", blob, offset + 4)[0]
                    if not 1 <= first_length <= 256 or offset + 8 + first_length > len(blob):
                        continue
                    if blob[offset + 8:offset + 8 + len(ACTION_PREFIX)] != ACTION_PREFIX.encode("ascii"):
                        continue
                    prefix = parse_actiondata_prefix(blob, offset)
                    if prefix is not None:
                        candidates.append(prefix)

                validated_name_offsets = {
                    (prefix["action_name_offsets"][index] + 4,
                     prefix["action_names"][index])
                    for prefix in candidates
                    for index in prefix["matching_action_indices"]
                }
                for name in TARGET_ACTION_NAMES:
                    encoded_name = (ACTION_PREFIX + name).encode("ascii")
                    offset = blob.find(encoded_name)
                    while offset >= 0:
                        if (offset, ACTION_PREFIX + name) not in validated_name_offsets:
                            unmapped_raw_occurrences.append({
                                "asset": path.name, "asset_sha256": asset_hash,
                                **identity, "action_name": ACTION_PREFIX + name,
                                "byte_offset": offset,
                            })
                        offset = blob.find(encoded_name, offset + 1)

                for prefix in candidates:
                    state_matches = find_state_header(blob, prefix["offset"])
                    if len(state_matches) != 1:
                        parse_errors.append({
                            "asset": path.name, "path_id": path_id,
                            "actiondata_offset": prefix["offset"],
                            "error": "state header is unresolved or ambiguous",
                            "candidate_count": len(state_matches),
                        })
                        continue
                    state = state_matches[0]
                    action_data, full_error = _decode_full_action_data(blob, prefix)
                    if action_data is not None and resolver is not None:
                        for index, action_name in enumerate(prefix["action_names"]):
                            if action_name not in TARGET_ACTIONS:
                                continue
                            fields = resolver.action_fields(action_name)
                            params = _target_action_parameters(action_data, prefix, index)
                            serialized_fields = fields[:len(params)] if params is not None else []
                            if params is None or [item["name"] for item in params] != [
                                    item["name"] for item in serialized_fields]:
                                full_error = "decoded parameters do not match AOT field names"
                                action_data = None
                                break
                            for param, field in zip(params, serialized_fields):
                                if param["type"] != field["type"]:
                                    full_error = "decoded parameter type disagrees with AOT metadata"
                                    action_data = None
                                    break
                            if action_data is None:
                                break

                    for index in prefix["matching_action_indices"]:
                        name = prefix["action_names"][index]
                        parameters = _target_action_parameters(action_data, prefix, index)
                        if parameters is None and index + 1 < len(prefix["start_indices"]):
                            parameters = {"count": prefix["start_indices"][index + 1] -
                                          prefix["start_indices"][index]}
                        elif parameters is None:
                            parameters = None
                        rows.append({
                            "asset": path.name,
                            "asset_sha256": asset_hash,
                            **identity,
                            "state_name": state["name"],
                            "state_path_offset": state["offset"],
                            "state_transitions": state["transitions"],
                            "actiondata_offset": prefix["offset"],
                            "actiondata_prefix_size": prefix["prefix_size"],
                            "actiondata_total_size": (
                                action_data["size"] if action_data is not None else None),
                            "action_count": len(prefix["action_names"]),
                            "actiondata_action_names": prefix["action_names"],
                            "actiondata_custom_names": prefix["custom_names"],
                            "actiondata_parameter_count": (
                                len(action_data["parameters"]) if action_data is not None
                                else None),
                            "action_name_index": index,
                            "action_name_offset": prefix["action_name_offsets"][index],
                            "action_name_content_offset": (
                                prefix["action_name_offsets"][index] + 4),
                            "action_name": name,
                            "custom_name": prefix["custom_names"][index],
                            "enabled": prefix["enabled"][index],
                            "is_open": prefix["is_open"][index],
                            "action_start_index": prefix["start_indices"][index],
                            "action_hash_code_u32": prefix["hash_codes_u32"][index],
                            "actiondata_decode_status": (
                                (("complete; byte-for-byte round-trip verified"
                                  if not action_data["unknown_parameter_type_codes"] and
                                  not any(isinstance(item["value"], dict) and
                                          item["value"].get("decoded") is False
                                          for item in action_data["parameters"])
                                  else "round-trip verified; some parameter fields remain opaque")
                                 if action_data is not None else "prefix only")),
                            "actiondata_decode_error": full_error,
                            "parameters": _public_json(parameters),
                        })
            except (ValueError, KeyError, struct.error) as exc:
                parse_errors.append({"asset": path.name, "path_id": path_id,
                                     "error": str(exc)})

    counts = Counter(row["action_name"].rsplit(".", 1)[-1] for row in rows)
    actiondata_blocks = {}
    for row in rows:
        key = (row["asset"], row["path_id"], row["actiondata_offset"])
        actiondata_blocks[key] = row["actiondata_decode_status"]
    full_count = sum("round-trip verified" in status
                     for status in actiondata_blocks.values())
    full_semantic_count = sum(status.startswith("complete")
                              for status in actiondata_blocks.values())
    aot_fields = None
    if resolver is not None:
        aot_fields = {}
        for name in TARGET_ACTION_NAMES:
            try:
                aot_fields[name] = resolver.action_fields(ACTION_PREFIX + name)
            except ValueError as exc:
                aot_fields[name] = {"metadata_status": str(exc)}
    return {
        "title": "The Forest PS4 CUSA12398 v1.15",
        "scope": {
            "files_scanned": len(files),
            "PlayMakerFSM_components": object_counts["PlayMakerFSM"],
            "FsmTemplate_objects": object_counts["FsmTemplate"],
            "raw_target_string_occurrences_in_PlayMaker_objects": dict(sorted(raw_string_counts.items())),
            "validated_actiondata_blocks_with_targets": len(actiondata_blocks),
            "validated_serialized_action_instances": len(rows),
            "actiondata_blocks_round_tripped_byte_for_byte": full_count,
            "actiondata_blocks_fully_semantic": full_semantic_count,
            "target_action_instance_counts": dict(sorted(counts.items())),
            "aot_fields_are_metadata_only": True,
        },
        "aot_action_fields": aot_fields,
        "source_files": [
            {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in files
        ],
        "instances": rows,
        "unmapped_raw_action_name_occurrences": unmapped_raw_occurrences,
        "parse_errors": parse_errors,
        "limitations": [
            "the ActionData name list and enclosing state header are validated independently of action AOT presence",
            "complete ActionData decoding is limited to the explicitly supported specialized arrays and parameter type codes",
            "raw asset strings are counted separately and do not count as serialized instances",
            "a serialized action or a successful offline round-trip does not prove that a new FSM can be loaded or activated at runtime",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--globalgamemanagers", type=Path, required=True)
    parser.add_argument("--asset", type=Path, action="append", required=True,
                        help="asset, scene, prefab container or resources.assets; repeatable")
    parser.add_argument("--module", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = scan(args.globalgamemanagers, args.asset,
                      module_path=args.module, metadata_path=args.metadata)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (OSError, ValueError, KeyError, struct.error) as exc:
        print(f"PlayMaker action scan rejected input: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
