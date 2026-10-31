"""Synthetic policy-gate tests; these do not create or inspect a real PKG."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_ps4_test_eligibility as gate


class PhysicalTestEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.private = Path(self.temp.name) / "private"
        self.private.mkdir()
        self.report = self.root / "docs" / "proof.md"
        self.report.parent.mkdir()
        self.report.write_text("Synthetic evidence placeholder.\n", encoding="utf-8")
        self.package = self.private / "candidate.pkg"
        self.package.write_bytes(b"synthetic-only; not a PS4 package")
        self.next_menu = self.private / "menu-candidate.pkg"
        self.next_menu.write_bytes(b"synthetic-only menu candidate")

    def tearDown(self):
        self.temp.cleanup()

    def artifact(self, path: Path) -> dict:
        return {"path": str(path), "sha256": gate.sha256_file(path)}

    def check(self) -> dict:
        return {"result": "PASS", "report": "docs/proof.md",
                "sha256": gate.sha256_file(self.report)}

    def checks(self, names: tuple[str, ...]) -> dict:
        return {name: self.check() for name in names}

    def first_menu_manifest(self) -> dict:
        return {
            "schema": 1,
            "test_kind": "first_menu",
            "package": {**self.artifact(self.package),
                        "function": "First UCM panel; L1+R1 opens and closes it",
                        "contains_graphical_ucm": True,
                        "contains_l1_r1_open_close": True},
            "physical_question": "Does the integrated host callback render from the loaded game scene on this console?",
            "expected_result": "A readable UCM panel appears and L1+R1 opens or closes it without stopping gameplay.",
            "failure_recovery": "Exit the title, remove only this test update, then restore the verified original CUSA12398 package.",
            "offline_checks": self.checks(gate.MENU_CHECKS),
        }

    def test_missing_manifest_is_blocked_without_install_authority(self):
        result = gate.evaluate({}, self.root)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertFalse(result["install_authorized"])

    def test_complete_first_menu_is_only_eligible_for_explicit_review(self):
        result = gate.evaluate(self.first_menu_manifest(), self.root)
        self.assertEqual(result["decision"], "ELIGIBLE_FOR_EXPLICIT_USER_REVIEW")
        self.assertFalse(result["install_authorized"])

    def test_first_menu_without_real_graphics_or_chord_is_blocked(self):
        manifest = self.first_menu_manifest()
        manifest["package"]["contains_graphical_ucm"] = False
        result = gate.evaluate(manifest, self.root)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("does not declare the first graphical UCM", result["reasons"][0])

    def test_changed_evidence_report_invalidates_prior_pass(self):
        manifest = self.first_menu_manifest()
        self.report.write_text("changed after validation\n", encoding="utf-8")
        result = gate.evaluate(manifest, self.root)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("unity_asset_graph", result["reasons"][0])

    def test_package_hash_mismatch_is_blocked(self):
        manifest = self.first_menu_manifest()
        self.package.write_bytes(b"replaced package")
        result = gate.evaluate(manifest, self.root)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("SHA-256 does not match", result["reasons"][0])

    def test_private_package_inside_git_tree_is_blocked(self):
        copied = self.root / "leaked.pkg"
        copied.write_bytes(b"synthetic")
        manifest = self.first_menu_manifest()
        manifest["package"].update(self.artifact(copied))
        result = gate.evaluate(manifest, self.root)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("must remain outside", result["reasons"][0])

    def test_intermediate_requires_indispensability_and_ready_direct_menu_step(self):
        manifest = {
            "schema": 1,
            "test_kind": "indispensable_intermediate",
            "package": {**self.artifact(self.package),
                        "function": "Specific compatibility question"},
            "offline_checks": self.checks(gate.BASE_CHECKS),
            "intermediate": {
                "why_indispensable": "A named console-only installation condition remains unmeasurable offline.",
                "why_offline_cannot_answer": "No local or independent package tool exposes this OS decision.",
                "measurable_result": "The console reports whether this exact update is accepted.",
                "failure_recovery": "Remove the candidate update and restore the known-good original game package without touching saves.",
                "direct_next_step": "first_menu_graphics_test",
                "menu_candidate_ready": True,
                "menu_package": self.artifact(self.next_menu),
                "menu_offline_checks": self.checks(gate.MENU_CHECKS),
            },
        }
        result = gate.evaluate(manifest, self.root)
        self.assertEqual(result["decision"], "ELIGIBLE_FOR_EXPLICIT_USER_REVIEW")
        self.assertFalse(result["install_authorized"])

        del manifest["intermediate"]["why_offline_cannot_answer"]
        blocked = gate.evaluate(manifest, self.root)
        self.assertEqual(blocked["decision"], "BLOCKED")

    def test_evidence_path_escape_is_blocked(self):
        manifest = self.first_menu_manifest()
        manifest["offline_checks"]["unity_render_host"]["report"] = "../outside.md"
        result = gate.evaluate(manifest, self.root)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("unity_render_host", result["reasons"][0])

    def test_cli_rejects_private_manifest_inside_repository(self):
        manifest_path = self.root / "private-manifest.json"
        manifest_path.write_text(json.dumps(self.first_menu_manifest()), encoding="utf-8")
        output = StringIO()
        with redirect_stdout(output):
            code = gate.main([str(manifest_path), "--repo-root", str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn("must remain outside", output.getvalue())


if __name__ == "__main__":
    unittest.main()
