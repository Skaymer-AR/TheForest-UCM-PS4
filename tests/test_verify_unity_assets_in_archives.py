"""Synthetic ZIP-only scanner tests. Never embeds commercial assets."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_unity_assets_in_archives as scan


class ArchiveAssetScannerTests(unittest.TestCase):
    def test_read_only_scan_and_verification(self):
        contents = {"level0": b"synthetic-level-zero",
                    "sharedassets0.assets": b"synthetic-shared-zero"}
        expected = {name: hashlib.sha256(data).hexdigest()
                    for name, data in contents.items()}
        with tempfile.TemporaryDirectory() as folder, patch.dict(scan.EXPECTED, expected):
            archive = Path(folder) / "game.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("TheForest/Media/level0", contents["level0"])
                z.writestr("Media/sharedassets0.assets", contents["sharedassets0.assets"])
                z.writestr("other/unknown.dat", b"irrelevant")
            result = scan.inspect_zip(archive)
            self.assertEqual(result["status"], "scanned")
            self.assertEqual(len(result["candidates"]), 2)
            self.assertTrue(all(row["status"] == "verified"
                                for row in result["candidates"]))
            self.assertEqual(sorted(Path(folder).iterdir()), [archive])

    def test_verification_and_explicit_extraction(self):
        fake = b"simulated data"
        name = "level1"
        sha = hashlib.sha256(fake).hexdigest()
        with tempfile.TemporaryDirectory() as folder, patch.dict(scan.EXPECTED,
                                                                   {name: sha}, clear=True):
            archive = Path(folder) / "source.zip"
            dest = Path(folder) / "private"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("Media/" + name, fake)
            result = scan.inspect_all([archive], dest)
            self.assertTrue(result["all_six_verified"])
            self.assertEqual((dest / name).read_bytes(), fake)
            self.assertEqual(result["archives"][0]["candidates"][0]["status"],
                             "extracted_verified")
            again = scan.inspect_all([archive], dest)
            self.assertEqual(again["archives"][0]["candidates"][0]["status"],
                             "verified_existing")

    def test_wrong_hash_does_not_publish(self):
        name = "level2"
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "source.zip"
            dest = Path(folder) / "private"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("Media/" + name, b"not the real asset")
            result = scan.inspect_all([archive], dest)
            self.assertFalse(result["all_six_verified"])
            self.assertEqual(result["archives"][0]["candidates"][0]["status"],
                             "hash_mismatch")
            self.assertFalse((dest / name).exists())
            self.assertEqual(list(dest.iterdir()), [])

    def test_path_traversal_and_misleading_directory_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "source.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for path in ("../Media/level0", "/Media/level1", "Mods/level2",
                             "Media/../level1", "Media/level0/"):
                    z.writestr(path, b"unsafe or unrelated")
            result = scan.inspect_zip(archive)
            self.assertEqual(result["candidates"], [])

    def test_file_limit_and_invalid_zip(self):
        info = zipfile.ZipInfo("Media/level0")
        info.file_size = scan.MAX_ENTRY_SIZE + 1
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "bad.zip"
            archive.write_bytes(b"not a ZIP")
            self.assertEqual(scan.inspect_zip(archive)["status"], "archive_error")
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("Media/level0", b"xyz")
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(scan.recognized_member(z.infolist()[0]), "level0")


if __name__ == "__main__":
    unittest.main()
