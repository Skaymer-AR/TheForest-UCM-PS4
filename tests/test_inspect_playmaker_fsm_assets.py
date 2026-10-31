"""Synthetic-only tests for bounded PlayMaker component and graph parsing."""
from __future__ import annotations

import copy
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_playmaker_fsm_assets as audit


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
    data += i32(1) + i32(1)              # actionEnabled
    data += i32(1) + i32(1)              # actionIsOpen
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
    data += i32(1) + i32(1)
    data += i32(1) + i32(1)
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
