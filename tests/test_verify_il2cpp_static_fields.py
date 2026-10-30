import sys
import json
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_il2cpp_static_fields as verifier


DUMP = """\
// Namespace: TheForest
public class DebugConsole : MonoBehaviour
{
    private static DebugConsole Instance; // 0x10
    private static bool DebugEnabled; // 0x18
    private void OnDestroy() { }
}

// Namespace: TheForest.Cheats
public class Cheats
{
    public static bool DebugConsole; // 0x10
}

// Namespace: TheForest.Network
public class CoopPeerStarter
{
    public static bool DedicatedHost; // 0x1
}
"""


class VerifyIl2CppStaticFieldsTests(unittest.TestCase):
    def setUp(self):
        self.fields = verifier.parse_dump_fields(DUMP)

    def test_parser_captures_namespace_staticness_and_declared_offset(self):
        records = {(field.type_name, field.field_name): field
                   for field in self.fields}
        instance = records[("TheForest.DebugConsole", "Instance")]
        self.assertTrue(instance.is_static)
        self.assertEqual(instance.declared_offset, 0x10)
        self.assertIn(("TheForest.Cheats.Cheats", "DebugConsole"), records)
        self.assertEqual(records[("TheForest.Network.CoopPeerStarter",
                                  "DedicatedHost")].declared_offset, 0x1)

    def test_verifies_field_identity_and_optional_dump_offset(self):
        expected = {
            "metadata_version": 23,
            "metadata_sha256": "ab" * 32,
            "fields": [
                {"type_suffix": "DebugConsole", "field": "Instance",
                 "static": True, "dump_offset": "0x10"},
                {"type_suffix": "Cheats", "field": "DebugConsole",
                 "static": True, "native_evidence": "native storage note"},
                {"type_suffix": "CoopPeerStarter", "field": "DedicatedHost",
                 "static": True},
            ],
        }
        results, valid = verifier.verify_expected_fields(
            self.fields, expected, 23, "ab" * 32)
        self.assertTrue(valid)
        self.assertTrue(all(result["status"] == "verified" for result in results))
        self.assertEqual(results[1]["native_evidence_note"], "native storage note")

    def test_rejects_metadata_hash_mismatch(self):
        expected = {"metadata_sha256": "ab" * 32, "fields": []}
        results, valid = verifier.verify_expected_fields(
            self.fields, expected, 23, "cd" * 32)
        self.assertFalse(valid)
        self.assertEqual(results[0]["field"], "<metadata SHA-256>")

    def test_repository_manifest_is_bound_to_the_recorded_ps4_metadata(self):
        manifest_path = Path(__file__).resolve().parents[1] / "docs/PS4_STATIC_FIELD_EXPECTATIONS.json"
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))
        results, valid = verifier.verify_expected_fields(
            self.fields, expected, 23, expected["metadata_sha256"])
        self.assertTrue(valid)
        self.assertEqual([result["field"] for result in results],
                         ["DebugConsole", "Instance"])

    def test_rejects_mismatched_metadata_version(self):
        expected = {"metadata_version": 24, "fields": []}
        results, valid = verifier.verify_expected_fields(self.fields, expected, 23)
        self.assertFalse(valid)
        self.assertEqual(results[0]["status"], "mismatch")

    def test_rejects_non_static_or_missing_field(self):
        expected = {"fields": [
            {"type_suffix": "DebugConsole", "field": "Instance", "static": False},
            {"type_suffix": "DebugConsole", "field": "Missing", "static": True},
        ]}
        results, valid = verifier.verify_expected_fields(self.fields, expected, 23)
        self.assertFalse(valid)
        self.assertEqual([result["status"] for result in results],
                         ["mismatch", "not found"])

    def test_ambiguous_type_suffix_is_not_silently_accepted(self):
        fields = self.fields + [verifier.FieldRecord(
            "Other.DebugConsole", "Instance", True, 0x10, "static Instance;")]
        expected = {"fields": [
            {"type_suffix": "DebugConsole", "field": "Instance", "static": True}
        ]}
        results, valid = verifier.verify_expected_fields(fields, expected, 23)
        self.assertFalse(valid)
        self.assertEqual(results[0]["status"], "ambiguous")

    def test_offset_mismatch_is_reported_separately_from_field_name(self):
        expected = {"fields": [
            {"type_suffix": "Cheats", "field": "DebugConsole",
             "static": True, "dump_offset": "0x18"}
        ]}
        results, valid = verifier.verify_expected_fields(self.fields, expected, 23)
        self.assertFalse(valid)
        self.assertEqual(results[0]["status"], "mismatch")
        self.assertIn("mismatch", results[0]["dump_offset_check"])


if __name__ == "__main__":
    unittest.main()
