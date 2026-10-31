"""Synthetic-only tests for bounded PlayMaker component and graph parsing."""
from __future__ import annotations

import copy
import json
import struct
import sys
from types import SimpleNamespace
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_playmaker_fsm_assets as audit
import scan_playmaker_action_instances as scan_actions


def i32(value: int) -> bytes:
    return struct.pack("<i", value)


def il2cpp_type_record(data: int, kind: int) -> bytes:
    return struct.pack("<QI", data, kind << 16) + bytes(4)


class SyntheticNativeImage:
    def __init__(self, regions: dict[int, bytes]):
        self.regions = regions

    def read(self, address: int, size: int) -> bytes:
        for start, data in self.regions.items():
            if start <= address and address + size <= start + len(data):
                return data[address - start:address - start + size]
        raise ValueError("synthetic native address is outside mapped regions")


def string(value: str) -> bytes:
    raw = value.encode("utf-8")
    data = i32(len(raw)) + raw
    return data + bytes(-len(data) % 4)


def fsm_event(name: str) -> bytes:
    return string(name) + i32(0) + i32(1)


def transition(event: str, to_state: str) -> bytes:
    return fsm_event(event) + string(to_state) + i32(0) * 3


def action_data_empty() -> bytes:
    # One zero actionNames count plus the 26 zero words in the title's empty
    # cameraFadeFSM sentinel. The test fixture contains no retail bytes.
    return bytes(27 * 4)


def action_data_generic(action_name: str) -> bytes:
    data = bytearray()
    data += i32(1) + string(action_name)  # actionNames
    data += i32(1) + string("")          # customNames
    data += i32(1) + b"\x01\0\0\0"    # packed actionEnabled
    data += i32(1) + b"\x01\0\0\0"    # packed actionIsOpen
    data += i32(1) + i32(0)              # actionStartIndex
    data += i32(1) + i32(123)            # actionHashCodes
    data += bytes(len(audit.ACTIONDATA_SPECIAL_ARRAYS) * 4)
    data += i32(0)                       # byteData length
    data += bytes(4 * 4)                 # array/custom type arrays
    data += i32(0)                       # customTypeNames
    data += bytes(4 * 4)                 # parameter arrays
    return bytes(data)


def action_data_one_parameter(action_name: str, parameter_name: str,
                              type_code: int, payload: bytes) -> bytes:
    data = bytearray()
    data += i32(1) + string(action_name)
    data += i32(1) + string("")
    data += i32(1) + b"\x01\0\0\0"
    data += i32(1) + b"\x01\0\0\0"
    data += i32(1) + i32(0)
    data += i32(1) + i32(123)
    data += bytes(len(audit.ACTIONDATA_SPECIAL_ARRAYS) * 4)
    data += i32(len(payload)) + payload + bytes(-len(payload) % 4)
    data += bytes(4 * 4)                 # array/custom type arrays
    data += i32(1) + i32(type_code)
    data += i32(1) + string(parameter_name)
    data += i32(1) + i32(0)
    data += i32(1) + i32(len(payload))
    return bytes(data)


def action_data_camera(position_time: int = 17) -> bytes:
    data = bytearray()
    action_name = "HutongGames.PlayMaker.Actions.CameraFadeIn"
    data += i32(1) + string(action_name)
    data += i32(1) + string("")
    data += i32(1) + b"\x01\0\0\0"
    data += i32(1) + b"\x01\0\0\0"
    data += i32(1) + i32(0)
    data += i32(1) + i32(0x12345678)
    data += bytes(len(audit.ACTIONDATA_SPECIAL_ARRAYS) * 4)
    byte_data = (struct.pack("<4f", 0.0, 0.0, 0.0, 1.0) + b"\0" +
                 struct.pack("<fB", 0.0, 1) + b"time" + b"\0")
    data += i32(len(byte_data)) + byte_data
    data += bytes(-len(data) % 4)
    data += i32(0) * 4                  # arrayParamSizes/types/customTypeSizes/names
    data += i32(4) + i32(25) + i32(15) + i32(23) + i32(1)
    data += i32(4) + string("color") + string("time") + string("finishEvent") + string("realTime")
    data += i32(4) + i32(0) + i32(position_time) + i32(26) + i32(26)
    data += i32(4) + i32(17) + i32(9) + i32(0) + i32(1)
    return bytes(data)


def synthetic_send_event_action_data() -> bytes:
    """Build a synthetic ActionData using the title-observed SendEvent layout."""
    game_object = {
        "use_variable": False, "name": "", "tooltip": "",
        "show_in_inspector": False, "network_sync": False,
        "value_pointer": {"file_id": 0, "path_id": 0},
    }
    bool_field = {
        "use_variable": False, "name": "", "tooltip": "",
        "show_in_inspector": False, "network_sync": False, "value": False,
    }
    event_target = {
        "target_value": 2,
        "exclude_self": bool_field,
        "game_object": {"owner_option": 0, "game_object": game_object},
        "fsm_name": {
            "use_variable": False, "name": "", "tooltip": "",
            "show_in_inspector": False, "network_sync": False, "value": "",
        },
        "send_to_children": bool_field,
        "fsm_component": {"file_id": 0, "path_id": 0},
    }
    specialized = {name: [] for name in audit.ACTIONDATA_SPECIAL_ARRAYS}
    specialized["fsmEventTargetParams"] = [event_target]
    byte_data = b"off" + struct.pack("<fB", 0.0, 0) + b"\0"
    parameters = [
        {"name": "eventTarget", "serialized_type_code": 31,
         "type": "HutongGames.PlayMaker.FsmEventTarget",
         "specialized_array": "fsmEventTargetParams", "specialized_array_index": 0,
         "value": event_target},
        {"name": "sendEvent", "serialized_type_code": 23,
         "type": "HutongGames.PlayMaker.FsmEvent",
         "byte_data_position": 0, "byte_data_size": 3,
         "value": {"event_name": "off"}},
        {"name": "delay", "serialized_type_code": 15,
         "type": "HutongGames.PlayMaker.FsmFloat",
         "byte_data_position": 3, "byte_data_size": 5,
         "value": {"value": 0.0, "use_variable": False, "variable_name": None}},
        {"name": "everyFrame", "serialized_type_code": 1,
         "type": "System.Boolean", "byte_data_position": 8,
         "byte_data_size": 1, "value": False},
    ]
    model = {
        "action_names": ["HutongGames.PlayMaker.Actions.SendEvent"],
        "custom_names": [""], "enabled": [True], "is_open": [True],
        "start_indices": [0], "hash_codes_u32": [0xFFFFFFFE],
        "specialized_parameter_arrays": specialized, "_byte_data": byte_data,
        "array_param_sizes": [], "array_param_types": [],
        "custom_type_sizes": [], "custom_type_names": [],
        "param_data_types": [31, 23, 15, 1],
        "param_names": ["eventTarget", "sendEvent", "delay", "everyFrame"],
        "param_data_positions": [0, 0, 3, 8],
        "param_byte_data_sizes": [0, 3, 5, 1], "parameters": parameters,
    }
    return audit.encode_action_data(model)


def synthetic_graphic_field_action_data() -> bytes:
    texture = {
        "use_variable": True, "name": "texture", "tooltip": "",
        "show_in_inspector": False, "network_sync": False,
        "type_name": "UnityEngine.Texture2D",
        "value_pointer": {"file_id": 0, "path_id": 77},
    }
    specialized = {name: [] for name in audit.ACTIONDATA_SPECIAL_ARRAYS}
    specialized["fsmObjectParams"] = [texture]
    byte_data = struct.pack("<4fB", 24.0, 36.0, 320.0, 180.0, 0)
    parameters = [
        {"name": "getTextureData", "serialized_type_code": 33,
         "type": "HutongGames.PlayMaker.FsmTexture",
         "specialized_array": "fsmObjectParams", "specialized_array_index": 0,
         "value": texture},
        {"name": "getRectData", "serialized_type_code": 30,
         "type": "HutongGames.PlayMaker.FsmRect",
         "byte_data_position": 0, "byte_data_size": 17,
         "value": {"rect": [24.0, 36.0, 320.0, 180.0], "use_variable": False}},
    ]
    model = {
        "action_names": ["HutongGames.PlayMaker.Actions.GetEventInfo"],
        "custom_names": [""], "enabled": [True], "is_open": [True],
        "start_indices": [0], "hash_codes_u32": [0x13572468],
        "specialized_parameter_arrays": specialized, "_byte_data": byte_data,
        "array_param_sizes": [], "array_param_types": [],
        "custom_type_sizes": [], "custom_type_names": [],
        "param_data_types": [33, 30],
        "param_names": ["getTextureData", "getRectData"],
        "param_data_positions": [0, 0], "param_byte_data_sizes": [0, 17],
        "parameters": parameters,
    }
    return audit.encode_action_data(model)


def actiondata_target_prefix(action_name: str, extra_names: list[str] | None = None) -> bytes:
    names = ["HutongGames.PlayMaker.Actions." + action_name, *(extra_names or [])]
    data = i32(len(names)) + b"".join(string(name) for name in names)
    data += i32(len(names)) + b"".join(string("") for _ in names)
    data += i32(len(names)) + bytes([1] * len(names)) + bytes(-len(names) % 4)
    data += i32(len(names)) + bytes([1] * len(names)) + bytes(-len(names) % 4)
    data += i32(len(names)) + b"".join(i32(0) for _ in names)
    data += i32(len(names)) + b"".join(i32(123) for _ in names)
    return data


def state(name: str, transitions: list[tuple[str, str]], action_data: bytes) -> bytes:
    data = string(name) + string("") + i32(0)
    data += struct.pack("<4f", 1.0, 2.0, 300.0, 80.0)
    data += i32(0) * 3
    data += i32(len(transitions))
    for event, target in transitions:
        data += transition(event, target)
    data += action_data
    return data


def variables_float(name: str = "time", value: float = 2.0) -> bytes:
    data = i32(1) + i32(1) + string(name) + struct.pack("<iqf", 0, 0, value)
    data += bytes(12 * 4) + i32(0)  # remaining arrays and GlobalVariablesSynced
    return data


def fsm_component(target: str = "Main", time_position: int = 17) -> bytes:
    data = bytearray(32)                 # synthetic MonoBehaviour header
    data += struct.pack("<iq", 0, 0)    # serialized Fsm.usedInTemplate is null
    data += string("SyntheticFSM") + string("Closed") + i32(2)
    data += state("Closed", [("Open", target)], action_data_empty())
    data += state("Main", [("Close", "Closed")], action_data_camera(time_position))
    data += i32(2) + fsm_event("Open") + fsm_event("Close")
    data += i32(0)                       # globalTransitions
    data += variables_float()
    data += bytes(40)                    # opaque Fsm tail in the pinned title layout
    data += struct.pack("<iq", 0, 0)     # null fsmTemplate PPtr
    return bytes(data)


def fsm_template(name: str = "SyntheticTemplate") -> bytes:
    data = bytearray(32)
    data += name.encode("utf-8") + b"\0"
    data += bytes(-len(data) % 4)
    data += string("General")
    data += struct.pack("<iq", 0, 77)    # Fsm.usedInTemplate points back to the template
    data += string("SyntheticFSM") + string("Closed") + i32(2)
    return bytes(data)


def graph_schema():
    prefix = "HutongGames.PlayMaker.Actions."
    fsm_string = "HutongGames.PlayMaker.FsmString"
    fsm_float = "HutongGames.PlayMaker.FsmFloat"
    fsm_bool = "HutongGames.PlayMaker.FsmBool"
    fsm_event = "HutongGames.PlayMaker.FsmEvent"
    fsm_texture = "HutongGames.PlayMaker.FsmTexture"
    fsm_rect = "HutongGames.PlayMaker.FsmRect"
    gui_content = "UnityEngine.GUIContent"
    unity_rect = "UnityEngine.Rect"
    fields = {
        prefix + "GUIBox": [
            {"name": "image", "type": fsm_texture}, {"name": "text", "type": fsm_string},
            {"name": "tooltip", "type": fsm_string}, {"name": "style", "type": fsm_string},
            {"name": "content", "type": gui_content}, {"name": "screenRect", "type": fsm_rect},
            {"name": "left", "type": fsm_float},
            {"name": "top", "type": fsm_float}, {"name": "width", "type": fsm_float},
            {"name": "height", "type": fsm_float}, {"name": "normalized", "type": fsm_bool},
            {"name": "rect", "type": unity_rect},
        ],
        prefix + "GUILabel": [
            {"name": "image", "type": fsm_texture}, {"name": "text", "type": fsm_string},
            {"name": "tooltip", "type": fsm_string}, {"name": "style", "type": fsm_string},
            {"name": "content", "type": gui_content}, {"name": "screenRect", "type": fsm_rect},
            {"name": "left", "type": fsm_float},
            {"name": "top", "type": fsm_float}, {"name": "width", "type": fsm_float},
            {"name": "height", "type": fsm_float}, {"name": "normalized", "type": fsm_bool},
            {"name": "rect", "type": unity_rect},
        ],
        prefix + "GUIButton": [
            {"name": "sendEvent", "type": fsm_event}, {"name": "storeButtonState", "type": fsm_bool},
            {"name": "image", "type": fsm_texture}, {"name": "text", "type": fsm_string},
            {"name": "tooltip", "type": fsm_string}, {"name": "style", "type": fsm_string},
            {"name": "content", "type": gui_content}, {"name": "screenRect", "type": fsm_rect},
            {"name": "left", "type": fsm_float},
            {"name": "top", "type": fsm_float}, {"name": "width", "type": fsm_float},
            {"name": "height", "type": fsm_float}, {"name": "normalized", "type": fsm_bool},
            {"name": "rect", "type": unity_rect},
        ],
        prefix + "GetButtonDown": [
            {"name": "buttonName", "type": fsm_string}, {"name": "sendEvent", "type": fsm_event},
            {"name": "storeResult", "type": fsm_bool},
        ],
        prefix + "SendEvent": [
            {"name": "eventTarget", "type": "HutongGames.PlayMaker.FsmEventTarget"},
            {"name": "sendEvent", "type": fsm_event}, {"name": "delay", "type": fsm_float},
            {"name": "everyFrame", "type": "System.Boolean"},
            {"name": "delayedEvent", "type": "HutongGames.PlayMaker.DelayedEvent"},
        ],
    }
    aot = {name: {"virtual_slot": slot} for name, slot in (
        ("GUIBox", 33), ("GUILabel", 33), ("GUIButton", 33),
        ("GetButtonDown", 32), ("SendEvent", 30),
    )}
    return fields, aot


class SyntheticGraphicResolver:
    def serializable_action_fields(self, full_name: str) -> list[dict]:
        if not full_name.endswith((".GUIBox", ".GUILabel")):
            raise ValueError("unexpected synthetic action")
        return [
            {"name": name, "type": type_name, "attributes": 0x0006}
            for name, type_name, _, _ in audit.GRAPHIC_ACTION_FIELD_LAYOUT
        ]


class PlayMakerFsmAssetInspectorTests(unittest.TestCase):
    def test_type_resolver_reads_bounded_field_custom_attribute_ranges(self):
        metadata = bytearray(320)
        struct.pack_into("<Ii", metadata,
                         8 + audit.CUSTOM_ATTRIBUTE_INFO_HEADER_INDEX * 8, 256, 16)
        struct.pack_into("<Ii", metadata,
                         8 + audit.CUSTOM_ATTRIBUTE_TYPES_HEADER_INDEX * 8, 272, 4)
        struct.pack_into("<ii", metadata, 264, 0, 1)  # attribute-info row 1
        struct.pack_into("<I", metadata, 272, 17)
        audit.FIELD_RECORD.pack_into(metadata, 300, 0, 0, 1, 0)
        resolver = audit.TypeResolver.__new__(audit.TypeResolver)
        resolver.metadata = SimpleNamespace(fields=[SimpleNamespace(declaring_type=0)])
        resolver.metadata_data = bytes(metadata)
        resolver.field_offset = 300
        resolver.attribute_info_offset = 256
        resolver.attribute_info_count = 2
        resolver.attribute_types_offset = 272
        resolver.attribute_type_count = 1
        resolver.resolve = lambda index: {17: "UnityEngine.SerializeField"}[index]
        self.assertEqual(resolver.field_custom_attributes(0), ["UnityEngine.SerializeField"])
        with self.assertRaisesRegex(ValueError, "field index outside"):
            resolver.field_custom_attributes(1)

        struct.pack_into("<ii", metadata, 264, 0, 2)
        resolver.metadata_data = bytes(metadata)
        with self.assertRaisesRegex(ValueError, "attribute range outside"):
            resolver.field_custom_attributes(0)

    def test_public_instance_field_attribute_filter_matches_reflection_flags(self):
        self.assertTrue(audit.is_public_instance_field(0x0006))
        self.assertFalse(audit.is_public_instance_field(0x0003))  # Assembly/internal
        self.assertFalse(audit.is_public_instance_field(0x0001))  # Private
        self.assertFalse(audit.is_public_instance_field(0x0016))  # Public static
        self.assertFalse(audit.is_public_instance_field(-1))
        self.assertFalse(audit.is_public_instance_field("public"))

    def test_type_resolver_reads_field_attributes_from_registered_type(self):
        regions = {
            0x1000: struct.pack("<Q", 0x2000),
            0x2000: struct.pack("<QI", 7, (0x12 << 16) | 0x0006) + bytes(4),
        }
        resolver = audit.TypeResolver.__new__(audit.TypeResolver)
        resolver.type_count = 1
        resolver.type_table = 0x1000
        resolver.image = SyntheticNativeImage(regions)
        self.assertEqual(resolver.field_attributes(0), 0x0006)

    def test_type_resolver_follows_bounded_szarray_element_types(self):
        regions = {
            0x1000: struct.pack("<Q", 0x2000),
            0x2000: il2cpp_type_record(0x3000, 0x1D),
            0x3000: il2cpp_type_record(0x4000, 0x1D),
            0x4000: il2cpp_type_record(42, 0x12),
        }
        resolver = audit.TypeResolver.__new__(audit.TypeResolver)
        resolver.type_count = 1
        resolver.type_table = 0x1000
        resolver.image = SyntheticNativeImage(regions)
        resolver.type_defs_by_index = {
            42: type("MetadataType", (), {"full_name": "Example.LayoutOption"})()
        }
        self.assertEqual(resolver.resolve(0), "Example.LayoutOption[][]")

        regions = {
            0x1000: struct.pack("<Q", 0x2000),
            0x2000: il2cpp_type_record(0x3000, 0x1D),
            0x3000: il2cpp_type_record(0x05, 0x05),
        }
        resolver.image = SyntheticNativeImage(regions)
        resolver.type_defs_by_index = {}
        self.assertEqual(resolver.resolve(0), "System.Byte[]")

    def test_type_resolver_rejects_bad_szarray_pointer_and_depth(self):
        resolver = audit.TypeResolver.__new__(audit.TypeResolver)
        resolver.type_count = 1
        resolver.type_table = 0x1000
        resolver.type_defs_by_index = {}
        resolver.image = SyntheticNativeImage({
            0x1000: struct.pack("<Q", 0x2000),
            0x2000: il2cpp_type_record(0, 0x1D),
        })
        with self.assertRaisesRegex(ValueError, "element type pointer is invalid"):
            resolver.resolve(0)

        regions = {0x1000: struct.pack("<Q", 0x2000)}
        for depth in range(audit.MAX_NATIVE_TYPE_NESTING + 2):
            current = 0x2000 + depth * 0x20
            next_pointer = current + 0x20
            regions[current] = il2cpp_type_record(next_pointer, 0x1D)
        regions[next_pointer] = il2cpp_type_record(0x05, 0x05)
        resolver.image = SyntheticNativeImage(regions)
        with self.assertRaisesRegex(ValueError, "recursion limit"):
            resolver.resolve(0)

    def test_parses_synthetic_state_graph_and_actiondata(self):
        parsed = audit.parse_fsm_component(fsm_component())
        self.assertEqual(parsed["name"], "SyntheticFSM")
        self.assertEqual(parsed["start_state"], "Closed")
        self.assertEqual([item["name"] for item in parsed["events"]], ["Open", "Close"])
        main = parsed["states"][1]
        self.assertEqual(main["action_data"]["action_names"], [
            "HutongGames.PlayMaker.Actions.CameraFadeIn"])
        self.assertEqual(main["action_data"]["parameters"][0]["value"]["rgba"],
                         [0.0, 0.0, 0.0, 1.0])
        self.assertEqual(main["action_data"]["parameters"][1]["value"]["variable_name"], "time")
        self.assertEqual(parsed["variables"]["float_variables"][0]["value"], 2.0)
        self.assertEqual(parsed["opaque_fsm_tail"]["size"], 40)
        self.assertEqual(parsed["fsm_template_pointer"], {
            "file_id": 0, "path_id": 0, "offset": len(fsm_component()) - 12})

    def test_complete_synthetic_gui_playmaker_component_round_trips(self):
        tail = bytes(range(audit.MAX_FSM_TAIL_BYTES))
        component = audit.build_synthetic_graphic_playmaker_component(
            tail, game_object_path_id=101, script_file_id=3,
            mono_script_path_id=115000)
        parsed = audit.parse_fsm_component(component)
        action_data = parsed["states"][0]["action_data"]
        self.assertEqual(parsed["name"], "UCM_Menu_Synthetic")
        self.assertEqual(parsed["start_state"], "DrawMenu")
        self.assertEqual(action_data["action_names"], [
            "HutongGames.PlayMaker.Actions.GUIBox",
            "HutongGames.PlayMaker.Actions.GUILabel",
        ])
        self.assertEqual(len(action_data["parameters"]), 20)
        self.assertEqual(action_data["parameters"][11]["value"]["value"],
                         "Ultimate Mod Menu")
        self.assertEqual(action_data["param_data_positions"][11], 3)
        self.assertEqual(action_data["parameters"][14]["byte_data_position"], 39)
        self.assertEqual(parsed["_opaque_fsm_tail"], tail)
        self.assertEqual(audit.encode_fsm_component(parsed), component)
        decoded_again = audit.parse_fsm_component(audit.encode_fsm_component(parsed))
        self.assertEqual(decoded_again["name"], parsed["name"])
        self.assertEqual(decoded_again["states"][0]["action_data"]["action_names"],
                         action_data["action_names"])
        self.assertEqual(decoded_again["_opaque_fsm_tail"], tail)

    def test_synthetic_playmaker_component_links_to_valid_unity_object_graph(self):
        component_bytes = audit.build_synthetic_graphic_playmaker_component(
            bytes(40), game_object_path_id=101, script_file_id=1,
            mono_script_path_id=501)
        graph = {
            "game_object_path_id": 101, "transform_path_id": 102,
            "playmaker_component_path_id": 103,
            "objects": [
                {"path_id": 101, "class_id": 1,
                 "components": [{"file_id": 0, "path_id": 102},
                                {"file_id": 0, "path_id": 103}]},
                {"path_id": 102, "class_id": 4,
                 "game_object": {"file_id": 0, "path_id": 101},
                 "father": {"file_id": 0, "path_id": 0}, "children": []},
                {"path_id": 103, "class_id": 114,
                 "game_object": {"file_id": 0, "path_id": 101},
                 "class_name": "PlayMakerFSM", "enabled": True,
                 "script": {"file_id": 1, "path_id": 501},
                 "mono_header": component_bytes[:32],
                 "component_bytes": component_bytes,
                 "component_payload_size": len(component_bytes)},
            ],
            "external_files": {1: "globalgamemanagers.assets"},
            "external_objects": {"globalgamemanagers.assets": {501: 115}},
            "dependencies": ["globalgamemanagers.assets"],
        }
        report = audit.validate_synthetic_unity_object_graph(graph)
        self.assertTrue(report["validated"])
        self.assertFalse(report["unity_assets_object_table_serialized"])
        self.assertTrue(report["fsm_template_pointer_validated"])

        duplicate = copy.deepcopy(graph)
        duplicate["objects"][2]["path_id"] = 102
        with self.assertRaisesRegex(ValueError, "duplicate or invalid"):
            audit.validate_synthetic_unity_object_graph(duplicate)

        unresolved = copy.deepcopy(graph)
        unresolved["objects"][2]["script"]["path_id"] = 999
        with self.assertRaisesRegex(ValueError, "does not resolve"):
            audit.validate_synthetic_unity_object_graph(unresolved)

    def test_synthetic_unity_graph_validates_optional_external_template_pptr(self):
        component_bytes = bytearray(audit.build_synthetic_graphic_playmaker_component(
            bytes(40), game_object_path_id=101, script_file_id=1,
            mono_script_path_id=501))
        struct.pack_into("<iq", component_bytes, len(component_bytes) - 12, 2, 600)
        component_bytes = bytes(component_bytes)
        graph = {
            "game_object_path_id": 101, "transform_path_id": 102,
            "playmaker_component_path_id": 103,
            "objects": [
                {"path_id": 101, "class_id": 1,
                 "components": [{"file_id": 0, "path_id": 102},
                                {"file_id": 0, "path_id": 103}]},
                {"path_id": 102, "class_id": 4,
                 "game_object": {"file_id": 0, "path_id": 101},
                 "father": {"file_id": 0, "path_id": 0}, "children": []},
                {"path_id": 103, "class_id": 114,
                 "game_object": {"file_id": 0, "path_id": 101},
                 "class_name": "PlayMakerFSM", "enabled": True,
                 "script": {"file_id": 1, "path_id": 501},
                 "mono_header": component_bytes[:32],
                 "component_bytes": component_bytes,
                 "component_payload_size": len(component_bytes)},
            ],
            "external_files": {1: "globalgamemanagers.assets",
                               2: "sharedassets2.assets"},
            "external_objects": {
                "globalgamemanagers.assets": {501: 115},
                "sharedassets2.assets": {
                    600: {"class_id": 114, "class_name": "FsmTemplate"},
                },
            },
            "dependencies": ["globalgamemanagers.assets", "sharedassets2.assets"],
        }
        self.assertTrue(audit.validate_synthetic_unity_object_graph(graph)["validated"])
        graph["external_objects"]["sharedassets2.assets"][600]["class_name"] = "Other"
        with self.assertRaisesRegex(ValueError, "wrong class"):
            audit.validate_synthetic_unity_object_graph(graph)

    def test_synthetic_gui_fsm_rejects_missing_or_malformed_opaque_tail(self):
        for tail in (b"", bytes(39), bytes(41)):
            with self.subTest(tail_size=len(tail)):
                with self.assertRaisesRegex(ValueError, "explicit 40-byte"):
                    audit.build_synthetic_graphic_playmaker_component(
                        tail, game_object_path_id=101, script_file_id=1,
                        mono_script_path_id=501)

    def test_fsm_encoder_rejects_duplicate_state_and_event_references(self):
        parsed = audit.parse_fsm_component(fsm_component())
        duplicate_state = copy.deepcopy(parsed)
        duplicate_state["states"][1]["name"] = duplicate_state["states"][0]["name"]
        with self.assertRaisesRegex(ValueError, "duplicate state name"):
            audit.encode_fsm_component(duplicate_state)

        unresolved_event = copy.deepcopy(parsed)
        unresolved_event["states"][0]["transitions"][0]["event"] = "Missing"
        with self.assertRaisesRegex(ValueError, "undeclared Fsm event"):
            audit.encode_fsm_component(unresolved_event)

    def test_rejects_unresolved_transition_state(self):
        with self.assertRaisesRegex(ValueError, "undeclared state"):
            audit.parse_fsm_component(fsm_component(target="Missing"))

    def test_rejects_unresolved_fsm_float_variable(self):
        data = bytearray(fsm_component())
        at = data.rfind(b"time")  # alter the serialized FsmVariables float name
        data[at:at + 4] = b"else"
        with self.assertRaisesRegex(ValueError, "variable link is unresolved"):
            audit.parse_fsm_component(bytes(data))

    def test_rejects_parameter_slice_past_byte_data(self):
        with self.assertRaisesRegex(ValueError, "outside byteData"):
            audit.parse_fsm_component(fsm_component(time_position=900))

    def test_actiondata_complete_synthetic_send_event_round_trip_and_edit(self):
        original = synthetic_send_event_action_data()
        parsed = audit.parse_action_data(audit.Reader(original))
        self.assertEqual(audit.encode_action_data(parsed), original)
        self.assertEqual(parsed["parameters"][0]["value"]["target_value"], 2)
        self.assertGreater(parsed["parameters"][0]["specialized_array_size"], 0)
        self.assertEqual(parsed["parameters"][0]["specialized_array_offset"],
                         parsed["specialized_parameter_array_offsets"][
                             "fsmEventTargetParams"][0]["offset"])
        self.assertEqual(parsed["parameters"][0]["value"]["game_object"]["owner_option"], 0)
        self.assertEqual(parsed["parameters"][1]["value"]["event_name"], "off")

        parsed["parameters"][1]["value"]["event_name"] = "on!"
        parsed["parameters"][2]["value"]["value"] = 1.25
        parsed["parameters"][3]["value"] = True
        parsed["specialized_parameter_arrays"]["fsmEventTargetParams"][0]["target_value"] = 3
        edited = audit.encode_action_data(parsed)
        decoded = audit.parse_action_data(audit.Reader(edited))
        self.assertEqual(decoded["parameters"][0]["value"]["target_value"], 3)
        self.assertEqual(decoded["parameters"][1]["value"]["event_name"], "on!")
        self.assertEqual(decoded["parameters"][2]["value"]["value"], 1.25)
        self.assertTrue(decoded["parameters"][3]["value"])

    def test_actiondata_fsmtexture_and_fsmrect_round_trip_and_edit(self):
        original = synthetic_graphic_field_action_data()
        parsed = audit.parse_action_data(audit.Reader(original))
        self.assertEqual(audit.encode_action_data(parsed), original)
        texture = parsed["parameters"][0]
        self.assertEqual(texture["type"], "HutongGames.PlayMaker.FsmTexture")
        self.assertEqual(texture["specialized_array"], "fsmObjectParams")
        self.assertEqual(texture["value"]["type_name"], "UnityEngine.Texture2D")
        self.assertEqual(parsed["parameters"][1]["value"]["rect"],
                         [24.0, 36.0, 320.0, 180.0])
        parsed["specialized_parameter_arrays"]["fsmObjectParams"][0][
            "value_pointer"]["path_id"] = 99
        parsed["parameters"][1]["value"]["rect"][2] = 400.0
        edited = audit.encode_action_data(parsed)
        decoded = audit.parse_action_data(audit.Reader(edited))
        self.assertEqual(decoded["parameters"][0]["value"]["value_pointer"]["path_id"], 99)
        self.assertEqual(decoded["parameters"][1]["value"]["rect"][2], 400.0)

    def test_actiondata_direct_unity_rect_round_trip(self):
        payload = struct.pack("<4f", 16.0, 24.0, 320.0, 180.0)
        raw = action_data_one_parameter(
            "HutongGames.PlayMaker.Actions.SyntheticRect", "rect", 11, payload)
        decoded = audit.parse_action_data(audit.Reader(raw))
        self.assertEqual(decoded["parameters"][0]["type"], "UnityEngine.Rect")
        self.assertEqual(decoded["parameters"][0]["value"]["rect"],
                         [16.0, 24.0, 320.0, 180.0])
        self.assertEqual(audit.encode_action_data(decoded), raw)

    def test_actiondata_direct_unity_rect_rejects_truncated_and_nonfinite_values(self):
        malformed = (
            struct.pack("<3f", 0.0, 0.0, 1.0),
            struct.pack("<4f", float("nan"), 0.0, 1.0, 1.0),
        )
        for payload in malformed:
            raw = action_data_one_parameter(
                "HutongGames.PlayMaker.Actions.SyntheticRect", "rect", 11, payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                audit.parse_action_data(audit.Reader(raw))

    def test_fsmfloat_variable_links_use_bounded_utf8_and_allow_empty_name(self):
        for variable_name in ("time", "tiempo-é", ""):
            payload = struct.pack("<fB", 1.25, 1) + variable_name.encode("utf-8")
            raw = action_data_one_parameter(
                "HutongGames.PlayMaker.Actions.GetEventInfo", "getFloatData", 15, payload)
            decoded = audit.parse_action_data(audit.Reader(raw))
            self.assertEqual(decoded["parameters"][0]["value"]["variable_name"],
                             variable_name)
            self.assertEqual(audit.encode_action_data(decoded), raw)

    def test_fsmbool_and_fsmrect_variable_links_use_bounded_utf8(self):
        cases = (
            ("flag", 17, b"\x01\x01" + "visible-é".encode("utf-8"), "visible-é"),
            ("flag", 17, b"\x00\x01", ""),
            ("rect", 30, struct.pack("<4fB", 1.0, 2.0, 3.0, 4.0, 1), ""),
            ("rect", 30, struct.pack("<4fB", 1.0, 2.0, 3.0, 4.0, 1) +
             "panel-é".encode("utf-8"), "panel-é"),
        )
        for name, code, payload, expected_name in cases:
            raw = action_data_one_parameter(
                "HutongGames.PlayMaker.Actions.Synthetic", name, code, payload)
            decoded = audit.parse_action_data(audit.Reader(raw))
            self.assertEqual(decoded["parameters"][0]["value"]["variable_name"],
                             expected_name)
            self.assertEqual(audit.encode_action_data(decoded), raw)

    def test_variable_link_rejects_invalid_utf8_and_oversized_suffix(self):
        malformed = (
            (15, struct.pack("<fB", 1.0, 1) + b"\xff"),
            (17, b"\x00\x01\xff"),
            (30, struct.pack("<4fB", 0.0, 0.0, 1.0, 1.0, 1) + b"\xff"),
            (15, struct.pack("<fB", 1.0, 1) + b"a" * (audit.MAX_STRING_BYTES + 1)),
        )
        for code, payload in malformed:
            raw = action_data_one_parameter(
                "HutongGames.PlayMaker.Actions.Synthetic", "value", code, payload)
            with self.subTest(code=code, size=len(payload)), self.assertRaises(ValueError):
                audit.parse_action_data(audit.Reader(raw))

    def test_synthetic_gui_actiondata_full_byte_round_trip_and_metadata_schema(self):
        resolver = SyntheticGraphicResolver()
        for action_name in ("GUIBox", "GUILabel"):
            with self.subTest(action=action_name):
                raw = audit.build_synthetic_graphic_action_data(action_name)
                summary = audit.validate_graphic_action_data(raw, action_name, resolver)
                parsed = audit.parse_action_data(audit.Reader(raw))
                encoded = audit.encode_action_data(parsed)
                redecoded = audit.parse_action_data(audit.Reader(encoded))
                self.assertEqual(encoded, raw)
                self.assertEqual(redecoded, parsed)
                self.assertEqual(summary["action_type_hash_code_u32"], 0xFC6EB184)
                self.assertEqual(summary["byte_data_size"], 39)
                self.assertEqual(len(summary["serialized_fields"]), 10)

    def test_synthetic_gui_actiondata_rejects_schema_or_hash_mismatch(self):
        resolver = SyntheticGraphicResolver()
        raw = audit.build_synthetic_graphic_action_data("GUIBox")
        parsed = audit.parse_action_data(audit.Reader(raw))
        parsed["hash_codes_u32"][0] ^= 1
        with self.assertRaisesRegex(ValueError, "start/hash metadata"):
            audit.validate_graphic_action_data(audit.encode_action_data(parsed),
                                               "GUIBox", resolver)

        class WrongResolver:
            def serializable_action_fields(self, _name):
                return [{"name": "content", "type": "UnityEngine.GUIContent"}]

        with self.assertRaisesRegex(ValueError, "native public-instance GUI action fields"):
            audit.validate_graphic_action_data(raw, "GUIBox", WrongResolver())

    def test_action_type_hash_matches_retail_camera_fade_witness(self):
        signature = [
            "HutongGames.PlayMaker.FsmColor", "HutongGames.PlayMaker.FsmFloat",
            "HutongGames.PlayMaker.FsmEvent", "System.Boolean",
        ]
        self.assertEqual(audit.action_type_hash_code(signature), 0xCF3E5806)

    def test_actiondata_fsmtexture_rejects_a_detached_parameter_value(self):
        parsed = audit.parse_action_data(
            audit.Reader(synthetic_graphic_field_action_data()))
        parsed["parameters"][0]["value"] = copy.deepcopy(
            parsed["parameters"][0]["value"])
        parsed["parameters"][0]["value"]["type_name"] = "UnityEngine.Material"
        with self.assertRaisesRegex(ValueError, "disagrees with its array entry"):
            audit.encode_action_data(parsed)

    def test_actiondata_fsmtexture_rejects_negative_object_reference(self):
        raw = bytearray(synthetic_graphic_field_action_data())
        parsed = audit.parse_action_data(audit.Reader(bytes(raw)))
        record = parsed["specialized_parameter_array_offsets"][
            "fsmObjectParams"][0]
        struct.pack_into("<q", raw, record["offset"] + record["size"] - 8, -1)
        with self.assertRaisesRegex(ValueError, "negative serialized PPtr"):
            audit.parse_action_data(audit.Reader(bytes(raw)))

    def test_actiondata_fsmrect_malformed_payloads_reject_or_round_trip_opaque(self):
        malformed = (
            b"\0" * 16,
            struct.pack("<4fB", float("nan"), 0.0, 10.0, 20.0, 0),
            struct.pack("<4fB", 0.0, 0.0, 10.0, 20.0, 2),
        )
        for payload in malformed:
            with self.subTest(payload=payload):
                raw = action_data_one_parameter(
                    "HutongGames.PlayMaker.Actions.GetEventInfo",
                    "getRectData", 30, payload)
                with self.assertRaises(ValueError):
                    audit.parse_action_data(audit.Reader(raw))
                recovered = audit.parse_action_data(
                    audit.Reader(raw), salvage_unknown_parameters=True)
                self.assertFalse(recovered["parameters"][0]["value"]["decoded"])
                self.assertEqual(audit.encode_action_data(recovered), raw)

    def test_full_actiondata_round_trip_redecodes_graphic_and_event_models(self):
        samples = (
            (synthetic_graphic_field_action_data(), "GetEventInfo"),
            (synthetic_send_event_action_data(), "SendEvent"),
        )
        for raw, action in samples:
            with self.subTest(action=action):
                prefix = scan_actions.parse_actiondata_prefix(
                    raw, 0, target_actions={
                        scan_actions.ACTION_PREFIX + action})
                self.assertIsNotNone(prefix)
                decoded, error = scan_actions._decode_full_action_data(
                    raw, prefix)
                self.assertIsNone(error)
                self.assertIsNotNone(decoded)
                self.assertEqual(audit.encode_action_data(decoded), raw)

    def test_actiondata_empty_fsmfloat_variable_is_decoded_and_round_trips(self):
        raw = action_data_one_parameter(
            "HutongGames.PlayMaker.Actions.GetEventInfo", "getFloatData", 15,
            struct.pack("<fB", 0.0, 1))
        decoded = audit.parse_action_data(audit.Reader(raw))
        self.assertEqual(decoded["parameters"][0]["value"]["variable_name"], "")
        self.assertEqual(audit.encode_action_data(decoded), raw)

    def test_actiondata_encoder_rejects_changed_payload_size_and_invalid_pointer(self):
        parsed = audit.parse_action_data(audit.Reader(synthetic_send_event_action_data()))
        parsed["parameters"][1]["value"]["event_name"] = "longer"
        with self.assertRaisesRegex(ValueError, "parameter size changed"):
            audit.encode_action_data(parsed)
        with self.assertRaisesRegex(ValueError, "negative serialized PPtr"):
            audit._read_pptr(audit.Reader(struct.pack("<iq", 0, -1)), "test")

    def test_actiondata_unknown_type_rejects_strictly_but_round_trips_opaque(self):
        parsed = audit.parse_action_data(audit.Reader(synthetic_send_event_action_data()))
        parsed["param_data_types"][1] = 99
        parsed["parameters"][1]["serialized_type_code"] = 99
        opaque_bytes = audit.encode_action_data(parsed)
        with self.assertRaisesRegex(ValueError, "unsupported ActionData serialized type code: 99"):
            audit.parse_action_data(audit.Reader(opaque_bytes))
        recovered = audit.parse_action_data(
            audit.Reader(opaque_bytes), salvage_unknown_parameters=True)
        self.assertEqual(recovered["unknown_parameter_type_codes"], [99])
        self.assertEqual(audit.encode_action_data(recovered), opaque_bytes)

    def test_actiondata_encoder_rejects_invalid_specialized_array_reference(self):
        parsed = audit.parse_action_data(audit.Reader(synthetic_send_event_action_data()))
        parsed["param_data_positions"][0] = 4
        parsed["parameters"][0]["specialized_array_index"] = 4
        with self.assertRaisesRegex(ValueError, "specialized parameter reference is invalid"):
            audit.encode_action_data(parsed)

    def test_graphic_actiondata_prefix_must_match_exact_state_header(self):
        action_data = actiondata_target_prefix("GUIBox", ["CustomActionTest"])
        blob = bytes(32) + state("draw", [("FINISHED", "closed")], action_data)
        offset = len(blob) - len(action_data)
        prefix = scan_actions.parse_actiondata_prefix(blob, offset)
        self.assertIsNotNone(prefix)
        self.assertEqual(prefix["action_names"], [
            "HutongGames.PlayMaker.Actions.GUIBox", "CustomActionTest"])
        matches = scan_actions.find_state_header(blob, offset)
        self.assertEqual([match["name"] for match in matches], ["draw"])
        self.assertIsNone(scan_actions.parse_actiondata_prefix(
            blob, offset,
            target_actions={scan_actions.ACTION_PREFIX + "GetEventInfo"}))

        truncated = blob[:offset] + action_data[:-2]
        self.assertIsNone(scan_actions.parse_actiondata_prefix(truncated, offset))
        malformed = bytearray(action_data)
        struct.pack_into("<i", malformed, 0, 65)
        self.assertIsNone(scan_actions.parse_actiondata_prefix(bytes(malformed), 0))

    def test_compact_jsonl_index_keeps_provenance_offsets_and_parameters(self):
        report = {
            "title": "Synthetic title",
            "selected_action_types": [
                "HutongGames.PlayMaker.Actions.GUIBox"],
            "provenance": {"aot_module_sha256": "a" * 64,
                           "metadata_sha256": "b" * 64},
            "scope": {"files_scanned": 1, "validated_serialized_action_instances": 1},
            "source_files": [{"name": "synthetic.assets", "sha256": "c" * 64}],
            "parse_errors": [], "unmapped_raw_action_name_occurrences": [],
            "instances": [{
                "asset": "synthetic.assets", "object_class": "FsmTemplate",
                "path_id": 99, "game_object_path_id": 0, "game_object_name": None,
                "fsm_name": "SyntheticFSM", "template_name": "SyntheticTemplate",
                "template_header_status": "decoded", "state_name": "draw",
                "state_path_offset": 120, "actiondata_offset": 180,
                "actiondata_prefix_size": 72, "actiondata_total_size": 144,
                "action_count": 1, "actiondata_parameter_count": 2,
                "actiondata_action_names": ["HutongGames.PlayMaker.Actions.GUIBox"],
                "actiondata_custom_names": [""],
                "actiondata_decode_status": "round-trip verified",
                "actiondata_decode_error": None, "action_name_index": 0,
                "action_name_offset": 200, "action_name_content_offset": 204,
                "action_name": "HutongGames.PlayMaker.Actions.GUIBox",
                "action_hash_code_u32": 123, "custom_name": "", "enabled": True,
                "is_open": True, "action_start_index": 0,
                "parameters": [{"name": "screenRect", "type": "FsmRect",
                                "byte_data_position": 0, "byte_data_size": 17,
                                "value": {"rect": [1.0, 2.0, 3.0, 4.0],
                                          "use_variable": False}}],
            }],
        }
        lines = scan_actions.render_jsonl(report).splitlines()
        header, row = (json.loads(line) for line in lines)
        self.assertEqual(header["selected_action_types"],
                         ["HutongGames.PlayMaker.Actions.GUIBox"])
        self.assertEqual(header["provenance"]["asset_hashes"]["synthetic.assets"], "c" * 64)
        self.assertEqual(row["object"]["path_id"], 99)
        self.assertEqual(row["actiondata"]["object_offset"], 180)
        self.assertEqual(row["action"]["name"], "GUIBox")
        self.assertEqual(row["parameters"][0]["value"]["rect"], [1.0, 2.0, 3.0, 4.0])

    def test_rejects_nonzero_empty_action_sentinel(self):
        data = bytearray(fsm_component())
        # The first state begins at offset 76; the empty ActionData follows its
        # synthetic transition and is represented by zero words.
        data[208:212] = i32(1)
        with self.assertRaisesRegex(ValueError, "zero-action sentinel"):
            audit.parse_fsm_component(bytes(data))

    def test_rejects_truncated_component_and_invalid_count(self):
        with self.assertRaisesRegex(ValueError, "tail size"):
            audit.parse_fsm_component(fsm_component()[:-1])
        data = bytearray(32) + struct.pack("<iq", 0, 0)
        data += string("bad") + string("start") + i32(129)
        with self.assertRaisesRegex(ValueError, "Fsm.states count"):
            audit.parse_fsm_component(bytes(data))

    def test_parses_fsm_template_wrapper_and_embedded_fsm_header(self):
        parsed = audit.parse_fsm_template_header(fsm_template())
        self.assertEqual(parsed["name"], "SyntheticTemplate")
        self.assertEqual(parsed["category"], "General")
        self.assertEqual(parsed["fsm_used_in_template_pointer"], {"file_id": 0, "path_id": 77})
        self.assertEqual(parsed["fsm_name"], "SyntheticFSM")
        self.assertEqual(parsed["start_state"], "Closed")
        self.assertEqual(parsed["state_count"], 2)

    def test_synthetic_fsm_template_round_trips_byte_for_byte(self):
        prefix = bytearray(32)
        prefix += b"SyntheticTemplate\0"
        prefix += bytes(-len(prefix) % 4)
        prefix += string("General")
        embedded_fsm = bytearray(fsm_component()[32:-12])
        struct.pack_into("<iq", embedded_fsm, 0, 0, 77)
        raw = bytes(prefix + embedded_fsm)
        header, fsm = audit.parse_fsm_template(raw)
        encoded = audit.encode_fsm_template(header, fsm)
        header_again, fsm_again = audit.parse_fsm_template(encoded)
        self.assertEqual(encoded, raw)
        self.assertEqual(header_again["name"], header["name"])
        self.assertEqual(audit._semantic_fsm_summary(fsm_again),
                         audit._semantic_fsm_summary(fsm))
        inconsistent = copy.deepcopy(header)
        inconsistent["fsm_name"] = "different"
        with self.assertRaisesRegex(ValueError, "header and embedded Fsm graph disagree"):
            audit.encode_fsm_template(inconsistent, fsm)

    def test_rejects_invalid_fsm_template_name_and_truncated_header(self):
        no_terminator = bytearray(32 + audit.MAX_STRING_BYTES + 1)
        no_terminator[32:] = b"X" * (audit.MAX_STRING_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "unterminated FsmTemplate name"):
            audit.parse_fsm_template_header(bytes(no_terminator))
        with self.assertRaisesRegex(ValueError, "truncated"):
            audit.parse_fsm_template_header(fsm_template()[:-5])

    def test_rejects_wrong_fsm_tail_layout(self):
        bad = fsm_component() + b"padding"
        with self.assertRaisesRegex(ValueError, "tail size"):
            audit.parse_fsm_component(bad)
        negative_pointer = bytearray(fsm_component())
        struct.pack_into("<iq", negative_pointer, len(negative_pointer) - 12, 0, -1)
        with self.assertRaisesRegex(ValueError, "negative serialized FsmTemplate PPtr"):
            audit.parse_fsm_component(bytes(negative_pointer))

    def test_inspector_rejects_unpinned_source_before_asset_parsing(self):
        with self.assertRaisesRegex(ValueError, "wrong level2 asset hash"):
            audit.inspect(b"untrusted", b"", b"", b"", b"")

    def test_synthetic_graph_uses_only_verified_actions_and_marks_input_unresolved(self):
        fields, aot = graph_schema()
        result = audit.validate_synthetic_menu_graph(
            audit.build_synthetic_menu_graph(), fields, aot)
        self.assertTrue(result["validated"])
        self.assertEqual(result["states"], 2)
        self.assertEqual(result["actions"], 6)
        self.assertFalse(result["input_binding_verified"])
        self.assertIn("image", result["unmodeled_metadata_fields"]["GUIBox"])
        self.assertIn("delayedEvent", result["unmodeled_metadata_fields"]["SendEvent"])

    def test_synthetic_graph_rejects_wrong_field_type_and_unknown_event(self):
        fields, aot = graph_schema()
        graph = audit.build_synthetic_menu_graph()
        bad_type = copy.deepcopy(graph)
        button = next(action for action in bad_type["states"][1]["actions"]
                      if action["type"].endswith("GUIButton"))
        button["fields"]["text"]["type"] = "HutongGames.PlayMaker.FsmFloat"
        with self.assertRaisesRegex(ValueError, "field type disagrees"):
            audit.validate_synthetic_menu_graph(bad_type, fields, aot)
        bad_event = copy.deepcopy(graph)
        bad_event["states"][0]["transitions"][0]["event"] = "Unknown"
        with self.assertRaisesRegex(ValueError, "unresolved event or state"):
            audit.validate_synthetic_menu_graph(bad_event, fields, aot)
        bad_target = copy.deepcopy(graph)
        send_event = next(action for action in bad_target["states"][1]["actions"]
                          if action["type"].endswith("SendEvent"))
        send_event["fields"]["eventTarget"]["value"] = "Self"
        with self.assertRaisesRegex(ValueError, "must stay explicitly symbolic"):
            audit.validate_synthetic_menu_graph(bad_target, fields, aot)
        bad_route = copy.deepcopy(graph)
        bad_route["states"][0]["actions"][0]["fields"]["sendEvent"]["value"] = "Close"
        with self.assertRaisesRegex(ValueError, "no state transition"):
            audit.validate_synthetic_menu_graph(bad_route, fields, aot)


if __name__ == "__main__":
    unittest.main()
