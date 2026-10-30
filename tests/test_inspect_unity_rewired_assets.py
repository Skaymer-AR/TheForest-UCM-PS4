"""Synthetic-only tests. No commercial game bytes are included."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_unity_rewired_assets as audit


def ptr(file_id, path_id):
    return struct.pack("<iq", file_id, path_id)


def string(value):
    raw = value.encode("utf-8")
    result = struct.pack("<i", len(raw)) + raw
    return result + b"\0" * (-len(result) % 4)


def gameobject(name, components):
    return (struct.pack("<i", len(components)) +
            b"".join(ptr(*entry) for entry in components) +
            struct.pack("<i", 0) + string(name) + struct.pack("<HB", 0, 1))


def mono(go_id, script_id, extra=b""):
    return ptr(0, go_id) + b"\x01\x00\x00\x00" + ptr(1, script_id) + string("") + extra


def monoscript(name, namespace, assembly):
    return (string(name) + b"\0" * 20 + string(name) +
            string(namespace) + string(assembly))


def action_bytes(select_id):
    entries = [
        (2, "MenuToggle"), (3, "Esc"), (43, "Back"),
        (7, "Horizontal"), (8, "Vertical"), (9, "Jump"), (11, "Run"),
        (10, "Fire1"), (19, "Inventory"), (30, "Batch"),
        (53, "Rebind"), (55, "RestoreDefaults"),
        (select_id, "Select")
    ]
    return (b"".join(struct.pack("<II", code, len(name)) +
                     name.encode("ascii") +
                     b"\0" * (-len(name) % 4)
                     for code, name in entries) +
            b"\0" * 8 + b"Navigate and interact with menu")


def build_asset(path, objects, externals):
    """Construct a synthetic Unity v17 no-typetree file with bounded objects."""
    types = list(dict.fromkeys(class_id for _, class_id, _ in objects))
    meta = bytearray(20)
    meta += b"5.6.6f2\0"
    meta += struct.pack("<iB", 31, 0)
    meta += struct.pack("<i", len(types))
    for class_id in types:
        meta += struct.pack("<iBh", class_id, 0, -1)
        if class_id == 114:
            meta += bytes(16)
        meta += bytes(16)
    meta += struct.pack("<i", len(objects))
    chunks = bytearray()
    for pid, class_id, raw in objects:
        meta += bytes(-len(meta) % 4)
        meta += struct.pack("<qIIi", pid, len(chunks), len(raw), types.index(class_id))
        chunks += raw
    meta += struct.pack("<ii", 0, len(externals))  # script types, externals
    for name in externals:
        meta += b"\0" + bytes(16) + struct.pack("<i", 0) + name.encode() + b"\0"
    meta += b"\0"  # user-information
    data_offset = max(512, (len(meta) + 15) & ~15)
    meta[:16] = struct.pack(">IIII", len(meta), data_offset + len(chunks), 17, data_offset)
    filedata = bytes(meta).ljust(data_offset, b"\0") + chunks
    path.write_bytes(filedata)


class UnityRewiredInspectorTests(unittest.TestCase):
    def test_action_catalog_does_not_stop_at_restore_defaults(self):
        actions = audit.action_catalog(b"\0" * 8 + action_bytes(58))
        self.assertEqual(actions["MenuToggle"], 2)
        self.assertEqual(actions["RestoreDefaults"], 55)
        self.assertEqual(actions["Select"], 58)
        with self.assertRaisesRegex(ValueError, "MenuToggle"):
            audit.action_catalog(bytes(100))

    def test_reject_invalid_string_and_script(self):
        with self.assertRaisesRegex(ValueError, "aligned Unity string"):
            audit.aligned_string(struct.pack("<i", 5000), 0)
        with self.assertRaisesRegex(ValueError, "MonoScript"):
            audit.monoscript(string("A"))

    def test_full_synthetic_cross_file_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_asset(root / "globalgamemanagers.assets", [
                (1352, 115, monoscript("InputManager", "Rewired", "Assembly-CSharp.dll")),
                (3035, 115, monoscript("RewiredSpawner", "TheForest.Utils", "Assembly-CSharp.dll")),
                (3715, 115, monoscript("HardwareJoystickMap", "Rewired.Data.Mapping", "Rewired_Core.dll")),
                (266, 115, monoscript("InputMappingButton", "TheForest.Utils", "Assembly-CSharp.dll")),
            ], [])
            hardware_guids = b"83b427e4-086f-47f3-bb06-be266abd1ca5;cd9718bf-a87a-44bc-8716-60a0def28a9f"
            build_asset(root / "sharedassets0.assets", [
                (21, 1, gameobject("Rewired Input Manager VR", [(0, 192)])),
                (22, 1, gameobject("Rewired Input Manager XInput", [(0, 193)])),
                (192, 114, mono(21, 1352, b"\0" * 16 + action_bytes(57) + hardware_guids)),
                (193, 114, mono(22, 1352, b"\0" * 16 + action_bytes(58) + hardware_guids)),
                (133, 114, mono(0, 3715, b"SonyDualShock4" + hardware_guids)),
            ], ["globalgamemanagers.assets"])
            build_asset(root / "sharedassets1.assets", [
                (500, 1, gameobject("inputMapButton_run", [(0, 501)])),
                (501, 114, mono(500, 266, string("Run"))),
            ], ["globalgamemanagers.assets"])
            for scene, go_id, mb_id in (
                ("level0", 8, 38),
                ("level1", 744, 2859),
                ("level2", 3961, 193462),
            ):
                build_asset(root / scene, [
                    (go_id, 1, gameobject("Rewired Spawner", [(0, mb_id)])),
                    (mb_id, 114, mono(go_id, 3035,
                                      ptr(2, 21) + ptr(2, 22) + bytes(12))),
                ], ["globalgamemanagers.assets", "sharedassets0.assets"])

            report = audit.analyze(root)
            self.assertEqual(report["unity_version"], "5.6.6f2")
            self.assertEqual(report["monoscripts_in_library"], 4)
            self.assertEqual(len(report["spawners"]), 3)
            self.assertEqual(report["spawners"][2]["prefabs"][1]["path_id"], 22)
            self.assertEqual(report["input_manager_prefabs"]["21"]["actions"]["Select"], 57)
            self.assertEqual(report["input_manager_prefabs"]["22"]["actions"]["Select"], 58)
            vr = report["input_manager_prefabs"]["21"]
            self.assertEqual(len(vr["components"]), 1)
            self.assertEqual(vr["components"][0]["script"], "Rewired.InputManager")
            self.assertTrue(vr["components"][0]["enabled"])
            self.assertEqual(report["generic_hardware_profiles"][0]["profile"], "SonyDualShock4")
            self.assertEqual(
                len(report["input_manager_prefabs"]["21"]["matching_hardware_identifiers"]), 2)
            self.assertEqual(
                report["input_manager_prefabs"]["21"]["matching_hardware_identifiers"],
                report["input_manager_prefabs"]["22"]["matching_hardware_identifiers"])
            self.assertIn("Select", report["varying_action_name_ids"])
            self.assertEqual(len(report["serialized_input_mapping_buttons"]), 1)
            self.assertEqual(report["serialized_input_mapping_buttons"][0]["action"], "Run")
            self.assertIn("not a physical DualShock", report["limitations"][1])

    def test_invalid_header_does_not_fall_back_to_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "bad"
            build_asset(file, [(1, 1, gameobject("test", []))], [])
            raw = bytearray(file.read_bytes())
            raw[11] = 22  # corrupt format version (was 17)
            file.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "unsupported"):
                audit.Asset(file)


if __name__ == "__main__":
    unittest.main()
