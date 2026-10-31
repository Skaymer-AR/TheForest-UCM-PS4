"""Bounded synthetic PlayMaker component in a real Unity format-17 object table."""
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_unity_rewired_assets import Asset
from unity_format17_fixture import MONOBEHAVIOUR_ID
from unity_format17_playmaker_fixture import (
    ACTION_NAMES, SCENE_FILE, LIBRARY_FILE, build_fixture, validate_fixture,
)


class UnityPlayMakerFormat17Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = build_fixture(self.root)
        self.scene = self.root / SCENE_FILE
        self.library = self.root / LIBRARY_FILE

    def mutate_component(self, label, modify):
        asset = Asset(self.scene)
        obj = asset.objects[MONOBEHAVIOUR_ID]
        data = bytearray(self.scene.read_bytes())
        modify(data, obj.offset, obj.size)
        path = self.root / label
        path.write_bytes(data)
        return path

    def test_component_inside_unity_container(self):
        result = validate_fixture(self.scene, self.library)
        self.assertEqual(result["action_names"], list(ACTION_NAMES))
        self.assertTrue(result["synthetic_only"])
        self.assertEqual(result["component_sha256"], self.manifest["component_sha256"])

    def test_bytes_are_deterministic(self):
        other = self.root / "other"
        self.assertEqual(build_fixture(other), self.manifest)
        self.assertEqual(self.scene.read_bytes(), (other / SCENE_FILE).read_bytes())

    def test_script_pointer_corruption_rejected(self):
        path = self.mutate_component(
            "wrong-script.assets",
            lambda b, offset, size: struct.pack_into("<q", b, offset + 20, 999))
        with self.assertRaisesRegex(ValueError, "MonoBehaviour base fields"):
            validate_fixture(path, self.library)

    def test_unresolved_fsm_template_rejected(self):
        def bad_pointer(data, offset, size):
            struct.pack_into("<iq", data, offset + size - 12, 1, 999)
        path = self.mutate_component("bad-template.assets", bad_pointer)
        with self.assertRaisesRegex(ValueError, "opaque tail placeholder or template"):
            validate_fixture(path, self.library)

    def test_action_identity_corruption_rejected(self):
        def bad_action(data, offset, size):
            position = bytes(data[offset:offset + size]).find(b"GUIBox")
            self.assertGreater(position, 0)
            data[offset + position] = ord("X")
        path = self.mutate_component("bad-action.assets", bad_action)
        with self.assertRaisesRegex(ValueError, "action list mismatch"):
            validate_fixture(path, self.library)

    def test_truncated_fsm_object_rejected(self):
        asset = Asset(self.scene)
        obj = asset.objects[MONOBEHAVIOUR_ID]
        data = bytearray(self.scene.read_bytes())
        # A malformed descriptor length cannot silently truncate opaque FSM data.
        descriptor = struct.pack("<q", MONOBEHAVIOUR_ID)
        # Inspect the asset descriptor, not an arbitrary in-object byte sequence.
        # Version-17 object descriptors align PathID to 4 bytes.
        pos = data.find(descriptor, 20, struct.unpack_from(">I", data, 12)[0])
        self.assertNotEqual(pos, -1)
        struct.pack_into("<I", data, pos + 12, obj.size - 1)
        path = self.root / "short-fsm.assets"
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            validate_fixture(path, self.library)


if __name__ == "__main__":
    unittest.main()
