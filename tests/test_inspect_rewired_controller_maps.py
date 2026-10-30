"""Synthetic-only tests for the pinned Rewired map decoder."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_rewired_controller_maps as audit


DS4_GUID = "83b427e4-086f-47f3-bb06-be266abd1ca5"
OTHER_GUID = "11111111-2222-3333-4444-555555555555"


def aligned_string(value: str) -> bytes:
    raw = value.encode("ascii")
    result = struct.pack("<i", len(raw)) + raw
    return result + b"\0" * (-len(result) % 4)


def action_element_map(category: int, action: int, kind: int, element: int,
                       trailing: tuple[int, ...] = (0,) * 7) -> bytes:
    if len(trailing) != 7:
        raise ValueError("fixture expects seven uninterpreted words")
    return struct.pack("<11I", category, action, kind, element, *trailing)


def controller_map(map_id: int, guid: str, records: list[bytes], *,
                   category: int = 0, layout: int = 0) -> bytes:
    return (struct.pack("<iii", map_id, category, layout) +
            aligned_string("") + aligned_string(guid) +
            struct.pack("<ii", 0, len(records)) + b"".join(records))


def map_category(name: str, category_id: int) -> bytes:
    return (aligned_string(name) + aligned_string(name) + aligned_string("") +
            struct.pack("<iIIi", category_id, 0, 0, 0))


def action_category(name: str, category_id: int) -> bytes:
    return (aligned_string(name) + aligned_string(name) + aligned_string("") +
            struct.pack("<iI", category_id, 0))


def input_action(action_id: int, name: str, category_id: int) -> bytes:
    return (struct.pack("<i", action_id) + aligned_string(name) +
            struct.pack("<i", 1) + aligned_string("") * 3 +
            struct.pack("<iii", 0, 0, category_id))


def layout(name: str, layout_id: int) -> bytes:
    return aligned_string(name) + aligned_string(name) + struct.pack("<i", layout_id)


def input_manager_prefix() -> bytes:
    # InputAction and InputCategory records precede a Player_Editor (id 1)
    # whose default maps include two enabled and one disabled category.
    actions = [
        input_action(2, "MenuToggle", 1),
        input_action(9, "Jump", 6),
        input_action(58, "Select", 4),
    ]
    action_categories = [("Default", 0), ("Menu", 1),
                         ("Inventory", 4), ("Movement", 6)]
    action_section = (struct.pack("<i", len(actions)) + b"".join(actions) +
                      struct.pack("<i", len(action_categories)) + b"".join(
                          action_category(name, category_id)
                          for name, category_id in action_categories))
    player = (struct.pack("<i", 1) + struct.pack("<i", 1) +
              aligned_string("Player") + aligned_string("Player") +
              struct.pack("<Ii", 1, 3) +
              struct.pack("<iiiiiiiii", 1, 0, 0, 1, 2, 0, 0, 4, 0))
    categories = [("Default", 0), ("Menu", 2), ("Book", 4)]
    map_category_table = struct.pack("<i", len(categories)) + b"".join(
        map_category(name, category_id) for name, category_id in categories)
    layout_tables = (
        struct.pack("<i", 2) + layout("Default", 0) + layout("Lefty", 2) +
        struct.pack("<i", 1) + layout("Default", 0) +
        struct.pack("<i", 1) + layout("Default", 0) +
        struct.pack("<i", 1) + layout("Default", 0)
    )
    return action_section + player + map_category_table + layout_tables


def collection(*maps: bytes) -> bytes:
    return input_manager_prefix() + struct.pack("<i", len(maps)) + b"".join(maps)


class RewiredControllerMapInspectorTests(unittest.TestCase):
    def parse(self, data: bytes, *, expected_count: int = 2,
              expected_ds4: int = 2) -> dict:
        return audit.parse_controller_map_collection(
            data, {"MenuToggle": 2, "Jump": 9, "Select": 58}, {DS4_GUID},
            expected_map_count=expected_count,
            expected_ds4_map_count=expected_ds4,
        )

    def test_decodes_action_and_ds4_element_fields(self):
        records = [
            action_element_map(1, 9, 1, 6,
                               trailing=(0xDEADBEEF,) * 7),
            action_element_map(0, 58, 0, 0),
        ]
        data = collection(
            controller_map(2, DS4_GUID, records),
            controller_map(14, DS4_GUID,
                           [action_element_map(0, audit.ACTION_ID_UNASSIGNED, 1, 15)],
                           category=4),
        )
        # The first count and all map bodies form one collection; expected
        # output uses only the first four words of each 44-byte entry.
        report = self.parse(data)
        self.assertEqual(report["serialized_map_count"], 2)
        self.assertEqual([(item["id"], item["name"])
                          for item in report["action_categories"]], [
            (0, "Default"), (1, "Menu"), (4, "Inventory"), (6, "Movement")])
        first, second = report["ds4_maps"]
        self.assertEqual((first["map_id"], first["category_id"],
                          first["category_name"], first["layout_id"],
                          first["layout_name"]), (2, 0, "Default", 0, "Default"))
        self.assertEqual(report["map_categories"], [
            {"id": 0, "name": "Default", "descriptive_name": "Default", "tag": "",
             "user_assignable": False, "checks_conflicts_with_all_categories": False,
             "check_conflict_category_ids": []},
            {"id": 2, "name": "Menu", "descriptive_name": "Menu", "tag": "",
             "user_assignable": False, "checks_conflicts_with_all_categories": False,
             "check_conflict_category_ids": []},
            {"id": 4, "name": "Book", "descriptive_name": "Book", "tag": "",
             "user_assignable": False, "checks_conflicts_with_all_categories": False,
             "check_conflict_category_ids": []},
        ])
        self.assertEqual(report["serialized_player_default"]["id"], 1)
        self.assertEqual(report["serialized_player_default"]["default_joystick_maps"], [
            {"enabled": True, "category_id": 0, "category_name": "Default",
             "layout_id": 0, "layout_name": "Default"},
            {"enabled": True, "category_id": 2, "category_name": "Menu",
             "layout_id": 0, "layout_name": "Default"},
            {"enabled": False, "category_id": 4, "category_name": "Book",
             "layout_id": 0, "layout_name": "Default"},
        ])
        self.assertEqual(first["action_element_maps"][0], {
            "action_category_id": 1,
            "action_category_name": "Menu",
            "action_id": 9,
            "action_name": "Jump",
            "input_action_category_id": 6,
            "input_action_category_name": "Movement",
            "element_type_id": 1,
            "element_type": "Button",
            "element_identifier_id": 6,
            "element_identifier_name": "Cross",
        })
        self.assertIsNone(second["action_element_maps"][0]["action_name"])
        self.assertIsNone(second["action_element_maps"][0]["input_action_category_id"])
        self.assertEqual(second["action_element_maps"][0]["action_id"],
                         audit.ACTION_ID_UNASSIGNED)

    def test_rejects_action_or_action_element_map_unknown_categories(self):
        unknown_map_category = collection(
            controller_map(2, DS4_GUID,
                           [action_element_map(99, 9, 1, 6)]),
            controller_map(14, DS4_GUID, []))
        with self.assertRaisesRegex(ValueError, "unknown action category"):
            self.parse(unknown_map_category)

        invalid_action = bytearray(collection(
            controller_map(2, DS4_GUID, [action_element_map(1, 9, 1, 6)]),
            controller_map(14, DS4_GUID, [])))
        marker = bytes(invalid_action).find(b"Jump")
        # InputAction categoryId follows four-byte ID, aligned name/type,
        # and three aligned description strings.
        category_id_offset = marker + 28
        struct.pack_into("<i", invalid_action, category_id_offset, 99)
        with self.assertRaisesRegex(ValueError, "InputAction references an unknown"):
            self.parse(bytes(invalid_action))

    def test_rejects_mismatched_list_count_and_noncontiguous_maps(self):
        one = controller_map(2, DS4_GUID,
                             [action_element_map(6, 9, 1, 6)])
        two = controller_map(14, DS4_GUID,
                             [action_element_map(0, 58, 1, 6)])
        with self.assertRaisesRegex(ValueError, "list count"):
            self.parse(input_manager_prefix() + struct.pack("<i", 3) + one + two)
        with self.assertRaisesRegex(ValueError, "not contiguous"):
            self.parse(input_manager_prefix() + struct.pack("<i", 2) +
                       one + b"\0\0\0\0" + two)

    def test_rejects_unknown_action_and_unsupported_element_type(self):
        unknown_action = controller_map(
            2, DS4_GUID, [action_element_map(0, 999, 1, 6)])
        with self.assertRaisesRegex(ValueError, "unknown action ID"):
            self.parse(collection(unknown_action,
                                 controller_map(14, DS4_GUID, [])))
        unknown_type = controller_map(
            2, DS4_GUID, [action_element_map(0, 9, 2, 6)])
        with self.assertRaisesRegex(ValueError, "ControllerElementType"):
            self.parse(collection(unknown_type,
                                 controller_map(14, DS4_GUID, [])))

    def test_rejects_unknown_ds4_element_and_truncated_record(self):
        unknown_element = controller_map(
            2, DS4_GUID, [action_element_map(0, 9, 1, 24)])
        with self.assertRaisesRegex(ValueError, "unknown hardware element"):
            self.parse(collection(unknown_element,
                                 controller_map(14, DS4_GUID, [])))
        truncated = collection(controller_map(
            2, DS4_GUID, [action_element_map(0, 9, 1, 6)]))[:-1]
        with self.assertRaisesRegex(ValueError, "truncated ActionElementMap"):
            self.parse(truncated, expected_count=1, expected_ds4=1)

    def test_rejects_unresolved_controller_map_category_or_layout(self):
        unknown_category = collection(controller_map(
            2, DS4_GUID, [action_element_map(0, 9, 1, 6)], category=99),
            controller_map(14, DS4_GUID, []))
        with self.assertRaisesRegex(ValueError, "unknown map category"):
            self.parse(unknown_category)
        unknown_layout = collection(controller_map(
            2, DS4_GUID, [action_element_map(0, 9, 1, 6)], layout=99),
            controller_map(14, DS4_GUID, []))
        with self.assertRaisesRegex(ValueError, "unknown joystick layout"):
            self.parse(unknown_layout)

    def test_rejects_invalid_candidate_and_duplicate_map_id(self):
        with self.assertRaisesRegex(ValueError, "hardware GUID string prefix"):
            self.parse(input_manager_prefix() + struct.pack("<i", 1) +
                       b"\0" * 20 + DS4_GUID.encode("ascii"),
                       expected_count=1, expected_ds4=1)
        duplicate_a = controller_map(2, DS4_GUID,
                                     [action_element_map(0, 9, 1, 6)])
        duplicate_b = controller_map(2, OTHER_GUID,
                                     [action_element_map(0, 9, 1, 6)])
        with self.assertRaisesRegex(ValueError, "duplicate ControllerMap ID"):
            self.parse(collection(duplicate_a, duplicate_b),
                       expected_count=2, expected_ds4=1)


if __name__ == "__main__":
    unittest.main()
