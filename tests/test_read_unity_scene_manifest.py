import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import read_unity_scene_manifest as scenes


def fixture(paths):
    encoded = bytearray(1024)
    struct.pack_into(">IIII", encoded, 0, 80, len(encoded), 17, 128)
    encoded[20:28] = b"5.6.6f2\0"
    offset = 256
    struct.pack_into("<I", encoded, offset, len(paths))
    offset += 4
    for path in paths:
        data = path.encode()
        struct.pack_into("<I", encoded, offset, len(data))
        offset += 4
        encoded[offset:offset + len(data)] = data
        offset += (len(data) + 3) & ~3
    return bytes(encoded)


class SceneManifestTests(unittest.TestCase):
    def test_version_and_scene_order(self):
        data = fixture(["Assets/Scenes/logoLoad.unity",
                        "Assets/Scenes/ForestMain_v08.unity"])
        self.assertEqual(scenes.read_header(data)["player_version"], "5.6.6f2")
        offset, names = scenes.find_scene_list(data)
        self.assertEqual(offset, 256)
        self.assertEqual(names[1], "Assets/Scenes/ForestMain_v08.unity")

    def test_rejects_corrupt_header(self):
        data = bytearray(fixture(["Assets/Scenes/a.unity", "Assets/Scenes/b.unity"]))
        data[4:8] = b"\x00\x00\x00\x01"
        with self.assertRaisesRegex(ValueError, "size"):
            scenes.read_header(bytes(data))

    def test_rejects_fabricated_scene_count(self):
        data = bytearray(fixture(["Assets/Scenes/a.unity", "Assets/Scenes/b.unity"]))
        struct.pack_into("<I", data, 256, 128)
        with self.assertRaisesRegex(ValueError, "no validated"):
            scenes.find_scene_list(bytes(data))

    def test_derived_report_contains_no_asset_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "globalgamemanagers"
            path.write_bytes(fixture(["Assets/Scenes/a.unity", "Assets/Scenes/b.unity"]))
            result = scenes.analyze(path)
            self.assertEqual(result["scene_count"], 2)
            self.assertEqual(result["scene_table_file_offset"], "0x100")
            self.assertIn("no Rewired action map", result["limits"])


if __name__ == "__main__":
    unittest.main()
