#!/usr/bin/env python3
"""Read-only decoder for this title's serialized Rewired joystick maps.

This is deliberately pinned to the verified sharedassets0 input-manager
asset. It decodes only the ControllerMap_Editor envelope and the first four
ActionElementMap words (action category, action, element type, element ID).
The remaining seven words of each 44-byte record are left uninterpreted.
Serialized defaults do not prove a live Player assignment or active map.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_ds4_hardware_elements import EXPECTED_IDS, inspect as inspect_ds4  # noqa: E402
from inspect_unity_rewired_assets import Asset, analyze  # noqa: E402

SHAREDASSETS0_SHA256 = "f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321"
ACTION_ELEMENT_MAP_SIZE = 44
ACTION_ID_UNASSIGNED = 0xFFFFFFFF
CONTROLLER_ELEMENT_TYPES = {0: "Axis", 1: "Button"}
UUID = re.compile(rb"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)
DS4_NAME_BY_ID = {element_id: name for name, element_id in EXPECTED_IDS.items()}
EXPECTED_MANAGER_MAP_COUNTS = {
    "Rewired Input Manager VR": (13, 4),
    "Rewired Input Manager XInput": (9, 9),
}


def _read_map_candidate(data: bytes, guid_match: re.Match[bytes]) -> dict:
    """Decode one map whose serialized name is empty in this pinned title."""
    guid_at = guid_match.start()
    if guid_at < 20 or struct.unpack_from("<I", data, guid_at - 4)[0] != 36:
        raise ValueError("ControllerMap hardware GUID string prefix is invalid")
    start = guid_at - 20
    map_id, category_id, layout_id = struct.unpack_from("<iii", data, start)
    name, after_name = _aligned_string(data, start + 12)
    guid, after_guid = _aligned_string(data, after_name)
    if name != "" or after_name != start + 16:
        raise ValueError("unexpected ControllerMap_Editor name/layout")
    if guid.lower() != guid_match.group().decode("ascii").lower():
        raise ValueError("ControllerMap GUID candidate mismatch")
    if after_guid != start + 56 or after_guid + 8 > len(data):
        raise ValueError("unexpected ControllerMap_Editor header size")
    custom_controller_uid, count = struct.unpack_from("<ii", data, after_guid)
    if map_id < 0 or category_id < 0 or layout_id < 0 or custom_controller_uid < 0:
        raise ValueError("negative ControllerMap_Editor identifier")
    if count < 0 or count > 512:
        raise ValueError("ActionElementMap count outside safe bounds")
    records_at = after_guid + 8
    end = records_at + count * ACTION_ELEMENT_MAP_SIZE
    if end > len(data):
        raise ValueError("truncated ActionElementMap list")
    return {
        "start": start,
        "end": end,
        "map_id": map_id,
        "category_id": category_id,
        "layout_id": layout_id,
        "hardware_guid": guid.lower(),
        "custom_controller_uid": custom_controller_uid,
        "action_element_map_count": count,
        "records_at": records_at,
    }


def _aligned_string(data: bytes, offset: int) -> tuple[str, int]:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("truncated aligned string")
    size = struct.unpack_from("<i", data, offset)[0]
    if size < 0 or size > 16384 or offset + 4 + size > len(data):
        raise ValueError("invalid aligned string size")
    raw = data[offset + 4:offset + 4 + size]
    value = raw.decode("ascii")
    end = offset + 4 + size
    return value, (end + 3) & ~3


def _action_names_by_id(actions: dict[str, int]) -> dict[int, str]:
    result: dict[int, str] = {}
    for name, action_id in actions.items():
        if action_id in result and result[action_id] != name:
            raise ValueError(f"conflicting names for Rewired action ID {action_id}")
        result[action_id] = name
    return result


def _printable_ascii(value: str) -> bool:
    return all(0x20 <= ord(char) <= 0x7E for char in value)


def _read_action_catalog_and_categories(
    data: bytes, expected_actions: dict[str, int]
) -> tuple[dict[int, dict], list[dict]]:
    """Decode the serialized InputAction and InputCategory records.

    The list starts at the uniquely validated MenuToggle action. Its field
    order follows this title's Rewired.InputAction metadata. The
    following InputCategory list supplies names for ActionElementMap category
    IDs, separate from ControllerMap map-category IDs.
    """
    marker = b"MenuToggle"
    name_at = data.find(marker)
    if name_at < 8 or data.find(marker, name_at + 1) >= 0:
        raise ValueError("expected one serialized MenuToggle action name")
    if struct.unpack_from("<I", data, name_at - 4)[0] != len(marker):
        raise ValueError("MenuToggle aligned-string prefix mismatch")
    first_action = name_at - 8
    count_at = first_action - 4
    if count_at < 0:
        raise ValueError("InputAction list count is missing")
    count = struct.unpack_from("<i", data, count_at)[0]
    if count != len(expected_actions) or count < 1 or count > 256:
        raise ValueError("InputAction list count does not match the action catalog")

    by_id: dict[int, dict] = {}
    names: dict[str, int] = {}
    pos = first_action
    for _ in range(count):
        if pos + 4 > len(data):
            raise ValueError("truncated InputAction ID")
        action_id = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        name, pos = _aligned_string(data, pos)
        if pos + 4 > len(data):
            raise ValueError("truncated InputAction type")
        action_type = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        descriptive_name, pos = _aligned_string(data, pos)
        positive_name, pos = _aligned_string(data, pos)
        negative_name, pos = _aligned_string(data, pos)
        if pos + 12 > len(data):
            raise ValueError("truncated InputAction tail")
        behavior_id, user_assignable, category_id = struct.unpack_from(
            "<iii", data, pos)
        pos += 12
        if (action_id < 0 or action_type < 0 or behavior_id < 0
                or category_id < 0 or user_assignable not in (0, 1)
                or not name or not _printable_ascii(name)
                or not _printable_ascii(descriptive_name)
                or not _printable_ascii(positive_name)
                or not _printable_ascii(negative_name)):
            raise ValueError("invalid serialized InputAction record")
        if action_id in by_id or name in names:
            raise ValueError("duplicate InputAction ID or name")
        by_id[action_id] = {
            "id": action_id,
            "name": name,
            "type_id": action_type,
            "category_id": category_id,
        }
        names[name] = action_id

    if names != expected_actions:
        raise ValueError("serialized InputAction names/IDs differ from the action catalog")

    if pos + 4 > len(data):
        raise ValueError("InputCategory list count is missing")
    category_count = struct.unpack_from("<i", data, pos)[0]
    pos += 4
    if category_count < 1 or category_count > 64:
        raise ValueError("InputCategory list count outside bounds")
    categories = []
    category_ids = set()
    category_names = set()
    for _ in range(category_count):
        name, pos = _aligned_string(data, pos)
        descriptive_name, pos = _aligned_string(data, pos)
        tag, pos = _aligned_string(data, pos)
        if pos + 8 > len(data):
            raise ValueError("truncated InputCategory record")
        category_id, user_assignable = struct.unpack_from("<iI", data, pos)
        pos += 8
        if (not name or not _printable_ascii(name)
                or not _printable_ascii(descriptive_name)
                or not _printable_ascii(tag) or category_id < 0
                or user_assignable not in (0, 1)):
            raise ValueError("invalid serialized InputCategory record")
        if category_id in category_ids or name in category_names:
            raise ValueError("duplicate InputCategory ID or name")
        category_ids.add(category_id)
        category_names.add(name)
        categories.append({
            "id": category_id,
            "name": name,
            "descriptive_name": descriptive_name,
            "tag": tag,
            "user_assignable": bool(user_assignable),
        })
    category_by_id = {item["id"]: item for item in categories}
    if category_by_id.get(0, {}).get("name") != "Default":
        raise ValueError("InputCategory table has no Default/0 entry")
    if any(action["category_id"] not in category_by_id
           for action in by_id.values()):
        raise ValueError("InputAction references an unknown InputCategory ID")
    return by_id, categories


def _read_map_configuration(data: bytes, first_map_start: int,
                            expected_map_count: int) -> dict:
    """Resolve map category and joystick-layout names from InputManager data.

    The UserData field order and record shapes follow the pinned IL2CPP
    metadata: InputMapCategory fields followed by the four UserData
    layout lists. The candidate must end immediately before this ControllerMap
    list's count, so unrelated printable strings are not enough.
    """
    candidates = []
    for start in range(0, first_map_start - 4, 4):
        try:
            count = struct.unpack_from("<i", data, start)[0]
            if not 1 <= count <= 32:
                continue
            pos = start + 4
            categories = []
            for _ in range(count):
                name, pos = _aligned_string(data, pos)
                description, pos = _aligned_string(data, pos)
                tag, pos = _aligned_string(data, pos)
                category_id = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                user_assignable, check_all, conflict_count = struct.unpack_from(
                    "<IIi", data, pos)
                pos += 12
                if (not name or not _printable_ascii(name)
                        or not _printable_ascii(description)
                        or not _printable_ascii(tag)
                        or category_id < 0
                        or user_assignable not in (0, 1)
                        or check_all not in (0, 1)
                        or conflict_count < 0 or conflict_count > 64):
                    raise ValueError("invalid InputMapCategory record")
                if pos + conflict_count * 4 > first_map_start:
                    raise ValueError("truncated InputMapCategory conflict list")
                conflicts = list(struct.unpack_from(
                    "<" + "i" * conflict_count, data, pos)) if conflict_count else []
                pos += conflict_count * 4
                if any(value < 0 for value in conflicts):
                    raise ValueError("negative InputMapCategory conflict ID")
                categories.append({
                    "id": category_id,
                    "name": name,
                    "descriptive_name": description,
                    "tag": tag,
                    "user_assignable": bool(user_assignable),
                    "checks_conflicts_with_all_categories": bool(check_all),
                    "check_conflict_category_ids": conflicts,
                })
            category_by_id = {item["id"]: item for item in categories}
            if (len(category_by_id) != len(categories)
                    or len({item["name"] for item in categories}) != len(categories)
                    or category_by_id.get(0, {}).get("name") != "Default"
                    or not any(item["name"] == "Menu" for item in categories)):
                raise ValueError("map category identity table is ambiguous")
            if any(conflict not in category_by_id
                   for item in categories
                   for conflict in item["check_conflict_category_ids"]):
                raise ValueError("map category conflict references an unknown ID")

            layout_lists = []
            for _ in range(4):
                layout_count = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                if layout_count < 0 or layout_count > 64:
                    raise ValueError("layout count outside bounds")
                layouts = []
                for _ in range(layout_count):
                    name, pos = _aligned_string(data, pos)
                    description, pos = _aligned_string(data, pos)
                    layout_id = struct.unpack_from("<i", data, pos)[0]
                    pos += 4
                    if (not name or not _printable_ascii(name)
                            or not _printable_ascii(description) or layout_id < 0):
                        raise ValueError("invalid InputLayout record")
                    layouts.append({"id": layout_id, "name": name,
                                    "descriptive_name": description})
                by_id = {item["id"]: item for item in layouts}
                if (len(by_id) != len(layouts)
                        or len({item["name"] for item in layouts}) != len(layouts)):
                    raise ValueError("duplicate InputLayout ID or name")
                layout_lists.append(layouts)
            joystick_layout_by_id = {
                item["id"]: item for item in layout_lists[0]
            }
            if joystick_layout_by_id.get(0, {}).get("name") != "Default":
                raise ValueError("joystick layout table has no Default/0 entry")
            if pos + 4 != first_map_start:
                raise ValueError("map category/layout tables do not meet ControllerMap list")
            serialized_count = struct.unpack_from("<i", data, pos)[0]
            if serialized_count != expected_map_count:
                raise ValueError("InputManager ControllerMap list count mismatch")
            candidates.append({
                "map_categories": categories,
                "map_category_names": {item["id"]: item["name"] for item in categories},
                "joystick_layouts": layout_lists[0],
                "joystick_layout_names": {
                    item["id"]: item["name"] for item in layout_lists[0]
                },
                "other_layout_counts": {
                    "keyboard": len(layout_lists[1]),
                    "mouse": len(layout_lists[2]),
                    "custom_controller": len(layout_lists[3]),
                },
            })
        except (ValueError, UnicodeError, struct.error):
            continue
    if len(candidates) != 1:
        raise ValueError(f"expected one bounded map category/layout table, found {len(candidates)}")
    return candidates[0]


def _read_player_joystick_defaults(data: bytes, map_category_names: dict[int, str],
                                   joystick_layout_names: dict[int, str]) -> dict:
    """Read the single serialized Player_Editor and its default joystick maps."""
    candidates = []
    for match in re.finditer(rb"Player", data):
        name_offset = match.start() - 4
        player_start = name_offset - 4
        if name_offset < 0 or player_start < 4:
            continue
        try:
            if struct.unpack_from("<i", data, name_offset)[0] != 6:
                continue
            player_id = struct.unpack_from("<i", data, player_start)[0]
            name, pos = _aligned_string(data, name_offset)
            descriptive_name, pos = _aligned_string(data, pos)
            if name != "Player" or descriptive_name != "Player" or player_id < 0:
                continue
            start_playing = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            count = struct.unpack_from("<i", data, pos)[0]
            pos += 4
            if start_playing not in (0, 1) or count < 0 or count > 64:
                continue
            if pos + count * 12 > len(data):
                continue
            defaults = []
            for index in range(count):
                enabled, category_id, layout_id = struct.unpack_from(
                    "<iii", data, pos + index * 12)
                if (enabled not in (0, 1) or category_id not in map_category_names
                        or layout_id not in joystick_layout_names):
                    raise ValueError("Player default map references unknown ID")
                defaults.append({
                    "enabled": bool(enabled),
                    "category_id": category_id,
                    "category_name": map_category_names[category_id],
                    "layout_id": layout_id,
                    "layout_name": joystick_layout_names[layout_id],
                })
            if len({(item["category_id"], item["layout_id"])
                    for item in defaults}) != len(defaults):
                raise ValueError("duplicate Player default joystick map")
            candidates.append({
                "id": player_id,
                "name": name,
                "descriptive_name": descriptive_name,
                "start_playing": bool(start_playing),
                "default_joystick_maps": defaults,
            })
        except (ValueError, UnicodeError, struct.error):
            continue
    if len(candidates) != 1:
        raise ValueError(f"expected one serialized Player_Editor, found {len(candidates)}")
    return candidates[0]


def parse_controller_map_collection(
    data: bytes,
    actions: dict[str, int],
    ds4_hardware_guids: set[str],
    *,
    expected_map_count: int,
    expected_ds4_map_count: int,
) -> dict:
    """Parse the map list and return DS4 maps with action/element names joined.

    In this title's exact object layout, the map-list count precedes the first
    map, ControllerMap_Editor records are contiguous, and each nested
    ActionElementMap record is 44 bytes. The caller enforces the asset hash and
    links this blob to the verified Rewired.InputManager MonoBehaviour.
    """
    id_to_name = _action_names_by_id(actions)
    input_actions, action_categories = _read_action_catalog_and_categories(
        data, actions)
    action_category_names = {item["id"]: item["name"]
                             for item in action_categories}
    matches = list(UUID.finditer(data))
    if not matches:
        raise ValueError("no serialized ControllerMap hardware GUIDs found")
    maps = [_read_map_candidate(data, match) for match in matches]
    maps.sort(key=lambda item: item["start"])
    if len(maps) != expected_map_count:
        raise ValueError(f"expected {expected_map_count} maps, found {len(maps)}")
    if len({item["map_id"] for item in maps}) != len(maps):
        raise ValueError("duplicate ControllerMap ID")
    if struct.unpack_from("<i", data, maps[0]["start"] - 4)[0] != len(maps):
        raise ValueError("ControllerMap list count does not match its records")
    for current, following in zip(maps, maps[1:]):
        if current["end"] != following["start"]:
            raise ValueError("ControllerMap list records are not contiguous")
    if any(item["custom_controller_uid"] != 0 for item in maps):
        raise ValueError("unexpected custom-controller ControllerMap")

    config = _read_map_configuration(data, maps[0]["start"], len(maps))
    player = _read_player_joystick_defaults(
        data, config["map_category_names"], config["joystick_layout_names"])

    decoded_ds4 = []
    for item in maps:
        if item["category_id"] not in config["map_category_names"]:
            raise ValueError("ControllerMap references unknown map category")
        if item["layout_id"] not in config["joystick_layout_names"]:
            raise ValueError("ControllerMap references unknown joystick layout")
        is_ds4 = item["hardware_guid"] in ds4_hardware_guids
        elements = []
        for index in range(item["action_element_map_count"]):
            offset = item["records_at"] + index * ACTION_ELEMENT_MAP_SIZE
            words = struct.unpack_from("<11I", data, offset)
            action_category_id, action_id, element_type, element_id = words[:4]
            if action_category_id not in action_category_names:
                raise ValueError("ActionElementMap references unknown action category")
            if element_type not in CONTROLLER_ELEMENT_TYPES:
                raise ValueError(f"unknown ControllerElementType value {element_type}")
            if element_id > 0xFFFF:
                raise ValueError("ActionElementMap element ID outside bounds")
            if action_id != ACTION_ID_UNASSIGNED and action_id not in id_to_name:
                raise ValueError(f"ActionElementMap references unknown action ID {action_id}")
            if is_ds4 and element_id not in DS4_NAME_BY_ID:
                raise ValueError(f"DS4 map references unknown hardware element ID {element_id}")
            if is_ds4:
                elements.append({
                    "action_category_id": action_category_id,
                    "action_category_name": action_category_names[action_category_id],
                    "action_id": action_id,
                    "action_name": id_to_name.get(action_id),
                    "input_action_category_id": (
                        input_actions[action_id]["category_id"]
                        if action_id in input_actions else None),
                    "input_action_category_name": (
                        action_category_names[input_actions[action_id]["category_id"]]
                        if action_id in input_actions else None),
                    "element_type_id": element_type,
                    "element_type": CONTROLLER_ELEMENT_TYPES[element_type],
                    "element_identifier_id": element_id,
                    "element_identifier_name": DS4_NAME_BY_ID[element_id],
                })
        if is_ds4:
            decoded_ds4.append({
                "map_id": item["map_id"],
                "category_id": item["category_id"],
                "category_name": config["map_category_names"][item["category_id"]],
                "layout_id": item["layout_id"],
                "layout_name": config["joystick_layout_names"][item["layout_id"]],
                "hardware_guid": item["hardware_guid"],
                "action_element_map_count": item["action_element_map_count"],
                "action_element_maps": elements,
            })
    if len(decoded_ds4) != expected_ds4_map_count:
        raise ValueError(
            f"expected {expected_ds4_map_count} DS4 maps, found {len(decoded_ds4)}")
    return {
        "serialized_map_count": len(maps),
        "action_categories": action_categories,
        "map_categories": config["map_categories"],
        "joystick_layouts": config["joystick_layouts"],
        "other_layout_counts": config["other_layout_counts"],
        "serialized_player_default": player,
        "ds4_maps": decoded_ds4,
    }


def inspect(root: Path) -> dict:
    graph = analyze(root)
    source = next(item for item in graph["sources"]
                  if item["file"] == "sharedassets0.assets")
    if source["sha256"] != SHAREDASSETS0_SHA256:
        raise ValueError("sharedassets0 SHA-256 does not match the verified title pin")
    profile = inspect_ds4(root)
    if profile["sharedassets_sha256"] != SHAREDASSETS0_SHA256:
        raise ValueError("DS4 profile asset does not match the verified title pin")
    ds4_guids = set(profile["guid_identifiers"])

    shared = Asset(root / "sharedassets0.assets")
    output_managers = []
    found_names = set()
    for prefab in graph["input_manager_prefabs"].values():
        name = prefab["name"]
        if name not in EXPECTED_MANAGER_MAP_COUNTS:
            continue
        if name in found_names:
            raise ValueError(f"duplicate InputManager prefab {name}")
        found_names.add(name)
        expected_total, expected_ds4 = EXPECTED_MANAGER_MAP_COUNTS[name]
        manager_id = prefab["component_id"]
        if shared.objects.get(manager_id) is None or shared.objects[manager_id].class_id != 114:
            raise ValueError("InputManager component does not resolve to a MonoBehaviour")
        if set(prefab["matching_hardware_identifiers"]) != ds4_guids:
            raise ValueError("InputManager does not link to both verified Sony DS4 GUIDs")
        parsed = parse_controller_map_collection(
            shared.obj(manager_id), prefab["actions"], ds4_guids,
            expected_map_count=expected_total,
            expected_ds4_map_count=expected_ds4,
        )
        mapped_actions = {
            entry["action_name"]
            for controller_map in parsed["ds4_maps"]
            for entry in controller_map["action_element_maps"]
            if entry["action_name"] is not None
        }
        output_managers.append({
            "prefab": name,
            "prefab_path_id": next(
                int(path_id) for path_id, value in graph["input_manager_prefabs"].items()
                if value is prefab),
            "component_path_id": manager_id,
            "serialized_component_enabled": prefab["enabled"],
            "catalog_actions_without_ds4_element_map": sorted(
                set(prefab["actions"]) - mapped_actions),
            **parsed,
        })
    if found_names != set(EXPECTED_MANAGER_MAP_COUNTS):
        raise ValueError("did not resolve both title InputManager prefabs")
    output_managers.sort(key=lambda item: item["prefab"])
    return {
        "title": "The Forest PS4 CUSA12398 v1.15",
        "unity_version": graph["unity_version"],
        "asset": {
            "file": "sharedassets0.assets",
            "sha256": source["sha256"],
            "serialized_object_count": source["objects"],
        },
        "hardware_profile": profile["hardware_profile"],
        "hardware_guid_identifiers": profile["guid_identifiers"],
        "element_identifier_ids": {str(value): key for key, value in EXPECTED_IDS.items()},
        "controller_element_types": {str(key): value
                                      for key, value in CONTROLLER_ELEMENT_TYPES.items()},
        "input_managers": output_managers,
        "interpretation_limits": [
            "ControllerMap_Editor and ActionElementMap data are serialized InputManager configuration",
            "first four ActionElementMap words are decoded; trailing seven words are not interpreted",
            "ActionElementMap enabled state is not decoded",
            "ActionElementMap action categories, ControllerMap map categories/layouts, and Player defaults are decoded from UserData",
            "ActionElementMap action-category IDs are retained separately from each InputAction catalog category ID",
            "serialized Player defaults do not prove an active Player, connected DualShock 4, selected manager/map, focus, or runtime remap",
            "the output is not evidence of a PS4 input provider or in-game menu integration",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = json.dumps(inspect(args.assets_root), indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            print(report, end="")
        return 0
    except (OSError, ValueError, UnicodeError, struct.error, KeyError, StopIteration) as exc:
        parser.exit(2, f"rewired-controller-maps: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
