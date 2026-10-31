#!/usr/bin/env python3
"""Offline conflict preflight for the *serialized*, not live, DS4 ControllerMaps.

Consumes only the already-derived, noncommercial Rewired JSON report. It
cannot establish effective runtime Player/controller/category/focus state and
must never mark the menu hotkey 'safe' or feed buttons to an in-game provider.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PINNED_ASSET = "f2b4c877b11b999ab590d71cb2682a017fb44c21720673487de288ff7c05e321"
PINNED_GUIDS = (
    "83b427e4-086f-47f3-bb06-be266abd1ca5",
    "cd9718bf-a87a-44bc-8716-60a0def28a9f",
)
# DS4 hardware element IDs from the original, verified SonyDualShock4 profile.
MENU_ELEMENTS = {
    6: "Cross", 7: "Circle", 10: "L1", 11: "R1",
    18: "D-Pad Up", 19: "D-Pad Right",
    20: "D-Pad Down", 21: "D-Pad Left",
}
CHORD_IDS = (10, 11)


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(detail)


def inspect(source: dict) -> dict:
    """Build conservative per-manager/per-GUID collision candidates.

    Enabled defaults are serialized Player_Editor *initial settings*, not
    evidence of the live Player, the selected layout or input consumption.
    The result intentionally exposes no 'allow menu' decision.
    """
    _require(source.get("title") == "The Forest PS4 CUSA12398 v1.15",
             "unexpected title/version in derived Rewired data")
    _require(source.get("asset", {}).get("sha256") == PINNED_ASSET,
             "unexpected sharedassets0 SHA-256")
    _require(source.get("hardware_profile") == "SonyDualShock4",
             "unexpected hardware profile")
    _require(sorted(source.get("hardware_guid_identifiers", [])) ==
             sorted(PINNED_GUIDS), "unexpected DS4 GUID set")
    ids = source.get("element_identifier_ids", {})
    for element_id, expected in MENU_ELEMENTS.items():
        _require(ids.get(str(element_id)) == expected,
                 f"invalid DS4 element identity {element_id}")
    managers = source.get("input_managers")
    _require(isinstance(managers, list) and bool(managers),
             "no input managers in derived report")

    result = []
    seen_managers = set()
    total_bindings = 0
    chord_exposure_groups = 0
    for manager in managers:
        name = manager.get("prefab")
        _require(name in ("Rewired Input Manager VR", "Rewired Input Manager XInput")
                 and name not in seen_managers, "unknown or duplicate input manager")
        seen_managers.add(name)
        player = manager.get("serialized_player_default", {})
        defaults = player.get("default_joystick_maps")
        _require(isinstance(defaults, list), "missing serialized Player defaults")
        enabled_defaults: set[tuple[int, int]] = set()
        for entry in defaults:
            _require(type(entry.get("enabled")) is bool,
                     "invalid serialized Player map-enable flag")
            category, layout = entry.get("category_id"), entry.get("layout_id")
            _require(type(category) is int and type(layout) is int,
                     "invalid category/layout ID")
            key = (category, layout)
            _require(key not in enabled_defaults or not entry["enabled"],
                     "duplicate enabled serialized Player default map")
            if entry["enabled"]:
                enabled_defaults.add(key)

        maps = manager.get("ds4_maps")
        _require(isinstance(maps, list), "missing DS4 map collection")
        seen_map_ids = set()
        grouped: dict[str, list[dict]] = {guid: [] for guid in PINNED_GUIDS}
        menu_toggle_mapped = False
        for controller_map in maps:
            guid = controller_map.get("hardware_guid")
            _require(guid in grouped, "unknown serialized controller GUID")
            map_id = controller_map.get("map_id")
            _require(type(map_id) is int and map_id not in seen_map_ids,
                     "invalid or duplicate controller-map ID")
            seen_map_ids.add(map_id)
            key = (controller_map.get("category_id"), controller_map.get("layout_id"))
            entries = controller_map.get("action_element_maps")
            _require(isinstance(entries, list) and
                     len(entries) == controller_map.get("action_element_map_count"),
                     "ActionElementMap count mismatch")
            if any(entry.get("action_name") == "MenuToggle" for entry in entries):
                menu_toggle_mapped = True
            if key not in enabled_defaults:
                continue
            for entry in entries:
                element_id = entry.get("element_identifier_id")
                if element_id not in MENU_ELEMENTS:
                    continue
                _require(entry.get("element_identifier_name") == MENU_ELEMENTS[element_id],
                         "DS4 element label/ID mismatch")
                action = entry.get("action_name")
                _require(isinstance(action, str) and bool(action),
                         "missing action name")
                grouped[guid].append({
                    "controller_map_id": map_id,
                    "map_category": controller_map.get("category_name"),
                    "layout": controller_map.get("layout_name"),
                    "element_id": element_id,
                    "element": MENU_ELEMENTS[element_id],
                    "element_type": entry.get("element_type"),
                    "action_id": entry.get("action_id"),
                    "action": action,
                })
        for guid in PINNED_GUIDS:
            bindings = grouped[guid]
            chord_ids_present = {entry["element_id"] for entry in bindings}
            chord_exposure = all(code in chord_ids_present for code in CHORD_IDS)
            if chord_exposure:
                chord_exposure_groups += 1
            total_bindings += len(bindings)
            result.append({
                "input_manager": name,
                "hardware_guid": guid,
                "player_default_map_selection_only": True,
                "l1_r1_both_assigned_in_enabled_defaults": chord_exposure,
                "candidate_binding_count": len(bindings),
                "candidate_bindings": bindings,
                "menu_toggle_has_serialized_ds4_binding": menu_toggle_mapped,
                "runtime_safe_to_intercept_input": None,
            })
    return {
        "title": source["title"],
        "origin": "previously verified serialized Unity 5.6.6f2 Rewired data",
        "risk_assessment": "potential input overlaps, not observed runtime collisions",
        "candidate_bindings_total": total_bindings,
        "manager_guid_groups_with_l1_and_r1_candidates": chord_exposure_groups,
        "input_contexts": result,
        "required_runtime_gates": [
            "verified title-owned Unity callback on correct thread",
            "actual local Player identity and live connected controller",
            "selected manager, hardware GUID, category, layout and map enablement",
            "effective per-ActionElementMap enablement and runtime input focus",
            "gameplay-input consumption or noninterference proof while menu open",
            "verified callback unregister and quiescent teardown",
        ],
        "menu_installable_or_tested": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derived", type=Path,
                        default=Path("docs/REWIRED_CONTROLLER_MAPS_20261030.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect(json.loads(args.derived.read_text(encoding="utf-8")))
        blob = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(blob, encoding="utf-8")
        else:
            print(blob, end="")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, "rewired-menu-conflicts: %s\n" % exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
