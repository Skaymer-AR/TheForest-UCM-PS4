"""Synthetic tests for the private package-tree change gate."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_private_pkg_tree as audit


class PrivatePkgTreeAuditTests(unittest.TestCase):
    def make_tree(self, root: Path, files: dict[str, bytes]) -> None:
        for relative, contents in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)

    def test_identical_trees_pass_and_report_only_relative_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "base"
            candidate = Path(temp) / "candidate"
            base.mkdir()
            candidate.mkdir()
            files = {"eboot.bin": b"synthetic executable",
                     "sce_sys/param.sfo": b"synthetic sfo",
                     "Media/level2": b"synthetic scene"}
            self.make_tree(base, files)
            self.make_tree(candidate, files)
            result = audit.audit_trees(base, candidate,
                                       required_paths=["eboot.bin", "sce_sys/param.sfo"])
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(result["changes"], [])
            self.assertNotIn(str(base), json.dumps(result))

    def test_only_exact_allowlisted_scene_change_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "base"
            candidate = Path(temp) / "candidate"
            base.mkdir()
            candidate.mkdir()
            self.make_tree(base, {"Media/level2": b"original scene",
                                  "Media/eboot.bin": b"unchanged executable"})
            self.make_tree(candidate, {"Media/level2": b"modified synthetic copy",
                                       "Media/eboot.bin": b"unchanged executable"})
            result = audit.audit_trees(base, candidate,
                                       allow_changes=["Media/level2"],
                                       required_paths=["Media/eboot.bin"])
            self.assertEqual(result["result"], "PASS")
            self.assertEqual([(x["path"], x["status"]) for x in result["changes"]],
                             [("Media/level2", "changed")])

    def test_unlisted_mutation_fails_even_when_another_file_is_allowlisted(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "base"
            candidate = Path(temp) / "candidate"
            base.mkdir()
            candidate.mkdir()
            self.make_tree(base, {"Media/level2": b"level", "eboot.bin": b"original"})
            self.make_tree(candidate, {"Media/level2": b"new level", "eboot.bin": b"changed"})
            result = audit.audit_trees(base, candidate, allow_changes=["Media/level2"])
            self.assertEqual(result["result"], "FAIL")
            self.assertEqual(result["unexpected_change_paths"], ["eboot.bin"])

    def test_added_removed_and_missing_required_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "base"
            candidate = Path(temp) / "candidate"
            base.mkdir()
            candidate.mkdir()
            self.make_tree(base, {"Media/level2": b"level", "Media/old": b"old"})
            self.make_tree(candidate, {"Media/level2": b"level", "Media/new": b"new"})
            result = audit.audit_trees(base, candidate,
                                       allow_changes=["Media/old", "Media/new"],
                                       required_paths=["eboot.bin"])
            self.assertEqual(result["result"], "FAIL")
            self.assertEqual(result["missing_required_paths"], ["eboot.bin"])
            self.assertEqual([x["status"] for x in result["changes"]], ["added", "removed"])

    def test_rejects_path_traversal_symlinks_and_case_collisions(self):
        with self.assertRaises(audit.AuditError):
            audit.normalize_relative("../eboot.bin")
        with self.assertRaises(audit.AuditError):
            audit.normalize_relative("Media\\level2")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "tree"
            root.mkdir()
            (root / "Media").mkdir()
            (root / "Media" / "level2").write_bytes(b"one")
            (root / "Media" / "LEVEL2").write_bytes(b"two")
            with self.assertRaisesRegex(audit.AuditError, "case-insensitive"):
                audit.inventory_tree(root)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "tree"
            root.mkdir()
            outside = Path(temp) / "outside"
            outside.write_bytes(b"private")
            (root / "linked").symlink_to(outside)
            with self.assertRaisesRegex(audit.AuditError, "symlink"):
                audit.inventory_tree(root)

    def test_cli_writes_metadata_report_and_nonzero_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "base"
            candidate = Path(temp) / "candidate"
            base.mkdir()
            candidate.mkdir()
            self.make_tree(base, {"eboot.bin": b"a"})
            self.make_tree(candidate, {"eboot.bin": b"b"})
            output = Path(temp) / "report.json"
            code = audit.main([str(base), str(candidate), "--require", "eboot.bin",
                               "--output", str(output)])
            self.assertEqual(code, 2)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["result"], "FAIL")
            self.assertNotIn(str(temp), output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
