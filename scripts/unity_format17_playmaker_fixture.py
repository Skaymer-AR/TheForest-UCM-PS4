#!/usr/bin/env python3
"""Synthetic Unity 5.6 PlayMakerFSM *container* fixture (offline only).

The FSM's 40-byte tail has no established semantic layout. Zero bytes here
are explicit synthetic placeholders, NOT a claimed valid PlayMaker default.
Neither a commercial asset nor an editor-importable component is generated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_unity_rewired_assets import Asset, monoscript
from inspect_playmaker_fsm_assets import (
    build_synthetic_graphic_playmaker_component,
    encode_fsm_component,
    parse_fsm_component,
)
from unity_format17_fixture import (
    _asset_bytes, _gameobject, _transform, _string, _read_transform,
    GAMEOBJECT_ID, TRANSFORM_ID, MONOBEHAVIOUR_ID, MONOSCRIPT_ID,
    UNITY_VERSION,
)

SCENE_FILE = "synthetic_playmaker_scene.assets"
LIBRARY_FILE = "synthetic_playmaker_library.assets"
SCENE_NAME = "Synthetic PlayMaker Menu (not importable)"
REWRITTEN_NAME = "Synthetic PlayMaker Menu (AssetsTools.NET rewrite)"
SCRIPT_ASSEMBLY = "SyntheticOnly.dll"
ACTION_NAMES = (
    "HutongGames.PlayMaker.Actions.GUIBox",
    "HutongGames.PlayMaker.Actions.GUILabel",
)


def build_fixture(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    # The assembly is deliberately non-existent. This tests the container and
    # script identity *fields*, not class resolution or execution in Unity.
    library, _ = _asset_bytes([
        (MONOSCRIPT_ID, 115, _string("PlayMakerFSM") + bytes(20) +
         _string("PlayMakerFSM") + _string("") +
         _string(SCRIPT_ASSEMBLY) + b"\0"),
    ])
    component = build_synthetic_graphic_playmaker_component(
        bytes(40), game_object_path_id=GAMEOBJECT_ID,
        script_file_id=1, mono_script_path_id=MONOSCRIPT_ID)
    scene, _ = _asset_bytes([
        (GAMEOBJECT_ID, 1, _gameobject(
            SCENE_NAME, [(0, TRANSFORM_ID), (0, MONOBEHAVIOUR_ID)])),
        (TRANSFORM_ID, 4, _transform(GAMEOBJECT_ID)),
        (MONOBEHAVIOUR_ID, 114, component),
    ], external_paths=[LIBRARY_FILE], script_types=[(1, MONOSCRIPT_ID)])
    (directory / SCENE_FILE).write_bytes(scene)
    (directory / LIBRARY_FILE).write_bytes(library)
    return {
        "format": 17, "unity_version": UNITY_VERSION,
        "scene": SCENE_FILE, "library": LIBRARY_FILE,
        "synthetic_only": True,
        "unknown_fsm_tail_semantics": True,
        "component_size": len(component),
        "component_sha256": hashlib.sha256(component).hexdigest(),
    }


def validate_fixture(scene_path: Path, library_path: Path, *,
                     expected_name: str = SCENE_NAME) -> dict:
    scene = Asset(scene_path)
    library = Asset(library_path)
    if scene.version != UNITY_VERSION or library.version != UNITY_VERSION:
        raise ValueError("Unity version mismatch")
    if len(scene.objects) != 3 or len(library.objects) != 1:
        raise ValueError("Unity object count mismatch")
    expected_classes = {
        GAMEOBJECT_ID: 1, TRANSFORM_ID: 4, MONOBEHAVIOUR_ID: 114,
    }
    if any(scene.objects[path].class_id != class_id
           for path, class_id in expected_classes.items()):
        raise ValueError("Unity object classes mismatch")
    if library.objects[MONOSCRIPT_ID].class_id != 115:
        raise ValueError("external MonoScript class mismatch")

    go = scene.gameobject(GAMEOBJECT_ID)
    if (go["name"] != expected_name or not go["active"] or
            go["components"] != [(0, TRANSFORM_ID),
                                 (0, MONOBEHAVIOUR_ID)]):
        raise ValueError("GameObject component/name graph mismatch")
    transform = _read_transform(scene, TRANSFORM_ID)
    if (transform["gameobject"] != (0, GAMEOBJECT_ID) or
            transform["father"] != (0, 0) or transform["children"] != 0):
        raise ValueError("Transform ownership or hierarchy mismatch")
    mb = scene.mono(MONOBEHAVIOUR_ID)
    if ((mb["game_file"], mb["game_id"]) != (0, GAMEOBJECT_ID) or
            not mb["enabled"] or
            (mb["script_file"], mb["script_id"]) != (1, MONOSCRIPT_ID)):
        raise ValueError("MonoBehaviour base fields or PPtrs mismatch")
    if scene.external(1) != LIBRARY_FILE:
        raise ValueError("MonoScript dependency mismatch")
    script = monoscript(library.obj(MONOSCRIPT_ID))
    if (script["class_name"] != "PlayMakerFSM" or
            script["namespace"] != "" or script["assembly"] != SCRIPT_ASSEMBLY):
        raise ValueError("synthetic MonoScript identity mismatch")

    component = scene.obj(MONOBEHAVIOUR_ID)
    fsm = parse_fsm_component(component)
    if encode_fsm_component(fsm) != component:
        raise ValueError("PlayMakerFSM codec round-trip changed bytes")
    if fsm["name"] != "UCM_Menu_Synthetic" or len(fsm["states"]) != 1:
        raise ValueError("synthetic PlayMakerFSM state/name mismatch")
    actions = fsm["states"][0]["action_data"]["action_names"]
    if actions != list(ACTION_NAMES):
        raise ValueError("synthetic GUIBox/GUILabel action list mismatch")
    if (fsm["_opaque_fsm_tail"] != bytes(40) or
            fsm["fsm_template_pointer"]["file_id"] != 0 or
            fsm["fsm_template_pointer"]["path_id"] != 0):
        raise ValueError("opaque tail placeholder or template pointer mismatch")
    if component[:12] != struct.pack("<iq", 0, GAMEOBJECT_ID):
        raise ValueError("component owner PPtr mismatch")

    return {
        "format": 17, "unity_version": scene.version,
        "component_size": len(component),
        "component_sha256": hashlib.sha256(component).hexdigest(),
        "action_names": actions,
        "synthetic_only": True, "unknown_fsm_tail_semantics": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("directory", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("scene", type=Path)
    verify.add_argument("library", type=Path)
    verify.add_argument("--expected-name", default=SCENE_NAME)
    args = parser.parse_args()
    if args.command == "build":
        result = build_fixture(args.directory)
    else:
        result = validate_fixture(args.scene, args.library,
                                  expected_name=args.expected_name)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
