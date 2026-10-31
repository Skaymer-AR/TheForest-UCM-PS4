"""Synthetic fixture tests plus a safe regression against derived, noncommercial data."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_rewired_menu_input_conflicts as audit


def fixture():
    ids = {str(k): v for k, v in audit.MENU_ELEMENTS.items()}
    return {
        "title": "The Forest PS4 CUSA12398 v1.15",
        "asset": {"sha256": audit.PINNED_ASSET},
        "hardware_profile": "SonyDualShock4",
        "hardware_guid_identifiers": list(audit.PINNED_GUIDS),
        "element_identifier_ids": ids,
        "input_managers": [{
            "prefab": "Rewired Input Manager XInput",
            "serialized_player_default": {
                "default_joystick_maps": [
                    {"category_id": 0, "layout_id": 0, "enabled": True},
                    {"category_id": 2, "layout_id": 0, "enabled": False},
                ],
            },
            "ds4_maps": [{
                "map_id": 3, "category_id": 0, "category_name": "Default",
                "layout_id": 0, "layout_name": "Default",
                "hardware_guid": audit.PINNED_GUIDS[0],
                "action_element_map_count": 2,
                "action_element_maps": [
                    {"element_identifier_id": 10, "element_identifier_name": "L1",
                     "action_id": 40, "action_name": "PreviousPage",
                     "element_type": "Button"},
                    {"element_identifier_id": 11, "element_identifier_name": "R1",
                     "action_id": 41, "action_name": "NextPage",
                     "element_type": "Button"},
                ],
            }],
        }],
    }


class RewiredMenuConflictTests(unittest.TestCase):
    def test_synthetic_chord_is_static_candidate_never_runtime_permission(self):
        result = audit.inspect(fixture())
        self.assertEqual(result["candidate_bindings_total"], 2)
        self.assertEqual(result["manager_guid_groups_with_l1_and_r1_candidates"], 1)
        self.assertTrue(result["input_contexts"][0]["l1_r1_both_assigned_in_enabled_defaults"])
        self.assertIsNone(result["input_contexts"][0]["runtime_safe_to_intercept_input"])
        self.assertFalse(result["menu_installable_or_tested"])

    def test_disabled_category_has_no_enabled_default_candidate(self):
        data = fixture()
        data["input_managers"][0]["serialized_player_default"]["default_joystick_maps"][0]["enabled"] = False
        result = audit.inspect(data)
        self.assertEqual(result["candidate_bindings_total"], 0)
        self.assertEqual(result["manager_guid_groups_with_l1_and_r1_candidates"], 0)

    def test_reject_mismatched_asset_and_hardware_profile(self):
        for field, value in (("sha256", "0" * 64),):
            data = fixture()
            data["asset"][field] = value
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                audit.inspect(data)
        data = fixture()
        data["hardware_profile"] = "Unknown"
        with self.assertRaisesRegex(ValueError, "hardware profile"):
            audit.inspect(data)

    def test_reject_false_mapping_identity(self):
        data = fixture()
        data["input_managers"][0]["ds4_maps"][0]["action_element_maps"][0]["element_identifier_name"] = "Circle"
        with self.assertRaisesRegex(ValueError, "label/ID"):
            audit.inspect(data)

    def test_reject_bad_map_and_default_counts(self):
        data = fixture()
        data["input_managers"][0]["ds4_maps"][0]["action_element_map_count"] = 1
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            audit.inspect(data)
        data = fixture()
        data["input_managers"][0]["serialized_player_default"]["default_joystick_maps"][0]["enabled"] = "true"
        with self.assertRaisesRegex(ValueError, "enable flag"):
            audit.inspect(data)

    def test_reject_duplicate_or_unknown_controller_map(self):
        data = fixture()
        data["input_managers"][0]["ds4_maps"].append(copy.deepcopy(data["input_managers"][0]["ds4_maps"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate controller-map"):
            audit.inspect(data)
        data = fixture()
        data["input_managers"][0]["ds4_maps"][0]["hardware_guid"] = "invalid-guid"
        with self.assertRaisesRegex(ValueError, "unknown serialized controller GUID"):
            audit.inspect(data)

    def test_derived_project_data_has_four_overlap_groups(self):
        src = (Path(__file__).resolve().parents[1] /
               "docs/REWIRED_CONTROLLER_MAPS_20261030.json")
        result = audit.inspect(json.loads(src.read_text(encoding="utf-8")))
        self.assertEqual(len(result["input_contexts"]), 4)
        self.assertEqual(result["manager_guid_groups_with_l1_and_r1_candidates"], 4)
        self.assertEqual(result["candidate_bindings_total"], 92)
        self.assertTrue(all(not group["menu_toggle_has_serialized_ds4_binding"]
                            for group in result["input_contexts"]))
        self.assertTrue(all(group["runtime_safe_to_intercept_input"] is None
                            for group in result["input_contexts"]))


if __name__ == "__main__":
    unittest.main()
