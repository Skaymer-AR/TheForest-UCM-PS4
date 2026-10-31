"""Synthetic-only tests for the read-only PlayMaker tail comparison."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_playmaker_fsm_tails as audit


class PlayMakerTailAuditTests(unittest.TestCase):
    def test_reports_equal_tails_without_emitting_raw_bytes(self):
        tail = bytes(range(audit.TAIL_SIZE))
        report = audit.compare_tails([
            ("level2", "PlayMakerFSM", tail),
            ("sharedassets2.assets", "FsmTemplate", tail),
        ])
        self.assertEqual(report["tail_samples"], 2)
        self.assertEqual(report["distinct_tail_values"], 1)
        self.assertTrue(report["all_tail_bytes_equal"])
        self.assertFalse(report["raw_tail_bytes_emitted"])
        self.assertEqual(len(report["distinct_tail_sha256"][0]), 64)

    def test_distinguishes_variant_tail_and_keeps_sample_counts(self):
        row_a = ("level2", "PlayMakerFSM", bytes(40))
        row_b = ("level7", "PlayMakerFSM", bytes([1]) + bytes(39))
        report = audit.compare_tails([row_a, row_b, row_a])
        self.assertEqual(report["tail_samples"], 3)
        self.assertEqual(report["distinct_tail_values"], 2)
        self.assertFalse(report["all_tail_bytes_equal"])
        self.assertEqual(report["samples_by_asset_and_type"][0]["count"], 2)

    def test_rejects_invalid_tail_size_and_unbounded_sample_count(self):
        with self.assertRaisesRegex(ValueError, "invalid PlayMaker tail"):
            audit.compare_tails([("level2", "PlayMakerFSM", bytes(39))])
        with self.assertRaisesRegex(ValueError, "sample count"):
            audit.compare_tails([("level2", "PlayMakerFSM", bytes(40))] *
                                (audit.MAX_TAILS + 1))


if __name__ == "__main__":
    unittest.main()
