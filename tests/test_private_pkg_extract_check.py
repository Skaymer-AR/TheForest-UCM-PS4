"""Offline tests only: no copyrighted game binaries and no console writes."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_private_pkg_extract as checker


class PrivatePkgExtractCheckTests(unittest.TestCase):
    def test_container_type_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample"
            cases = [
                (b"\x7fELF" + bytes(12), "decrypted ELF"),
                (bytes.fromhex("4f153d1d") + bytes(12), "SCE/SELF"),
                (b"OELF" + bytes(12), "OELF"),
                (b"ABCD" + bytes(12), "unrecognized"),
            ]
            for marker, label in cases:
                with self.subTest(label=label):
                    path.write_bytes(marker)
                    self.assertIn(label, checker.container_type(path))

    def test_sha256_and_select_single_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = root / "Media" / "Modules"
            a.mkdir(parents=True)
            path = a / "Il2CppUserAssemblies.prx"
            path.write_bytes(b"test data")
            self.assertEqual(checker.choose_one(root, "Il2CppUserAssemblies.prx"), path)
            self.assertEqual(checker.digest(path), hashlib.sha256(b"test data").hexdigest())
            with self.assertRaisesRegex(ValueError, "found 0"):
                checker.choose_one(root, "missing.dat")
            duplicate = root / "Il2CppUserAssemblies.prx"
            duplicate.write_bytes(b"another file")
            with self.assertRaisesRegex(ValueError, "found 2"):
                checker.choose_one(root, "Il2CppUserAssemblies.prx")

    def test_previous_elf_hash_is_only_compared_to_an_elf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "module"
            path.write_bytes(bytes.fromhex("4f153d1d") + bytes(12))
            self.assertIn("NOT COMPARABLE", checker.previous_elf_comparison(
                path, checker.PREVIOUS_PRX_SHA))
            path.write_bytes(b"\x7fELF" + bytes(12))
            self.assertEqual("SAME", checker.previous_elf_comparison(
                path, checker.PREVIOUS_PRX_SHA))
            self.assertEqual("DIFFERENT", checker.previous_elf_comparison(
                path, "0" * 64))


if __name__ == "__main__":
    unittest.main()

