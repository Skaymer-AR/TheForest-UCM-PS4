import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inventory_unity_assets import classify, parse_listing, scan_directory, report


class UnityAssetInventoryTests(unittest.TestCase):
    def test_classify_specific_native_assets_without_inventing_rewired_bindings(self):
        self.assertEqual(classify("Media/Native/Data/globalgamemanagers"), "player-config")
        self.assertEqual(classify("Media/Native/Data/level0"), "scene-candidate")
        self.assertEqual(classify("Media/Native/Data/sharedassets1.assets"), "serialized-asset-candidate")
        self.assertEqual(classify("Media/StreamingAssets/forest.bundle"), "bundle-candidate")
        self.assertEqual(classify("Media/StreamingAssets/Rewired/actions.json"), "rewired-named-file")
        self.assertIsNone(classify("Media/Modules/Il2CppUserAssemblies.prx"))

    def test_parse_pkg_listing_does_not_report_header_lines(self):
        text = ("PKG : /tmp/file.pkg\n"
                "        12345  Media/Native/Data/level0\n"
                "           416  sce_sys/playgo-chunk.dat   (pkg entry)\n"
                "        12345  Media/Native/Data/globalgamemanagers\n")
        entries = parse_listing(text)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].path, "Media/Native/Data/level0")
        self.assertEqual(entries[1].path, "sce_sys/playgo-chunk.dat")
        rendered = report(entries)
        self.assertIn("globalgamemanagers", rendered)
        self.assertNotIn("playgo-chunk.dat", rendered)

    def test_scans_tree_without_mutating_anything(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "Media/Native/Data/level1"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"synthetic")
            result = scan_directory(root)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].size, 9)
            self.assertEqual(result[0].path, "Media/Native/Data/level1")


if __name__ == "__main__":
    unittest.main()
