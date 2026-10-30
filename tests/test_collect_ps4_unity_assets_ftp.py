"""Offline fake FTP tests: no PS4 connection or game bytes required."""
from __future__ import annotations

import ftplib
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_ps4_unity_assets_ftp import (
    EXPECTED, TITLE, collect, inventory, retrieve_verified,
)


class FakeReadOnlyFTP:
    def __init__(self, roots=None, contents=None):
        self.mounts = roots or ["/mnt/sandbox/pfsmnt/" + TITLE + "-app0"]
        self.contents = contents or {}
        self.commands = []

    def nlst(self, path):
        self.commands.append(("NLST", path))
        if path in ("/mnt/sandbox/pfsmnt", "/mnt/sandbox/pfsmount"):
            return self.mounts
        prefix = path + "/"
        return [item for item in self.contents if item.startswith(prefix)
                and "/" not in item[len(prefix):]]

    def retrbinary(self, command, callback, blocksize=8192):
        self.commands.append(("RETR", command))
        if not command.startswith("RETR "):
            raise AssertionError("unexpected command")
        path = command[5:]
        if path not in self.contents:
            raise ftplib.error_perm("550 not found")
        content = self.contents[path]
        for i in range(0, len(content), blocksize):
            callback(content[i:i+blocksize])


class ReadOnlyCollectorTests(unittest.TestCase):
    def test_inventory_is_bounded_to_matching_mount_and_expected_filenames(self):
        prefix = "/mnt/sandbox/pfsmnt/CUSA12398-app0/Media/"
        fake = FakeReadOnlyFTP(
            roots=["CUSA12398-app0", "/mnt/sandbox/pfsmnt/CUSA00000-app0"],
            contents={prefix + "level1": b"abc", prefix + "unrelated.bin": b"x"})
        found = inventory(fake)
        self.assertEqual(found["level1"], [prefix + "level1"])
        self.assertTrue(all(not found[x] for x in EXPECTED if x != "level1"))
        self.assertTrue(all(verb == "NLST" for verb, _ in fake.commands))


    def test_union_mount_is_preferred_and_fallback_root_is_supported(self):
        filename = "sharedassets0.assets"
        union_path = "/mnt/sandbox/pfsmount/CUSA12398-app0-patch0-union/Media/" + filename
        app_path = "/mnt/sandbox/pfsmount/CUSA12398-app0/Media/" + filename

        class OnlyPfsmount(FakeReadOnlyFTP):
            def nlst(self, path):
                if path == "/mnt/sandbox/pfsmnt":
                    raise ftplib.error_perm("550 unavailable")
                if path == "/mnt/sandbox/pfsmount":
                    return ["CUSA12398-app0", "CUSA12398-app0-patch0-union"]
                return super().nlst(path)

        fake = OnlyPfsmount(contents={union_path: b"union", app_path: b"base"})
        found = inventory(fake)
        self.assertEqual(found[filename], [union_path, app_path])
        self.assertFalse(any(command[0] == "RETR" for command in fake.commands))

    def test_dry_run_never_downloads(self):
        fake = FakeReadOnlyFTP()
        with tempfile.TemporaryDirectory() as work:
            result = collect(fake, Path(work), False)
            self.assertEqual(len(result["files"]), 6)
            self.assertFalse(any(x[0] == "RETR" for x in fake.commands))
            self.assertFalse(list(Path(work).iterdir()))

    def test_hash_verified_download_only(self):
        prefix = "/mnt/sandbox/pfsmnt/CUSA12398-patch0/Media/"
        payload = b"synthetic safe asset"
        fake = FakeReadOnlyFTP(
            roots=["CUSA12398-patch0"],
            contents={prefix + "level1": payload})
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / "level1"
            out = retrieve_verified(fake, prefix + "level1", target,
                                    hashlib.sha256(payload).hexdigest())
            self.assertEqual(out["status"], "downloaded")
            self.assertEqual(target.read_bytes(), payload)
            self.assertTrue(all(x[0] == "RETR" for x in fake.commands))

    def test_mismatch_never_publishes_file_or_leaves_temp(self):
        prefix = "/mnt/sandbox/pfsmnt/CUSA12398-app0/Media/"
        fake = FakeReadOnlyFTP(contents={prefix + "level1": b"WRONG"})
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / "level1"
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                retrieve_verified(fake, prefix + "level1", target, EXPECTED["level1"])
            self.assertEqual(list(Path(work).iterdir()), [])

    def test_existing_file_never_overwritten(self):
        prefix = "/mnt/sandbox/pfsmnt/CUSA12398-app0/Media/"
        fake = FakeReadOnlyFTP(contents={prefix + "level1": b"unexpected"})
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / "level1"
            target.write_bytes(b"existing data")
            with self.assertRaisesRegex(ValueError, "Existing local file"):
                retrieve_verified(fake, prefix + "level1", target, EXPECTED["level1"])
            self.assertEqual(target.read_bytes(), b"existing data")
            self.assertEqual(fake.commands, [])


    def test_remote_ftp_error_is_reported_without_publishing(self):
        prefix = "/mnt/sandbox/pfsmnt/CUSA12398-app0/Media/"

        class InterruptedFTP(FakeReadOnlyFTP):
            def retrbinary(self, command, callback, blocksize=8192):
                raise ftplib.error_temp("421 test interruption")

        fake = InterruptedFTP(contents={prefix + "level1": b"synthetic"})
        with tempfile.TemporaryDirectory() as work:
            result = collect(fake, Path(work), True)
            selected = next(item for item in result["files"] if item["name"] == "level1")
            self.assertEqual(selected["status"], "unverified")
            self.assertEqual(len(selected["failures"]), 1)
            self.assertEqual(list(Path(work).iterdir()), [])

    def test_unmounted_game_fails_without_file_transfer(self):
        fake = FakeReadOnlyFTP(roots=["/mnt/sandbox/pfsmnt/CUSA00000-app0"])
        with self.assertRaisesRegex(ValueError, "No active CUSA12398"):
            inventory(fake)
        self.assertFalse(any(x[0] == "RETR" for x in fake.commands))


if __name__ == "__main__":
    unittest.main()
