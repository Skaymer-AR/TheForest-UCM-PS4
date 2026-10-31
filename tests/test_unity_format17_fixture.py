from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_unity_rewired_assets import Asset  # noqa: E402
from unity_format17_fixture import (  # noqa: E402
    GAMEOBJECT_ID,
    LIBRARY_FILE,
    MONOBEHAVIOUR_ID,
    SCENE_FILE,
    TRANSFORM_ID,
    build_fixture,
    validate_fixture,
)


class UnityFormat17FixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = build_fixture(self.root)
        self.scene = self.root / SCENE_FILE
        self.library = self.root / LIBRARY_FILE

    def tearDown(self):
        self.temp.cleanup()

    def _mutated_scene(self, name: str, mutate) -> Path:
        path = self.root / name
        data = bytearray(self.scene.read_bytes())
        mutate(data)
        path.write_bytes(data)
        return path

    def test_generated_graph_has_gameobject_transform_mono_and_dependency(self):
        report = validate_fixture(self.scene, self.library)
        self.assertEqual(report["format"], 17)
        self.assertEqual(report["gameobject"]["components"],
                         [(0, TRANSFORM_ID), (0, MONOBEHAVIOUR_ID)])
        self.assertEqual(report["transform"]["gameobject"], (0, GAMEOBJECT_ID))
        self.assertEqual(report["monobehaviour"]["script"], (1, 900))
        self.assertEqual(report["external"], LIBRARY_FILE)

    def test_fixture_generation_is_deterministic(self):
        other = self.root / "second-build"
        second_manifest = build_fixture(other)
        self.assertEqual(self.manifest["fixture_sha256"],
                         second_manifest["fixture_sha256"])
        self.assertEqual(self.scene.read_bytes(),
                         (other / SCENE_FILE).read_bytes())
        self.assertEqual(self.library.read_bytes(),
                         (other / LIBRARY_FILE).read_bytes())

    def test_truncated_file_rejected(self):
        data = self.scene.read_bytes()
        path = self.root / "truncated.assets"
        path.write_bytes(data[:-1])
        with self.assertRaisesRegex(ValueError, "header"):
            Asset(path)

    def test_invalid_data_offset_rejected(self):
        def mutate(data):
            struct.pack_into(">I", data, 12, 64)
        path = self._mutated_scene("bad-data-offset.assets", mutate)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            Asset(path)

    def test_object_offset_past_end_rejected(self):
        offset = self.manifest["descriptor_offsets"]["scene"][TRANSFORM_ID]
        def mutate(data):
            struct.pack_into("<I", data, offset + 8, 0xFFFFFFF0)
        path = self._mutated_scene("bad-object-offset.assets", mutate)
        with self.assertRaisesRegex(ValueError, "object descriptor"):
            Asset(path)

    def test_duplicate_path_id_rejected(self):
        descriptors = self.manifest["descriptor_offsets"]["scene"]
        first = descriptors[GAMEOBJECT_ID]
        second = descriptors[TRANSFORM_ID]
        def mutate(data):
            path_id = struct.unpack_from("<q", data, first)[0]
            struct.pack_into("<q", data, second, path_id)
        path = self._mutated_scene("duplicate-path-id.assets", mutate)
        with self.assertRaisesRegex(ValueError, "duplicate object ID"):
            Asset(path)

    def test_dangling_component_pointer_rejected(self):
        asset = Asset(self.scene)
        go_offset = asset.objects[GAMEOBJECT_ID].offset
        def mutate(data):
            struct.pack_into("<q", data, go_offset + 8, 999999)
        path = self._mutated_scene("dangling-component.assets", mutate)
        with self.assertRaisesRegex(ValueError, "unresolved component PPtr"):
            validate_fixture(path, self.library)

    def test_out_of_range_script_dependency_rejected(self):
        asset = Asset(self.scene)
        mb_offset = asset.objects[MONOBEHAVIOUR_ID].offset
        def mutate(data):
            struct.pack_into("<i", data, mb_offset + 16, 2)
        path = self._mutated_scene("dangling-script.assets", mutate)
        with self.assertRaisesRegex(ValueError, "dependency index"):
            validate_fixture(path, self.library)


if __name__ == "__main__":
    unittest.main()
