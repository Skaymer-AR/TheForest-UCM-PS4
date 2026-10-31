import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_unity_rewired_assets import Asset
from inspect_ongui_scene_hosts import (
    ancestry, read_ongui_methods, read_exec_mapping, transform_parent
)
from test_inspect_unity_rewired_assets import build_asset, gameobject, ptr


def make_transform(go_id, parent_transform_id=0):
    return ptr(0, go_id) + bytes(40) + struct.pack("<i", 0) + ptr(0, parent_transform_id)


def make_metadata():
    buf = bytearray(1024)
    names = ["string_literals", "string_literal_data", "strings", "events", "properties",
             "methods", "parameter_defaults", "field_defaults", "default_value_data",
             "marshaled_sizes", "parameters", "fields", "generic_parameters",
             "generic_constraints", "generic_containers", "nested_types", "interfaces",
             "vtables", "interface_offsets", "types", "rgctx", "images", "assemblies",
             "metadata_usage_lists", "metadata_usage_pairs", "field_refs",
             "referenced_assemblies", "attributes", "attribute_types",
             "unresolved_virtual_parameter_types",
             "unresolved_virtual_parameter_ranges", "windows_runtime_types"]
    struct.pack_into("<II", buf, 0, 0xFAB11BAF, 23)
    strings = b"PlayMakerGUI\0OnGUI\0"
    for i, n in enumerate(names):
        if n == "strings": off, size = 300, len(strings)
        elif n == "types": off, size = 400, 104
        elif n == "methods": off, size = 600, 56
        else: off, size = 280, 0
        struct.pack_into("<II", buf, 8 + 8*i, off, size)
    buf[300:300+len(strings)] = strings
    struct.pack_into("<II", buf, 400, 0, 12)  # class + empty namespace
    struct.pack_into("<i", buf, 400 + 52, 0)  # methodStart
    struct.pack_into("<H", buf, 400 + 80, 1)  # method count
    struct.pack_into("<I", buf, 600, 13)  # "OnGUI"
    struct.pack_into("<i", buf, 600 + 24, 31674)
    return bytes(buf)


class UnityOnGuiHostTests(unittest.TestCase):
    def test_parses_metadata_method_name_and_pointer_index(self):
        self.assertEqual(read_ongui_methods(make_metadata()), {"PlayMakerGUI": (0, 31674)})
        damaged = bytearray(make_metadata())
        damaged[0:4] = bytes(4)
        with self.assertRaisesRegex(ValueError, "metadata version"):
            read_ongui_methods(damaged)

    def test_executable_va_mapping_requires_pt_load(self):
        elf = bytearray(512)
        elf[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<Q", elf, 32, 64)
        struct.pack_into("<HH", elf, 54, 56, 1)
        struct.pack_into("<IIQQQQQQ", elf, 64, 1, 5, 0x100, 0x1000, 0, 0x60, 0x60, 0x1000)
        self.assertEqual(read_exec_mapping(elf, 0x1010, 16), 0x110)
        with self.assertRaisesRegex(ValueError, "executable segment"):
            read_exec_mapping(elf, 0x1060, 16)
        struct.pack_into("<I", elf, 68, 4)  # remove execute flag
        with self.assertRaisesRegex(ValueError, "executable segment"):
            read_exec_mapping(elf, 0x1010, 16)

    def test_inactive_parent_and_active_root(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "level2"
            parent = bytearray(gameobject("PauseMenu", [(0, 21)]))
            parent[-1] = 0
            build_asset(path, [
                (10, 1, gameobject("Panel - Main", [(0, 11)])),
                (11, 4, make_transform(10, 21)),
                (20, 1, bytes(parent)),
                (21, 4, make_transform(20)),
                (30, 1, gameobject("PlayMakerGUI", [(0, 31)])),
                (31, 4, make_transform(30)),
            ], [])
            asset = Asset(path)
            chain = ancestry(asset, 10)
            self.assertFalse(chain["active_in_serialized_hierarchy"])
            self.assertEqual([node["name"] for node in chain["chain"]],
                             ["Panel - Main", "PauseMenu"])
            root = ancestry(asset, 30)
            self.assertTrue(root["active_in_serialized_hierarchy"])
            self.assertEqual(len(root["chain"]), 1)
            self.assertEqual(transform_parent(asset, 31), None)

    def test_cycle_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "level2"
            build_asset(path, [
                (10, 1, gameobject("A", [(0, 11)])),
                (11, 4, make_transform(10, 21)),
                (20, 1, gameobject("B", [(0, 21)])),
                (21, 4, make_transform(20, 11)),
            ], [])
            with self.assertRaisesRegex(ValueError, "cycle"):
                ancestry(Asset(path), 10)

    def test_refuses_missing_transform_instead_of_claiming_active(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "level2"
            build_asset(path, [(10, 1, gameobject("NoTransform", []))], [])
            with self.assertRaisesRegex(ValueError, "one plain Transform"):
                ancestry(Asset(path), 10)


if __name__ == "__main__":
    unittest.main()
