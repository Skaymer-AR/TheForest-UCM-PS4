"""Synthetic-only tests for bounded PlayMaker component and graph parsing."""
from __future__ import annotations

import copy
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_playmaker_fsm_assets as audit
import scan_playmaker_action_instances as scan_actions


def i32(value: int) -> bytes:
    return struct.pack("<i", value)


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


class PlayMakerFsmAssetInspectorTests(unittest.TestCase):
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

        truncated = blob[:offset] + action_data[:-2]
        self.assertIsNone(scan_actions.parse_actiondata_prefix(truncated, offset))
        malformed = bytearray(action_data)
        struct.pack_into("<i", malformed, 0, 65)
        self.assertIsNone(scan_actions.parse_actiondata_prefix(bytes(malformed), 0))

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
